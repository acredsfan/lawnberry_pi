from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from backend.src.core.runtime import RuntimeContext, get_runtime
from backend.src.main import app
from backend.src.models.mission import Mission, MissionLifecycleStatus, MissionStatus
from backend.src.services.mission_service import (
    MissionConflictError,
    MissionNotFoundError,
    MissionService,
    MissionStateError,
    MissionValidationError,
)


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
    fake_runtime = RuntimeContext(
        config_loader=MagicMock(),
        hardware_config=MagicMock(),
        safety_limits=MagicMock(),
        navigation=MagicMock(),
        mission_service=mock_mission_service,
        safety_state={},
        blade_state={},
        robohat=MagicMock(),
        websocket_hub=MagicMock(),
        persistence=MagicMock(),
    )
    app.dependency_overrides[get_runtime] = lambda: fake_runtime
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
    response = client.post("/api/v2/missions/test_mission/start", json={})
    assert response.status_code == 200
    mock_mission_service.start_mission.assert_called_once_with("test_mission")

def test_pause_mission(client, mock_mission_service):
    response = client.post("/api/v2/missions/test_mission/pause", json={})
    assert response.status_code == 200
    mock_mission_service.pause_mission.assert_called_once_with("test_mission")


def test_resume_mission(client, mock_mission_service):
    response = client.post("/api/v2/missions/test_mission/resume", json={})
    assert response.status_code == 200
    mock_mission_service.resume_mission.assert_called_once_with("test_mission")


def test_abort_mission(client, mock_mission_service):
    response = client.post("/api/v2/missions/test_mission/abort", json={})
    assert response.status_code == 200
    mock_mission_service.abort_mission.assert_called_once_with("test_mission")


def test_get_mission_status(client, mock_mission_service):
    mock_mission_service.get_mission_status.return_value = MissionStatus(
        mission_id="test_mission",
        status=MissionLifecycleStatus.RUNNING,
        current_waypoint_index=1,
        completion_percentage=50.0,
        total_waypoints=2,
    )

    response = client.get("/api/v2/missions/test_mission/status")

    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.json()["completion_percentage"] == 50.0


def test_list_missions(client, mock_mission_service):
    mock_mission_service.list_missions.return_value = [
        Mission(id="test_mission", name="Test", waypoints=[], created_at="now")
    ]

    response = client.get("/api/v2/missions/list")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == "test_mission"


@pytest.mark.parametrize(
    ("side_effect", "expected_status"),
    [
        (MissionValidationError("invalid mission"), 400),
        (MissionNotFoundError("missing mission"), 404),
        (MissionStateError("wrong state"), 409),
        (MissionConflictError("already active"), 409),
    ],
)
def test_mission_error_mapping(client, mock_mission_service, side_effect, expected_status):
    mock_mission_service.start_mission.side_effect = side_effect

    response = client.post("/api/v2/missions/test_mission/start", json={})

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(side_effect)


def test_create_mission_request_validation(client):
    response = client.post("/api/v2/missions/create", json={"name": "", "waypoints": []})

    assert response.status_code == 422


def test_mission_endpoints_resolve_via_runtime_dependency():
    """Confirm mission endpoints resolve via the runtime override path.

    After this task migrated mission.py from Depends(get_mission_service)
    to Depends(get_runtime), the only valid test injection path is
    overriding get_runtime. Overriding get_mission_service no longer has
    any effect on these endpoints — the router doesn't call that
    dependency. The factory still exists in services/mission_service.py
    for non-router callers.
    """
    mock_mission = MagicMock()
    # list_missions is an async endpoint — use AsyncMock so await succeeds.
    mock_mission.list_missions = AsyncMock(return_value=[])

    fake_runtime = RuntimeContext(
        config_loader=MagicMock(),
        hardware_config=MagicMock(),
        safety_limits=MagicMock(),
        navigation=MagicMock(),
        mission_service=mock_mission,
        safety_state={},
        blade_state={},
        robohat=MagicMock(),
        websocket_hub=MagicMock(),
        persistence=MagicMock(),
    )

    app.dependency_overrides[get_runtime] = lambda: fake_runtime
    try:
        with TestClient(app) as client:
            # /api/v2/missions/list is the list-missions endpoint.
            response = client.get("/api/v2/missions/list")
            assert response.status_code == 200, (
                f"status={response.status_code} body={response.text}"
            )
    finally:
        app.dependency_overrides.clear()
