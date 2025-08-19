import os
import sys
import pathlib
import pytest
from fastapi.testclient import TestClient


def _make_client():
    """Create a TestClient for the FastAPI app.
    Ensures the repository's `src` directory is on sys.path for imports.
    """
    src_path = pathlib.Path(__file__).resolve().parents[1] / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    # Import after sys.path modification so it works without PYTHONPATH
    from web_api.main import create_app
    app = create_app()
    return TestClient(app)


def test_health_and_status_mock_path():
    """Basic smoke: app starts, /health ok, /api/v1/status returns JSON.
    When MQTT is not connected, the API falls back to mock data; this validates route wiring
    and that our mqtt_bridge import fix doesn't crash during startup.
    """
    with _make_client() as client:
        r = client.get("/health", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "healthy"

        r2 = client.get("/api/v1/status", timeout=8)
        assert r2.status_code == 200
        payload = r2.json()
        # Minimal shape checks (mock or real)
        assert "state" in payload
        assert "sensors" in payload
        assert "position" in payload


class _FakeMQTT:
    def __init__(self):
        self._cache = {
            "sensors/gps/data": {"latitude": 12.34, "longitude": 56.78, "accuracy": 1.0, "satellites": 6},
            "sensors/imu/data": {"acceleration": {"x": 0.2, "y": 0.0, "z": 9.8}, "orientation": {"yaw": 123.0}},
            "sensors/tof/data": {"left_distance": 750.0, "right_distance": 900.0},
            "sensors/environmental/data": {"temperature": 25.0, "humidity": 55.0, "pressure": 1013.0},
            "power/battery": {"battery_level": 80.0, "battery_voltage": 24.6, "battery_current": 1.5, "charging": False},
        }

    async def connect(self):
        return True

    async def disconnect(self):
        return True

    def is_connected(self):
        return True

    def get_cached_data(self, topic: str):
        return self._cache.get(topic)


def test_status_with_fake_mqtt_bridge():
    """Inject a fake MQTT bridge after startup and verify the API surfaces its data."""
    with _make_client() as client:
        # After the TestClient constructs, lifespan has run; override bridge now
        client.app.state.mqtt_bridge = _FakeMQTT()
        r = client.get("/api/v1/status", timeout=8)
        assert r.status_code == 200
        payload = r.json()
        pos = payload.get("position", {})
        assert pos.get("lat") == 12.34
        assert pos.get("lng") == 56.78
        tof = payload.get("sensors", {}).get("tof", {})
        # Our API converts mm -> meters for large values
        assert 0.74 <= tof.get("left", 0) <= 0.76
        assert 0.89 <= tof.get("right", 0) <= 0.91
