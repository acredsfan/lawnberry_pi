"""Configured production object-detector runtime.

Only real ONNX model execution is supported here.  Missing configuration,
model artifacts, OpenCV DNN support, or invalid output shapes remain explicit
unavailable states; this module never substitutes a heuristic detector.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DetectorRuntimeError(RuntimeError):
    """Raised when a configured detector cannot load or execute truthfully."""


class DetectorManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str = Field(min_length=1)
    model_path: str = Field(min_length=1)
    model_format: Literal["onnx"] = "onnx"
    runtime: Literal["opencv_dnn"] = "opencv_dnn"
    version: str = "1.0"
    task: Literal["obstacle_detection"] = "obstacle_detection"
    input_width: int = Field(gt=0)
    input_height: int = Field(gt=0)
    class_labels: list[str] = Field(min_length=1)
    output_format: Literal["xyxy", "yolov5", "yolov8"] = "yolov8"
    camera_horizontal_fov_degrees: float = Field(default=62.0, gt=1.0, lt=179.0)
    class_height_m: dict[str, float] = Field(default_factory=dict)
    semantic_cost_multipliers: dict[str, float] = Field(default_factory=dict)
    nms_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    max_result_age_seconds: float = Field(default=2.0, gt=0.0)

    @field_validator("class_labels")
    @classmethod
    def validate_labels(cls, labels: list[str]) -> list[str]:
        cleaned = [label.strip() for label in labels]
        if any(not label for label in cleaned) or len(set(cleaned)) != len(cleaned):
            raise ValueError("class_labels must contain unique non-empty labels")
        return cleaned

    @field_validator("class_height_m", "semantic_cost_multipliers")
    @classmethod
    def validate_positive_mapping(cls, values: dict[str, float]) -> dict[str, float]:
        if any(float(value) <= 0 for value in values.values()):
            raise ValueError("detector class mappings must contain positive values")
        return values

    @model_validator(mode="after")
    def validate_class_mappings(self) -> DetectorManifest:
        mapped_classes = set(self.class_height_m) | set(self.semantic_cost_multipliers)
        unknown = mapped_classes - set(self.class_labels)
        if unknown:
            raise ValueError(f"detector class mappings reference unknown labels: {sorted(unknown)}")
        if any(value < 1.0 for value in self.semantic_cost_multipliers.values()):
            raise ValueError("semantic_cost_multipliers cannot reduce route cost below 1.0")
        return self


@dataclass(frozen=True, slots=True)
class RuntimeDetection:
    class_name: str
    confidence: float
    x: float
    y: float
    width: float
    height: float


class DetectorRuntime(Protocol):
    manifest: DetectorManifest
    model_path: Path
    model_sha256: str
    ready: bool
    last_error: str | None

    def initialize(self) -> None: ...

    def infer(self, rgb_image: np.ndarray, confidence_threshold: float) -> list[RuntimeDetection]: ...


def _box_iou(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])
    intersection = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    box_area = max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])
    areas = np.maximum(0.0, boxes[:, 2] - boxes[:, 0]) * np.maximum(
        0.0, boxes[:, 3] - boxes[:, 1]
    )
    union = box_area + areas - intersection
    return np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)


def _nms(rows: list[tuple[np.ndarray, float, int]], threshold: float) -> list[int]:
    if not rows:
        return []
    boxes = np.stack([row[0] for row in rows])
    scores = np.asarray([row[1] for row in rows])
    classes = np.asarray([row[2] for row in rows])
    keep: list[int] = []
    for class_id in np.unique(classes):
        indices = np.where(classes == class_id)[0]
        order = indices[np.argsort(scores[indices])[::-1]]
        while order.size:
            current = int(order[0])
            keep.append(current)
            if order.size == 1:
                break
            remaining = order[1:]
            order = remaining[_box_iou(boxes[current], boxes[remaining]) <= threshold]
    keep.sort(key=lambda index: rows[index][1], reverse=True)
    return keep


def parse_detector_output(
    output: Any,
    *,
    manifest: DetectorManifest,
    confidence_threshold: float,
    nms_threshold: float,
) -> list[RuntimeDetection]:
    """Normalize common ONNX detector outputs into typed normalized boxes."""
    if isinstance(output, (list, tuple)):
        if not output:
            return []
        output = output[0]
    array = np.asarray(output, dtype=np.float32)
    while array.ndim > 2 and array.shape[0] == 1:
        array = array[0]
    if array.ndim != 2:
        raise DetectorRuntimeError(f"Unsupported detector output shape {array.shape}")

    class_count = len(manifest.class_labels)
    expected_features = 6 if manifest.output_format == "xyxy" else (
        5 + class_count if manifest.output_format == "yolov5" else 4 + class_count
    )
    if array.shape[1] != expected_features and array.shape[0] == expected_features:
        array = array.T
    if array.shape[1] < expected_features:
        raise DetectorRuntimeError(
            f"Detector output has {array.shape[1]} features; expected {expected_features}"
        )

    width = float(manifest.input_width)
    height = float(manifest.input_height)
    candidates: list[tuple[np.ndarray, float, int]] = []
    for row in array:
        if manifest.output_format == "xyxy":
            x1, y1, x2, y2, confidence, class_value = row[:6]
            class_id = int(class_value)
        else:
            center_x, center_y, box_width, box_height = row[:4]
            if manifest.output_format == "yolov5":
                class_scores = row[5 : 5 + class_count]
                class_id = int(np.argmax(class_scores))
                confidence = float(row[4]) * float(class_scores[class_id])
            else:
                class_scores = row[4 : 4 + class_count]
                class_id = int(np.argmax(class_scores))
                confidence = float(class_scores[class_id])
            x1 = center_x - box_width / 2.0
            y1 = center_y - box_height / 2.0
            x2 = center_x + box_width / 2.0
            y2 = center_y + box_height / 2.0

        confidence = float(confidence)
        if confidence < confidence_threshold or not 0 <= class_id < class_count:
            continue
        box = np.asarray([x1, y1, x2, y2], dtype=np.float32)
        if float(np.max(np.abs(box))) <= 1.5:
            box[[0, 2]] *= width
            box[[1, 3]] *= height
        box[0::2] = np.clip(box[0::2], 0.0, width)
        box[1::2] = np.clip(box[1::2], 0.0, height)
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        candidates.append((box, confidence, class_id))

    detections: list[RuntimeDetection] = []
    for index in _nms(candidates, nms_threshold):
        box, confidence, class_id = candidates[index]
        detections.append(
            RuntimeDetection(
                class_name=manifest.class_labels[class_id],
                confidence=min(1.0, max(0.0, confidence)),
                x=float(box[0] / width),
                y=float(box[1] / height),
                width=float((box[2] - box[0]) / width),
                height=float((box[3] - box[1]) / height),
            )
        )
    return detections


class OpenCVDnnDetectorRuntime:
    """OpenCV DNN ONNX runtime loaded from a validated local manifest."""

    def __init__(self, manifest_path: str | Path) -> None:
        self.manifest_path = Path(manifest_path)
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.manifest = DetectorManifest.model_validate(payload)
        configured_model = Path(self.manifest.model_path)
        self.model_path = (
            configured_model
            if configured_model.is_absolute()
            else (self.manifest_path.parent / configured_model).resolve()
        )
        self.model_sha256 = ""
        self.ready = False
        self.last_error: str | None = None
        self._cv2: Any = None
        self._network: Any = None

    def initialize(self) -> None:
        self.load_metadata()
        try:
            import cv2
        except ImportError as exc:
            raise DetectorRuntimeError(
                "OpenCV DNN runtime unavailable; install Raspberry Pi OS python3-opencv"
            ) from exc
        try:
            self._network = cv2.dnn.readNetFromONNX(str(self.model_path))
            self._cv2 = cv2
            self.ready = True
            self.last_error = None
        except Exception as exc:
            self.ready = False
            self.last_error = str(exc)
            raise DetectorRuntimeError(f"Failed to load ONNX detector: {exc}") from exc

    def load_metadata(self) -> None:
        """Validate and hash the artifact without allocating an inference network."""
        if not self.model_path.is_file():
            raise DetectorRuntimeError(f"Configured detector model not found: {self.model_path}")
        try:
            # Models can be hundreds of MiB on a Pi. Hash the artifact as a
            # stream so provenance validation never duplicates it in memory.
            with self.model_path.open("rb") as artifact:
                self.model_sha256 = hashlib.file_digest(artifact, "sha256").hexdigest()
            self.last_error = None
        except Exception as exc:
            self.last_error = str(exc)
            raise DetectorRuntimeError(f"Failed to validate ONNX detector: {exc}") from exc

    def infer(self, rgb_image: np.ndarray, confidence_threshold: float) -> list[RuntimeDetection]:
        if not self.ready or self._network is None or self._cv2 is None:
            raise DetectorRuntimeError("Detector runtime is not ready")
        blob = self._cv2.dnn.blobFromImage(
            rgb_image,
            scalefactor=1.0 / 255.0,
            size=(self.manifest.input_width, self.manifest.input_height),
            mean=(0.0, 0.0, 0.0),
            swapRB=False,
            crop=False,
        )
        self._network.setInput(blob)
        output = self._network.forward()
        return parse_detector_output(
            output,
            manifest=self.manifest,
            confidence_threshold=confidence_threshold,
            nms_threshold=self.manifest.nms_threshold,
        )


__all__ = [
    "DetectorManifest",
    "DetectorRuntime",
    "DetectorRuntimeError",
    "OpenCVDnnDetectorRuntime",
    "RuntimeDetection",
    "parse_detector_output",
]
