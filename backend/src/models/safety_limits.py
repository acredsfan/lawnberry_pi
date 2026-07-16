from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

BOOTSTRAP_SENSOR_POLL_INTERVAL_S = 0.20


def heading_bootstrap_stop_reserve_m(
    *,
    speed_mps: float,
    command_ttl_ms: int,
    braking_decel_mps2: float,
    poll_interval_s: float = BOOTSTRAP_SENSOR_POLL_INTERVAL_S,
) -> float:
    """Worst-case distance after the latest GPS sample before a lease can stop."""
    speed = max(0.0, float(speed_mps))
    latency_s = max(0.0, float(command_ttl_ms) / 1000.0) + max(
        0.0, float(poll_interval_s)
    )
    braking_m = (speed * speed) / (2.0 * max(float(braking_decel_mps2), 1e-6))
    return speed * latency_s + braking_m


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
    geofence_buffer_meters: float = Field(
        default=0.05,
        ge=0,
        description="Additional inset applied when generating the safe boundary.",
    )
    high_temperature_celsius: float = Field(default=80.0)
    tof_obstacle_distance_meters: float = Field(default=0.2)
    obstacle_detection_latency_s: float = Field(default=0.35, gt=0)
    obstacle_conservative_deceleration_mps2: float = Field(default=0.45, gt=0)
    obstacle_front_offset_m: float = Field(
        default=0.25,
        ge=0,
        description=(
            "Center-to-front sensor geometry; diagnostic only and not added to front-sensor range."
        ),
    )
    obstacle_fixed_margin_m: float = Field(default=0.10, ge=0)
    obstacle_min_clearance_m: float = Field(default=0.15, gt=0)
    obstacle_stale_sample_timeout_s: float = Field(default=0.25, gt=0)
    obstacle_conservative_unknown_speed_mps: float = Field(default=0.4, gt=0)
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
    supervised_test_enabled: bool = Field(
        default=False,
        description=(
            "Explicit local enable for supervised blade-test permit issuance. Disabled until "
            "the operator approves physical bounds and test controls."
        ),
    )
    supervised_test_permit_ttl_s: int = Field(
        default=0,
        ge=0,
        description="Monotonic time allowed to activate a newly issued supervised-test permit.",
    )
    supervised_test_max_duration_s: int = Field(
        default=0,
        ge=0,
        description="Maximum active lifetime of one supervised blade test.",
    )
    supervised_test_max_speed_mps: float = Field(
        default=0.0,
        ge=0,
        description="Physical speed ceiling for qualification-only drive commands.",
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
    bootstrap_min_travel_m: float = Field(
        default=0.25,
        gt=0,
        description="Minimum measured antenna travel required to accept heading bootstrap.",
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

    @model_validator(mode="after")
    def validate_heading_bootstrap_budget(self):
        if self.supervised_test_enabled:
            if (
                self.supervised_test_permit_ttl_s <= 0
                or self.supervised_test_max_duration_s <= 0
                or self.supervised_test_max_speed_mps <= 0
            ):
                raise ValueError(
                    "enabled supervised testing requires positive permit TTL, duration, and speed bounds"
                )
            if self.supervised_test_max_speed_mps > self.bootstrap_speed_mps:
                raise ValueError(
                    "supervised_test_max_speed_mps cannot exceed the existing blade-off "
                    "bootstrap speed ceiling"
                )
        reserve_m = heading_bootstrap_stop_reserve_m(
            speed_mps=self.bootstrap_speed_mps,
            command_ttl_ms=self.autonomous_command_ttl_ms,
            braking_decel_mps2=self.autonomous_braking_decel_mps2,
        )
        if self.bootstrap_min_travel_m + reserve_m >= self.bootstrap_max_travel_m:
            raise ValueError(
                "bootstrap_min_travel_m plus lease/braking reserve must be less than "
                "bootstrap_max_travel_m"
            )
        return self
