import pytest
import os
import json
from fastapi.testclient import TestClient
from backend.src.api.routers.settings import router, SETTINGS_FILE
from backend.src.main import app

client = TestClient(app)

@pytest.fixture
def clean_settings_file():
    if os.path.exists(SETTINGS_FILE):
        os.remove(SETTINGS_FILE)
    yield
    if os.path.exists(SETTINGS_FILE):
        os.remove(SETTINGS_FILE)

def test_get_default_settings(clean_settings_file):
    response = client.get("/api/v2/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["theme"] == "dark"

def test_update_and_persist_settings(clean_settings_file):
    new_settings = {
        "theme": "light",
        "units": "imperial",
        "language": "fr",
        "notifications_enabled": False,
        "map_provider": "google"
    }
    response = client.put("/api/v2/settings", json=new_settings)
    assert response.status_code == 200
    assert response.json() == new_settings
    
    # Verify file persistence
    assert os.path.exists(SETTINGS_FILE)
    with open(SETTINGS_FILE, "r") as f:
        saved_data = json.load(f)
        assert saved_data == new_settings
        
    # Verify get returns persisted data
    response = client.get("/api/v2/settings")
    assert response.status_code == 200
    assert response.json() == new_settings
