"""Integration tests for delete_mission() with stale asyncio tasks.

Verifies that delete_mission() on a terminal mission (COMPLETED/ABORTED/FAILED/IDLE)
that still has a not-done asyncio task cancels the task and proceeds without raising
MissionConflictError.
"""
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
from backend.src.services.mission_service import MissionConflictError, MissionService

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
        completion_percentage=100.0 if status == MissionLifecycleStatus.COMPLETED else 0.0,
        total_waypoints=1,
    )


async def _never_finishing_coro():
    """A coroutine that sleeps forever, simulating a stale task."""
    await asyncio.sleep(9999)


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
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_completed_mission_with_stale_task(svc: MissionService):
    """delete_mission on a COMPLETED mission with a not-done task cancels it and deletes."""
    mid = "completed-stale"
    m = _make_mission(mid, "Completed Mission")
    svc.missions[mid] = m
    svc.mission_statuses[mid] = _make_status(mid, MissionLifecycleStatus.COMPLETED)
    svc._mission_repo.save_mission(m.model_dump())

    # Create a stale task that will never finish on its own
    loop = asyncio.get_event_loop()
    stale_task = loop.create_task(_never_finishing_coro())
    svc.mission_tasks[mid] = stale_task

    # Should NOT raise MissionConflictError
    await svc.delete_mission(mid)

    assert mid not in svc.missions
    assert mid not in svc.mission_statuses
    assert mid not in svc.mission_tasks
    assert stale_task.cancelled()


@pytest.mark.asyncio
async def test_delete_aborted_mission_with_stale_task(svc: MissionService):
    """delete_mission on an ABORTED mission with a not-done task cancels it and deletes."""
    mid = "aborted-stale"
    m = _make_mission(mid, "Aborted Mission")
    svc.missions[mid] = m
    svc.mission_statuses[mid] = _make_status(mid, MissionLifecycleStatus.ABORTED)
    svc._mission_repo.save_mission(m.model_dump())

    loop = asyncio.get_event_loop()
    stale_task = loop.create_task(_never_finishing_coro())
    svc.mission_tasks[mid] = stale_task

    await svc.delete_mission(mid)

    assert mid not in svc.missions
    assert stale_task.cancelled()


@pytest.mark.asyncio
async def test_delete_failed_mission_with_stale_task(svc: MissionService):
    """delete_mission on a FAILED mission with a not-done task cancels it and deletes."""
    mid = "failed-stale"
    m = _make_mission(mid, "Failed Mission")
    svc.missions[mid] = m
    svc.mission_statuses[mid] = _make_status(mid, MissionLifecycleStatus.FAILED)
    svc._mission_repo.save_mission(m.model_dump())

    loop = asyncio.get_event_loop()
    stale_task = loop.create_task(_never_finishing_coro())
    svc.mission_tasks[mid] = stale_task

    await svc.delete_mission(mid)

    assert mid not in svc.missions
    assert stale_task.cancelled()


@pytest.mark.asyncio
async def test_delete_idle_mission_with_stale_task(svc: MissionService):
    """delete_mission on an IDLE mission with a not-done task cancels it and deletes."""
    mid = "idle-stale"
    m = _make_mission(mid, "Idle Mission")
    svc.missions[mid] = m
    svc.mission_statuses[mid] = _make_status(mid, MissionLifecycleStatus.IDLE)
    svc._mission_repo.save_mission(m.model_dump())

    loop = asyncio.get_event_loop()
    stale_task = loop.create_task(_never_finishing_coro())
    svc.mission_tasks[mid] = stale_task

    await svc.delete_mission(mid)

    assert mid not in svc.missions
    assert stale_task.cancelled()


@pytest.mark.asyncio
async def test_delete_running_mission_raises_even_with_task(svc: MissionService):
    """delete_mission on a RUNNING mission with an active task raises MissionConflictError."""
    mid = "running-active"
    m = _make_mission(mid, "Running Mission")
    svc.missions[mid] = m
    svc.mission_statuses[mid] = _make_status(mid, MissionLifecycleStatus.RUNNING)
    svc._mission_repo.save_mission(m.model_dump())

    loop = asyncio.get_event_loop()
    stale_task = loop.create_task(_never_finishing_coro())
    svc.mission_tasks[mid] = stale_task

    with pytest.raises(MissionConflictError):
        await svc.delete_mission(mid)

    # Cleanup
    stale_task.cancel()
    try:
        await stale_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_delete_running_mission_raises_without_task(svc: MissionService):
    """delete_mission on a RUNNING mission with no task raises MissionConflictError."""
    mid = "running-no-task"
    m = _make_mission(mid, "Running Mission No Task")
    svc.missions[mid] = m
    svc.mission_statuses[mid] = _make_status(mid, MissionLifecycleStatus.RUNNING)
    svc._mission_repo.save_mission(m.model_dump())

    with pytest.raises(MissionConflictError):
        await svc.delete_mission(mid)


@pytest.mark.asyncio
async def test_delete_mission_no_stale_task(svc: MissionService):
    """delete_mission on a COMPLETED mission with no task deletes cleanly."""
    mid = "completed-clean"
    m = _make_mission(mid, "Clean Completed")
    svc.missions[mid] = m
    svc.mission_statuses[mid] = _make_status(mid, MissionLifecycleStatus.COMPLETED)
    svc._mission_repo.save_mission(m.model_dump())

    await svc.delete_mission(mid)

    assert mid not in svc.missions
    assert mid not in svc.mission_statuses
