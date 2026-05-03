# tests/unit/test_mission_repository.py
"""Unit tests for MissionRepository.

Run: SIM_MODE=1 uv run pytest tests/unit/test_mission_repository.py -v
"""
from __future__ import annotations

import pytest
from datetime import UTC, datetime
from pathlib import Path
from backend.src.repositories.mission_repository import MissionRepository


@pytest.fixture
def repo(tmp_path: Path) -> MissionRepository:
    return MissionRepository(db_path=tmp_path / "missions.db")


def _make_mission(mid: str = "m1") -> dict:
    return {
        "id": mid,
        "name": "Test mission",
        "waypoints": [{"lat": 40.0, "lng": -75.0}],
        "created_at": datetime.now(UTC).isoformat(),
    }


def test_list_missions_empty(repo: MissionRepository) -> None:
    assert repo.list_missions() == []


def test_save_and_list_mission(repo: MissionRepository) -> None:
    m = _make_mission("m1")
    repo.save_mission(m)
    missions = repo.list_missions()
    assert len(missions) == 1
    assert missions[0]["id"] == "m1"
    assert missions[0]["waypoints"] == [{"lat": 40.0, "lng": -75.0}]


def test_get_mission(repo: MissionRepository) -> None:
    repo.save_mission(_make_mission("m1"))
    m = repo.get_mission("m1")
    assert m is not None
    assert m["name"] == "Test mission"


def test_get_mission_missing(repo: MissionRepository) -> None:
    assert repo.get_mission("no_such_id") is None


def test_delete_mission(repo: MissionRepository) -> None:
    repo.save_mission(_make_mission("m1"))
    assert repo.delete_mission("m1") is True
    assert repo.get_mission("m1") is None


def test_delete_mission_missing(repo: MissionRepository) -> None:
    assert repo.delete_mission("nope") is False


def test_save_and_load_execution_state(repo: MissionRepository) -> None:
    repo.save_mission(_make_mission("m1"))
    state = {
        "mission_id": "m1",
        "status": "running",
        "current_waypoint_index": 2,
        "completion_percentage": 50.0,
        "total_waypoints": 4,
        "detail": None,
    }
    repo.save_execution_state(state)
    loaded = repo.get_execution_state("m1")
    assert loaded is not None
    assert loaded["status"] == "running"
    assert loaded["current_waypoint_index"] == 2


def test_execution_state_missing(repo: MissionRepository) -> None:
    assert repo.get_execution_state("ghost") is None


def test_list_active_execution_states(repo: MissionRepository) -> None:
    repo.save_mission(_make_mission("m1"))
    repo.save_mission(_make_mission("m2"))
    repo.save_execution_state({"mission_id": "m1", "status": "running", "current_waypoint_index": 0,
                                "completion_percentage": 0.0, "total_waypoints": 3, "detail": None})
    repo.save_execution_state({"mission_id": "m2", "status": "completed", "current_waypoint_index": 3,
                                "completion_percentage": 100.0, "total_waypoints": 3, "detail": None})
    active = repo.list_execution_states_by_status("running")
    assert len(active) == 1
    assert active[0]["mission_id"] == "m1"


def test_prune_terminal_missions(repo: MissionRepository) -> None:
    # Save two missions with terminal states; prune with 0-day retention
    repo.save_mission(_make_mission("m1"))
    repo.save_mission(_make_mission("m2"))
    repo.save_execution_state({"mission_id": "m1", "status": "completed",
                                "current_waypoint_index": 1, "completion_percentage": 100.0,
                                "total_waypoints": 1, "detail": None})
    repo.save_execution_state({"mission_id": "m2", "status": "aborted",
                                "current_waypoint_index": 0, "completion_percentage": 0.0,
                                "total_waypoints": 1, "detail": None})
    deleted = repo.prune_terminal_missions(retention_days=0)
    assert deleted >= 2
    assert repo.list_missions() == []
