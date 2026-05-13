"""Integration tests for delete_all_missions with mixed lifecycle states."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.src.models.mission import (
    Mission,
    MissionLifecycleStatus,
    MissionStatus,
    MissionWaypoint,
)
from backend.src.repositories.mission_repository import MissionRepository
from backend.src.services.mission_service import MissionService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mission(mission_id: str, name: str = "Test") -> Mission:
    return Mission(
        id=mission_id,
        name=name,
        waypoints=[
            MissionWaypoint(lat=37.0, lon=-122.0, blade_on=False, speed=50)
        ],
        created_at=datetime.now(UTC).isoformat(),
    )


def _make_status(mission_id: str, status: MissionLifecycleStatus) -> MissionStatus:
    return MissionStatus(
        mission_id=mission_id,
        status=status,
        current_waypoint_index=0,
        completion_percentage=0.0,
        total_waypoints=1,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_db(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def mission_repo(tmp_db: Path) -> MissionRepository:
    return MissionRepository(db_path=tmp_db)


@pytest.fixture()
def nav_mock() -> MagicMock:
    nav = MagicMock()
    nav.navigation_state = MagicMock()
    nav.navigation_state.safety_boundaries = []
    nav.execute_mission = AsyncMock()
    return nav


@pytest.fixture()
def svc(nav_mock: MagicMock, mission_repo: MissionRepository) -> MissionService:
    return MissionService(
        navigation_service=nav_mock,
        websocket_hub=None,
        mission_repository=mission_repo,
    )


# ---------------------------------------------------------------------------
# Tests: delete_all_missions return shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_all_empty(svc: MissionService):
    """delete_all_missions on an empty store returns {deleted: 0, skipped: []}."""
    result = await svc.delete_all_missions()
    assert result == {"deleted": 0, "skipped": []}


@pytest.mark.asyncio
async def test_delete_all_idle_only(svc: MissionService):
    """delete_all_missions with all IDLE missions deletes all and returns correct count."""
    for i in range(3):
        mid = f"m{i}"
        m = _make_mission(mid, f"Mission {i}")
        svc.missions[mid] = m
        svc.mission_statuses[mid] = _make_status(mid, MissionLifecycleStatus.IDLE)
        svc._mission_repo.save_mission(m.model_dump())

    result = await svc.delete_all_missions()
    assert result["deleted"] == 3
    assert result["skipped"] == []
    assert svc.missions == {}


@pytest.mark.asyncio
async def test_delete_all_skips_running(svc: MissionService):
    """delete_all_missions skips the RUNNING mission and deletes the idle one."""
    running_id = "running-1"
    idle_id = "idle-1"

    r_mission = _make_mission(running_id, "Running Mission")
    i_mission = _make_mission(idle_id, "Idle Mission")

    svc.missions[running_id] = r_mission
    svc.missions[idle_id] = i_mission
    svc.mission_statuses[running_id] = _make_status(running_id, MissionLifecycleStatus.RUNNING)
    svc.mission_statuses[idle_id] = _make_status(idle_id, MissionLifecycleStatus.IDLE)
    svc._mission_repo.save_mission(r_mission.model_dump())
    svc._mission_repo.save_mission(i_mission.model_dump())

    result = await svc.delete_all_missions()

    assert result["deleted"] == 1
    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["id"] == running_id
    assert result["skipped"][0]["name"] == "Running Mission"
    assert result["skipped"][0]["reason"] == "running"

    # Running mission should still be present
    assert running_id in svc.missions
    # Idle mission should be gone
    assert idle_id not in svc.missions


@pytest.mark.asyncio
async def test_delete_all_skips_paused(svc: MissionService):
    """delete_all_missions skips the PAUSED mission and deletes idle ones."""
    paused_id = "paused-1"
    idle_id = "idle-1"

    p_mission = _make_mission(paused_id, "Paused Mission")
    i_mission = _make_mission(idle_id, "Idle Mission")

    svc.missions[paused_id] = p_mission
    svc.missions[idle_id] = i_mission
    svc.mission_statuses[paused_id] = _make_status(paused_id, MissionLifecycleStatus.PAUSED)
    svc.mission_statuses[idle_id] = _make_status(idle_id, MissionLifecycleStatus.IDLE)
    svc._mission_repo.save_mission(p_mission.model_dump())
    svc._mission_repo.save_mission(i_mission.model_dump())

    result = await svc.delete_all_missions()

    assert result["deleted"] == 1
    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["id"] == paused_id
    assert result["skipped"][0]["reason"] == "paused"

    assert paused_id in svc.missions
    assert idle_id not in svc.missions


@pytest.mark.asyncio
async def test_delete_all_skips_multiple_active(svc: MissionService):
    """delete_all_missions skips all active missions and deletes only terminal ones."""
    missions_by_status = {
        "r1": MissionLifecycleStatus.RUNNING,
        "p1": MissionLifecycleStatus.PAUSED,
        "c1": MissionLifecycleStatus.COMPLETED,
        "a1": MissionLifecycleStatus.ABORTED,
        "f1": MissionLifecycleStatus.FAILED,
        "i1": MissionLifecycleStatus.IDLE,
    }
    for mid, status in missions_by_status.items():
        m = _make_mission(mid, f"Mission {mid}")
        svc.missions[mid] = m
        svc.mission_statuses[mid] = _make_status(mid, status)
        svc._mission_repo.save_mission(m.model_dump())

    result = await svc.delete_all_missions()

    assert result["deleted"] == 4  # completed, aborted, failed, idle
    assert len(result["skipped"]) == 2  # running, paused
    skipped_ids = {s["id"] for s in result["skipped"]}
    assert skipped_ids == {"r1", "p1"}


@pytest.mark.asyncio
async def test_delete_all_completed_missions(svc: MissionService):
    """delete_all_missions deletes COMPLETED/ABORTED/FAILED missions."""
    for mid, status in [
        ("c1", MissionLifecycleStatus.COMPLETED),
        ("a1", MissionLifecycleStatus.ABORTED),
        ("f1", MissionLifecycleStatus.FAILED),
    ]:
        m = _make_mission(mid)
        svc.missions[mid] = m
        svc.mission_statuses[mid] = _make_status(mid, status)
        svc._mission_repo.save_mission(m.model_dump())

    result = await svc.delete_all_missions()
    assert result["deleted"] == 3
    assert result["skipped"] == []
    assert svc.missions == {}
