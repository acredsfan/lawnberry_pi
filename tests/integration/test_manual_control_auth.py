"""Manual motion authentication and fail-safe control contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from backend.src.core.globals import _manual_control_sessions
from backend.src.main import app


def _drive_payload(session_id: str | None) -> dict:
    payload = {
        "vector": {"linear": 0.2, "angular": 0.0},
        "duration_ms": 250,
    }
    if session_id is not None:
        payload["session_id"] = session_id
    return payload


async def _login_and_unlock(client: httpx.AsyncClient) -> tuple[str, str]:
    login = await client.post("/api/v2/auth/login", json={"credential": "operator123"})
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    unlock = await client.post(
        "/api/v2/control/manual-unlock",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert unlock.status_code == 200, unlock.text
    return token, unlock.json()["session_id"]


@pytest.fixture(autouse=True)
def _hardware_auth_boundary(monkeypatch):
    monkeypatch.setenv("SIM_MODE", "0")
    _manual_control_sessions.clear()
    yield
    _manual_control_sessions.clear()


@pytest.mark.asyncio
async def test_manual_drive_rejects_missing_or_invalid_session() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.post("/api/v2/control/drive", json=_drive_payload(None))
        invalid = await client.post(
            "/api/v2/control/drive", json=_drive_payload("not-an-authorized-session")
        )

    assert missing.status_code in {400, 401}
    assert invalid.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_manual_unlock_authorizes_drive() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        _token, session_id = await _login_and_unlock(client)
        response = await client.post(
            "/api/v2/control/drive", json=_drive_payload(session_id)
        )

    assert response.status_code == 202, response.text
    assert response.json()["accepted"] is True


@pytest.mark.asyncio
async def test_blade_enable_requires_session_before_qualification() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unauthenticated = await client.post(
            "/api/v2/control/blade", json={"active": True}
        )
        _token, session_id = await _login_and_unlock(client)
        authenticated = await client.post(
            "/api/v2/control/blade",
            json={"active": True, "session_id": session_id},
        )

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 409
    assert "qualification_required" in authenticated.text


@pytest.mark.asyncio
async def test_blade_disable_and_emergency_stop_remain_fail_safe_without_auth() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        blade_off = await client.post("/api/v2/control/blade", json={"active": False})
        emergency = await client.post("/api/v2/control/emergency-stop")

    assert blade_off.status_code == 200
    assert emergency.status_code == 200
    assert emergency.json()["emergency_stop_active"] is True


@pytest.mark.asyncio
async def test_bearer_token_refresh_returns_a_new_valid_token() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        token, _session_id = await _login_and_unlock(client)
        refreshed = await client.post(
            "/api/v2/auth/refresh",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["token"]
    assert refreshed.json()["expires_in"] > 0


@pytest.mark.asyncio
async def test_expired_manual_session_is_rejected() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        _token, session_id = await _login_and_unlock(client)
        entry = next(
            entry
            for entry in _manual_control_sessions.values()
            if entry["session_id"] == session_id
        )
        entry["expires_at"] = datetime.now(UTC) - timedelta(seconds=1)
        response = await client.post(
            "/api/v2/control/drive", json=_drive_payload(session_id)
        )

    assert response.status_code == 401
