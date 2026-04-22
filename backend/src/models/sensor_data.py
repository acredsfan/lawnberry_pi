"""
SensorData model for LawnBerry Pi v2
Hardware sensor readings and status information
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    value: dict[str, Any]
    unit: str | None = None
    accuracy: float | None = None
    confidence: float | None = None
    status: SensorStatus = SensorStatus.ONLINE


class GpsReading(BaseModel):
    """GPS-specific sensor reading"""

    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    accuracy: float | None = None  # meters
    heading: float | None = None  # degrees
    speed: float | None = None  # m/s
    satellites: int | None = None
    hdop: float | None = None  # horizontal dilution of precision
    mode: GpsMode = GpsMode.NEO8M_UART
    rtk_status: str | None = None  # RTK correction status
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ImuReading(BaseModel):
    """IMU (BNO085) sensor reading"""

    roll: float | None = None  # degrees
    pitch: float | None = None  # degrees
    yaw: float | None = None  # degrees
    accel_x: float | None = None  # m/s²
    accel_y: float | None = None  # m/s²
    accel_z: float | None = None  # m/s²
    gyro_x: float | None = None  # rad/s
    gyro_y: float | None = None  # rad/s
    gyro_z: float | None = None  # rad/s
    mag_x: float | None = None  # µT
    mag_y: float | None = None  # µT
    mag_z: float | None = None  # µT
    calibration_status: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TofReading(BaseModel):
    """Time-of-Flight sensor reading"""

    distance: float | None = None  # millimeters
    signal_strength: float | None = None
    ambient_light: float | None = None
    range_status: str | None = None  # "valid", "wrap_around", "signal_fail", etc.
    sensor_side: str  # "left" or "right"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EnvironmentalReading(BaseModel):
    """Environmental sensor (BME280) reading"""

    temperature: float | None = None  # °C
    humidity: float | None = None  # %RH
    pressure: float | None = None  # hPa
    altitude: float | None = None  # meters (calculated from pressure)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PowerReading(BaseModel):
    """Power monitoring (INA3221) reading"""

    battery_voltage: float | None = None  # V
    battery_current: float | None = None  # A
    battery_power: float | None = None  # W
    solar_voltage: float | None = None  # V
    solar_current: float | None = None  # A
    solar_power: float | None = None  # W
    solar_yield_today_wh: float | None = None  # Wh (daily yield from Victron)
    battery_consumed_today_wh: float | None = None  # Wh (accumulated load consumption today)
    load_voltage: float | None = None  # V (if applicable)
    load_current: float | None = None  # A (if applicable)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SensorData(BaseModel):
    """Complete sensor data snapshot"""

    gps: GpsReading | None = None
    imu: ImuReading | None = None
    tof_left: TofReading | None = None
    tof_right: TofReading | None = None
    environmental: EnvironmentalReading | None = None
    power: PowerReading | None = None
    sensor_health: dict[SensorType, SensorStatus] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    hardware_baseline_id: str | None = None  # Reference to hardware configuration

    model_config = ConfigDict(use_enum_values=True)
