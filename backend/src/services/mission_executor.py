"""MissionExecutor — owns mission lifecycle and waypoint traversal loop.

Accepts localization and motor gateway as constructor dependencies so it can
be tested with fakes, without constructing NavigationService or touching
hardware.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ..models import NavigationMode, PathStatus, Position, Waypoint
from ..nav.waypoint_geometry import (
    compute_blend_speeds,
    compute_tank_speeds,
    heading_error,
    is_in_tank_mode,
)
from ..nav.path_planner import PathPlanner
from ..nav.geoutils import point_in_polygon

if TYPE_CHECKING:
    from ..models.mission import Mission, MissionWaypoint
    from ..protocols.mission import MissionStatusReader

logger = logging.getLogger(__name__)


class MissionExecutor:
    """Owns mission lifecycle traversal and waypoint-to-motion conversion.

    Args:
        localization: Any object satisfying LocalizationProvider protocol.
            Must expose: current_position, heading, dead_reckoning_active,
            last_gps_fix.
        gateway: Any object satisfying the drive interface.
            Must expose: is_emergency_active() -> bool,
            dispatch_drive_speeds(left, right) -> Awaitable[bool].
        max_speed: Maximum wheel speed (m/s-equivalent, default 0.8).
        cruise_speed: Default forward speed (m/s-equivalent, default 0.5).
        waypoint_tolerance: Arrival radius in metres (default 0.5).
        max_waypoint_fix_age_seconds: GPS staleness threshold (default 2.0).
        max_waypoint_accuracy_m: GPS accuracy floor in metres (default 5.0).
        position_verification_timeout_seconds: Abort timeout (default 30.0).
    """

    def __init__(
        self,
        *,
        localization: Any,
        gateway: Any,
        max_speed: float = 0.8,
        cruise_speed: float = 0.5,
        waypoint_tolerance: float = 0.5,
        max_waypoint_fix_age_seconds: float = 2.0,
        max_waypoint_accuracy_m: float = 5.0,
        position_verification_timeout_seconds: float = 30.0,
    ) -> None:
        self._loc = localization
        self._gw = gateway
        self.max_speed = max_speed
        self.cruise_speed = cruise_speed
        self.waypoint_tolerance = waypoint_tolerance
        self.max_waypoint_fix_age_seconds = max_waypoint_fix_age_seconds
        self.max_waypoint_accuracy_m = max_waypoint_accuracy_m
        self.position_verification_timeout_seconds = position_verification_timeout_seconds
        self._path_planner = PathPlanner()
        # Mutable mission state — reset by execute_mission()
        self.current_waypoint_index: int = 0
        self._active: bool = False
        self._failure_detail: str | None = None

    # ------------------------------------------------------------------
    # Position verification helpers (Task 4)
    # ------------------------------------------------------------------

    def _gps_fix_is_fresh(self) -> bool:
        """Return True when the latest GPS fix is within the staleness window."""
        last_fix = self._loc.last_gps_fix
        if last_fix is None:
            return False
        return (datetime.now(UTC) - last_fix).total_seconds() <= self.max_waypoint_fix_age_seconds

    def _position_is_verified(self) -> bool:
        """Return True when position is trustworthy enough to advance a waypoint."""
        position = self._loc.current_position
        if position is None:
            return False
        if self._loc.dead_reckoning_active:
            return False
        if not self._gps_fix_is_fresh():
            return False
        accuracy = position.accuracy
        if accuracy is None:
            return False
        return float(accuracy) <= self.max_waypoint_accuracy_m

    # ------------------------------------------------------------------
    # Stop delivery helper (Task 5)
    # ------------------------------------------------------------------

    async def _deliver_stop_command(
        self,
        *,
        reason: str,
        retries: int = 3,
        initial_delay: float = 0.1,
    ) -> bool:
        """Best-effort bounded stop delivery used by hold and interruption paths."""
        delay = max(0.0, initial_delay)
        total_attempts = max(1, retries)
        for attempt in range(1, total_attempts + 1):
            try:
                ok = await self._gw.dispatch_drive_speeds(0.0, 0.0)
                if ok:
                    return True
            except Exception as exc:
                logger.warning(
                    "Failed to deliver %s stop command (attempt %d/%d): %s",
                    reason,
                    attempt,
                    total_attempts,
                    exc,
                )
            if attempt < total_attempts and delay > 0:
                await asyncio.sleep(delay)
                delay *= 2
        logger.error(
            "Unable to confirm %s stop command after %d attempts", reason, total_attempts
        )
        return False

    # ------------------------------------------------------------------
    # Waypoint pursuit loop (Task 6)
    # ------------------------------------------------------------------

    async def go_to_waypoint(
        self,
        mission: "Mission",
        waypoint: "MissionWaypoint",
        mission_service: "MissionStatusReader",
    ) -> bool:
        """Navigate to a single waypoint; block until arrival or interruption.

        Returns True when the waypoint is reached, False when interrupted.
        Raises RuntimeError for unrecoverable navigation failures.
        """
        target_pos = Position(latitude=waypoint.lat, longitude=waypoint.lon)
        logger.info(
            "MissionExecutor: navigating to waypoint (%.6f, %.6f)",
            target_pos.latitude,
            target_pos.longitude,
        )

        planner = self._path_planner
        verification_wait_start = time.monotonic()
        heading_wait_start: float | None = None
        _last_nav_log: float = 0.0

        # Stall detection
        _stall_start: float | None = None
        _stall_heading: float | None = None
        _stall_max_start: float | None = None

        # Tank-turn hysteresis state
        _in_tank_mode: bool = False
        _TANK_TURN_TIMEOUT_S: float = 8.0
        _tank_turn_start: float | None = None

        # Position-hold diagnostic
        _pos_hold_start: float | None = None
        _pos_hold_log_last: float = -5.0

        while True:
            status = mission_service.mission_statuses.get(mission.id)
            if not status:
                logger.info("Waypoint navigation interrupted: mission status missing.")
                await self._deliver_stop_command(reason="missing mission status")
                return False

            if status.status == "paused" or (
                hasattr(status.status, "value") and status.status.value == "paused"
            ):
                await self._deliver_stop_command(reason="mission pause hold")
                await asyncio.sleep(0.1)
                continue

            _status_val = status.status.value if hasattr(status.status, "value") else status.status
            if _status_val != "running":
                logger.info("Waypoint navigation interrupted: status=%s", _status_val)
                await self._deliver_stop_command(reason="mission status change")
                return False

            if self._gw.is_emergency_active():
                logger.critical("Waypoint navigation blocked by active emergency stop latch")
                await self._deliver_stop_command(reason="global emergency hold")
                return False

            current_position = self._loc.current_position
            if current_position is None:
                heading_wait_start = None
                if (
                    time.monotonic() - verification_wait_start
                ) >= self.position_verification_timeout_seconds:
                    await self._deliver_stop_command(reason="position acquisition timeout")
                    raise RuntimeError("Position acquisition timeout while navigating waypoint")
                await asyncio.sleep(0.5)
                continue

            if not self._position_is_verified():
                heading_wait_start = None
                await self._deliver_stop_command(reason="position verification hold")
                _now_mono = time.monotonic()
                if _pos_hold_start is None:
                    _pos_hold_start = _now_mono
                if _now_mono - _pos_hold_log_last >= 5.0:
                    _pos_hold_log_last = _now_mono
                    _elapsed = _now_mono - _pos_hold_start
                    logger.info(
                        "Position verification hold active for %.0f s",
                        _elapsed,
                    )
                if (
                    time.monotonic() - verification_wait_start
                ) >= self.position_verification_timeout_seconds:
                    raise RuntimeError("Position verification timeout while navigating waypoint")
                await asyncio.sleep(0.2)
                continue

            verification_wait_start = time.monotonic()
            _pos_hold_start = None
            _pos_hold_log_last = -5.0

            distance_to_target = planner.calculate_distance(current_position, target_pos)

            if distance_to_target <= self.waypoint_tolerance:
                logger.info(
                    "MissionExecutor: waypoint reached (%.6f, %.6f)",
                    waypoint.lat,
                    waypoint.lon,
                )
                stop_confirmed = await self._deliver_stop_command(reason="waypoint arrival")
                if not stop_confirmed:
                    raise RuntimeError("Failed to stop safely at waypoint")
                return True

            # --- Heading and motor calculation ---
            heading_to_target = planner.calculate_bearing(current_position, target_pos)
            current_heading = self._loc.heading
            _in_heading_bootstrap = current_heading is None

            if current_heading is None:
                if heading_wait_start is None:
                    heading_wait_start = time.monotonic()
                    logger.warning(
                        "No heading data available; assuming bearing %.1f° to bootstrap motion.",
                        heading_to_target,
                    )
                if (
                    time.monotonic() - heading_wait_start
                ) >= self.position_verification_timeout_seconds:
                    await self._deliver_stop_command(reason="heading unavailable — mission aborted")
                    raise RuntimeError(
                        "Heading unavailable while navigating waypoint; mission aborted"
                    )
                current_heading = heading_to_target
            else:
                heading_wait_start = None

            err = heading_error(target=heading_to_target, current=current_heading)
            abs_err = abs(err)

            _now = time.monotonic()
            if _now - _last_nav_log > 2.0:
                logger.debug(
                    "NAV_CONTROL: target_bearing=%.1f° heading=%.1f° error=%.1f° tank=%s",
                    heading_to_target,
                    current_heading,
                    err,
                    _in_tank_mode,
                )
                _last_nav_log = _now

            # Stall detection
            _stall_boost = 0.0
            if abs_err > 20:
                if _stall_start is None:
                    _stall_start = time.monotonic()
                    _stall_heading = current_heading
                else:
                    _hdg_delta = abs(heading_error(target=current_heading, current=(_stall_heading or 0)))
                    if _hdg_delta < 5.0:
                        _stall_boost = min(0.6, (time.monotonic() - _stall_start) * 0.15)
                        if _stall_boost >= 0.59:
                            if _stall_max_start is None:
                                _stall_max_start = time.monotonic()
                            elif (time.monotonic() - _stall_max_start) > 8.0:
                                logger.error(
                                    "Mower physically stuck: max turn boost for 8 s, "
                                    "heading unchanged at %.1f° — stopping mission",
                                    current_heading,
                                )
                                await self._deliver_stop_command(reason="physically stuck")
                                raise RuntimeError(
                                    "Mower appears physically stuck: heading did not change "
                                    "despite maximum turn effort for 8 s"
                                )
                        else:
                            _stall_max_start = None
                    else:
                        _stall_start = time.monotonic()
                        _stall_heading = current_heading
                        _stall_max_start = None
            else:
                _stall_start = None
                _stall_heading = None
                _stall_max_start = None

            # Waypoint base speed
            base_speed = self.cruise_speed
            try:
                if hasattr(waypoint, "speed") and isinstance(waypoint.speed, int):
                    base_speed = max(
                        0.1, min(self.max_speed, (waypoint.speed / 100.0) * self.max_speed)
                    )
            except Exception:
                base_speed = self.cruise_speed

            # Tank/blend mode selection with hysteresis
            _in_tank_mode = is_in_tank_mode(abs_error=abs_err, currently_in_tank=_in_tank_mode)

            if _in_tank_mode:
                if _tank_turn_start is None:
                    _tank_turn_start = time.monotonic()
                elif (time.monotonic() - _tank_turn_start) > _TANK_TURN_TIMEOUT_S:
                    logger.error(
                        "Tank-turn watchdog: heading not converging after %.0f s "
                        "(last err=%.1f°, hdg=%.1f°) — aborting waypoint",
                        _TANK_TURN_TIMEOUT_S,
                        err,
                        current_heading,
                    )
                    await self._deliver_stop_command(reason="tank-turn timeout")
                    raise RuntimeError(
                        f"Tank-turn timed out after {_TANK_TURN_TIMEOUT_S:.0f} s "
                        "without heading convergence"
                    )
                left_speed, right_speed = compute_tank_speeds(
                    err, max_speed=self.max_speed, stall_boost=_stall_boost
                )
            else:
                _tank_turn_start = None
                left_speed, right_speed = compute_blend_speeds(
                    err,
                    base_speed=base_speed,
                    stall_boost=_stall_boost,
                    max_speed=self.max_speed,
                    in_heading_bootstrap=_in_heading_bootstrap,
                )

            # Dispatch drive command through gateway
            _motor_attempts = 3
            _motor_last_exc: Exception | None = None
            for _attempt in range(1, _motor_attempts + 1):
                try:
                    ok = await self._gw.dispatch_drive_speeds(left_speed, right_speed)
                    if ok:
                        _motor_last_exc = None
                        break
                    raise RuntimeError("gateway rejected drive command")
                except Exception as exc:
                    _motor_last_exc = exc
                    logger.warning(
                        "Motor command attempt %d/%d failed: %s", _attempt, _motor_attempts, exc
                    )
                    if _attempt < _motor_attempts:
                        await asyncio.sleep(0.15)
            if _motor_last_exc is not None:
                logger.error(
                    "All %d motor command attempts failed: %s", _motor_attempts, _motor_last_exc
                )
                await self._deliver_stop_command(reason="navigation command failure")
                raise RuntimeError(
                    "Failed to deliver navigation motor command"
                ) from _motor_last_exc

            # Control loop at 5 Hz
            await asyncio.sleep(0.2)

        return False
