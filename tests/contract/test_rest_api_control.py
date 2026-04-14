"""Contract tests for manual control REST endpoints."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest

from backend.src.main import app
from backend.src.core.globals import _safety_state
from backend.src.models import NavigationMode, PathStatus
from backend.src.api import rest as rest_api
from backend.src.services.navigation_service import NavigationService
from backend.src.services import robohat_service as robohat_module

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
async def test_post_drive_command_blocks_when_obstacle_detected(monkeypatch):
    transport = httpx.ASGITransport(app=app)
    monkeypatch.setenv("SIM_MODE", "0")

    async def fake_telemetry():
        # Use a distance clearly below whatever the configured obstacle threshold is
        from backend.src.core.config_loader import ConfigLoader
        _, safety = ConfigLoader().get()
        threshold_m = safety.tof_obstacle_distance_meters
        obstacle_distance_mm = threshold_m * 1000 * 0.5  # half the threshold — definitely blocked
        return {
            "source": "hardware",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "position": {
                "latitude": 39.0,
                "longitude": -84.0,
                "accuracy": 0.2,
            },
            "tof": {
                "left": {"distance_mm": obstacle_distance_mm},
                "right": {"distance_mm": 500.0},
            },
        }

    async def fake_send_motor_command(_left: float, _right: float) -> bool:
        raise AssertionError("drive command should not reach RoboHAT while obstacle interlock is active")

    fake_robohat = SimpleNamespace(
        status=SimpleNamespace(serial_connected=True, last_watchdog_echo="status", last_error=None),
        send_motor_command=fake_send_motor_command,
    )

    monkeypatch.setattr(rest_api.websocket_hub, "_generate_telemetry", fake_telemetry)
    monkeypatch.setattr(robohat_module, "get_robohat_service", lambda: fake_robohat)
    monkeypatch.setattr(rest_api, "_resolve_manual_session", lambda _session_id: {"principal": "operator"})

    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post(
            "/api/v2/control/drive",
            json={
                "session_id": _session_id(),
                "vector": {"linear": 0.3, "angular": 0.0},
                "duration_ms": 500,
            },
        )

    assert response.status_code == 423, response.text
    payload = response.json()
    assert payload["result"] == "blocked"
    assert payload["status_reason"] == "OBSTACLE_DETECTED"
    assert "obstacle_detected" in payload["active_interlocks"]


@pytest.mark.asyncio
async def test_post_blade_command_surfaces_lockout_reason():
    """Blade engagement must be blocked with 409 when emergency stop is active."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # Activate emergency stop (session_id required by the endpoint)
        await client.post("/api/v2/control/emergency", json={"session_id": _session_id()})

        response = await client.post(
            "/api/v2/control/blade",
            json={"active": True},
        )

        # Emergency stop blocks blade engagement — 409 Conflict
        assert response.status_code == 409, response.text
        payload = response.json()
        assert "emergency_stop" in payload.get("detail", "").lower()

        # Disable is always allowed regardless of e-stop state
        response = await client.post(
            "/api/v2/control/blade",
            json={"active": False},
        )
        assert response.status_code == 200, response.text


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


@pytest.mark.asyncio
async def test_control_navigation_endpoints_surface_runtime_state(monkeypatch):
    """Control navigation endpoints should expose coherent operator-facing state."""

    _safety_state["emergency_stop_active"] = False
    rest_api._emergency_until = 0.0
    rest_api._client_emergency.clear()

    class _FakeNavService:
        def __init__(self):
            self.navigation_state = SimpleNamespace(
                navigation_mode=NavigationMode.IDLE,
                path_status=PathStatus.PLANNED,
                current_waypoint_index=0,
                planned_path=[object(), object()],
            )

        async def start_autonomous_navigation(self):
            self.navigation_state.navigation_mode = NavigationMode.AUTO
            self.navigation_state.path_status = PathStatus.EXECUTING
            return True

        async def pause_navigation(self):
            self.navigation_state.navigation_mode = NavigationMode.PAUSED
            return True

        async def resume_navigation(self):
            self.navigation_state.navigation_mode = NavigationMode.AUTO
            self.navigation_state.path_status = PathStatus.EXECUTING
            return True

        async def stop_navigation(self):
            self.navigation_state.navigation_mode = NavigationMode.IDLE
            self.navigation_state.path_status = PathStatus.INTERRUPTED
            return True

        async def return_home(self):
            self.navigation_state.navigation_mode = NavigationMode.RETURN_HOME
            self.navigation_state.path_status = PathStatus.EXECUTING
            return True

    fake_nav = _FakeNavService()
    monkeypatch.setattr(NavigationService, "get_instance", classmethod(lambda cls, weather=None: fake_nav))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        start = await client.post("/api/v2/control/start", json={})
        assert start.status_code == 200, start.text
        assert start.json()["status"] == "running"
        assert start.json()["mode"] == "auto"

        pause = await client.post("/api/v2/control/pause", json={})
        assert pause.status_code == 200, pause.text
        assert pause.json()["status"] == "paused"
        assert pause.json()["mode"] == "paused"

        resume = await client.post("/api/v2/control/resume", json={})
        assert resume.status_code == 200, resume.text
        assert resume.json()["status"] == "running"
        assert resume.json()["mode"] == "auto"

        return_home = await client.post("/api/v2/control/return-home", json={})
        assert return_home.status_code == 200, return_home.text
        assert return_home.json()["status"] == "returning_home"
        assert return_home.json()["mode"] == "return_home"

        stop = await client.post("/api/v2/control/stop", json={})
        assert stop.status_code == 200, stop.text
        assert stop.json()["status"] == "stopped"
        assert stop.json()["mode"] == "idle"

        status_response = await client.get("/api/v2/control/status")
        assert status_response.status_code == 200, status_response.text
        payload = status_response.json()
        assert payload["ok"] is True
        assert payload["mode"] == "idle"
        assert payload["waypoints_total"] == 2
