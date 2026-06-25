from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictHardwareModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Ina3221Config(StrictHardwareModel):
    address: int | None = Field(default=None, description="I2C address override for INA3221")
    bus: int | None = Field(default=None, description="I2C bus override for INA3221")
    shunt_ohms_ch1: float | None = Field(
        default=None, description="Override shunt resistance for channel 1 (solar)"
    )
    shunt_ohms_ch2: float | None = Field(
        default=None, description="Override shunt resistance for channel 2"
    )
    shunt_ohms_ch3: float | None = Field(
        default=None, description="Override shunt resistance for channel 3 (battery)"
    )
    shunt_spec_ch1: str | None = Field(
        default=None, description="Channel 1 shunt spec, e.g. '30A/75mV'"
    )
    shunt_spec_ch2: str | None = Field(
        default=None, description="Channel 2 shunt spec, e.g. '5A/50mV'"
    )
    shunt_spec_ch3: str | None = Field(
        default=None, description="Channel 3 shunt spec, e.g. '50A/75mV'"
    )
    battery_voltage_offset_v: float = Field(
        default=0.0, description="Additive calibration offset for battery (ch3) bus voltage reading"
    )
    battery_voltage_scale: float = Field(
        default=1.0, description="Multiplicative scale for battery bus voltage"
    )
    solar_voltage_offset_v: float = Field(
        default=0.0, description="Additive calibration offset for solar (ch1) bus voltage reading"
    )
    solar_voltage_scale: float = Field(
        default=1.0, description="Multiplicative scale for solar bus voltage"
    )
    solar_current_scale: float = Field(
        default=1.0, description="Multiplicative scale for solar current (use -1.0 to invert sign when shunt IN+/IN- are reversed)"
    )
    battery_current_offset_a: float = Field(
        default=0.0, description="Additive offset for battery current reading"
    )


class VictronBleConfig(StrictHardwareModel):
    enabled: bool = Field(default=True, description="Enable Victron SmartSolar BLE reader")
    device_id: str | None = Field(
        default=None, description="Victron identifier or MAC address for BLE connection"
    )
    device_key: str | None = Field(
        default=None,
        description="Optional combined '<address>@<key>' string accepted by victron-ble CLI",
    )
    encryption_key: str | None = Field(
        default=None,
        description="Victron Instant Readout encryption key; combined with device_id when device_key not provided",
    )
    cli_path: str = Field(default="victron-ble", description="victron-ble CLI executable path")
    adapter: str | None = Field(
        default=None, description="Optional BLE adapter (passed as --adapter)"
    )
    read_timeout_s: float = Field(
        default=8.0, description="Timeout for BLE read command in seconds"
    )
    prefer_battery: bool = Field(
        default=False,
        description="Prefer Victron telemetry for battery voltage/current/power when merging with INA3221",
    )
    prefer_solar: bool = Field(
        default=False,
        description="Prefer Victron telemetry for solar metrics when merging with INA3221",
    )
    prefer_load: bool = Field(
        default=False,
        description="Prefer Victron telemetry for load current when merging with INA3221",
    )
    sample_limit: int = Field(
        default=1,
        ge=1,
        description="Number of victron-ble frames to collect per poll before returning the most recent",
    )
    yield_today_unit: str = Field(
        default="wh",
        description="Unit reported by victron-ble for yield_today; expected 'wh' or 'kwh'.",
    )
    solar_panel_max_wh: float = Field(
        default=1000.0,
        gt=0.0,
        description="Physical daily-yield sanity limit used when interpreting Victron telemetry.",
    )

    @field_validator("yield_today_unit")
    @classmethod
    def validate_yield_today_unit(cls, value: str) -> str:
        normalized = str(value).strip().lower()
        if normalized not in {"wh", "kwh"}:
            raise ValueError("yield_today_unit must be 'wh' or 'kwh'")
        return normalized


class Bme280Config(StrictHardwareModel):
    enabled: bool = Field(default=True, description="Whether BME280 environmental sensing is enabled")
    address: int | None = Field(default=0x76, description="I2C address for BME280")
    bus: int | None = Field(default=1, description="I2C bus for BME280")
    sea_level_hpa: float = Field(
        default=1013.25,
        gt=0.0,
        description="Sea-level pressure reference used for altitude estimation.",
    )


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


class BladePinsConfig(StrictHardwareModel):
    in1: int = Field(default=24, ge=0, description="GPIO number wired to IBT-4 IN1")
    in2: int = Field(default=25, ge=0, description="GPIO number wired to IBT-4 IN2")


class BladeConfig(StrictHardwareModel):
    controller: BladeControllerType | None = Field(
        default=None,
        description="Configured physical blade controller backend.",
    )
    allow_autonomous: bool = Field(
        default=False,
        description="Whether this configured backend is approved for autonomous mowing.",
    )
    spinup_seconds: float = Field(default=2.0, ge=0.0)
    shutdown_timeout_seconds: float = Field(default=1.0, gt=0.0)
    command_ack_timeout_seconds: float = Field(default=0.5, gt=0.0)
    pins: BladePinsConfig = Field(default_factory=BladePinsConfig)


class BatteryConfig(StrictHardwareModel):
    """Battery pack specification.

    Used for voltage-to-SOC estimation and runtime calculations.
    Set these values in the ``battery:`` section of ``config/hardware.yaml``
    to match your actual battery pack.

    Defaults match the standard LawnBerry Pi build:
    LiFePO4 12.8 V nominal, 30 Ah / 384 Wh.
    """

    chemistry: str = Field(
        default="lifepo4",
        description="Battery chemistry: 'lifepo4' (default) or any string for linear model fallback.",
    )
    capacity_ah: float = Field(
        default=30.0,
        gt=0,
        description="Total rated capacity in Amp-hours (e.g. 384 Wh / 12.8 V = 30 Ah).",
    )
    capacity_wh: float = Field(
        default=384.0,
        gt=0,
        description="Total rated capacity in Watt-hours.",
    )
    nominal_voltage: float = Field(
        default=12.8,
        gt=0,
        description="Nominal pack voltage (e.g. 12.8 V for 4S LiFePO4).",
    )
    min_voltage: float = Field(
        default=10.0,
        gt=0,
        description="Absolute discharge cutoff voltage — maps to 0 % SOC.",
    )
    max_voltage: float = Field(
        default=14.6,
        gt=0,
        description="Full-charge voltage — maps to 100 % SOC (e.g. 14.6 V for 4S LiFePO4).",
    )


class ToFConfig(StrictHardwareModel):
    bus: int | None = Field(default=1)
    left_address: int | None = Field(default=0x29)
    right_address: int | None = Field(default=0x30)
    ranging_mode: str | None = Field(default="better_accuracy")
    left_shutdown_gpio: int | None = Field(default=None)
    right_shutdown_gpio: int | None = Field(default=None)
    left_interrupt_gpio: int | None = Field(default=None)
    right_interrupt_gpio: int | None = Field(default=None)
    timing_budget_us: int | None = Field(default=None)


class HardwareConfig(StrictHardwareModel):
    """Declares physical hardware modules present in the system.

    Loaded from config/hardware.yaml at startup (FR-003).
    """

    gps_type: GPSType | None = Field(default=None)
    gps_ntrip_enabled: bool = Field(default=False)
    gps_usb_device: str | None = Field(
        default=None, description="Serial device for GPS (e.g. /dev/lawnberry-gps)"
    )
    gps_antenna_offset_forward_m: float = Field(
        default=0.0,
        description=(
            "GPS antenna offset from the mower navigation point in meters. "
            "Positive is forward; negative is behind. Applied with heading to navigate "
            "from the mower point instead of the antenna point."
        ),
    )
    gps_antenna_offset_right_m: float = Field(
        default=0.0,
        description=(
            "GPS antenna offset from the mower navigation point in meters. "
            "Positive is right; negative is left."
        ),
    )
    imu_type: IMUType | None = Field(default=None)
    imu_port: str | None = Field(
        default=None, description="Serial port for IMU (e.g. /dev/ttyAMA4)"
    )
    imu_yaw_offset_degrees: float = Field(
        default=0.0,
        description=(
            "Degrees added to raw IMU yaw before use in navigation. "
            "Set to 180 if the IMU chip X-axis is mounted facing backward relative to mower forward."
        ),
    )
    encoder_enabled: bool = Field(
        default=True,
        description=(
            "Set false if wheel encoders are missing or unreliable. "
            "When false, encoder_feedback_ok is suppressed in telemetry and odometry falls back to velocity integration."
        ),
    )
    tof_sensors: list[str] = Field(
        default_factory=list, description="ToF sensor positions e.g. ['left','right']"
    )
    env_sensor: bool = Field(default=False, description="BME280 present")
    power_monitor: bool = Field(default=False, description="INA3221 present")
    motor_controller: MotorControllerType | None = Field(default=None)
    motor_controller_port: str | None = Field(
        default=None,
        description="Optional explicit RoboHAT serial path; null keeps safe discovery enabled.",
    )
    blade_controller: BladeControllerType | None = Field(default=None)
    blade: BladeConfig = Field(default_factory=BladeConfig)
    camera_enabled: bool = Field(default=False)
    # Optional typed ToF configuration (sensors.tof_config in hardware.yaml)
    tof_config: ToFConfig | None = Field(default=None)
    # Optional INA3221 configuration overrides (ina3221 block in hardware.yaml)
    ina3221_config: Ina3221Config | None = Field(default=None)
    bme280_config: Bme280Config | None = Field(default=None)
    # Optional Victron SmartSolar BLE configuration
    victron_config: VictronBleConfig | None = Field(default=None)
    # Battery pack specification — used for SOC estimation and runtime calcs
    battery_config: BatteryConfig = Field(default_factory=BatteryConfig)

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
    def motor_controller_required(cls, v: MotorControllerType | None):
        # System requires a motor controller for motion; allow None for SIM_MODE setups.
        return v
