import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.src.api.routers import settings as settings_router
from backend.src.main import app
from backend.src.models.safety_limits import SafetyLimits

client = TestClient(app)

@pytest.fixture
def clean_settings_file(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    ui_settings_file = tmp_path / "ui_settings.json"
    monkeypatch.setattr(settings_router, "DATA_DIR", Path(tmp_path))
    monkeypatch.setattr(settings_router, "SETTINGS_FILE", settings_file)
    monkeypatch.setattr(settings_router, "UI_SETTINGS_FILE", ui_settings_file)
    # Also redirect SettingsService.save_profile so it writes to tmp_path
    # instead of the real config/default.json (config_dir default is ./config)
    from backend.src.services.settings_service import SettingsService
    monkeypatch.setattr(settings_router, "_settings_service", lambda: SettingsService(config_dir=tmp_path))
    # Disable settings_repository so the router falls back to file-based I/O.
    # Required when tests run after test_health_api_endpoints.py which wires a
    # real repo into app.state.runtime; without this, monkeypatching SETTINGS_FILE
    # has no effect because the router delegates to the repo first.
    runtime = getattr(app.state, "runtime", None)
    if runtime is not None:
        original_repo = getattr(runtime, "settings_repository", None)
        runtime.settings_repository = None
    yield
    if runtime is not None:
        runtime.settings_repository = original_repo
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
    with open(settings_file) as f:
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
        "source_id": "google:hybrid",
    }

    stored_sections = json.loads(settings_router.UI_SETTINGS_FILE.read_text())
    assert stored_sections["maps"]["mission_planner"] == {
        "provider": "google",
        "style": "hybrid",
        "source_id": "google:hybrid",
    }

    response_get = client.get("/api/v2/settings/maps")
    assert response_get.status_code == 200
    assert response_get.json()["mission_planner"] == {
        "provider": "google",
        "style": "hybrid",
        "source_id": "google:hybrid",
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


def test_settings_maps_section_rejects_google_oauth_client_id(clean_settings_file):
    response = client.put(
        "/api/v2/settings/maps",
        json={
            "provider": "google",
            "style": "satellite",
            "google_api_key": "1234567890-example.apps.googleusercontent.com",
        },
    )

    assert response.status_code == 422
    assert "oauth client id" in response.json()["detail"].lower()


def test_settings_maps_get_tolerates_saved_invalid_google_key(clean_settings_file):
    settings_router.UI_SETTINGS_FILE.write_text(
        json.dumps(
            {
                "maps": {
                    "provider": "google",
                    "style": "satellite",
                    "google_api_key": "1234567890-example.apps.googleusercontent.com",
                    "mission_planner": {
                        "provider": "google",
                        "style": "hybrid",
                    },
                }
            }
        )
    )

    response = client.get("/api/v2/settings/maps")

    assert response.status_code == 200
    payload = response.json()
    assert payload["google_api_key_invalid"] is True
    assert payload["provider"] == "google"
    assert payload["mission_planner"] == {
        "provider": "google",
        "style": "hybrid",
        "source_id": "google:hybrid",
    }


def test_v14_settings_safety_hot_reloads_runtime_limits(monkeypatch):
    updated_limits = SafetyLimits(
        battery_low_voltage=12.2,
        battery_critical_voltage=10.7,
        tof_obstacle_distance_meters=0.33,
    )

    class FakeLoader:
        def update_limits(self, patch):
            assert patch["battery_critical_voltage"] == 10.7
            return updated_limits

    fake_nav = SimpleNamespace(obstacle_detector=SimpleNamespace())
    runtime = SimpleNamespace(safety_limits=SafetyLimits())

    import backend.src.core.config_loader as config_loader
    import backend.src.services.navigation_service as navigation_service

    monkeypatch.setattr(config_loader, "get_config_loader", lambda: FakeLoader())
    monkeypatch.setattr(
        navigation_service.NavigationService,
        "get_instance",
        staticmethod(lambda: fake_nav),
    )
    monkeypatch.setattr(app.state, "runtime", runtime, raising=False)

    response = client.put(
        "/api/v2/settings/safety",
        json={"battery_critical_voltage": 10.7},
    )

    assert response.status_code == 200
    assert runtime.safety_limits is updated_limits
    assert fake_nav._safety_limits is updated_limits
    assert fake_nav.obstacle_detector.limits is updated_limits
    assert fake_nav.obstacle_detector.safety_distance == 0.33
