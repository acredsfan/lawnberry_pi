from __future__ import annotations

"""NavigationWaypoint model (T043).

Fields:
- waypoint_id: unique identifier
- latitude: degrees (-90..90)
- longitude: degrees (-180..180)
- target_speed_mps: desired linear speed in m/s (>=0)
- arrival_threshold_m: distance threshold to mark reached (>0)
- reached: flag indicating arrival
- reached_at_ts: timestamp when reached

Notes:
- Keep independent from existing Waypoint model to avoid breaking existing APIs.
"""

from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class NavigationWaypoint(BaseModel):
    waypoint_id: str
    latitude: float
    longitude: float
    target_speed_mps: float = Field(0.5, ge=0.0)
    arrival_threshold_m: float = Field(0.5, gt=0.0)
    reached: bool = False
    reached_at_ts: datetime | None = None

    @field_validator("latitude")
    @classmethod
    def _validate_lat(cls, v: float) -> float:
        if not (-90.0 <= v <= 90.0):
            raise ValueError("latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def _validate_lon(cls, v: float) -> float:
        if not (-180.0 <= v <= 180.0):
            raise ValueError("longitude must be between -180 and 180")
        return v

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
