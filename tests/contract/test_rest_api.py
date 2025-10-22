import httpx
import pytest

from backend.src.main import app


@pytest.mark.asyncio
async def test_auth_login_success():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v2/auth/login", json={"credential": "secret"})
        assert resp.status_code == 200
        body = resp.json()
        assert "token" in body and isinstance(body["token"], str)
        assert "expires_at" in body


@pytest.mark.asyncio
async def test_auth_login_failure():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v2/auth/login", json={"credential": ""})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_status_schema_minimal():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/dashboard/status")
        assert resp.status_code == 200
        body = resp.json()
        # Minimal schema checks per contract (presence of keys)
        assert "battery_percentage" in body
        assert "navigation_state" in body
