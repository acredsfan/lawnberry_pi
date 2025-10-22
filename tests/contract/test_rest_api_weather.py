import httpx
import pytest

from backend.src.main import app


@pytest.mark.asyncio
async def test_weather_current_shape():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/weather/current")
        assert resp.status_code == 200
        body = resp.json()
        # minimal shape checks
        assert "timestamp" in body
        assert "source" in body
        assert "temperature_c" in body
        assert "humidity_percent" in body
        assert "pressure_hpa" in body


@pytest.mark.asyncio
async def test_weather_planning_advice_shape():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/weather/planning-advice")
        assert resp.status_code == 200
        body = resp.json()
        assert "advice" in body
        assert body["advice"] in {"proceed", "avoid", "insufficient-data"}
        assert "reasons" in body
        assert isinstance(body["reasons"], list)
