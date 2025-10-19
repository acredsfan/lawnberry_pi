from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class Ina3221Config(BaseModel):
    address: Optional[int] = Field(default=None, description="I2C address override for INA3221")
    bus: Optional[int] = Field(default=None, description="I2C bus override for INA3221")
    shunt_ohms_ch1: Optional[float] = Field(default=None, description="Override shunt resistance for channel 1 (solar)")
    shunt_ohms_ch2: Optional[float] = Field(default=None, description="Override shunt resistance for channel 2")
    shunt_ohms_ch3: Optional[float] = Field(default=None, description="Override shunt resistance for channel 3 (battery)")
    shunt_spec_ch1: Optional[str] = Field(default=None, description="Channel 1 shunt spec, e.g. '30A/75mV'")
    shunt_spec_ch2: Optional[str] = Field(default=None, description="Channel 2 shunt spec, e.g. '5A/50mV'")
    shunt_spec_ch3: Optional[str] = Field(default=None, description="Channel 3 shunt spec, e.g. '50A/75mV'")


class GPSType(str, Enum):
    ZED_F9P_USB = "zed-f9p-usb"
    ZED_F9P_UART = "zed-f9p-uart"
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
    # Optional typed ToF configuration (sensors.tof_config in hardware.yaml)
    tof_config: Optional["ToFConfig"] = Field(default=None)
    # Optional INA3221 configuration overrides (ina3221 block in hardware.yaml)
    ina3221_config: Optional[Ina3221Config] = Field(default=None)

    @field_validator("gps_ntrip_enabled")
    @classmethod
    def ntrip_requires_zed_f9p(cls, v: bool, info):
        if v:
            gps_type = info.data.get("gps_type")
            if gps_type not in {GPSType.ZED_F9P_USB, GPSType.ZED_F9P_UART}:
                raise ValueError("NTRIP corrections require ZED-F9P GPS")
        return v

    @field_validator("motor_controller")
    @classmethod
    def motor_controller_required(cls, v: Optional[MotorControllerType]):
        # System requires a motor controller for motion; allow None for SIM_MODE setups.
        return v


class ToFConfig(BaseModel):
    bus: Optional[int] = Field(default=1)
    left_address: Optional[int] = Field(default=0x29)
    right_address: Optional[int] = Field(default=0x30)
    ranging_mode: Optional[str] = Field(default="better_accuracy")
    left_shutdown_gpio: Optional[int] = Field(default=None)
    right_shutdown_gpio: Optional[int] = Field(default=None)
    timing_budget_us: Optional[int] = Field(default=None)

