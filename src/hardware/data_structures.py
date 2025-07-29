"""Standardized data structures for sensor readings"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
import asyncio


@dataclass
class SensorReading:
    """Base sensor reading with timestamp and metadata"""
    timestamp: datetime
    sensor_id: str
    value: Any
    unit: str
    quality: float = 1.0  # 0.0 to 1.0, 1.0 = perfect
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class I2CDeviceReading(SensorReading):
    """I2C device reading with address info"""
    i2c_address: int
    register: Optional[int] = None


@dataclass
class SerialDeviceReading(SensorReading):
    """Serial device reading with port info"""
    port: str
    baud_rate: int


@dataclass
class GPIOReading(SensorReading):
    """GPIO pin reading"""
    pin: int
    direction: str  # 'input' or 'output'


@dataclass
class CameraFrame:
    """Camera frame data"""
    timestamp: datetime
    frame_id: int
    width: int
    height: int
    format: str
    data: bytes
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ToFReading(I2CDeviceReading):
    """Time-of-Flight sensor reading in millimeters"""
    distance_mm: int
    range_status: str = "valid"


@dataclass
class IMUReading(SerialDeviceReading):
    """IMU sensor reading with orientation and motion data"""
    quaternion: tuple[float, float, float, float]
    acceleration: tuple[float, float, float]  # m/s²
    angular_velocity: tuple[float, float, float]  # rad/s
    magnetic_field: Optional[tuple[float, float, float]] = None  # µT


@dataclass
class GPSReading(SerialDeviceReading):
    """GPS reading with position and accuracy"""
    latitude: float
    longitude: float
    altitude: float
    accuracy: float  # meters
    satellites: int
    fix_type: str  # 'none', '2d', '3d', 'rtk'


@dataclass
class PowerReading(I2CDeviceReading):
    """Power monitor reading"""
    voltage: float  # V
    current: float  # A
    power: float    # W


@dataclass
class EnvironmentalReading(I2CDeviceReading):
    """Environmental sensor reading (BME280)"""
    temperature: float  # °C
    humidity: float     # %
    pressure: float     # hPa


@dataclass
class RoboHATStatus:
    """RoboHAT controller status"""
    timestamp: datetime
    rc_enabled: bool
    steer_pwm: int      # µs (1000-2000)
    throttle_pwm: int   # µs (1000-2000) 
    encoder_position: int
    connection_active: bool


class DeviceHealth:
    """Track device health and connection status"""
    
    def __init__(self, device_id: str):
        self.device_id = device_id
        self.last_successful_read = datetime.now()
        self.consecutive_failures = 0
        self.total_reads = 0
        self.total_failures = 0
        self.is_connected = False
        self._lock = asyncio.Lock()
    
    async def record_success(self):
        """Record successful device operation"""
        async with self._lock:
            self.last_successful_read = datetime.now()
            self.consecutive_failures = 0
            self.total_reads += 1
            self.is_connected = True
    
    async def record_failure(self):
        """Record failed device operation"""
        async with self._lock:
            self.consecutive_failures += 1
            self.total_failures += 1
            self.total_reads += 1
            if self.consecutive_failures >= 5:
                self.is_connected = False
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0 to 1.0)"""
        if self.total_reads == 0:
            return 1.0
        return (self.total_reads - self.total_failures) / self.total_reads
    
    @property
    def is_healthy(self) -> bool:
        """Check if device is considered healthy"""
        return (
            self.is_connected and 
            self.consecutive_failures < 3 and
            self.success_rate > 0.8
        )
