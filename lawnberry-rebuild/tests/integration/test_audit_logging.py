import pytest
import httpx

from backend.src.main import app
from backend.src.core.persistence import persistence


@pytest.mark.asyncio
async def test_audit_manual_control_and_settings():
    transport = httpx.ASGITransport(app=app)
    headers = {"X-Client-Id": "audit-client-1"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Drive command
        resp = await client.post("/api/v2/control/drive", json={"mode": "arcade", "throttle": 0.1, "turn": 0.0}, headers=headers)
        assert resp.status_code == 200

        # Blade toggle
        resp = await client.post("/api/v2/control/blade", json={"active": True}, headers=headers)
        assert resp.status_code == 200

        # Emergency stop
        resp = await client.post("/api/v2/control/emergency-stop", headers=headers)
        assert resp.status_code == 200

        # Settings update
        resp = await client.put("/api/v2/settings/system", json={"telemetry": {"cadence_hz": 3}}, headers=headers)
        assert resp.status_code == 200

    logs = persistence.load_audit_logs(limit=50)
    actions = [log["action"] for log in logs]
    # Ensure our expected actions are present
    assert any(a == "control.drive" for a in actions)
    assert any(a == "control.blade" for a in actions)
    assert any(a == "control.emergency_stop" for a in actions)
    assert any(a == "settings.update" for a in actions)


@pytest.mark.asyncio
async def test_audit_ai_export():
    transport = httpx.ASGITransport(app=app)
    headers = {"X-Client-Id": "audit-client-2"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v2/ai/datasets/obstacle-detection/export",
            json={"format": "COCO", "include_unlabeled": False},
            headers=headers,
        )
        assert resp.status_code == 202

    logs = persistence.load_audit_logs(limit=50)
    assert any(log["action"] == "ai.export" for log in logs)
