import pytest
import httpx
from backend.src.main import app


@pytest.mark.asyncio
async def test_get_ai_datasets_returns_list():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/ai/datasets")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        resp = await client.get("/api/v2/ai/datasets")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)


@pytest.mark.asyncio
async def test_post_ai_dataset_export_starts_job():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "format": "COCO",
            "include_unlabeled": False,
            "min_confidence": 0.8
        }
        resp = await client.post("/api/v2/ai/datasets/obstacle-detection/export", json=payload)
        assert resp.status_code == 202  # Accepted - export job started
        body = resp.json()
        assert "export_id" in body
        assert "status" in body
        assert body["status"] == "started"


@pytest.mark.asyncio
async def test_post_ai_dataset_export_yolo_format():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "format": "YOLO",
            "include_unlabeled": True,
            "min_confidence": 0.5
        }
        resp = await client.post("/api/v2/ai/datasets/grass-detection/export", json=payload)
        assert resp.status_code == 202
        body = resp.json()
        assert body["format"] == "YOLO"


@pytest.mark.asyncio 
async def test_post_ai_dataset_export_invalid_dataset():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "format": "COCO",
            "include_unlabeled": False,
            "min_confidence": 0.8
        }
        resp = await client.post("/api/v2/ai/datasets/nonexistent/export", json=payload)
        assert resp.status_code == 404
