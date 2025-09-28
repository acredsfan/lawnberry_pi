import pytest
import httpx
from backend.src.main import app

@pytest.mark.asyncio
async def test_control_drive_accepts_command():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"mode": "arcade", "throttle": 0.5, "turn": -0.2}
        resp = await client.post("/api/v2/control/drive", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("accepted") is True

@pytest.mark.asyncio
async def test_control_blade_toggle():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # turn blade on
        resp_on = await client.post("/api/v2/control/blade", json={"active": True})
        assert resp_on.status_code == 200
        assert resp_on.json().get("blade_active") is True
        # turn blade off
        resp_off = await client.post("/api/v2/control/blade", json={"active": False})
        assert resp_off.status_code == 200
        assert resp_off.json().get("blade_active") is False

@pytest.mark.asyncio
async def test_emergency_stop_sets_flag():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v2/control/emergency-stop")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("emergency_stop_active") is True
