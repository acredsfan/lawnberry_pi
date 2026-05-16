"""MissionExecutor — owns mission lifecycle and waypoint traversal loop.

Accepts localization and motor gateway as constructor dependencies so it can
be tested with fakes, without constructing NavigationService or touching
hardware.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ..models import Position
from ..nav.path_planner import PathPlanner
from ..nav.waypoint_geometry import (
    HEADING_EMA_ALPHA_GPS,
    HEADING_EMA_ALPHA_IMU,
    HEADING_SLEW_DEG_PER_TICK_GPS,
    HEADING_SLEW_DEG_PER_TICK_IMU,
    compute_blend_speeds,
    compute_tank_speeds,
    cross_track_error,
    heading_error,
    is_in_tank_mode,
    smooth_heading,
    stanley_steer,
)

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
        encoder_rpm_provider: Any = None,
        encoder_active_provider: Any = None,
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
        self._encoder_rpm_provider = encoder_rpm_provider
        self._encoder_active_provider = encoder_active_provider
        import os
        _boost_disabled = os.environ.get("LAWNBERRY_DISABLE_TRACTION_BOOST", "").strip() == "1"
        if _boost_disabled:
            self._tc = None
        else:
            from .traction_control_service import get_traction_control_service
            self._tc = get_traction_control_service()
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
        mission: Mission,
        waypoint: MissionWaypoint,
        mission_service: MissionStatusReader,
        *,
        previous_position: Position | None = None,
    ) -> bool:
        """Navigate to a single waypoint; block until arrival or interruption.

        Returns True when the waypoint is reached, False when interrupted.
        Raises RuntimeError for unrecoverable navigation failures.

        Args:
            previous_position: Position of the previous waypoint (or None for
                the first leg). Used to define the path line A→B for the Stanley
                path-tracker. When None, the mower's position at first valid GPS
                tick is used as the leg-start anchor.
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

        # Heading stall detection + escape ladder
        _stall_start: float | None = None
        _stall_heading: float | None = None
        _stall_escape_stage: str | None = None

        # GPS position stall detection — fires when mower stops physically moving
        # while motors are running, independent of heading error.
        _GPS_STALL_ARM_S: float = 8.0       # seconds without movement → trigger escape
        _GPS_STALL_MIN_M: float = 0.15      # meters needed to reset the stall timer
        _GPS_STALL_PIVOT_S: float = 2.0     # pivot phase duration (s)
        _GPS_STALL_FWD_S: float = 2.5       # forward drive phase duration (s)
        _GPS_STALL_RECHECK_S: float = 10.0  # recheck window after escape (s)
        _gps_stall_ref_lat: float | None = None
        _gps_stall_ref_lon: float | None = None
        _gps_stall_ref_time: float | None = None
        _gps_stall_escape_start: float | None = None
        _gps_stall_escape_phase: str | None = None  # None | "pivot" | "forward" | "recheck"
        _gps_stall_pivot_dir: float = 1.0   # +1 pivot right, -1 pivot left

        # Encoder-aware stuck detectors (Part 3)
        # Trigger A — motor stall: wheels commanded but not turning
        _motor_stall_start: float | None = None
        _MOTOR_STALL_ARM_S: float = 3.0    # seconds of RPM≈0 with command > threshold
        _MOTOR_STALL_ABORT_S: float = 6.0  # abort after this long without recovery
        _MOTOR_STALL_RPM_THRESHOLD: float = 2.0   # RPM below this = stall
        _MOTOR_STALL_CMD_THRESHOLD: float = 0.2   # min command to arm

        # Trigger B — wheel spin: wheels turning but GPS not moving
        _wheel_spin_ref_lat: float | None = None
        _wheel_spin_ref_lon: float | None = None
        _wheel_spin_ref_time: float | None = None
        _WHEEL_SPIN_ARM_S: float = 5.0     # seconds of high-RPM + no-GPS-movement
        _WHEEL_SPIN_RPM_THRESHOLD: float = 10.0  # RPM above this = wheels turning
        _WHEEL_SPIN_MIN_M: float = 0.15    # GPS must move this far to reset

        # Tank-turn hysteresis state
        _in_tank_mode: bool = False
        _TANK_TURN_TIMEOUT_S: float = 25.0
        _tank_turn_start: float | None = None

        # Dead-reckoning heading for tank turns.
        # GPS COG tracks the antenna's arc (~90° offset from mower heading during a pivot),
        # so we integrate (left - right) / wheelbase instead while spinning.
        _TANK_WHEELBASE_M: float = 0.30  # match odometry.py
        _tank_dr_heading: float | None = None
        _tank_dr_last_t: float | None = None
        _prev_left_speed: float = 0.0
        _prev_right_speed: float = 0.0

        # Position-hold diagnostic
        _pos_hold_start: float | None = None
        _pos_hold_log_last: float = -5.0

        # Stanley path-tracking state (per-leg)
        # _path_a: start of the current path segment (previous waypoint, or mower
        #   start position captured at the first valid GPS tick on leg 0).
        # _path_bearing: bearing A→B, cached once and constant for the whole leg.
        # _heading_ema: exponential moving average of IMU heading for noise reduction.
        _path_a_lat: float | None = (
            previous_position.latitude if previous_position is not None else None
        )
        _path_a_lon: float | None = (
            previous_position.longitude if previous_position is not None else None
        )
        _path_bearing: float | None = None
        _heading_ema: float | None = None
        # Detect once per leg whether we are GPS-only (no IMU) for EMA tuning
        _loc_state_init = getattr(self._loc, "state", None)
        _imu_valid_for_leg = bool(getattr(_loc_state_init, "imu_valid", False))
        _ema_alpha = HEADING_EMA_ALPHA_IMU if _imu_valid_for_leg else HEADING_EMA_ALPHA_GPS
        _ema_slew = HEADING_SLEW_DEG_PER_TICK_IMU if _imu_valid_for_leg else HEADING_SLEW_DEG_PER_TICK_GPS

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

            # --- Stanley path anchor: capture leg-start on first valid GPS tick ---
            if _path_a_lat is None:
                _path_a_lat = current_position.latitude
                _path_a_lon = current_position.longitude
            if _path_bearing is None:
                _path_bearing = planner.calculate_bearing(
                    Position(latitude=_path_a_lat, longitude=_path_a_lon),
                    target_pos,
                )

            # --- Heading and motor calculation ---
            # Use the cached path bearing (A→B constant for this leg) to avoid
            # GPS-jitter from recomputing bearing from the current position each tick.
            heading_to_target = _path_bearing
            raw_heading = self._loc.heading
            _in_heading_bootstrap = raw_heading is None

            # Update EMA-filtered heading using smooth_heading() which applies
            # a shortest-arc EMA with a per-tick slew cap.  GPS-only legs use
            # tighter alpha/slew to suppress noisy COG jumps.
            if raw_heading is not None:
                _heading_ema = smooth_heading(
                    _heading_ema, raw_heading, alpha=_ema_alpha, max_step_deg=_ema_slew
                )

            if raw_heading is None:
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
                _tank_dr_heading = None
            elif _in_tank_mode:
                # During a tank turn the GPS antenna traces an arc (~90° offset from the
                # mower's actual facing direction), so GPS COG is unreliable.  Dead-reckon
                # heading from commanded wheel speeds instead.
                _now_dr = time.monotonic()
                if _tank_dr_heading is None:
                    _tank_dr_heading = raw_heading
                    _tank_dr_last_t = _now_dr
                else:
                    _dt_dr = _now_dr - (_tank_dr_last_t or _now_dr)
                    if _dt_dr > 0 and (_prev_left_speed != 0.0 or _prev_right_speed != 0.0):
                        _angular_rad_s = (_prev_left_speed - _prev_right_speed) / _TANK_WHEELBASE_M
                        _tank_dr_heading = (
                            _tank_dr_heading + _angular_rad_s * _dt_dr * (180.0 / math.pi)
                        ) % 360.0
                    _tank_dr_last_t = _now_dr
                current_heading = _tank_dr_heading
                heading_wait_start = None
            else:
                _tank_dr_heading = None
                current_heading = raw_heading
                heading_wait_start = None

            control_heading = _heading_ema if _heading_ema is not None else current_heading
            err = heading_error(target=heading_to_target, current=control_heading)
            abs_err = abs(err)

            _now = time.monotonic()
            if _now - _last_nav_log > 2.0:
                logger.debug(
                    "NAV_CONTROL: path_bearing=%.1f° heading=%.1f° ema=%.1f° err=%.1f° tank=%s",
                    heading_to_target,
                    current_heading,
                    _heading_ema if _heading_ema is not None else current_heading,
                    err,
                    _in_tank_mode,
                )
                _last_nav_log = _now

            # Heading stall detection + staged escape ladder.
            # ALL arm/clear decisions use raw IMU heading (never dead-reckoned).
            # When Stage B forces _in_tank_mode=True, current_heading switches to
            # _tank_dr_heading, which has a very high angular rate model and laps
            # the compass in seconds — causing abs_err to hit 0° spuriously and
            # falsely clearing the stall.  _raw_abs_err is always from IMU.
            _stall_boost = 0.0
            _force_tank_escape = False
            _force_reverse_escape = False
            _force_gps_pivot = False
            _force_gps_forward = False
            _stall_active = _stall_start is not None
            _imu_heading = raw_heading if raw_heading is not None else current_heading
            _raw_abs_err = abs(heading_error(target=heading_to_target, current=_imu_heading))

            # --- GPS position stall detection ---
            # Tracks whether the mower is physically moving while motors run.
            # Operates independently of heading error — catches the case where
            # heading is aligned but the mower is spinning in place or blocked.
            if _prev_left_speed == 0.0 and _prev_right_speed == 0.0:
                # Motors were stopped last iteration; reset the reference so the
                # stall timer starts fresh when motors restart (avoids false stall
                # accumulation across position-hold pauses).
                if _gps_stall_escape_phase is None:
                    _gps_stall_ref_lat = None
                    _gps_stall_ref_lon = None
                    _gps_stall_ref_time = None
                # NEW: reset encoder-aware detectors when stopped
                _motor_stall_start = None
                _wheel_spin_ref_lat = None
                _wheel_spin_ref_lon = None
                _wheel_spin_ref_time = None
            else:
                # Motors were running — track GPS displacement.
                _cur_lat = current_position.latitude
                _cur_lon = current_position.longitude
                if _gps_stall_ref_lat is None:
                    _gps_stall_ref_lat = _cur_lat
                    _gps_stall_ref_lon = _cur_lon
                    _gps_stall_ref_time = time.monotonic()
                else:
                    _gps_moved_m = planner.calculate_distance(
                        Position(latitude=_gps_stall_ref_lat, longitude=_gps_stall_ref_lon),
                        Position(latitude=_cur_lat, longitude=_cur_lon),
                    )
                    if _gps_moved_m >= _GPS_STALL_MIN_M:
                        # Moved enough — reset reference and clear any escape.
                        _gps_stall_ref_lat = _cur_lat
                        _gps_stall_ref_lon = _cur_lon
                        _gps_stall_ref_time = time.monotonic()
                        if _gps_stall_escape_phase == "recheck":
                            logger.info(
                                "GPS stall: movement detected (%.2f m) after escape — "
                                "resuming normal navigation",
                                _gps_moved_m,
                            )
                        _gps_stall_escape_phase = None
                        _gps_stall_escape_start = None
                        # GPS confirms physical movement — reset encoder stall timer
                        # so broken/disconnected encoders don't trigger a false abort.
                        _motor_stall_start = None
                    else:
                        _gps_no_move_s = time.monotonic() - (
                            _gps_stall_ref_time or time.monotonic()
                        )
                        if _gps_stall_escape_phase is None:
                            if _gps_no_move_s >= _GPS_STALL_ARM_S:
                                _gps_stall_escape_start = time.monotonic()
                                _gps_stall_escape_phase = "pivot"
                                # Pivot opposite to heading error: try to get different wheel
                                # contact before retrying the original direction.
                                _gps_stall_pivot_dir = -1.0 if err >= 0 else 1.0
                                logger.warning(
                                    "GPS position stall: no movement (%.2f m) in %.1f s — "
                                    "escape pivot starting (dir=%+.0f, hdg=%.1f°)",
                                    _gps_moved_m,
                                    _gps_no_move_s,
                                    _gps_stall_pivot_dir,
                                    _imu_heading,
                                )
                        elif _gps_stall_escape_phase == "pivot":
                            _esc_t = time.monotonic() - (
                                _gps_stall_escape_start or time.monotonic()
                            )
                            if _esc_t < _GPS_STALL_PIVOT_S:
                                _force_gps_pivot = True
                            else:
                                _gps_stall_escape_phase = "forward"
                                logger.info(
                                    "GPS stall escape: pivot complete (%.1f s), "
                                    "switching to forward drive",
                                    _esc_t,
                                )
                                _force_gps_forward = True
                        elif _gps_stall_escape_phase == "forward":
                            _esc_t = time.monotonic() - (
                                _gps_stall_escape_start or time.monotonic()
                            )
                            if _esc_t < _GPS_STALL_PIVOT_S + _GPS_STALL_FWD_S:
                                _force_gps_forward = True
                            else:
                                _gps_stall_escape_phase = "recheck"
                                _gps_stall_ref_lat = _cur_lat
                                _gps_stall_ref_lon = _cur_lon
                                _gps_stall_ref_time = time.monotonic()
                                logger.info(
                                    "GPS stall escape: forward drive complete — "
                                    "rechecking for %.0f s",
                                    _GPS_STALL_RECHECK_S,
                                )
                        elif _gps_stall_escape_phase == "recheck":
                            _recheck_s = time.monotonic() - (
                                _gps_stall_ref_time or time.monotonic()
                            )
                            if _recheck_s >= _GPS_STALL_RECHECK_S:
                                logger.error(
                                    "GPS position stall: no movement (%.2f m) in %.1f s "
                                    "after escape maneuver — stopping mission",
                                    _gps_moved_m,
                                    _recheck_s,
                                )
                                await self._deliver_stop_command(
                                    reason="GPS position stall after escape"
                                )
                                raise RuntimeError(
                                    "Mower physically stuck: GPS position did not change "
                                    "after escape maneuver"
                                )

            # --- Encoder-aware stuck detectors ---
            # Get encoder RPM for this tick (0.0 if provider unavailable)
            _enc_rpm_a, _enc_rpm_b = (
                self._encoder_rpm_provider()
                if self._encoder_rpm_provider is not None
                else (0.0, 0.0)
            )
            _max_enc_rpm = max(abs(_enc_rpm_a), abs(_enc_rpm_b))
            _max_cmd = max(abs(_prev_left_speed), abs(_prev_right_speed))

            # Trigger A: motor stall — commanded but not turning.
            # Only arm when encoder_active_provider confirms sensors have ever
            # incremented; if sensors are unconnected/broken they always read 0
            # and would produce a permanent false positive.
            _enc_active = (
                self._encoder_active_provider()
                if self._encoder_active_provider is not None
                else True
            )
            if (
                _enc_active
                and _max_cmd > _MOTOR_STALL_CMD_THRESHOLD
                and _max_enc_rpm < _MOTOR_STALL_RPM_THRESHOLD
                and not _force_gps_pivot
                and not _force_gps_forward
                and not _force_reverse_escape
                and not _stall_active
                and _gps_stall_escape_phase is None
            ):
                if _motor_stall_start is None:
                    _motor_stall_start = time.monotonic()
                    logger.debug(
                        "Motor-stall detector armed: cmd=%.2f rpm=%.1f",
                        _max_cmd, _max_enc_rpm,
                    )
                else:
                    _stall_elapsed = time.monotonic() - _motor_stall_start
                    if _stall_elapsed >= _MOTOR_STALL_ABORT_S:
                        logger.error(
                            "Motor stall: RPM≈0 for %.1f s with cmd=%.2f — aborting",
                            _stall_elapsed, _max_cmd,
                        )
                        await self._deliver_stop_command(reason="motor stall abort")
                        raise RuntimeError(
                            "Motor stall: encoder RPM ~0 with active command"
                        )
                    elif _stall_elapsed >= _MOTOR_STALL_ARM_S:
                        if not _force_reverse_escape and not _stall_active:
                            _force_reverse_escape = True
                            logger.warning(
                                "Motor-stall escape: RPM≈0 for %.1f s — "
                                "triggering reverse kick (cmd=%.2f)",
                                _stall_elapsed, _max_cmd,
                            )
            else:
                # Clear only on clear recovery (5× threshold) or zero command,
                # so transient gear-lash blips don't reset accumulated stall time.
                if _max_enc_rpm >= _MOTOR_STALL_RPM_THRESHOLD * 5.0 or _max_cmd <= _MOTOR_STALL_CMD_THRESHOLD:
                    _motor_stall_start = None

            # Trigger B: wheel spin — turning but not moving
            if (
                _max_enc_rpm > _WHEEL_SPIN_RPM_THRESHOLD
                and _max_cmd > _MOTOR_STALL_CMD_THRESHOLD
                and not _force_gps_pivot
                and not _force_gps_forward
                and not _stall_active
                and _gps_stall_escape_phase is None
            ):
                _cur_lat = current_position.latitude
                _cur_lon = current_position.longitude
                if _wheel_spin_ref_lat is None:
                    _wheel_spin_ref_lat = _cur_lat
                    _wheel_spin_ref_lon = _cur_lon
                    _wheel_spin_ref_time = time.monotonic()
                else:
                    _spin_moved_m = planner.calculate_distance(
                        Position(latitude=_wheel_spin_ref_lat, longitude=_wheel_spin_ref_lon),
                        Position(latitude=_cur_lat, longitude=_cur_lon),
                    )
                    if _spin_moved_m >= _WHEEL_SPIN_MIN_M:
                        _wheel_spin_ref_lat = _cur_lat
                        _wheel_spin_ref_lon = _cur_lon
                        _wheel_spin_ref_time = time.monotonic()
                    else:
                        _spin_no_move_s = time.monotonic() - (
                            _wheel_spin_ref_time or time.monotonic()
                        )
                        if _spin_no_move_s >= _WHEEL_SPIN_ARM_S and _gps_stall_escape_phase is None:
                            _gps_stall_escape_start = time.monotonic()
                            _gps_stall_escape_phase = "pivot"
                            _gps_stall_pivot_dir = -1.0 if err >= 0 else 1.0
                            logger.warning(
                                "Wheel-spin stall: RPM=%.1f but only %.3f m in %.1f s — "
                                "triggering pivot escape",
                                _max_enc_rpm, _spin_moved_m, _spin_no_move_s,
                            )
            if _raw_abs_err > 20 and (not _in_tank_mode or _stall_active):
                if _stall_start is None:
                    _stall_start = time.monotonic()
                    _stall_heading = _imu_heading
                    _stall_escape_stage = None
                    logger.debug(
                        "Stall detector armed: err=%.1f° hdg=%.1f°",
                        err, _imu_heading,
                    )
                else:
                    _hdg_delta = abs(
                        heading_error(target=_imu_heading, current=(_stall_heading or 0.0))
                    )
                    if _raw_abs_err < 12.0:
                        # Error converged — mower is aligned, clear completely.
                        logger.debug(
                            "Stall cleared: raw_err=%.1f° converged (stage=%s)",
                            _raw_abs_err, _stall_escape_stage,
                        )
                        _stall_start = None
                        _stall_heading = None
                        _stall_escape_stage = None
                    elif _stall_escape_stage is None and _hdg_delta >= 5.0:
                        # Pre-escape: heading IS moving, just slowly.  Reset the
                        # clock from the new position so boost never fires during
                        # active turning.  Only escalate after 4 s with <5° movement.
                        _stall_start = time.monotonic()
                        _stall_heading = _imu_heading
                        logger.debug(
                            "Stall timer reset: IMU moved %.1f° (raw_err=%.1f°)",
                            _hdg_delta, _raw_abs_err,
                        )
                    elif _stall_escape_stage is not None and _hdg_delta >= 15.0:
                        # Active escape stage: large rotation means mower broke free.
                        logger.debug(
                            "Stall cleared during escape: IMU moved %.1f° (stage=%s)",
                            _hdg_delta, _stall_escape_stage,
                        )
                        _stall_start = None
                        _stall_heading = None
                        _stall_escape_stage = None
                    else:
                        _elapsed = time.monotonic() - _stall_start
                        if _elapsed < 4.0:
                            # Stage A: ramp boost from 0 → 0.6 over 4 s.
                            # With stall_boost now wired into compute_blend_speeds,
                            # this actually amplifies commanded wheel speeds.
                            _stall_boost = min(0.6, _elapsed * 0.15)
                            if _stall_escape_stage != "A":
                                _stall_escape_stage = "A"
                                logger.info(
                                    "Stall escape A: ramping blend boost "
                                    "(err=%.1f°, hdg=%.1f°)",
                                    err, _imu_heading,
                                )
                        elif _elapsed < 7.0:
                            # Stage B: force counter-rotating tank pivot for 3 s.
                            # Mechanically cleaner than blend on grass; the inner-wheel
                            # stiction anchor is eliminated.
                            _stall_boost = 0.6
                            _force_tank_escape = True
                            if _stall_escape_stage != "B":
                                _stall_escape_stage = "B"
                                logger.info(
                                    "Stall escape B: forcing tank pivot "
                                    "(elapsed=%.1fs, err=%.1f°, hdg=%.1f°)",
                                    _elapsed, err, _imu_heading,
                                )
                        elif _elapsed < 7.5:
                            # Stage C: brief reverse kick (~0.5 s) to break ground-contact
                            # lock and change wheel loading before retrying pivot.
                            _force_reverse_escape = True
                            if _stall_escape_stage != "C":
                                _stall_escape_stage = "C"
                                logger.info(
                                    "Stall escape C: reverse kick "
                                    "(elapsed=%.1fs, err=%.1f°, hdg=%.1f°)",
                                    _elapsed, err, _imu_heading,
                                )
                        elif _elapsed < 10.0:
                            # Stage D: second tank pivot attempt after reverse kick.
                            _stall_boost = 0.6
                            _force_tank_escape = True
                            if _stall_escape_stage != "D":
                                _stall_escape_stage = "D"
                                logger.info(
                                    "Stall escape D: tank pivot retry "
                                    "(elapsed=%.1fs, err=%.1f°, hdg=%.1f°)",
                                    _elapsed, err, _imu_heading,
                                )
                        else:
                            logger.error(
                                "Mower physically stuck: all escape stages exhausted after "
                                "%.1f s (err=%.1f°, hdg=%.1f°) — stopping mission",
                                _elapsed, err, current_heading,
                            )
                            await self._deliver_stop_command(reason="physically stuck")
                            raise RuntimeError(
                                "Mower appears physically stuck: heading did not change "
                                "after staged escape attempts (A→B→C→D)"
                            )
            else:
                _stall_start = None
                _stall_heading = None
                _stall_escape_stage = None

            # Waypoint base speed
            base_speed = self.cruise_speed
            try:
                if hasattr(waypoint, "speed") and isinstance(waypoint.speed, int):
                    base_speed = max(
                        0.1, min(self.max_speed, (waypoint.speed / 100.0) * self.max_speed)
                    )
            except Exception:
                base_speed = self.cruise_speed

            # Tank/blend mode selection with hysteresis.
            # _force_tank_escape and _force_reverse_escape override normal mode selection
            # during escape stages B–D; the tank-turn watchdog is suppressed for those
            # iterations so the 25 s timer doesn't accumulate against escape attempts.
            _in_tank_mode = is_in_tank_mode(abs_error=abs_err, currently_in_tank=_in_tank_mode)
            if _force_tank_escape:
                _in_tank_mode = True

            if _force_gps_pivot:
                # GPS stall escape phase 1: tank pivot to break contact and get new traction.
                _pivot_spd = self.max_speed * 0.5
                left_speed = _pivot_spd * _gps_stall_pivot_dir
                right_speed = -_pivot_spd * _gps_stall_pivot_dir
                _tank_turn_start = None
                logger.debug(
                    "GPS stall escape: pivot dir=%+.0f spd=%.2f hdg=%.1f°",
                    _gps_stall_pivot_dir, _pivot_spd, current_heading,
                )
            elif _force_gps_forward:
                # GPS stall escape phase 2: straight forward to move to new ground.
                left_speed = self.cruise_speed
                right_speed = self.cruise_speed
                _tank_turn_start = None
                logger.debug(
                    "GPS stall escape: forward drive spd=%.2f hdg=%.1f°",
                    self.cruise_speed, current_heading,
                )
            elif _force_reverse_escape:
                # Stage C: straight reverse to change ground contact
                left_speed, right_speed = -0.35, -0.35
                _tank_turn_start = None
                logger.debug(
                    "Escape C: dispatching reverse (%.2f, %.2f) hdg=%.1f°",
                    left_speed, right_speed, current_heading,
                )
            elif _in_tank_mode:
                if _force_tank_escape:
                    # Don't tick the watchdog during escape; reset it so normal
                    # tank turns get a clean 25 s window after escape succeeds.
                    _tank_turn_start = None
                else:
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

                # Stanley path-tracker: combine filtered heading error with
                # cross-track-error correction.  Falls back to raw heading error
                # during bootstrap (no IMU) or before path anchor is established.
                _steer = err
                _loc_state = getattr(self._loc, "state", None)
                _loc_vel = (
                    getattr(_loc_state, "velocity", None) if _loc_state is not None else None
                ) or 0.0
                _use_gps_smoothing = not _imu_valid_for_leg
                if (
                    not _in_heading_bootstrap
                    and _path_a_lat is not None
                    and _heading_ema is not None
                    and not (_use_gps_smoothing and _loc_vel < 0.3)
                ):
                    _cte = cross_track_error(
                        (current_position.latitude, current_position.longitude),
                        (_path_a_lat, _path_a_lon),
                        (target_pos.latitude, target_pos.longitude),
                    )
                    _heading_err_path = heading_error(
                        target=heading_to_target, current=_heading_ema
                    )
                    _steer = stanley_steer(_heading_err_path, _cte, _loc_vel)
                    logger.debug(
                        "STANLEY: path_bearing=%.1f° ema_hdg=%.1f° err=%.1f° "
                        "cte=%.3fm steer=%.1f°",
                        heading_to_target,
                        _heading_ema,
                        _heading_err_path,
                        _cte,
                        _steer,
                    )

                left_speed, right_speed = compute_blend_speeds(
                    _steer,
                    base_speed=base_speed,
                    stall_boost=_stall_boost,
                    max_speed=self.max_speed,
                    in_heading_bootstrap=_in_heading_bootstrap,
                )

            # Adaptive traction boost — suppressed during any escape phase or existing stall boost
            if (
                self._tc is not None
                and not _force_reverse_escape
                and not _force_tank_escape
                and not _force_gps_pivot
                and not _force_gps_forward
                and not (_stall_boost > 0)
            ):
                _enc1, _enc2 = (
                    self._encoder_rpm_provider()
                    if self._encoder_rpm_provider is not None
                    else (0.0, 0.0)
                )
                self._tc.update_motor_feedback(_enc1, _enc2)
                self._tc.update_velocity_feedback(
                    base_speed,
                    getattr(getattr(self._loc, "state", None), "velocity", None) or 0.0,
                )
                left_speed, right_speed = self._tc.apply_boost_to_command(
                    left_speed, right_speed, max_speed=self.max_speed
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
                # Before aborting the mission: check whether the RoboHAT watchdog
                # has detected a firmware crash (REPL mode or freeze) and is in the
                # process of auto-recovering.  Wait up to 15 s for motor_controller_ok
                # to become True, then retry once so the mission can continue.
                # Skip the wait if auto-recovery has been throttled — that means the
                # firmware keeps crashing and operator intervention is needed.
                try:
                    from .robohat_service import get_robohat_service as _get_robohat
                    _robohat = _get_robohat()
                    if (
                        _robohat is not None
                        and _robohat.status.serial_connected
                        and not _robohat.recovery_throttled
                        and (_robohat._in_soft_reset or _robohat._in_repl)
                    ):
                        logger.warning(
                            "RoboHAT firmware recovery in progress; suspending mission up to 15 s"
                        )
                        _recovery_deadline = time.monotonic() + 15.0
                        while time.monotonic() < _recovery_deadline:
                            if _robohat.status.motor_controller_ok:
                                break
                            await asyncio.sleep(0.5)
                        if _robohat.status.motor_controller_ok:
                            logger.info("RoboHAT recovered; retrying drive command")
                            try:
                                ok = await self._gw.dispatch_drive_speeds(left_speed, right_speed)
                                if ok:
                                    _motor_last_exc = None
                            except Exception as exc:
                                _motor_last_exc = exc
                except Exception:
                    pass  # recovery-wait is best-effort; original failure path applies

                if _motor_last_exc is not None:
                    await self._deliver_stop_command(reason="navigation command failure")
                    raise RuntimeError(
                        "Failed to deliver navigation motor command"
                    ) from _motor_last_exc

            # Store for next-iteration dead-reckoning
            _prev_left_speed = left_speed
            _prev_right_speed = right_speed

            # Control loop at 5 Hz
            await asyncio.sleep(0.2)

    # ------------------------------------------------------------------
    # Mission orchestration loop (Task 7)
    # ------------------------------------------------------------------

    async def execute_mission(
        self,
        mission: Mission,
        mission_service: MissionStatusReader,
        *,
        on_bootstrap: Any | None = None,
        on_waypoint_advance: Any | None = None,
    ) -> None:
        """Execute all waypoints in mission order.

        Args:
            mission: The mission object with waypoints.
            mission_service: MissionStatusReader for pause/abort polling.
            on_bootstrap: Optional async callable invoked once before the
                waypoint loop (heading bootstrap hook). Signature: async () -> None.
                Defaults to a no-op when None.
            on_waypoint_advance: Optional callable invoked after each waypoint is
                reached. Signature: (completed_index: int) -> None.
                completed_index is the 0-based index of the waypoint just reached.
        """
        logger.info(
            "MissionExecutor: starting mission %s — %s", mission.id, mission.name
        )
        self._active = True
        self._failure_detail = None
        self.current_waypoint_index = 0

        if on_bootstrap is not None:
            await on_bootstrap()

        status = mission_service.mission_statuses.get(mission.id)
        if status is not None:
            requested_index = getattr(status, "current_waypoint_index", 0) or 0
            max_index = max(0, len(mission.waypoints) - 1)
            self.current_waypoint_index = max(0, min(requested_index, max_index))

        # Track the position of the most recently reached waypoint so each leg
        # has a known path anchor (A = previous wp, B = current wp).
        _prev_wp_pos: Position | None = None

        try:
            while self.current_waypoint_index < len(mission.waypoints):
                status = mission_service.mission_statuses.get(mission.id)
                if not status:
                    logger.warning(
                        "Mission %s interrupted: status missing", mission.id
                    )
                    return

                _status_val = (
                    status.status.value if hasattr(status.status, "value") else status.status
                )

                if _status_val == "paused":
                    await self._deliver_stop_command(reason="mission pause hold")
                    await asyncio.sleep(0.1)
                    continue

                if _status_val != "running":
                    logger.warning(
                        "Mission %s interrupted: status=%s", mission.id, _status_val
                    )
                    return

                current_wp = mission.waypoints[self.current_waypoint_index]
                waypoint_reached = await self.go_to_waypoint(
                    mission, current_wp, mission_service,
                    previous_position=_prev_wp_pos,
                )

                if not waypoint_reached:
                    status = mission_service.mission_statuses.get(mission.id)
                    _sv = (
                        status.status.value if status and hasattr(status.status, "value")
                        else (status.status if status else None)
                    )
                    if not status or _sv != "running":
                        return
                else:
                    _prev_wp_pos = Position(latitude=current_wp.lat, longitude=current_wp.lon)
                    await mission_service.update_waypoint_progress(
                        mission.id, self.current_waypoint_index
                    )
                    self.current_waypoint_index += 1
                    if on_waypoint_advance is not None:
                        on_waypoint_advance(self.current_waypoint_index - 1)

                await asyncio.sleep(0.05)

            logger.info("MissionExecutor: mission %s completed.", mission.id)

        except Exception as exc:
            self._failure_detail = str(exc)
            await self._deliver_stop_command(reason="mission failure")
            raise
        finally:
            self._active = False
