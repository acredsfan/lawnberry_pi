"""Live safety coordinator for mission-time critical sensor enforcement.

The coordinator owns the fast safety path: IMU tilt and near-field ToF checks
must not wait for GPS, power/Victron, environmental, camera, history, HTTP, or
WebSocket work. Slow samples are evaluated separately from cached/independent
reads and still fail closed when stale while autonomy is active.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..control.commands import BladeCommand, DriveCommand, EmergencyTrigger
from ..models.sensor_data import SensorData
from ..nav.obstacle_clearance import required_obstacle_clearance_m
from .safety_triggers import get_safety_trigger_manager

logger = logging.getLogger(__name__)


@dataclass
class LiveSafetyStatus:
    running: bool = False
    last_fast_tick_monotonic_s: float | None = None
    last_slow_tick_monotonic_s: float | None = None
    last_imu_sample_monotonic_s: float | None = None
    last_tof_left_sample_monotonic_s: float | None = None
    last_tof_right_sample_monotonic_s: float | None = None
    last_power_sample_monotonic_s: float | None = None
    last_environment_sample_monotonic_s: float | None = None
    active_faults: set[str] = field(default_factory=set)
    last_fault_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        now = time.monotonic()

        def _age(sample_time: float | None) -> float | None:
            return None if sample_time is None else max(0.0, now - sample_time)

        return {
            "running": self.running,
            "fast_loop_age_s": _age(self.last_fast_tick_monotonic_s),
            "slow_loop_age_s": _age(self.last_slow_tick_monotonic_s),
            "imu_sample_age_s": _age(self.last_imu_sample_monotonic_s),
            "tof_left_sample_age_s": _age(self.last_tof_left_sample_monotonic_s),
            "tof_right_sample_age_s": _age(self.last_tof_right_sample_monotonic_s),
            "power_sample_age_s": _age(self.last_power_sample_monotonic_s),
            "environment_sample_age_s": _age(self.last_environment_sample_monotonic_s),
            "active_faults": sorted(self.active_faults),
            "last_fault_reason": self.last_fault_reason,
        }


class LiveSafetyCoordinator:
    """Evaluates live safety samples and invokes final stop/blade-off actions."""

    FAST_PERIOD_S = 0.05
    SLOW_PERIOD_S = 1.0

    def __init__(self, runtime: Any):
        self._runtime = runtime
        self._status = LiveSafetyStatus()
        self._fast_task: asyncio.Task | None = None
        self._slow_task: asyncio.Task | None = None
        self._stopping = False
        self._trigger_manager = get_safety_trigger_manager()

    @property
    def status(self) -> LiveSafetyStatus:
        return self._status

    def status_dict(self) -> dict[str, Any]:
        return self._status.to_dict()

    async def start(self) -> None:
        if self._status.running:
            return
        self._status.running = True
        self._fast_task = asyncio.create_task(self._fast_loop(), name="live_safety_fast")
        self._slow_task = asyncio.create_task(self._slow_loop(), name="live_safety_slow")

    async def stop(self) -> None:
        self._status.running = False
        for task in (self._fast_task, self._slow_task):
            if task and not task.done():
                task.cancel()
        for task in (self._fast_task, self._slow_task):
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._fast_task = None
        self._slow_task = None

    async def _fast_loop(self) -> None:
        while self._status.running:
            try:
                manager = getattr(self._runtime, "sensor_manager", None)
                if manager is not None and getattr(manager, "initialized", False):
                    read_fast = getattr(manager, "read_fast_safety_sensors", None)
                    if callable(read_fast):
                        sample = await read_fast()
                    else:
                        sample = await manager.read_all_sensors()
                    await self.evaluate_fast_sample(sample)
                self._status.last_fast_tick_monotonic_s = time.monotonic()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Live safety fast loop failed: %s", exc)
                self._status.last_fault_reason = "LIVE_SAFETY_LOOP_ERROR"
            await asyncio.sleep(self.FAST_PERIOD_S)

    async def _slow_loop(self) -> None:
        while self._status.running:
            try:
                manager = getattr(self._runtime, "sensor_manager", None)
                if manager is not None and getattr(manager, "initialized", False):
                    read_slow = getattr(manager, "read_slow_safety_sensors", None)
                    if callable(read_slow):
                        sample = await read_slow()
                    else:
                        sample = await manager.read_all_sensors()
                    await self.evaluate_slow_sample(sample)
                self._status.last_slow_tick_monotonic_s = time.monotonic()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Live safety slow loop failed: %s", exc)
                self._status.last_fault_reason = "LIVE_SAFETY_LOOP_ERROR"
            await asyncio.sleep(self.SLOW_PERIOD_S)

    def _actuator_active(self) -> bool:
        try:
            if bool((getattr(self._runtime, "blade_state", {}) or {}).get("active")):
                return True
        except Exception:
            pass
        try:
            nav_state = getattr(getattr(self._runtime, "navigation", None), "navigation_state", None)
            target_velocity = getattr(nav_state, "target_velocity", 0.0)
            return abs(float(target_velocity or 0.0)) > 1e-6
        except Exception:
            return False

    async def evaluate_fast_sample(self, sample: SensorData) -> set[str]:
        limits = self._runtime.safety_limits
        faults: set[str] = set()
        now_mono = time.monotonic()

        imu = sample.imu
        if imu is not None:
            self._status.last_imu_sample_monotonic_s = now_mono
            roll = float(imu.roll or 0.0)
            pitch = float(imu.pitch or 0.0)
            if self._trigger_manager.trigger_tilt(
                roll, pitch, float(limits.tilt_threshold_degrees)
            ):
                faults.add("TILT_STOP")
        elif self._actuator_active():
            faults.add("IMU_SAFETY_SAMPLE_STALE")

        tof_left = sample.tof_left
        tof_right = sample.tof_right
        if tof_left is not None:
            self._status.last_tof_left_sample_monotonic_s = now_mono
        if tof_right is not None:
            self._status.last_tof_right_sample_monotonic_s = now_mono

        actuator_active = self._actuator_active()
        stale_timeout_s = float(getattr(limits, "obstacle_stale_sample_timeout_s", 0.25))
        if actuator_active:
            for code, sample_time in (
                ("TOF_LEFT_STALE", self._status.last_tof_left_sample_monotonic_s),
                ("TOF_RIGHT_STALE", self._status.last_tof_right_sample_monotonic_s),
            ):
                if sample_time is None or now_mono - sample_time > stale_timeout_s:
                    faults.add(code)

        if actuator_active:
            commanded_speed = self._current_commanded_speed_mps()
            obstacle_threshold_m = required_obstacle_clearance_m(commanded_speed, limits)
            for tof in (tof_left, tof_right):
                if tof is None or tof.distance is None:
                    continue
                try:
                    distance_m = float(tof.distance) / 1000.0
                except (TypeError, ValueError):
                    continue
                if distance_m <= 0.0:
                    continue
                if self._trigger_manager.trigger_obstacle(distance_m, obstacle_threshold_m):
                    faults.add("OBSTACLE_STOP")

        if faults:
            await self._fail_closed(faults)
        return faults

    async def evaluate_slow_sample(self, sample: SensorData) -> set[str]:
        limits = self._runtime.safety_limits
        faults: set[str] = set()
        now_mono = time.monotonic()

        power = sample.power
        if power is not None:
            self._status.last_power_sample_monotonic_s = now_mono
            voltage = power.battery_voltage
            if voltage is not None:
                voltage_f = float(voltage)
                if voltage_f <= float(limits.battery_critical_voltage):
                    faults.add("CRITICAL_BATTERY_STOP")
                elif voltage_f <= float(limits.battery_low_voltage):
                    faults.add("LOW_BATTERY_STOP")

        environmental = sample.environmental
        if environmental is not None:
            self._status.last_environment_sample_monotonic_s = now_mono
            temperature = environmental.temperature
            if temperature is not None and float(temperature) >= float(
                limits.high_temperature_celsius
            ):
                faults.add("THERMAL_STOP")

        if faults:
            await self._fail_closed(faults)
        return faults

    def _current_commanded_speed_mps(self) -> float:
        try:
            nav_state = getattr(getattr(self._runtime, "navigation", None), "navigation_state", None)
            velocity = getattr(nav_state, "target_velocity", None)
            if isinstance(velocity, (int, float)) and abs(float(velocity)) > 1e-6:
                return abs(float(velocity))
        except Exception:
            pass
        return float(
            getattr(
                self._runtime.safety_limits,
                "obstacle_conservative_unknown_speed_mps",
                0.4,
            )
            or 0.4
        )

    async def _fail_closed(self, faults: set[str]) -> None:
        new_faults = set(faults) - self._status.active_faults
        self._status.active_faults.update(faults)
        self._status.last_fault_reason = sorted(faults)[0]
        if not new_faults and self._stopping:
            return
        self._stopping = True
        reason = ",".join(sorted(faults))
        try:
            gateway = getattr(self._runtime, "command_gateway", None)
            if gateway is not None:
                await gateway.dispatch_drive(
                    DriveCommand(left=0.0, right=0.0, source="safety", duration_ms=0)
                )
                await gateway.dispatch_blade(
                    BladeCommand(active=False, source="safety", motors_active=False)
                )
                if "CRITICAL_BATTERY_STOP" in faults or "TILT_STOP" in faults:
                    await gateway.trigger_emergency(
                        EmergencyTrigger(reason=reason, source="safety_trigger")
                    )
        finally:
            self._stopping = False

    def clear_fault(self, code: str) -> None:
        """Clear a coordinator fault without restarting motion or blade."""
        self._status.active_faults.discard(code)


__all__ = ["LiveSafetyCoordinator", "LiveSafetyStatus"]
