"""LocalizationService — owns current pose, GPS/IMU/encoder fusion, antenna
offset, GPS age/accuracy policy, pose quality, and mission-start heading
bootstrap.

Extracted from the 1910-line NavigationService per §2 of the architecture
plan (docs/major-architecture-and-code-improvement-plan.md).

The legacy NavigationService path remains intact when USE_LEGACY_NAVIGATION=1.
When the env var is absent or 0, NavigationService delegates localization
responsibilities to this service.
"""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import UTC, datetime
from pathlib import Path

from ..fusion.pose2d import PoseQuality
from ..models import Position, SensorData
from ..nav.geoutils import haversine_m
from ..nav.localization_helpers import (
    apply_antenna_offset,
    heading_delta,
    resolve_gps_cog_from_inputs,
    wrap_heading,
)
from ..nav.odometry import OdometryIntegrator
from ..nav.path_planner import PathPlanner

logger = logging.getLogger(__name__)


class LocalizationState:
    """Mutable pose state owned exclusively by LocalizationService.

    Not a Pydantic model: mutable hot-path state that is updated at 5 Hz
    should not pay Pydantic validation overhead on every field write.
    """

    __slots__ = (
        "current_position",
        "heading",
        "gps_cog",
        "velocity",
        "quality",
        "dead_reckoning_active",
        "dead_reckoning_drift",
        "last_gps_fix",
        "timestamp",
    )

    def __init__(self) -> None:
        self.current_position: Position | None = None
        self.heading: float | None = None          # compass degrees, IMU-derived
        self.gps_cog: float | None = None          # GPS course-over-ground degrees
        self.velocity: float | None = None         # m/s
        self.quality: PoseQuality = PoseQuality.STALE
        self.dead_reckoning_active: bool = False
        self.dead_reckoning_drift: float | None = None  # metres estimated drift
        self.last_gps_fix: datetime | None = None
        self.timestamp: datetime = datetime.now(UTC)


# ── Dead reckoning state (private inner class) ──────────────────────────────

class _DeadReckoningState:
    """Minimal dead reckoning tracker — mirrors NavigationService.DeadReckoningSystem."""

    def __init__(self) -> None:
        self.last_gps_position: Position | None = None
        self.last_gps_time: datetime | None = None
        self.estimated_position: Position | None = None
        self.drift_estimate: float = 0.0

    def update_reference(self, gps_position: Position) -> None:
        self.last_gps_position = gps_position
        self.last_gps_time = datetime.now(UTC)
        self.estimated_position = gps_position
        self.drift_estimate = 0.0

    def estimate(self, heading_deg: float, distance_m: float) -> Position | None:
        if self.last_gps_position is None:
            self.last_gps_position = Position(latitude=0.0, longitude=0.0, accuracy=10.0)
            self.last_gps_time = datetime.now(UTC)
            self.estimated_position = self.last_gps_position

        lat_ref = self.last_gps_position.latitude
        meters_per_deg_lon = 111_000.0 * math.cos(math.radians(lat_ref))
        lat_offset = distance_m * math.cos(math.radians(heading_deg)) / 111_000.0
        lon_offset = (
            distance_m * math.sin(math.radians(heading_deg)) / meters_per_deg_lon
            if abs(meters_per_deg_lon) > 1.0
            else 0.0
        )
        self.estimated_position = Position(
            latitude=self.last_gps_position.latitude + lat_offset,
            longitude=self.last_gps_position.longitude + lon_offset,
            accuracy=max(3.0, distance_m * 0.1),
        )
        elapsed_s = (
            (datetime.now(UTC) - self.last_gps_time).total_seconds()
            if self.last_gps_time
            else 0.0
        )
        self.drift_estimate = min(distance_m * 0.05, elapsed_s * 0.1)
        return self.estimated_position


# ── LocalizationService ──────────────────────────────────────────────────────

class LocalizationService:
    """Owns current pose, GPS/IMU fusion, antenna offset, GPS age/accuracy
    policy, pose quality, and mission-start heading bootstrap.

    Constructed with explicit parameters rather than calling ConfigLoader
    internally so tests can inject values without monkey-patching.

    Args:
        imu_yaw_offset: Persistent mechanical yaw offset from hardware.yaml
            (``imu_yaw_offset_degrees``). Applied on every IMU tick.
        antenna_forward_m: GPS antenna offset ahead of center (metres).
        antenna_right_m: GPS antenna offset to the right of center (metres).
        max_fix_age_seconds: Maximum age of a GPS fix for it to be considered
            fresh enough to authorize waypoint advance.
        max_accuracy_m: Maximum GPS accuracy (metres) for position verification.
        alignment_file: Path to ``imu_alignment.json``, or None to disable
            disk I/O (useful in tests).
        position_mismatch_warn_threshold_m: Log a warning when GPS re-acquisition
            diverges more than this many metres from dead-reckoning estimate.
    """

    _DEFAULT_ALIGNMENT_FILE = (
        Path(__file__).resolve().parent.parent.parent.parent / "data" / "imu_alignment.json"
    )

    def __init__(
        self,
        *,
        imu_yaw_offset: float = 0.0,
        antenna_forward_m: float = 0.0,
        antenna_right_m: float = 0.0,
        max_fix_age_seconds: float = 2.0,
        max_accuracy_m: float = 5.0,
        alignment_file: Path | None = _DEFAULT_ALIGNMENT_FILE,
        position_mismatch_warn_threshold_m: float = 5.0,
    ) -> None:
        self._imu_yaw_offset = imu_yaw_offset
        self._antenna_forward_m = antenna_forward_m
        self._antenna_right_m = antenna_right_m
        self._max_fix_age_seconds = max_fix_age_seconds
        self._max_accuracy_m = max_accuracy_m
        self._alignment_file: Path | None = alignment_file
        self._mismatch_warn_threshold_m = position_mismatch_warn_threshold_m

        # Session heading alignment (reset each mission, persisted between runs)
        self._session_heading_alignment: float = 0.0
        self._heading_alignment_sample_count: int = 0
        self._require_gps_heading_alignment: bool = False
        self._gps_cog_history: list[float] = []

        # Bootstrap drive state
        self._bootstrap_start_time: float | None = None

        # GPS track position for deriving COG from position deltas
        self._last_gps_track_position: Position | None = None
        self._last_gps_track_time: datetime | None = None

        # PathPlanner used only for haversine distance/bearing calls
        self._path_planner = PathPlanner()

        # Dead reckoning fallback
        self._dead_reckoning = _DeadReckoningState()
        self._odometry_integrator = OdometryIntegrator()
        self._last_dr_time_s: float = time.monotonic()

        # Public mutable pose state
        self.state = LocalizationState()

        # IMU diagnostic log throttle
        self._last_imu_log: float = 0.0

        if alignment_file is not None:
            self.load_alignment()
        else:
            logger.debug("LocalizationService: alignment_file=None, disk I/O disabled")

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def bootstrap_active(self) -> bool:
        return self._bootstrap_start_time is not None

    @property
    def alignment_ready(self) -> bool:
        return (
            not self._require_gps_heading_alignment
            or self._heading_alignment_sample_count > 0
        )

    @property
    def alignment_sample_count(self) -> int:
        return self._heading_alignment_sample_count

    @property
    def session_heading_alignment(self) -> float:
        return self._session_heading_alignment

    # ── LocalizationProvider proxy properties ────────────────────────────────
    # These delegate to self.state so callers can read pose without accessing
    # the internal LocalizationState object directly.

    @property
    def current_position(self) -> Position | None:
        return self.state.current_position

    @property
    def heading(self) -> float | None:
        return self.state.heading

    @property
    def dead_reckoning_active(self) -> bool:
        return self.state.dead_reckoning_active

    @property
    def last_gps_fix(self) -> datetime | None:
        return self.state.last_gps_fix

    # ── Mission lifecycle ────────────────────────────────────────────────────

    def reset_for_mission(
        self,
        saved_alignment: tuple[float, int, float] | None = None,
    ) -> None:
        """Reset heading alignment for a new mission.

        Args:
            saved_alignment: Optional ``(value_deg, sample_count, age_s)`` tuple
                returned by ``NavigationService._load_saved_alignment_for_mission_start``.
                When provided, the saved value is restored so IMU heading works
                immediately while a fresh GPS COG bootstrap snap runs to validate it.
                When None, falls back to the original 0° reset behaviour.
        """
        self._gps_cog_history.clear()
        self._require_gps_heading_alignment = True
        self._last_gps_track_position = None
        self._last_gps_track_time = None
        self.state.heading = None
        self.state.gps_cog = None
        self._odometry_integrator.reset_ticks()
        self._last_dr_time_s = time.monotonic()
        if saved_alignment is not None:
            saved_value, saved_samples, _age_s = saved_alignment
            self._session_heading_alignment = saved_value
            self._heading_alignment_sample_count = max(1, saved_samples)
            # Disk already holds the valid snap; do not overwrite with a reset record.
        else:
            self._session_heading_alignment = 0.0
            self._heading_alignment_sample_count = 0
            if self._alignment_file is not None:
                self.save_alignment(source="mission_start_reset")

    def begin_bootstrap(self) -> None:
        """Mark that the heading bootstrap drive has started."""
        self._bootstrap_start_time = time.monotonic()

    def end_bootstrap(self) -> None:
        """Mark that the bootstrap drive has ended."""
        self._bootstrap_start_time = None

    # ── GPS age/accuracy policy ──────────────────────────────────────────────

    def gps_fix_is_fresh(self) -> bool:
        """Return True when the latest GPS fix is within max_fix_age_seconds."""
        last_fix = self.state.last_gps_fix
        if last_fix is None:
            return False
        return (datetime.now(UTC) - last_fix).total_seconds() <= self._max_fix_age_seconds

    def position_is_verified(self) -> bool:
        """Return True when position is trustworthy enough to authorize waypoint advance."""
        pos = self.state.current_position
        if pos is None:
            return False
        if self.state.dead_reckoning_active:
            return False
        if not self.gps_fix_is_fresh():
            return False
        accuracy = pos.accuracy
        if accuracy is None:
            return False
        return accuracy <= self._max_accuracy_m

    # ── Main update loop ─────────────────────────────────────────────────────

    async def update(self, sensor_data: SensorData) -> LocalizationState:
        """Consume one sensor tick and update pose state.

        Returns the updated LocalizationState (same object as self.state).
        """
        # 1. Pre-resolve heading from IMU so dead reckoning in step 2 can use it.
        #    Full heading reconciliation with GPS COG happens in step 3.
        imu_valid = (
            sensor_data.imu is not None
            and sensor_data.imu.yaw is not None
            and sensor_data.imu.calibration_status != "uncalibrated"
        )
        if imu_valid:
            raw_yaw_preview = float(sensor_data.imu.yaw)  # type: ignore[union-attr]
            adjusted_yaw_preview = wrap_heading(
                -raw_yaw_preview + self._imu_yaw_offset + self._session_heading_alignment
            )
            if self.alignment_ready:
                # Apply outlier rejection via _set_heading
                self._set_heading(adjusted_yaw_preview)

        # 2. Update position from GPS or dead reckoning
        new_position = await self._update_position(sensor_data)
        if new_position is not None:
            self.state.current_position = new_position

        # 3. Resolve GPS COG from this tick
        speed_threshold = 0.1 if self._bootstrap_start_time is not None else 0.3
        gps_cog, gps_cog_speed, gps_cog_source = self._resolve_gps_cog(
            sensor_data, new_position, speed_threshold=speed_threshold
        )
        if gps_cog is not None:
            self.state.gps_cog = gps_cog
        # Write velocity from GPS COG speed when available; encoder odometry will replace this.
        if gps_cog_speed is not None:
            self.state.velocity = gps_cog_speed

        # 4. Resolve heading from IMU + alignment (full reconciliation with GPS COG)
        if imu_valid:
            raw_yaw = float(sensor_data.imu.yaw)  # type: ignore[union-attr]
            # BNO085 Game Rotation Vector: positive yaw = CCW (aerospace ZYX).
            # Compass convention: CW-positive. Negate then apply offsets.
            adjusted_yaw = wrap_heading(
                -raw_yaw + self._imu_yaw_offset + self._session_heading_alignment
            )

            now_mono = time.monotonic()
            if now_mono - self._last_imu_log > 5.0:
                logger.info(
                    "IMU heading: raw_zyx=%.1f° adjusted_compass=%.1f° "
                    "mounting_offset=%.1f° session_align=%.1f° alignment_ready=%s",
                    raw_yaw,
                    adjusted_yaw,
                    self._imu_yaw_offset,
                    self._session_heading_alignment,
                    self.alignment_ready,
                )
                self._last_imu_log = now_mono

            if self.alignment_ready:
                self._set_heading(adjusted_yaw)
            elif gps_cog is not None:
                self.state.heading = gps_cog
            else:
                # No GPS COG and alignment not ready (mission not started yet).
                # Provide raw adjusted IMU yaw for display — navigation control
                # layers must still wait for alignment_ready before using heading.
                self.state.heading = adjusted_yaw

            # GPS COG comparison and session alignment update during bootstrap
            if gps_cog is not None:
                cog = gps_cog
                delta = heading_delta(cog, adjusted_yaw)
                logger.debug(
                    "HDG: raw_imu=%.1f° adjusted=%.1f° gps_cog=%.1f° "
                    "source=%s speed=%.2f delta=%.1f° session_align=%.1f°",
                    raw_yaw,
                    adjusted_yaw,
                    cog,
                    gps_cog_source,
                    gps_cog_speed if gps_cog_speed is not None else -1.0,
                    delta,
                    self._session_heading_alignment,
                )
                if (
                    self._bootstrap_start_time is not None
                    and abs(delta) > 45.0
                    and self._heading_alignment_sample_count < 10
                ):
                    logger.warning(
                        "HDG mismatch: adjusted IMU=%.1f° vs GPS COG=%.1f° (delta=%.1f°) — "
                        "session alignment converging (samples=%d)",
                        adjusted_yaw, cog, delta, self._heading_alignment_sample_count,
                    )

                if self._bootstrap_start_time is not None:
                    self._gps_cog_history.append(cog)
                    if len(self._gps_cog_history) > 5:
                        self._gps_cog_history.pop(0)

                    going_straight = False
                    if len(self._gps_cog_history) >= 3:
                        sin_c = sum(math.sin(math.radians(c)) for c in self._gps_cog_history)
                        cos_c = sum(math.cos(math.radians(c)) for c in self._gps_cog_history)
                        cog_mean = math.degrees(math.atan2(sin_c, cos_c)) % 360.0
                        max_dev = max(
                            abs(heading_delta(c, cog_mean)) for c in self._gps_cog_history
                        )
                        going_straight = max_dev < 15.0

                    if going_straight and self._heading_alignment_sample_count == 0:
                        clamped_delta = max(-180.0, min(180.0, delta))
                        self._session_heading_alignment = wrap_heading(
                            self._session_heading_alignment + clamped_delta
                        )
                        self._heading_alignment_sample_count = 1
                        self._require_gps_heading_alignment = False
                        adjusted_yaw = wrap_heading(
                            -raw_yaw + self._imu_yaw_offset + self._session_heading_alignment
                        )
                        self._set_heading(adjusted_yaw, allow_large_jump=True)
                        logger.info(
                            "HDG snap-calibrated from GPS COG: delta=%.1f° "
                            "new_align=%.1f° source=%s",
                            clamped_delta,
                            self._session_heading_alignment,
                            gps_cog_source,
                        )
                        if self._alignment_file is not None:
                            self.save_alignment(source="gps_cog_snap")

        elif gps_cog is not None:
            # IMU unavailable — use GPS COG as heading fallback while in motion
            self.state.heading = gps_cog
            # Bootstrap can still snap heading from GPS COG without IMU
            if self._bootstrap_start_time is not None:
                self._gps_cog_history.append(gps_cog)
                if len(self._gps_cog_history) > 5:
                    self._gps_cog_history.pop(0)
                going_straight = False
                if len(self._gps_cog_history) >= 3:
                    sin_c = sum(math.sin(math.radians(c)) for c in self._gps_cog_history)
                    cos_c = sum(math.cos(math.radians(c)) for c in self._gps_cog_history)
                    cog_mean = math.degrees(math.atan2(sin_c, cos_c)) % 360.0
                    max_dev = max(
                        abs(heading_delta(c, cog_mean)) for c in self._gps_cog_history
                    )
                    going_straight = max_dev < 15.0
                if going_straight and self._heading_alignment_sample_count == 0:
                    self._heading_alignment_sample_count = 1
                    self._require_gps_heading_alignment = False
                    logger.info(
                        "HDG snap from GPS COG (IMU unavailable): heading=%.1f° source=%s",
                        gps_cog,
                        gps_cog_source,
                    )
                    if self._alignment_file is not None:
                        self.save_alignment(source="gps_cog_snap_no_imu")

        # 5. Update pose quality
        self._update_quality()

        # Diagnostic: trace heading / gps_cog during bootstrap and just after.
        # Includes GPS position availability so we can distinguish "no GPS fix"
        # from "GPS fix but not moving enough to compute COG".
        if self._bootstrap_start_time is not None or self._heading_alignment_sample_count <= 1:
            _gps = sensor_data.gps if sensor_data else None
            _gps_has_fix = bool(_gps and _gps.latitude and _gps.longitude)
            _gps_acc = getattr(_gps, "accuracy", None) if _gps else None
            logger.info(
                "LOC_TRACE: heading=%s gps_cog=%s gps_fix=%s gps_acc=%s "
                "imu_valid=%s bootstrap=%s samples=%d",
                f"{self.state.heading:.1f}°" if self.state.heading is not None else "None",
                f"{gps_cog:.1f}°" if gps_cog is not None else "None",
                _gps_has_fix,
                f"{_gps_acc:.2f}m" if _gps_acc is not None else "None",
                imu_valid,
                self._bootstrap_start_time is not None,
                self._heading_alignment_sample_count,
            )

        self.state.timestamp = datetime.now(UTC)
        return self.state

    # ── Internal helpers ─────────────────────────────────────────────────────

    async def _update_position(self, sensor_data: SensorData) -> Position | None:
        """Resolve position from GPS or dead reckoning."""
        gps = sensor_data.gps
        if gps and gps.latitude and gps.longitude:
            gps_position = Position(
                latitude=gps.latitude,
                longitude=gps.longitude,
                altitude=gps.altitude,
                accuracy=gps.accuracy,
            )

            # Apply antenna offset when heading is available
            heading = self.state.heading
            if (
                (self._antenna_forward_m != 0.0 or self._antenna_right_m != 0.0)
                and isinstance(heading, (int, float))
            ):
                new_lat, new_lon = apply_antenna_offset(
                    gps_lat=gps_position.latitude,
                    gps_lon=gps_position.longitude,
                    forward_m=self._antenna_forward_m,
                    right_m=self._antenna_right_m,
                    heading_deg=float(heading),
                )
                gps_position = gps_position.model_copy(
                    update={"latitude": new_lat, "longitude": new_lon}
                )
            elif self._antenna_forward_m != 0.0 or self._antenna_right_m != 0.0:
                logger.debug(
                    "GPS antenna offset configured but heading unavailable; using antenna position"
                )

            # Log divergence when recovering from dead reckoning
            if self.state.dead_reckoning_active:
                dr_pos = self._dead_reckoning.estimated_position
                if dr_pos is not None:
                    try:
                        mismatch_m = haversine_m(
                            dr_pos.latitude, dr_pos.longitude,
                            gps_position.latitude, gps_position.longitude,
                        )
                        if mismatch_m > self._mismatch_warn_threshold_m:
                            logger.warning(
                                "Position mismatch on GPS re-acquisition: "
                                "dead-reckoning estimate diverged %.1fm from GPS fix; "
                                "re-synchronising to GPS.",
                                mismatch_m,
                            )
                        else:
                            logger.info(
                                "GPS re-acquired after dead-reckoning; divergence %.1fm; "
                                "re-synchronising.",
                                mismatch_m,
                            )
                    except Exception:
                        logger.debug("Position mismatch check failed.", exc_info=True)

            self._dead_reckoning.update_reference(gps_position)
            self.state.dead_reckoning_active = False
            self.state.last_gps_fix = datetime.now(UTC)
            return gps_position

        # Fallback: dead reckoning using velocity integration (never a fixed constant).
        heading = self.state.heading
        if heading is not None:
            now_s = time.monotonic()
            dt_s = now_s - self._last_dr_time_s
            self._last_dr_time_s = now_s
            commanded_v = float(getattr(self.state, 'target_velocity', None) or 0.0)
            distance_traveled, _ = self._odometry_integrator.step_velocity(
                commanded_v, 0.0, dt_s
            )
            dr_pos = self._dead_reckoning.estimate(float(heading), distance_traveled)
            if dr_pos is not None:
                self.state.dead_reckoning_active = True
                self.state.dead_reckoning_drift = self._dead_reckoning.drift_estimate
                return dr_pos

        return None

    def _resolve_gps_cog(
        self,
        sensor_data: SensorData,
        current_position: Position | None,
        *,
        speed_threshold: float,
    ) -> tuple[float | None, float | None, str | None]:
        """Derive GPS COG from receiver fields or sequential position deltas."""
        gps = sensor_data.gps
        if gps is None or current_position is None:
            return None, None, None

        now = getattr(gps, "timestamp", None)
        if not isinstance(now, datetime) or now.tzinfo is None:
            now = datetime.now(UTC)

        derived_cog: float | None = None
        derived_speed: float | None = None
        previous_position = self._last_gps_track_position
        previous_time = self._last_gps_track_time

        if previous_position is not None and previous_time is not None:
            elapsed_s = max(0.0, (now - previous_time).total_seconds())
            if elapsed_s >= 0.2:
                distance_m = self._path_planner.calculate_distance(
                    previous_position, current_position
                )
                accuracy = max(
                    float(previous_position.accuracy or 0.0),
                    float(current_position.accuracy or 0.0),
                )
                # During bootstrap the mower drives slowly (~0.3 m/s). The GPS
                # driver blocks ~0.75 s per read, so each window captures ~0.22 m of
                # travel. Use 0.15 m (5× RTK noise floor) so COG fires on every read.
                # Outside bootstrap use the accuracy-scaled floor to filter noise.
                if self._bootstrap_start_time is not None:
                    min_distance_m = 0.15
                else:
                    min_distance_m = max(0.25, min(1.0, accuracy * 0.5))
                if distance_m >= min_distance_m:
                    derived_speed = distance_m / elapsed_s
                    if derived_speed >= speed_threshold:
                        derived_cog = self._path_planner.calculate_bearing(
                            previous_position, current_position
                        )
                # Advance the baseline only after a proper elapsed-time window so
                # rapid back-to-back callers (background telemetry + bootstrap loop)
                # don't reset the delta before enough movement has accumulated.
                self._last_gps_track_position = current_position
                self._last_gps_track_time = now
        else:
            # First call — initialize tracking baseline.
            self._last_gps_track_position = current_position
            self._last_gps_track_time = now

        receiver_heading = getattr(gps, "heading", None)
        receiver_speed = getattr(gps, "speed", None)

        return resolve_gps_cog_from_inputs(
            receiver_heading=receiver_heading,
            receiver_speed=float(receiver_speed) if isinstance(receiver_speed, (int, float)) else None,
            derived_cog=derived_cog,
            derived_speed=derived_speed,
            speed_threshold=speed_threshold,
        )

    def _set_heading(self, heading: float, *, allow_large_jump: bool = False) -> None:
        """Set heading with outlier/vibration rejection."""
        heading = wrap_heading(heading)
        previous = self.state.heading
        if previous is not None and not allow_large_jump:
            jump = abs(heading_delta(heading, previous))
            if jump > 60.0:
                logger.debug(
                    "IMU heading outlier rejected: prev=%.1f° new=%.1f° (Δ=%.1f°) — "
                    "keeping previous value",
                    previous, heading, jump,
                )
                return
        self.state.heading = heading

    def _update_quality(self) -> None:
        """Classify and update state.quality from current position data."""
        pos = self.state.current_position
        if pos is None:
            self.state.quality = PoseQuality.STALE
            return
        if self.state.dead_reckoning_active:
            self.state.quality = PoseQuality.DEAD_RECKONING
            return
        if not self.gps_fix_is_fresh():
            self.state.quality = PoseQuality.STALE
            return
        accuracy = pos.accuracy
        if accuracy is None:
            self.state.quality = PoseQuality.GPS_FLOAT
            return
        if accuracy <= 0.05:  # RTK-level
            self.state.quality = PoseQuality.RTK_FIXED
        elif accuracy <= self._max_accuracy_m:
            self.state.quality = PoseQuality.GPS_FLOAT
        else:
            self.state.quality = PoseQuality.GPS_DEGRADED

    # ── Alignment persistence ────────────────────────────────────────────────

    def load_alignment(self) -> None:
        """Load persisted IMU alignment from disk."""
        if self._alignment_file is None:
            return
        try:
            if not self._alignment_file.exists():
                return
            data = json.loads(self._alignment_file.read_text())
            saved = float(data.get("session_heading_alignment", 0.0))
            samples = int(data.get("sample_count", 0))
            source = data.get("source", "unknown")
            self._session_heading_alignment = saved % 360.0
            self._heading_alignment_sample_count = samples
            logger.info(
                "IMU alignment loaded: %.1f° (source=%s, samples=%d)",
                self._session_heading_alignment,
                source,
                samples,
            )
        except Exception as exc:
            logger.warning("Could not load IMU alignment file: %s", exc)
            self._session_heading_alignment = 0.0

    def save_alignment(self, source: str) -> None:
        """Persist current session heading alignment atomically."""
        if self._alignment_file is None:
            return
        try:
            payload = {
                "session_heading_alignment": round(self._session_heading_alignment, 3),
                "sample_count": self._heading_alignment_sample_count,
                "source": source,
                "last_updated": datetime.now(UTC).isoformat(),
            }
            tmp = self._alignment_file.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2))
            tmp.replace(self._alignment_file)
            logger.info(
                "IMU alignment saved: %.1f° (source=%s, samples=%d)",
                self._session_heading_alignment,
                source,
                self._heading_alignment_sample_count,
            )
        except Exception as exc:
            logger.warning("Could not save IMU alignment: %s", exc)


def build_localization_service_from_config() -> LocalizationService:
    """Construct a LocalizationService from the project hardware config.

    Used in main.py lifespan. Isolates ConfigLoader dependency from the
    service class itself so tests can construct the service directly.
    """
    from ..core.config_loader import ConfigLoader

    imu_yaw_offset = 0.0
    antenna_forward_m = 0.0
    antenna_right_m = 0.0
    try:
        hardware, limits = ConfigLoader().get()
        imu_yaw_offset = float(getattr(hardware, "imu_yaw_offset_degrees", 0.0))
        antenna_forward_m = float(getattr(hardware, "gps_antenna_offset_forward_m", 0.0) or 0.0)
        antenna_right_m = float(getattr(hardware, "gps_antenna_offset_right_m", 0.0) or 0.0)
        max_accuracy_m = float(getattr(limits, "gps_max_accuracy_m", 5.0))
        max_fix_age_s = float(getattr(limits, "gps_max_fix_age_seconds", 2.0))
    except Exception as exc:
        logger.warning("LocalizationService: config load failed (%s); using defaults.", exc)
        max_accuracy_m = 5.0
        max_fix_age_s = 2.0

    return LocalizationService(
        imu_yaw_offset=imu_yaw_offset,
        antenna_forward_m=antenna_forward_m,
        antenna_right_m=antenna_right_m,
        max_fix_age_seconds=max_fix_age_s,
        max_accuracy_m=max_accuracy_m,
    )


__all__ = [
    "LocalizationService",
    "LocalizationState",
    "PoseQuality",
    "build_localization_service_from_config",
]
