import pytest
from fastapi.testclient import TestClient

try:
    from backend.src.main import app
except Exception:
    app = None


def _healthy_sensor_provider() -> dict:
    """Mock sensor health provider for contract tests — returns all-healthy state."""
    from datetime import datetime, timezone

    return {
        "status": "healthy",
        "detail": "All sensors reporting healthy",
        "components": {
            "gps": {"status": "online", "health": "healthy"},
            "imu": {"status": "online", "health": "healthy"},
            "tof": {"status": "online", "health": "healthy"},
            "environmental": {"status": "online", "health": "healthy"},
            "power": {"status": "online", "health": "healthy"},
        },
        "initialized": True,
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }


@pytest.mark.skipif(app is None, reason="Backend app not importable yet")
def test_health_endpoint_reports_subsystems():
    """Contract: /health must return 200, status healthy/degraded, and required subsystem keys."""
    from unittest.mock import patch
    from backend.src.api import health as health_api

    # Inject a deterministic sensor health provider so the test is not gated
    # on live hardware being attached to the test runner.
    with patch.object(health_api.health_service, "_sensor_health_provider", _healthy_sensor_provider):
        client = TestClient(app)
        resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.json()

    # Status must be healthy or degraded — never critical — when all sensors are up.
    assert data.get("status") in {"healthy", "degraded"}, (
        f"Expected healthy or degraded, got: {data.get('status')!r}"
    )

    # Contract: subsystem keys must be present
    required = {"message_bus", "drivers", "persistence", "safety"}
    missing = [k for k in required if k not in data]
    assert not missing, f"Missing subsystem health keys: {missing}"
