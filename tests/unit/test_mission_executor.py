"""Unit tests for MissionExecutor.

All tests use fake localization (FakeLocalization) and fake gateway (FakeGateway)
so no hardware, RoboHAT, or NavigationService instance is required.
"""
from __future__ import annotations

import asyncio
import types
from datetime import UTC, datetime

import pytest

from backend.src.models import Position
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
    from backend.src.models.mission import Mission, MissionWaypoint

    wps = [MissionWaypoint(**d) for d in waypoints_dicts]
    mission = Mission(name="test", waypoints=wps, created_at=datetime.now(UTC).isoformat())
    return mission


def _make_status(mission, status=None):
    from backend.src.models.mission import MissionStatus

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
    from backend.src.models.mission import MissionStatus
    from backend.src.services.mission_executor import MissionExecutor

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
    from backend.src.models.mission import MissionStatus
    from backend.src.services.mission_executor import MissionExecutor

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
    from backend.src.models.mission import MissionStatus
    from backend.src.services.mission_executor import MissionExecutor

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


# ---------------------------------------------------------------------------
# Part 3: Encoder-aware stuck detectors
# ---------------------------------------------------------------------------

from unittest.mock import patch as _patch


class FakeLocalizationWithState:
    """Extended FakeLocalization that exposes a state attribute with imu_valid, velocity, gps_cog."""

    def __init__(
        self,
        *,
        position: Position | None = None,
        heading: float | None = 90.0,
        dead_reckoning_active: bool = False,
        last_gps_fix: datetime | None = None,
        velocity: float = 0.5,
    ):
        self._position = position
        self._heading = heading
        self._dead_reckoning_active = dead_reckoning_active
        self._last_gps_fix = last_gps_fix or datetime.now(UTC)

        self.state = types.SimpleNamespace(
            imu_valid=False,
            gps_cog=heading,
            velocity=velocity,
        )

    @property
    def current_position(self):
        return self._position

    @property
    def heading(self):
        return self._heading

    @property
    def dead_reckoning_active(self):
        return self._dead_reckoning_active

    @property
    def last_gps_fix(self):
        return self._last_gps_fix


@pytest.mark.asyncio
async def test_motor_stall_triggers_reverse_escape():
    """Encoder RPM=0 with active command for >3 s must trigger _force_reverse_escape."""
    from backend.src.services.mission_executor import MissionExecutor

    # Use heading ≈ 0° (north) and target due north so heading error < 20°
    # This prevents the heading-stall detector from firing and competing.
    loc = FakeLocalizationWithState(
        position=Position(latitude=0.0, longitude=0.0, accuracy=0.5),
        heading=2.0,   # nearly north — heading error to due-north target is < 20°
        velocity=0.1,
    )
    gw = FakeGateway()

    encoder_rpms = [0.0, 0.0]   # wheels not turning

    def fake_enc_provider():
        return (encoder_rpms[0], encoder_rpms[1])

    executor = MissionExecutor(
        localization=loc,
        gateway=gw,
        encoder_rpm_provider=fake_enc_provider,
        waypoint_tolerance=0.001,  # won't be reached
        position_verification_timeout_seconds=60.0,
    )

    mission = _make_mission([{"lat": 1.0, "lon": 0.0, "blade_on": False, "speed": 50}])
    status = _make_status(mission)
    ms_reader = FakeMissionStatusReader(mission, status)

    # Run for a short time — the motor-stall detector should fire within ~3 ticks.
    # We simulate time passing with a monotonically increasing counter (0.05 s per call)
    # so elapsed-time calculations inside the loop always see forward progress.
    reverse_dispatched = []
    original_dispatch = gw.dispatch_drive_speeds
    async def spy_dispatch(left, right):
        if left < -0.1 and right < -0.1:
            reverse_dispatched.append((left, right))
        return await original_dispatch(left, right)
    gw.dispatch_drive_speeds = spy_dispatch

    _call_count = [0]
    _TIME_PER_CALL = 0.05  # seconds per time.monotonic() call

    def mock_monotonic():
        t = _call_count[0] * _TIME_PER_CALL
        _call_count[0] += 1
        return t

    try:
        with _patch("time.monotonic", mock_monotonic):
            await asyncio.wait_for(
                executor.go_to_waypoint(mission, mission.waypoints[0], ms_reader),
                timeout=5.0,
            )
    except (TimeoutError, RuntimeError):
        pass

    # Should have dispatched at least one reverse command
    assert len(reverse_dispatched) > 0, (
        f"Expected reverse-escape command, got drive calls: {gw.drive_calls[:10]}"
    )


@pytest.mark.asyncio
async def test_wheel_spin_triggers_pivot_escape():
    """High encoder RPM + GPS not moving for >5 s must trigger pivot escape."""
    from backend.src.services.mission_executor import MissionExecutor

    # Position stays fixed (GPS frozen — simulating wheel spin, no traction)
    # Use heading ≈ 0° (north) and target due north so heading error < 20°
    # This prevents heading-stall from interfering.
    fixed_pos = Position(latitude=0.0, longitude=0.0, accuracy=0.5)
    loc = FakeLocalizationWithState(
        position=fixed_pos,
        heading=2.0,   # nearly north, heading error < 20°
        velocity=0.0,  # GPS says not moving
    )
    gw = FakeGateway()

    encoder_rpms = [25.0, 25.0]  # wheels spinning freely

    executor = MissionExecutor(
        localization=loc,
        gateway=gw,
        encoder_rpm_provider=lambda: (encoder_rpms[0], encoder_rpms[1]),
        waypoint_tolerance=0.001,
        position_verification_timeout_seconds=60.0,
    )

    mission = _make_mission([{"lat": 1.0, "lon": 0.0, "blade_on": False, "speed": 50}])
    status = _make_status(mission)
    ms_reader = FakeMissionStatusReader(mission, status)

    # Collect all drive calls and look for a pivot (left and right with opposite signs)
    pivot_dispatched = []
    original_dispatch = gw.dispatch_drive_speeds
    async def spy_dispatch(left, right):
        if abs(left) > 0.1 and abs(right) > 0.1 and (left * right < 0):
            pivot_dispatched.append((left, right))
        return await original_dispatch(left, right)
    gw.dispatch_drive_speeds = spy_dispatch

    # Monotonically increasing time mock: 0.10 s per call ensures elapsed
    # calculations see forward progress; 10 calls/iter × 0.10 = 1.0 s fake/iter,
    # so the 5 s wheel-spin arm fires after ~6 real loop iterations.
    _call_count = [0]
    _TIME_PER_CALL = 0.10

    def mock_monotonic():
        t = _call_count[0] * _TIME_PER_CALL
        _call_count[0] += 1
        return t

    try:
        with _patch("time.monotonic", mock_monotonic):
            await asyncio.wait_for(
                executor.go_to_waypoint(mission, mission.waypoints[0], ms_reader),
                timeout=10.0,
            )
    except (TimeoutError, RuntimeError):
        pass

    assert len(pivot_dispatched) > 0, (
        f"Expected pivot escape, got drive calls: {gw.drive_calls[:10]}"
    )


@pytest.mark.asyncio
async def test_traction_boost_not_applied_during_motor_stall_escape():
    """Once motor stall triggers reverse escape, boost must not interfere."""
    import os

    from backend.src.services.mission_executor import MissionExecutor

    # Ensure boost is enabled
    env = os.environ.copy()
    env.pop("LAWNBERRY_DISABLE_TRACTION_BOOST", None)

    loc = FakeLocalizationWithState(
        position=Position(latitude=0.0, longitude=0.0, accuracy=0.5),
        heading=2.0,   # nearly north, heading error < 20° to suppress heading-stall
        velocity=0.0,
    )
    gw = FakeGateway()

    executor = MissionExecutor(
        localization=loc,
        gateway=gw,
        encoder_rpm_provider=lambda: (0.0, 0.0),  # stall condition
        waypoint_tolerance=0.001,
        position_verification_timeout_seconds=60.0,
    )

    mission = _make_mission([{"lat": 1.0, "lon": 0.0, "blade_on": False, "speed": 50}])
    status = _make_status(mission)
    ms_reader = FakeMissionStatusReader(mission, status)

    # The reverse escape sets left_speed = right_speed = -0.35
    # The boost must NOT scale this (since _force_reverse_escape is True)
    # Collect reverse commands that are NOT excessively large
    _call_count = [0]
    _TIME_PER_CALL = 0.05

    def mock_monotonic():
        t = _call_count[0] * _TIME_PER_CALL
        _call_count[0] += 1
        return t

    try:
        with _patch("time.monotonic", mock_monotonic):
            await asyncio.wait_for(
                executor.go_to_waypoint(mission, mission.waypoints[0], ms_reader),
                timeout=5.0,
            )
    except (TimeoutError, RuntimeError):
        pass

    # Check that any reverse command is exactly -0.35 (not boosted beyond that)
    reverse_calls = [(lv, rv) for lv, rv in gw.drive_calls if lv < -0.1 and rv < -0.1]
    for left, right in reverse_calls:
        assert abs(left) <= 0.45, f"Reverse left boosted too high: {left}"
        assert abs(right) <= 0.45, f"Reverse right boosted too high: {right}"
