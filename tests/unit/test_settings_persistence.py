import pytest
import os
import json
from pathlib import Path
from fastapi.testclient import TestClient
from backend.src.api.routers import settings as settings_router
from backend.src.main import app

client = TestClient(app)

@pytest.fixture
def clean_settings_file(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    ui_settings_file = tmp_path / "ui_settings.json"
    monkeypatch.setattr(settings_router, "DATA_DIR", Path(tmp_path))
    monkeypatch.setattr(settings_router, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_router, "UI_SETTINGS_FILE", ui_settings_file)
    yield
    for path in (settings_file, ui_settings_file):
        if os.path.exists(path):
            os.remove(path)

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
        "google_api_key": "AIza-test-key",
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


def test_get_settings_prefers_ui_unit_system(clean_settings_file):
    settings_router.SETTINGS_FILE.write_text(
        json.dumps(
            {
                "theme": "dark",
                "units": "metric",
                "unit_system": "metric",
                "language": "en",
                "notifications_enabled": True,
                "map_provider": "osm",
            }
        )
    )
    settings_router.UI_SETTINGS_FILE.write_text(
        json.dumps(
            {
                "system": {
                    "unit_system": "imperial",
                    "ui": {
                        "unit_system": "imperial",
                    },
                }
            }
        )
    )

    response = client.get("/api/v2/settings")

    assert response.status_code == 200
    data = response.json()
    assert data["units"] == "imperial"
    assert data["unit_system"] == "imperial"
    assert data["system"]["unit_system"] == "imperial"

    saved_data = json.loads(settings_router.SETTINGS_FILE.read_text())
    assert saved_data["units"] == "imperial"
    assert saved_data["unit_system"] == "imperial"


def test_settings_maps_section_persists_mission_planner_overrides(clean_settings_file):
    response = client.put(
        "/api/v2/settings/maps",
        json={
            "provider": "osm",
            "style": "standard",
            "google_api_key": "AIza-test-key",
            "mission_planner": {
                "provider": "google",
                "style": "hybrid",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "osm"
    assert payload["style"] == "standard"
    assert payload["mission_planner"] == {
        "provider": "google",
        "style": "hybrid",
    }

    stored_sections = json.loads(settings_router.UI_SETTINGS_FILE.read_text())
    assert stored_sections["maps"]["mission_planner"] == {
        "provider": "google",
        "style": "hybrid",
    }

    response_get = client.get("/api/v2/settings/maps")
    assert response_get.status_code == 200
    assert response_get.json()["mission_planner"] == {
        "provider": "google",
        "style": "hybrid",
    }


def test_settings_maps_section_rejects_google_without_shared_api_key(clean_settings_file):
    response = client.put(
        "/api/v2/settings/maps",
        json={
            "provider": "osm",
            "style": "standard",
            "mission_planner": {
                "provider": "google",
                "style": "hybrid",
            },
        },
    )

    assert response.status_code == 422
    assert "google_api_key" in response.json()["detail"]
