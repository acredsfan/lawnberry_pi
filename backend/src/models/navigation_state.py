"""
NavigationState model for LawnBerry Pi v2
Current position, planned path, and movement state
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


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
    altitude: Optional[float] = None
    accuracy: Optional[float] = None  # meters
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Waypoint(BaseModel):
    """Navigation waypoint with metadata"""
    position: Position
    target_speed: Optional[float] = None  # m/s
    action: Optional[str] = None  # e.g., "cut", "turn", "dock"
    tolerance: float = 0.5  # meters
    sequence_id: Optional[int] = None


class Obstacle(BaseModel):
    """Detected obstacle information"""
    id: str
    position: Position
    size_x: Optional[float] = None  # meters
    size_y: Optional[float] = None  # meters
    confidence: float = 1.0  # 0.0-1.0
    obstacle_type: Optional[str] = None  # "static", "dynamic", "unknown"
    detection_source: str  # "tof", "camera", "gps", "user"
    first_detected: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CoverageCell(BaseModel):
    """Grid cell coverage tracking"""
    x: int  # grid coordinates
    y: int
    covered: bool = False
    coverage_count: int = 0
    last_covered: Optional[datetime] = None
    quality_score: Optional[float] = None  # 0.0-1.0


class NavigationState(BaseModel):
    """Current navigation state and planning information"""
    # Current position and movement
    current_position: Optional[Position] = None
    heading: Optional[float] = None  # degrees (0-360)
    velocity: Optional[float] = None  # m/s current speed
    target_velocity: Optional[float] = None  # m/s desired speed
    
    # Path planning
    planned_path: List[Waypoint] = Field(default_factory=list)
    current_waypoint_index: int = 0
    path_status: PathStatus = PathStatus.PLANNING
    path_confidence: float = 0.0  # 0.0-1.0
    
    # Obstacle management
    obstacle_map: List[Obstacle] = Field(default_factory=list)
    obstacle_avoidance_active: bool = False
    
    # Coverage tracking
    coverage_grid: List[CoverageCell] = Field(default_factory=list)
    coverage_percentage: float = 0.0
    grid_resolution: float = 0.5  # meters per cell
    
    # Navigation mode and status
    navigation_mode: NavigationMode = NavigationMode.IDLE
    mode_changed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Safety and constraints
    safety_boundaries: List[List[Position]] = Field(default_factory=list)  # Polygon boundaries
    no_go_zones: List[List[Position]] = Field(default_factory=list)  # Exclusion areas
    home_position: Optional[Position] = None
    docking_position: Optional[Position] = None
    
    # Performance metrics
    distance_traveled: float = 0.0  # total meters
    area_covered: float = 0.0  # square meters
    operation_start_time: Optional[datetime] = None
    estimated_completion_time: Optional[datetime] = None
    
    # Dead reckoning fallback
    dead_reckoning_active: bool = False
    dead_reckoning_drift: Optional[float] = None  # estimated drift in meters
    last_gps_fix: Optional[datetime] = None
    
    # References
    job_id: Optional[str] = None  # Current job being executed
    map_configuration_id: Optional[str] = None  # Reference to map config
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}
    
    def get_current_waypoint(self) -> Optional[Waypoint]:
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
    
    def calculate_distance_to_target(self) -> Optional[float]:
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
        
        return (lat_meters**2 + lon_meters**2)**0.5