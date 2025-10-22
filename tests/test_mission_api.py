import pytest
from fastapi.testclient import TestClient
from your_main_app import app  # Make sure to import your FastAPI app instance
from ..src.services.mission_service import get_mission_service, MissionService
from ..src.models.mission import Mission, MissionWaypoint
from unittest.mock import AsyncMock

# Mock MissionService for testing
@pytest.fixture
def mock_mission_service():
    service = MissionService(navigation_service=AsyncMock())
    service.create_mission = AsyncMock()
    service.start_mission = AsyncMock()
    service.pause_mission = AsyncMock()
    service.resume_mission = AsyncMock()
    service.abort_mission = AsyncMock()
    service.get_mission_status = AsyncMock()
    service.list_missions = AsyncMock()
    return service

@pytest.fixture
def client(mock_mission_service):
    app.dependency_overrides[get_mission_service] = lambda: mock_mission_service
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_create_mission(client, mock_mission_service):
    waypoints = [{"lat": 1.0, "lon": 1.0, "blade_on": True, "speed": 80}]
    mock_mission_service.create_mission.return_value = Mission(
        id="test_mission", name="Test", waypoints=waypoints, created_at="now"
    )
    
    response = client.post("/api/v2/missions/create", json={"name": "Test", "waypoints": waypoints})
    
    assert response.status_code == 200
    assert response.json()["name"] == "Test"
    mock_mission_service.create_mission.assert_called_once()

def test_start_mission(client, mock_mission_service):
    response = client.post("/api/v2/missions/test_mission/start")
    assert response.status_code == 200
    mock_mission_service.start_mission.assert_called_once_with("test_mission")

# Add more tests for pause, resume, abort, status, and list endpoints...
