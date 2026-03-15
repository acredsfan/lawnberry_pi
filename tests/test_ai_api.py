from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from backend.src.main import app
from backend.src.services.ai_service import (
    AINoFrameAvailableError,
    AIModelNotReadyError,
    AIService,
    get_ai_service,
)


def _make_test_image_bytes() -> bytes:
    image = Image.new("RGB", (256, 256), (20, 160, 20))
    draw = ImageDraw.Draw(image)
    draw.rectangle((70, 70, 180, 180), fill=(220, 20, 20))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path):
    model_path = tmp_path / "ai-model.json"
    model_path.write_text(
        """
        {
          "model_name": "api-test-model",
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
              "max_components": 4
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    ai_service = AIService(model_path=str(model_path), confidence_threshold=0.2)
    app.dependency_overrides[get_ai_service] = lambda: ai_service
    with TestClient(app) as test_client:
        yield test_client, ai_service
    app.dependency_overrides.clear()


def test_get_ai_status(client):
    test_client, _service = client

    response = test_client.get("/api/v2/ai/status")

    assert response.status_code == 200
    assert response.json()["configured_model_path"].endswith("ai-model.json")


def test_run_uploaded_inference(client):
    test_client, _service = client

    response = test_client.post(
        "/api/v2/ai/inference?task=obstacle_detection&confidence_threshold=0.2&frame_id=frame.jpg",
        content=_make_test_image_bytes(),
        headers={"Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_name"] == "api-test-model"
    assert len(payload["detected_objects"]) >= 1


def test_recent_results_returns_latest_first(client):
    test_client, _service = client
    test_client.post(
        "/api/v2/ai/inference?task=obstacle_detection&confidence_threshold=0.2&frame_id=frame.jpg",
        content=_make_test_image_bytes(),
        headers={"Content-Type": "application/octet-stream"},
    )

    response = test_client.get("/api/v2/ai/results/recent?limit=5")

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_ai_error_mapping_for_missing_model(tmp_path):
    ai_service = AIService(model_path=str(tmp_path / "missing.json"))
    app.dependency_overrides[get_ai_service] = lambda: ai_service
    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v2/ai/inference?task=obstacle_detection&frame_id=frame.jpg",
            content=_make_test_image_bytes(),
            headers={"Content-Type": "application/octet-stream"},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "No AI model is loaded" in response.json()["detail"]


def test_ai_error_mapping_for_missing_camera_frame(client, monkeypatch):
    test_client, ai_service = client

    async def raise_no_frame(*args, **kwargs):
        raise AINoFrameAvailableError("No camera frame available for inference")

    monkeypatch.setattr(ai_service, "infer_latest_frame", raise_no_frame)
    response = test_client.post("/api/v2/ai/inference/latest")

    assert response.status_code == 404
    assert "No camera frame available" in response.json()["detail"]