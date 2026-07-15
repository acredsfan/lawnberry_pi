import asyncio
from types import SimpleNamespace

import pytest

from backend.src.api.rest import _safety_state
from backend.src.models import NavigationMode, Position
from backend.src.models.mission import MissionLegType, MissionLifecycleStatus, MissionWaypoint
from backend.src.services.mission_service import (
    MissionConflictError,
    MissionService,
    MissionStateError,
    MissionValidationError,
)


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
        self.execute_exception: Exception | None = None
        self.reuse_heading_alignment_calls: list[bool] = []

    async def execute_mission(
        self,
        mission,
        mission_service=None,
        *,
        reuse_heading_alignment=False,
    ):
        # mission_service intentionally unused in this test stub
        self.reuse_heading_alignment_calls.append(reuse_heading_alignment)
        if self._mission_gate is not None:
            await self._mission_gate.wait()
        if self.execute_exception is not None:
            raise self.execute_exception
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


def test_legacy_blade_flag_defaults_off_without_leg_semantics():
    waypoint = MissionWaypoint(lat=0.1, lon=0.1, blade_on=True)

    assert waypoint.leg_type == MissionLegType.TRANSIT
    assert waypoint.blade_on is False
    assert waypoint.blade_permitted is False


def test_blade_is_permitted_only_on_explicit_mow_leg():
    waypoint = MissionWaypoint(
        lat=0.1,
        lon=0.1,
        blade_on=True,
        leg_type=MissionLegType.MOW,
    )

    assert waypoint.blade_permitted is True


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


@pytest.mark.asyncio
async def test_blade_off_diagnostic_rejects_blade_on_waypoints():
    nav = DummyNavigationService()
    service = MissionService(nav)
    mission = await service.create_mission(
        "Blade-on mission",
        [
            MissionWaypoint(
                lat=0.1,
                lon=0.1,
                blade_on=True,
                leg_type=MissionLegType.MOW,
                speed=50,
            )
        ],
    )

    with pytest.raises(MissionStateError, match="Blade-off diagnostic mode"):
        await service.start_mission(mission.id, blade_off_diagnostic=True)


@pytest.mark.asyncio
async def test_start_return_home_creates_blade_off_dock_mission():
    nav = DummyNavigationService()
    nav.build_return_home_waypoints = lambda: [
        MissionWaypoint(
            lat=0.1,
            lon=0.1,
            leg_type=MissionLegType.DOCK,
            blade_on=False,
        )
    ]
    service = MissionService(nav)

    mission = await service.start_return_home()

    assert mission.id in service.missions
    assert mission.waypoints[-1].leg_type == MissionLegType.DOCK
    assert all(not waypoint.blade_permitted for waypoint in mission.waypoints)


@pytest.mark.asyncio
async def test_start_return_home_removes_rejected_mission(monkeypatch):
    nav = DummyNavigationService()
    nav.build_return_home_waypoints = lambda: [
        MissionWaypoint(lat=0.1, lon=0.1, leg_type=MissionLegType.DOCK)
    ]
    service = MissionService(nav)

    async def reject_start(*args, **kwargs):
        raise MissionStateError("admission rejected")

    monkeypatch.setattr(service, "start_mission", reject_start)

    with pytest.raises(MissionStateError, match="admission rejected"):
        await service.start_return_home()

    assert service.missions == {}


@pytest.mark.asyncio
async def test_heading_reuse_is_restricted_to_blade_off_diagnostic():
    nav = DummyNavigationService()
    service = MissionService(nav)
    mission = await service.create_mission(
        "Diagnostic route",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=20)],
    )

    with pytest.raises(MissionStateError, match="restricted to blade-off diagnostics"):
        await service.start_mission(mission.id, reuse_heading_alignment=True)


@pytest.mark.asyncio
async def test_blade_off_diagnostic_can_reuse_saved_heading_without_repeat_bootstrap():
    nav = DummyNavigationService()
    service = MissionService(nav)
    mission = await service.create_mission(
        "Boundary verification leg",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=20)],
    )

    await service.start_mission(
        mission.id,
        blade_off_diagnostic=True,
        reuse_heading_alignment=True,
    )
    await asyncio.sleep(0)

    assert nav.reuse_heading_alignment_calls == [True]


@pytest.mark.asyncio
async def test_start_mission_surfaces_navigation_failure_detail():
    nav = DummyNavigationService()
    nav.execute_exception = RuntimeError("Heading unavailable while navigating waypoint")
    service = MissionService(nav)
    mission = await service.create_mission(
        "Execution failure",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )

    await service.start_mission(mission.id)
    for _ in range(20):
        if service.mission_statuses[mission.id].status == MissionLifecycleStatus.FAILED:
            break
        await asyncio.sleep(0.01)

    assert service.mission_statuses[mission.id].status == MissionLifecycleStatus.FAILED
    assert service.mission_statuses[mission.id].detail == "Heading unavailable while navigating waypoint"


@pytest.mark.asyncio
async def test_update_mission_happy_path():
    """update_mission mutates name/waypoints in place, keeps id + created_at."""
    nav = DummyNavigationService()
    service = MissionService(nav)
    mission = await service.create_mission(
        "original", [MissionWaypoint(lat=0.1, lon=0.1)]
    )
    original_id = mission.id
    original_created_at = mission.created_at

    updated = await service.update_mission(
        mission.id, name="renamed", waypoints=[MissionWaypoint(lat=0.2, lon=0.2)]
    )

    assert updated.id == original_id
    assert updated.created_at == original_created_at
    assert updated.name == "renamed"
    assert updated.waypoints[0].lat == pytest.approx(0.2)
    # In-memory dict also updated
    assert service.missions[original_id].name == "renamed"


@pytest.mark.asyncio
async def test_update_mission_rejects_when_running():
    nav = DummyNavigationService()
    service = MissionService(nav)
    mission = await service.create_mission("m", [MissionWaypoint(lat=0.1, lon=0.1)])
    service.mission_statuses[mission.id].status = MissionLifecycleStatus.RUNNING

    with pytest.raises(MissionConflictError, match="running or paused"):
        await service.update_mission(mission.id, name="renamed")


@pytest.mark.asyncio
async def test_update_mission_rejects_when_paused():
    nav = DummyNavigationService()
    service = MissionService(nav)
    mission = await service.create_mission("m", [MissionWaypoint(lat=0.1, lon=0.1)])
    service.mission_statuses[mission.id].status = MissionLifecycleStatus.PAUSED

    with pytest.raises(MissionConflictError, match="running or paused"):
        await service.update_mission(mission.id, name="renamed")


@pytest.mark.asyncio
async def test_update_mission_terminal_states_allowed():
    """Completed/aborted/failed missions can be edited."""
    nav = DummyNavigationService()
    service = MissionService(nav)
    for terminal in (MissionLifecycleStatus.COMPLETED, MissionLifecycleStatus.ABORTED, MissionLifecycleStatus.FAILED):
        mission = await service.create_mission("m", [MissionWaypoint(lat=0.1, lon=0.1)])
        service.mission_statuses[mission.id].status = terminal
        updated = await service.update_mission(mission.id, name="new name")
        assert updated.name == "new name"


@pytest.mark.asyncio
async def test_delete_mission_happy_path():
    nav = DummyNavigationService()
    service = MissionService(nav)
    mission = await service.create_mission("m", [MissionWaypoint(lat=0.1, lon=0.1)])

    await service.delete_mission(mission.id)

    assert mission.id not in service.missions
    assert mission.id not in service.mission_statuses


@pytest.mark.asyncio
async def test_delete_mission_rejects_when_running():
    nav = DummyNavigationService()
    service = MissionService(nav)
    mission = await service.create_mission("m", [MissionWaypoint(lat=0.1, lon=0.1)])
    service.mission_statuses[mission.id].status = MissionLifecycleStatus.RUNNING

    with pytest.raises(MissionConflictError, match="running or paused"):
        await service.delete_mission(mission.id)


@pytest.mark.asyncio
async def test_delete_mission_rejects_when_paused():
    nav = DummyNavigationService()
    service = MissionService(nav)
    mission = await service.create_mission("m", [MissionWaypoint(lat=0.1, lon=0.1)])
    service.mission_statuses[mission.id].status = MissionLifecycleStatus.PAUSED

    with pytest.raises(MissionConflictError, match="running or paused"):
        await service.delete_mission(mission.id)
