"""
Data structures for sensor fusion engine
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
import numpy as np


class HazardLevel(Enum):
    """Hazard severity levels"""
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class ObstacleType(Enum):
    """Types of detected obstacles"""
    UNKNOWN = "unknown"
    PERSON = "person"
    PET = "pet"
    STATIC_OBJECT = "static_object"
    DYNAMIC_OBJECT = "dynamic_object"
    VEGETATION = "vegetation"
    BOUNDARY = "boundary"
    CLIFF = "cliff"
    WATER = "water"


@dataclass
class PoseEstimate:
    """Standardized pose estimation (position, orientation, velocity)"""
    timestamp: datetime
    
    # Position (meters, GPS coordinates)
    latitude: float
    longitude: float
    altitude: float
    
    # Local position (meters from reference point)
    x: float
    y: float
    z: float
    
    # Orientation (quaternion)
    qw: float
    qx: float
    qy: float
    qz: float
    
    # Velocity (m/s)
    vx: float
    vy: float
    vz: float
    
    # Angular velocity (rad/s)
    wx: float
    wy: float
    wz: float
    
    # Uncertainty covariance matrix (6x6 for position and orientation)
    covariance: np.ndarray
    
    # Quality metrics
    gps_accuracy: float = 0.0  # meters
    imu_quality: float = 1.0   # 0.0 to 1.0
    fusion_confidence: float = 1.0  # 0.0 to 1.0
    
    def __post_init__(self):
        if self.covariance is None:
            self.covariance = np.eye(6) * 0.1  # Default uncertainty


@dataclass
class ObstacleInfo:
    """Individual obstacle information"""
    obstacle_id: str
    obstacle_type: ObstacleType
    
    # Position relative to robot (meters)
    x: float
    y: float
    z: float
    
    # Size (meters)
    width: float
    height: float
    depth: float
    
    # Velocity (m/s) - for dynamic obstacles
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    
    # Detection confidence (0.0 to 1.0)
    confidence: float = 1.0
    
    # Detection source
    detected_by: List[str] = None  # e.g., ['tof_left', 'camera', 'lidar']
    
    # Distance to robot (meters)
    distance: float = 0.0
    
    # Time when obstacle was first detected
    first_detected: datetime = None
    
    # Time when obstacle was last updated
    last_updated: datetime = None
    
    def __post_init__(self):
        if self.detected_by is None:
            self.detected_by = []
        if self.first_detected is None:
            self.first_detected = datetime.now()
        if self.last_updated is None:
            self.last_updated = datetime.now()
        
        # Calculate distance if not provided
        if self.distance == 0.0:
            self.distance = np.sqrt(self.x**2 + self.y**2 + self.z**2)


@dataclass
class ObstacleMap:
    """Obstacle map with confidence levels"""
    timestamp: datetime
    obstacles: List[ObstacleInfo]
    
    # Map bounds (meters from robot)
    map_radius: float = 10.0
    
    # Grid resolution (meters per cell)
    resolution: float = 0.1
    
    # Occupancy grid (optional for detailed mapping)
    occupancy_grid: Optional[np.ndarray] = None
    
    # Detection statistics
    total_obstacles: int = 0
    high_confidence_obstacles: int = 0
    dynamic_obstacles: int = 0
    
    def __post_init__(self):
        self.total_obstacles = len(self.obstacles)
        self.high_confidence_obstacles = sum(1 for obs in self.obstacles if obs.confidence > 0.8)
        self.dynamic_obstacles = sum(1 for obs in self.obstacles if obs.vx != 0 or obs.vy != 0 or obs.vz != 0)
    
    def get_obstacles_in_radius(self, radius: float) -> List[ObstacleInfo]:
        """Get obstacles within specified radius"""
        return [obs for obs in self.obstacles if obs.distance <= radius]
    
    def get_obstacles_by_type(self, obstacle_type: ObstacleType) -> List[ObstacleInfo]:
        """Get obstacles of specific type"""
        return [obs for obs in self.obstacles if obs.obstacle_type == obstacle_type]


@dataclass
class HazardAlert:
    """Safety hazard alert"""
    alert_id: str
    hazard_level: HazardLevel
    hazard_type: str  # 'tilt', 'drop', 'collision', 'person', 'weather', etc.
    
    timestamp: datetime
    description: str
    
    # Location where hazard was detected
    location: Optional[Tuple[float, float, float]] = None
    
    # Sensor data that triggered the alert
    sensor_data: Dict[str, Any] = None
    
    # Recommended action
    recommended_action: str = "STOP"
    
    # Time critical flag
    immediate_response_required: bool = False
    
    def __post_init__(self):
        if self.sensor_data is None:
            self.sensor_data = {}


@dataclass
class SafetyStatus:
    """Safety status indicators"""
    timestamp: datetime
    
    # Overall safety state
    is_safe: bool = True
    safety_level: HazardLevel = HazardLevel.NONE
    
    # Individual safety checks
    tilt_safe: bool = True
    drop_safe: bool = True
    collision_safe: bool = True
    weather_safe: bool = True
    boundary_safe: bool = True
    
    # Current tilt angle (degrees)
    tilt_angle: float = 0.0
    max_safe_tilt: float = 15.0
    
    # Drop detection
    ground_clearance: float = 0.0  # meters
    min_safe_clearance: float = 0.05  # meters
    
    # Obstacle proximity
    nearest_obstacle_distance: float = float('inf')
    safe_distance_threshold: float = 0.3  # meters
    
    # Weather conditions
    temperature: float = 20.0  # Celsius
    humidity: float = 50.0     # %
    is_raining: bool = False
    
    # Active alerts
    active_alerts: List[HazardAlert] = None
    
    # Response time tracking
    last_hazard_detected: Optional[datetime] = None
    response_time_ms: Optional[float] = None
    
    def __post_init__(self):
        if self.active_alerts is None:
            self.active_alerts = []
        
        # Update overall safety status
        self.is_safe = (
            self.tilt_safe and 
            self.drop_safe and 
            self.collision_safe and 
            self.weather_safe and 
            self.boundary_safe
        )
        
        # Determine overall safety level
        if not self.is_safe:
            if any(alert.hazard_level == HazardLevel.CRITICAL for alert in self.active_alerts):
                self.safety_level = HazardLevel.CRITICAL
            elif any(alert.hazard_level == HazardLevel.HIGH for alert in self.active_alerts):
                self.safety_level = HazardLevel.HIGH
            elif any(alert.hazard_level == HazardLevel.MEDIUM for alert in self.active_alerts):
                self.safety_level = HazardLevel.MEDIUM
            else:
                self.safety_level = HazardLevel.LOW


@dataclass
class SensorHealthMetrics:
    """Sensor health metrics"""
    timestamp: datetime
    
    # Individual sensor health
    gps_healthy: bool = True
    imu_healthy: bool = True
    tof_left_healthy: bool = True
    tof_right_healthy: bool = True
    camera_healthy: bool = True
    power_monitor_healthy: bool = True
    weather_sensor_healthy: bool = True
    
    # Data quality metrics
    gps_accuracy: float = 0.0      # meters
    imu_calibration: float = 1.0   # 0.0 to 1.0
    sensor_update_rates: Dict[str, float] = None  # Hz
    
    # Communication health
    mqtt_connected: bool = True
    hardware_interface_connected: bool = True
    
    # Overall system health
    overall_health_score: float = 1.0  # 0.0 to 1.0
    
    def __post_init__(self):
        if self.sensor_update_rates is None:
            self.sensor_update_rates = {}
        
        # Calculate overall health score
        healthy_sensors = sum([
            self.gps_healthy,
            self.imu_healthy, 
            self.tof_left_healthy,
            self.tof_right_healthy,
            self.camera_healthy,
            self.power_monitor_healthy,
            self.weather_sensor_healthy
        ])
        
        total_sensors = 7
        self.overall_health_score = healthy_sensors / total_sensors


@dataclass 
class LocalizationData:
    """Localization system data"""
    pose: PoseEstimate
    gps_fix_type: str  # 'none', '2d', '3d', 'rtk'
    satellites_visible: int = 0
    hdop: float = 0.0  # Horizontal Dilution of Precision
    
    # Dead reckoning data
    wheel_encoder_position: int = 0
    estimated_distance_traveled: float = 0.0
    
    # Kalman filter state
    filter_state: Optional[np.ndarray] = None
    filter_covariance: Optional[np.ndarray] = None


@dataclass
class ObstacleData:
    """Obstacle detection system data"""
    obstacle_map: ObstacleMap
    
    # ToF sensor readings
    tof_left_distance: float = 0.0    # meters
    tof_right_distance: float = 0.0   # meters
    
    # Computer vision results
    cv_detections: List[Dict[str, Any]] = None
    processing_time_ms: float = 0.0
    
    def __post_init__(self):
        if self.cv_detections is None:
            self.cv_detections = []
