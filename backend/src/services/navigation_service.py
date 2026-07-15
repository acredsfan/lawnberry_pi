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
from ..models.mission import MissionLegType, MissionWaypoint
from ..models.safety_limits import (
    BOOTSTRAP_SENSOR_POLL_INTERVAL_S,
    heading_bootstrap_stop_reserve_m,
)
from ..nav.geoutils import body_offset_to_north_east, haversine_m, offset_lat_lon, point_in_polygon
from ..nav.gps_degradation import (
    GPSDegradationConfig,
    GPSDegradationState,
    GPSDegradationStateMachine,
)
from ..nav.obstacle_clearance import required_obstacle_clearance_m
from ..nav.odometry import OdometryIntegrator
from ..nav.path_planner import PathPlanner
from .operating_area_service import OperatingAreaError, load_operating_area_snapshot
from .robohat_service import get_robohat_service

if TYPE_CHECKING:
    from ..models.mission import Mission
    from ..protocols.mission import MissionStatusReader

logger = logging.getLogger(__name__)


## Path planning moved to backend.src.nav.path_planner.PathPlanner


class ObstacleDetector:
    """Obstacle detection and avoidance"""

    def __init__(
        self,
        safety_distance: float = 0.2,
        limits: Any | None = None,
        persistence_seconds: float = 30.0,
    ):
        self.safety_distance = safety_distance
        self.limits = limits
        self.detected_obstacles: list[Obstacle] = []
        self.persistence_seconds = max(0.0, float(persistence_seconds))
        self._cost_map: dict[str, Obstacle] = {}
        self._last_seen_monotonic: dict[str, float] = {}
        self._active_ids: set[str] = set()

    @property
    def has_active_obstacle(self) -> bool:
        return bool(self._active_ids)

    def update_obstacles_from_sensors(
        self,
        sensor_data: SensorData,
        commanded_speed_mps: float | None = None,
        origin_position: Position | None = None,
        heading_deg: float | None = None,
    ) -> list[Obstacle]:
        """Update active detections and retain a bounded spatial cost map."""
        now = time.monotonic()
        active: list[Obstacle] = []
        speed = (
            commanded_speed_mps
            if commanded_speed_mps is not None
            else sensor_data.gps.speed if sensor_data.gps is not None else None
        )
        if self.limits is not None:
            threshold_m = required_obstacle_clearance_m(speed, self.limits)
        else:
            threshold_m = max(0.0, float(self.safety_distance))
        threshold_mm = threshold_m * 1000.0

        def observe(sensor_id: str, distance_mm: float, bearing_offset_deg: float) -> None:
            if not (0.0 < distance_mm <= threshold_mm):
                return
            distance_m = distance_mm / 1000.0
            position = None
            if origin_position is not None and heading_deg is not None:
                bearing = math.radians(float(heading_deg) + bearing_offset_deg)
                latitude, longitude = offset_lat_lon(
                    origin_position.latitude,
                    origin_position.longitude,
                    north_m=math.cos(bearing) * distance_m,
                    east_m=math.sin(bearing) * distance_m,
                )
                position = Position(latitude=latitude, longitude=longitude)
            previous = self._cost_map.get(sensor_id)
            first_detected = previous.first_detected if previous is not None else datetime.now(UTC)
            age_s = max(0.0, (datetime.now(UTC) - first_detected).total_seconds())
            obstacle = Obstacle(
                id=sensor_id,
                position=position,
                range_m=distance_m,
                bearing_offset_deg=bearing_offset_deg,
                confidence=0.9,
                obstacle_type="persistent" if age_s >= 2.0 else "transient",
                detection_source="tof",
                first_detected=first_detected,
                last_seen=datetime.now(UTC),
            )
            active.append(obstacle)
            self._cost_map[sensor_id] = obstacle
            self._last_seen_monotonic[sensor_id] = now

        if sensor_data.tof_left and sensor_data.tof_left.distance is not None:
            observe("tof_left", float(sensor_data.tof_left.distance), -20.0)
        if sensor_data.tof_right and sensor_data.tof_right.distance is not None:
            observe("tof_right", float(sensor_data.tof_right.distance), 20.0)

        self._active_ids = {obstacle.id for obstacle in active}
        expired = [
            obstacle_id
            for obstacle_id, seen_at in self._last_seen_monotonic.items()
            if now - seen_at > self.persistence_seconds
        ]
        for obstacle_id in expired:
            self._last_seen_monotonic.pop(obstacle_id, None)
            self._cost_map.pop(obstacle_id, None)
        self.detected_obstacles = list(self._cost_map.values())
        return self.detected_obstacles

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

    @property
    def velocity(self) -> float | None:
        return self._nav.navigation_state.velocity

    @property
    def quality(self) -> str | None:
        return self._nav.navigation_state.pose_quality

    @property
    def imu_valid(self) -> bool:
        return bool(self._nav.navigation_state.imu_valid)

    @property
    def heading_source(self) -> str | None:
        return self._nav.navigation_state.heading_source

    @property
    def accuracy_m(self) -> float | None:
        position = self.current_position
        return float(position.accuracy) if position and position.accuracy is not None else None

    @property
    def obstacle_avoidance_active(self) -> bool:
        return bool(self._nav.navigation_state.obstacle_avoidance_active)

    @property
    def obstacle_map(self) -> list[Obstacle]:
        return list(self._nav.navigation_state.obstacle_map)

    @property
    def gps_degradation(self) -> Any:
        return self._nav.gps_degradation.snapshot()

    @property
    def state(self) -> _NavStateLocalizationAdapter:
        return self


class _NavGatewayAdapter:
    """Adapts NavigationService drive/emergency interface to MissionExecutor's gateway protocol."""

    def __init__(self, nav_service: NavigationService) -> None:
        self._nav = nav_service

    def is_emergency_active(self) -> bool:
        return self._nav._global_emergency_active()

    async def dispatch_drive_speeds(
        self,
        left: float,
        right: float,
        *,
        heading_bootstrap: bool = False,
        require_hardware_ack: bool = False,
    ) -> bool:
        try:
            degradation = self._nav.gps_degradation.snapshot()
            motion_requested = abs(float(left)) > 1e-6 or abs(float(right)) > 1e-6
            if motion_requested and (degradation.terminal or degradation.motion_held):
                self._nav.navigation_state.target_velocity = 0.0
                logger.warning(
                    "Mission drive held by GPS policy: state=%s reason=%s",
                    degradation.state.value,
                    degradation.reason,
                )
                return False
            if motion_requested and degradation.speed_cap_mps is not None:
                peak = max(abs(float(left)), abs(float(right)))
                if peak > degradation.speed_cap_mps and peak > 0:
                    scale = degradation.speed_cap_mps / peak
                    left = float(left) * scale
                    right = float(right) * scale
            self._nav.navigation_state.target_velocity = float(max(abs(left), abs(right)))
            if self._nav._command_gateway is None:
                if heading_bootstrap:
                    logger.error("Heading bootstrap requires MotorCommandGateway")
                    self._nav.navigation_state.target_velocity = 0.0
                    return False
                await self._nav.set_speed(left, right)
                return True
            from ..control.commands import CommandStatus, DriveCommand

            def _normalize(value: float) -> float:
                if self._nav.max_speed <= 0:
                    return 0.0
                return max(-1.0, min(1.0, float(value) / self._nav.max_speed))

            outcome = await self._nav._command_gateway.dispatch_drive(
                DriveCommand(
                    left=_normalize(right),
                    right=_normalize(left),
                    source="mission",
                    duration_ms=self._nav.autonomous_command_ttl_ms,
                    max_speed_limit=1.0,
                    heading_bootstrap=heading_bootstrap,
                )
            )
            accepted = outcome.status == CommandStatus.ACCEPTED or (
                outcome.status == CommandStatus.QUEUED
                and (not require_hardware_ack or os.getenv("SIM_MODE", "0") == "1")
            )
            if not accepted:
                self._nav.navigation_state.target_velocity = 0.0
            return accepted
        except Exception as exc:
            self._nav.navigation_state.target_velocity = 0.0
            logger.debug("_NavGatewayAdapter.dispatch_drive_speeds failed: %s", exc)
            return False

    async def dispatch_blade(self, active: bool) -> bool:
        if self._nav._command_gateway is None:
            return not active
        try:
            from ..control.commands import BladeCommand, CommandStatus

            outcome = await self._nav._command_gateway.dispatch_blade(
                BladeCommand(active=active, source="mission")
            )
            return outcome.status == CommandStatus.ACCEPTED
        except Exception as exc:
            logger.debug("_NavGatewayAdapter.dispatch_blade failed: %s", exc)
            return False


class NavigationService:
    """Main navigation service with sensor fusion and path planning"""

    def __init__(
        self,
        weather=None,
        calibration_repository=None,
        *,
        config_loader: ConfigLoader | None = None,
        load_runtime_config: bool = True,
        alignment_file: str | Path | None = None,
        load_persisted_alignment: bool = True,
    ):
        self.navigation_state = NavigationState()
        self.path_planner = PathPlanner()
        self.dead_reckoning = DeadReckoningSystem()
        self.gps_degradation = GPSDegradationStateMachine()
        # Optional weather service with get_current() and get_planning_advice()
        self.weather = weather
        # Optional CalibrationRepository for IMU alignment persistence.
        # When set, _load_alignment_from_disk and _save_alignment_to_disk delegate
        # to the repository instead of reading/writing data/imu_alignment.json directly.
        self._calibration_repo = calibration_repository

        # Navigation parameters
        self.max_speed = 0.8  # m/s
        self.cruise_speed = 0.7  # m/s
        self.waypoint_tolerance = 1.0  # meters — fallback when GPS accuracy unavailable
        self.obstacle_avoidance_distance = 0.2  # meters
        self._safety_limits = None
        self.max_waypoint_fix_age_seconds = 2.0
        self.max_waypoint_accuracy_m = 5.0
        self.bootstrap_required_accuracy_m = 0.25
        self.geofence_inner_margin_m = 1.0
        self.autonomous_max_gps_accuracy_m = 0.25
        self.autonomous_max_gps_fix_age_s = 2.0
        self.mower_footprint_radius_m = 0.35
        self.differential_drive_wheelbase_m = 0.30
        self.geofence_safety_allowance_m = 0.10
        self.autonomous_prediction_horizon_s = 1.0
        self.autonomous_command_ttl_ms = 350
        self.autonomous_braking_decel_mps2 = 0.5
        self.bootstrap_speed_mps = 0.20
        self.bootstrap_min_travel_m = 0.25
        self.bootstrap_max_travel_m = 0.60
        self.coverage_endpoint_clearance_m = 0.25
        self.max_operational_cross_track_error_m = 1.5
        self.position_verification_timeout_seconds = 30.0
        # Warn when GPS position diverges from dead-reckoning estimate by more
        # than this distance (metres) on re-acquisition after a GPS outage.
        self.position_mismatch_warn_threshold_m = 5.0
        self._imu_yaw_offset = 0.0
        self._gps_antenna_offset_forward_m = 0.0
        self._gps_antenna_offset_right_m = 0.0

        if load_runtime_config:
            try:
                hardware, limits = (config_loader or ConfigLoader()).get()
                self._safety_limits = limits
                self.obstacle_avoidance_distance = float(limits.tof_obstacle_distance_meters)
                self.autonomous_max_gps_accuracy_m = float(limits.autonomous_max_gps_accuracy_m)
                self.autonomous_max_gps_fix_age_s = float(limits.autonomous_max_gps_fix_age_s)
                self.max_waypoint_accuracy_m = self.autonomous_max_gps_accuracy_m
                self.bootstrap_required_accuracy_m = self.autonomous_max_gps_accuracy_m
                self.mower_footprint_radius_m = float(limits.mower_footprint_radius_m)
                self.differential_drive_wheelbase_m = float(
                    limits.differential_drive_wheelbase_m
                )
                self.geofence_safety_allowance_m = float(limits.geofence_safety_allowance_m)
                self.autonomous_prediction_horizon_s = float(
                    limits.autonomous_prediction_horizon_s
                )
                self.autonomous_command_ttl_ms = int(limits.autonomous_command_ttl_ms)
                self.autonomous_braking_decel_mps2 = float(
                    limits.autonomous_braking_decel_mps2
                )
                self.bootstrap_speed_mps = float(limits.bootstrap_speed_mps)
                self.bootstrap_min_travel_m = float(limits.bootstrap_min_travel_m)
                self.bootstrap_max_travel_m = float(limits.bootstrap_max_travel_m)
                self.coverage_endpoint_clearance_m = float(limits.coverage_endpoint_clearance_m)
                self.max_operational_cross_track_error_m = float(
                    limits.max_operational_cross_track_error_m
                )
                self._imu_yaw_offset = float(
                    getattr(hardware, "imu_yaw_offset_degrees", 0.0)
                )
                self._gps_antenna_offset_forward_m = float(
                    getattr(hardware, "gps_antenna_offset_forward_m", 0.0) or 0.0
                )
                self._gps_antenna_offset_right_m = float(
                    getattr(hardware, "gps_antenna_offset_right_m", 0.0) or 0.0
                )
                if self._imu_yaw_offset != 0.0:
                    logger.info(
                        "IMU yaw offset loaded: %.1f° "
                        "(applied as: adjusted = (-raw + offset) %% 360)",
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

        try:
            self.geofence_inner_margin_m = max(
                0.0, float(os.getenv("LAWNBERRY_GEOFENCE_INNER_MARGIN_M", "1.0"))
            )
        except ValueError:
            self.geofence_inner_margin_m = 1.0

        self.obstacle_detector = ObstacleDetector(
            self.obstacle_avoidance_distance,
            self._safety_limits,
        )

        # State tracking
        self.total_distance = 0.0
        self.last_position: Position | None = None
        self._mission_execution_active = False
        self._active_mission_id: str | None = None
        self._mission_execution_phase: str = "idle"

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
        self._alignment_imu_epoch_id: str | None = None
        self._active_imu_epoch_id: str | None = None
        self._gps_cog_history: list = []  # recent GPS COG values for straight-motion gate
        # Tolerance for GPS COG consistency during bootstrap straight-line detection.
        # GPS COG can be noisy; increased from 10° to 15° to tolerate GPS jitter
        # and minor steering inputs during the ~15s bootstrap drive.
        # Set via LAWNBERRY_BOOTSTRAP_STRAIGHT_TOLERANCE_DEG environment variable.
        try:
            self._bootstrap_straight_tolerance_deg = float(
                os.getenv("LAWNBERRY_BOOTSTRAP_STRAIGHT_TOLERANCE_DEG", "15.0")
            )
        except ValueError:
            self._bootstrap_straight_tolerance_deg = 15.0
        # Track when bootstrap begins for lenient GPS snap criteria.
        self._bootstrap_start_time: float | None = None
        self._bootstrap_start_antenna_position: Position | None = None
        self._bootstrap_initial_imu_yaw_deg: float | None = None
        self._bootstrap_alignment_staged: bool = False
        self._last_imu_monotonic_s: float | None = None
        self._last_imu_raw_yaw_deg: float | None = None
        self._require_gps_heading_alignment: bool = False
        self._last_gps_track_position: Position | None = None
        self._last_gps_track_time: datetime | None = None
        if alignment_file is not None:
            self._ALIGNMENT_FILE = Path(alignment_file)
        if load_persisted_alignment:
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
        self._command_gateway: Any | None = None
        self._operating_area_snapshot: Any | None = None

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
            docking_confirmed_provider=self._cached_docking_confirmed,
            obstacle_active_provider=lambda: self.navigation_state.obstacle_avoidance_active,
            obstacle_replan_provider=self._plan_obstacle_detour,
            gps_degradation_provider=self.gps_degradation.snapshot,
            max_speed=self.max_speed,
            cruise_speed=self.cruise_speed,
            waypoint_tolerance=self.waypoint_tolerance,
            max_waypoint_fix_age_seconds=self.max_waypoint_fix_age_seconds,
            max_waypoint_accuracy_m=self.max_waypoint_accuracy_m,
            position_verification_timeout_seconds=self.position_verification_timeout_seconds,
            max_operational_cross_track_error_m=self.max_operational_cross_track_error_m,
        )

    @staticmethod
    def _cached_docking_confirmed() -> bool:
        """Return cached charge truth; never initiate a sensor read from the control loop."""
        if os.getenv("SIM_MODE", "0") == "1":
            return True
        try:
            from ..core.state_manager import get_sensor_manager

            manager = get_sensor_manager()
            reading = getattr(getattr(manager, "power", None), "last_reading", None)
            if reading is None:
                return False
            battery_current = getattr(reading, "battery_current", None)
            solar_power = getattr(reading, "solar_power", None)
            return bool(
                battery_current is not None
                and float(battery_current) > 0.05
                and solar_power is not None
                and float(solar_power) > 0.5
            )
        except Exception:
            logger.debug("Cached dock/charge confirmation unavailable", exc_info=True)
            return False

    def _plan_obstacle_detour(
        self,
        current: Position,
        goal: Position,
    ) -> list[Position]:
        """Plan against the retained spatial obstacle cost map after a stop/wait cycle."""
        snapshot = self.get_operating_area_snapshot()
        if not snapshot.valid:
            return []
        obstacle_polygons: list[list[Position]] = []
        for obstacle in self.navigation_state.obstacle_map:
            if obstacle.position is None:
                continue
            center = obstacle.position
            radius_m = 0.08

            def corner(
                north_m: float,
                east_m: float,
                center_position: Position = center,
            ) -> Position:
                latitude, longitude = offset_lat_lon(
                    center_position.latitude,
                    center_position.longitude,
                    north_m=north_m,
                    east_m=east_m,
                )
                return Position(latitude=latitude, longitude=longitude)

            obstacle_polygons.append(
                [
                    corner(north, east)
                    for north, east in (
                        (-radius_m, -radius_m),
                        (-radius_m, radius_m),
                        (radius_m, radius_m),
                        (radius_m, -radius_m),
                    )
                ]
            )
        if not obstacle_polygons:
            return []
        route = self.path_planner.find_path(
            current,
            goal,
            snapshot.safe_boundary,
            obstacles=obstacle_polygons,
            grid_resolution_m=0.25,
            safety_margin_m=0.10,
            boundary_margin_m=self.coverage_endpoint_clearance_m,
        )
        positions = [waypoint.position for waypoint in route]
        if not positions or not snapshot.path_is_safe(
            positions, self.coverage_endpoint_clearance_m
        ):
            return []
        return positions

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

    @property
    def nav_debug(self) -> dict:
        """Return the latest per-tick debug snapshot from the mission executor."""
        return self._mission_executor._debug_state if self._mission_executor is not None else {}

    def _current_pose_quality(self) -> str:
        """Map current GPS/IMU state to a pose quality string."""
        if self.navigation_state.pose_quality:
            return self.navigation_state.pose_quality
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

    def _bind_live_imu_epoch(self, imu_epoch_id: str) -> bool:
        """Bind navigation alignment to the actual BNO085 reset generation."""
        normalized = imu_epoch_id.strip() if isinstance(imu_epoch_id, str) else ""
        if not normalized:
            return False
        previous = self._active_imu_epoch_id
        self._active_imu_epoch_id = normalized
        if self._calibration_repo is not None:
            self._calibration_repo.bind_imu_epoch(normalized)
        if self._use_localization():
            self._localization.bind_imu_epoch(normalized)
        if self._alignment_imu_epoch_id != normalized:
            self._session_heading_alignment = 0.0
            self._heading_alignment_sample_count = 0
            self._alignment_imu_epoch_id = None
            self._require_gps_heading_alignment = True
            self._bootstrap_alignment_staged = False
            self.navigation_state.heading = None
            self.navigation_state.heading_source = None
        return previous is not None and previous != normalized

    def _imu_epoch_is_current(self) -> bool:
        if self._active_imu_epoch_id is None:
            return False
        if self._calibration_repo is None:
            return True
        return self._calibration_repo.imu_epoch_id == self._active_imu_epoch_id

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

    def attach_command_gateway(self, command_gateway: Any) -> None:
        """Route mission drive commands through MotorCommandGateway."""
        self._command_gateway = command_gateway
        if hasattr(command_gateway, "set_autonomy_context_provider"):
            command_gateway.set_autonomy_context_provider(self._autonomy_context_for_gateway)
        logger.info("MotorCommandGateway attached to NavigationService")

    def apply_safety_limits(self, limits: Any) -> None:
        """Hot-reload navigation-owned safety thresholds from the canonical model."""
        self._safety_limits = limits
        self.obstacle_avoidance_distance = float(limits.tof_obstacle_distance_meters)
        self.obstacle_detector.safety_distance = self.obstacle_avoidance_distance
        self.obstacle_detector.limits = limits
        self.autonomous_max_gps_accuracy_m = float(limits.autonomous_max_gps_accuracy_m)
        self.autonomous_max_gps_fix_age_s = float(limits.autonomous_max_gps_fix_age_s)
        prior_gps_policy = self.gps_degradation.config
        self.gps_degradation.configure(
            GPSDegradationConfig(
                max_accuracy_m=self.autonomous_max_gps_accuracy_m,
                max_fix_age_s=self.autonomous_max_gps_fix_age_s,
                hold_grace_s=prior_gps_policy.hold_grace_s,
                max_degraded_s=prior_gps_policy.max_degraded_s,
                recovery_samples=prior_gps_policy.recovery_samples,
                degraded_speed_cap_mps=prior_gps_policy.degraded_speed_cap_mps,
            )
        )
        self.bootstrap_required_accuracy_m = self.autonomous_max_gps_accuracy_m
        self.mower_footprint_radius_m = float(limits.mower_footprint_radius_m)
        self.differential_drive_wheelbase_m = float(limits.differential_drive_wheelbase_m)
        self.geofence_safety_allowance_m = float(limits.geofence_safety_allowance_m)
        self.autonomous_prediction_horizon_s = float(limits.autonomous_prediction_horizon_s)
        self.autonomous_command_ttl_ms = int(limits.autonomous_command_ttl_ms)
        self.autonomous_braking_decel_mps2 = float(limits.autonomous_braking_decel_mps2)
        self.bootstrap_speed_mps = float(limits.bootstrap_speed_mps)
        self.bootstrap_min_travel_m = float(limits.bootstrap_min_travel_m)
        self.bootstrap_max_travel_m = float(limits.bootstrap_max_travel_m)
        self.coverage_endpoint_clearance_m = float(limits.coverage_endpoint_clearance_m)
        self.max_operational_cross_track_error_m = float(
            limits.max_operational_cross_track_error_m
        )

    def _load_operating_area_snapshot(self) -> Any:
        snapshot = load_operating_area_snapshot(
            map_repository=self._map_repository,
            allow_zone_fallback=os.getenv("SIM_MODE", "0") == "1",
        )
        self._operating_area_snapshot = snapshot
        self.navigation_state.operating_area_source = snapshot.source
        self.navigation_state.operating_area_revision = snapshot.revision_hash
        self.navigation_state.operating_area_validity = snapshot.validity_state
        if snapshot.valid:
            self.navigation_state.safety_boundaries = [snapshot.safe_boundary]
            self.navigation_state.no_go_zones = snapshot.exclusions
            if self.navigation_state.current_position is not None:
                self.navigation_state.boundary_clearance_m = snapshot.distance_to_boundary(
                    self.navigation_state.current_position
                )
        return snapshot

    def get_operating_area_snapshot(self) -> Any:
        return getattr(self, "_operating_area_snapshot", None) or self._load_operating_area_snapshot()

    def _autonomy_context_for_gateway(self, cmd: Any) -> dict[str, Any]:
        snapshot = self.get_operating_area_snapshot()
        bootstrap_requested = bool(getattr(cmd, "heading_bootstrap", False))
        bootstrap_active = (
            self._bootstrap_start_time is not None
            and self._mission_execution_phase == "heading_bootstrap"
        )
        pos = (
            self._raw_antenna_position_for_bootstrap()
            if bootstrap_requested
            else self.navigation_state.current_position
        )
        traveled_m = self._bootstrap_travel_m(pos) if bootstrap_active else None
        bootstrap_remaining_m = (
            max(0.0, float(self.bootstrap_max_travel_m) - traveled_m)
            if traveled_m is not None
            else None
        )
        bootstrap_stop_reserve_m = (
            self._heading_bootstrap_stop_reserve_m() if bootstrap_requested else None
        )
        imu_age_s = self._live_imu_age_s()
        yaw_delta_deg: float | None = None
        if (
            self._bootstrap_initial_imu_yaw_deg is not None
            and self._last_imu_raw_yaw_deg is not None
        ):
            yaw_delta_deg = abs(
                self._heading_delta(
                    self._last_imu_raw_yaw_deg,
                    self._bootstrap_initial_imu_yaw_deg,
                )
            )
        if pos is not None and snapshot.valid:
            self.navigation_state.boundary_clearance_m = snapshot.distance_to_boundary(pos)
        return {
            "snapshot": snapshot,
            "position": pos,
            "last_gps_fix": self.navigation_state.last_gps_fix,
            "dead_reckoning_active": self.navigation_state.dead_reckoning_active,
            "heading": self.navigation_state.heading,
            "imu_valid": self.navigation_state.imu_valid,
            "imu_age_s": imu_age_s,
            "imu_epoch_valid": self._imu_epoch_is_current(),
            "accuracy_m": pos.accuracy if pos is not None else None,
            "heading_bootstrap_active": bootstrap_active,
            "mission_phase": self._mission_execution_phase,
            "bootstrap_travel_m": traveled_m,
            "bootstrap_remaining_m": bootstrap_remaining_m,
            "bootstrap_stop_reserve_m": bootstrap_stop_reserve_m,
            "bootstrap_max_travel_m": self.bootstrap_max_travel_m,
            "bootstrap_speed_mps": self.bootstrap_speed_mps,
            "bootstrap_imu_yaw_delta_deg": yaw_delta_deg,
            "bootstrap_max_yaw_delta_deg": self._bootstrap_straight_tolerance_deg,
            "antenna_offset_m": math.hypot(
                self._gps_antenna_offset_forward_m,
                self._gps_antenna_offset_right_m,
            ),
            "tof_blocked": self.navigation_state.obstacle_avoidance_active,
            "max_fix_age_s": self.autonomous_max_gps_fix_age_s,
            "max_accuracy_m": self.autonomous_max_gps_accuracy_m,
            "footprint_radius_m": self.mower_footprint_radius_m,
            "fixed_allowance_m": self.geofence_safety_allowance_m,
            "prediction_horizon_s": self.autonomous_prediction_horizon_s,
            "command_latency_s": max(0.0, float(getattr(cmd, "duration_ms", 0)) / 1000.0),
            "wheelbase_m": self.differential_drive_wheelbase_m,
            "braking_decel_mps2": self.autonomous_braking_decel_mps2,
        }

    def _raw_antenna_position_for_bootstrap(self) -> Position | None:
        """Return one stable raw-GPS frame for bootstrap geometry and travel."""
        if self._use_localization():
            pose = self._localization.canonical_pose()
            return pose.antenna_position
        if math.hypot(
            self._gps_antenna_offset_forward_m,
            self._gps_antenna_offset_right_m,
        ) > 1e-6:
            return None
        return self.navigation_state.current_position

    def _bootstrap_travel_m(self, current_antenna: Position | None = None) -> float | None:
        start = self._bootstrap_start_antenna_position
        current = current_antenna or self._raw_antenna_position_for_bootstrap()
        if start is None or current is None:
            return None
        return haversine_m(
            start.latitude,
            start.longitude,
            current.latitude,
            current.longitude,
        )

    def _heading_bootstrap_stop_reserve_m(self) -> float:
        gps_age_s = self._bootstrap_gps_age_s()
        return heading_bootstrap_stop_reserve_m(
            speed_mps=self.bootstrap_speed_mps,
            command_ttl_ms=self.autonomous_command_ttl_ms,
            braking_decel_mps2=self.autonomous_braking_decel_mps2,
            poll_interval_s=max(
                BOOTSTRAP_SENSOR_POLL_INTERVAL_S,
                gps_age_s if gps_age_s is not None else BOOTSTRAP_SENSOR_POLL_INTERVAL_S,
            ),
        )

    def _bootstrap_gps_age_s(self) -> float | None:
        if self._use_localization():
            received = self._localization.canonical_pose().sample_monotonic_s
            if isinstance(received, (int, float)) and math.isfinite(float(received)):
                return max(0.0, time.monotonic() - float(received))
        last_fix = self.navigation_state.last_gps_fix
        if isinstance(last_fix, datetime) and last_fix.tzinfo is not None:
            return max(0.0, (datetime.now(UTC) - last_fix).total_seconds())
        return None

    def _live_imu_age_s(self) -> float | None:
        if self._last_imu_monotonic_s is None:
            return None
        return max(0.0, time.monotonic() - self._last_imu_monotonic_s)

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

    async def execute_mission(
        self,
        mission: Mission,
        mission_service: MissionStatusReader,
        *,
        reuse_heading_alignment: bool = False,
    ):
        """Execute a mission by navigating to each waypoint."""
        logger.info("NavigationService: delegating execute_mission %s to MissionExecutor", mission.id)
        saved = self._load_saved_alignment_for_mission_start()
        if reuse_heading_alignment and (saved is None or int(saved[1]) < 1):
            raise RuntimeError(
                "HEADING_ALIGNMENT_REQUIRED: run one fresh center-yard heading bootstrap first"
            )
        self._active_mission_id = mission.id
        gps_snapshot = self.gps_degradation.start_mission()
        self.navigation_state.gps_degradation_state = gps_snapshot.state.value
        self.navigation_state.gps_degradation_reason = None
        self.navigation_state.gps_degradation_seconds = 0.0
        self.navigation_state.gps_speed_cap_mps = None
        self._mission_execution_phase = "admitting"
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

        # Reset heading alignment state for new mission (localization bootstrap).
        # Prefer the last saved alignment so IMU heading works immediately while
        # a fresh GPS COG bootstrap snap validates/refines it.  Only fall back to
        # 0° if the saved alignment is stale (> 24 h) or was itself a reset record.
        self._gps_cog_history.clear()
        self._require_gps_heading_alignment = not reuse_heading_alignment
        self._last_gps_track_position = None
        self._last_gps_track_time = None
        # A saved alignment may be reused, but the heading itself must be
        # regenerated by a live IMU tick before any drive command.
        self.navigation_state.heading = None
        self.navigation_state.heading_source = None
        self.navigation_state.imu_valid = False
        self._last_imu_monotonic_s = None
        self._last_imu_raw_yaw_deg = None
        self.navigation_state.gps_cog = None
        if saved is not None:
            saved_value, saved_samples, saved_age_s = saved
            self._session_heading_alignment = saved_value
            self._heading_alignment_sample_count = (
                max(1, int(saved_samples)) if reuse_heading_alignment else 0
            )
            self._alignment_imu_epoch_id = (
                self._active_imu_epoch_id if reuse_heading_alignment else None
            )
            # Do NOT write "mission_start_reset" — the disk still holds the prior snap.
            logger.info(
                "Mission start: loaded saved heading alignment %.1f° (age %.0fs, prev_samples=%d) "
                "— %s",
                saved_value,
                saved_age_s,
                saved_samples,
                (
                    "reusing alignment for blade-off diagnostic"
                    if reuse_heading_alignment
                    else "requiring fresh GPS COG bootstrap"
                ),
            )
        else:
            self._session_heading_alignment = 0.0
            self._heading_alignment_sample_count = 0
            self._alignment_imu_epoch_id = None
            self._save_alignment_to_disk("mission_start_reset")
            logger.info("Mission start: no valid saved alignment — GPS COG bootstrap required")
        # Mirror state into LocalizationService when it owns pose state.
        if self._use_localization():
            self._localization.reset_for_mission(
                saved_alignment=saved,
                require_fresh_bootstrap=not reuse_heading_alignment,
            )
        self._bootstrap_alignment_staged = False

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
        await asyncio.to_thread(self._load_boundaries_from_zones)

        async def _bootstrap():
            if reuse_heading_alignment:
                self._mission_execution_phase = "heading_validation"
                await self._validate_reused_heading_and_geofence()
            else:
                self._mission_execution_phase = "heading_bootstrap"
                await self._run_bootstrap_and_check_geofence()
            self._mission_execution_phase = "waypoint"

        def _on_waypoint_advance(completed_index: int) -> None:
            self.navigation_state.current_waypoint_index = completed_index + 1

        async def _sensor_pump() -> None:
            """Poll sensors and update navigation state throughout the mission.

            The go_to_waypoint control loop reads navigation_state.heading but
            never calls update_navigation_state itself. Without this pump the
            heading freezes the moment the bootstrap loop ends, causing any
            tank-turn to steer against a static heading forever.

            Also enforces the geofence on every tick: if the mower's GPS
            position exits the safety boundary during a mission, the global
            emergency stop is latched immediately so the waypoint loop halts
            on its next iteration.
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

                # Continuous geofence enforcement — use the authoritative
                # operating-area snapshot and the same footprint/uncertainty
                # semantics as gateway authorization. Center-point containment
                # alone is insufficient near edges and exclusions.
                try:
                    pos = self.navigation_state.current_position
                    if pos is not None and not self._global_emergency_active():
                        snapshot = self.get_operating_area_snapshot()
                        snapshot.validate_ready_for_autonomy(
                            position=pos,
                            last_gps_fix=self.navigation_state.last_gps_fix,
                            dead_reckoning_active=self.navigation_state.dead_reckoning_active,
                            max_fix_age_s=float(
                                getattr(self, "autonomous_max_gps_fix_age_s", 2.0)
                            ),
                            max_accuracy_m=float(
                                getattr(self, "autonomous_max_gps_accuracy_m", 0.25)
                            ),
                            footprint_radius_m=float(
                                getattr(self, "mower_footprint_radius_m", 0.35)
                            ),
                            fixed_allowance_m=float(
                                getattr(self, "geofence_safety_allowance_m", 0.10)
                            ),
                        )
                        self.navigation_state.boundary_clearance_m = (
                            snapshot.distance_to_boundary(pos) if snapshot.valid else None
                        )
                except OperatingAreaError as exc:
                    logger.critical(
                        "GEOFENCE VIOLATION: %s (%s) — emergency stop triggered",
                        exc.reason_code,
                        exc.detail,
                    )
                    self._latch_global_emergency_state(
                        reason=f"{exc.reason_code}: {exc.detail}"
                    )
                except Exception as exc:
                    logger.warning("Geofence check error in sensor pump: %s", exc)

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
            self._active_mission_id = None
            self._mission_execution_phase = "idle"

    def get_mission_execution_phase(self, mission_id: str) -> str | None:
        """Return the live async phase only for the active navigation mission."""
        if self._active_mission_id != mission_id:
            return None
        return self._mission_execution_phase

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
        The blade-off command is explicitly tagged, renews only after fresh sensor
        and travel-budget checks, and remains inside a direction-independent radial
        envelope while world heading is unknown.

        Raises RuntimeError if GPS COG cannot snap within the deadline — callers
        must treat this as a mission abort, not a recoverable condition.
        """
        _BOOTSTRAP_DEADLINE_S: float = 15.0
        _GPS_PREFLIGHT_WAIT_S: float = 60.0

        # Require a raw antenna position so the coordinate frame cannot jump when
        # the heading snap makes the body-center correction available.
        antenna_position = self._raw_antenna_position_for_bootstrap()
        if not (
            self._position_ready_for_bootstrap(antenna_position)
            and self._imu_ready_for_bootstrap()
        ):
            logger.info(
                "Heading bootstrap: waiting for RTK-grade GPS (<=%.2f m) and live IMU "
                "before driving "
                "(timeout %.0f s)...",
                self.bootstrap_required_accuracy_m,
                _GPS_PREFLIGHT_WAIT_S,
            )
            from ..core.state_manager import get_sensor_manager as _get_sm
            gps_wait_start = time.monotonic()
            gps_fix_deadline = gps_wait_start + _GPS_PREFLIGHT_WAIT_S
            _last_gps_warn_t = gps_wait_start
            while time.monotonic() < gps_fix_deadline:
                await asyncio.sleep(BOOTSTRAP_SENSOR_POLL_INTERVAL_S)
                try:
                    await self._refresh_bootstrap_sensor_state(_get_sm())
                except Exception as exc:
                    logger.debug("Heading bootstrap preflight sensor refresh failed: %s", exc)
                antenna_position = self._raw_antenna_position_for_bootstrap()
                if (
                    self._position_ready_for_bootstrap(antenna_position)
                    and self._imu_ready_for_bootstrap()
                ):
                    _acc = getattr(antenna_position, "accuracy", None)
                    logger.info(
                        "Heading bootstrap: RTK-grade GPS and live IMU acquired "
                        "(accuracy=%.2f m, waited %.0f s) — starting drive.",
                        _acc or 0.0,
                        time.monotonic() - gps_wait_start,
                    )
                    break
                _now = time.monotonic()
                if _now - _last_gps_warn_t >= 10.0:
                    logger.warning(
                        "Heading bootstrap: still waiting for RTK-grade GPS (<=%.2f m) "
                        "and live IMU (%.0f s elapsed — check GPS and IMU status)",
                        self.bootstrap_required_accuracy_m,
                        _now - gps_wait_start,
                    )
                    _last_gps_warn_t = _now
            else:
                raise RuntimeError(
                    "Heading bootstrap pre-flight: no RTK-grade GPS plus live IMU "
                    f"(<= {self.bootstrap_required_accuracy_m:.2f} m) within "
                    f"{_GPS_PREFLIGHT_WAIT_S:.0f} s. Check GPS and IMU status."
                )
        else:
            _acc = getattr(antenna_position, "accuracy", None)
            logger.info(
                "Heading bootstrap: RTK-grade GPS and live IMU already available "
                "(accuracy=%.2f m) — starting drive.",
                _acc or 0.0,
            )

        stop_reserve_m = self._heading_bootstrap_stop_reserve_m()
        if self.bootstrap_min_travel_m + stop_reserve_m >= self.bootstrap_max_travel_m:
            raise RuntimeError(
                "HEADING_BOOTSTRAP_BUDGET_INVALID: minimum travel plus live GPS/lease/"
                "braking reserve does not fit inside maximum travel"
            )
        if antenna_position is None or self._last_imu_raw_yaw_deg is None:
            raise RuntimeError("IMU_NOT_READY: live bootstrap pose was lost before dispatch")

        logger.info("Heading bootstrap: driving forward to acquire GPS COG snap...")
        self._bootstrap_start_antenna_position = antenna_position
        self._bootstrap_initial_imu_yaw_deg = self._last_imu_raw_yaw_deg
        self._bootstrap_start_time = time.monotonic()
        if self._use_localization():
            self._localization.begin_bootstrap()
        deadline = time.monotonic() + _BOOTSTRAP_DEADLINE_S
        completed = False
        try:
            accepted = await self._gateway_adapter.dispatch_drive_speeds(
                self.bootstrap_speed_mps,
                self.bootstrap_speed_mps,
                heading_bootstrap=True,
            )
            if not accepted:
                raise RuntimeError("Heading bootstrap drive rejected by safety gateway")
            _last_drive_t = time.monotonic()
            refresh_interval_s = min(
                0.2,
                max(0.05, float(self.autonomous_command_ttl_ms) / 2000.0),
            )
            while time.monotonic() < deadline:
                await asyncio.sleep(BOOTSTRAP_SENSOR_POLL_INTERVAL_S)
                if self._global_emergency_active():
                    raise RuntimeError("EMERGENCY_STOP_ACTIVE: heading bootstrap aborted")

                try:
                    from ..core.state_manager import get_sensor_manager
                    await self._refresh_bootstrap_sensor_state(get_sensor_manager())
                except Exception as exc:
                    logger.debug("Bootstrap sensor refresh failed: %s", exc)

                if not self._imu_ready_for_bootstrap():
                    raise RuntimeError("IMU_NOT_READY: live IMU was lost during bootstrap")

                yaw_delta_deg = abs(
                    self._heading_delta(
                        self._last_imu_raw_yaw_deg or 0.0,
                        self._bootstrap_initial_imu_yaw_deg or 0.0,
                    )
                )
                if yaw_delta_deg > self._bootstrap_straight_tolerance_deg:
                    raise RuntimeError(
                        "HEADING_BOOTSTRAP_TURN_DETECTED: relative IMU yaw changed "
                        f"{yaw_delta_deg:.1f} degrees"
                    )

                if self._use_localization():
                    done = self._localization.alignment_sample_count >= 1
                    align_val = self._localization.session_heading_alignment
                else:
                    done = self._heading_alignment_sample_count >= 1
                    align_val = self._session_heading_alignment

                current_antenna = self._raw_antenna_position_for_bootstrap()
                dist_m = self._bootstrap_travel_m(current_antenna)
                if dist_m is None:
                    raise RuntimeError("LOCALIZATION_STALE: raw GPS antenna position unavailable")
                if dist_m > self.bootstrap_max_travel_m:
                    raise RuntimeError(
                        "Heading bootstrap exceeded maximum configured travel distance"
                    )

                if done and dist_m >= self.bootstrap_min_travel_m:
                    logger.info(
                        "Heading bootstrap complete: session_align=%.1f° travel=%.2fm",
                        align_val,
                        dist_m,
                    )
                    completed = True
                    break
                if done:
                    logger.debug(
                        "Bootstrap snap at %.2fm — waiting for %.2fm minimum travel",
                        dist_m,
                        self.bootstrap_min_travel_m,
                    )

                # The estimate is based on the latest raw antenna fix. Reserve all
                # movement possible during GPS age, the next lease, polling, and braking
                # before authorizing another nonzero command.
                stop_reserve_m = self._heading_bootstrap_stop_reserve_m()
                if dist_m + stop_reserve_m >= self.bootstrap_max_travel_m:
                    raise RuntimeError(
                        "HEADING_BOOTSTRAP_BUDGET_EXHAUSTED: stopping before configured "
                        "maximum travel"
                    )

                if time.monotonic() - _last_drive_t >= refresh_interval_s:
                    ok = await self._gateway_adapter.dispatch_drive_speeds(
                        self.bootstrap_speed_mps,
                        self.bootstrap_speed_mps,
                        heading_bootstrap=True,
                    )
                    if not ok:
                        raise RuntimeError("Heading bootstrap drive refresh rejected by gateway")
                    _last_drive_t = time.monotonic()
            else:
                raise RuntimeError(
                    f"Heading bootstrap failed: GPS COG not acquired within "
                    f"{_BOOTSTRAP_DEADLINE_S:.0f} s. "
                    "Check sky view and GPS lock before retrying."
                )
        finally:
            stop_confirmed = await self._deliver_stop_command(reason="heading bootstrap")
            alignment_committed = False
            if self._use_localization():
                alignment_committed = self._localization.end_bootstrap(
                    commit_alignment=completed and stop_confirmed
                )
            elif completed and stop_confirmed and self._bootstrap_alignment_staged:
                alignment_committed = self._save_alignment_to_disk("gps_cog_snap")
            if self._bootstrap_alignment_staged and not alignment_committed:
                self._session_heading_alignment = 0.0
                self._heading_alignment_sample_count = 0
                self._alignment_imu_epoch_id = None
                self._require_gps_heading_alignment = True
                self.navigation_state.heading = None
                self.navigation_state.heading_source = None
            self._bootstrap_start_time = None
            self._bootstrap_start_antenna_position = None
            self._bootstrap_initial_imu_yaw_deg = None
            self._bootstrap_alignment_staged = False
            await asyncio.sleep(0.3)
            if not stop_confirmed:
                reason = "STOP_CONFIRMATION_FAILED: heading bootstrap motor stop not acknowledged"
                self._latch_global_emergency_state(reason)
                try:
                    await self.emergency_stop(reason)
                except Exception:
                    logger.exception("Emergency stop escalation failed after bootstrap stop failure")
                raise RuntimeError(reason)
            if completed and not alignment_committed:
                raise RuntimeError(
                    "HEADING_ALIGNMENT_PERSISTENCE_FAILED: bootstrap evidence was not committed"
                )

    async def _refresh_bootstrap_sensor_state(self, manager: Any | None) -> None:
        """Refresh bootstrap inputs without allowing a slow GPS read to outlive a lease."""
        if manager is None:
            raise RuntimeError("sensor manager unavailable")
        if self._mission_execution_active:
            imu_interface = getattr(manager, "imu", None)
            self._record_live_imu_sample(getattr(imu_interface, "last_reading", None))
            return
        sensor_data = await manager.read_all_sensors(bootstrap_mode=True)
        if sensor_data is None:
            raise RuntimeError("sensor manager returned no bootstrap data")
        await self.update_navigation_state(sensor_data)

    def _record_live_imu_sample(self, imu: Any | None) -> None:
        yaw = getattr(imu, "yaw", None)
        received_mono = getattr(imu, "monotonic_received_s", None)
        imu_epoch_id = getattr(imu, "imu_epoch_id", None)
        epoch_changed = False
        if isinstance(imu_epoch_id, str) and imu_epoch_id.strip():
            epoch_changed = self._bind_live_imu_epoch(imu_epoch_id)
            if epoch_changed:
                self._latch_global_emergency_state(
                    "IMU_EPOCH_CHANGED: BNO085 reset invalidated heading alignment"
                )
        valid = (
            imu is not None
            and not epoch_changed
            and self._imu_epoch_is_current()
            and isinstance(yaw, (int, float))
            and math.isfinite(float(yaw))
            and getattr(imu, "calibration_status", None) != "uncalibrated"
            and not bool(getattr(imu, "cached", False))
            and isinstance(received_mono, (int, float))
            and math.isfinite(float(received_mono))
        )
        self.navigation_state.imu_valid = bool(valid)
        if valid:
            self._last_imu_monotonic_s = float(received_mono)
            self._last_imu_raw_yaw_deg = float(yaw)

    def assert_heading_bootstrap_ready(self) -> None:
        """Fail closed unless a bounded heading bootstrap fits inside the safe area."""
        snapshot = self.get_operating_area_snapshot()
        footprint_radius_m = float(getattr(self, "mower_footprint_radius_m", 0.35))
        fixed_allowance_m = float(getattr(self, "geofence_safety_allowance_m", 0.10))
        bootstrap_max_travel_m = float(getattr(self, "bootstrap_max_travel_m", 0.60))
        antenna_offset_m = math.hypot(
            self._gps_antenna_offset_forward_m,
            self._gps_antenna_offset_right_m,
        )
        position = self._raw_antenna_position_for_bootstrap()
        if position is None:
            raise RuntimeError("LOCALIZATION_STALE: raw GPS antenna position unavailable")
        accuracy_m = float(getattr(position, "accuracy", 0.0) or 0.0)
        try:
            snapshot.validate_ready_for_autonomy(
                position=position,
                last_gps_fix=self.navigation_state.last_gps_fix,
                dead_reckoning_active=self.navigation_state.dead_reckoning_active,
                max_fix_age_s=float(getattr(self, "autonomous_max_gps_fix_age_s", 2.0)),
                max_accuracy_m=float(getattr(self, "autonomous_max_gps_accuracy_m", 0.25)),
                footprint_radius_m=footprint_radius_m,
                fixed_allowance_m=fixed_allowance_m,
                bootstrap_clearance_m=(
                    footprint_radius_m
                    + fixed_allowance_m
                    + accuracy_m
                    + antenna_offset_m
                    + bootstrap_max_travel_m
                ),
            )
        except OperatingAreaError as exc:
            raise RuntimeError(f"{exc.reason_code}: {exc.detail}") from exc

    async def _run_bootstrap_and_check_geofence(self) -> None:
        """Run heading bootstrap then abort if mower is outside geofence boundary.

        Called once at mission start after reset. Raises RuntimeError and latches
        the global emergency state if the position is outside the safety boundary.
        """
        self.assert_heading_bootstrap_ready()

        await self._bootstrap_heading_from_gps_cog()

        snapshot = self.get_operating_area_snapshot()
        footprint_radius_m = float(getattr(self, "mower_footprint_radius_m", 0.35))
        fixed_allowance_m = float(getattr(self, "geofence_safety_allowance_m", 0.10))
        cur = self.navigation_state.current_position
        if cur is None or not snapshot.contains_footprint(
            cur,
            float(cur.accuracy or 0.0)
            + footprint_radius_m
            + fixed_allowance_m,
        ):
            self._latch_global_emergency_state("Bootstrap drive exited safe operating area")
            logger.error("Bootstrap drive exited safe operating area — mission aborted")
            raise RuntimeError("GEOFENCE_PREDICTION_BLOCKED: bootstrap exited safe area")

    async def _validate_reused_heading_and_geofence(self) -> None:
        """Validate a saved alignment for a blade-off diagnostic without moving."""
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if (
                self.navigation_state.current_position is not None
                and self.navigation_state.heading is not None
                and self.navigation_state.last_gps_fix is not None
                and self.navigation_state.imu_valid
                and self.navigation_state.heading_source == "imu"
            ):
                break
            await asyncio.sleep(0.05)

        snapshot = self.get_operating_area_snapshot()
        try:
            snapshot.validate_ready_for_autonomy(
                position=self.navigation_state.current_position,
                last_gps_fix=self.navigation_state.last_gps_fix,
                dead_reckoning_active=self.navigation_state.dead_reckoning_active,
                max_fix_age_s=float(getattr(self, "autonomous_max_gps_fix_age_s", 2.0)),
                max_accuracy_m=float(getattr(self, "autonomous_max_gps_accuracy_m", 0.25)),
                footprint_radius_m=float(getattr(self, "mower_footprint_radius_m", 0.35)),
                fixed_allowance_m=float(getattr(self, "geofence_safety_allowance_m", 0.10)),
            )
        except OperatingAreaError as exc:
            raise RuntimeError(f"{exc.reason_code}: {exc.detail}") from exc
        if (
            self.navigation_state.heading is None
            or not self.navigation_state.imu_valid
            or self.navigation_state.heading_source != "imu"
        ):
            raise RuntimeError(
                "HEADING_ALIGNMENT_REQUIRED: saved alignment did not produce a live IMU heading"
            )

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
                confirmed = await self._gateway_adapter.dispatch_drive_speeds(
                    0.0,
                    0.0,
                    require_hardware_ack=True,
                )
                if confirmed:
                    return True
                raise RuntimeError("safety gateway did not confirm controller stop")
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

    def _position_ready_for_bootstrap(self, position: Position | None) -> bool:
        """Return True when position quality is sufficient for a safe heading bootstrap."""
        if position is None:
            return False
        accuracy = position.accuracy
        if accuracy is None:
            return False
        return float(accuracy) <= float(self.bootstrap_required_accuracy_m)

    def _imu_ready_for_bootstrap(self) -> bool:
        """Return True only after the live localization owner accepted an IMU sample."""
        age_s = self._live_imu_age_s()
        max_age_s = max(0.05, float(self.autonomous_command_ttl_ms) / 1000.0)
        return bool(
            self.navigation_state.imu_valid
            and self._imu_epoch_is_current()
            and age_s is not None
            and age_s <= max_age_s
            and self._last_imu_raw_yaw_deg is not None
            and math.isfinite(self._last_imu_raw_yaw_deg)
        )

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

    def _latch_global_emergency_state(self, reason: str | None = None) -> None:
        """Mirror the control API emergency latch for non-HTTP emergency paths."""
        try:
            from ..control.commands import EmergencyTrigger
            from ..main import app

            gw = getattr(getattr(app.state, "runtime", None), "command_gateway", None)
            if gw is not None:
                asyncio.ensure_future(
                    gw.trigger_emergency(
                        EmergencyTrigger(reason=reason or "Navigation safety trigger", source="navigation")
                    )
                )
                return
        except Exception:
            pass

        # Legacy fallback when gateway unavailable (unit tests, early startup)
        try:
            from ..core.robot_state_manager import get_robot_state_manager
            get_robot_state_manager().set_emergency_stop(True, reason or "Navigation safety trigger")
            from ..core import globals as _g
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
            state = await _dispatch(sensor_data)
            self._update_gps_degradation_state()
            return state
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            observability.metrics.record_timer("navigation_tick_duration", duration_ms)

    def _update_gps_degradation_state(self) -> None:
        """Project canonical localization freshness into mission GPS policy."""
        if not self._mission_execution_active:
            return
        state = self.navigation_state
        fix_age_s = None
        if state.last_gps_fix is not None:
            fix = state.last_gps_fix
            if fix.tzinfo is None:
                fix = fix.replace(tzinfo=UTC)
            fix_age_s = max(0.0, (datetime.now(UTC) - fix).total_seconds())
        accuracy_m = (
            float(state.current_position.accuracy)
            if state.current_position is not None and state.current_position.accuracy is not None
            else None
        )
        snapshot = self.gps_degradation.update(
            position_available=state.current_position is not None,
            fix_age_s=fix_age_s,
            accuracy_m=accuracy_m,
            dead_reckoning_active=state.dead_reckoning_active,
        )
        state.gps_degradation_state = snapshot.state.value
        state.gps_degradation_reason = snapshot.reason
        state.gps_degradation_seconds = snapshot.degraded_for_s
        state.gps_speed_cap_mps = snapshot.speed_cap_mps
        if snapshot.state is GPSDegradationState.TERMINAL:
            state.target_velocity = 0.0

    async def _update_navigation_state_impl(self, sensor_data: SensorData) -> NavigationState:
        """Original update_navigation_state body — measured by the public wrapper."""

        imu_epoch_id = getattr(sensor_data.imu, "imu_epoch_id", None)
        if isinstance(imu_epoch_id, str) and imu_epoch_id.strip():
            epoch_changed = self._bind_live_imu_epoch(imu_epoch_id)
            if epoch_changed and self._mission_execution_active:
                reason = "IMU_EPOCH_CHANGED: BNO085 reset invalidated heading alignment"
                self._latch_global_emergency_state(reason)
                stop_confirmed = await self._deliver_stop_command(reason="IMU epoch change")
                if not stop_confirmed:
                    await self.emergency_stop(reason)
                raise RuntimeError(reason)

        if self._use_localization():
            # Delegate position, heading, GPS COG, dead reckoning, and quality to
            # LocalizationService. Mirror the results into NavigationState so all
            # callers of NavigationService see consistent data.
            loc_state = await self._localization.update(
                sensor_data,
                target_velocity=self.navigation_state.target_velocity,
            )
            self.navigation_state.current_position = loc_state.current_position
            self.navigation_state.heading = loc_state.heading
            self.navigation_state.gps_cog = loc_state.gps_cog
            self.navigation_state.velocity = loc_state.velocity
            self.navigation_state.imu_valid = bool(loc_state.imu_valid)
            self._last_imu_monotonic_s = loc_state.imu_received_monotonic_s
            self._last_imu_raw_yaw_deg = loc_state.imu_raw_yaw_deg
            self.navigation_state.heading_source = loc_state.heading_source
            self.navigation_state.pose_quality = loc_state.quality.value
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

            imu = sensor_data.imu
            imu_yaw = getattr(imu, "yaw", None)
            imu_valid = (
                imu is not None
                and isinstance(imu_yaw, (int, float))
                and math.isfinite(float(imu_yaw))
                and imu.calibration_status != "uncalibrated"
                and not bool(getattr(imu, "cached", False))
                and isinstance(getattr(imu, "monotonic_received_s", None), (int, float))
                and math.isfinite(float(imu.monotonic_received_s))
            )
            self.navigation_state.imu_valid = bool(imu_valid)
            imu_alignment_ready = (
                not self._require_gps_heading_alignment
                or self._heading_alignment_sample_count > 0
            )

            if imu_valid:
                raw_yaw = float(imu_yaw)
                received_mono = getattr(imu, "monotonic_received_s", None)
                self._last_imu_monotonic_s = float(received_mono)
                self._last_imu_raw_yaw_deg = raw_yaw
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
                    self.navigation_state.heading_source = "imu"
                    self._pose_filter.update_imu_heading(
                        adjusted_yaw,
                        quality=getattr(sensor_data.imu, 'calibration_status', None) or "calibrated"
                    )
                elif gps_cog is not None:
                    self.navigation_state.heading = gps_cog
                    self.navigation_state.heading_source = "gps_cog"
                else:
                    self.navigation_state.heading = None
                    self.navigation_state.heading_source = None

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
                            going_straight = max_dev < self._bootstrap_straight_tolerance_deg

                        if going_straight and self._heading_alignment_sample_count == 0:
                            # First stable bootstrap sample: snap immediately to GPS COG.
                            clamped_delta = max(-180.0, min(180.0, delta))
                            self._session_heading_alignment = (
                                self._session_heading_alignment + clamped_delta
                            ) % 360.0
                            self._heading_alignment_sample_count = 1
                            self._alignment_imu_epoch_id = self._active_imu_epoch_id
                            self._bootstrap_alignment_staged = True
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
                            logger.info(
                                "Heading alignment staged pending minimum travel and "
                                "confirmed motor stop"
                            )
            elif gps_cog is not None:
                # Use GPS course-over-ground as heading fallback while in motion.
                # GPS COG is already in world frame; IMU yaw_offset does NOT apply here.
                self.navigation_state.heading = gps_cog
                self.navigation_state.heading_source = "gps_cog"

        self.navigation_state.pose_quality = self._current_pose_quality()

        # Update obstacles
        obstacles = self.obstacle_detector.update_obstacles_from_sensors(
            sensor_data,
            commanded_speed_mps=self.navigation_state.target_velocity,
            origin_position=current_position,
            heading_deg=self.navigation_state.heading,
        )
        self.navigation_state.obstacle_map = obstacles

        # Check if obstacle avoidance is needed
        self.navigation_state.obstacle_avoidance_active = (
            self.obstacle_detector.has_active_obstacle
        )

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
        if self._operating_area_snapshot is not None and current_position is not None:
            try:
                self.navigation_state.boundary_clearance_m = (
                    self._operating_area_snapshot.distance_to_boundary(current_position)
                )
            except Exception:
                pass
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
            logger.error("Weather check failed closed: %s", e)
            return False

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
            epoch = data.get("imu_epoch_id")
            self._alignment_imu_epoch_id = (
                epoch.strip() if isinstance(epoch, str) and epoch.strip() else None
            )
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
            epoch = data.get("imu_epoch_id")
            self._alignment_imu_epoch_id = (
                epoch.strip() if isinstance(epoch, str) and epoch.strip() else None
            )
            logger.info(
                "IMU alignment loaded from disk: %.1f° (source=%s, samples=%d)",
                self._session_heading_alignment,
                source,
                samples,
            )
        except Exception as exc:
            logger.warning("Could not load IMU alignment file: %s", exc)
            self._session_heading_alignment = 0.0
            self._heading_alignment_sample_count = 0
            self._alignment_imu_epoch_id = None

    _ALIGNMENT_MAX_AGE_S: float = 24.0 * 3600.0  # 24 hours
    _ALIGNMENT_MAX_FUTURE_SKEW_S: float = 30.0
    _REUSABLE_ALIGNMENT_SOURCES = {"gps_cog_snap", "stop_navigation"}

    def _load_saved_alignment_for_mission_start(
        self,
    ) -> tuple[float, int, float] | None:
        """Return (value_deg, sample_count, age_s) if a valid saved alignment exists.

        Returns None when:
        - No saved alignment file / repository data exists.
        - The alignment is older than 24 hours (stale sensor drift risk).
        - The source is a non-authoritative bootstrap record
          ("mission_start_reset", "gps_cog_snap_fallback", or "gps_cog_snap_no_imu").

        Normal missions apply the value while still requiring a fresh GPS COG
        bootstrap. Explicit blade-off diagnostic legs may reuse it without
        repeated motion after fresh localization/geofence validation.
        """
        try:
            if self._calibration_repo is not None:
                data = self._calibration_repo.load_reusable_imu_alignment(
                    max_age_s=self._ALIGNMENT_MAX_AGE_S
                )
                if data is None:
                    return None
            else:
                if not self._ALIGNMENT_FILE.exists():
                    return None
                data = json.loads(self._ALIGNMENT_FILE.read_text())

            source = str(data.get("source", "default")).strip()
            if source not in self._REUSABLE_ALIGNMENT_SOURCES:
                return None

            last_updated_str = data.get("last_updated")
            if last_updated_str is None:
                return None
            try:
                last_updated = datetime.fromisoformat(last_updated_str)
            except ValueError:
                return None

            # Ensure tz-aware comparison
            now = datetime.now(UTC)
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=UTC)
            age_s = (now - last_updated).total_seconds()
            if age_s < -self._ALIGNMENT_MAX_FUTURE_SKEW_S:
                logger.warning("Mission start: saved alignment timestamp is in the future")
                return None
            if age_s > self._ALIGNMENT_MAX_AGE_S:
                logger.info(
                    "Mission start: saved alignment age %.0fs > %.0fs — discarding",
                    age_s,
                    self._ALIGNMENT_MAX_AGE_S,
                )
                return None

            value = float(data.get("session_heading_alignment", 0.0)) % 360.0
            if not math.isfinite(value):
                return None
            samples = int(data.get("sample_count", 0))
            return (value, samples, age_s)
        except Exception as exc:
            logger.warning("Could not check saved alignment for mission start: %s", exc)
            return None

    def has_reusable_heading_alignment(self) -> bool:
        """Return whether fresh authoritative heading evidence can be reused."""
        saved = self._load_saved_alignment_for_mission_start()
        return saved is not None and int(saved[1]) >= 1

    def _save_alignment_to_disk(self, source: str) -> bool:
        """Persist current session heading alignment to data/imu_alignment.json.

        Uses an atomic write (write to tmp then rename) to avoid partial files.
        Silently swallows errors so a filesystem issue never crashes navigation.

        When a CalibrationRepository is injected, delegates to it instead of
        writing the file directly.
        """
        if self._calibration_repo is not None:
            return bool(self._calibration_repo.save_imu_alignment(
                heading_deg=self._session_heading_alignment,
                sample_count=self._heading_alignment_sample_count,
                source=source,
                imu_epoch_id=self._alignment_imu_epoch_id,
            ))
        try:
            payload = {
                "session_heading_alignment": round(self._session_heading_alignment, 3),
                "sample_count": self._heading_alignment_sample_count,
                "source": source,
                "last_updated": datetime.now(UTC).isoformat(),
            }
            if self._alignment_imu_epoch_id is not None:
                payload["imu_epoch_id"] = self._alignment_imu_epoch_id
            tmp = self._ALIGNMENT_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2))
            tmp.replace(self._ALIGNMENT_FILE)
            logger.info(
                "IMU alignment saved: %.1f° (source=%s, samples=%d)",
                self._session_heading_alignment,
                source,
                self._heading_alignment_sample_count,
            )
            return True
        except Exception as exc:
            logger.warning("Could not save IMU alignment to disk: %s", exc)
            return False

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
        self._latch_global_emergency_state(reason)

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

    def build_return_home_waypoints(self) -> list[MissionWaypoint]:
        """Build a safe blade-off route for canonical MissionService execution."""
        current = self.navigation_state.current_position
        home = self.navigation_state.home_position
        if current is None:
            raise ValueError("RETURN_HOME_POSITION_UNAVAILABLE: current position is unknown")
        if home is None:
            raise ValueError("RETURN_HOME_NOT_CONFIGURED: home position is unknown")
        boundaries = self.navigation_state.safety_boundaries
        if not boundaries or len(boundaries[0]) < 3:
            raise ValueError("RETURN_HOME_SAFE_AREA_UNAVAILABLE: a valid boundary is required")

        planned = self.path_planner.return_to_base(
            current=current,
            home=home,
            boundary=boundaries[0],
            obstacles=self.navigation_state.no_go_zones or None,
        )
        if not planned:
            raise ValueError("RETURN_HOME_NO_SAFE_ROUTE: path planner found no safe route")

        mission_waypoints: list[MissionWaypoint] = []
        for index, waypoint in enumerate(planned):
            target_speed = waypoint.target_speed if waypoint.target_speed is not None else 0.3
            speed_pct = round(
                max(0.0, min(1.0, target_speed / max(0.01, self.max_speed))) * 100
            )
            leg_type = (
                MissionLegType.DOCK if index == len(planned) - 1 else MissionLegType.TRANSIT
            )
            mission_waypoints.append(
                MissionWaypoint(
                    lat=waypoint.position.latitude,
                    lon=waypoint.position.longitude,
                    blade_on=False,
                    leg_type=leg_type,
                    speed=speed_pct,
                    arrival_threshold_m=waypoint.tolerance,
                )
            )
        return mission_waypoints

    async def return_home(self) -> bool:
        """Reject the obsolete non-mission execution path.

        Callers must use ``MissionService.start_return_home`` so lifecycle,
        gateway authorization, blade state, and terminal truth share one owner.
        """
        logger.error("Direct NavigationService.return_home is disabled; use MissionService")
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

        The generated safe boundary file is preferred for autonomous operation.
        Confirmed map zones are a compatibility fallback only. Imported parcel
        helper geometry is intentionally not read here.

        Gracefully handles an empty repository (no zones saved) or a missing repository
        by leaving the boundary lists unchanged and logging a warning.
        """
        try:
            snapshot = self._load_operating_area_snapshot()
            if snapshot.valid:
                if snapshot.source == "simulation_zone_fallback" and self._map_repository is not None:
                    try:
                        zones = self._map_repository.list_zones()
                        boundaries: list[list[Position]] = []
                        exclusions: list[list[Position]] = []
                        for zone in zones:
                            points = []
                            for point in zone.get("polygon", []):
                                if isinstance(point, dict):
                                    lat = point.get("latitude", point.get("lat"))
                                    lon = point.get("longitude", point.get("lon", point.get("lng")))
                                    if lat is not None and lon is not None:
                                        points.append(Position(latitude=float(lat), longitude=float(lon)))
                                elif isinstance(point, (list, tuple)) and len(point) >= 2:
                                    points.append(Position(latitude=float(point[0]), longitude=float(point[1])))
                            if len(points) < 3:
                                continue
                            kind = str(zone.get("zone_kind") or "").lower()
                            if kind == "exclusion" or bool(zone.get("exclusion_zone", False)):
                                exclusions.append(points)
                            else:
                                boundaries.append(points)
                        self.navigation_state.safety_boundaries = boundaries
                        self.navigation_state.no_go_zones = exclusions
                    except Exception:
                        logger.debug("Failed to expand simulation zone fallback", exc_info=True)
                logger.info(
                    "Loaded operating area source=%s exclusions=%d buffer_m=%.2f",
                    snapshot.source,
                    len(snapshot.exclusions),
                    snapshot.buffer_meters,
                )
            else:
                if os.getenv("SIM_MODE", "0") == "1" and self._map_repository is not None:
                    try:
                        zones = self._map_repository.list_zones()
                        exclusions: list[list[Position]] = []
                        for zone in zones:
                            kind = str(zone.get("zone_kind") or "").lower()
                            if kind != "exclusion" and not bool(zone.get("exclusion_zone", False)):
                                continue
                            points = []
                            for point in zone.get("polygon", []):
                                if isinstance(point, dict):
                                    lat = point.get("latitude", point.get("lat"))
                                    lon = point.get("longitude", point.get("lon", point.get("lng")))
                                    if lat is not None and lon is not None:
                                        points.append(Position(latitude=float(lat), longitude=float(lon)))
                                elif isinstance(point, (list, tuple)) and len(point) >= 2:
                                    points.append(Position(latitude=float(point[0]), longitude=float(point[1])))
                            if len(points) >= 3:
                                exclusions.append(points)
                        self.navigation_state.no_go_zones = exclusions
                    except Exception:
                        logger.debug("Failed to load simulation exclusions", exc_info=True)
                logger.warning("Operating area unavailable: %s", snapshot.validity_state)
        except Exception:
            self.navigation_state.safety_boundaries = []
            self.navigation_state.no_go_zones = []
            self.navigation_state.operating_area_validity = "SAFE_BOUNDARY_REQUIRED"
            logger.warning("Failed to load operating-area snapshot", exc_info=True)

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
            "gps_degradation": self.gps_degradation.snapshot().to_dict(),
            "path_confidence": self.navigation_state.path_confidence,
            "pose_quality": pose.quality.value if pose else None,
            "pose_x_m": pose.x_m if pose else None,
            "pose_y_m": pose.y_m if pose else None,
            "pose_heading_deg": pose.heading_deg if pose else None,
        }
