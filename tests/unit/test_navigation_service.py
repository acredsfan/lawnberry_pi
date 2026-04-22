import asyncio

import pytest

import backend.src.services.mission_service as mission_service_module
import backend.src.services.navigation_service as navigation_service_module
from backend.src.models import (
    GpsReading,
    ImuReading,
    NavigationMode,
    PathStatus,
    Position,
    SensorData,
    TofReading,
    Waypoint,
)
from backend.src.models.mission import MissionLifecycleStatus
from backend.src.services.mission_service import MissionService
from backend.src.services.navigation_service import NavigationService


@pytest.fixture(autouse=True)
def reset_mission_singleton():
    original = mission_service_module._mission_service_instance
    mission_service_module._mission_service_instance = None
    yield
    mission_service_module._mission_service_instance = original


def test_are_waypoints_in_geofence():
    nav = NavigationService()
    nav.set_safety_boundaries([
        [
            Position(latitude=0.0, longitude=0.0),
            Position(latitude=0.0, longitude=1.0),
            Position(latitude=1.0, longitude=1.0),
            Position(latitude=1.0, longitude=0.0),
        ]
    ])
    mission_service = MissionService(nav)
    mission = asyncio.run(mission_service.create_mission(
        "Inside",
        [
            {"lat": 0.25, "lon": 0.25, "blade_on": False, "speed": 50},
        ],
    ))

    assert nav.are_waypoints_in_geofence(mission.waypoints) is True


@pytest.mark.asyncio
async def test_execute_mission_waits_while_paused(monkeypatch):
    nav = NavigationService()
    mission_service = MissionService(nav)
    mission_service_module._mission_service_instance = mission_service

    mission = await mission_service.create_mission(
        "Pause test",
        [
            {"lat": 0.1, "lon": 0.1, "blade_on": False, "speed": 50},
        ],
    )
    mission_service.mission_statuses[mission.id].status = MissionLifecycleStatus.PAUSED

    go_to_waypoint_called = asyncio.Event()

    async def fake_go_to_waypoint(_mission, _waypoint):
        go_to_waypoint_called.set()
        nav.navigation_state.current_waypoint_index = len(nav.navigation_state.planned_path)
        return True

    async def fake_bootstrap():
        pass

    monkeypatch.setattr(nav, "go_to_waypoint", fake_go_to_waypoint)
    monkeypatch.setattr(nav, "_bootstrap_heading_from_gps_cog", fake_bootstrap)

    task = asyncio.create_task(nav.execute_mission(mission))
    await asyncio.sleep(0.2)

    assert go_to_waypoint_called.is_set() is False
    assert nav.navigation_state.navigation_mode == NavigationMode.PAUSED

    mission_service.mission_statuses[mission.id].status = MissionLifecycleStatus.RUNNING
    await asyncio.wait_for(task, timeout=1.0)

    assert go_to_waypoint_called.is_set() is True
    assert nav.navigation_state.navigation_mode == NavigationMode.IDLE


@pytest.mark.asyncio
async def test_go_to_waypoint_holds_until_fresh_gps_fix(monkeypatch):
    nav = NavigationService()
    mission_service = MissionService(nav)
    mission_service_module._mission_service_instance = mission_service

    mission = await mission_service.create_mission(
        "GPS freshness hold",
        [
            {"lat": 0.1, "lon": 0.1, "blade_on": False, "speed": 50},
        ],
    )
    mission_service.mission_statuses[mission.id].status = MissionLifecycleStatus.RUNNING

    nav.navigation_state.current_position = Position(latitude=0.1, longitude=0.1, accuracy=1.0)
    nav.navigation_state.last_gps_fix = None
    nav.navigation_state.dead_reckoning_active = True
    nav.navigation_state.planned_path = [Waypoint(position=Position(latitude=0.1, longitude=0.1))]

    stop_commands: list[tuple[float, float]] = []

    async def fake_set_speed(left_speed: float, right_speed: float):
        stop_commands.append((left_speed, right_speed))

    monkeypatch.setattr(nav, "set_speed", fake_set_speed)

    task = asyncio.create_task(nav.go_to_waypoint(mission, mission.waypoints[0]))

    await asyncio.sleep(0.3)
    assert task.done() is False
    assert (0.0, 0.0) in stop_commands

    nav.navigation_state.dead_reckoning_active = False
    nav.navigation_state.last_gps_fix = nav.navigation_state.current_position.timestamp

    assert await asyncio.wait_for(task, timeout=1.0) is True


@pytest.mark.asyncio
async def test_update_path_execution_skips_waypoint_advance_during_mission():
    nav = NavigationService()
    nav.navigation_state.planned_path = [
        Waypoint(position=Position(latitude=1.0, longitude=1.0)),
        Waypoint(position=Position(latitude=2.0, longitude=2.0)),
    ]
    nav.navigation_state.current_position = Position(latitude=1.0, longitude=1.0, accuracy=1.0)
    nav.navigation_state.last_gps_fix = nav.navigation_state.current_position.timestamp
    nav.navigation_state.path_status = PathStatus.EXECUTING
    nav.navigation_state.navigation_mode = NavigationMode.AUTO
    nav._mission_execution_active = True

    await nav._update_path_execution()

    assert nav.navigation_state.current_waypoint_index == 0


@pytest.mark.asyncio
async def test_update_path_execution_requires_verified_position_for_arrival():
    nav = NavigationService()
    nav.navigation_state.planned_path = [
        Waypoint(position=Position(latitude=1.0, longitude=1.0)),
        Waypoint(position=Position(latitude=2.0, longitude=2.0)),
    ]
    nav.navigation_state.current_position = Position(latitude=1.0, longitude=1.0, accuracy=1.0)
    nav.navigation_state.dead_reckoning_active = True
    nav.navigation_state.path_status = PathStatus.EXECUTING
    nav.navigation_state.navigation_mode = NavigationMode.AUTO

    await nav._update_path_execution()

    assert nav.navigation_state.current_waypoint_index == 0
    assert nav.navigation_state.target_velocity == 0.0


@pytest.mark.asyncio
async def test_pause_navigation_stops_motion_and_sets_paused_mode(monkeypatch):
    nav = NavigationService()
    nav.navigation_state.navigation_mode = NavigationMode.AUTO
    nav.navigation_state.path_status = PathStatus.EXECUTING

    stop_commands: list[tuple[float, float]] = []

    async def fake_set_speed(left_speed: float, right_speed: float):
        stop_commands.append((left_speed, right_speed))

    monkeypatch.setattr(nav, "set_speed", fake_set_speed)

    assert await nav.pause_navigation() is True
    assert nav.navigation_state.navigation_mode == NavigationMode.PAUSED
    assert nav.navigation_state.target_velocity == 0.0
    assert stop_commands == [(0.0, 0.0)]


@pytest.mark.asyncio
async def test_resume_navigation_requires_paused_state_and_path():
    nav = NavigationService()
    nav.navigation_state.navigation_mode = NavigationMode.PAUSED
    nav.navigation_state.path_status = PathStatus.INTERRUPTED
    nav.navigation_state.current_position = Position(latitude=1.0, longitude=1.0, accuracy=1.0)
    nav.navigation_state.planned_path = [Waypoint(position=Position(latitude=2.0, longitude=2.0))]

    assert await nav.resume_navigation() is True
    assert nav.navigation_state.navigation_mode == NavigationMode.AUTO
    assert nav.navigation_state.path_status == PathStatus.EXECUTING


@pytest.mark.asyncio
async def test_update_navigation_state_uses_configured_tof_threshold(monkeypatch):
    class StubConfigLoader:
        def get(self):
            return object(), type("Limits", (), {"tof_obstacle_distance_meters": 0.2})()

    monkeypatch.setattr(navigation_service_module, "ConfigLoader", StubConfigLoader)

    nav = NavigationService()

    clear_path_data = SensorData(
        gps=GpsReading(latitude=1.0, longitude=1.0, accuracy=0.5),
        imu=ImuReading(yaw=0.0),
        tof_left=TofReading(distance=250.0, sensor_side="left"),
        tof_right=TofReading(distance=350.0, sensor_side="right"),
    )
    await nav.update_navigation_state(clear_path_data)
    assert nav.navigation_state.obstacle_avoidance_active is False

    blocked_path_data = SensorData(
        gps=GpsReading(latitude=1.0, longitude=1.0, accuracy=0.5),
        imu=ImuReading(yaw=0.0),
        tof_left=TofReading(distance=199.0, sensor_side="left"),
    )
    await nav.update_navigation_state(blocked_path_data)
    assert nav.navigation_state.obstacle_avoidance_active is True


@pytest.mark.asyncio
async def test_go_to_waypoint_fails_when_heading_missing_too_long(monkeypatch):
    nav = NavigationService()
    nav.position_verification_timeout_seconds = 0.1
    mission_service = MissionService(nav)
    mission_service_module._mission_service_instance = mission_service

    mission = await mission_service.create_mission(
        "Heading missing",
        [
            {"lat": 0.1, "lon": 0.2, "blade_on": False, "speed": 50},
        ],
    )
    mission_service.mission_statuses[mission.id].status = MissionLifecycleStatus.RUNNING
    nav.navigation_state.current_position = Position(latitude=0.0, longitude=0.0, accuracy=1.0)
    nav.navigation_state.last_gps_fix = nav.navigation_state.current_position.timestamp
    nav.navigation_state.dead_reckoning_active = False
    nav.navigation_state.heading = None

    async def fake_deliver_stop_command(*, reason: str, retries: int = 3, initial_delay: float = 0.1):
        return True

    async def fake_emergency_stop():
        nav.navigation_state.navigation_mode = NavigationMode.EMERGENCY_STOP
        return True

    async def fake_set_speed(left: float, right: float) -> None:
        pass

    monkeypatch.setattr(nav, "_deliver_stop_command", fake_deliver_stop_command)
    monkeypatch.setattr(nav, "emergency_stop", fake_emergency_stop)
    monkeypatch.setattr(nav, "set_speed", fake_set_speed)

    with pytest.raises(RuntimeError, match="Heading unavailable while navigating waypoint"):
        await nav.go_to_waypoint(mission, mission.waypoints[0])


@pytest.mark.asyncio
async def test_execute_mission_marks_navigation_failed_on_waypoint_error(monkeypatch):
    nav = NavigationService()
    mission_service = MissionService(nav)
    mission_service_module._mission_service_instance = mission_service

    mission = await mission_service.create_mission(
        "Execution failure",
        [
            {"lat": 0.1, "lon": 0.2, "blade_on": False, "speed": 50},
        ],
    )
    mission_service.mission_statuses[mission.id].status = MissionLifecycleStatus.RUNNING

    stop_reasons: list[str] = []

    async def fake_go_to_waypoint(_mission, _waypoint):
        raise RuntimeError("Heading unavailable while navigating waypoint")

    async def fake_deliver_stop_command(*, reason: str, retries: int = 3, initial_delay: float = 0.1):
        stop_reasons.append(reason)
        return True

    async def fake_bootstrap():
        pass

    monkeypatch.setattr(nav, "go_to_waypoint", fake_go_to_waypoint)
    monkeypatch.setattr(nav, "_deliver_stop_command", fake_deliver_stop_command)
    monkeypatch.setattr(nav, "_bootstrap_heading_from_gps_cog", fake_bootstrap)

    with pytest.raises(RuntimeError, match="Heading unavailable while navigating waypoint"):
        await nav.execute_mission(mission)

    assert nav.navigation_state.path_status == PathStatus.FAILED
    assert nav.navigation_state.navigation_mode == NavigationMode.IDLE
    assert nav.navigation_state.target_velocity == 0.0
    assert stop_reasons == ["mission failure"]


@pytest.mark.asyncio
async def test_gps_reacquisition_clears_dead_reckoning_and_logs_mismatch(caplog):
    """After GPS outage (dead reckoning active), re-acquiring GPS clears the DR flag
    and emits a position-mismatch warning when divergence exceeds the threshold."""
    import logging

    nav = NavigationService()
    nav.position_mismatch_warn_threshold_m = 2.0  # low threshold for test

    # Simulate GPS outage: run DR first
    nav.navigation_state.heading = 0.0
    dr_sd = SensorData(imu=ImuReading(yaw=0.0))
    await nav.update_navigation_state(dr_sd)
    assert nav.navigation_state.dead_reckoning_active is True

    # Force DR estimated position far from the incoming GPS fix to trigger warning
    nav.dead_reckoning.estimated_position = Position(latitude=0.0, longitude=0.0, accuracy=10.0)

    # Provide a GPS fix that is > 2m away from (0, 0) — (1.0, 1.0) is ~157 km away
    gps_sd = SensorData(
        gps=GpsReading(latitude=1.0, longitude=1.0, accuracy=1.5),
    )
    with caplog.at_level(logging.WARNING, logger="backend.src.services.navigation_service"):
        state = await nav.update_navigation_state(gps_sd)

    assert state.dead_reckoning_active is False, "dead_reckoning_active should be cleared on GPS fix"
    assert state.last_gps_fix is not None, "last_gps_fix should be set on GPS fix"
    assert abs(state.current_position.latitude - 1.0) < 1e-6, "position should snap to GPS"

    # A position-mismatch warning must have been emitted
    mismatch_records = [
        r for r in caplog.records
        if "position mismatch" in r.message.lower() and r.levelno >= logging.WARNING
    ]
    assert mismatch_records, (
        "Expected a position-mismatch WARNING when GPS re-acquired after DR divergence"
    )


@pytest.mark.asyncio
async def test_gps_reacquisition_no_mismatch_warning_when_within_threshold(caplog):
    """When GPS returns with negligible divergence from DR estimate, only an INFO
    re-sync message is emitted — no WARNING."""
    import logging

    nav = NavigationService()
    nav.position_mismatch_warn_threshold_m = 1000.0  # very high threshold

    # Seed dead reckoning
    nav.navigation_state.heading = 0.0
    await nav.update_navigation_state(SensorData(imu=ImuReading(yaw=0.0)))
    assert nav.navigation_state.dead_reckoning_active is True

    # DR position is at origin; GPS fix also effectively at origin (tiny offset)
    nav.dead_reckoning.estimated_position = Position(latitude=37.0, longitude=-122.0, accuracy=10.0)

    gps_sd = SensorData(
        gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=1.0),
    )
    with caplog.at_level(logging.DEBUG, logger="backend.src.services.navigation_service"):
        state = await nav.update_navigation_state(gps_sd)

    assert state.dead_reckoning_active is False

    # No WARNING-level mismatch record expected
    warning_mismatch = [
        r for r in caplog.records
        if "position mismatch" in r.message.lower() and r.levelno >= logging.WARNING
    ]
    assert not warning_mismatch, (
        "No position-mismatch WARNING expected when divergence is within threshold"
    )
    # But an INFO re-sync log should be present
    info_resync = [
        r for r in caplog.records
        if "gps re-acquired" in r.message.lower() and r.levelno == logging.INFO
    ]
    assert info_resync, "Expected an INFO re-sync log on clean GPS re-acquisition"


@pytest.mark.asyncio
async def test_bootstrap_geofence_violation_aborts_mission():
    """Bootstrap drive that exits geofence must latch emergency and abort."""
    from unittest.mock import AsyncMock, MagicMock

    nav = NavigationService.__new__(NavigationService)
    from backend.src.models import NavigationState
    state = NavigationState()
    # Position outside boundary square (0,0)-(1,1)
    state.current_position = Position(latitude=5.0, longitude=5.0)
    state.safety_boundaries = [[
        Position(latitude=0.0, longitude=0.0),
        Position(latitude=0.0, longitude=1.0),
        Position(latitude=1.0, longitude=1.0),
        Position(latitude=1.0, longitude=0.0),
    ]]
    nav.navigation_state = state
    nav._global_emergency_active = MagicMock(return_value=False)
    nav._latch_global_emergency_state = MagicMock()
    nav._bootstrap_heading_from_gps_cog = AsyncMock()
    nav._load_boundaries_from_zones = MagicMock()

    with pytest.raises(RuntimeError, match="Bootstrap drive exited geofence"):
        await nav._run_bootstrap_and_check_geofence()

    nav._latch_global_emergency_state.assert_called_once()
