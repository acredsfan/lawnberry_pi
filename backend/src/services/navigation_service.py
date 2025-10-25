"""
NavigationService for LawnBerry Pi v2
Path planning, navigation, and sensor fusion with safety constraints
"""

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any

from ..models import (
    NavigationState, Position, Waypoint, Obstacle, CoverageCell,
    NavigationMode, PathStatus, SensorData
)
from ..nav.path_planner import PathPlanner

logger = logging.getLogger(__name__)


## Path planning moved to backend.src.nav.path_planner.PathPlanner


class ObstacleDetector:
    """Obstacle detection and avoidance"""
    
    def __init__(self, safety_distance: float = 1.0):
        self.safety_distance = safety_distance
        self.detected_obstacles: List[Obstacle] = []
    
    def update_obstacles_from_sensors(self, sensor_data: SensorData) -> List[Obstacle]:
        """Update obstacle list from sensor data"""
        obstacles = []
        obstacle_id_counter = 0
        
        # ToF sensor obstacles
        if sensor_data.tof_left and sensor_data.tof_left.distance:
            if sensor_data.tof_left.distance < 1000:  # Less than 1 meter
                obstacles.append(Obstacle(
                    id=f"tof_left_{obstacle_id_counter}",
                    position=Position(latitude=0, longitude=0),  # Relative position
                    confidence=0.8,
                    obstacle_type="static",
                    detection_source="tof"
                ))
                obstacle_id_counter += 1
        
        if sensor_data.tof_right and sensor_data.tof_right.distance:
            if sensor_data.tof_right.distance < 1000:  # Less than 1 meter
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
        self.obstacle_detector = ObstacleDetector()
        self.dead_reckoning = DeadReckoningSystem()
        # Optional weather service with get_current() and get_planning_advice()
        self.weather = weather
        
        # Navigation parameters
        self.max_speed = 0.8  # m/s
        self.cruise_speed = 0.5  # m/s
        self.waypoint_tolerance = 0.5  # meters
        self.obstacle_avoidance_distance = 1.0  # meters
        
        # State tracking
        self.total_distance = 0.0
        self.last_position: Optional[Position] = None
        
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
        from .mission_service import MissionService, get_mission_service
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
        
        self.navigation_state.current_waypoint_index = 0
        self.navigation_state.operation_start_time = datetime.now(timezone.utc)

        while self.navigation_state.current_waypoint_index < len(self.navigation_state.planned_path):
            status = mission_service.mission_statuses.get(mission.id)
            if not status or status.status != "running":
                logger.warning(f"Mission {mission.id} interrupted. Status: {status.status if status else 'N/A'}")
                self.navigation_state.path_status = PathStatus.INTERRUPTED
                self.navigation_state.navigation_mode = NavigationMode.IDLE
                return

            current_mission_waypoint = mission.waypoints[self.navigation_state.current_waypoint_index]
            await self.go_to_waypoint(current_mission_waypoint)

            # The go_to_waypoint method is blocking until the waypoint is reached or interrupted.
            # The loop will then proceed to the next waypoint.
            # We add a small sleep to prevent a tight loop if go_to_waypoint returns immediately.
            await asyncio.sleep(0.1)

        if self.navigation_state.navigation_mode == NavigationMode.AUTO:
            self.navigation_state.path_status = PathStatus.COMPLETED
            self.navigation_state.navigation_mode = NavigationMode.IDLE
            logger.info(f"Mission {mission.id} completed.")

    async def go_to_waypoint(self, waypoint: "MissionWaypoint"):
        """Navigate to a single waypoint and block until arrival."""
        from .mission_service import MissionService, get_mission_service
        mission_service = get_mission_service()
        
        target_pos = Position(latitude=waypoint.lat, longitude=waypoint.lon)
        logger.info(f"Navigating to waypoint: {target_pos.latitude}, {target_pos.longitude}")

        # Here you would set motor commands based on heading to target
        # e.g., self.motor_service.set_speed_and_direction(...)
        
        # Placeholder for blade control
        # e.g., self.blade_service.set_blade_on(waypoint.blade_on)

        while True:
            if not self.navigation_state.current_position:
                await asyncio.sleep(0.5)
                continue

            # Check for interruptions (pause/abort)
            mission_id = next((mid for mid, m in mission_service.missions.items() if waypoint.id in [w.id for w in m.waypoints]), None)
            if mission_id:
                status = mission_service.mission_statuses.get(mission_id)
                if not status or status.status != "running":
                    logger.info("Waypoint navigation interrupted.")
                    self.nav_service.set_speed(0, 0)
                    return

            distance_to_target = self.path_planner.calculate_distance(
                self.navigation_state.current_position,
                target_pos
            )

            if distance_to_target <= self.waypoint_tolerance:
                logger.info(f"Waypoint reached: {waypoint.lat}, {waypoint.lon}")
                self.nav_service.set_speed(0, 0) # Stop at waypoint
                if self.navigation_state.advance_waypoint():
                    logger.info(f"Advanced to next waypoint index: {self.navigation_state.current_waypoint_index}")
                else:
                    logger.info("Final waypoint in path reached.")
                break

            # Calculate heading and apply motor commands
            heading_to_target = self.path_planner.calculate_bearing(
                self.navigation_state.current_position,
                target_pos
            )
            
            current_heading = self.navigation_state.heading
            if current_heading is None:
                logger.warning("No heading data, cannot navigate.")
                await asyncio.sleep(1)
                continue

            heading_error = (heading_to_target - current_heading + 180) % 360 - 180
            
            # Proportional controller for turning
            turn_effort = max(-1.0, min(1.0, heading_error / 45.0)) # Normalize error to [-1, 1] over a 90 degree arc
            
            # Set speed
            forward_speed = self.cruise_speed
            if abs(heading_error) > 30:
                forward_speed *= 0.5 # Slow down for sharp turns
            
            left_speed = forward_speed * (1 - turn_effort)
            right_speed = forward_speed * (1 + turn_effort)
            
            # Clamp speeds
            left_speed = max(-self.max_speed, min(self.max_speed, left_speed))
            right_speed = max(-self.max_speed, min(self.max_speed, right_speed))

            try:
                self.set_speed(left_speed, right_speed)
            except Exception as e:
                logger.error(f"Failed to set motor speed: {e}")
                self.set_speed(0, 0)
                return
            
            # Simulation of movement
            await asyncio.sleep(0.2) # Control loop at 5Hz
    
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
            datetime.now(timezone.utc) + 
            datetime.timedelta(seconds=estimated_time_seconds)
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
    
    async def stop_navigation(self) -> bool:
        """Stop navigation and return to idle"""
        self.navigation_state.navigation_mode = NavigationMode.IDLE
        self.navigation_state.target_velocity = 0.0
        
        if self.navigation_state.path_status == PathStatus.EXECUTING:
            self.navigation_state.path_status = PathStatus.INTERRUPTED
        
        logger.info("Navigation stopped")
        return True
    
    async def emergency_stop(self) -> bool:
        """Emergency stop navigation"""
        self.navigation_state.navigation_mode = NavigationMode.EMERGENCY_STOP
        self.navigation_state.target_velocity = 0.0
        self.navigation_state.path_status = PathStatus.INTERRUPTED
        
        logger.critical("Emergency stop activated")
        return True
    
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