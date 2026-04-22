"""
NavigationState model for LawnBerry Pi v2
Current position, planned path, and movement state
"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class NavigationMode(str, Enum):
    """Navigation operation modes"""

    MANUAL = "manual"
    AUTO = "auto"
    RETURN_HOME = "return_home"
    EMERGENCY_STOP = "emergency_stop"
    PAUSED = "paused"
    IDLE = "idle"


class PathStatus(str, Enum):
    """Path planning status"""

    PLANNING = "planning"
    PLANNED = "planned"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class Position(BaseModel):
    """Geographic position coordinate"""

    latitude: float
    longitude: float
    altitude: float | None = None
    accuracy: float | None = None  # meters
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Waypoint(BaseModel):
    """Navigation waypoint with metadata"""

    position: Position
    target_speed: float | None = None  # m/s
    action: str | None = None  # e.g., "cut", "turn", "dock"
    tolerance: float = 0.5  # meters
    sequence_id: int | None = None


class Obstacle(BaseModel):
    """Detected obstacle information"""

    id: str
    position: Position
    size_x: float | None = None  # meters
    size_y: float | None = None  # meters
    confidence: float = 1.0  # 0.0-1.0
    obstacle_type: str | None = None  # "static", "dynamic", "unknown"
    detection_source: str  # "tof", "camera", "gps", "user"
    first_detected: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CoverageCell(BaseModel):
    """Grid cell coverage tracking"""

    x: int  # grid coordinates
    y: int
    covered: bool = False
    coverage_count: int = 0
    last_covered: datetime | None = None
    quality_score: float | None = None  # 0.0-1.0


class NavigationState(BaseModel):
    """Current navigation state and planning information"""

    # Current position and movement
    current_position: Position | None = None
    heading: float | None = None  # degrees (0-360), IMU yaw converted to compass convention
    gps_cog: float | None = None  # degrees (0-360), GPS Course-Over-Ground heading
    velocity: float | None = None  # m/s current speed
    target_velocity: float | None = None  # m/s desired speed

    # Path planning
    planned_path: list[Waypoint] = Field(default_factory=list)
    current_waypoint_index: int = 0
    path_status: PathStatus = PathStatus.PLANNING
    path_confidence: float = 0.0  # 0.0-1.0

    # Obstacle management
    obstacle_map: list[Obstacle] = Field(default_factory=list)
    obstacle_avoidance_active: bool = False

    # Coverage tracking
    coverage_grid: list[CoverageCell] = Field(default_factory=list)
    coverage_percentage: float = 0.0
    grid_resolution: float = 0.5  # meters per cell

    # Navigation mode and status
    navigation_mode: NavigationMode = NavigationMode.IDLE
    mode_changed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Safety and constraints
    safety_boundaries: list[list[Position]] = Field(default_factory=list)  # Polygon boundaries
    no_go_zones: list[list[Position]] = Field(default_factory=list)  # Exclusion areas
    home_position: Position | None = None
    docking_position: Position | None = None

    # Performance metrics
    distance_traveled: float = 0.0  # total meters
    area_covered: float = 0.0  # square meters
    operation_start_time: datetime | None = None
    estimated_completion_time: datetime | None = None

    # Dead reckoning fallback
    dead_reckoning_active: bool = False
    dead_reckoning_drift: float | None = None  # estimated drift in meters
    last_gps_fix: datetime | None = None

    # References
    job_id: str | None = None  # Current job being executed
    map_configuration_id: str | None = None  # Reference to map config

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(use_enum_values=True)

    def get_current_waypoint(self) -> Waypoint | None:
        """Get the current target waypoint"""
        if 0 <= self.current_waypoint_index < len(self.planned_path):
            return self.planned_path[self.current_waypoint_index]
        return None

    def advance_waypoint(self) -> bool:
        """Advance to next waypoint, returns True if successful"""
        if self.current_waypoint_index < len(self.planned_path) - 1:
            self.current_waypoint_index += 1
            return True
        return False

    def calculate_distance_to_target(self) -> float | None:
        """Calculate distance to current waypoint in meters"""
        current_wp = self.get_current_waypoint()
        if not current_wp or not self.current_position:
            return None

        # Simple Haversine approximation for short distances
        lat_diff = current_wp.position.latitude - self.current_position.latitude
        lon_diff = current_wp.position.longitude - self.current_position.longitude

        # Convert to meters (rough approximation)
        lat_meters = lat_diff * 111000  # ~111km per degree latitude
        lon_meters = lon_diff * 111000 * 0.7  # approximate longitude factor

        return (lat_meters**2 + lon_meters**2) ** 0.5
