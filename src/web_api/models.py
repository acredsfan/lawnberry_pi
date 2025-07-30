"""
Pydantic Models
API request/response models with validation for all endpoints.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field, validator
from enum import Enum


# Enums
class SystemState(str, Enum):
    IDLE = "idle"
    MOWING = "mowing"
    CHARGING = "charging"
    RETURNING_HOME = "returning_home"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class MowingPattern(str, Enum):
    PARALLEL_LINES = "parallel_lines"
    CHECKERBOARD = "checkerboard"
    SPIRAL = "spiral"
    WAVES = "waves"
    CROSSHATCH = "crosshatch"


class SensorType(str, Enum):
    GPS = "gps"
    IMU = "imu"
    TOF = "tof"
    CAMERA = "camera"
    POWER = "power"
    ENVIRONMENTAL = "environmental"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Base Models
class BaseAPIModel(BaseModel):
    """Base model with common configuration"""
    
    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class TimestampedModel(BaseAPIModel):
    """Base model with timestamp"""
    timestamp: datetime = Field(default_factory=datetime.now)


# System Models
class SystemStatus(BaseAPIModel):
    """Overall system status"""
    state: SystemState
    uptime: float
    version: str
    services_online: int
    services_total: int
    last_error: Optional[str] = None
    error_count: int = 0


class ServiceHealth(BaseAPIModel):
    """Individual service health status"""
    name: str
    status: str
    last_heartbeat: datetime
    cpu_usage: float
    memory_usage: float
    error_count: int = 0


# Sensor Models
class SensorReading(TimestampedModel):
    """Sensor data reading"""
    sensor_id: str
    sensor_type: SensorType
    value: Union[float, int, Dict[str, Any]]
    unit: str = ""
    quality: float = Field(ge=0.0, le=1.0, default=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SensorStatus(BaseAPIModel):
    """Sensor status information"""
    sensor_id: str
    sensor_type: SensorType
    online: bool
    last_reading: Optional[datetime] = None
    error_count: int = 0
    calibration_status: str = "ok"


# Navigation Models
class Position(BaseAPIModel):
    """Geographic position"""
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    altitude: Optional[float] = None
    accuracy: Optional[float] = None


class NavigationStatus(TimestampedModel):
    """Current navigation status"""
    position: Position
    heading: float = Field(ge=0, lt=360)
    speed: float = Field(ge=0)
    target_position: Optional[Position] = None
    distance_to_target: Optional[float] = None
    path_progress: float = Field(ge=0, le=1, default=0)


class NavigationCommand(BaseAPIModel):
    """Navigation control command"""
    action: str = Field(regex="^(start|stop|pause|resume|return_home)$")
    target_position: Optional[Position] = None
    pattern: Optional[MowingPattern] = None
    speed: Optional[float] = Field(gt=0, le=2.0)


# Pattern Models
class MowingSchedule(BaseAPIModel):
    """Mowing schedule configuration"""
    enabled: bool = True
    days_of_week: List[int] = Field(min_items=1, max_items=7)
    start_time: str = Field(regex="^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
    duration_minutes: int = Field(gt=0, le=480)
    pattern: MowingPattern
    
    @validator('days_of_week')
    def validate_days(cls, v):
        if not all(0 <= day <= 6 for day in v):
            raise ValueError('Days must be 0-6 (Monday=0)')
        return sorted(list(set(v)))


class PatternConfig(BaseAPIModel):
    """Mowing pattern configuration"""
    pattern: MowingPattern
    parameters: Dict[str, Any] = Field(default_factory=dict)
    coverage_overlap: float = Field(ge=0, le=0.5, default=0.1)
    edge_cutting: bool = True


# Configuration Models
class SystemConfig(BaseAPIModel):
    """System configuration"""
    units: str = Field(regex="^(metric|imperial)$", default="metric")
    temperature_unit: str = Field(regex="^(celsius|fahrenheit)$", default="celsius")
    safety_timeout: int = Field(gt=0, le=300, default=100)
    emergency_stop_enabled: bool = True
    auto_return_battery_level: float = Field(ge=0.1, le=0.5, default=0.2)


class SafetyConfig(BaseAPIModel):
    """Safety system configuration"""
    obstacle_detection_sensitivity: float = Field(ge=0.1, le=1.0, default=0.8)
    tilt_threshold_degrees: float = Field(gt=0, le=45, default=15)
    person_detection_distance: float = Field(gt=0, le=10, default=3.0)
    pet_detection_distance: float = Field(gt=0, le=5, default=1.5)
    rain_sensitivity: float = Field(ge=0.1, le=1.0, default=0.7)


# Map Models
class Boundary(BaseAPIModel):
    """Yard boundary definition"""
    points: List[Position] = Field(min_items=3)
    name: str = "main_boundary"
    
    @validator('points')
    def validate_boundary(cls, v):
        if len(v) < 3:
            raise ValueError('Boundary must have at least 3 points')
        return v


class NoGoZone(BaseAPIModel):
    """No-go zone definition"""
    points: List[Position] = Field(min_items=3)
    name: str
    priority: Priority = Priority.HIGH
    
    @validator('points')
    def validate_zone(cls, v):
        if len(v) < 3:
            raise ValueError('No-go zone must have at least 3 points')
        return v


class MapData(BaseAPIModel):
    """Complete map data"""
    boundaries: List[Boundary] = Field(default_factory=list)
    no_go_zones: List[NoGoZone] = Field(default_factory=list)
    home_position: Optional[Position] = None
    charging_spots: List[Position] = Field(default_factory=list)
    coverage_map: Optional[Dict[str, Any]] = None


# Weather Models
class WeatherCondition(TimestampedModel):
    """Current weather conditions"""
    temperature: float
    humidity: float
    precipitation: float = 0.0
    wind_speed: float = 0.0
    wind_direction: Optional[float] = None
    pressure: Optional[float] = None
    visibility: Optional[float] = None
    conditions: str = "clear"


class WeatherForecast(BaseAPIModel):
    """Weather forecast data"""
    date: datetime
    temperature_high: float
    temperature_low: float
    precipitation_probability: float = Field(ge=0, le=1)
    precipitation_amount: float = 0.0
    wind_speed: float = 0.0
    conditions: str


# Power Models
class BatteryStatus(TimestampedModel):
    """Battery status information"""
    voltage: float = Field(gt=0)
    current: float
    power: float
    state_of_charge: float = Field(ge=0, le=1)
    temperature: Optional[float] = None
    health: float = Field(ge=0, le=1, default=1.0)
    cycles: int = Field(ge=0, default=0)
    time_remaining: Optional[int] = None  # minutes


class SolarStatus(TimestampedModel):
    """Solar charging status"""
    voltage: float = Field(ge=0)
    current: float = Field(ge=0)
    power: float = Field(ge=0)
    daily_energy: float = Field(ge=0, default=0.0)
    efficiency: float = Field(ge=0, le=1, default=0.0)


class PowerStatus(BaseAPIModel):
    """Complete power system status"""
    battery: BatteryStatus
    solar: Optional[SolarStatus] = None
    charging_mode: str = "auto"
    power_saving_enabled: bool = False


# WebSocket Models
class WebSocketMessage(BaseAPIModel):
    """WebSocket message format"""
    type: str
    topic: Optional[str] = None
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)


class WebSocketCommand(BaseAPIModel):
    """WebSocket command message"""
    command: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = None


# Response Models
class SuccessResponse(BaseAPIModel):
    """Standard success response"""
    success: bool = True
    message: str = "Operation completed successfully"
    data: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseAPIModel):
    """Standard error response"""
    success: bool = False
    error: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)


# Pagination Models
class PaginationParams(BaseAPIModel):
    """Pagination parameters"""
    page: int = Field(ge=1, default=1)
    size: int = Field(ge=1, le=100, default=20)
    
    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


class PaginatedResponse(BaseAPIModel):
    """Paginated response wrapper"""
    items: List[Any]
    total: int
    page: int
    size: int
    pages: int
    
    @validator('pages', pre=True, always=True)
    def calculate_pages(cls, v, values):
        total = values.get('total', 0)
        size = values.get('size', 20)
        return (total + size - 1) // size if total > 0 else 1
