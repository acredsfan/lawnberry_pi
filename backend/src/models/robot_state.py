"""RobotState model capturing canonical mower state.

Follows Phase 1 T016 requirements with platform-agnostic fields and
Pydantic v2 conventions. All fields are optional unless otherwise required
by downstream contracts. This model is intended for REST/WS serialization.
"""
from __future__ import annotations

import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from .safety_interlock import SafetyInterlock


class NavigationMode(str, Enum):
    IDLE = "IDLE"
    MANUAL = "MANUAL"
    AUTONOMOUS = "AUTONOMOUS"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class Position(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = None
    accuracy_m: float | None = None

    @field_validator("latitude")
    @classmethod
    def _lat_range(cls, v: float | None) -> float | None:
        if v is None:
            return v
        if not (-90.0 <= v <= 90.0):
            raise ValueError("latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def _lng_range(cls, v: float | None) -> float | None:
        if v is None:
            return v
        if not (-180.0 <= v <= 180.0):
            raise ValueError("longitude must be between -180 and 180")
        return v


class Orientation(BaseModel):
    roll_deg: float | None = None
    pitch_deg: float | None = None
    yaw_deg: float | None = None


class BatteryState(BaseModel):
    percentage: float | None = Field(default=None, ge=0.0, le=100.0)
    voltage_v: float | None = None
    current_a: float | None = None


class SensorReadings(BaseModel):
    imu_calibration: int | None = None
    tof_left_m: float | None = None
    tof_right_m: float | None = None
    temperature_c: float | None = None


class RobotState(BaseModel):
    position: Position = Field(default_factory=Position)
    heading_deg: float | None = None
    velocity_mps: float | None = None
    angular_velocity_dps: float | None = None
    orientation: Orientation = Field(default_factory=Orientation)
    navigation_mode: NavigationMode = NavigationMode.IDLE
    active_interlocks: list[SafetyInterlock] = Field(default_factory=list)
    battery: BatteryState = Field(default_factory=BatteryState)
    sensors: SensorReadings = Field(default_factory=SensorReadings)
    # Navigation-state adjuncts used by /api/v2/nav/status
    current_waypoint_id: str | None = None
    distance_to_waypoint_m: float | None = None
    inside_geofence: bool | None = None
    last_updated: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC)
    )

    def touch(self) -> None:
        """Update the timestamp to now (UTC)."""
        self.last_updated = datetime.datetime.now(datetime.UTC)
