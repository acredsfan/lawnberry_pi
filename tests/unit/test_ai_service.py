import asyncio
import json
import threading
import time
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from backend.src.models import InferenceTask
from backend.src.services.ai_service import (
    AIModelNotReadyError,
    AINoFrameAvailableError,
    AIService,
)


def _write_test_model(path):
    path.write_text(
        json.dumps(
            {
                "model_name": "test-color-detector",
                "model_format": "custom",
                "version": "1.0",
                "task": "obstacle_detection",
                "input_width": 128,
                "input_height": 128,
                "class_labels": ["obstacle"],
                "rules": [
                    {
                        "class_name": "obstacle",
                        "min_rgb": [180, 0, 0],
                        "max_rgb": [255, 120, 120],
                        "min_area_ratio": 0.01,
                        "max_components": 4,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _make_test_image_bytes() -> bytes:
    image = Image.new("RGB", (256, 256), (20, 160, 20))
    draw = ImageDraw.Draw(image)
    draw.rectangle((70, 70, 180, 180), fill=(220, 20, 20))

    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


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
    model_path = tmp_path / "ai-model.json"
    _write_test_model(model_path)
    service = AIService(model_path=str(model_path), confidence_threshold=0.2)
    await service.initialize()

    result = await service.infer_image_bytes(
        _make_test_image_bytes(),
        task=InferenceTask.OBSTACLE_DETECTION,
        frame_id="unit-test-frame",
    )

    assert result.model_name == "test-color-detector"
    assert result.input_frame_id == "unit-test-frame"
    assert len(result.detected_objects) >= 1
    assert result.detected_objects[0].class_name == "obstacle"
    assert service.ai_processing.total_inferences == 1
    assert service.ai_processing.successful_inferences == 1
    assert service.ai_processing.processing_fps > 0


@pytest.mark.asyncio
async def test_infer_latest_frame_uses_camera_frame(tmp_path):
    model_path = tmp_path / "ai-model.json"
    _write_test_model(model_path)
    service = AIService(model_path=str(model_path), confidence_threshold=0.2)
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
    model_path = tmp_path / "ai-model.json"
    _write_test_model(model_path)
    service = AIService(model_path=str(model_path))
    await service.initialize()

    async def fake_get_current_frame():
        return None

    service.set_camera_frame_provider(fake_get_current_frame)

    with pytest.raises(AINoFrameAvailableError):
        await service.infer_latest_frame()


@pytest.mark.asyncio
async def test_infer_latest_frame_requires_injected_provider(tmp_path):
    model_path = tmp_path / "ai-model.json"
    _write_test_model(model_path)
    service = AIService(model_path=str(model_path))
    await service.initialize()

    with pytest.raises(AINoFrameAvailableError, match="provider"):
        await service.infer_latest_frame()


@pytest.mark.asyncio
async def test_camera_inference_returns_none_when_ai_is_disabled(tmp_path):
    model_path = tmp_path / "ai-model.json"
    _write_test_model(model_path)
    service = AIService(model_path=str(model_path))
    await service.initialize()
    service.set_enabled(False)

    result = await service.infer_camera_frame(
        _make_test_image_bytes(),
        frame_id="disabled-camera-frame",
    )

    assert result is None
    assert service.ai_processing.total_inferences == 0


@pytest.mark.asyncio
async def test_inference_runs_off_loop_and_serializes_concurrent_callers(tmp_path, monkeypatch):
    model_path = tmp_path / "ai-model.json"
    _write_test_model(model_path)
    service = AIService(model_path=str(model_path), confidence_threshold=0.2)
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
    model_path = tmp_path / "ai-model.json"
    _write_test_model(model_path)
    service = AIService(model_path=str(model_path), confidence_threshold=0.2)
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
