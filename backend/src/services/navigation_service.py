"""
NavigationService for LawnBerry Pi v2
Path planning, navigation, and sensor fusion with safety constraints
"""

import asyncio
import json
import logging
import math
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.config_loader import ConfigLoader
from ..nav.geoutils import haversine_m, point_in_polygon
from ..nav.path_planner import PathPlanner
from ..models import (
    NavigationMode,
    NavigationState,
    Obstacle,
    PathStatus,
    Position,
    SensorData,
    Waypoint,
)
from .robohat_service import get_robohat_service

logger = logging.getLogger(__name__)


## Path planning moved to backend.src.nav.path_planner.PathPlanner


class ObstacleDetector:
    """Obstacle detection and avoidance"""
    
    def __init__(self, safety_distance: float = 0.2):
        self.safety_distance = safety_distance
        self.detected_obstacles: List[Obstacle] = []
    
    def update_obstacles_from_sensors(self, sensor_data: SensorData) -> List[Obstacle]:
        """Update obstacle list from sensor data"""
        obstacles = []
        obstacle_id_counter = 0
        threshold_mm = max(0.0, float(self.safety_distance) * 1000.0)
        
        # ToF sensor obstacles
        if sensor_data.tof_left and sensor_data.tof_left.distance is not None:
            if float(sensor_data.tof_left.distance) <= threshold_mm:
                obstacles.append(Obstacle(
                    id=f"tof_left_{obstacle_id_counter}",
                    position=Position(latitude=0, longitude=0),  # Relative position
                    confidence=0.8,
                    obstacle_type="static",
                    detection_source="tof"
                ))
                obstacle_id_counter += 1
        
        if sensor_data.tof_right and sensor_data.tof_right.distance is not None:
            if float(sensor_data.tof_right.distance) <= threshold_mm:
                obstacles.append(Obstacle(
                    id=f"tof_right_{obstacle_id_counter}",
                    position=Position(latitude=0, longitude=0),  # Relative position
                    confidence=0.8,
                    obstacle_type="static",
                    detection_source="tof"
                ))
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
        self.last_gps_position: Optional[Position] = None
        self.last_gps_time: Optional[datetime] = None
        self.estimated_position: Optional[Position] = None
        self.drift_estimate: float = 0.0
        self.active = False
    
    def update_gps_reference(self, gps_position: Position):
        """Update GPS reference for dead reckoning"""
        self.last_gps_position = gps_position
        self.last_gps_time = datetime.now(timezone.utc)
        self.estimated_position = gps_position
        self.active = False
        self.drift_estimate = 0.0
    
    def estimate_position(self, heading: float, distance_traveled: float) -> Optional[Position]:
        """Estimate current position using dead reckoning"""
        if not self.last_gps_position:
            # Initialize a local frame at origin if no GPS reference exists yet.
            # This enables dead-reckoning operation even before first GPS fix.
            self.last_gps_position = Position(latitude=0.0, longitude=0.0, accuracy=10.0)
            self.last_gps_time = datetime.now(timezone.utc)
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
            accuracy=max(3.0, distance_traveled * 0.1)  # Increasing uncertainty
        )
        
        # Update drift estimate
        time_since_gps = (datetime.now(timezone.utc) - self.last_gps_time).total_seconds()
        self.drift_estimate = min(distance_traveled * 0.05, time_since_gps * 0.1)
        
        return self.estimated_position


class NavigationService:
    """Main navigation service with sensor fusion and path planning"""
    
    def __init__(self, weather=None):
        self.navigation_state = NavigationState()
        self.path_planner = PathPlanner()
        self.dead_reckoning = DeadReckoningSystem()
        # Optional weather service with get_current() and get_planning_advice()
        self.weather = weather
        
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

        try:
            hardware, limits = ConfigLoader().get()
            self.obstacle_avoidance_distance = float(limits.tof_obstacle_distance_meters)
            self._imu_yaw_offset: float = float(getattr(hardware, "imu_yaw_offset_degrees", 0.0))
            if self._imu_yaw_offset != 0.0:
                logger.info(
                    "IMU yaw offset loaded: %.1f° (applied as: adjusted = (-raw + offset) %% 360)",
                    self._imu_yaw_offset,
                )
        except Exception as exc:
            self._imu_yaw_offset = 0.0
            logger.warning(
                "Failed to load navigation config from hardware/safety limits: %s",
                exc,
            )

        self.obstacle_detector = ObstacleDetector(self.obstacle_avoidance_distance)
        
        # State tracking
        self.total_distance = 0.0
        self.last_position: Optional[Position] = None
        self._mission_execution_active = False
        
        # Progressive stiffness detection for stuck motor diagnosis
        self._stiffness_test_active = False
        self._stiffness_test_start_time: Optional[float] = None
        self._stiffness_test_effort = 0.1  # Start with 10% turn effort
        self._stiffness_test_effort_step = 0.05  # Increase by 5% every step
        self._stiffness_test_max_effort = 1.0  # Max 100% turn effort
        self._stiffness_test_stuck_threshold = 0.3  # Heading change < 0.3° in 2 seconds = stuck
        self._stiffness_test_direction: str = "left"
        self._stiffness_test_last_heading: Optional[float] = None
        self._stiffness_test_last_check: Optional[float] = None

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
        self._load_alignment_from_disk()

    _instance: Optional["NavigationService"] = None

    @classmethod
    def get_instance(cls, weather=None) -> "NavigationService":
        if cls._instance is None:
            cls._instance = NavigationService(weather=weather)
        return cls._instance
        
    async def initialize(self) -> bool:
        """Initialize navigation service"""
        logger.info("Initializing navigation service")
        self.navigation_state.navigation_mode = NavigationMode.IDLE
        return True
    
    async def execute_mission(self, mission: "Mission"):
        """Execute a mission by navigating to each waypoint."""
        from .mission_service import get_mission_service
        mission_service = get_mission_service()

        logger.info(f"Starting mission execution: {mission.id} - {mission.name}")
        self.navigation_state.navigation_mode = NavigationMode.AUTO
        self.navigation_state.path_status = PathStatus.EXECUTING
        
        # Convert MissionWaypoints to Navigation Waypoints
        self.navigation_state.planned_path = [
            Waypoint(
                position=Position(latitude=wp.lat, longitude=wp.lon), 
                target_speed=(wp.speed / 100.0 * self.max_speed)
            )
            for wp in mission.waypoints
        ]

        status = mission_service.mission_statuses.get(mission.id)
        requested_index = status.current_waypoint_index if status else 0
        max_index = max(0, len(self.navigation_state.planned_path) - 1)
        self.navigation_state.current_waypoint_index = max(0, min(requested_index or 0, max_index))
        self.navigation_state.operation_start_time = datetime.now(timezone.utc)
        self._mission_execution_active = True

        # Reset heading alignment for each mission so the bootstrap drive gets a
        # clean GPS COG snap.  IMU Game Rotation Vector yaw is relative to boot
        # orientation and must be re-calibrated before the first tank turn.
        self._session_heading_alignment = 0.0
        self._heading_alignment_sample_count = 0
        self._gps_cog_history.clear()
        self._save_alignment_to_disk("mission_start_reset")
        await self._bootstrap_heading_from_gps_cog()

        # Load yard boundary from map zones so geofence enforcement is active for this mission
        self._load_boundaries_from_zones()

        try:
            while self.navigation_state.current_waypoint_index < len(self.navigation_state.planned_path):
                status = mission_service.mission_statuses.get(mission.id)
                if not status:
                    logger.warning(f"Mission {mission.id} interrupted. Status: {status.status if status else 'N/A'}")
                    self.navigation_state.path_status = PathStatus.INTERRUPTED
                    self.navigation_state.navigation_mode = NavigationMode.IDLE
                    return

                if status.status == "paused":
                    self.navigation_state.navigation_mode = NavigationMode.PAUSED
                    await self._deliver_stop_command(reason="mission pause hold")
                    await asyncio.sleep(0.1)
                    continue

                if status.status != "running":
                    logger.warning(f"Mission {mission.id} interrupted. Status: {status.status}")
                    self.navigation_state.path_status = PathStatus.INTERRUPTED
                    self.navigation_state.navigation_mode = NavigationMode.IDLE
                    await self._deliver_stop_command(reason="mission interruption")
                    return

                if self.navigation_state.navigation_mode != NavigationMode.AUTO:
                    self.navigation_state.navigation_mode = NavigationMode.AUTO

                current_mission_waypoint = mission.waypoints[self.navigation_state.current_waypoint_index]
                waypoint_reached = await self.go_to_waypoint(mission, current_mission_waypoint)
                if not waypoint_reached:
                    status = mission_service.mission_statuses.get(mission.id)
                    if not status or status.status != "running":
                        self.navigation_state.path_status = PathStatus.INTERRUPTED
                        self.navigation_state.navigation_mode = NavigationMode.IDLE
                        return
                else:
                    mission_service._sync_status_with_navigation(mission.id)

                # The go_to_waypoint method is blocking until the waypoint is reached or interrupted.
                # The loop will then proceed to the next waypoint.
                # We add a small sleep to prevent a tight loop if go_to_waypoint returns immediately.
                await asyncio.sleep(0.1)

            if self.navigation_state.navigation_mode == NavigationMode.AUTO:
                self.navigation_state.path_status = PathStatus.COMPLETED
                self.navigation_state.navigation_mode = NavigationMode.IDLE
                logger.info(f"Mission {mission.id} completed.")
        except Exception:
            self.navigation_state.target_velocity = 0.0
            self.navigation_state.path_status = PathStatus.FAILED
            if self.navigation_state.navigation_mode != NavigationMode.EMERGENCY_STOP:
                self.navigation_state.navigation_mode = NavigationMode.IDLE
                stop_confirmed = await self._deliver_stop_command(reason="mission failure")
                if not stop_confirmed:
                    logger.error("Mission %s failed and stop delivery could not be confirmed", mission.id)
            raise
        finally:
            self._mission_execution_active = False

    async def go_to_waypoint(self, mission: "Mission", waypoint: "MissionWaypoint") -> bool:
        """Navigate to a single waypoint and block until arrival."""
        from .mission_service import get_mission_service
        mission_service = get_mission_service()
        
        target_pos = Position(latitude=waypoint.lat, longitude=waypoint.lon)
        logger.info(f"Navigating to waypoint: {target_pos.latitude}, {target_pos.longitude}")

        # Engage/disengage blade for this leg when hardware is available
        try:
            if os.getenv("SIM_MODE", "0") == "0":
                robohat = get_robohat_service()
                if robohat is not None and robohat.running and robohat.status.serial_connected:
                    await robohat.send_blade_command(bool(waypoint.blade_on))
        except Exception:
            # Blade command failures should not abort navigation
            logger.warning("Blade command failed or unavailable; continuing movement")

        verification_wait_start = time.monotonic()
        heading_wait_start: float | None = None
        obstacle_wait_start: float | None = None
        _last_nav_log: float = 0.0
        # Stall detection: ramp up motor power when heading isn't changing
        _stall_start: float | None = None
        _stall_heading: float | None = None
        # Hysteresis: prevent TANK/BLEND mode flapping near the 60° boundary.
        # Enter TANK when |error| > 70°, exit TANK when |error| < 50°.
        _in_tank_mode: bool = False
        # Tank-turn watchdog: abort the waypoint if we spend too long in pure-rotation
        # mode without converging.  Motor EMI on the IMU magnetometer can cause heading
        # to oscillate indefinitely; this guard prevents eternal spinning.
        _tank_turn_start: float | None = None
        _TANK_TURN_TIMEOUT_S: float = 30.0
        # "Definitely stuck" detector: if stall boost is maxed AND heading is
        # still frozen, the mower is mechanically stuck — abort cleanly.
        _stall_max_start: float | None = None
        # Grace period for motor controller USB reconnect.  When the controller
        # is transiently unavailable (USB disconnect / replug), the loop continues
        # checking safety gates rather than failing immediately.  After
        # _MOTOR_RECONNECT_GRACE_S seconds with no recovery, the mission fails.
        _motor_unavail_start: float | None = None
        _MOTOR_RECONNECT_GRACE_S: float = 20.0

        while True:
            status = mission_service.mission_statuses.get(mission.id)
            if not status:
                logger.info("Waypoint navigation interrupted: mission status missing.")
                await self._deliver_stop_command(reason="missing mission status")
                return False

            if status.status == "paused":
                self.navigation_state.navigation_mode = NavigationMode.PAUSED
                await self._deliver_stop_command(reason="mission pause hold")
                await asyncio.sleep(0.1)
                continue

            if status.status != "running":
                logger.info("Waypoint navigation interrupted.")
                await self._deliver_stop_command(reason="mission status change")
                return False

            if self._global_emergency_active():
                logger.critical("Waypoint navigation blocked by active emergency stop latch")
                await self._deliver_stop_command(reason="global emergency hold")
                self.navigation_state.navigation_mode = NavigationMode.EMERGENCY_STOP
                return False

            if not self.navigation_state.current_position:
                heading_wait_start = None
                obstacle_wait_start = None
                if (time.monotonic() - verification_wait_start) >= self.position_verification_timeout_seconds:
                    await self._deliver_stop_command(reason="position acquisition timeout")
                    emergency_ok = await self.emergency_stop(reason="GPS position unavailable for 30 s")
                    raise RuntimeError(
                        "Position acquisition timeout while navigating waypoint"
                        + ("; emergency stop activated" if emergency_ok else "")
                    )
                await asyncio.sleep(0.5)
                continue

            if not self._position_is_verified_for_waypoint():
                heading_wait_start = None
                obstacle_wait_start = None
                self.navigation_state.target_velocity = 0.0
                await self._deliver_stop_command(reason="position verification hold")
                if (time.monotonic() - verification_wait_start) >= self.position_verification_timeout_seconds:
                    emergency_ok = await self.emergency_stop(reason="GPS accuracy too low for 30 s")
                    raise RuntimeError(
                        "Position verification timeout while navigating waypoint"
                        + ("; emergency stop activated" if emergency_ok else "")
                    )
                await asyncio.sleep(0.2)
                continue

            verification_wait_start = time.monotonic()

            distance_to_target = self.path_planner.calculate_distance(
                self.navigation_state.current_position,
                target_pos
            )

            if distance_to_target <= self.waypoint_tolerance:
                logger.info(f"Waypoint reached: {waypoint.lat}, {waypoint.lon}")
                stop_confirmed = await self._deliver_stop_command(reason="waypoint arrival")
                if not stop_confirmed:
                    raise RuntimeError("Failed to stop safely at waypoint")
                if self.navigation_state.advance_waypoint():
                    logger.info(f"Advanced to next waypoint index: {self.navigation_state.current_waypoint_index}")
                else:
                    logger.info("Final waypoint in path reached.")
                return True

            if self.navigation_state.obstacle_avoidance_active and not self.obstacle_detector.is_path_clear(
                self.navigation_state.current_position,
                target_pos,
            ):
                heading_wait_start = None
                if obstacle_wait_start is None:
                    obstacle_wait_start = time.monotonic()
                    logger.warning("Obstacle detected while navigating to waypoint; holding position")
                await self._deliver_stop_command(reason="obstacle hold")
                if (time.monotonic() - obstacle_wait_start) >= self.position_verification_timeout_seconds:
                    raise RuntimeError(
                        "Obstacle persisted inside navigation safety distance "
                        f"({self.obstacle_avoidance_distance:.2f} m) while navigating waypoint"
                    )
                await asyncio.sleep(0.2)
                continue
            obstacle_wait_start = None

            # Geofence enforcement: stop and return to boundary if outside mowing area
            if self.navigation_state.safety_boundaries and self.navigation_state.current_position:
                outer_boundary = self.navigation_state.safety_boundaries[0]
                polygon = [(p.latitude, p.longitude) for p in outer_boundary]
                cur = self.navigation_state.current_position
                if not point_in_polygon(cur.latitude, cur.longitude, polygon):
                    await self._deliver_stop_command(reason="outside geofence boundary")
                    nearest = self._nearest_boundary_point(cur, outer_boundary)
                    logger.warning(
                        "Mower outside geofence boundary at (%.6f, %.6f); returning to boundary (%.6f, %.6f)",
                        cur.latitude, cur.longitude, nearest.latitude, nearest.longitude,
                    )
                    target_pos = nearest
                    continue

            # Calculate heading and apply motor commands
            heading_to_target = self.path_planner.calculate_bearing(
                self.navigation_state.current_position,
                target_pos
            )
            
            current_heading = self.navigation_state.heading
            _in_heading_bootstrap = current_heading is None
            if current_heading is None:
                # No heading from IMU or GPS COG yet.  Bootstrap by assuming we face
                # the target so the mower starts moving; GPS COG will take over once
                # speed >= 0.3 m/s.  E-stop is intentionally NOT triggered here — a
                # missing heading source is a navigation limitation, not a safety
                # emergency.  The mission will be aborted cleanly if heading never arrives.
                if heading_wait_start is None:
                    heading_wait_start = time.monotonic()
                    logger.warning(
                        "No heading data available; assuming bearing %.1f° to target to start motion.",
                        heading_to_target,
                    )
                if (time.monotonic() - heading_wait_start) >= self.position_verification_timeout_seconds:
                    await self._deliver_stop_command(reason="heading unavailable — mission aborted")
                    raise RuntimeError("Heading unavailable while navigating waypoint; mission aborted")
                current_heading = heading_to_target
            else:
                heading_wait_start = None

            heading_error = (heading_to_target - current_heading + 180) % 360 - 180
            
            # DEBUG: Log heading control every 2 seconds
            _now = time.monotonic()
            if _now - _last_nav_log > 2.0:
                logger.info(
                    "NAV_CONTROL: target_bearing=%.1f° current_heading=%.1f° error=%.1f° | "
                    "tank_mode=%s in_turn=%s",
                    heading_to_target, current_heading, heading_error,
                    _in_tank_mode, (abs(heading_error) > 10),
                )
                _last_nav_log = _now

            # --- Stall detection: if heading barely changes while we command a
            # turn, progressively boost motor power to overcome grass/friction.
            _stall_boost = 0.0
            if abs(heading_error) > 20:
                if _stall_start is None:
                    _stall_start = time.monotonic()
                    _stall_heading = current_heading
                else:
                    _hdg_delta = abs(((current_heading - (_stall_heading or 0)) + 180) % 360 - 180)
                    if _hdg_delta < 5.0:
                        # Heading barely moved — ramp up 15% per second, cap at +60%
                        _stall_boost = min(0.6, (time.monotonic() - _stall_start) * 0.15)
                        # "Definitely stuck": boost is maxed and heading still frozen
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
                        # Heading is changing — reset stall tracker
                        _stall_start = time.monotonic()
                        _stall_heading = current_heading
                        _stall_max_start = None
            else:
                _stall_start = None
                _stall_heading = None
                _stall_max_start = None

            # Set speed (scale by waypoint speed preference when provided)
            base_speed = self.cruise_speed
            try:
                if hasattr(waypoint, "speed") and isinstance(waypoint.speed, int):
                    base_speed = max(0.1, min(self.max_speed, (waypoint.speed / 100.0) * self.max_speed))
            except Exception:
                base_speed = self.cruise_speed

            # --- Motor command strategy depends on heading error magnitude ---
            abs_err = abs(heading_error)
            turn_sign = 1.0 if heading_error > 0 else -1.0

            # Hysteresis: enter TANK at >70°, exit at <50° to prevent mode flapping.
            if abs_err > 70:
                _in_tank_mode = True
            elif abs_err < 50:
                _in_tank_mode = False

            if _in_tank_mode:
                # Tank-turn watchdog: heading should converge within the timeout.
                # EMI from motor windings can corrupt the BNO085 magnetometer and
                # cause the heading to oscillate without ever settling on target.
                if _tank_turn_start is None:
                    _tank_turn_start = time.monotonic()
                elif (time.monotonic() - _tank_turn_start) > _TANK_TURN_TIMEOUT_S:
                    logger.error(
                        "Tank-turn watchdog: heading not converging after %.0f s "
                        "(last err=%.1f°, hdg=%.1f°) — aborting waypoint",
                        _TANK_TURN_TIMEOUT_S,
                        heading_error,
                        current_heading,
                    )
                    await self._deliver_stop_command(reason="tank-turn timeout")
                    raise RuntimeError(
                        f"Tank-turn timed out after {_TANK_TURN_TIMEOUT_S:.0f} s "
                        "without heading convergence"
                    )

                # TANK TURN: counter-rotate wheels in place to point toward
                # the waypoint.  One-wheel turns can't overcome grass friction.
                # Sign convention: turn_sign > 0 means we need CW (right).
                # Note: 2026-04-20 motor direction inversion fix - left/right are swapped at motor driver,
                # so we swap the assignment here to match blended mode.
                turn_speed = min(self.max_speed, 0.5 + _stall_boost)
                right_speed = turn_sign * turn_speed
                left_speed = -turn_sign * turn_speed
            else:
                _tank_turn_start = None  # reset watchdog when no longer in tank mode
                # BLENDED: proportional turn with forward movement.
                # Note: 2026-04-20 motor direction inversion fix - left/right are swapped
                # at the motor driver level, so we compute right_speed and left_speed in opposite order.
                turn_effort = max(-1.0, min(1.0, heading_error / 45.0))
                forward_speed = base_speed
                # Gentle taper: full speed at 0°, 70% at 60°
                if abs_err > 10:
                    taper = max(0.7, 1.0 - abs_err / 200.0)
                    forward_speed *= taper

                # During heading bootstrap, enforce minimum forward speed so GPS
                # COG activates quickly (COG gate is 0.3 m/s; 0.4 m/s for margin).
                if _in_heading_bootstrap:
                    forward_speed = max(forward_speed, 0.4)

                # Floor so motor controller dead zone is always overcome
                forward_speed = max(forward_speed, 0.3)

                # SWAPPED: Due to motor wiring, send left commands to right and vice versa
                right_speed = forward_speed + turn_effort * forward_speed
                left_speed = forward_speed - turn_effort * forward_speed

                # In thick grass single-wheel pivots (one wheel stopped) cause
                # bogging.  Ensure both wheels keep at least 20% forward speed.
                _inner_min = forward_speed * 0.2
                if turn_effort > 0:   # CW turn — right is inner wheel (now left due to swap)
                    left_speed = max(left_speed, _inner_min)
                elif turn_effort < 0:  # CCW turn — left is inner wheel (now right due to swap)
                    right_speed = max(right_speed, _inner_min)

            # Clamp speeds
            left_speed = max(-self.max_speed, min(self.max_speed, left_speed))
            right_speed = max(-self.max_speed, min(self.max_speed, right_speed))

            # Motor controller availability check with grace-period reconnect.
            # When the controller is unavailable (USB drop), the loop continues
            # iterating — all safety gates above keep running — while the RoboHAT
            # service attempts to reconnect in the background.  The firmware's
            # serial-timeout (~5 s) will stop the physical motors if commands
            # stop arriving.  After _MOTOR_RECONNECT_GRACE_S the mission fails.
            if os.getenv("SIM_MODE", "0") != "1":
                _robohat_chk = get_robohat_service()
                _ctrl_ok = (
                    _robohat_chk is not None
                    and _robohat_chk.running
                    and _robohat_chk.status.serial_connected
                )
                if not _ctrl_ok:
                    if _motor_unavail_start is None:
                        _motor_unavail_start = time.monotonic()
                        logger.warning(
                            "Motor controller unavailable during navigation; "
                            "waiting up to %.0f s for reconnect "
                            "(firmware serial-timeout will stop motors ~5 s)",
                            _MOTOR_RECONNECT_GRACE_S,
                        )
                    if time.monotonic() - _motor_unavail_start >= _MOTOR_RECONNECT_GRACE_S:
                        logger.error(
                            "Motor controller still unavailable after %.0f s grace period; "
                            "aborting waypoint",
                            _MOTOR_RECONNECT_GRACE_S,
                        )
                        raise RuntimeError(
                            "Motor controller unavailable: failed to reconnect "
                            f"within {_MOTOR_RECONNECT_GRACE_S:.0f} s grace period"
                        )
                    await asyncio.sleep(0.2)
                    continue  # loop back; all safety gates re-run each iteration
                else:
                    _motor_unavail_start = None  # reset on confirmed controller presence

            # Retry transient motor command failures (e.g. single PWM ack timeout)
            # before aborting the mission.
            _motor_attempts = 3
            _motor_last_exc: Exception | None = None
            for _attempt in range(1, _motor_attempts + 1):
                try:
                    await self.set_speed(left_speed, right_speed)
                    _motor_last_exc = None
                    break
                except Exception as e:
                    _motor_last_exc = e
                    logger.warning(
                        "Motor command attempt %d/%d failed: %s",
                        _attempt,
                        _motor_attempts,
                        e,
                    )
                    if _attempt < _motor_attempts:
                        await asyncio.sleep(0.15)
            if _motor_last_exc is not None:
                logger.error("All %d motor command attempts failed: %s", _motor_attempts, _motor_last_exc)
                await self._deliver_stop_command(reason="navigation command failure")
                raise RuntimeError("Failed to deliver navigation motor command") from _motor_last_exc

            # Periodic navigation progress log (~every 5 s)
            _now = time.monotonic()
            if (_now - _last_nav_log) >= 5.0:
                _last_nav_log = _now
                _mode = "TANK" if _in_tank_mode else "BLEND"
                logger.info(
                    "NAV %s → wp(%.6f,%.6f) dist=%.1fm hdg=%.1f° err=%.1f° spd=L%.2f/R%.2f boost=%.0f%%",
                    _mode,
                    target_pos.latitude,
                    target_pos.longitude,
                    distance_to_target,
                    current_heading if current_heading is not None else -1,
                    heading_error,
                    left_speed,
                    right_speed,
                    _stall_boost * 100,
                )

            # Control loop at 5Hz
            await asyncio.sleep(0.2)

        return False

    async def set_speed(self, left_speed: float, right_speed: float) -> None:
        """Drive command helper integrating with the RoboHAT controller.

        - Accepts normalized wheel speeds in m/s-like units scaled to [-1, 1].
        - In SIM_MODE, updates state without touching hardware.
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

        accepted = await robohat.send_motor_command(_normalize(rs), _normalize(ls), ack_timeout=1.0)
        if not accepted:
            raise RuntimeError("Motor command not accepted by controller")

    async def _bootstrap_heading_from_gps_cog(self) -> None:
        """Drive briefly forward so GPS COG snaps the heading alignment.

        IMU Game Rotation Vector yaw is relative to boot orientation (arbitrary zero).
        This method drives at ~75% throttle for up to 3 seconds.  As soon as
        update_navigation_state() fires the GPS COG snap (sample_count 0→1), motion
        stops and the alignment is correct for the mission.

        If GPS COG is not available within 3 s the method logs a warning and returns
        without calibrating — the mission loop will attempt to use whatever heading
        data is available.
        """
        logger.info("Heading bootstrap: driving forward to acquire GPS COG snap...")
        deadline = time.monotonic() + 3.0
        try:
            await self.set_speed(0.6, 0.6)
            while time.monotonic() < deadline:
                await asyncio.sleep(0.2)
                if self._global_emergency_active():
                    logger.warning("Heading bootstrap aborted: emergency stop active")
                    return
                if self._heading_alignment_sample_count >= 1:
                    logger.info(
                        "Heading bootstrap complete: session_align=%.1f°",
                        self._session_heading_alignment,
                    )
                    break
            else:
                logger.warning(
                    "Heading bootstrap: GPS COG not available in 3 s — "
                    "proceeding with uncalibrated heading"
                )
        finally:
            await self._deliver_stop_command(reason="heading bootstrap")
            await asyncio.sleep(0.3)

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
        last_fix = self.navigation_state.last_gps_fix
        if last_fix is None:
            return False
        return (datetime.now(timezone.utc) - last_fix).total_seconds() <= self.max_waypoint_fix_age_seconds

    def _position_is_verified_for_waypoint(self) -> bool:
        """Return True when position data is trustworthy enough to advance a waypoint."""
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
        """Return True when API-level emergency stop is currently latched."""
        try:
            from ..api import rest as rest_api

            return bool(rest_api._safety_state.get("emergency_stop_active", False))
        except Exception:
            return False

    def _latch_global_emergency_state(self) -> None:
        """Mirror the control API emergency latch for non-HTTP emergency paths."""
        try:
            from ..api import rest as rest_api

            rest_api._safety_state["emergency_stop_active"] = True
            rest_api._blade_state["active"] = False
            rest_api._legacy_motors_active = False
            rest_api._emergency_until = time.time() + 0.2
        except Exception:
            logger.debug("Unable to mirror global emergency state from navigation service", exc_info=True)
    
    async def update_navigation_state(self, sensor_data: SensorData) -> NavigationState:
        """Update navigation state with sensor fusion"""
        
        # Update position from GPS or dead reckoning
        current_position = await self._update_position(sensor_data)
        if current_position:
            self.navigation_state.current_position = current_position

        # Update heading: prefer IMU yaw, fall back to GPS course-over-ground when moving.
        # Reject IMU placeholder value (yaw=0.0 with calibration_status="uncalibrated")
        # so stale defaults don't corrupt the navigation heading controller.
        imu_valid = (
            sensor_data.imu is not None
            and sensor_data.imu.yaw is not None
            and sensor_data.imu.calibration_status != "uncalibrated"
        )
        if imu_valid:
            raw_yaw = float(sensor_data.imu.yaw)  # type: ignore[union-attr]
            # BNO085 Game Rotation Vector uses ZYX aerospace convention (right-hand, z-up):
            # positive yaw = CCW rotation (counter-clockwise when viewed from above).
            # Navigation uses compass convention: North=0°, East=90°, South=180°, West=270°.
            # Compass convention is CW-positive (clockwise: North→East→South→West).
            # These rotational directions are OPPOSITE, so negate raw_yaw to convert.
            # Then apply yaw_offset for mechanical mounting (e.g., IMU rotated in enclosure).
            adjusted_yaw = (-raw_yaw + self._imu_yaw_offset + self._session_heading_alignment) % 360.0

            # Log raw and adjusted yaw for diagnostic purposes
            _log_imu_now = time.monotonic()
            if _log_imu_now - getattr(self, '_last_imu_log', 0) > 5.0:
                logger.info(
                    "IMU heading: raw_zyx=%.1f° adjusted_compass=%.1f° mounting_offset=%.1f° session_align=%.1f°",
                    raw_yaw, adjusted_yaw, self._imu_yaw_offset, self._session_heading_alignment,
                )
                self._last_imu_log = _log_imu_now
            
            # Glitch rejection: extreme motor vibration can cause momentary gyroscope spikes.
            # Max realistic turn rate: max_speed (0.8 m/s) × 2 / wheel_base (0.5 m) ≈ 183°/s.
            # At 5 Hz updates that is ≈37°/update; reject any jump larger than 60° as a
            # gyroscope glitch so it never corrupts the navigation heading controller.
            prev_heading = self.navigation_state.heading
            if prev_heading is not None:
                jump = abs(((adjusted_yaw - prev_heading) + 180.0) % 360.0 - 180.0)
                if jump > 60.0:
                    logger.debug(
                        "IMU heading outlier rejected: prev=%.1f° new=%.1f° (Δ=%.1f°) — "
                        "keeping previous value",
                        prev_heading, adjusted_yaw, jump,
                    )
                    # Don't update — keep the previous heading value
                else:
                    self.navigation_state.heading = adjusted_yaw
            else:
                self.navigation_state.heading = adjusted_yaw
            # GPS COG comparison and session heading alignment update
            gps_cog_available = (
                sensor_data.gps is not None
                and sensor_data.gps.heading is not None
                and (sensor_data.gps.speed or 0.0) >= 0.3
            )
            if gps_cog_available:
                cog = float(sensor_data.gps.heading)  # type: ignore[union-attr]
                # delta = how much alignment needs to increase (positive = IMU reads too low)
                delta = (cog - adjusted_yaw + 180.0) % 360.0 - 180.0
                logger.debug(
                    "HDG: raw_imu=%.1f° adjusted=%.1f° gps_cog=%.1f° delta=%.1f° session_align=%.1f°",
                    raw_yaw, adjusted_yaw, cog, delta, self._session_heading_alignment,
                )
                if abs(delta) > 45.0 and self._heading_alignment_sample_count < 10:
                    logger.warning(
                        "HDG mismatch: adjusted IMU=%.1f° vs GPS COG=%.1f° (delta=%.1f°) — "
                        "session alignment converging (samples=%d)",
                        adjusted_yaw, cog, delta, self._heading_alignment_sample_count,
                    )

                # Track GPS COG stability for straight-motion detection.
                # Alignment is only valid when GPS COG is stable (not turning).
                self._gps_cog_history.append(cog)
                if len(self._gps_cog_history) > 5:
                    self._gps_cog_history.pop(0)

                going_straight = False
                if len(self._gps_cog_history) >= 3:
                    sin_c = sum(math.sin(math.radians(c)) for c in self._gps_cog_history)
                    cos_c = sum(math.cos(math.radians(c)) for c in self._gps_cog_history)
                    cog_mean = math.degrees(math.atan2(sin_c, cos_c))
                    max_dev = max(
                        abs(((c - cog_mean) + 180) % 360 - 180) for c in self._gps_cog_history
                    )
                    going_straight = max_dev < 8.0

                if going_straight:
                    if self._heading_alignment_sample_count == 0:
                        # First sample: snap immediately to GPS COG — corrects full boot offset.
                        clamped_delta = max(-180.0, min(180.0, delta))
                        self._session_heading_alignment = (
                            self._session_heading_alignment + clamped_delta
                        ) % 360.0
                        self._heading_alignment_sample_count = 1
                        logger.info(
                            "HDG snap-calibrated from GPS COG: delta=%.1f° new_align=%.1f°",
                            clamped_delta, self._session_heading_alignment,
                        )
                        self._save_alignment_to_disk("gps_cog_snap")
                    else:
                        # Fine-tune with gentle EMA after the initial snap.
                        clamped_delta = max(-45.0, min(45.0, delta))
                        self._session_heading_alignment += 0.1 * clamped_delta
                        self._heading_alignment_sample_count += 1
                        if self._heading_alignment_sample_count % 20 == 0:
                            logger.info(
                                "HDG fine-tune: align=%.1f° delta=%.1f° samples=%d",
                                self._session_heading_alignment,
                                clamped_delta,
                                self._heading_alignment_sample_count,
                            )
                            self._save_alignment_to_disk("gps_cog")
        elif (
            sensor_data.gps is not None
            and sensor_data.gps.heading is not None
            and (sensor_data.gps.speed or 0.0) >= 0.3  # COG valid only when moving
        ):
            # Use GPS course-over-ground as heading fallback while in motion.
            # GPS COG is already in world frame; IMU yaw_offset does NOT apply here.
            self.navigation_state.heading = sensor_data.gps.heading
        
        # Always store GPS COG for diagnostic purposes
        if (
            sensor_data.gps is not None
            and sensor_data.gps.heading is not None
        ):
            self.navigation_state.gps_cog = sensor_data.gps.heading


        # Update obstacles
        obstacles = self.obstacle_detector.update_obstacles_from_sensors(sensor_data)
        self.navigation_state.obstacle_map = obstacles
        
        # Check if obstacle avoidance is needed
        self.navigation_state.obstacle_avoidance_active = len(obstacles) > 0
        
        # Update path execution if in auto mode
        if self.navigation_state.navigation_mode == NavigationMode.AUTO:
            await self._update_path_execution()
        
        # Update distance tracking
        if self.last_position and current_position:
            distance_increment = self.path_planner.calculate_distance(
                self.last_position, current_position
            )
            self.navigation_state.distance_traveled += distance_increment
            self.total_distance += distance_increment
        
        self.last_position = current_position
        self.navigation_state.timestamp = datetime.now(timezone.utc)
        
        return self.navigation_state
    
    async def _update_position(self, sensor_data: SensorData) -> Optional[Position]:
        """Update position using sensor fusion"""
        
        # Primary: GPS position
        if sensor_data.gps and sensor_data.gps.latitude and sensor_data.gps.longitude:
            gps_position = Position(
                latitude=sensor_data.gps.latitude,
                longitude=sensor_data.gps.longitude,
                altitude=sensor_data.gps.altitude,
                accuracy=sensor_data.gps.accuracy
            )

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
                        logger.debug("Position mismatch check failed; continuing with GPS fix.", exc_info=True)
            
            # Update dead reckoning reference
            self.dead_reckoning.update_gps_reference(gps_position)
            self.navigation_state.dead_reckoning_active = False
            self.navigation_state.last_gps_fix = datetime.now(timezone.utc)
            
            return gps_position
        
        # Fallback: Dead reckoning
        elif self.navigation_state.heading is not None:
            # Estimate distance traveled since last update (placeholder)
            distance_traveled = 0.1  # meters, would be calculated from wheel encoders
            
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
            self.navigation_state.current_position,
            current_waypoint.position
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
            self.navigation_state.target_velocity = current_waypoint.target_speed or self.cruise_speed
    
    async def plan_path(self, boundaries: List[Position], 
                       cutting_pattern: str = "parallel") -> bool:
        """Plan a mowing path for the given boundaries"""
        logger.info(f"Planning {cutting_pattern} path for area with {len(boundaries)} boundary points")
        
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
                self.navigation_state.planned_path[i-1].position,
                self.navigation_state.planned_path[i].position
            )
        
        # Estimate completion time
        estimated_time_seconds = total_distance / self.cruise_speed
        self.navigation_state.estimated_completion_time = (
            datetime.now(timezone.utc) + timedelta(seconds=estimated_time_seconds)
        )
    
    async def start_autonomous_navigation(self) -> bool:
        """Start autonomous navigation"""
        if (self.navigation_state.path_status != PathStatus.PLANNED or
            not self.navigation_state.planned_path):
            logger.error("Cannot start navigation: no planned path")
            return False
        
        if not self.navigation_state.current_position:
            logger.error("Cannot start navigation: no current position")
            return False
        
        # Weather gating if service is available
        try:
            if self.weather is not None:
                pos = self.navigation_state.current_position
                latitude = getattr(pos, 'latitude', None)
                longitude = getattr(pos, 'longitude', None)

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
        self.navigation_state.operation_start_time = datetime.now(timezone.utc)
        
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
            self.navigation_state.operation_start_time = datetime.now(timezone.utc)

        logger.info("Navigation resumed")
        return True
    
    # ------------------------------------------------------------------
    # IMU alignment persistence
    # ------------------------------------------------------------------
    _ALIGNMENT_FILE = Path(__file__).resolve().parent.parent.parent.parent / "data" / "imu_alignment.json"

    def _load_alignment_from_disk(self) -> None:
        """Load persisted IMU alignment offset from data/imu_alignment.json.

        Called once during __init__.  A missing or corrupt file is silently ignored
        and the alignment starts at 0.0 (boot-time default).
        """
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
                self._session_heading_alignment, source, samples,
            )
        except Exception as exc:
            logger.warning("Could not load IMU alignment file: %s", exc)
            self._session_heading_alignment = 0.0

    def _save_alignment_to_disk(self, source: str) -> None:
        """Persist current session heading alignment to data/imu_alignment.json.

        Uses an atomic write (write to tmp then rename) to avoid partial files.
        Silently swallows errors so a filesystem issue never crashes navigation.
        """
        try:
            payload = {
                "session_heading_alignment": round(self._session_heading_alignment, 3),
                "sample_count": self._heading_alignment_sample_count,
                "source": source,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
            tmp = self._ALIGNMENT_FILE.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2))
            tmp.replace(self._ALIGNMENT_FILE)
            logger.info(
                "IMU alignment saved: %.1f° (source=%s, samples=%d)",
                self._session_heading_alignment, source, self._heading_alignment_sample_count,
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
            import backend.src.api.rest as rest_api
            rest_api._safety_state["estop_reason"] = reason
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
                    emergency_ok = await self._deliver_stop_command(reason="emergency stop fallback")
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

    def are_waypoints_in_geofence(self, waypoints: List["MissionWaypoint"]) -> bool:
        """Return True when all mission waypoints are inside the configured safety boundary."""
        boundaries = self.navigation_state.safety_boundaries
        if not boundaries:
            return True

        outer_boundary = boundaries[0]
        if len(outer_boundary) < 3:
            return False

        polygon = [(point.latitude, point.longitude) for point in outer_boundary]
        return all(point_in_polygon(waypoint.lat, waypoint.lon, polygon) for waypoint in waypoints)
    
    def set_safety_boundaries(self, boundaries: List[List[Position]]):
        """Set safety boundaries that must not be crossed"""
        self.navigation_state.safety_boundaries = boundaries
        logger.info(f"Set {len(boundaries)} safety boundaries")

    def _load_boundaries_from_zones(self) -> None:
        """Load mowing-area polygons from the map zones store into safety_boundaries."""
        try:
            from ..api import rest as rest_api
            zones = rest_api._zones_store  # list[Zone]
            boundary_polygons: list[list[Position]] = []
            for zone in zones:
                if not getattr(zone, "exclusion_zone", False):
                    pts = [Position(latitude=p.latitude, longitude=p.longitude) for p in zone.polygon]
                    if len(pts) >= 3:
                        boundary_polygons.append(pts)
            if boundary_polygons:
                self.navigation_state.safety_boundaries = boundary_polygons
                logger.info("Loaded %d boundary polygon(s) from map zones", len(boundary_polygons))
            else:
                logger.warning("No mowing-area zones defined; geofence enforcement disabled for this mission")
        except Exception:
            logger.warning("Failed to load map zones for geofence; continuing without boundary enforcement", exc_info=True)
    
    def add_no_go_zone(self, zone: List[Position]):
        """Add a no-go zone to avoid"""
        self.navigation_state.no_go_zones.append(zone)
        logger.info("Added no-go zone")

    def _nearest_boundary_point(self, pos: "Position", boundary: List["Position"]) -> "Position":
        """Return the boundary vertex closest to pos (Euclidean approx for nearby points)."""
        best = boundary[0]
        best_dist = haversine_m(pos.latitude, pos.longitude, best.latitude, best.longitude)
        for pt in boundary[1:]:
            d = haversine_m(pos.latitude, pos.longitude, pt.latitude, pt.longitude)
            if d < best_dist:
                best_dist = d
                best = pt
        return best
    
    async def get_navigation_status(self) -> Dict[str, Any]:
        """Get current navigation status"""
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
            "path_confidence": self.navigation_state.path_confidence
        }
