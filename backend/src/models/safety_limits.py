from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class SafetyLimits(BaseModel):
    """Defines constitutional safety thresholds and timeouts (FR-004)."""

    estop_latency_ms: int = Field(default=100, ge=1, description="Max E-stop response time")
    tilt_threshold_degrees: float = Field(default=30.0)
    tilt_cutoff_latency_ms: int = Field(default=200, ge=1)
    battery_low_voltage: float = Field(
        default=12.2,
        description=(
            "Pack voltage (V) at which the LOW_BATTERY safety interlock activates. "
            "For 4S LiFePO4 (12.8 V nominal) this corresponds to roughly 10 % SOC — "
            "enough remaining charge for the robot to return home safely. "
            "Raise this value if your yard is large or the battery capacity is small."
        ),
    )
    battery_critical_voltage: float = Field(
        default=11.8,
        description=(
            "Pack voltage (V) at which emergency stop is triggered. "
            "Must be strictly less than battery_low_voltage. "
            "For 4S LiFePO4 this is approximately 2–5 % SOC, just above the BMS protection cutoff."
        ),
    )
    motor_current_max_amps: float = Field(default=5.0)
    watchdog_timeout_ms: int = Field(default=1000, ge=1)
    geofence_buffer_meters: float = Field(default=0.5)
    high_temperature_celsius: float = Field(default=80.0)
    tof_obstacle_distance_meters: float = Field(default=0.2)

    @field_validator("estop_latency_ms")
    @classmethod
    def validate_estop_latency(cls, v: int):
        if v > 100:
            raise ValueError("estop_latency_ms must be ≤ 100 (constitutional)")
        return v

    @field_validator("tilt_cutoff_latency_ms")
    @classmethod
    def validate_tilt_cutoff_latency(cls, v: int):
        if v > 200:
            raise ValueError("tilt_cutoff_latency_ms must be ≤ 200 (constitutional)")
        return v

    @field_validator("battery_critical_voltage")
    @classmethod
    def critical_below_low(cls, v: float, info):
        low = info.data.get("battery_low_voltage", 12.2)
        if v >= low:
            raise ValueError("battery_critical_voltage must be < battery_low_voltage")
        return v
