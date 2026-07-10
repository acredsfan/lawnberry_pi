import pytest
from fastapi.testclient import TestClient

try:
    from backend.src.main import app
except Exception:
    app = None


def _healthy_sensor_provider() -> dict:
    """Mock sensor health provider for contract tests — returns all-healthy state."""
    from datetime import UTC, datetime

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
        "last_checked": datetime.now(UTC).isoformat(),
    }


@pytest.mark.skipif(app is None, reason="Backend app not importable yet")
def test_health_endpoint_reports_subsystems(tmp_path):
    """Contract: missing production hardware config remains a critical blocker."""
    from unittest.mock import patch

    from backend.src.api import health as health_api

    # Inject a deterministic sensor health provider so the test is not gated
    # on live hardware. Keep hardware config explicitly absent so the endpoint
    # proves that healthy sensor mocks cannot hide the production config blocker.
    with (
        patch.object(
            health_api.health_service,
            "_sensor_health_provider",
            _healthy_sensor_provider,
        ),
        patch.object(
            health_api.health_service,
            "hardware_config_path",
            tmp_path / "missing-hardware.yaml",
        ),
        patch.object(health_api.health_service, "_hardware_config", None),
        patch.object(health_api.health_service, "_config_loader", None),
    ):
        client = TestClient(app)
        resp = client.get("/health")

    assert resp.status_code == 200
    data = resp.json()

    assert data.get("status") == "critical"
    assert data["drivers"]["status"] == "critical"
    config_checks = [
        check
        for check in data["drivers"]["checks"]
        if check.get("component") == "configuration"
    ]
    assert len(config_checks) == 1
    assert config_checks[0]["status"] == "error"
    assert "Hardware configuration not found" in config_checks[0]["detail"]

    # Contract: subsystem keys must be present
    required = {"message_bus", "drivers", "persistence", "safety"}
    missing = [k for k in required if k not in data]
    assert not missing, f"Missing subsystem health keys: {missing}"
