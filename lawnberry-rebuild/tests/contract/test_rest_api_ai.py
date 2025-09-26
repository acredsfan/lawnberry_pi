import pytest
import httpx
from backend.src.main import app


@pytest.mark.asyncio
async def test_get_ai_datasets_returns_list():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/ai/model/datasets")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        # Should have some default datasets
        assert len(body) >= 1
        # Check structure of first dataset
        if body:
            dataset = body[0]
            for key in ["id", "name", "type", "size_mb", "last_updated"]:
                assert key in dataset


@pytest.mark.asyncio
async def test_export_path_data_csv():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/ai/export/path-data?format=csv")
        assert resp.status_code == 200
        body = resp.json()
        assert "export_url" in body
        assert "format" in body
        assert body["format"] == "csv"
        assert "size_estimate_mb" in body
        assert "expires_at" in body


@pytest.mark.asyncio
async def test_export_path_data_json():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/ai/export/path-data?format=json")
        assert resp.status_code == 200
        body = resp.json()
        assert body["format"] == "json"


@pytest.mark.asyncio
async def test_export_path_data_invalid_format():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/ai/export/path-data?format=xml")
        assert resp.status_code == 422
