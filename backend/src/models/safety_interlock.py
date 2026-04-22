from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class InterlockType(str, Enum):
    EMERGENCY_STOP = "emergency_stop"
    TILT_DETECTED = "tilt_detected"
    LOW_BATTERY = "low_battery"
    GEOFENCE_VIOLATION = "geofence_violation"
    WATCHDOG_TIMEOUT = "watchdog_timeout"
    HIGH_TEMPERATURE = "high_temperature"
    OBSTACLE_DETECTED = "obstacle_detected"


class InterlockState(str, Enum):
    ACTIVE = "active"
    CLEARED_PENDING_ACK = "cleared_pending_ack"
    ACKNOWLEDGED = "acknowledged"


class SafetyInterlock(BaseModel):
    interlock_id: str
    interlock_type: InterlockType
    triggered_at_us: int
    cleared_at_us: int | None = None
    acknowledged_at_us: int | None = None
    state: InterlockState = Field(default=InterlockState.ACTIVE)
    trigger_value: float | None = None
    description: str = ""
