import asyncio
import time
from types import SimpleNamespace

import pytest

from backend.src.models.safety_limits import SafetyLimits
from backend.src.models.sensor_data import (
    EnvironmentalReading,
    ImuReading,
    PowerReading,
    SensorData,
    TofReading,
)
from backend.src.safety.live_safety_coordinator import LiveSafetyCoordinator


class FakeGateway:
    def __init__(self) -> None:
        self.drive_commands = []
        self.blade_commands = []
        self.emergency_reasons = []

    async def dispatch_drive(self, command):
        self.drive_commands.append(command)
        return SimpleNamespace(status="accepted")

    async def dispatch_blade(self, command):
        self.blade_commands.append(command)
        return SimpleNamespace(status="accepted")

    async def trigger_emergency(self, trigger):
        self.emergency_reasons.append(trigger.reason)
        return SimpleNamespace(status="accepted")


def _runtime(*, blade_active: bool = False, target_velocity: float = 0.0, manager=None):
    return SimpleNamespace(
        safety_limits=SafetyLimits(),
        command_gateway=FakeGateway(),
        blade_state={"active": blade_active},
        navigation=SimpleNamespace(
            navigation_state=SimpleNamespace(target_velocity=target_velocity)
        ),
        sensor_manager=manager,
    )


def _tof(side: str, distance: float = 1000.0) -> TofReading:
    return TofReading(
        sensor_side=side,
        distance=distance,
        sample_id=1,
        monotonic_received_s=time.monotonic(),
    )


@pytest.mark.asyncio
async def test_tilt_reaches_stop_blade_off_and_emergency():
    runtime = _runtime(blade_active=True)
    coordinator = LiveSafetyCoordinator(runtime)

    faults = await coordinator.evaluate_fast_sample(
        SensorData(
            imu=ImuReading(roll=45.0, pitch=0.0),
            tof_left=_tof("left"),
            tof_right=_tof("right"),
        )
    )

    assert "TILT_STOP" in faults
    assert runtime.command_gateway.drive_commands[-1].left == 0.0
    assert runtime.command_gateway.drive_commands[-1].right == 0.0
    assert runtime.command_gateway.blade_commands[-1].active is False
    assert runtime.command_gateway.emergency_reasons == ["TILT_STOP"]


@pytest.mark.asyncio
async def test_obstacle_reaches_stop_and_blade_off():
    runtime = _runtime(target_velocity=0.3)
    coordinator = LiveSafetyCoordinator(runtime)

    faults = await coordinator.evaluate_fast_sample(
        SensorData(
            imu=ImuReading(roll=0.0, pitch=0.0),
            tof_left=_tof("left", distance=100.0),
            tof_right=_tof("right", distance=1000.0),
        )
    )

    assert "OBSTACLE_STOP" in faults
    assert runtime.command_gateway.drive_commands[-1].left == 0.0
    assert runtime.command_gateway.blade_commands[-1].active is False
    assert runtime.command_gateway.emergency_reasons == []


@pytest.mark.asyncio
async def test_v20_idle_clear_path_above_operator_cutoff_does_not_latch_obstacle():
    runtime = _runtime(target_velocity=0.0)
    runtime.safety_limits = SafetyLimits(
        tof_obstacle_distance_meters=0.0254,
        obstacle_min_clearance_m=0.55,
        obstacle_front_offset_m=0.25,
        obstacle_fixed_margin_m=0.2,
    )
    coordinator = LiveSafetyCoordinator(runtime)

    faults = await coordinator.evaluate_fast_sample(
        SensorData(
            imu=ImuReading(roll=0.0, pitch=0.0),
            tof_left=_tof("left", distance=500.0),
            tof_right=_tof("right", distance=600.0),
        )
    )

    assert "OBSTACLE_STOP" not in faults
    assert runtime.command_gateway.drive_commands == []
    assert runtime.command_gateway.blade_commands == []


@pytest.mark.asyncio
async def test_critical_battery_reaches_stop_blade_off_and_emergency():
    runtime = _runtime(blade_active=True)
    coordinator = LiveSafetyCoordinator(runtime)

    faults = await coordinator.evaluate_slow_sample(
        SensorData(power=PowerReading(battery_voltage=11.0))
    )

    assert "CRITICAL_BATTERY_STOP" in faults
    assert runtime.command_gateway.drive_commands[-1].left == 0.0
    assert runtime.command_gateway.blade_commands[-1].active is False
    assert runtime.command_gateway.emergency_reasons == ["CRITICAL_BATTERY_STOP"]


@pytest.mark.asyncio
async def test_high_temperature_reaches_stop_and_blade_off():
    runtime = _runtime(blade_active=True)
    coordinator = LiveSafetyCoordinator(runtime)

    faults = await coordinator.evaluate_slow_sample(
        SensorData(environmental=EnvironmentalReading(temperature=90.0))
    )

    assert "THERMAL_STOP" in faults
    assert runtime.command_gateway.drive_commands[-1].left == 0.0
    assert runtime.command_gateway.blade_commands[-1].active is False


@pytest.mark.asyncio
async def test_stale_tof_while_moving_fails_closed():
    runtime = _runtime(target_velocity=0.3)
    coordinator = LiveSafetyCoordinator(runtime)

    faults = await coordinator.evaluate_fast_sample(
        SensorData(imu=ImuReading(roll=0.0, pitch=0.0))
    )

    assert "TOF_LEFT_STALE" in faults
    assert "TOF_RIGHT_STALE" in faults
    assert runtime.command_gateway.blade_commands[-1].active is False


@pytest.mark.asyncio
async def test_stale_imu_while_blade_active_fails_closed():
    runtime = _runtime(blade_active=True)
    coordinator = LiveSafetyCoordinator(runtime)

    faults = await coordinator.evaluate_fast_sample(
        SensorData(tof_left=_tof("left"), tof_right=_tof("right"))
    )

    assert "IMU_SAFETY_SAMPLE_STALE" in faults
    assert runtime.command_gateway.blade_commands[-1].active is False


@pytest.mark.asyncio
async def test_cached_imu_does_not_refresh_live_safety_age():
    runtime = _runtime(blade_active=True)
    coordinator = LiveSafetyCoordinator(runtime)

    faults = await coordinator.evaluate_fast_sample(
        SensorData(
            imu=ImuReading(
                roll=0.0,
                pitch=0.0,
                cached=True,
                monotonic_received_s=0.0,
            ),
            tof_left=_tof("left"),
            tof_right=_tof("right"),
        )
    )

    assert "IMU_SAFETY_SAMPLE_STALE" in faults
    assert coordinator.status.last_imu_sample_monotonic_s is None


@pytest.mark.asyncio
async def test_slow_power_stall_does_not_delay_fast_tilt_response():
    class SlowManager:
        initialized = True

        async def read_fast_safety_sensors(self):
            return SensorData(
                imu=ImuReading(roll=45.0, pitch=0.0),
                tof_left=_tof("left"),
                tof_right=_tof("right"),
            )

        async def read_slow_safety_sensors(self):
            await asyncio.sleep(5.0)
            return SensorData(power=PowerReading(battery_voltage=12.8))

    runtime = _runtime(blade_active=True, manager=SlowManager())
    coordinator = LiveSafetyCoordinator(runtime)

    await coordinator.start()
    try:
        await asyncio.sleep(0.12)
        assert runtime.command_gateway.blade_commands
        assert runtime.command_gateway.blade_commands[-1].active is False
        assert "TILT_STOP" in coordinator.status.active_faults
    finally:
        await coordinator.stop()


@pytest.mark.asyncio
async def test_clear_fault_does_not_restart_drive_or_blade():
    runtime = _runtime(blade_active=True)
    coordinator = LiveSafetyCoordinator(runtime)
    await coordinator.evaluate_fast_sample(
        SensorData(
            imu=ImuReading(roll=45.0, pitch=0.0),
            tof_left=_tof("left"),
            tof_right=_tof("right"),
        )
    )
    drive_count = len(runtime.command_gateway.drive_commands)
    blade_count = len(runtime.command_gateway.blade_commands)

    coordinator.clear_fault("TILT_STOP")

    assert "TILT_STOP" not in coordinator.status.active_faults
    assert len(runtime.command_gateway.drive_commands) == drive_count
    assert len(runtime.command_gateway.blade_commands) == blade_count
