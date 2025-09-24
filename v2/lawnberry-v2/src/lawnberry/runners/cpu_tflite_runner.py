"""CPU-based TensorFlow Lite detector fallback for LawnBerry Pi v2."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, MutableMapping, Optional

import numpy as np

try:  # pragma: no cover - OpenCV may be unavailable in CI but is required on device
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - fallback only used in testing
    cv2 = None  # type: ignore

LOGGER = logging.getLogger(__name__)

__all__ = ["CpuTFLiteDetector", "CpuTFLiteError"]


class CpuTFLiteError(RuntimeError):
    """Raised when the CPU TFLite detector cannot be initialised or executed."""


InterpreterFactory = Callable[[str], Any]
DEFAULT_MODEL_PATH = Path(os.getenv("LBY_TFLITE_MODEL", "/opt/lawnberry/models/mower_detect.tflite"))


class CpuTFLiteDetector:
    """TensorFlow Lite CPU fallback detector with graceful degradation."""

    def __init__(
        self,
        *,
        model_path: Optional[str | Path] = None,
        interpreter_factory: Optional[InterpreterFactory] = None,
        label_map: Optional[Mapping[int, str]] = None,
        score_threshold: float | None = None,
        input_mean: float = 127.5,
        input_std: float = 127.5,
    ) -> None:
        self._model_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
        self._interpreter_factory = interpreter_factory or self._default_interpreter_factory
        self._label_map: Dict[int, str] = dict(label_map or {})
        self._score_threshold = self._resolve_threshold(score_threshold)
        self._input_mean = input_mean
        self._input_std = input_std

        self._interpreter: Any | None = None
        self._input_details: List[MutableMapping[str, Any]] | None = None
        self._output_details: List[MutableMapping[str, Any]] | None = None
        self._input_shape: tuple[int, ...] | None = None
        self._input_dtype: Any | None = None

    def _resolve_threshold(self, configured: float | None) -> float:
        if configured is not None:
            if configured < 0 or configured > 1:
                raise ValueError("score_threshold must be between 0.0 and 1.0")
            return configured

        env_value = os.getenv("LBY_TFLITE_SCORE_THRESHOLD")
        if env_value:
            try:
                parsed = float(env_value)
            except ValueError as exc:
                raise CpuTFLiteError(
                    "LBY_TFLITE_SCORE_THRESHOLD must be a float between 0.0 and 1.0"
                ) from exc
            if parsed < 0 or parsed > 1:
                raise CpuTFLiteError(
                    "LBY_TFLITE_SCORE_THRESHOLD must be between 0.0 and 1.0"
                )
            return parsed

        return 0.5

    def _default_interpreter_factory(self, model_path: str) -> Any:
        try:
            from tflite_runtime.interpreter import Interpreter  # type: ignore
        except ImportError as exc:  # pragma: no cover - ensures clear error on device
            raise CpuTFLiteError(
                "tflite-runtime is required for CPU inference on Raspberry Pi"
            ) from exc

        num_threads = int(os.getenv("LBY_TFLITE_THREADS", "2"))
        return Interpreter(model_path=model_path, num_threads=num_threads)

    def _ensure_interpreter(self) -> Any:
        if self._interpreter is not None:
            return self._interpreter

        if not self._model_path.exists():
            LOGGER.warning("TFLite model not found at %s", self._model_path)

        try:
            interpreter = self._interpreter_factory(str(self._model_path))
        except Exception as exc:  # pragma: no cover - covered via tests raising
            raise CpuTFLiteError(f"Unable to create TFLite interpreter: {exc}") from exc

        try:
            interpreter.allocate_tensors()
        except Exception as exc:  # pragma: no cover - exercised via tests
            raise CpuTFLiteError("Failed to allocate tensors for TFLite interpreter") from exc

        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()
        if not input_details:
            raise CpuTFLiteError("Interpreter provided no input tensors")

        shape = tuple(int(dim) for dim in input_details[0]["shape"])
        if len(shape) != 4 or shape[0] != 1 or shape[3] != 3:
            raise CpuTFLiteError("TFLite model must accept [1, height, width, 3] input tensor")

        self._input_shape = shape
        self._input_dtype = input_details[0]["dtype"]
        self._interpreter = interpreter
        self._input_details = input_details
        self._output_details = output_details

        LOGGER.info(
            "CPU TFLite interpreter initialised: shape=%s, dtype=%s", shape, self._input_dtype
        )

        return interpreter

    def warmup(self) -> None:
        """Perform a single inference on a zero frame to prime the interpreter."""
        interpreter = self._ensure_interpreter()
        if self._input_shape is None:
            raise CpuTFLiteError("Interpreter input shape unavailable during warmup")

        height, width = self._input_shape[1], self._input_shape[2]
        zero_frame = np.zeros((height, width, 3), dtype=np.uint8)
        self._run_inference(interpreter, zero_frame, collect_outputs=False)

    def infer(self, frame_bgr: np.ndarray) -> List[Dict[str, Any]]:
        """Run inference on a BGR frame and return detected objects."""
        interpreter = self._ensure_interpreter()
        outputs = self._run_inference(interpreter, frame_bgr, collect_outputs=True)
        if outputs is None:
            return []
        return self._parse_detections(outputs)

    def _run_inference(
        self,
        interpreter: Any,
        frame_bgr: np.ndarray,
        *,
        collect_outputs: bool,
    ) -> Optional[Dict[str, np.ndarray]]:
        input_tensor = self._prepare_input(frame_bgr)
        assert self._input_details is not None
        interpreter.set_tensor(self._input_details[0]["index"], input_tensor)
        interpreter.invoke()
        if not collect_outputs:
            return None
        assert self._output_details is not None
        outputs: Dict[str, np.ndarray] = {}
        for detail in self._output_details:
            name = detail.get("name") or f"tensor_{detail['index']}"
            outputs[name] = interpreter.get_tensor(detail["index"])
        return outputs

    def _prepare_input(self, frame_bgr: np.ndarray) -> np.ndarray:
        if self._input_shape is None or self._input_dtype is None:
            raise CpuTFLiteError("Interpreter not initialised before preprocessing input")
        if frame_bgr.ndim != 3 or frame_bgr.shape[2] != 3:
            raise ValueError("Frame must be an HxWx3 BGR array")

        target_height, target_width = self._input_shape[1], self._input_shape[2]
        if frame_bgr.shape[0] != target_height or frame_bgr.shape[1] != target_width:
            frame_bgr = self._resize_frame(frame_bgr, target_width, target_height)

        tensor = frame_bgr.astype(np.float32)
        tensor = (tensor - self._input_mean) / self._input_std
        tensor = np.expand_dims(tensor, axis=0)
        return tensor.astype(np.float32)

    def _resize_frame(self, frame: np.ndarray, width: int, height: int) -> np.ndarray:
        if cv2 is not None:  # pragma: no cover - dependent on OpenCV availability
            return cv2.resize(frame, (width, height), interpolation=cv2.INTER_LINEAR)
        # Fallback nearest neighbour resize for testing environments
        y_idx = np.linspace(0, frame.shape[0] - 1, height)
        x_idx = np.linspace(0, frame.shape[1] - 1, width)
        xi, yi = np.meshgrid(x_idx, y_idx)
        xi = np.clip(np.rint(xi), 0, frame.shape[1] - 1).astype(int)
        yi = np.clip(np.rint(yi), 0, frame.shape[0] - 1).astype(int)
        return frame[yi, xi]

    def _parse_detections(self, outputs: Mapping[str, np.ndarray]) -> List[Dict[str, Any]]:
        boxes = self._extract_output(outputs, {"detection_boxes", "boxes"})
        scores = self._extract_output(outputs, {"detection_scores", "scores"})
        classes = self._extract_output(outputs, {"detection_classes", "classes"})
        count = self._extract_output(outputs, {"num_detections", "count"})

        if boxes is None or scores is None or classes is None or count is None:
            LOGGER.warning("Incomplete detection outputs from TFLite interpreter")
            return []

        boxes = np.squeeze(boxes, axis=0) if boxes.ndim == 3 else boxes
        scores = np.squeeze(scores, axis=0)
        classes = np.squeeze(classes, axis=0)

        detections: List[Dict[str, Any]] = []
        num = int(np.round(float(count.reshape(-1)[0])))
        for idx in range(min(num, scores.shape[0], boxes.shape[0], classes.shape[0])):
            score = float(scores[idx])
            if score < self._score_threshold:
                continue
            class_id = int(classes[idx])
            ymin, xmin, ymax, xmax = [float(v) for v in boxes[idx]]
            detections.append(
                {
                    "label": self._label_map.get(class_id, f"class_{class_id}"),
                    "confidence": score,
                    "bbox": {
                        "ymin": ymin,
                        "xmin": xmin,
                        "ymax": ymax,
                        "xmax": xmax,
                    },
                    "class_id": class_id,
                }
            )
        return detections

    @staticmethod
    def _extract_output(outputs: Mapping[str, np.ndarray], names: set[str]) -> np.ndarray | None:
        for name in names:
            if name in outputs:
                return outputs[name]
        return None
