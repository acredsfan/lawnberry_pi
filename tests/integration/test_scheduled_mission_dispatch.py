"""Integration tests: JobsService._dispatch_scheduled_job fires create + start mission.

Tests verify:
  - A job with past next_run creates and starts a mission via MissionService.
  - A job is skipped when emergency stop is active.
  - A job is skipped when a mission is already RUNNING.
  - A job with no zones is skipped with a warning.
  - WS broadcast is best-effort (failure does not crash dispatch).
  - last_run is updated and persisted after successful dispatch.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.services.jobs_service import JobsService
from backend.src.models.mission import Mission, MissionLifecycleStatus, MissionStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(
    *,
    zones: list[str] | None = None,
    pattern: str = "parallel",
    pattern_params: dict | None = None,
    next_run: str | None = None,
) -> dict:
    """Return a minimal planning-job dict as returned by persistence.load_planning_jobs()."""
    return {
        "id": "job-test-001",
        "name": "Test Schedule",
        "schedule": "08:00",
        "zones": zones if zones is not None else ["zone-abc"],
        "pattern": pattern,
        "pattern_params": pattern_params or {},
        "priority": 1,
        "enabled": True,
        "created_at": "2026-01-01T00:00:00+00:00",
        "last_run": None,
        "status": "pending",
        "next_run": next_run or "2026-01-01T08:00:00+00:00",
    }


def _make_running_mission() -> Mission:
    return Mission(
        id="mission-running-001",
        name="Active Mission",
        waypoints=[],
        created_at=datetime.now(UTC).isoformat(),
    )


def _mission_status_running(mission_id: str) -> MissionStatus:
    return MissionStatus(
        mission_id=mission_id,
        status=MissionLifecycleStatus.RUNNING,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduled_job_creates_and_starts_mission():
    """Dispatch creates a mission and starts it when all conditions are met."""
    svc = JobsService()

    # Mock MissionService
    created_mission = Mission(
        id="mission-new-001",
        name="Scheduled: Test Schedule",
        waypoints=[],
        created_at=datetime.now(UTC).isoformat(),
    )
    mock_mission_svc = MagicMock()
    mock_mission_svc.list_missions = AsyncMock(return_value=[])
    mock_mission_svc.create_mission = AsyncMock(return_value=created_mission)
    mock_mission_svc.start_mission = AsyncMock(return_value=None)

    # Mock WebSocketHub
    mock_ws_hub = MagicMock()
    mock_ws_hub.broadcast_to_topic = AsyncMock(return_value=None)

    svc.set_mission_service(mock_mission_svc)
    svc.set_websocket_hub(mock_ws_hub)

    job = _make_job(zones=["zone-abc"], pattern="parallel", pattern_params={"angle": 45})

    # Safety state: no emergency
    with patch(
        "backend.src.services.jobs_service.get_safety_state",
        return_value={"emergency_stop_active": False},
    ):
        await svc._dispatch_scheduled_job(job)

    # create_mission called with right args
    mock_mission_svc.create_mission.assert_awaited_once_with(
        name="Scheduled: Test Schedule",
        zone_id="zone-abc",
        pattern="parallel",
        pattern_params={"angle": 45},
    )
    # start_mission called with the new mission id
    mock_mission_svc.start_mission.assert_awaited_once_with(created_mission.id)

    # WS broadcast called
    mock_ws_hub.broadcast_to_topic.assert_awaited_once()
    call_args = mock_ws_hub.broadcast_to_topic.await_args
    assert call_args[0][0] == "planning.schedule.fired"
    payload = call_args[0][1]
    assert payload["job_id"] == "job-test-001"
    assert payload["mission_id"] == created_mission.id

    # last_run updated on the job dict
    assert job["last_run"] is not None


@pytest.mark.asyncio
async def test_scheduled_job_skipped_if_emergency_active():
    """Dispatch skips mission creation when emergency stop is active."""
    svc = JobsService()

    mock_mission_svc = MagicMock()
    mock_mission_svc.list_missions = AsyncMock(return_value=[])
    mock_mission_svc.create_mission = AsyncMock()
    mock_mission_svc.start_mission = AsyncMock()

    svc.set_mission_service(mock_mission_svc)

    job = _make_job(zones=["zone-abc"])

    with patch(
        "backend.src.services.jobs_service.get_safety_state",
        return_value={"emergency_stop_active": True},
    ):
        await svc._dispatch_scheduled_job(job)

    mock_mission_svc.create_mission.assert_not_awaited()
    mock_mission_svc.start_mission.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduled_job_skipped_if_mission_already_running():
    """Dispatch skips mission creation when a mission is already RUNNING."""
    svc = JobsService()

    running_mission = _make_running_mission()
    running_status = _mission_status_running(running_mission.id)

    mock_mission_svc = MagicMock()
    # list_missions returns missions; statuses are checked via mission_statuses dict
    mock_mission_svc.list_missions = AsyncMock(return_value=[running_mission])
    mock_mission_svc.mission_statuses = {
        running_mission.id: running_status,
    }
    mock_mission_svc.create_mission = AsyncMock()
    mock_mission_svc.start_mission = AsyncMock()

    svc.set_mission_service(mock_mission_svc)

    job = _make_job(zones=["zone-abc"])

    with patch(
        "backend.src.services.jobs_service.get_safety_state",
        return_value={"emergency_stop_active": False},
    ):
        await svc._dispatch_scheduled_job(job)

    mock_mission_svc.create_mission.assert_not_awaited()
    mock_mission_svc.start_mission.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduled_job_skipped_if_no_zones():
    """Dispatch skips when the job has no zones configured."""
    svc = JobsService()

    mock_mission_svc = MagicMock()
    mock_mission_svc.list_missions = AsyncMock(return_value=[])
    mock_mission_svc.create_mission = AsyncMock()
    mock_mission_svc.start_mission = AsyncMock()

    svc.set_mission_service(mock_mission_svc)

    job = _make_job(zones=[])

    with patch(
        "backend.src.services.jobs_service.get_safety_state",
        return_value={"emergency_stop_active": False},
    ):
        await svc._dispatch_scheduled_job(job)

    mock_mission_svc.create_mission.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduled_job_ws_broadcast_failure_does_not_crash():
    """WS broadcast failure is swallowed; start_mission still completes."""
    svc = JobsService()

    created_mission = Mission(
        id="mission-ws-fail-001",
        name="Scheduled: Test Schedule",
        waypoints=[],
        created_at=datetime.now(UTC).isoformat(),
    )
    mock_mission_svc = MagicMock()
    mock_mission_svc.list_missions = AsyncMock(return_value=[])
    mock_mission_svc.create_mission = AsyncMock(return_value=created_mission)
    mock_mission_svc.start_mission = AsyncMock(return_value=None)

    mock_ws_hub = MagicMock()
    mock_ws_hub.broadcast_to_topic = AsyncMock(side_effect=RuntimeError("WS down"))

    svc.set_mission_service(mock_mission_svc)
    svc.set_websocket_hub(mock_ws_hub)

    job = _make_job(zones=["zone-abc"])

    with patch(
        "backend.src.services.jobs_service.get_safety_state",
        return_value={"emergency_stop_active": False},
    ):
        # Must not raise despite WS failure
        await svc._dispatch_scheduled_job(job)

    mock_mission_svc.start_mission.assert_awaited_once()


@pytest.mark.asyncio
async def test_scheduled_job_start_mission_error_logged_not_raised():
    """If start_mission raises, the error is logged and last_run is still updated."""
    svc = JobsService()

    created_mission = Mission(
        id="mission-start-fail-001",
        name="Scheduled: Test Schedule",
        waypoints=[],
        created_at=datetime.now(UTC).isoformat(),
    )
    mock_mission_svc = MagicMock()
    mock_mission_svc.list_missions = AsyncMock(return_value=[])
    mock_mission_svc.create_mission = AsyncMock(return_value=created_mission)
    mock_mission_svc.start_mission = AsyncMock(
        side_effect=RuntimeError("Navigation not ready")
    )

    svc.set_mission_service(mock_mission_svc)

    job = _make_job(zones=["zone-abc"])

    with patch(
        "backend.src.services.jobs_service.get_safety_state",
        return_value={"emergency_stop_active": False},
    ):
        # Must not raise despite start_mission failure
        await svc._dispatch_scheduled_job(job)

    # last_run still updated so we don't re-fire immediately
    assert job["last_run"] is not None


@pytest.mark.asyncio
async def test_set_mission_service_guard():
    """_dispatch_scheduled_job raises RuntimeError if mission_service not wired."""
    svc = JobsService()

    job = _make_job(zones=["zone-abc"])

    with pytest.raises(RuntimeError, match="MissionService"):
        await svc._dispatch_scheduled_job(job)
