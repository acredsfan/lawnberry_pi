import pytest
import os
import json
from fastapi.testclient import TestClient
from backend.src.api.routers import settings as settings_router
from backend.src.main import app

client = TestClient(app)

@pytest.fixture
def clean_settings_file():
    settings_file = settings_router.SETTINGS_FILE
    if os.path.exists(settings_file):
        os.remove(settings_file)
    yield
    if os.path.exists(settings_file):
        os.remove(settings_file)

def test_get_default_settings(clean_settings_file):
    response = client.get("/api/v2/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["theme"] == "dark"
    assert data["profile_version"] == "1.0.0"
    assert int(data["telemetry"]["cadence_hz"]) >= 1

def test_update_and_persist_settings(clean_settings_file):
    new_settings = {
        "profile_version": "1.0.1",
        "theme": "light",
        "units": "imperial",
        "language": "fr",
        "notifications_enabled": False,
        "map_provider": "google",
        "simulation_mode": True,
        "telemetry": {
            "cadence_hz": 7,
            "latency_targets": {
                "pi5_ms": 240,
                "pi4b_ms": 340,
            },
        },
    }
    response = client.put("/api/v2/settings", json=new_settings)
    assert response.status_code == 200
    body = response.json()
    assert body["profile_version"] == "1.0.1"
    assert body["theme"] == "light"
    assert body["units"] == "imperial"
    assert body["simulation_mode"] is True
    assert body["telemetry"]["cadence_hz"] == 7
    
    # Verify file persistence
    settings_file = settings_router.SETTINGS_FILE
    assert os.path.exists(settings_file)
    with open(settings_file, "r") as f:
        saved_data = json.load(f)
        assert saved_data["profile_version"] == "1.0.1"
        assert saved_data["theme"] == "light"
        assert saved_data["units"] == "imperial"
        
    # Verify get returns persisted data
    response = client.get("/api/v2/settings")
    assert response.status_code == 200
    refreshed = response.json()
    assert refreshed["profile_version"] == "1.0.1"
    assert refreshed["theme"] == "light"
    assert refreshed["units"] == "imperial"
    assert refreshed["telemetry"]["cadence_hz"] == 7
