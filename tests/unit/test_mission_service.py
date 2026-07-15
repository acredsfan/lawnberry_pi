import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.src.api.rest import _safety_state
from backend.src.models import NavigationMode, Position
from backend.src.models.mission import MissionLegType, MissionLifecycleStatus, MissionWaypoint
from backend.src.services import ai_service as ai_service_module
from backend.src.services import camera_runtime as camera_runtime_module
from backend.src.services.mission_service import (
    MissionConflictError,
    MissionService,
    MissionStateError,
    MissionValidationError,
)
from backend.src.services.power_manager import PowerManager


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
async def test_concurrent_start_admits_exactly_one_navigation_task():
    nav = DummyNavigationService()
    nav._mission_gate = asyncio.Event()

    class BarrierPowerManager:
        def __init__(self):
            self.entered = asyncio.Event()
            self.release = asyncio.Event()
            self.calls = 0

        async def wake_for_mission(self):
            self.calls += 1
            self.entered.set()
            await self.release.wait()

    power = BarrierPowerManager()
    service = MissionService(nav, power_manager=power)
    mission = await service.create_mission(
        "Concurrent start",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )

    first = asyncio.create_task(service.start_mission(mission.id))
    await power.entered.wait()
    second = asyncio.create_task(service.start_mission(mission.id))
    await asyncio.sleep(0)
    power.release.set()

    assert (await first).status == MissionLifecycleStatus.RUNNING
    with pytest.raises(MissionConflictError, match="already active"):
        await second
    await asyncio.sleep(0)

    assert power.calls == 1
    assert len(nav.reuse_heading_alignment_calls) == 1
    assert list(service.mission_tasks) == [mission.id]

    mission_task = service.mission_tasks[mission.id]
    nav._mission_gate.set()
    await asyncio.wait_for(mission_task, timeout=1.0)


@pytest.mark.asyncio
async def test_bulk_delete_waits_for_start_admission_and_skips_running_mission():
    nav = DummyNavigationService()
    nav._mission_gate = asyncio.Event()

    class BarrierPowerManager:
        def __init__(self):
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def wake_for_mission(self):
            self.entered.set()
            await self.release.wait()

    power = BarrierPowerManager()
    service = MissionService(nav, power_manager=power)
    mission = await service.create_mission(
        "Bulk delete race",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )

    start_task = asyncio.create_task(service.start_mission(mission.id))
    await power.entered.wait()
    delete_task = asyncio.create_task(service.delete_all_missions())
    await asyncio.sleep(0)

    assert not delete_task.done()

    power.release.set()
    assert (await start_task).status == MissionLifecycleStatus.RUNNING
    result = await delete_task

    assert result["deleted"] == 0
    assert result["skipped"] == [
        {"id": mission.id, "name": mission.name, "reason": "running"}
    ]
    assert mission.id in service.missions
    assert mission.id in service.mission_tasks

    nav._mission_gate.set()
    await asyncio.wait_for(service.mission_tasks[mission.id], timeout=1.0)


@pytest.mark.asyncio
async def test_update_waits_for_diagnostic_admission_and_cannot_enable_blade():
    nav = DummyNavigationService()
    nav._mission_gate = asyncio.Event()

    class BarrierPowerManager:
        def __init__(self):
            self.entered = asyncio.Event()
            self.release = asyncio.Event()

        async def wake_for_mission(self):
            self.entered.set()
            await self.release.wait()

    power = BarrierPowerManager()
    service = MissionService(nav, power_manager=power)
    mission = await service.create_mission(
        "Diagnostic mutation race",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=20)],
    )

    start_task = asyncio.create_task(
        service.start_mission(mission.id, blade_off_diagnostic=True)
    )
    await power.entered.wait()
    update_task = asyncio.create_task(
        service.update_mission(
            mission.id,
            waypoints=[
                MissionWaypoint(
                    lat=0.1,
                    lon=0.1,
                    blade_on=True,
                    leg_type=MissionLegType.MOW,
                    speed=20,
                )
            ],
        )
    )
    await asyncio.sleep(0)

    assert not update_task.done()

    power.release.set()
    assert (await start_task).status == MissionLifecycleStatus.RUNNING
    with pytest.raises(MissionConflictError, match="running or paused"):
        await update_task

    assert all(not waypoint.blade_permitted for waypoint in mission.waypoints)

    nav._mission_gate.set()
    await asyncio.wait_for(service.mission_tasks[mission.id], timeout=1.0)


@pytest.mark.asyncio
async def test_pause_cannot_overwrite_concurrent_task_completion():
    nav = DummyNavigationService()
    nav._mission_gate = asyncio.Event()
    service = MissionService(nav)
    mission = await service.create_mission(
        "Pause completion race",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )

    await service.start_mission(mission.id)
    mission_task = service.mission_tasks[mission.id]

    async def complete_during_stop(left_speed: float, right_speed: float):
        assert (left_speed, right_speed) == (0.0, 0.0)
        nav._mission_gate.set()
        await asyncio.shield(mission_task)

    nav.set_speed = complete_during_stop

    result = await service.pause_mission(mission.id)

    assert result.status == MissionLifecycleStatus.COMPLETED
    assert result.completion_percentage == 100.0
    assert mission.id not in service.mission_tasks
    assert len(nav.reuse_heading_alignment_calls) == 1
    with pytest.raises(MissionStateError, match="not paused"):
        await service.resume_mission(mission.id)


@pytest.mark.asyncio
async def test_pause_returns_terminal_truth_when_task_finishes_during_broadcast():
    nav = DummyNavigationService()
    nav._mission_gate = asyncio.Event()
    service = MissionService(nav)
    mission = await service.create_mission(
        "Pause broadcast completion race",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )

    await service.start_mission(mission.id)
    mission_task = service.mission_tasks[mission.id]

    async def complete_during_pause_broadcast(
        broadcast_mission_id: str,
        detail: str = "",
    ) -> None:
        assert broadcast_mission_id == mission.id
        assert detail == "Mission paused"
        nav._mission_gate.set()
        await asyncio.shield(mission_task)

    service._broadcast_status = complete_during_pause_broadcast

    result = await service.pause_mission(mission.id)

    assert result.status == MissionLifecycleStatus.COMPLETED
    assert result.completion_percentage == 100.0
    assert mission.id not in service.mission_tasks


@pytest.mark.asyncio
async def test_second_mission_cannot_take_motion_ownership():
    nav = DummyNavigationService()
    nav._mission_gate = asyncio.Event()
    service = MissionService(nav)
    first = await service.create_mission(
        "First mission",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )
    second = await service.create_mission(
        "Second mission",
        [MissionWaypoint(lat=0.2, lon=0.2, blade_on=False, speed=50)],
    )

    await service.start_mission(first.id)

    with pytest.raises(MissionConflictError, match="only one mission"):
        await service.start_mission(second.id)

    mission_task = service.mission_tasks[first.id]
    nav._mission_gate.set()
    await asyncio.wait_for(mission_task, timeout=1.0)


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

    monkeypatch.setattr(service, "_start_mission_unlocked", reject_start)

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
async def test_start_mission_wakes_camera_and_ai_before_navigation_dispatch(monkeypatch):
    order: list[str] = []
    camera = SimpleNamespace(stream=SimpleNamespace(is_active=False))

    async def get_camera_status():
        order.append("camera.status")
        return {"is_active": camera.stream.is_active}

    async def start_streaming():
        order.append("camera.start")
        camera.stream.is_active = True
        return True

    async def set_ai_enabled(enabled):
        order.append(f"camera.ai={enabled}")

    camera.get_camera_status = get_camera_status
    camera.start_streaming = start_streaming
    camera.set_ai_enabled = set_ai_enabled
    local_ai = SimpleNamespace(
        set_enabled=lambda enabled: order.append(f"local.ai={enabled}")
    )
    monkeypatch.setattr(camera_runtime_module, "camera_service", camera)
    monkeypatch.setattr(ai_service_module, "get_ai_service", lambda: local_ai)
    power_manager = PowerManager()
    power_manager._ai_soft_disabled = True

    nav = DummyNavigationService()
    nav._mission_gate = asyncio.Event()
    original_execute = nav.execute_mission

    async def assert_ready_then_execute(*args, **kwargs):
        order.append("navigation.execute")
        assert camera.stream.is_active is True
        assert "camera.ai=True" in order
        return await original_execute(*args, **kwargs)

    monkeypatch.setattr(nav, "execute_mission", assert_ready_then_execute)
    service = MissionService(nav, power_manager=power_manager)
    mission = await service.create_mission(
        "Power wake ordering",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )

    await service.start_mission(mission.id)
    await asyncio.sleep(0)

    assert order.index("camera.start") < order.index("navigation.execute")
    assert order.index("camera.ai=True") < order.index("navigation.execute")
    assert power_manager._ai_soft_disabled is False

    nav._mission_gate.set()
    await asyncio.wait_for(service.mission_tasks[mission.id], timeout=1.0)


@pytest.mark.asyncio
async def test_start_mission_fails_before_task_when_power_wake_is_unacknowledged(
    monkeypatch,
):
    power_manager = SimpleNamespace(
        wake_for_mission=AsyncMock(side_effect=RuntimeError("owner IPC unavailable"))
    )
    nav = DummyNavigationService()
    service = MissionService(nav, power_manager=power_manager)
    mission = await service.create_mission(
        "Power wake failure",
        [MissionWaypoint(lat=0.1, lon=0.1, blade_on=False, speed=50)],
    )

    with pytest.raises(MissionStateError, match="CAMERA_AI_POWER_WAKE_FAILED"):
        await service.start_mission(mission.id)

    assert mission.id not in service.mission_tasks
    assert service.mission_statuses[mission.id].status == MissionLifecycleStatus.IDLE


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
