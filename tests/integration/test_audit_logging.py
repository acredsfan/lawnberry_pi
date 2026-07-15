import asyncio

import httpx
import pytest

from backend.src.core.persistence import persistence
from backend.src.main import app


@pytest.mark.asyncio
async def test_audit_manual_control_and_settings():
    transport = httpx.ASGITransport(app=app)
    headers = {"X-Client-Id": "audit-client-1"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Blade-on is qualification-gated even in simulation; audit the blocked path.
        resp = await client.post(
            "/api/v2/control/blade",
            json={"active": True, "session_id": "audit-session-1"},
            headers=headers,
        )
        assert resp.status_code == 409

        # Drive command
        resp = await client.post(
            "/api/v2/control/drive",
            json={
                "session_id": "audit-session-1",
                "vector": {"linear": 0.1, "angular": 0.0},
                "duration_ms": 250,
            },
            headers=headers,
        )
        assert resp.status_code == 202

        # Emergency stop
        resp = await client.post("/api/v2/control/emergency-stop", headers=headers)
        assert resp.status_code == 200

        # Settings update
        resp = await client.put(
            "/api/v2/settings/system",
            json={"telemetry": {"cadence_hz": 3}},
            headers=headers,
        )
        assert resp.status_code == 200

    await asyncio.sleep(0.05)
    logs = persistence.load_audit_logs(limit=50)
    actions = [log["action"] for log in logs]
    # Ensure our expected actions are present
    assert any(a == "control.blade.blocked" for a in actions)
    assert any(a == "control.drive.v2" for a in actions)
    assert any(a == "control.emergency_stop" for a in actions)
    assert any(a == "settings.update" for a in actions)
