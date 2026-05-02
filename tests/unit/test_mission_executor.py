"""Unit tests for MissionExecutor.

All tests use fake localization (FakeLocalization) and fake gateway (FakeGateway)
so no hardware, RoboHAT, or NavigationService instance is required.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.src.models import NavigationMode, PathStatus, Position
from backend.src.models.mission import MissionLifecycleStatus


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------

class FakeLocalization:
    """Minimal LocalizationProvider for testing."""

    def __init__(
        self,
        *,
        position: Position | None = None,
        heading: float | None = 0.0,
        dead_reckoning_active: bool = False,
        last_gps_fix: datetime | None = None,
    ):
        self._position = position
        self._heading = heading
        self._dead_reckoning_active = dead_reckoning_active
        self._last_gps_fix = last_gps_fix or datetime.now(UTC)

    @property
    def current_position(self) -> Position | None:
        return self._position

    @property
    def heading(self) -> float | None:
        return self._heading

    @property
    def dead_reckoning_active(self) -> bool:
        return self._dead_reckoning_active

    @property
    def last_gps_fix(self) -> datetime | None:
        return self._last_gps_fix


class FakeGateway:
    """Minimal gateway stub — records drive calls, never errors."""

    def __init__(self):
        self.drive_calls: list[tuple[float, float]] = []
        self._emergency = False

    def is_emergency_active(self) -> bool:
        return self._emergency

    async def dispatch_drive_speeds(self, left: float, right: float) -> bool:
        self.drive_calls.append((left, right))
        return True


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------

def test_mission_executor_constructs():
    from backend.src.services.mission_executor import MissionExecutor

    loc = FakeLocalization()
    gw = FakeGateway()
    executor = MissionExecutor(localization=loc, gateway=gw)
    assert executor is not None


# ---------------------------------------------------------------------------
# Task 4: Position verification helpers
# ---------------------------------------------------------------------------

def test_position_verified_when_gps_fresh_and_accurate():
    from backend.src.services.mission_executor import MissionExecutor

    loc = FakeLocalization(
        position=Position(latitude=1.0, longitude=1.0, accuracy=1.0),
        dead_reckoning_active=False,
        last_gps_fix=datetime.now(UTC),
    )
    executor = MissionExecutor(localization=loc, gateway=FakeGateway())
    assert executor._position_is_verified() is True


def test_position_not_verified_when_dead_reckoning():
    from backend.src.services.mission_executor import MissionExecutor

    loc = FakeLocalization(
        position=Position(latitude=1.0, longitude=1.0, accuracy=1.0),
        dead_reckoning_active=True,
        last_gps_fix=datetime.now(UTC),
    )
    executor = MissionExecutor(localization=loc, gateway=FakeGateway())
    assert executor._position_is_verified() is False


def test_position_not_verified_when_accuracy_too_low():
    from backend.src.services.mission_executor import MissionExecutor

    loc = FakeLocalization(
        position=Position(latitude=1.0, longitude=1.0, accuracy=99.0),
        dead_reckoning_active=False,
        last_gps_fix=datetime.now(UTC),
    )
    executor = MissionExecutor(localization=loc, gateway=FakeGateway(), max_waypoint_accuracy_m=5.0)
    assert executor._position_is_verified() is False


def test_position_not_verified_when_no_position():
    from backend.src.services.mission_executor import MissionExecutor

    loc = FakeLocalization(position=None)
    executor = MissionExecutor(localization=loc, gateway=FakeGateway())
    assert executor._position_is_verified() is False


# ---------------------------------------------------------------------------
# Task 5: Stop delivery helper
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deliver_stop_succeeds_on_first_attempt():
    from backend.src.services.mission_executor import MissionExecutor

    gw = FakeGateway()
    executor = MissionExecutor(localization=FakeLocalization(), gateway=gw)
    result = await executor._deliver_stop_command(reason="test")
    assert result is True
    assert (0.0, 0.0) in gw.drive_calls


@pytest.mark.asyncio
async def test_deliver_stop_returns_false_when_all_retries_fail():
    from backend.src.services.mission_executor import MissionExecutor

    class FailingGateway(FakeGateway):
        async def dispatch_drive_speeds(self, left: float, right: float) -> bool:
            raise RuntimeError("hardware unavailable")

    executor = MissionExecutor(
        localization=FakeLocalization(),
        gateway=FailingGateway(),
    )
    result = await executor._deliver_stop_command(reason="test", retries=2, initial_delay=0.0)
    assert result is False


# ---------------------------------------------------------------------------
# Task 6: go_to_waypoint
# ---------------------------------------------------------------------------

def _make_mission(waypoints_dicts):
    """Build a minimal Mission object for testing."""
    from backend.src.models.mission import Mission, MissionWaypoint, MissionStatus, MissionLifecycleStatus

    wps = [MissionWaypoint(**d) for d in waypoints_dicts]
    mission = Mission(name="test", waypoints=wps, created_at=datetime.now(UTC).isoformat())
    return mission


def _make_status(mission, status=None):
    from backend.src.models.mission import MissionStatus, MissionLifecycleStatus

    if status is None:
        status = MissionLifecycleStatus.RUNNING
    return MissionStatus(
        mission_id=mission.id,
        status=status,
        current_waypoint_index=0,
        completion_percentage=0.0,
        total_waypoints=len(mission.waypoints),
    )


class FakeMissionStatusReader:
    def __init__(self, mission, status):
        self.mission = mission
        self._status = status
        self.mission_statuses = {mission.id: status}
        self.progress_calls = []

    async def update_waypoint_progress(self, mission_id: str, waypoint_index: int) -> None:
        self.progress_calls.append((mission_id, waypoint_index))


@pytest.mark.asyncio
async def test_go_to_waypoint_returns_true_when_already_at_target():
    from backend.src.services.mission_executor import MissionExecutor

    # Position already within tolerance of target
    loc = FakeLocalization(
        position=Position(latitude=1.0, longitude=1.0, accuracy=0.5),
        heading=0.0,
        dead_reckoning_active=False,
        last_gps_fix=datetime.now(UTC),
    )
    gw = FakeGateway()
    executor = MissionExecutor(localization=loc, gateway=gw, waypoint_tolerance=1.0)

    mission = _make_mission([{"lat": 1.0, "lon": 1.0, "blade_on": False, "speed": 50}])
    status = _make_status(mission)
    ms_reader = FakeMissionStatusReader(mission, status)

    reached = await executor.go_to_waypoint(mission, mission.waypoints[0], ms_reader)
    assert reached is True


@pytest.mark.asyncio
async def test_go_to_waypoint_returns_false_when_mission_aborted():
    from backend.src.services.mission_executor import MissionExecutor
    from backend.src.models.mission import MissionLifecycleStatus

    loc = FakeLocalization(
        position=Position(latitude=0.0, longitude=0.0, accuracy=0.5),
        heading=0.0,
        dead_reckoning_active=False,
        last_gps_fix=datetime.now(UTC),
    )
    gw = FakeGateway()
    executor = MissionExecutor(localization=loc, gateway=gw)

    mission = _make_mission([{"lat": 1.0, "lon": 1.0, "blade_on": False, "speed": 50}])
    from backend.src.models.mission import MissionStatus
    status = MissionStatus(
        mission_id=mission.id,
        status=MissionLifecycleStatus.ABORTED,
        current_waypoint_index=0,
        completion_percentage=0.0,
        total_waypoints=1,
    )
    ms_reader = FakeMissionStatusReader(mission, status)

    reached = await executor.go_to_waypoint(mission, mission.waypoints[0], ms_reader)
    assert reached is False


@pytest.mark.asyncio
async def test_go_to_waypoint_holds_when_paused():
    from backend.src.services.mission_executor import MissionExecutor
    from backend.src.models.mission import MissionLifecycleStatus, MissionStatus

    loc = FakeLocalization(
        position=Position(latitude=0.0, longitude=0.0, accuracy=0.5),
        heading=0.0,
        dead_reckoning_active=False,
        last_gps_fix=datetime.now(UTC),
    )
    gw = FakeGateway()
    executor = MissionExecutor(localization=loc, gateway=gw)

    mission = _make_mission([{"lat": 1.0, "lon": 1.0, "blade_on": False, "speed": 50}])
    status = MissionStatus(
        mission_id=mission.id,
        status=MissionLifecycleStatus.PAUSED,
        current_waypoint_index=0,
        completion_percentage=0.0,
        total_waypoints=1,
    )
    ms_reader = FakeMissionStatusReader(mission, status)

    task = asyncio.create_task(
        executor.go_to_waypoint(mission, mission.waypoints[0], ms_reader)
    )
    await asyncio.sleep(0.2)
    # Still paused — should not have returned
    assert not task.done()

    # Resume it by switching to aborted and letting task finish
    status.status = MissionLifecycleStatus.ABORTED
    result = await asyncio.wait_for(task, timeout=1.0)
    assert result is False


@pytest.mark.asyncio
async def test_go_to_waypoint_blocked_by_emergency():
    from backend.src.services.mission_executor import MissionExecutor

    loc = FakeLocalization(
        position=Position(latitude=0.0, longitude=0.0, accuracy=0.5),
        heading=0.0,
        dead_reckoning_active=False,
        last_gps_fix=datetime.now(UTC),
    )
    gw = FakeGateway()
    gw._emergency = True
    executor = MissionExecutor(localization=loc, gateway=gw)

    mission = _make_mission([{"lat": 1.0, "lon": 1.0, "blade_on": False, "speed": 50}])
    status = _make_status(mission)
    ms_reader = FakeMissionStatusReader(mission, status)

    reached = await executor.go_to_waypoint(mission, mission.waypoints[0], ms_reader)
    assert reached is False


# ---------------------------------------------------------------------------
# Task 7: execute_mission
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_mission_completes_when_all_waypoints_reached():
    from backend.src.services.mission_executor import MissionExecutor
    from backend.src.models.mission import MissionLifecycleStatus

    # Position already within tolerance of every waypoint
    loc = FakeLocalization(
        position=Position(latitude=0.1, longitude=0.1, accuracy=0.3),
        heading=0.0,
        dead_reckoning_active=False,
        last_gps_fix=datetime.now(UTC),
    )
    gw = FakeGateway()
    executor = MissionExecutor(localization=loc, gateway=gw, waypoint_tolerance=20000.0)

    mission = _make_mission([
        {"lat": 0.1, "lon": 0.1, "blade_on": False, "speed": 50},
        {"lat": 0.2, "lon": 0.2, "blade_on": False, "speed": 50},
    ])
    from backend.src.models.mission import MissionStatus
    status = MissionStatus(
        mission_id=mission.id,
        status=MissionLifecycleStatus.RUNNING,
        current_waypoint_index=0,
        completion_percentage=0.0,
        total_waypoints=2,
    )
    ms_reader = FakeMissionStatusReader(mission, status)

    await executor.execute_mission(mission, ms_reader)

    # Both waypoints should have been reported as reached
    assert len(ms_reader.progress_calls) == 2


@pytest.mark.asyncio
async def test_execute_mission_waits_while_paused():
    from backend.src.services.mission_executor import MissionExecutor
    from backend.src.models.mission import MissionLifecycleStatus, MissionStatus

    loc = FakeLocalization(
        position=Position(latitude=0.1, longitude=0.1, accuracy=0.3),
        heading=0.0,
        dead_reckoning_active=False,
        last_gps_fix=datetime.now(UTC),
    )
    gw = FakeGateway()
    executor = MissionExecutor(localization=loc, gateway=gw, waypoint_tolerance=5000.0)

    mission = _make_mission([{"lat": 0.1, "lon": 0.1, "blade_on": False, "speed": 50}])
    status = MissionStatus(
        mission_id=mission.id,
        status=MissionLifecycleStatus.PAUSED,
        current_waypoint_index=0,
        completion_percentage=0.0,
        total_waypoints=1,
    )
    ms_reader = FakeMissionStatusReader(mission, status)

    task = asyncio.create_task(executor.execute_mission(mission, ms_reader))
    await asyncio.sleep(0.2)
    assert not task.done()

    # Unblock by setting running
    status.status = MissionLifecycleStatus.RUNNING
    await asyncio.wait_for(task, timeout=1.0)
    assert len(ms_reader.progress_calls) == 1


@pytest.mark.asyncio
async def test_execute_mission_marks_failure_on_waypoint_error():
    from backend.src.services.mission_executor import MissionExecutor
    from backend.src.models.mission import MissionLifecycleStatus, MissionStatus

    loc = FakeLocalization(
        position=Position(latitude=0.0, longitude=0.0, accuracy=0.3),
        heading=0.0,
        dead_reckoning_active=False,
        last_gps_fix=datetime.now(UTC),
    )
    gw = FakeGateway()
    executor = MissionExecutor(
        localization=loc,
        gateway=gw,
        waypoint_tolerance=0.001,  # tiny tolerance — never reached
        position_verification_timeout_seconds=0.05,  # fast abort
    )
    # Force position verification to fail so go_to_waypoint raises
    loc._dead_reckoning_active = True

    mission = _make_mission([{"lat": 1.0, "lon": 1.0, "blade_on": False, "speed": 50}])
    status = MissionStatus(
        mission_id=mission.id,
        status=MissionLifecycleStatus.RUNNING,
        current_waypoint_index=0,
        completion_percentage=0.0,
        total_waypoints=1,
    )
    ms_reader = FakeMissionStatusReader(mission, status)

    with pytest.raises(RuntimeError):
        await executor.execute_mission(mission, ms_reader)

    assert executor._failure_detail is not None
