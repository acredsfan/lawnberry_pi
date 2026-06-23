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
    autonomous_max_gps_accuracy_m: float = Field(
        default=0.25,
        gt=0,
        description="Maximum GPS accuracy allowed for autonomous drive authorization.",
    )
    autonomous_max_gps_fix_age_s: float = Field(
        default=2.0,
        gt=0,
        description="Maximum GPS fix age allowed for autonomous drive authorization.",
    )
    mower_footprint_radius_m: float = Field(
        default=0.35,
        gt=0,
        description="Conservative mower footprint radius used for geofence authorization.",
    )
    differential_drive_wheelbase_m: float = Field(
        default=0.30,
        gt=0,
        description="Canonical differential-drive wheelbase used by prediction guards.",
    )
    geofence_safety_allowance_m: float = Field(
        default=0.10,
        ge=0,
        description="Fixed geofence allowance added to footprint and uncertainty buffers.",
    )
    autonomous_prediction_horizon_s: float = Field(
        default=1.0,
        gt=0,
        description="Forward horizon for autonomous swept-motion geofence prediction.",
    )
    autonomous_command_ttl_ms: int = Field(
        default=350,
        ge=50,
        le=2000,
        description="TTL for mission drive commands sent through the command gateway.",
    )
    autonomous_braking_decel_mps2: float = Field(
        default=0.5,
        gt=0,
        description="Conservative braking capability used to estimate stopping distance.",
    )
    bootstrap_speed_mps: float = Field(
        default=0.20,
        gt=0,
        description="Low mission-start heading bootstrap speed.",
    )
    bootstrap_max_travel_m: float = Field(
        default=0.60,
        gt=0,
        description="Maximum blade-off heading-bootstrap travel before aborting.",
    )
    coverage_endpoint_clearance_m: float = Field(
        default=0.25,
        ge=0,
        description="Minimum clearance for coverage stripe endpoints and turns.",
    )
    max_operational_cross_track_error_m: float = Field(
        default=1.5,
        gt=0,
        description="Maximum lateral error before waypoint pursuit stops for recovery.",
    )

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
