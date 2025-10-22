"""Contract tests for manual control REST endpoints."""

import uuid

import httpx
import pytest

from backend.src.main import app

BASE_URL = "http://test"


def _session_id() -> str:
    return str(uuid.uuid4())


@pytest.mark.asyncio
async def test_get_robohat_status_exposes_watchdog_and_safety_state():
    """GET /api/v2/hardware/robohat must surface firmware, watchdog, and safety status."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get("/api/v2/hardware/robohat")

        assert response.status_code == 200, response.text
        payload = response.json()

        for field in ("firmware_version", "watchdog_heartbeat_ms", "safety_state"):
            assert field in payload, f"Missing field {field} in RoboHAT status"

        assert payload["safety_state"] in {"nominal", "lockout", "emergency_stop"}


@pytest.mark.asyncio
async def test_post_drive_command_returns_audit_id_and_snapshot():
    """Drive command should acknowledge request with audit metadata and telemetry echo."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post(
            "/api/v2/control/drive",
            json={
                "session_id": _session_id(),
                "vector": {"linear": 0.4, "angular": -0.1},
                "duration_ms": 500,
                "reason": "manual_override",
            },
        )

        assert response.status_code == 202, response.text
        payload = response.json()

    assert payload.get("result") in {"accepted", "queued"}
    assert isinstance(payload.get("audit_id"), str)
    snapshot = payload.get("telemetry_snapshot")
    assert snapshot, "telemetry_snapshot missing from drive acknowledgement"
    assert snapshot.get("component_id") in {"drive_left", "drive_right"}
    assert snapshot.get("status") in {"healthy", "warning"}
    assert snapshot.get("latency_ms") is not None
    assert payload.get("status_reason") in {None, "nominal", "safety_override"}


@pytest.mark.asyncio
async def test_post_blade_command_surfaces_lockout_reason():
    """Blade engagement should be blocked during safety lockout with structured reason."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post(
            "/api/v2/control/blade",
            json={
                "session_id": _session_id(),
                "action": "engage",
                "reason": "safety_lockout",
            },
        )

        # During lockout the endpoint must return HTTP 423 with remediation info.
        assert response.status_code == 423, response.text
        payload = response.json()
        assert payload.get("result") == "blocked"
        assert payload.get("status_reason") == "SAFETY_LOCKOUT"
        assert "remediation_url" in payload


@pytest.mark.asyncio
async def test_post_emergency_stop_acknowledges_and_audits():
    """Emergency stop must immediately respond with audit ID and echoed watchdog state."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post(
            "/api/v2/control/emergency",
            json={"session_id": _session_id()},
        )

        assert response.status_code == 202, response.text
        payload = response.json()

        assert payload.get("result") == "accepted"
        assert payload.get("audit_id")
    snapshot = payload.get("telemetry_snapshot")
    assert snapshot and snapshot.get("status") == "fault"
