from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PowerSource(str, Enum):
    BATTERY = "battery"
    CHARGING = "charging"
    EXTERNAL = "external"


class BatteryHealth(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


class PowerReading(BaseModel):
    """Power system readings and battery status."""

    # Battery status
    battery_voltage: float | None = None
    battery_current_a: float | None = None
    battery_percentage: float | None = None
    battery_health: BatteryHealth | None = None

    # Charging status
    charging_active: bool = False
    charging_voltage: float | None = None
    charging_current_a: float | None = None

    # Power consumption
    total_power_w: float | None = None
    motor_power_w: float | None = None
    blade_power_w: float | None = None
    system_power_w: float | None = None

    # Power source
    active_source: PowerSource = PowerSource.BATTERY

    # Temperature monitoring
    battery_temp_c: float | None = None
    controller_temp_c: float | None = None

    # Runtime estimates
    estimated_runtime_minutes: int | None = None
    time_to_full_charge_minutes: int | None = None

    # Alerts
    low_battery_alert: bool = False
    critical_battery_alert: bool = False
    overheating_alert: bool = False

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("battery_percentage")
    def validate_percentage(cls, v):
        if v is not None and not (0.0 <= v <= 100.0):
            raise ValueError("Battery percentage must be between 0.0 and 100.0")
        return v

    @field_validator("battery_voltage", "charging_voltage")
    def validate_voltage(cls, v):
        if v is not None and v < 0:
            raise ValueError("Voltage values must be non-negative")
        return v

    model_config = ConfigDict(use_enum_values=True)
