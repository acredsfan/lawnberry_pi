"""
NavigationService for LawnBerry Pi v2
Path planning, navigation, and sensor fusion with safety constraints
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..core.config_loader import ConfigLoader
from ..core.observability import observability
from ..fusion.ekf import PoseFilter
from ..fusion.enu_frame import ENUFrame
from ..fusion.pose2d import Pose2D
from ..models import (
    NavigationMode,
    NavigationState,
    Obstacle,
    PathStatus,
    Position,
    SensorData,
    Waypoint,
)
from ..nav.geoutils import body_offset_to_north_east, haversine_m, offset_lat_lon, point_in_polygon
from ..nav.odometry import OdometryIntegrator
from ..nav.path_planner import PathPlanner
from .robohat_service import get_robohat_service

if TYPE_CHECKING:
    from ..models.mission import Mission, MissionWaypoint
    from ..protocols.mission import MissionStatusReader

logger = logging.getLogger(__name__)


## Path planning moved to backend.src.nav.path_planner.PathPlanner


class ObstacleDetector:
    """Obstacle detection and avoidance"""

    def __init__(self, safety_distance: float = 0.2):
        self.safety_distance = safety_distance
        self.detected_obstacles: list[Obstacle] = []

    def update_obstacles_from_sensors(self, sensor_data: SensorData) -> list[Obstacle]:
        """Update obstacle list from sensor data"""
        obstacles = []
        obstacle_id_counter = 0
        threshold_mm = max(0.0, float(self.safety_distance) * 1000.0)

        # ToF sensor obstacles
        if sensor_data.tof_left and sensor_data.tof_left.distance is not None:
            if float(sensor_data.tof_left.distance) <= threshold_mm:
                obstacles.append(
                    Obstacle(
                        id=f"tof_left_{obstacle_id_counter}",
                        position=Position(latitude=0, longitude=0),  # Relative position
                        confidence=0.8,
                        obstacle_type="static",
                        detection_source="tof",
                    )
                )
                obstacle_id_counter += 1

        if sensor_data.tof_right and sensor_data.tof_right.distance is not None:
            if float(sensor_data.tof_right.distance) <= threshold_mm:
                obstacles.append(
                    Obstacle(
                        id=f"tof_right_{obstacle_id_counter}",
                        position=Position(latitude=0, longitude=0),  # Relative position
                        confidence=0.8,
                        obstacle_type="static",
                        detection_source="tof",
                    )
                )
                obstacle_id_counter += 1

        self.detected_obstacles = obstacles
        return obstacles

    def is_path_clear(self, current_pos: Position, target_pos: Position) -> bool:
        """Check if path to target is clear of obstacles"""
        # Simple obstacle checking - would be more sophisticated in real implementation
        for obstacle in self.detected_obstacles:
            if obstacle.confidence > 0.5:
                # Check if obstacle is near the path
                return False
        return True


class DeadReckoningSystem:
    """Dead reckoning navigation fallback"""

    def __init__(self):
        self.last_gps_position: Position | None = None
        self.last_gps_time: datetime | None = None
        self.estimated_position: Position | None = None
        self.drift_estimate: float = 0.0
        self.active = False

    def update_gps_reference(self, gps_position: Position):
        """Update GPS reference for dead reckoning"""
        self.last_gps_position = gps_position
        self.last_gps_time = datetime.now(UTC)
        self.estimated_position = gps_position
        self.active = False
        self.drift_estimate = 0.0

    def estimate_position(self, heading: float, distance_traveled: float) -> Position | None:
        """Estimate current position using dead reckoning"""
        if not self.last_gps_position:
            # Initialize a local frame at origin if no GPS reference exists yet.
            # This enables dead-reckoning operation even before first GPS fix.
            self.last_gps_position = Position(latitude=0.0, longitude=0.0, accuracy=10.0)
            self.last_gps_time = datetime.now(UTC)
            self.estimated_position = self.last_gps_position

        self.active = True

        # Dead reckoning: convert bearing + distance to lat/lon offsets.
        # Latitude: 1 degree ≈ 111,000 m regardless of position.
        # Longitude: 1 degree ≈ 111,000 * cos(lat) m — use the actual reference latitude.
        lat_ref = self.last_gps_position.latitude
        meters_per_deg_lon = 111000.0 * math.cos(math.radians(lat_ref))
        lat_offset = distance_traveled * math.cos(math.radians(heading)) / 111000.0
        lon_offset = (
            distance_traveled * math.sin(math.radians(heading)) / meters_per_deg_lon
            if abs(meters_per_deg_lon) > 1.0
            else 0.0
        )

        self.estimated_position = Position(
            latitude=self.last_gps_position.latitude + lat_offset,
            longitude=self.last_gps_position.longitude + lon_offset,
            accuracy=max(3.0, distance_traveled * 0.1),  # Increasing uncertainty
        )

        # Update drift estimate
        time_since_gps = (datetime.now(UTC) - self.last_gps_time).total_seconds()
        self.drift_estimate = min(distance_traveled * 0.05, time_since_gps * 0.1)

        return self.estimated_position


class _NavStateLocalizationAdapter:
    """Adapts NavigationService.navigation_state to the LocalizationProvider protocol.

    Used by the embedded MissionExecutor so it can read localization state
    without holding a reference to the full NavigationService.
    """

    def __init__(self, nav_service: NavigationService) -> None:
        self._nav = nav_service

    @property
    def current_position(self) -> Position | None:
        return self._nav.navigation_state.current_position

    @property
    def heading(self) -> float | None:
        return self._nav.navigation_state.heading

    @property
    def dead_reckoning_active(self) -> bool:
        return self._nav.navigation_state.dead_reckoning_active

    @property
    def last_gps_fix(self) -> datetime | None:
        return self._nav.navigation_state.last_gps_fix


class _NavGatewayAdapter:
    """Adapts NavigationService drive/emergency interface to MissionExecutor's gateway protocol."""

    def __init__(self, nav_service: NavigationService) -> None:
        self._nav = nav_service

    def is_emergency_active(self) -> bool:
        return self._nav._global_emergency_active()

    async def dispatch_drive_speeds(self, left: float, right: float) -> bool:
        try:
            await self._nav.set_speed(left, right)
            return True
        except Exception as exc:
            logger.debug("_NavGatewayAdapter.dispatch_drive_speeds failed: %s", exc)
            return False


class NavigationService:
    """Main navigation service with sensor fusion and path planning"""

    def __init__(self, weather=None, calibration_repository=None):
        self.navigation_state = NavigationState()
        self.path_planner = PathPlanner()
        self.dead_reckoning = DeadReckoningSystem()
        # Optional weather service with get_current() and get_planning_advice()
        self.weather = weather
        # Optional CalibrationRepository for IMU alignment persistence.
        # When set, _load_alignment_from_disk and _save_alignment_to_disk delegate
        # to the repository instead of reading/writing data/imu_alignment.json directly.
        self._calibration_repo = calibration_repository

        # Navigation parameters
        self.max_speed = 0.8  # m/s
        self.cruise_speed = 0.5  # m/s
        self.waypoint_tolerance = 0.5  # meters
        self.obstacle_avoidance_distance = 0.2  # meters
        self.max_waypoint_fix_age_seconds = 2.0
        self.max_waypoint_accuracy_m = 5.0
        self.position_verification_timeout_seconds = 30.0
        # Warn when GPS position diverges from dead-reckoning estimate by more
        # than this distance (metres) on re-acquisition after a GPS outage.
        self.position_mismatch_warn_threshold_m = 5.0
        self._gps_antenna_offset_forward_m = 0.0
        self._gps_antenna_offset_right_m = 0.0

        try:
            hardware, limits = ConfigLoader().get()
            self.obstacle_avoidance_distance = float(limits.tof_obstacle_distance_meters)
            self._imu_yaw_offset: float = float(getattr(hardware, "imu_yaw_offset_degrees", 0.0))
            self._gps_antenna_offset_forward_m = float(
                getattr(hardware, "gps_antenna_offset_forward_m", 0.0) or 0.0
            )
            self._gps_antenna_offset_right_m = float(
                getattr(hardware, "gps_antenna_offset_right_m", 0.0) or 0.0
            )
            if self._imu_yaw_offset != 0.0:
                logger.info(
                    "IMU yaw offset loaded: %.1f° (applied as: adjusted = (-raw + offset) %% 360)",
                    self._imu_yaw_offset,
                )
            if (
                self._gps_antenna_offset_forward_m != 0.0
                or self._gps_antenna_offset_right_m != 0.0
            ):
                logger.info(
                    "GPS antenna offset loaded: forward=%.2fm right=%.2fm",
                    self._gps_antenna_offset_forward_m,
                    self._gps_antenna_offset_right_m,
                )
        except Exception as exc:
            self._imu_yaw_offset = 0.0
            self._gps_antenna_offset_forward_m = 0.0
            self._gps_antenna_offset_right_m = 0.0
            logger.warning(
                "Failed to load navigation config from hardware/safety limits: %s",
                exc,
            )

        self.obstacle_detector = ObstacleDetector(self.obstacle_avoidance_distance)

        # State tracking
        self.total_distance = 0.0
        self.last_position: Position | None = None
        self._mission_execution_active = False

        # Progressive stiffness detection for stuck motor diagnosis
        self._stiffness_test_active = False
        self._stiffness_test_start_time: float | None = None
        self._stiffness_test_effort = 0.1  # Start with 10% turn effort
        self._stiffness_test_effort_step = 0.05  # Increase by 5% every step
        self._stiffness_test_max_effort = 1.0  # Max 100% turn effort
        self._stiffness_test_stuck_threshold = 0.3  # Heading change < 0.3° in 2 seconds = stuck
        self._stiffness_test_direction: str = "left"
        self._stiffness_test_last_heading: float | None = None
        self._stiffness_test_last_check: float | None = None

        # GPS-based session heading alignment.
        # The BNO085 Game Rotation Vector uses gyro+accel only (no magnetometer);
        # its yaw zero is arbitrary at power-on.  _imu_yaw_offset is the persistent
        # mounting offset from hardware.yaml.  _session_heading_alignment is snapped
        # from GPS COG on the first straight-motion sample each mission, then fine-tuned.
        # It IS persisted to data/imu_alignment.json so subsequent reboots start
        # from the last-known good offset; however, it is reset at each mission start
        # and re-derived from GPS COG via the bootstrap drive.
        self._session_heading_alignment: float = 0.0
        self._heading_alignment_sample_count: int = 0
        self._gps_cog_history: list = []  # recent GPS COG values for straight-motion gate
        # Track when bootstrap begins for lenient GPS snap criteria.
        self._bootstrap_start_time: float | None = None
        self._require_gps_heading_alignment: bool = False
        self._last_gps_track_position: Position | None = None
        self._last_gps_track_time: datetime | None = None
        self._load_alignment_from_disk()
        # Optional telemetry capture. Set via attach_capture(); default is no-op.
        self._capture = None
        # Observability: event store injected per-run by set_event_store().
        self._event_store: Any | None = None
        self._obs_run_id: str = ""
        self._obs_mission_id: str = ""
        # Localization facade: set by attach_localization() during lifespan startup.
        # When not None and USE_LEGACY_NAVIGATION is not set, position/heading
        # state is owned by LocalizationService and mirrored here.
        self._localization: Any | None = None
        # MapRepository: injected at lifespan startup via attach_map_repository().
        # Used by _load_boundaries_from_zones() to read persisted zone definitions.
        self._map_repository: Any | None = None

        # Odometry integrator for dead-reckoning distance/heading estimation.
        self._odometry_integrator = OdometryIntegrator()
        self._last_dr_time_s: float = time.monotonic()

        # EKF pose pipeline (Phase 4: Real Pose Pipeline)
        self._pose_filter = PoseFilter()
        self._enu_frame = ENUFrame()
        self._current_pose: Pose2D | None = None
        self._last_predict_ts: float = time.monotonic()

        from .mission_executor import MissionExecutor

        self._localization_adapter = _NavStateLocalizationAdapter(self)
        self._gateway_adapter = _NavGatewayAdapter(self)
        self._mission_executor = MissionExecutor(
            localization=self._localization_adapter,
            gateway=self._gateway_adapter,
            encoder_rpm_provider=self._get_encoder_rpms,
            encoder_active_provider=self._get_encoder_active,
            max_speed=self.max_speed,
            cruise_speed=self.cruise_speed,
            waypoint_tolerance=self.waypoint_tolerance,
            max_waypoint_fix_age_seconds=self.max_waypoint_fix_age_seconds,
            max_waypoint_accuracy_m=self.max_waypoint_accuracy_m,
            position_verification_timeout_seconds=self.position_verification_timeout_seconds,
        )

    _instance: NavigationService | None = None

    @classmethod
    def get_instance(cls, weather=None, calibration_repository=None) -> NavigationService:
        if cls._instance is None:
            cls._instance = NavigationService(
                weather=weather, calibration_repository=calibration_repository
            )
        return cls._instance

    def attach_capture(self, capture) -> None:
        """Attach a TelemetryCapture for diagnostic replay.

        See backend/src/diagnostics/capture.py. Pass None to detach.
        """
        self._capture = capture

    def set_event_store(self, store: Any, run_id: str, mission_id: str) -> None:
        """Attach an EventStore for this run. Called by MissionService on start."""
        self._event_store = store
        self._obs_run_id = run_id
        self._obs_mission_id = mission_id

    def _emit_event(self, event: Any) -> None:
        if self._event_store is not None:
            try:
                self._event_store.emit(event)
            except Exception:
                pass  # never let event emission crash the nav loop

    def _current_pose_quality(self) -> str:
        """Map current GPS/IMU state to a pose quality string."""
        gps_qual = getattr(self.navigation_state, "gps_fix_quality", None)
        if gps_qual in ("rtk_fixed", "rtk_float"):
            return "rtk_fixed"
        if self._heading_alignment_sample_count > 0:
            return "gps_float"
        return "gps_degraded"

    def attach_calibration_repository(self, calibration_repository) -> None:
        """Late-inject a CalibrationRepository and reload IMU alignment from it.

        Called during lifespan startup after the repository is constructed.
        Re-runs _load_alignment_from_disk so the alignment is sourced from the
        repository rather than the legacy flat-file path.
        """
        self._calibration_repo = calibration_repository
        self._load_alignment_from_disk()
        logger.info("CalibrationRepository attached; IMU alignment reloaded via repository")

    def attach_localization(self, localization_service: Any) -> None:
        """Attach a LocalizationService for facade delegation.

        When attached and USE_LEGACY_NAVIGATION is not set, position/heading
        updates are delegated to the LocalizationService and its results are
        mirrored into NavigationState.
        """
        self._localization = localization_service

    def attach_map_repository(self, map_repository: Any) -> None:
        """Late-inject a MapRepository for geofence/zone persistence.

        Called during lifespan startup after the repository is constructed.
        After attachment, _load_boundaries_from_zones() reads zones from the
        repository rather than the deprecated _zones_store global.
        """
        self._map_repository = map_repository
        logger.info("MapRepository attached to NavigationService")

    def _use_localization(self) -> bool:
        """Return True when delegation to LocalizationService is active."""
        return (
            self._localization is not None
            and os.getenv("USE_LEGACY_NAVIGATION", "0") != "1"
        )

    async def initialize(self) -> bool:
        """Initialize navigation service"""
        logger.info("Initializing navigation service")
        self.navigation_state.navigation_mode = NavigationMode.IDLE
        return True

    async def execute_mission(self, mission: Mission, mission_service: MissionStatusReader):
        """Execute a mission by navigating to each waypoint."""
        logger.info("NavigationService: delegating execute_mission %s to MissionExecutor", mission.id)
        self.navigation_state.navigation_mode = NavigationMode.AUTO
        self.navigation_state.path_status = PathStatus.EXECUTING
        self.navigation_state.planned_path = [
            Waypoint(
                position=Position(latitude=wp.lat, longitude=wp.lon),
                target_speed=(wp.speed / 100.0 * self.max_speed),
            )
            for wp in mission.waypoints
        ]
        self.navigation_state.operation_start_time = datetime.now(UTC)

        # Reset heading alignment state for new mission (localization bootstrap)
        self._session_heading_alignment = 0.0
        self._heading_alignment_sample_count = 0
        self._gps_cog_history.clear()
        self._require_gps_heading_alignment = True
        self._last_gps_track_position = None
        self._last_gps_track_time = None
        self.navigation_state.heading = None
        self.navigation_state.gps_cog = None
        self._save_alignment_to_disk("mission_start_reset")
        # Mirror reset into LocalizationService when it owns pose state.
        # Without this, _heading_alignment_sample_count loaded from the alignment
        # file stays at 1, blocking the GPS-COG snap guard which requires == 0.
        if self._use_localization():
            self._localization.reset_for_mission()

        # Reset ENU frame and pose filter for this mission
        self._enu_frame = ENUFrame()  # will anchor on first GPS fix
        self._pose_filter.reset()
        self._odometry_integrator.reset_ticks()
        self._last_dr_time_s = time.monotonic()
        self._last_predict_ts = time.monotonic()

        # Propagate current_waypoint_index from mission status
        status = mission_service.mission_statuses.get(mission.id)
        requested_index = status.current_waypoint_index if status else 0
        max_index = max(0, len(self.navigation_state.planned_path) - 1)
        self.navigation_state.current_waypoint_index = max(0, min(requested_index or 0, max_index))

        self._mission_execution_active = True
        self._load_boundaries_from_zones()

        async def _bootstrap():
            await self._run_bootstrap_and_check_geofence()

        def _on_waypoint_advance(completed_index: int) -> None:
            self.navigation_state.current_waypoint_index = completed_index + 1

        async def _sensor_pump() -> None:
            """Poll sensors and update navigation state throughout the mission.

            The go_to_waypoint control loop reads navigation_state.heading but
            never calls update_navigation_state itself. Without this pump the
            heading freezes the moment the bootstrap loop ends, causing any
            tank-turn to steer against a static heading forever.
            """
            from ..core.state_manager import get_sensor_manager
            from ..services.telemetry_service import telemetry_service

            while True:
                try:
                    manager = get_sensor_manager()
                    if manager is None:
                        await telemetry_service.initialize_sensors()
                        manager = get_sensor_manager()
                    if manager is not None:
                        sensor_data = await manager.read_all_sensors()
                        if sensor_data:
                            await self.update_navigation_state(sensor_data)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.debug("Mission sensor pump error: %s", exc)
                await asyncio.sleep(0.1)  # 10 Hz

        sensor_pump_task = asyncio.create_task(_sensor_pump())
        try:
            await self._mission_executor.execute_mission(
                mission,
                mission_service,
                on_bootstrap=_bootstrap,
                on_waypoint_advance=_on_waypoint_advance,
            )
            # Sync terminal state back
            if self.navigation_state.navigation_mode == NavigationMode.AUTO:
                self.navigation_state.path_status = PathStatus.COMPLETED
                self.navigation_state.navigation_mode = NavigationMode.IDLE
        except Exception:
            self.navigation_state.target_velocity = 0.0
            self.navigation_state.path_status = PathStatus.FAILED
            if self.navigation_state.navigation_mode != NavigationMode.EMERGENCY_STOP:
                self.navigation_state.navigation_mode = NavigationMode.IDLE
            raise
        finally:
            sensor_pump_task.cancel()
            try:
                await sensor_pump_task
            except asyncio.CancelledError:
                pass
            self._mission_execution_active = False

    async def go_to_waypoint(
        self,
        mission: Mission,
        waypoint: MissionWaypoint,
        mission_service: MissionStatusReader,
    ) -> bool:
        """Navigate to a single waypoint — delegates to MissionExecutor."""
        return await self._mission_executor.go_to_waypoint(mission, waypoint, mission_service)

    async def set_speed(self, left_speed: float, right_speed: float) -> None:
        """Drive command helper integrating with the RoboHAT controller.

        Accepts normalized wheel speeds in m/s-like units scaled to [-1, 1].
        In SIM_MODE, updates state without touching hardware.
        """
        # Clamp inputs for safety
        ls = max(-self.max_speed, min(self.max_speed, float(left_speed)))
        rs = max(-self.max_speed, min(self.max_speed, float(right_speed)))

        if self._global_emergency_active() and (abs(ls) > 1e-6 or abs(rs) > 1e-6):
            raise RuntimeError("Emergency stop active; rejecting non-zero navigation command")

        # Update desired velocity estimate (magnitude)
        try:
            self.navigation_state.target_velocity = float(max(abs(ls), abs(rs)))
        except Exception:
            self.navigation_state.target_velocity = None

        # SIM_MODE: don't touch hardware
        if os.getenv("SIM_MODE", "0") == "1":
            # Roughly reflect commanded speed in reported velocity for UI
            try:
                self.navigation_state.velocity = float((abs(ls) + abs(rs)) / 2.0)
            except Exception:
                pass
            return

        robohat = get_robohat_service()
        if robohat is None or not robohat.running or not robohat.status.serial_connected:
            raise RuntimeError("RoboHAT controller unavailable")

        # Normalize to [-1, 1] before mixing to PWM on RoboHAT layer
        def _normalize(v: float) -> float:
            if self.max_speed <= 0:
                return 0.0
            return max(-1.0, min(1.0, v / self.max_speed))

        norm_ls = _normalize(ls)
        norm_rs = _normalize(rs)

        accepted = await robohat.send_motor_command(norm_rs, norm_ls, ack_timeout=1.0)
        if not accepted:
            raise RuntimeError("Motor command not accepted by controller")

    async def _bootstrap_heading_from_gps_cog(self) -> None:
        """Drive forward so GPS COG snaps the heading alignment.

        IMU Game Rotation Vector yaw is relative to boot orientation (arbitrary zero).
        This method drives at ~75% throttle for up to 15 seconds and requires the
        mower to travel at least 1 m before accepting the GPS COG snap, ensuring the
        alignment comes from real forward motion, not GPS jitter.

        CRITICAL: During the bootstrap drive, we must actively poll sensor data and
        call update_navigation_state() to process GPS COG snaps. The snap cannot fire
        unless telemetry data reaches update_navigation_state().

        Raises RuntimeError if GPS COG cannot snap within the deadline — callers
        must treat this as a mission abort, not a recoverable condition.
        """
        _BOOTSTRAP_DEADLINE_S: float = 15.0
        _GPS_PREFLIGHT_WAIT_S: float = 60.0

        # Pre-flight: ensure GPS has provided at least one valid position before driving.
        # Without a position, _resolve_gps_cog returns None immediately on every tick
        # because current_position is None, so the bootstrap drive produces no COG no
        # matter how long the mower moves.
        if self.navigation_state.current_position is None:
            logger.info(
                "Heading bootstrap: waiting for GPS fix before driving (timeout %.0f s)...",
                _GPS_PREFLIGHT_WAIT_S,
            )
            from ..core.state_manager import get_sensor_manager as _get_sm
            gps_wait_start = time.monotonic()
            gps_fix_deadline = gps_wait_start + _GPS_PREFLIGHT_WAIT_S
            _last_gps_warn_t = gps_wait_start
            while time.monotonic() < gps_fix_deadline:
                await asyncio.sleep(1.0)
                try:
                    _mgr = _get_sm()
                    if _mgr is not None:
                        _sd = await _mgr.read_all_sensors()
                        if _sd:
                            await self.update_navigation_state(_sd)
                except Exception:
                    pass
                if self.navigation_state.current_position is not None:
                    _acc = getattr(self.navigation_state.current_position, "accuracy", None)
                    logger.info(
                        "Heading bootstrap: GPS fix acquired "
                        "(accuracy=%.2f m, waited %.0f s) — starting drive.",
                        _acc or 0.0,
                        time.monotonic() - gps_wait_start,
                    )
                    break
                _now = time.monotonic()
                if _now - _last_gps_warn_t >= 10.0:
                    logger.warning(
                        "Heading bootstrap: still waiting for GPS fix "
                        "(%.0f s elapsed — check sky view and antenna)",
                        _now - gps_wait_start,
                    )
                    _last_gps_warn_t = _now
            else:
                raise RuntimeError(
                    f"Heading bootstrap pre-flight: no GPS fix within {_GPS_PREFLIGHT_WAIT_S:.0f} s. "
                    "Check sky view, GPS antenna, and satellite signal before retrying."
                )
        else:
            _acc = getattr(self.navigation_state.current_position, "accuracy", None)
            logger.info(
                "Heading bootstrap: GPS fix already available (accuracy=%.2f m) — starting drive.",
                _acc or 0.0,
            )

        logger.info("Heading bootstrap: driving forward to acquire GPS COG snap...")
        self._bootstrap_start_time = time.monotonic()
        start_pos = self.navigation_state.current_position
        if self._use_localization():
            self._localization.begin_bootstrap()
        deadline = time.monotonic() + _BOOTSTRAP_DEADLINE_S
        try:
            await self.set_speed(0.6, 0.6)
            _last_drive_t = time.monotonic()
            while time.monotonic() < deadline:
                await asyncio.sleep(0.2)
                if self._global_emergency_active():
                    logger.warning("Heading bootstrap aborted: emergency stop active")
                    return

                # CRITICAL: Poll telemetry and update navigation state during bootstrap.
                # The GPS COG snap only fires when valid GPS data reaches navigation state.
                try:
                    from ..core.state_manager import get_sensor_manager

                    manager = get_sensor_manager()
                    if manager is None:
                        from ..services.telemetry_service import telemetry_service

                        await telemetry_service.initialize_sensors()
                        manager = get_sensor_manager()
                    if manager is None:
                        continue
                    sensor_data = await manager.read_all_sensors()
                    if sensor_data:
                        await self.update_navigation_state(sensor_data)
                except Exception as e:
                    logger.debug(f"Bootstrap telemetry update failed: {e}")

                # Re-issue drive command every 0.5 s to prevent RoboHAT motor watchdog
                # from cutting power before the mower covers the required 1 m.
                if time.monotonic() - _last_drive_t >= 0.5:
                    try:
                        await self.set_speed(0.6, 0.6)
                        _last_drive_t = time.monotonic()
                        logger.info("Bootstrap: drive re-issued at t+%.1f s", time.monotonic() - self._bootstrap_start_time)
                    except Exception as e:
                        logger.warning("Bootstrap drive refresh failed: %s", e)

                if self._use_localization():
                    done = self._localization.alignment_sample_count >= 1
                    align_val = self._localization.session_heading_alignment
                else:
                    done = self._heading_alignment_sample_count >= 1
                    align_val = self._session_heading_alignment

                if done:
                    current_pos = self.navigation_state.current_position
                    if start_pos is not None and current_pos is not None:
                        dist_m = haversine_m(
                            start_pos.latitude, start_pos.longitude,
                            current_pos.latitude, current_pos.longitude,
                        )
                        if dist_m < 1.0:
                            logger.debug(
                                "Bootstrap snap at %.1f m — continuing to ≥1.0 m",
                                dist_m,
                            )
                            done = False

                if done:
                    logger.info(
                        "Heading bootstrap complete: session_align=%.1f°",
                        align_val,
                    )
                    break
            else:
                raise RuntimeError(
                    f"Heading bootstrap failed: GPS COG not acquired within "
                    f"{_BOOTSTRAP_DEADLINE_S:.0f} s. "
                    "Check sky view and GPS lock before retrying."
                )
        finally:
            self._bootstrap_start_time = None
            if self._use_localization():
                self._localization.end_bootstrap()
            await self._deliver_stop_command(reason="heading bootstrap")
            await asyncio.sleep(0.3)

    async def _run_bootstrap_and_check_geofence(self) -> None:
        """Run heading bootstrap then abort if mower is outside geofence boundary.

        Called once at mission start after reset. Raises RuntimeError and latches
        the global emergency state if the position is outside the safety boundary.
        """
        await self._bootstrap_heading_from_gps_cog()

        if self.navigation_state.safety_boundaries and self.navigation_state.current_position:
            outer_boundary = self.navigation_state.safety_boundaries[0]
            polygon = [(p.latitude, p.longitude) for p in outer_boundary]
            cur = self.navigation_state.current_position
            if not point_in_polygon(cur.latitude, cur.longitude, polygon):
                self._latch_global_emergency_state()
                logger.error(
                    "Bootstrap drive exited geofence at (%.6f, %.6f) — mission aborted",
                    cur.latitude,
                    cur.longitude,
                )
                raise RuntimeError("Bootstrap drive exited geofence — mission aborted")

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
                await self.set_speed(0.0, 0.0)
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
        logger.error("Unable to confirm %s stop command after %d attempts", reason, total_attempts)
        return False

    def _gps_fix_is_fresh(self) -> bool:
        """Return True when the latest GPS fix is recent enough for autonomy decisions."""
        if self._use_localization():
            return self._localization.gps_fix_is_fresh()
        last_fix = self.navigation_state.last_gps_fix
        if last_fix is None:
            return False
        return (datetime.now(UTC) - last_fix).total_seconds() <= self.max_waypoint_fix_age_seconds

    def _position_is_verified_for_waypoint(self) -> bool:
        """Return True when position data is trustworthy enough to advance a waypoint."""
        if self._use_localization():
            return self._localization.position_is_verified()
        position = self.navigation_state.current_position
        if position is None:
            return False
        if self.navigation_state.dead_reckoning_active:
            return False
        if not self._gps_fix_is_fresh():
            return False
        accuracy = position.accuracy
        if accuracy is None:
            return False
        return accuracy <= self.max_waypoint_accuracy_m

    def _global_emergency_active(self) -> bool:
        """Return True when the API-level emergency stop is latched OR any active
        hardware safety interlock (tilt, obstacle, geofence, etc.) is present.

        Prefer the gateway if available (Phase C+); fall back to direct state read.
        """
        try:
            from ..main import app

            gw = getattr(getattr(app.state, "runtime", None), "command_gateway", None)
            if gw is not None:
                return gw.is_emergency_active()
        except Exception:
            pass

        # Legacy fallback: read the shared dict directly (same dict the gateway holds)
        try:
            from ..core import globals as _g

            if _g._safety_state.get("emergency_stop_active", False):
                return True
        except Exception:
            pass

        # Check hardware-triggered interlocks via RobotStateManager — these are
        # set by SafetyTriggerManager._activate() but NOT reflected in rest_api state.
        try:
            from ..core.robot_state_manager import get_robot_state_manager
            from ..models.safety_interlock import InterlockState

            active = get_robot_state_manager().get_state().active_interlocks
            if any(il.state == InterlockState.ACTIVE for il in active):
                return True
        except Exception:
            pass

        return False

    def _latch_global_emergency_state(self) -> None:
        """Mirror the control API emergency latch for non-HTTP emergency paths."""
        try:
            from ..control.commands import EmergencyTrigger
            from ..main import app

            gw = getattr(getattr(app.state, "runtime", None), "command_gateway", None)
            if gw is not None:
                asyncio.ensure_future(
                    gw.trigger_emergency(
                        EmergencyTrigger(reason="Navigation safety trigger", source="navigation")
                    )
                )
                return
        except Exception:
            pass

        # Legacy fallback when gateway unavailable (unit tests, early startup)
        try:
            from ..core import globals as _g

            _g._safety_state["emergency_stop_active"] = True
            _g._blade_state["active"] = False
        except Exception:
            logger.debug(
                "Unable to latch emergency state from navigation service", exc_info=True
            )

    @staticmethod
    def _heading_delta(target: float, current: float) -> float:
        """Return signed shortest heading delta from current to target."""
        return (target - current + 180.0) % 360.0 - 180.0

    def _resolve_gps_course_over_ground(
        self,
        sensor_data: SensorData,
        current_position: Position | None,
        *,
        speed_threshold: float,
    ) -> tuple[float | None, float | None, str | None]:
        """Resolve usable GPS COG from receiver course or coordinate deltas.

        The ZED-F9P/NMEA path does not always provide RMC course in the same read
        as GGA position. During mission bootstrap, deriving COG from actual GPS
        coordinate movement gives us an independent heading check before trusting
        relative IMU yaw.
        """
        gps = sensor_data.gps
        if gps is None or current_position is None:
            return None, None, None

        now = getattr(gps, "timestamp", None)
        if not isinstance(now, datetime):
            now = datetime.now(UTC)

        derived_cog: float | None = None
        derived_speed: float | None = None
        previous_position = self._last_gps_track_position
        previous_time = self._last_gps_track_time

        if previous_position is not None and previous_time is not None:
            elapsed_s = max(0.0, (now - previous_time).total_seconds())
            if elapsed_s >= 0.2:
                distance_m = self.path_planner.calculate_distance(
                    previous_position,
                    current_position,
                )
                accuracy = max(
                    float(previous_position.accuracy or 0.0),
                    float(current_position.accuracy or 0.0),
                )
                min_distance_m = max(0.25, min(1.0, accuracy * 0.5))
                if distance_m >= min_distance_m:
                    derived_speed = distance_m / elapsed_s
                    if derived_speed >= speed_threshold:
                        derived_cog = self.path_planner.calculate_bearing(
                            previous_position,
                            current_position,
                        )

        self._last_gps_track_position = current_position
        self._last_gps_track_time = now

        receiver_heading = getattr(gps, "heading", None)
        receiver_speed = getattr(gps, "speed", None)
        if isinstance(receiver_heading, (int, float)):
            speed = float(receiver_speed) if isinstance(receiver_speed, (int, float)) else None
            if speed is not None and speed >= speed_threshold:
                return float(receiver_heading) % 360.0, speed, "receiver"

        if derived_cog is not None:
            return derived_cog, derived_speed, "position_delta"

        return None, None, None

    def _set_navigation_heading(self, heading: float, *, allow_large_jump: bool = False) -> None:
        """Set navigation heading with vibration/outlier rejection."""
        heading = heading % 360.0
        previous_heading = self.navigation_state.heading
        if previous_heading is not None and not allow_large_jump:
            jump = abs(self._heading_delta(heading, previous_heading))
            if jump > 60.0:
                logger.debug(
                    "IMU heading outlier rejected: prev=%.1f° new=%.1f° (Δ=%.1f°) — "
                    "keeping previous value",
                    previous_heading,
                    heading,
                    jump,
                )
                return
        self.navigation_state.heading = heading

    async def update_navigation_state(self, sensor_data: SensorData) -> NavigationState:
        """Update navigation state with sensor fusion.

        Wall-time of the tick is recorded as the ``navigation_tick_duration``
        timer metric (§12 runtime budget baseline).

        When LAWN_LEGACY_NAV=1 the pre-Phase-2 localization path is used.
        Set this flag to run the legacy path during Phase 2 migration or to
        bisect a regression.  See docs/rollback-bisect.md.
        """
        use_legacy = os.getenv("LAWN_LEGACY_NAV", "0") == "1"
        _dispatch = (
            self._update_navigation_state_legacy
            if use_legacy
            else self._update_navigation_state_impl
        )
        start = time.perf_counter()
        try:
            return await _dispatch(sensor_data)
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            observability.metrics.record_timer("navigation_tick_duration", duration_ms)

    async def _update_navigation_state_impl(self, sensor_data: SensorData) -> NavigationState:
        """Original update_navigation_state body — measured by the public wrapper."""

        if self._use_localization():
            # Delegate position, heading, GPS COG, dead reckoning, and quality to
            # LocalizationService. Mirror the results into NavigationState so all
            # callers of NavigationService see consistent data.
            loc_state = await self._localization.update(sensor_data)
            self.navigation_state.current_position = loc_state.current_position
            self.navigation_state.heading = loc_state.heading
            self.navigation_state.gps_cog = loc_state.gps_cog
            self.navigation_state.dead_reckoning_active = loc_state.dead_reckoning_active
            self.navigation_state.dead_reckoning_drift = loc_state.dead_reckoning_drift
            self.navigation_state.last_gps_fix = loc_state.last_gps_fix
            current_position = loc_state.current_position
        else:
            # Legacy path: original implementation unchanged.
            # Update position from GPS or dead reckoning
            current_position = await self._update_position(sensor_data)
            if current_position:
                self.navigation_state.current_position = current_position

            # Update heading. During mission bootstrap, do not trust BNO085 Game Rotation
            # Vector yaw as an absolute compass until GPS COG has snapped the session
            # alignment. Its yaw zero is relative to power-on, not true north.
            speed_threshold = 0.1 if self._bootstrap_start_time else 0.3
            gps_cog, gps_cog_speed, gps_cog_source = self._resolve_gps_course_over_ground(
                sensor_data,
                current_position,
                speed_threshold=speed_threshold,
            )
            if gps_cog is not None:
                self.navigation_state.gps_cog = gps_cog

            imu_valid = (
                sensor_data.imu is not None
                and sensor_data.imu.yaw is not None
                and sensor_data.imu.calibration_status != "uncalibrated"
            )
            imu_alignment_ready = (
                not self._require_gps_heading_alignment
                or self._heading_alignment_sample_count > 0
            )

            if imu_valid:
                raw_yaw = float(sensor_data.imu.yaw)  # type: ignore[union-attr]
                # BNO085 Game Rotation Vector uses ZYX aerospace convention (right-hand, z-up):
                # positive yaw = CCW rotation (counter-clockwise when viewed from above).
                # Navigation uses compass convention: North=0°, East=90°, South=180°, West=270°.
                # Compass convention is CW-positive (clockwise: North→East→South→West).
                # These rotational directions are OPPOSITE, so negate raw_yaw to convert.
                # Then apply yaw_offset for mechanical mounting (e.g., IMU rotated in enclosure).
                adjusted_yaw = (
                    -raw_yaw + self._imu_yaw_offset + self._session_heading_alignment
                ) % 360.0

                # Log raw and adjusted yaw for diagnostic purposes
                _log_imu_now = time.monotonic()
                if _log_imu_now - getattr(self, "_last_imu_log", 0) > 5.0:
                    logger.info(
                        "IMU heading: raw_zyx=%.1f° adjusted_compass=%.1f° "
                        "mounting_offset=%.1f° session_align=%.1f° alignment_ready=%s",
                        raw_yaw,
                        adjusted_yaw,
                        self._imu_yaw_offset,
                        self._session_heading_alignment,
                        imu_alignment_ready,
                    )
                    self._last_imu_log = _log_imu_now

                if imu_alignment_ready:
                    self._set_navigation_heading(adjusted_yaw)
                    self._pose_filter.update_imu_heading(
                        adjusted_yaw,
                        quality=getattr(sensor_data.imu, 'calibration_status', None) or "calibrated"
                    )
                elif gps_cog is not None:
                    self.navigation_state.heading = gps_cog
                else:
                    self.navigation_state.heading = None

                # GPS COG comparison and session heading alignment update.
                # Only mutate IMU alignment during the explicit straight bootstrap drive.
                # During normal waypoint pursuit, GPS COG is the motion vector and can differ
                # from chassis heading during arcs, tank turns, slip, or obstacle maneuvers.
                if gps_cog is not None:
                    cog = gps_cog
                    # delta = how much alignment needs to increase (positive = IMU reads too low)
                    delta = self._heading_delta(cog, adjusted_yaw)
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
                            adjusted_yaw,
                            cog,
                            delta,
                            self._heading_alignment_sample_count,
                        )

                    if self._bootstrap_start_time is not None:
                        # Track GPS COG stability for straight-motion detection.
                        self._gps_cog_history.append(cog)
                        if len(self._gps_cog_history) > 5:
                            self._gps_cog_history.pop(0)

                        going_straight = False
                        if len(self._gps_cog_history) >= 5:
                            sin_c = sum(math.sin(math.radians(c)) for c in self._gps_cog_history)
                            cos_c = sum(math.cos(math.radians(c)) for c in self._gps_cog_history)
                            cog_mean = math.degrees(math.atan2(sin_c, cos_c)) % 360.0
                            max_dev = max(
                                abs(self._heading_delta(c, cog_mean))
                                for c in self._gps_cog_history
                            )
                            going_straight = max_dev < 10.0

                        if going_straight and self._heading_alignment_sample_count == 0:
                            # First stable bootstrap sample: snap immediately to GPS COG.
                            clamped_delta = max(-180.0, min(180.0, delta))
                            self._session_heading_alignment = (
                                self._session_heading_alignment + clamped_delta
                            ) % 360.0
                            self._heading_alignment_sample_count = 1
                            self._require_gps_heading_alignment = False
                            if self._event_store is not None:
                                from ..observability.events import HeadingAligned
                                self._emit_event(HeadingAligned(
                                    run_id=self._obs_run_id,
                                    mission_id=self._obs_mission_id,
                                    aligned_heading_deg=float(self._session_heading_alignment),
                                    sample_count=self._heading_alignment_sample_count,
                                    alignment_source="gps_cog_snap",
                                    delta_applied_deg=float(clamped_delta),
                                ))
                            adjusted_yaw = (
                                -raw_yaw + self._imu_yaw_offset + self._session_heading_alignment
                            ) % 360.0
                            self._set_navigation_heading(adjusted_yaw, allow_large_jump=True)
                            logger.info(
                                "HDG snap-calibrated from GPS COG: delta=%.1f° "
                                "new_align=%.1f° source=%s",
                                clamped_delta,
                                self._session_heading_alignment,
                                gps_cog_source,
                            )
                            self._save_alignment_to_disk("gps_cog_snap")
            elif gps_cog is not None:
                # Use GPS course-over-ground as heading fallback while in motion.
                # GPS COG is already in world frame; IMU yaw_offset does NOT apply here.
                self.navigation_state.heading = gps_cog

        # Update obstacles
        obstacles = self.obstacle_detector.update_obstacles_from_sensors(sensor_data)
        self.navigation_state.obstacle_map = obstacles

        # Check if obstacle avoidance is needed
        self.navigation_state.obstacle_avoidance_active = len(obstacles) > 0

        # Update path execution if in auto mode
        if self.navigation_state.navigation_mode == NavigationMode.AUTO:
            await self._update_path_execution()

        # Emit PoseUpdated if we have a position and an event store.
        if current_position and self._event_store is not None:
            from ..observability.events import PoseUpdated
            gps = sensor_data.gps
            self._emit_event(PoseUpdated(
                run_id=self._obs_run_id,
                mission_id=self._obs_mission_id,
                lat=float(current_position.latitude) if hasattr(current_position, "latitude") else 0.0,
                lon=float(current_position.longitude) if hasattr(current_position, "longitude") else 0.0,
                heading_deg=float(self.navigation_state.heading or 0.0),
                pose_quality=self._current_pose_quality(),
                source="gps" if (gps and gps.accuracy) else "dead_reckoning",
                accuracy_m=float(gps.accuracy) if (gps and gps.accuracy) else None,
            ))

        # Update distance tracking
        if self.last_position and current_position:
            distance_increment = self.path_planner.calculate_distance(
                self.last_position, current_position
            )
            self.navigation_state.distance_traveled += distance_increment
            self.total_distance += distance_increment

        self.last_position = current_position
        self.navigation_state.timestamp = datetime.now(UTC)

        # Optional capture for replay diagnostics. Failures must never break
        # navigation, so swallow any exception and log at debug.
        if self._capture is not None:
            try:
                from backend.src.models.diagnostics_capture import (
                    CAPTURE_SCHEMA_VERSION,
                    CaptureRecord,
                    NavigationStateSnapshot,
                )

                snapshot = NavigationStateSnapshot(
                    current_position=self.navigation_state.current_position,
                    heading=self.navigation_state.heading,
                    gps_cog=self.navigation_state.gps_cog,
                    velocity=self.navigation_state.velocity,
                    target_velocity=self.navigation_state.target_velocity,
                    current_waypoint_index=self.navigation_state.current_waypoint_index,
                    path_status=self.navigation_state.path_status,
                    navigation_mode=self.navigation_state.navigation_mode,
                    dead_reckoning_active=self.navigation_state.dead_reckoning_active,
                    dead_reckoning_drift=self.navigation_state.dead_reckoning_drift,
                    last_gps_fix=self.navigation_state.last_gps_fix,
                    timestamp=self.navigation_state.timestamp,
                    pose_quality=self._current_pose.quality.value if self._current_pose else None,
                )
                self._capture.record(
                    CaptureRecord(
                        capture_version=CAPTURE_SCHEMA_VERSION,
                        record_type="nav_step",
                        sensor_data=sensor_data,
                        navigation_state_after=snapshot,
                    )
                )
            except Exception as exc:  # pragma: no cover - safety net
                logger.warning("Telemetry capture record failed: %s", exc)
        return self.navigation_state

    async def _update_navigation_state_legacy(self, sensor_data: SensorData) -> NavigationState:
        """Legacy NavigationService localization path.

        This method is the stable alias for the pre-Phase-2 implementation.
        It delegates to _update_navigation_state_impl for the duration of
        Phase 2.  Once the refactored localization path (_update_navigation_state_impl)
        has demonstrated replay parity, this method body will be replaced with
        the old implementation snapshot and _update_navigation_state_impl will
        contain the refactored code.

        Controlled by LAWN_LEGACY_NAV=1.  See docs/rollback-bisect.md.
        """
        return await self._update_navigation_state_impl(sensor_data)

    def _apply_gps_antenna_offset(self, gps_position: Position) -> Position:
        forward_m = self._gps_antenna_offset_forward_m
        right_m = self._gps_antenna_offset_right_m
        if forward_m == 0.0 and right_m == 0.0:
            return gps_position

        heading = self.navigation_state.heading
        if not isinstance(heading, (int, float)):
            logger.debug(
                "GPS antenna offset configured but heading is unavailable; using antenna position"
            )
            return gps_position

        antenna_north_m, antenna_east_m = body_offset_to_north_east(
            forward_m=forward_m,
            right_m=right_m,
            heading_degrees=float(heading),
        )
        latitude, longitude = offset_lat_lon(
            gps_position.latitude,
            gps_position.longitude,
            north_m=-antenna_north_m,
            east_m=-antenna_east_m,
        )
        return gps_position.model_copy(update={"latitude": latitude, "longitude": longitude})

    async def _update_position(self, sensor_data: SensorData) -> Position | None:
        """Update position using sensor fusion"""

        # Primary: GPS position
        if sensor_data.gps and sensor_data.gps.latitude and sensor_data.gps.longitude:
            gps_position = Position(
                latitude=sensor_data.gps.latitude,
                longitude=sensor_data.gps.longitude,
                altitude=sensor_data.gps.altitude,
                accuracy=sensor_data.gps.accuracy,
            )
            gps_position = self._apply_gps_antenna_offset(gps_position)

            # When dead reckoning was active, compare the DR estimate to the
            # incoming GPS fix.  A large divergence means the internal position
            # model drifted significantly during the outage (e.g. caused by GPS
            # health being reported as unknown).  Log a structured warning so
            # operators can diagnose the recovery and confirm resync is clean.
            if self.navigation_state.dead_reckoning_active:
                dr_pos = self.dead_reckoning.estimated_position
                if dr_pos is not None:
                    try:
                        mismatch_m = haversine_m(
                            dr_pos.latitude,
                            dr_pos.longitude,
                            gps_position.latitude,
                            gps_position.longitude,
                        )
                        if mismatch_m > self.position_mismatch_warn_threshold_m:
                            logger.warning(
                                "Position mismatch on GPS re-acquisition: "
                                "dead-reckoning estimate diverged %.1fm from GPS fix "
                                "(DR lat=%.6f lon=%.6f, GPS lat=%.6f lon=%.6f); "
                                "re-synchronising to GPS.",
                                mismatch_m,
                                dr_pos.latitude,
                                dr_pos.longitude,
                                gps_position.latitude,
                                gps_position.longitude,
                            )
                        else:
                            logger.info(
                                "GPS re-acquired after dead-reckoning; position divergence "
                                "%.1fm (within %.1fm threshold); re-synchronising.",
                                mismatch_m,
                                self.position_mismatch_warn_threshold_m,
                            )
                    except Exception:
                        logger.debug(
                            "Position mismatch check failed; continuing with GPS fix.",
                            exc_info=True,
                        )

            # Anchor ENU frame on first GPS fix
            if not self._enu_frame.is_anchored:
                self._enu_frame.set_origin(gps_position.latitude, gps_position.longitude)
                self._pose_filter.reset(x_m=0.0, y_m=0.0,
                                        heading_deg=self.navigation_state.heading or 0.0)

            x_m, y_m = self._enu_frame.to_local(gps_position.latitude, gps_position.longitude)
            acc = float(gps_position.accuracy or 5.0)
            self._pose_filter.update_gps(x_m, y_m, accuracy_m=acc)
            self._current_pose = self._pose_filter.get_pose()

            # Update dead reckoning reference
            self.dead_reckoning.update_gps_reference(gps_position)
            self.navigation_state.dead_reckoning_active = False
            self.navigation_state.last_gps_fix = datetime.now(UTC)

            return gps_position

        # Fallback: Dead reckoning
        elif self.navigation_state.heading is not None:
            # Dead-reckoning fallback: use encoder ticks if available, otherwise
            # commanded velocity × elapsed time. Never a fixed constant.
            now_s = time.monotonic()
            dt_s = now_s - self._last_dr_time_s
            self._last_dr_time_s = now_s

            # Try encoder ticks from RoboHAT status
            distance_traveled = 0.0
            delta_heading_deg = 0.0
            encoder_used = False

            try:
                if os.getenv("SIM_MODE", "0") != "1":
                    from .robohat_service import get_robohat_service as _rhs
                    robohat = _rhs()
                    if (
                        robohat is not None
                        and hasattr(robohat.status, "encoder_left_ticks")
                        and hasattr(robohat.status, "encoder_right_ticks")
                    ):
                        dist, dh = self._odometry_integrator.step_ticks(
                            int(robohat.status.encoder_left_ticks),
                            int(robohat.status.encoder_right_ticks),
                        )
                        distance_traveled = dist
                        delta_heading_deg = dh
                        encoder_used = True
            except Exception:
                pass

            if not encoder_used and dt_s > 0:
                # Velocity fallback: use last commanded target_velocity
                commanded_v = float(self.navigation_state.target_velocity or 0.0)
                distance_traveled, delta_heading_deg = self._odometry_integrator.step_velocity(
                    commanded_v, 0.0, dt_s
                )

            now_s_mono = time.monotonic()
            dt_for_predict = now_s_mono - self._last_predict_ts
            self._last_predict_ts = now_s_mono
            self._pose_filter.predict(dt=dt_for_predict, distance_m=distance_traveled,
                                      delta_heading_deg=delta_heading_deg)
            self._current_pose = self._pose_filter.get_pose()

            dead_reckoning_pos = self.dead_reckoning.estimate_position(
                self.navigation_state.heading, distance_traveled
            )

            if dead_reckoning_pos:
                self.navigation_state.dead_reckoning_active = True
                self.navigation_state.dead_reckoning_drift = self.dead_reckoning.drift_estimate
                return dead_reckoning_pos

        return None

    async def _update_path_execution(self):
        """Update path execution for autonomous navigation"""
        if self._mission_execution_active:
            return

        if not self.navigation_state.planned_path:
            return

        current_waypoint = self.navigation_state.get_current_waypoint()
        if not current_waypoint or not self.navigation_state.current_position:
            return

        # Check if we've reached the current waypoint
        distance_to_waypoint = self.path_planner.calculate_distance(
            self.navigation_state.current_position, current_waypoint.position
        )

        if distance_to_waypoint <= self.waypoint_tolerance:
            if not self._position_is_verified_for_waypoint():
                self.navigation_state.target_velocity = 0.0
                return

            # Advance to next waypoint
            if self.navigation_state.advance_waypoint():
                logger.info(f"Advanced to waypoint {self.navigation_state.current_waypoint_index}")
            else:
                # Reached end of path
                self.navigation_state.path_status = PathStatus.COMPLETED
                self.navigation_state.navigation_mode = NavigationMode.IDLE
                logger.info("Path execution completed")

        # Update target velocity based on conditions
        if self.navigation_state.obstacle_avoidance_active:
            self.navigation_state.target_velocity = 0.0  # Stop for obstacles
        else:
            self.navigation_state.target_velocity = (
                current_waypoint.target_speed or self.cruise_speed
            )

    async def plan_path(
        self, boundaries: list[Position], cutting_pattern: str = "parallel"
    ) -> bool:
        """Plan a mowing path for the given boundaries"""
        logger.info(
            f"Planning {cutting_pattern} path for area with {len(boundaries)} boundary points"
        )

        if cutting_pattern == "parallel":
            waypoints = self.path_planner.generate_parallel_lines_path(boundaries)
        else:
            logger.warning(f"Unsupported cutting pattern: {cutting_pattern}")
            return False

        if waypoints:
            self.navigation_state.planned_path = waypoints
            self.navigation_state.current_waypoint_index = 0
            self.navigation_state.path_status = PathStatus.PLANNED
            self.navigation_state.path_confidence = 0.9

            # Calculate estimated area and time
            self._calculate_path_estimates()

            logger.info(f"Path planned with {len(waypoints)} waypoints")
            return True

        return False

    def _calculate_path_estimates(self):
        """Calculate estimated completion time and area coverage"""
        if not self.navigation_state.planned_path:
            return

        total_distance = 0.0
        for i in range(1, len(self.navigation_state.planned_path)):
            total_distance += self.path_planner.calculate_distance(
                self.navigation_state.planned_path[i - 1].position,
                self.navigation_state.planned_path[i].position,
            )

        # Estimate completion time
        estimated_time_seconds = total_distance / self.cruise_speed
        self.navigation_state.estimated_completion_time = datetime.now(UTC) + timedelta(
            seconds=estimated_time_seconds
        )

    async def start_autonomous_navigation(self) -> bool:
        """Start autonomous navigation"""
        if (
            self.navigation_state.path_status != PathStatus.PLANNED
            or not self.navigation_state.planned_path
        ):
            logger.error("Cannot start navigation: no planned path")
            return False

        if not self.navigation_state.current_position:
            logger.error("Cannot start navigation: no current position")
            return False

        # Weather gating if service is available
        try:
            if self.weather is not None:
                pos = self.navigation_state.current_position
                latitude = getattr(pos, "latitude", None)
                longitude = getattr(pos, "longitude", None)

                current = None
                if hasattr(self.weather, "get_current_async"):
                    current = await self.weather.get_current_async(
                        latitude=latitude,
                        longitude=longitude,
                    )
                elif hasattr(self.weather, "get_current"):
                    maybe = self.weather.get_current(
                        latitude=latitude,
                        longitude=longitude,
                    )
                    if asyncio.iscoroutine(maybe):
                        current = await maybe
                    else:
                        current = maybe

                advice = self.weather.get_planning_advice(current)
                if advice and advice.get("advice") == "avoid":
                    logger.warning("Navigation start blocked by weather: %s", advice)
                    return False
        except Exception as e:
            # Fail-open to avoid hard-blocking in case of weather service errors
            logger.warning("Weather check failed, proceeding: %s", e)

        self.navigation_state.navigation_mode = NavigationMode.AUTO
        self.navigation_state.path_status = PathStatus.EXECUTING
        self.navigation_state.operation_start_time = datetime.now(UTC)

        logger.info("Started autonomous navigation")
        return True

    async def pause_navigation(self) -> bool:
        """Pause active navigation without discarding the current path."""
        if self.navigation_state.navigation_mode == NavigationMode.EMERGENCY_STOP:
            logger.error("Cannot pause navigation while emergency stop is active")
            return False

        if self.navigation_state.navigation_mode == NavigationMode.PAUSED:
            return True

        self.navigation_state.target_velocity = 0.0
        stop_confirmed = await self._deliver_stop_command(reason="navigation pause")
        if not stop_confirmed:
            logger.error("Navigation pause requested but controller stop could not be confirmed")
            return False

        self.navigation_state.navigation_mode = NavigationMode.PAUSED
        if self.navigation_state.path_status == PathStatus.PLANNING:
            self.navigation_state.path_status = PathStatus.INTERRUPTED

        logger.info("Navigation paused")
        return True

    async def resume_navigation(self) -> bool:
        """Resume navigation after an explicit pause."""
        if self.navigation_state.navigation_mode == NavigationMode.EMERGENCY_STOP:
            logger.error("Cannot resume navigation while emergency stop is active")
            return False

        if self.navigation_state.navigation_mode != NavigationMode.PAUSED:
            logger.error("Cannot resume navigation: system is not paused")
            return False

        if not self.navigation_state.planned_path:
            logger.error("Cannot resume navigation: no planned path")
            return False

        if not self.navigation_state.current_position:
            logger.error("Cannot resume navigation: no current position")
            return False

        self.navigation_state.navigation_mode = NavigationMode.AUTO
        self.navigation_state.path_status = PathStatus.EXECUTING
        if self.navigation_state.operation_start_time is None:
            self.navigation_state.operation_start_time = datetime.now(UTC)

        logger.info("Navigation resumed")
        return True

    # ------------------------------------------------------------------
    # IMU alignment persistence
    # ------------------------------------------------------------------
    _ALIGNMENT_FILE = (
        Path(__file__).resolve().parent.parent.parent.parent / "data" / "imu_alignment.json"
    )

    def _load_alignment_from_disk(self) -> None:
        """Load persisted IMU alignment offset from data/imu_alignment.json.

        Called once during __init__.  A missing or corrupt file is silently ignored
        and the alignment starts at 0.0 (boot-time default).

        When a CalibrationRepository is injected, delegates to it instead of
        reading the file directly.
        """
        if self._calibration_repo is not None:
            data = self._calibration_repo.load_imu_alignment()
            self._session_heading_alignment = float(data.get("session_heading_alignment", 0.0)) % 360.0
            self._heading_alignment_sample_count = int(data.get("sample_count", 0))
            logger.info(
                "IMU alignment loaded via CalibrationRepository: %.1f° (source=%s, samples=%d)",
                self._session_heading_alignment,
                data.get("source", "unknown"),
                self._heading_alignment_sample_count,
            )
            return
        try:
            if not self._ALIGNMENT_FILE.exists():
                return
            data = json.loads(self._ALIGNMENT_FILE.read_text())
            saved = float(data.get("session_heading_alignment", 0.0))
            samples = int(data.get("sample_count", 0))
            source = data.get("source", "unknown")
            self._session_heading_alignment = saved % 360.0
            self._heading_alignment_sample_count = samples
            logger.info(
                "IMU alignment loaded from disk: %.1f° (source=%s, samples=%d)",
                self._session_heading_alignment,
                source,
                samples,
            )
        except Exception as exc:
            logger.warning("Could not load IMU alignment file: %s", exc)
            self._session_heading_alignment = 0.0

    def _save_alignment_to_disk(self, source: str) -> None:
        """Persist current session heading alignment to data/imu_alignment.json.

        Uses an atomic write (write to tmp then rename) to avoid partial files.
        Silently swallows errors so a filesystem issue never crashes navigation.

        When a CalibrationRepository is injected, delegates to it instead of
        writing the file directly.
        """
        if self._calibration_repo is not None:
            self._calibration_repo.save_imu_alignment(
                heading_deg=self._session_heading_alignment,
                sample_count=self._heading_alignment_sample_count,
                source=source,
            )
            return
        try:
            payload = {
                "session_heading_alignment": round(self._session_heading_alignment, 3),
                "sample_count": self._heading_alignment_sample_count,
                "source": source,
                "last_updated": datetime.now(UTC).isoformat(),
            }
            tmp = self._ALIGNMENT_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2))
            tmp.replace(self._ALIGNMENT_FILE)
            logger.info(
                "IMU alignment saved: %.1f° (source=%s, samples=%d)",
                self._session_heading_alignment,
                source,
                self._heading_alignment_sample_count,
            )
        except Exception as exc:
            logger.warning("Could not save IMU alignment to disk: %s", exc)

    async def stop_navigation(self) -> bool:
        """Stop navigation and return to idle"""
        self.navigation_state.navigation_mode = NavigationMode.IDLE
        self.navigation_state.target_velocity = 0.0

        if self.navigation_state.path_status == PathStatus.EXECUTING:
            self.navigation_state.path_status = PathStatus.INTERRUPTED

        stop_confirmed = await self._deliver_stop_command(reason="navigation stop")
        if stop_confirmed:
            logger.info("Navigation stopped")
        else:
            logger.error("Navigation stop requested but controller stop could not be confirmed")

        # Persist alignment if GPS COG has had a chance to refine it this session
        if self._heading_alignment_sample_count >= 10:
            self._save_alignment_to_disk("stop_navigation")

        return stop_confirmed

    async def emergency_stop(self, reason: str = "emergency stop") -> bool:
        """Emergency stop navigation"""
        self.navigation_state.navigation_mode = NavigationMode.EMERGENCY_STOP
        self.navigation_state.target_velocity = 0.0
        self.navigation_state.path_status = PathStatus.INTERRUPTED
        self._latch_global_emergency_state()

        # Record reason so the UI can show why the e-stop was activated
        try:
            from ..core import globals as _g

            _g._safety_state["estop_reason"] = reason
        except Exception:
            pass

        # Try to invoke controller-level emergency stop when available
        emergency_ok = True
        try:
            if os.getenv("SIM_MODE", "0") == "0":
                robohat = get_robohat_service()
                if robohat is not None:
                    emergency_ok = await robohat.emergency_stop()
                else:
                    emergency_ok = await self._deliver_stop_command(
                        reason="emergency stop fallback"
                    )
            else:
                emergency_ok = await self._deliver_stop_command(reason="simulation emergency stop")
        except Exception:
            logger.exception("Emergency stop delivery failed")
            emergency_ok = False

        logger.critical("Emergency stop activated")
        return emergency_ok

    async def return_home(self) -> bool:
        """Navigate back to home position"""
        if not self.navigation_state.home_position:
            logger.error("No home position set")
            return False

        # Plan path (with avoidance and boundary constraints if available)
        if self.navigation_state.current_position:
            boundaries = None
            if self.navigation_state.safety_boundaries:
                # Use the outer boundary (first polygon) if provided
                boundaries = self.navigation_state.safety_boundaries[0]
            obstacles = (
                self.navigation_state.no_go_zones if self.navigation_state.no_go_zones else None
            )

            waypoints = self.path_planner.return_to_base(
                current=self.navigation_state.current_position,
                home=self.navigation_state.home_position,
                boundary=boundaries,
                obstacles=obstacles,
            )

            self.navigation_state.planned_path = waypoints
            self.navigation_state.current_waypoint_index = 0
            self.navigation_state.navigation_mode = NavigationMode.RETURN_HOME
            self.navigation_state.path_status = PathStatus.EXECUTING

            logger.info("Returning to home position")
            return True

        return False

    def set_home_position(self, position: Position):
        """Set the home/docking position"""
        self.navigation_state.home_position = position
        logger.info(f"Home position set to {position.latitude}, {position.longitude}")

    def are_waypoints_in_geofence(self, waypoints: list[MissionWaypoint]) -> bool:
        """Return True when all mission waypoints are inside the configured safety boundary."""
        boundaries = self.navigation_state.safety_boundaries
        if not boundaries:
            return True

        outer_boundary = boundaries[0]
        if len(outer_boundary) < 3:
            return False

        polygon = [(point.latitude, point.longitude) for point in outer_boundary]
        return all(point_in_polygon(waypoint.lat, waypoint.lon, polygon) for waypoint in waypoints)

    def set_safety_boundaries(self, boundaries: list[list[Position]]):
        """Set safety boundaries that must not be crossed"""
        self.navigation_state.safety_boundaries = boundaries
        logger.info(f"Set {len(boundaries)} safety boundaries")

    def _load_boundaries_from_zones(self) -> None:
        """Load zone polygons from MapRepository into safety_boundaries and no_go_zones.

        Non-exclusion zones are stored as safety_boundaries (the mower must stay inside).
        Zones with exclusion_zone=True are stored as no_go_zones (the mower avoids these).

        Gracefully handles an empty repository (no zones saved) or a missing repository
        by leaving the boundary lists unchanged and logging a warning.
        """
        if self._map_repository is None:
            logger.warning(
                "MapRepository not attached; geofence enforcement disabled for this mission"
            )
            return

        try:
            zones = self._map_repository.list_zones()  # list[dict[str, Any]]
            boundary_polygons: list[list[Position]] = []
            no_go_polygons: list[list[Position]] = []

            for zone in zones:
                polygon_data = zone.get("polygon", [])
                pts = [
                    Position(latitude=float(p["latitude"]), longitude=float(p["longitude"]))
                    for p in polygon_data
                ]
                if len(pts) < 3:
                    continue

                if zone.get("exclusion_zone", False):
                    no_go_polygons.append(pts)
                else:
                    boundary_polygons.append(pts)

            self.navigation_state.safety_boundaries = boundary_polygons
            self.navigation_state.no_go_zones = no_go_polygons

            if boundary_polygons:
                logger.info(
                    "Loaded %d boundary polygon(s) and %d no-go zone(s) from MapRepository",
                    len(boundary_polygons),
                    len(no_go_polygons),
                )
            else:
                logger.warning(
                    "No mowing-area zones defined in MapRepository; "
                    "geofence enforcement disabled for this mission"
                )
        except Exception:
            logger.warning(
                "Failed to load map zones from MapRepository for geofence; "
                "continuing without boundary enforcement",
                exc_info=True,
            )

    def add_no_go_zone(self, zone: list[Position]):
        """Add a no-go zone to avoid"""
        self.navigation_state.no_go_zones.append(zone)
        logger.info("Added no-go zone")

    def _nearest_boundary_point(self, pos: Position, boundary: list[Position]) -> Position:
        """Return the boundary vertex closest to pos (Euclidean approx for nearby points)."""
        best = boundary[0]
        best_dist = haversine_m(pos.latitude, pos.longitude, best.latitude, best.longitude)
        for pt in boundary[1:]:
            d = haversine_m(pos.latitude, pos.longitude, pt.latitude, pt.longitude)
            if d < best_dist:
                best_dist = d
                best = pt
        return best

    def _get_encoder_rpms(self) -> tuple[float, float]:
        """Return (enc1_rpm, enc2_rpm) from RoboHAT status for traction control."""
        from .robohat_service import get_robohat_service
        robohat = get_robohat_service()
        if robohat is None:
            return 0.0, 0.0
        return robohat.status.encoder_1_rpm, robohat.status.encoder_2_rpm

    def _get_encoder_active(self) -> bool:
        """Return True only once encoders have shown at least one real tick."""
        from .robohat_service import get_robohat_service
        robohat = get_robohat_service()
        if robohat is None:
            return False
        return robohat.status.encoder_ever_incremented

    def get_pose(self) -> Pose2D | None:
        """Return the current fused Pose2D. None until first GPS fix."""
        return self._current_pose

    async def get_navigation_status(self) -> dict[str, Any]:
        """Get current navigation status"""
        pose = self._current_pose
        return {
            "mode": self.navigation_state.navigation_mode,
            "path_status": self.navigation_state.path_status,
            "current_position": self.navigation_state.current_position,
            "heading": self.navigation_state.heading,
            "velocity": self.navigation_state.velocity,
            "target_velocity": self.navigation_state.target_velocity,
            "waypoints_total": len(self.navigation_state.planned_path),
            "waypoints_completed": self.navigation_state.current_waypoint_index,
            "distance_traveled": self.navigation_state.distance_traveled,
            "obstacles_detected": len(self.navigation_state.obstacle_map),
            "dead_reckoning_active": self.navigation_state.dead_reckoning_active,
            "path_confidence": self.navigation_state.path_confidence,
            "pose_quality": pose.quality.value if pose else None,
            "pose_x_m": pose.x_m if pose else None,
            "pose_y_m": pose.y_m if pose else None,
            "pose_heading_deg": pose.heading_deg if pose else None,
        }
