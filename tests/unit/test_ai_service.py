import json
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from backend.src.models import InferenceTask
from backend.src.services.ai_service import (
    AINoFrameAvailableError,
    AIModelNotReadyError,
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
async def test_infer_latest_frame_uses_camera_frame(monkeypatch, tmp_path):
    model_path = tmp_path / "ai-model.json"
    _write_test_model(model_path)
    service = AIService(model_path=str(model_path), confidence_threshold=0.2)
    await service.initialize()

    frame = SimpleNamespace(
        data=_make_test_image_bytes(),
        metadata=SimpleNamespace(frame_id="camera-frame-1"),
    )
    monkeypatch.setattr(
        "backend.src.services.ai_service.camera_service.get_current_frame",
        lambda: None,
        raising=False,
    )

    async def fake_get_current_frame():
        return frame

    monkeypatch.setattr(
        "backend.src.services.ai_service.camera_service.get_current_frame",
        fake_get_current_frame,
        raising=False,
    )

    result = await service.infer_latest_frame()

    assert result.input_frame_id == "camera-frame-1"
    assert len(result.detected_objects) >= 1


@pytest.mark.asyncio
async def test_infer_latest_frame_fails_cleanly_when_no_frame(tmp_path, monkeypatch):
    model_path = tmp_path / "ai-model.json"
    _write_test_model(model_path)
    service = AIService(model_path=str(model_path))
    await service.initialize()

    async def fake_get_current_frame():
        return None

    monkeypatch.setattr(
        "backend.src.services.ai_service.camera_service.get_current_frame",
        fake_get_current_frame,
        raising=False,
    )

    with pytest.raises(AINoFrameAvailableError):
        await service.infer_latest_frame()