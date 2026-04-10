import asyncio
from types import SimpleNamespace

import pytest

from backend.src.models import NavigationMode, Position
from backend.src.models.mission import MissionLifecycleStatus, MissionWaypoint
from backend.src.services.mission_service import (
    MissionConflictError,
    MissionService,
    MissionStateError,
    MissionValidationError,
)
from backend.src.api.rest import _safety_state


class DummyNavigationService:
    def __init__(self):
        self.navigation_state = SimpleNamespace(
            navigation_mode=NavigationMode.IDLE,
            planned_path=[],
            current_waypoint_index=0,
            safety_boundaries=[],
        )
        self.stop_calls = 0
        self.emergency_calls = 0
        self.set_speed_calls: list[tuple[float, float]] = []
        self._mission_gate: asyncio.Event | None = None
        self.stop_navigation_results: list[bool] = []
        self.set_speed_failures_remaining = 0

    async def execute_mission(self, mission):
        if self._mission_gate is not None:
            await self._mission_gate.wait()
        return None

    async def stop_navigation(self):
        self.stop_calls += 1
        self.navigation_state.navigation_mode = NavigationMode.IDLE
        if self.stop_navigation_results:
            return self.stop_navigation_results.pop(0)
        return True

    async def set_speed(self, left_speed: float, right_speed: float):
        if self.set_speed_failures_remaining > 0:
            self.set_speed_failures_remaining -= 1
            raise RuntimeError("stop delivery failed")
        self.set_speed_calls.append((left_speed, right_speed))

    async def emergency_stop(self):
        self.emergency_calls += 1
        self.navigation_state.navigation_mode = NavigationMode.EMERGENCY_STOP
        return True


@pytest.mark.asyncio
async def test_create_mission_rejects_waypoints_outside_geofence():
    nav = DummyNavigationService()
    nav.navigation_state.safety_boundaries = [[
        Position(latitude=0.0, longitude=0.0),
        Position(latitude=0.0, longitude=1.0),
        Position(latitude=1.0, longitude=1.0),
        Position(latitude=1.0, longitude=0.0),
    ]]
    service = MissionService(nav)

    with pytest.raises(MissionValidationError, match="outside the configured safety boundary"):
        await service.create_mission(
            "Outside",
            [MissionWaypoint(lat=2.0, lon=2.0, blade_on=False, speed=50)],
        )


@pytest.mark.asyncio
async def test_pause_and_resume_reuse_existing_task():
    nav = DummyNavigationService()
    nav._mission_gate = asyncio.Event()
    service = MissionService(nav)
    mission = await service.create_mission(
        "Test mission",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )

    await service.start_mission(mission.id)
    await asyncio.sleep(0)

    original_task = service.mission_tasks[mission.id]
    assert not original_task.done()

    await service.pause_mission(mission.id)
    assert service.mission_statuses[mission.id].status == MissionLifecycleStatus.PAUSED
    assert nav.navigation_state.navigation_mode == NavigationMode.PAUSED

    await service.resume_mission(mission.id)
    assert service.mission_statuses[mission.id].status == MissionLifecycleStatus.RUNNING
    assert nav.navigation_state.navigation_mode == NavigationMode.AUTO
    assert service.mission_tasks[mission.id] is original_task

    nav._mission_gate.set()
    await asyncio.wait_for(original_task, timeout=1.0)


@pytest.mark.asyncio
async def test_resume_recreates_task_when_paused_mission_was_recovered():
    nav = DummyNavigationService()
    nav._mission_gate = asyncio.Event()
    service = MissionService(nav)
    mission = await service.create_mission(
        "Paused mission",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )
    service.mission_statuses[mission.id].status = MissionLifecycleStatus.PAUSED
    service.mission_statuses[mission.id].current_waypoint_index = 0

    await service.resume_mission(mission.id)

    assert mission.id in service.mission_tasks
    assert not service.mission_tasks[mission.id].done()
    assert service.mission_statuses[mission.id].status == MissionLifecycleStatus.RUNNING

    nav._mission_gate.set()
    await asyncio.wait_for(service.mission_tasks[mission.id], timeout=1.0)


@pytest.mark.asyncio
async def test_abort_cancels_task_and_stops_navigation():
    nav = DummyNavigationService()
    nav._mission_gate = asyncio.Event()
    service = MissionService(nav)
    mission = await service.create_mission(
        "Abort mission",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )

    await service.start_mission(mission.id)
    await asyncio.sleep(0)

    task = service.mission_tasks[mission.id]
    await service.abort_mission(mission.id)
    await asyncio.sleep(0)

    assert task.cancelled() or task.done()
    assert service.mission_statuses[mission.id].status == MissionLifecycleStatus.ABORTED
    assert nav.stop_calls == 1


@pytest.mark.asyncio
async def test_pause_escalates_to_emergency_when_stop_fails():
    nav = DummyNavigationService()
    nav._mission_gate = asyncio.Event()
    nav.set_speed_failures_remaining = 3
    service = MissionService(nav)
    mission = await service.create_mission(
        "Pause escalation",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )

    await service.start_mission(mission.id)
    await asyncio.sleep(0)

    await service.pause_mission(mission.id)

    assert service.mission_statuses[mission.id].status == MissionLifecycleStatus.FAILED
    assert nav.emergency_calls == 1
    assert nav.navigation_state.navigation_mode == NavigationMode.EMERGENCY_STOP


@pytest.mark.asyncio
async def test_abort_escalates_to_emergency_when_stop_navigation_fails():
    nav = DummyNavigationService()
    nav._mission_gate = asyncio.Event()
    nav.stop_navigation_results = [False]
    service = MissionService(nav)
    mission = await service.create_mission(
        "Abort escalation",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )

    await service.start_mission(mission.id)
    await asyncio.sleep(0)

    await service.abort_mission(mission.id)

    assert service.mission_statuses[mission.id].status == MissionLifecycleStatus.ABORTED
    assert "emergency stop activated" in (service.mission_statuses[mission.id].detail or "")
    assert nav.stop_calls == 1
    assert nav.emergency_calls == 1


@pytest.mark.asyncio
async def test_start_mission_rejected_when_emergency_stop_active():
    nav = DummyNavigationService()
    service = MissionService(nav)
    mission = await service.create_mission(
        "Emergency locked mission",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )

    _safety_state["emergency_stop_active"] = True
    try:
        with pytest.raises(MissionStateError, match="emergency stop"):
            await service.start_mission(mission.id)
    finally:
        _safety_state["emergency_stop_active"] = False
