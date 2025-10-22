import pytest
from fastapi.testclient import TestClient

try:
    from backend.src.main import app
except Exception:
    app = None


@pytest.mark.skipif(app is None, reason="Backend app not importable yet")
def test_health_endpoint_reports_subsystems():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "healthy"

    # Contract: subsystems should be present once implemented
    # Force failure until health endpoints include subsystem statuses
    required = {"message_bus", "drivers", "persistence", "safety"}
    missing = [k for k in required if k not in data]
    assert not missing, f"Missing subsystem health keys: {missing}"
