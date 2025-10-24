"""
SensorData model for LawnBerry Pi v2
Hardware sensor readings and status information
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict


class SensorType(str, Enum):
    """Available sensor types"""
    GPS = "gps"
    IMU = "imu"
    TOF_LEFT = "tof_left"
    TOF_RIGHT = "tof_right"
    ENVIRONMENTAL = "environmental"
    POWER = "power"
    CAMERA = "camera"


class SensorStatus(str, Enum):
    """Sensor operational status"""
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"
    CALIBRATING = "calibrating"
    UNKNOWN = "unknown"


class GpsMode(str, Enum):
    """GPS module configuration"""
    F9P_USB = "f9p_usb"  # u-blox ZED-F9P via USB with RTK
    F9P_UART = "f9p_uart"  # u-blox ZED-F9P via UART with RTK
    NEO8M_UART = "neo8m_uart"  # u-blox Neo-8M via UART


class SensorReading(BaseModel):
    """Individual sensor data reading"""
    sensor_type: SensorType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    value: Dict[str, Any]
    unit: Optional[str] = None
    accuracy: Optional[float] = None
    confidence: Optional[float] = None
    status: SensorStatus = SensorStatus.ONLINE


class GpsReading(BaseModel):
    """GPS-specific sensor reading"""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    accuracy: Optional[float] = None  # meters
    heading: Optional[float] = None  # degrees
    speed: Optional[float] = None  # m/s
    satellites: Optional[int] = None
    hdop: Optional[float] = None  # horizontal dilution of precision
    mode: GpsMode = GpsMode.NEO8M_UART
    rtk_status: Optional[str] = None  # RTK correction status
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ImuReading(BaseModel):
    """IMU (BNO085) sensor reading"""
    roll: Optional[float] = None  # degrees
    pitch: Optional[float] = None  # degrees
    yaw: Optional[float] = None  # degrees
    accel_x: Optional[float] = None  # m/s²
    accel_y: Optional[float] = None  # m/s²
    accel_z: Optional[float] = None  # m/s²
    gyro_x: Optional[float] = None  # rad/s
    gyro_y: Optional[float] = None  # rad/s
    gyro_z: Optional[float] = None  # rad/s
    mag_x: Optional[float] = None  # µT
    mag_y: Optional[float] = None  # µT
    mag_z: Optional[float] = None  # µT
    calibration_status: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TofReading(BaseModel):
    """Time-of-Flight sensor reading"""
    distance: Optional[float] = None  # millimeters
    signal_strength: Optional[float] = None
    ambient_light: Optional[float] = None
    range_status: Optional[str] = None  # "valid", "wrap_around", "signal_fail", etc.
    sensor_side: str  # "left" or "right"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EnvironmentalReading(BaseModel):
    """Environmental sensor (BME280) reading"""
    temperature: Optional[float] = None  # °C
    humidity: Optional[float] = None  # %RH
    pressure: Optional[float] = None  # hPa
    altitude: Optional[float] = None  # meters (calculated from pressure)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PowerReading(BaseModel):
    """Power monitoring (INA3221) reading"""
    battery_voltage: Optional[float] = None  # V
    battery_current: Optional[float] = None  # A
    battery_power: Optional[float] = None  # W
    solar_voltage: Optional[float] = None  # V
    solar_current: Optional[float] = None  # A
    solar_power: Optional[float] = None  # W
    solar_yield_today_wh: Optional[float] = None  # Wh (daily yield from Victron)
    load_voltage: Optional[float] = None  # V (if applicable)
    load_current: Optional[float] = None  # A (if applicable)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SensorData(BaseModel):
    """Complete sensor data snapshot"""
    gps: Optional[GpsReading] = None
    imu: Optional[ImuReading] = None
    tof_left: Optional[TofReading] = None
    tof_right: Optional[TofReading] = None
    environmental: Optional[EnvironmentalReading] = None
    power: Optional[PowerReading] = None
    sensor_health: Dict[SensorType, SensorStatus] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    hardware_baseline_id: Optional[str] = None  # Reference to hardware configuration
    
    model_config = ConfigDict(use_enum_values=True)