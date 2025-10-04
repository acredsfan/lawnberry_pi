from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class SafetyLimits(BaseModel):
    """Defines constitutional safety thresholds and timeouts (FR-004)."""

    estop_latency_ms: int = Field(default=100, ge=1, description="Max E-stop response time")
    tilt_threshold_degrees: float = Field(default=30.0)
    tilt_cutoff_latency_ms: int = Field(default=200, ge=1)
    battery_low_voltage: float = Field(default=10.0)
    battery_critical_voltage: float = Field(default=9.5)
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
        low = info.data.get("battery_low_voltage", 10.0)
        if v >= low:
            raise ValueError("battery_critical_voltage must be < battery_low_voltage")
        return v
