"""AIService for LawnBerry Pi v2.

Provides a configured ONNX detector runtime, frame-bound typed results, and
truthful unavailable state. No heuristic detector or fabricated training data
is substituted when configuration, model artifacts, or runtime support is absent.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import logging
import math
import os
import time
import uuid
from collections.abc import Awaitable, Callable
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
    PerceptionSnapshot,
)
from .detector_runtime import (
    DetectorRuntime,
    DetectorRuntimeError,
    OpenCVDnnDetectorRuntime,
)

logger = logging.getLogger(__name__)


class AIServiceError(Exception):
    """Base AI service error."""


class AIModelNotReadyError(AIServiceError):
    """Raised when inference is requested without a loadable model."""


class AIInferenceInputError(AIServiceError):
    """Raised when an inference request is malformed or unsupported."""


class AINoFrameAvailableError(AIServiceError):
    """Raised when latest-frame inference is requested without a camera frame."""


CameraFrameProvider = Callable[[], Awaitable[Any | None]]
PerceptionResultConsumer = Callable[[InferenceResult], Any]


class AIService:
    """AI processing service"""

    def __init__(
        self,
        model_path: str | None = None,
        confidence_threshold: float | None = None,
        max_detections: int | None = None,
        camera_frame_provider: CameraFrameProvider | None = None,
        detector_runtime: DetectorRuntime | None = None,
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
        self._configured_enabled = os.getenv("AI_INFERENCE_ENABLED", "1") != "0"
        self.model_path = Path(
            model_path or os.getenv("AI_MODEL_CONFIG") or "config/ai_detector.json"
        )
        self.active_model_name: str | None = None
        self._detector_runtime = detector_runtime
        self._external_owner = False
        self._external_owner_sim_mode = True
        self._external_owner_hardware_available = False
        self._external_owner_ai_runtime_ready = False
        self._external_owner_model_sha256: str | None = None
        self._external_owner_error: str | None = None
        self._camera_frame_provider = camera_frame_provider
        self._result_consumer: PerceptionResultConsumer | None = None
        self._route_cost_obstacle_count = 0
        # Serialize all inference sources (API and sampled camera frames). The
        # image work itself runs in a worker thread so it cannot stall the
        # backend event loop.
        self._inference_lock = asyncio.Lock()
        self._inference_tasks: set[asyncio.Task[InferenceResult]] = set()

    async def initialize(self, *, metadata_only: bool = False) -> bool:
        """Initialize AI service"""
        logger.info("Initializing AI service")
        self._configured_enabled = os.getenv("AI_INFERENCE_ENABLED", "1") != "0"
        self.ai_processing.system_enabled = self._configured_enabled

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
            self._external_owner = bool(metadata_only)
            await self._load_configured_model(metadata_only=metadata_only)

        self.initialized = True
        return True

    def set_enabled(self, enabled: bool) -> None:
        """Soft-enable or soft-disable AI inference without restarting the service.

        Called by PowerManager to disable inference when the mower is idle at
        night and re-enable it when a mission begins.  The model stays loaded
        in memory so re-enabling is instantaneous.
        """
        effective_enabled = bool(enabled) and self._configured_enabled
        if self.ai_processing.system_enabled == effective_enabled:
            return
        self.ai_processing.system_enabled = effective_enabled
        logger.info("AIService: system_enabled set to %s by PowerManager", effective_enabled)

    async def get_ai_status(self) -> dict[str, Any]:
        """Get current AI processing status"""
        if not self.initialized:
            await self.initialize()

        perception = self.get_perception_snapshot()
        runtime = self._detector_runtime
        return {
            "initialized": self.initialized,
            "configured_enabled": self._configured_enabled,
            "system_enabled": self.ai_processing.system_enabled,
            "primary_accelerator": self.ai_processing.primary_accelerator,
            "fallback_accelerator": self.ai_processing.fallback_accelerator,
            "processing_fps": self.ai_processing.processing_fps,
            "configured_model_path": str(self.model_path),
            "model_ready": self._model_ready(),
            "execution_owner": "camera_ipc" if self._external_owner else "backend",
            "owner_sim_mode": self._external_owner_sim_mode if self._external_owner else None,
            "owner_hardware_available": (
                self._external_owner_hardware_available if self._external_owner else None
            ),
            "owner_ai_runtime_ready": (
                self._external_owner_ai_runtime_ready if self._external_owner else None
            ),
            "owner_ai_runtime_error": self._external_owner_error if self._external_owner else None,
            "active_model_name": self.active_model_name,
            "runtime": runtime.manifest.runtime if runtime is not None else None,
            "model_sha256": runtime.model_sha256 if runtime is not None else None,
            "max_result_age_seconds": (
                runtime.manifest.max_result_age_seconds if runtime is not None else None
            ),
            "model_artifact_path": str(runtime.model_path) if runtime is not None else None,
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
            "latest_result": perception.model_dump(mode="json"),
            "last_error": self.last_error,
        }

    async def infer_image_bytes(
        self,
        image_bytes: bytes,
        *,
        task: InferenceTask = InferenceTask.OBSTACLE_DETECTION,
        frame_id: str | None = None,
        source_frame_timestamp: datetime | None = None,
        confidence_threshold: float | None = None,
    ) -> InferenceResult:
        """Run inference on uploaded image bytes."""
        if not image_bytes:
            raise AIInferenceInputError("Image payload is empty")

        worker_started = asyncio.Event()
        inference_task = asyncio.create_task(
            self._infer_image_bytes_serialized(
                image_bytes,
                task=task,
                frame_id=frame_id,
                source_frame_timestamp=source_frame_timestamp,
                confidence_threshold=confidence_threshold,
                worker_started=worker_started,
            ),
            name=f"ai-inference-{frame_id or 'upload'}",
        )
        # The event loop otherwise holds only a weak reference to detached
        # tasks. Retain the worker until its to_thread call has really exited.
        self._inference_tasks.add(inference_task)
        inference_task.add_done_callback(self._inference_tasks.discard)
        try:
            return await asyncio.shield(inference_task)
        except asyncio.CancelledError:
            # A queued request can be discarded safely. Once the worker has
            # started, leave its task alive so the serialization lock remains
            # held until the underlying thread actually exits.
            if not worker_started.is_set():
                inference_task.cancel()
            inference_task.add_done_callback(self._consume_detached_inference)
            raise

    async def _infer_image_bytes_serialized(
        self,
        image_bytes: bytes,
        *,
        task: InferenceTask,
        frame_id: str | None,
        source_frame_timestamp: datetime | None,
        confidence_threshold: float | None,
        worker_started: asyncio.Event,
    ) -> InferenceResult:
        """Serialize inference while preserving the lock across caller cancellation."""
        async with self._inference_lock:
            await self._ensure_model_ready(task)
            threshold = (
                confidence_threshold
                if confidence_threshold is not None
                else self.ai_processing.confidence_threshold
            )
            worker_started.set()
            try:
                result = await asyncio.to_thread(
                    self._infer_image_bytes_sync,
                    image_bytes,
                    task=task,
                    frame_id=frame_id,
                    source_frame_timestamp=source_frame_timestamp,
                    confidence_threshold=threshold,
                )
            except Exception as exc:
                self.ai_processing.failed_inferences += 1
                self.last_error = str(exc)
                raise

            # Keep shared runtime state mutations on the event-loop thread.
            self.ai_processing.add_inference_result(result)
            self._update_runtime_statistics(result.total_time_ms)
            await self._publish_result(result)
            return result

    @staticmethod
    def _consume_detached_inference(task: asyncio.Task[InferenceResult]) -> None:
        """Consume a cancellation-detached worker result or exception."""
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            # The normal inference path already records last_error and failure
            # counters. This callback only prevents an unhandled-task warning.
            pass

    def _infer_image_bytes_sync(
        self,
        image_bytes: bytes,
        *,
        task: InferenceTask,
        frame_id: str | None,
        source_frame_timestamp: datetime | None,
        confidence_threshold: float,
    ) -> InferenceResult:
        """Decode and infer one image in a worker thread."""
        runtime = self._detector_runtime
        if runtime is None or not runtime.ready:
            raise AIModelNotReadyError("Detector runtime is not ready")
        started = time.perf_counter()

        try:
            preprocess_start = time.perf_counter()
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
            original_width, original_height = image.size
            rgb = np.asarray(image, dtype=np.uint8)
            preprocessing_time_ms = (time.perf_counter() - preprocess_start) * 1000.0
        except UnidentifiedImageError as exc:
            raise AIInferenceInputError(f"Unsupported image payload: {exc}") from exc
        except Exception as exc:
            raise AIInferenceInputError(f"Unable to decode image payload: {exc}") from exc

        inference_start = time.perf_counter()
        runtime_detections = runtime.infer(rgb, confidence_threshold)
        inference_time_ms = (time.perf_counter() - inference_start) * 1000.0

        postprocess_start = time.perf_counter()
        manifest = runtime.manifest
        focal_pixels = original_width / (
            2.0 * math.tan(math.radians(manifest.camera_horizontal_fov_degrees) / 2.0)
        )
        detected_objects: list[DetectedObject] = []
        for detection in runtime_detections[: self.ai_processing.max_detections]:
            center_x = detection.x + detection.width / 2.0
            relative_bearing = (
                center_x - 0.5
            ) * manifest.camera_horizontal_fov_degrees
            distance_estimate = None
            class_height = manifest.class_height_m.get(detection.class_name)
            bbox_height_pixels = detection.height * original_height
            if class_height is not None and bbox_height_pixels > 1.0:
                distance_estimate = min(
                    30.0,
                    max(0.1, float(class_height) * focal_pixels / bbox_height_pixels),
                )
            detected_objects.append(
                DetectedObject(
                    object_id=str(uuid.uuid4()),
                    class_name=detection.class_name,
                    confidence=detection.confidence,
                    bounding_box=BoundingBox(
                        x=detection.x,
                        y=detection.y,
                        width=detection.width,
                        height=detection.height,
                    ),
                    distance_estimate=distance_estimate,
                    relative_bearing=relative_bearing,
                    angular_width_degrees=(
                        detection.width * manifest.camera_horizontal_fov_degrees
                    ),
                    semantic_cost_multiplier=max(
                        1.0,
                        float(
                            manifest.semantic_cost_multipliers.get(
                                detection.class_name,
                                1.0,
                            )
                        ),
                    ),
                )
            )
        postprocessing_time_ms = (time.perf_counter() - postprocess_start) * 1000.0
        total_time_ms = (time.perf_counter() - started) * 1000.0

        return InferenceResult(
            inference_id=str(uuid.uuid4()),
            task=task,
            model_name=self.active_model_name or manifest.model_name,
            input_frame_id=frame_id or f"upload-{uuid.uuid4().hex[:8]}",
            input_width=original_width,
            input_height=original_height,
            source_frame_timestamp=source_frame_timestamp,
            detected_objects=detected_objects,
            inference_time_ms=inference_time_ms,
            preprocessing_time_ms=preprocessing_time_ms,
            postprocessing_time_ms=postprocessing_time_ms,
            total_time_ms=total_time_ms,
            model_version=manifest.version,
            model_runtime=manifest.runtime,
            model_sha256=runtime.model_sha256,
            confidence_threshold=confidence_threshold,
        )

    async def infer_camera_frame(
        self,
        image_bytes: bytes,
        *,
        frame_id: str,
        source_frame_timestamp: datetime | None = None,
    ) -> InferenceResult | None:
        """Best-effort sampled-camera inference with explicit unavailable semantics."""
        if not self.initialized:
            await self.initialize()
        if (
            not self.ai_processing.system_enabled
            or self.active_model_name is None
            or self._detector_runtime is None
            or not self._detector_runtime.ready
        ):
            return None

        try:
            return await self.infer_image_bytes(
                image_bytes,
                frame_id=frame_id,
                source_frame_timestamp=source_frame_timestamp,
            )
        except AIModelNotReadyError:
            # PowerManager may disable inference between the readiness check
            # above and lock acquisition. That is an expected sampled-frame skip.
            return None

    async def infer_latest_frame(
        self,
        *,
        task: InferenceTask = InferenceTask.OBSTACLE_DETECTION,
        confidence_threshold: float | None = None,
    ) -> InferenceResult:
        """Run inference on the latest available camera frame."""
        provider = self._camera_frame_provider
        if provider is None:
            raise AINoFrameAvailableError("No camera frame provider is configured")

        frame = await provider()
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
            source_frame_timestamp=getattr(frame.metadata, "timestamp", None),
            confidence_threshold=confidence_threshold,
        )

    def set_camera_frame_provider(
        self,
        provider: CameraFrameProvider | None,
    ) -> None:
        """Inject the asynchronous latest-frame owner used by API inference."""
        self._camera_frame_provider = provider

    def set_external_owner_state(
        self,
        *,
        sim_mode: bool,
        hardware_available: bool,
        ai_runtime_ready: bool,
        model_sha256: str | None,
        error: str | None = None,
    ) -> None:
        """Record the live camera owner's topology and detector readiness."""
        self._external_owner_sim_mode = bool(sim_mode)
        self._external_owner_hardware_available = bool(hardware_available)
        self._external_owner_ai_runtime_ready = bool(ai_runtime_ready)
        self._external_owner_model_sha256 = model_sha256
        self._external_owner_error = error

    async def get_recent_results(self, limit: int = 10) -> list[InferenceResult]:
        """Return recent inference results, newest first."""
        bounded_limit = max(1, min(limit, 50))
        return list(reversed(self.ai_processing.recent_results[-bounded_limit:]))

    def set_result_consumer(self, consumer: PerceptionResultConsumer | None) -> None:
        """Attach the canonical navigation/WebSocket perception consumer."""
        self._result_consumer = consumer

    async def _publish_result(self, result: InferenceResult) -> None:
        consumer = self._result_consumer
        if consumer is None:
            return
        try:
            outcome = consumer(result)
            if inspect.isawaitable(outcome):
                outcome = await outcome
            if isinstance(outcome, int):
                self._route_cost_obstacle_count = max(0, outcome)
        except Exception:
            logger.exception("Perception result consumer failed")

    async def ingest_external_result(self, result: InferenceResult) -> bool:
        """Validate one camera-owner result before exposing it to API/WS/navigation."""
        runtime = self._detector_runtime
        if (
            runtime is None
            or not self._external_owner
            or not runtime.model_sha256
            or not self._model_ready()
        ):
            logger.warning("Rejected perception result from an unavailable camera owner")
            return False
        timestamp = result.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        source_timestamp = result.source_frame_timestamp
        if source_timestamp is not None and source_timestamp.tzinfo is None:
            source_timestamp = source_timestamp.replace(tzinfo=UTC)
        result_age = (datetime.now(UTC) - timestamp).total_seconds()
        source_age = (
            (datetime.now(UTC) - source_timestamp).total_seconds()
            if source_timestamp is not None
            else None
        )
        if (
            result_age < 0
            or result_age > runtime.manifest.max_result_age_seconds
            or source_age is None
            or source_age < 0
            or source_age > runtime.manifest.max_result_age_seconds
            or source_timestamp > timestamp
            or result.model_name != runtime.manifest.model_name
            or result.model_version != runtime.manifest.version
            or result.model_runtime != runtime.manifest.runtime
            or result.model_sha256 != runtime.model_sha256
            or not result.input_frame_id
        ):
            logger.warning("Rejected camera-owner perception result with invalid provenance")
            return False
        if any(
            existing.inference_id == result.inference_id
            for existing in self.ai_processing.recent_results
        ):
            return False
        self.ai_processing.add_inference_result(result)
        model = self.ai_processing.active_models.get(runtime.manifest.model_name)
        if model is not None:
            model.status = ModelStatus.LOADED
        await self._publish_result(result)
        return True

    def get_perception_snapshot(self) -> PerceptionSnapshot:
        runtime = self._detector_runtime
        max_age = runtime.manifest.max_result_age_seconds if runtime is not None else 2.0
        runtime_available = self._model_ready()
        if not runtime_available:
            reason_code = "DETECTOR_RUNTIME_UNAVAILABLE"
            if self._external_owner and (
                self._external_owner_sim_mode
                or not self._external_owner_hardware_available
            ):
                reason_code = "CAMERA_HARDWARE_UNAVAILABLE"
            elif self._external_owner and not self._external_owner_ai_runtime_ready:
                reason_code = "CAMERA_DETECTOR_RUNTIME_UNAVAILABLE"
            return PerceptionSnapshot(
                available=False,
                fresh=False,
                reason_code=reason_code,
                max_result_age_seconds=max_age,
            )
        if not self.ai_processing.recent_results:
            return PerceptionSnapshot(
                available=True,
                fresh=False,
                reason_code="NO_PERCEPTION_RESULT",
                max_result_age_seconds=max_age,
            )
        result = self.ai_processing.recent_results[-1]
        timestamp = result.source_frame_timestamp or result.timestamp
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        age = max(0.0, (datetime.now(UTC) - timestamp).total_seconds())
        provenance_valid = bool(
            result.input_frame_id
            and result.model_runtime == runtime.manifest.runtime
            and result.model_sha256 == runtime.model_sha256
        )
        fresh = provenance_valid and age <= max_age
        reason = None
        if not provenance_valid:
            reason = "PERCEPTION_PROVENANCE_INVALID"
        elif not fresh:
            reason = "PERCEPTION_RESULT_STALE"
        return PerceptionSnapshot(
            available=True,
            fresh=fresh,
            reason_code=reason,
            result_age_seconds=age,
            max_result_age_seconds=max_age,
            route_cost_obstacle_count=self._route_cost_obstacle_count,
            result=result,
        )

    def get_detector_provenance(self) -> dict[str, str | float] | None:
        """Return the exact configured source accepted by route-cost consumers."""
        runtime = self._detector_runtime
        if runtime is None or not runtime.model_sha256:
            return None
        manifest = runtime.manifest
        return {
            "model_name": manifest.model_name,
            "model_version": manifest.version,
            "model_runtime": manifest.runtime,
            "model_sha256": runtime.model_sha256,
            "max_result_age_seconds": manifest.max_result_age_seconds,
        }

    def _model_ready(self) -> bool:
        runtime = self._detector_runtime
        if runtime is None:
            return False
        if not self._external_owner:
            return bool(runtime.ready)
        return bool(
            runtime.model_sha256
            and not self._external_owner_sim_mode
            and self._external_owner_hardware_available
            and self._external_owner_ai_runtime_ready
            and self._external_owner_model_sha256 == runtime.model_sha256
        )

    async def _ensure_model_ready(self, task: InferenceTask) -> None:
        if not self.initialized:
            await self.initialize()

        if not self.ai_processing.system_enabled:
            raise AIModelNotReadyError("AI inference is disabled by configuration")

        if self._external_owner:
            raise AIModelNotReadyError(
                "Live inference is owned by the standalone camera service"
            )

        if (
            self.active_model_name is None
            or self._detector_runtime is None
            or not self._detector_runtime.ready
        ):
            raise AIModelNotReadyError(f"No AI model is loaded from '{self.model_path}'")

        model_task = self._detector_runtime.manifest.task
        if model_task != task.value:
            raise AIInferenceInputError(f"Loaded model supports '{model_task}', not '{task.value}'")

    async def _load_configured_model(self, *, metadata_only: bool = False) -> None:
        """Load a real configured detector runtime without heuristic fallback."""
        try:
            runtime = self._detector_runtime
            if runtime is None:
                if not self.model_path.is_file():
                    raise DetectorRuntimeError(
                        f"Configured detector manifest not found: {self.model_path}"
                    )
                runtime = OpenCVDnnDetectorRuntime(self.model_path)
                self._detector_runtime = runtime
            if metadata_only:
                load_metadata = getattr(runtime, "load_metadata", None)
                if not callable(load_metadata):
                    raise DetectorRuntimeError(
                        "Configured detector runtime cannot validate remote-owner metadata"
                    )
                await asyncio.to_thread(load_metadata)
            else:
                await asyncio.to_thread(runtime.initialize)
            model_info = self._build_model_info(runtime)
            model_info.status = ModelStatus.UNLOADED if metadata_only else ModelStatus.LOADED
            model_info.load_time = model_info.load_time or datetime.now(UTC)
            self.ai_processing.active_models[model_info.model_name] = model_info
            self.ai_processing.primary_accelerator = AIAccelerator.CPU
            self.active_model_name = model_info.model_name
            self.last_error = None
        except Exception as exc:
            self.active_model_name = None
            self.last_error = f"Detector unavailable: {exc}"
            logger.warning(self.last_error)

    def _build_model_info(self, runtime: DetectorRuntime) -> ModelInfo:
        """Translate validated detector metadata into operator-facing model info."""
        manifest = runtime.manifest
        return ModelInfo(
            model_name=manifest.model_name,
            model_path=str(runtime.model_path),
            format=ModelFormat.ONNX,
            version=manifest.version,
            input_width=manifest.input_width,
            input_height=manifest.input_height,
            input_channels=3,
            num_classes=len(manifest.class_labels),
            class_labels=manifest.class_labels,
            target_accelerator=AIAccelerator.CPU,
            status=ModelStatus.LOADING,
        )

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
