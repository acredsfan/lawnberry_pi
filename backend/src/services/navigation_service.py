"""
NavigationService for LawnBerry Pi v2
Path planning, navigation, and sensor fusion with safety constraints
"""

import asyncio
import logging
import math
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ..core.config_loader import ConfigLoader
from ..nav.geoutils import point_in_polygon
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
        
        # Simple dead reckoning calculation
        lat_offset = distance_traveled * math.cos(math.radians(heading)) / 111000
        lon_offset = distance_traveled * math.sin(math.radians(heading)) / (111000 * 0.7)
        
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

        try:
            _, limits = ConfigLoader().get()
            self.obstacle_avoidance_distance = float(limits.tof_obstacle_distance_meters)
        except Exception as exc:
            logger.warning(
                "Failed to load navigation obstacle threshold from safety limits: %s",
                exc,
            )

        self.obstacle_detector = ObstacleDetector(self.obstacle_avoidance_distance)
        
        # State tracking
        self.total_distance = 0.0
        self.last_position: Optional[Position] = None
        self._mission_execution_active = False
        
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
                    emergency_ok = await self.emergency_stop()
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
                    emergency_ok = await self.emergency_stop()
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

            # Calculate heading and apply motor commands
            heading_to_target = self.path_planner.calculate_bearing(
                self.navigation_state.current_position,
                target_pos
            )
            
            current_heading = self.navigation_state.heading
            if current_heading is None:
                if heading_wait_start is None:
                    heading_wait_start = time.monotonic()
                    logger.warning("No heading data, cannot navigate.")
                await self._deliver_stop_command(reason="heading unavailable hold")
                if (time.monotonic() - heading_wait_start) >= self.position_verification_timeout_seconds:
                    emergency_ok = await self.emergency_stop()
                    raise RuntimeError(
                        "Heading unavailable while navigating waypoint"
                        + ("; emergency stop activated" if emergency_ok else "")
                    )
                await asyncio.sleep(1)
                continue
            heading_wait_start = None

            heading_error = (heading_to_target - current_heading + 180) % 360 - 180
            
            # Proportional controller for turning
            turn_effort = max(-1.0, min(1.0, heading_error / 45.0)) # Normalize error to [-1, 1] over a 90 degree arc
            
            # Set speed (scale by waypoint speed preference when provided)
            base_speed = self.cruise_speed
            try:
                if hasattr(waypoint, "speed") and isinstance(waypoint.speed, int):
                    base_speed = max(0.1, min(self.max_speed, (waypoint.speed / 100.0) * self.max_speed))
            except Exception:
                base_speed = self.cruise_speed

            forward_speed = base_speed
            if abs(heading_error) > 30:
                forward_speed *= 0.5 # Slow down for sharp turns
            
            left_speed = forward_speed * (1 - turn_effort)
            right_speed = forward_speed * (1 + turn_effort)
            
            # Clamp speeds
            left_speed = max(-self.max_speed, min(self.max_speed, left_speed))
            right_speed = max(-self.max_speed, min(self.max_speed, right_speed))

            try:
                await self.set_speed(left_speed, right_speed)
            except Exception as e:
                logger.error(f"Failed to set motor speed: {e}")
                await self._deliver_stop_command(reason="navigation command failure")
                raise RuntimeError("Failed to deliver navigation motor command") from e
            
            # Simulation of movement
            await asyncio.sleep(0.2) # Control loop at 5Hz

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

        accepted = await robohat.send_motor_command(_normalize(ls), _normalize(rs))
        if not accepted:
            raise RuntimeError("Motor command not accepted by controller")

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
        
        # Update heading from IMU
        if sensor_data.imu and sensor_data.imu.yaw is not None:
            self.navigation_state.heading = sensor_data.imu.yaw
        
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
        return stop_confirmed
    
    async def emergency_stop(self) -> bool:
        """Emergency stop navigation"""
        self.navigation_state.navigation_mode = NavigationMode.EMERGENCY_STOP
        self.navigation_state.target_velocity = 0.0
        self.navigation_state.path_status = PathStatus.INTERRUPTED
        self._latch_global_emergency_state()
        
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
    
    def add_no_go_zone(self, zone: List[Position]):
        """Add a no-go zone to avoid"""
        self.navigation_state.no_go_zones.append(zone)
        logger.info("Added no-go zone")
    
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
