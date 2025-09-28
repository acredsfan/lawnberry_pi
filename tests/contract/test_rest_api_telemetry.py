import pytest
import httpx

from backend.src.main import app


@pytest.mark.asyncio
async def test_get_dashboard_telemetry_shape():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/dashboard/telemetry")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, dict)
        # expected top-level keys (placeholder tolerant)
        for key in [
            "timestamp",
            "battery",
            "temperatures",
            "position",
            "imu",
        ]:
            assert key in body
