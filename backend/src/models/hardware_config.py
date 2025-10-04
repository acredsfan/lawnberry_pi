from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class GPSType(str, Enum):
    ZED_F9P_USB = "zed-f9p-usb"
    NEO_8M_UART = "neo-8m-uart"


class IMUType(str, Enum):
    BNO085_UART = "bno085-uart"


class MotorControllerType(str, Enum):
    ROBOHAT_RP2040 = "robohat-rp2040"
    L298N = "l298n"


class BladeControllerType(str, Enum):
    ROBOHAT_RP2040 = "robohat-rp2040"
    IBT_4 = "ibt-4"


class HardwareConfig(BaseModel):
    """Declares physical hardware modules present in the system.

    Loaded from config/hardware.yaml at startup (FR-003).
    """

    gps_type: Optional[GPSType] = Field(default=None)
    gps_ntrip_enabled: bool = Field(default=False)
    imu_type: Optional[IMUType] = Field(default=None)
    tof_sensors: List[str] = Field(default_factory=list, description="ToF sensor positions e.g. ['left','right']")
    env_sensor: bool = Field(default=False, description="BME280 present")
    power_monitor: bool = Field(default=False, description="INA3221 present")
    motor_controller: Optional[MotorControllerType] = Field(default=None)
    blade_controller: Optional[BladeControllerType] = Field(default=None)
    camera_enabled: bool = Field(default=False)

    @field_validator("gps_ntrip_enabled")
    @classmethod
    def ntrip_requires_zed_f9p(cls, v: bool, info):
        if v:
            gps_type = info.data.get("gps_type")
            if gps_type != GPSType.ZED_F9P_USB:
                raise ValueError("NTRIP corrections require ZED-F9P GPS")
        return v

    @field_validator("motor_controller")
    @classmethod
    def motor_controller_required(cls, v: Optional[MotorControllerType]):
        # System requires a motor controller for motion; allow None for SIM_MODE setups.
        return v
