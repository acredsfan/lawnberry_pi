import asyncio
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from backend.src.models import InferenceTask
from backend.src.services.ai_service import (
    AIModelNotReadyError,
    AINoFrameAvailableError,
    AIService,
)
from backend.src.services.detector_runtime import DetectorManifest, RuntimeDetection


class FakeDetectorRuntime:
    def __init__(self, model_path: Path):
        self.manifest = DetectorManifest(
            model_name="test-onnx-detector",
            model_path=str(model_path),
            input_width=128,
            input_height=128,
            class_labels=["obstacle"],
            class_height_m={"obstacle": 0.5},
            semantic_cost_multipliers={"obstacle": 1.5},
        )
        self.model_path = model_path
        self.model_sha256 = "a" * 64
        self.ready = False
        self.last_error = None

    def initialize(self) -> None:
        self.ready = True

    def load_metadata(self) -> None:
        return None

    def infer(self, _rgb_image, _confidence_threshold):
        return [
            RuntimeDetection(
                class_name="obstacle",
                confidence=0.9,
                x=0.25,
                y=0.25,
                width=0.5,
                height=0.5,
            )
        ]


def _service(tmp_path, *, confidence_threshold: float = 0.5) -> AIService:
    model_path = tmp_path / "detector.onnx"
    return AIService(
        model_path=str(tmp_path / "ai-detector.json"),
        confidence_threshold=confidence_threshold,
        detector_runtime=FakeDetectorRuntime(model_path),
    )


def _make_test_image_bytes() -> bytes:
    image = Image.new("RGB", (256, 256), (20, 160, 20))

    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_ai_status_route_refreshes_external_owner_before_serializing(monkeypatch):
    from backend.src.api import ai as ai_api

    refreshed = False

    async def sync_owner(_service):
        nonlocal refreshed
        refreshed = True
        return True

    class _StatusService:
        async def get_ai_status(self):
            assert refreshed is True
            return {"model_ready": True}

    monkeypatch.setattr(ai_api, "sync_external_ai_owner_state", sync_owner)

    assert await ai_api.get_ai_status(_StatusService()) == {"model_ready": True}


@pytest.mark.asyncio
async def test_initialize_reports_missing_model_gracefully(tmp_path):
    service = AIService(model_path=str(tmp_path / "missing-model.json"))

    initialized = await service.initialize()
    status = await service.get_ai_status()

    assert initialized is True
    assert status["model_ready"] is False
    assert "not found" in status["last_error"]

    with pytest.raises(AIModelNotReadyError):
        await service.infer_image_bytes(_make_test_image_bytes())


@pytest.mark.asyncio
async def test_infer_image_bytes_returns_detected_objects_and_updates_stats(tmp_path):
    service = _service(tmp_path, confidence_threshold=0.2)
    await service.initialize()

    result = await service.infer_image_bytes(
        _make_test_image_bytes(),
        task=InferenceTask.OBSTACLE_DETECTION,
        frame_id="unit-test-frame",
    )

    assert result.model_name == "test-onnx-detector"
    assert result.input_frame_id == "unit-test-frame"
    assert len(result.detected_objects) >= 1
    assert result.detected_objects[0].class_name == "obstacle"
    assert result.model_runtime == "opencv_dnn"
    assert result.model_sha256 == "a" * 64
    assert result.detected_objects[0].semantic_cost_multiplier == 1.5
    assert service.ai_processing.total_inferences == 1
    assert service.ai_processing.successful_inferences == 1
    assert service.ai_processing.processing_fps > 0


@pytest.mark.asyncio
async def test_infer_latest_frame_uses_camera_frame(tmp_path):
    service = _service(tmp_path, confidence_threshold=0.2)
    await service.initialize()

    frame = SimpleNamespace(
        data=_make_test_image_bytes(),
        metadata=SimpleNamespace(frame_id="camera-frame-1"),
    )
    async def fake_get_current_frame():
        return frame

    service.set_camera_frame_provider(fake_get_current_frame)

    result = await service.infer_latest_frame()

    assert result.input_frame_id == "camera-frame-1"
    assert len(result.detected_objects) >= 1


@pytest.mark.asyncio
async def test_infer_latest_frame_fails_cleanly_when_no_frame(tmp_path):
    service = _service(tmp_path)
    await service.initialize()

    async def fake_get_current_frame():
        return None

    service.set_camera_frame_provider(fake_get_current_frame)

    with pytest.raises(AINoFrameAvailableError):
        await service.infer_latest_frame()


@pytest.mark.asyncio
async def test_infer_latest_frame_requires_injected_provider(tmp_path):
    service = _service(tmp_path)
    await service.initialize()

    with pytest.raises(AINoFrameAvailableError, match="provider"):
        await service.infer_latest_frame()


@pytest.mark.asyncio
async def test_camera_inference_returns_none_when_ai_is_disabled(tmp_path):
    service = _service(tmp_path)
    await service.initialize()
    service.set_enabled(False)

    result = await service.infer_camera_frame(
        _make_test_image_bytes(),
        frame_id="disabled-camera-frame",
    )

    assert result is None
    assert service.ai_processing.total_inferences == 0


@pytest.mark.asyncio
async def test_power_gate_cannot_override_operator_hard_disable(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_INFERENCE_ENABLED", "0")
    service = _service(tmp_path)

    await service.initialize()
    service.set_enabled(True)

    status = await service.get_ai_status()
    assert status["configured_enabled"] is False
    assert status["system_enabled"] is False
    assert status["model_ready"] is False


@pytest.mark.asyncio
async def test_external_camera_result_requires_exact_model_and_source_frame(tmp_path):
    local = _service(tmp_path)
    await local.initialize()
    source_timestamp = datetime.now(UTC)
    result = await local.infer_camera_frame(
        _make_test_image_bytes(),
        frame_id="camera-frame-provenance",
        source_frame_timestamp=source_timestamp,
    )
    assert result is not None

    external = _service(tmp_path)
    await external.initialize(metadata_only=True)
    assert (await external.get_ai_status())["model_ready"] is False
    external.set_external_owner_state(
        sim_mode=False,
        hardware_available=True,
        ai_runtime_ready=True,
        model_sha256="b" * 64,
    )
    assert (await external.get_ai_status())["model_ready"] is False
    external.set_external_owner_state(
        sim_mode=False,
        hardware_available=True,
        ai_runtime_ready=True,
        model_sha256="a" * 64,
    )
    assert (await external.get_ai_status())["model_ready"] is True
    consumer = AsyncMock(return_value=1)
    external.set_result_consumer(consumer)

    assert await external.ingest_external_result(result) is True
    assert await external.ingest_external_result(result) is False
    consumer.assert_awaited_once_with(result)

    without_source = result.model_copy(
        update={
            "inference_id": "missing-source",
            "source_frame_timestamp": None,
        }
    )
    assert await external.ingest_external_result(without_source) is False


@pytest.mark.asyncio
async def test_external_camera_result_fails_closed_for_fallback_or_unready_owner(tmp_path):
    local = _service(tmp_path)
    await local.initialize()
    result = await local.infer_camera_frame(
        _make_test_image_bytes(),
        frame_id="hardware-frame",
        source_frame_timestamp=datetime.now(UTC),
    )
    assert result is not None

    external = _service(tmp_path)
    await external.initialize(metadata_only=True)
    external.set_external_owner_state(
        sim_mode=True,
        hardware_available=False,
        ai_runtime_ready=True,
        model_sha256="a" * 64,
        error="camera fallback",
    )

    assert await external.ingest_external_result(result) is False
    fallback = external.get_perception_snapshot()
    assert fallback.available is False
    assert fallback.fresh is False
    assert fallback.reason_code == "CAMERA_HARDWARE_UNAVAILABLE"

    external.set_external_owner_state(
        sim_mode=False,
        hardware_available=True,
        ai_runtime_ready=False,
        model_sha256="a" * 64,
        error="ONNX initialization failed",
    )
    assert (await external.get_ai_status())["model_ready"] is False
    assert external.get_perception_snapshot().reason_code == (
        "CAMERA_DETECTOR_RUNTIME_UNAVAILABLE"
    )


def test_detector_freshness_default_has_bounded_owner_delivery_margin(tmp_path):
    service = _service(tmp_path)
    manifest = service._detector_runtime.manifest

    assert manifest.max_result_age_seconds == pytest.approx(5.0)
    assert manifest.max_result_age_seconds - 3.0 == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_inference_runs_off_loop_and_serializes_concurrent_callers(tmp_path, monkeypatch):
    service = _service(tmp_path, confidence_threshold=0.2)
    await service.initialize()

    original = service._infer_image_bytes_sync
    main_thread_id = threading.get_ident()
    worker_thread_ids: list[int] = []
    active = 0
    max_active = 0
    active_lock = threading.Lock()

    def slow_inference(*args, **kwargs):
        nonlocal active, max_active
        worker_thread_ids.append(threading.get_ident())
        with active_lock:
            active += 1
            max_active = max(max_active, active)
        try:
            time.sleep(0.05)
            return original(*args, **kwargs)
        finally:
            with active_lock:
                active -= 1

    monkeypatch.setattr(service, "_infer_image_bytes_sync", slow_inference)
    first = asyncio.create_task(service.infer_image_bytes(_make_test_image_bytes()))
    second = asyncio.create_task(service.infer_image_bytes(_make_test_image_bytes()))

    await asyncio.sleep(0.01)
    assert first.done() is False
    assert second.done() is False
    await asyncio.gather(first, second)

    assert worker_thread_ids
    assert all(thread_id != main_thread_id for thread_id in worker_thread_ids)
    assert max_active == 1


@pytest.mark.asyncio
async def test_cancelled_inference_keeps_lock_until_worker_exits(tmp_path, monkeypatch):
    """Cancelling an awaiter must not let another worker overlap its live thread."""
    service = _service(tmp_path, confidence_threshold=0.2)
    await service.initialize()

    original = service._infer_image_bytes_sync
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    call_count = 0
    active = 0
    max_active = 0
    state_lock = threading.Lock()

    def controlled_inference(*args, **kwargs):
        nonlocal call_count, active, max_active
        with state_lock:
            call_count += 1
            current_call = call_count
            active += 1
            max_active = max(max_active, active)
        try:
            if current_call == 1:
                first_started.set()
                assert release_first.wait(timeout=2.0)
            else:
                second_started.set()
            return original(*args, **kwargs)
        finally:
            with state_lock:
                active -= 1

    monkeypatch.setattr(service, "_infer_image_bytes_sync", controlled_inference)
    first = asyncio.create_task(service.infer_image_bytes(_make_test_image_bytes()))
    assert await asyncio.to_thread(first_started.wait, 1.0)

    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first

    second = asyncio.create_task(service.infer_image_bytes(_make_test_image_bytes()))
    await asyncio.sleep(0.05)

    assert service._inference_lock.locked() is True
    assert second_started.is_set() is False

    release_first.set()
    await asyncio.wait_for(second, timeout=2.0)

    assert second_started.is_set() is True
    assert max_active == 1
