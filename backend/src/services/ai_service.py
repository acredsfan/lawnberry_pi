"""AIService for LawnBerry Pi v2.

Provides a real, backend-first CPU inference path using a local JSON model
definition. The first implementation is intentionally simple and operationally
safe: it decodes an image, applies configured color-based rules, builds
detected-object results, and updates runtime statistics. Coral detection is
preserved for status reporting but does not block CPU inference.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError

from ..models import (
    AcceleratorStatus,
    AIAccelerator,
    AIProcessing,
    BoundingBox,
    DetectedObject,
    InferenceResult,
    InferenceTask,
    ModelFormat,
    ModelInfo,
    ModelStatus,
)
from .camera_stream_service import camera_service

logger = logging.getLogger(__name__)


class AIServiceError(Exception):
    """Base AI service error."""


class AIModelNotReadyError(AIServiceError):
    """Raised when inference is requested without a loadable model."""


class AIInferenceInputError(AIServiceError):
    """Raised when an inference request is malformed or unsupported."""


class AINoFrameAvailableError(AIServiceError):
    """Raised when latest-frame inference is requested without a camera frame."""


class AIService:
    """AI processing service"""

    def __init__(
        self,
        model_path: str | None = None,
        confidence_threshold: float | None = None,
        max_detections: int | None = None,
    ):
        env_confidence = self._read_float_env("AI_CONFIDENCE_THRESHOLD", 0.5)
        env_max_detections = self._read_int_env("AI_MAX_DETECTIONS", 10)

        self.ai_processing = AIProcessing(
            confidence_threshold=confidence_threshold
            if confidence_threshold is not None
            else env_confidence,
            max_detections=max_detections if max_detections is not None else env_max_detections,
        )
        self.initialized = False
        self.last_error: str | None = None
        self.model_path = Path(
            model_path or os.getenv("AI_MODEL_PATH") or "config/ai_heuristic_model.json"
        )
        self.model_definition: dict[str, Any] | None = None
        self.active_model_name: str | None = None

    async def initialize(self) -> bool:
        """Initialize AI service"""
        logger.info("Initializing AI service")
        self.ai_processing.system_enabled = os.getenv("AI_INFERENCE_ENABLED", "1") != "0"

        # Detect Coral USB presence (best-effort, non-fatal)
        try:
            coral_present = False
            # Quick heuristic: check common device nodes
            possible = [
                "/dev/apex_0",
                "/dev/usb-accelerator",
            ]
            for p in possible:
                if os.path.exists(p):
                    coral_present = True
                    break
            # Populate accelerator status map
            self.ai_processing.accelerator_status[AIAccelerator.CPU] = AcceleratorStatus(
                accelerator_type=AIAccelerator.CPU, is_available=True
            )
            self.ai_processing.accelerator_status[AIAccelerator.CORAL_USB] = AcceleratorStatus(
                accelerator_type=AIAccelerator.CORAL_USB,
                is_available=coral_present,
                device_path=possible[0] if coral_present else None,
            )
            # Select best accelerator
            self.ai_processing.primary_accelerator = self.ai_processing.get_best_accelerator()
        except Exception as exc:
            # Default to CPU
            self.ai_processing.primary_accelerator = AIAccelerator.CPU
            self.last_error = str(exc)

        if self.ai_processing.system_enabled:
            await self._load_configured_model()

        self.initialized = True
        return True

    async def get_ai_status(self) -> dict[str, Any]:
        """Get current AI processing status"""
        if not self.initialized:
            await self.initialize()

        return {
            "initialized": self.initialized,
            "system_enabled": self.ai_processing.system_enabled,
            "primary_accelerator": self.ai_processing.primary_accelerator,
            "fallback_accelerator": self.ai_processing.fallback_accelerator,
            "processing_fps": self.ai_processing.processing_fps,
            "configured_model_path": str(self.model_path),
            "model_ready": self.active_model_name is not None,
            "active_model_name": self.active_model_name,
            "active_models": {
                name: model.model_dump(mode="json")
                for name, model in self.ai_processing.active_models.items()
            },
            "accelerators": {
                accelerator.value
                if hasattr(accelerator, "value")
                else str(accelerator): status.model_dump(mode="json")
                for accelerator, status in self.ai_processing.accelerator_status.items()
            },
            "performance": self.ai_processing.get_inference_performance(),
            "recent_results_count": len(self.ai_processing.recent_results),
            "last_error": self.last_error,
        }

    async def infer_image_bytes(
        self,
        image_bytes: bytes,
        *,
        task: InferenceTask = InferenceTask.OBSTACLE_DETECTION,
        frame_id: str | None = None,
        confidence_threshold: float | None = None,
    ) -> InferenceResult:
        """Run inference on uploaded image bytes."""
        if not image_bytes:
            raise AIInferenceInputError("Image payload is empty")

        await self._ensure_model_ready(task)
        assert self.model_definition is not None  # Narrowed by _ensure_model_ready

        threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else self.ai_processing.confidence_threshold
        )
        started = time.perf_counter()

        try:
            preprocess_start = time.perf_counter()
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            original_width, original_height = image.size
            input_width = int(self.model_definition["input_width"])
            input_height = int(self.model_definition["input_height"])
            resized = image.resize((input_width, input_height))
            rgb = np.asarray(resized, dtype=np.uint8)
            preprocessing_time_ms = (time.perf_counter() - preprocess_start) * 1000.0
        except UnidentifiedImageError as exc:
            raise AIInferenceInputError(f"Unsupported image payload: {exc}") from exc
        except Exception as exc:
            raise AIInferenceInputError(f"Unable to decode image payload: {exc}") from exc

        inference_start = time.perf_counter()
        detected_objects = self._run_custom_inference(rgb, threshold)
        inference_time_ms = (time.perf_counter() - inference_start) * 1000.0

        postprocess_start = time.perf_counter()
        detected_objects = detected_objects[: self.ai_processing.max_detections]
        postprocessing_time_ms = (time.perf_counter() - postprocess_start) * 1000.0
        total_time_ms = (time.perf_counter() - started) * 1000.0

        result = InferenceResult(
            inference_id=str(uuid.uuid4()),
            task=task,
            model_name=self.active_model_name or self.model_definition["model_name"],
            input_frame_id=frame_id or f"upload-{uuid.uuid4().hex[:8]}",
            input_width=original_width,
            input_height=original_height,
            detected_objects=detected_objects,
            inference_time_ms=inference_time_ms,
            preprocessing_time_ms=preprocessing_time_ms,
            postprocessing_time_ms=postprocessing_time_ms,
            total_time_ms=total_time_ms,
            model_version=str(self.model_definition.get("version", "1.0")),
            confidence_threshold=threshold,
        )

        self.ai_processing.add_inference_result(result)
        self._update_runtime_statistics(total_time_ms)
        return result

    async def infer_latest_frame(
        self,
        *,
        task: InferenceTask = InferenceTask.OBSTACLE_DETECTION,
        confidence_threshold: float | None = None,
    ) -> InferenceResult:
        """Run inference on the latest available camera frame."""
        frame = await camera_service.get_current_frame()
        if frame is None:
            raise AINoFrameAvailableError("No camera frame available for inference")

        frame_bytes: bytes | None = None
        if hasattr(frame, "get_frame_data"):
            frame_bytes = frame.get_frame_data()
        elif isinstance(getattr(frame, "data", None), bytes):
            frame_bytes = frame.data
        elif isinstance(getattr(frame, "data", None), str):
            try:
                frame_bytes = base64.b64decode(frame.data)
            except Exception as exc:
                raise AIInferenceInputError(
                    f"Unable to decode camera frame payload: {exc}"
                ) from exc

        if not frame_bytes:
            raise AINoFrameAvailableError("No camera frame available for inference")

        return await self.infer_image_bytes(
            frame_bytes,
            task=task,
            frame_id=getattr(frame.metadata, "frame_id", None),
            confidence_threshold=confidence_threshold,
        )

    async def get_recent_results(self, limit: int = 10) -> list[InferenceResult]:
        """Return recent inference results, newest first."""
        bounded_limit = max(1, min(limit, 50))
        return list(reversed(self.ai_processing.recent_results[-bounded_limit:]))

    async def _ensure_model_ready(self, task: InferenceTask) -> None:
        if not self.initialized:
            await self.initialize()

        if not self.ai_processing.system_enabled:
            raise AIModelNotReadyError("AI inference is disabled by configuration")

        if self.active_model_name is None or self.model_definition is None:
            raise AIModelNotReadyError(f"No AI model is loaded from '{self.model_path}'")

        model_task = self.model_definition.get("task", InferenceTask.OBSTACLE_DETECTION.value)
        if model_task != task.value:
            raise AIInferenceInputError(f"Loaded model supports '{model_task}', not '{task.value}'")

    async def _load_configured_model(self) -> None:
        """Load the configured local model definition if present."""
        if not self.model_path.exists():
            self.last_error = f"Configured AI model not found at {self.model_path}"
            logger.warning(self.last_error)
            return

        try:
            payload = json.loads(self.model_path.read_text(encoding="utf-8"))
            model_info = self._build_model_info(payload)
            model_info.status = ModelStatus.LOADED
            model_info.load_time = model_info.load_time or datetime.now(UTC)
            self.ai_processing.active_models[model_info.model_name] = model_info
            self.ai_processing.primary_accelerator = AIAccelerator.CPU
            self.active_model_name = model_info.model_name
            self.model_definition = payload
            self.last_error = None
        except Exception as exc:
            self.last_error = f"Failed to load AI model definition: {exc}"
            logger.exception(self.last_error)

    def _build_model_info(self, payload: dict[str, Any]) -> ModelInfo:
        """Translate JSON model metadata into ModelInfo."""
        required = ["model_name", "input_width", "input_height", "class_labels", "task", "rules"]
        missing = [field for field in required if field not in payload]
        if missing:
            raise ValueError(f"Model definition missing required fields: {', '.join(missing)}")

        if not payload.get("rules"):
            raise ValueError("Model definition must include at least one inference rule")

        return ModelInfo(
            model_name=str(payload["model_name"]),
            model_path=str(self.model_path),
            format=ModelFormat(payload.get("model_format", ModelFormat.CUSTOM.value)),
            version=str(payload.get("version", "1.0")),
            input_width=int(payload["input_width"]),
            input_height=int(payload["input_height"]),
            input_channels=3,
            num_classes=len(payload["class_labels"]),
            class_labels=[str(label) for label in payload["class_labels"]],
            target_accelerator=AIAccelerator.CPU,
            status=ModelStatus.LOADING,
        )

    def _run_custom_inference(
        self,
        rgb_image: np.ndarray,
        confidence_threshold: float,
    ) -> list[DetectedObject]:
        """Apply JSON-configured RGB rules and emit detected objects."""
        if self.model_definition is None:
            raise AIModelNotReadyError("Model definition is not loaded")

        detected: list[DetectedObject] = []
        image_height, image_width = rgb_image.shape[:2]
        max_detections = self.ai_processing.max_detections

        for rule in self.model_definition.get("rules", []):
            mask = self._rule_mask(rgb_image, rule)
            components = self._extract_components(mask)
            min_area_ratio = float(rule.get("min_area_ratio", 0.002))
            max_components = int(rule.get("max_components", max_detections))

            for component in components[:max_components]:
                area_ratio = component["area"] / float(image_height * image_width)
                confidence = float(min(0.99, max(0.0, area_ratio / max(min_area_ratio, 1e-6))))
                if area_ratio < min_area_ratio or confidence < confidence_threshold:
                    continue

                x_min, y_min, x_max, y_max = component["bbox"]
                detected.append(
                    DetectedObject(
                        object_id=str(uuid.uuid4()),
                        class_name=str(rule["class_name"]),
                        confidence=confidence,
                        bounding_box=BoundingBox(
                            x=x_min / image_width,
                            y=y_min / image_height,
                            width=max((x_max - x_min + 1) / image_width, 1.0 / image_width),
                            height=max((y_max - y_min + 1) / image_height, 1.0 / image_height),
                        ),
                    )
                )

        detected.sort(key=lambda item: item.confidence, reverse=True)
        return detected[:max_detections]

    def _rule_mask(self, rgb_image: np.ndarray, rule: dict[str, Any]) -> np.ndarray:
        """Build a boolean mask for a single RGB threshold rule."""
        min_rgb = np.array(rule.get("min_rgb", [0, 0, 0]), dtype=np.uint8)
        max_rgb = np.array(rule.get("max_rgb", [255, 255, 255]), dtype=np.uint8)
        return np.all(rgb_image >= min_rgb, axis=2) & np.all(rgb_image <= max_rgb, axis=2)

    def _extract_components(self, mask: np.ndarray) -> list[dict[str, Any]]:
        """Extract connected components from a binary mask."""
        height, width = mask.shape
        visited = np.zeros_like(mask, dtype=bool)
        components: list[dict[str, Any]] = []

        for y in range(height):
            for x in range(width):
                if not mask[y, x] or visited[y, x]:
                    continue

                stack = [(x, y)]
                visited[y, x] = True
                area = 0
                min_x = max_x = x
                min_y = max_y = y

                while stack:
                    current_x, current_y = stack.pop()
                    area += 1
                    min_x = min(min_x, current_x)
                    max_x = max(max_x, current_x)
                    min_y = min(min_y, current_y)
                    max_y = max(max_y, current_y)

                    for next_x, next_y in (
                        (current_x - 1, current_y),
                        (current_x + 1, current_y),
                        (current_x, current_y - 1),
                        (current_x, current_y + 1),
                    ):
                        if 0 <= next_x < width and 0 <= next_y < height:
                            if mask[next_y, next_x] and not visited[next_y, next_x]:
                                visited[next_y, next_x] = True
                                stack.append((next_x, next_y))

                components.append(
                    {
                        "area": area,
                        "bbox": (min_x, min_y, max_x, max_y),
                    }
                )

        components.sort(key=lambda item: item["area"], reverse=True)
        return components

    def _update_runtime_statistics(self, total_time_ms: float) -> None:
        """Update AIProcessing and accelerator runtime statistics."""
        self.ai_processing.processing_fps = 1000.0 / total_time_ms if total_time_ms > 0 else 0.0

        cpu_status = self.ai_processing.accelerator_status.setdefault(
            AIAccelerator.CPU,
            AcceleratorStatus(accelerator_type=AIAccelerator.CPU, is_available=True),
        )
        cpu_status.inference_count += 1
        cpu_status.total_inference_time_ms += total_time_ms
        cpu_status.average_inference_time_ms = (
            cpu_status.total_inference_time_ms / cpu_status.inference_count
        )

    @staticmethod
    def _read_float_env(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _read_int_env(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except (TypeError, ValueError):
            return default


_ai_service_instance: AIService | None = None


def get_ai_service() -> AIService:
    """Return the singleton AI service instance."""
    global _ai_service_instance
    if _ai_service_instance is None:
        _ai_service_instance = AIService()
    return _ai_service_instance
