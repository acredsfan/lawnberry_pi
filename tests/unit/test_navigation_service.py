import asyncio

import pytest

import backend.src.services.mission_service as mission_service_module
from backend.src.models import NavigationMode, PathStatus, Position, Waypoint
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

    monkeypatch.setattr(nav, "go_to_waypoint", fake_go_to_waypoint)

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