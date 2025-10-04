from __future__ import annotations

"""Generic SensorReadingV2 model (T044).

This complements existing domain-specific models by providing a simple
container for raw sensor observations suitable for persistence/diagnostics.

Fields:
- sensor_id: string identifier (e.g., "imu", "gps", "tof_left")
- timestamp_us: integer microseconds since epoch
- value: arbitrary JSON-serializable payload (number/str/dict)
- unit: optional unit string
- quality_indicator: optional 0..1 score or categorical string
"""

from typing import Any
from pydantic import BaseModel, Field, field_validator


class SensorReadingV2(BaseModel):
    sensor_id: str
    timestamp_us: int = Field(ge=0)
    value: Any
    unit: str | None = None
    quality_indicator: float | str | None = None

    @field_validator("sensor_id")
    @classmethod
    def _validate_sensor_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("sensor_id must be non-empty")
        return v.strip()

    @field_validator("quality_indicator")
    @classmethod
    def _validate_quality(cls, v):
        if isinstance(v, (int, float)):
            vf = float(v)
            if vf < 0.0 or vf > 1.0:
                raise ValueError("quality_indicator numeric must be between 0 and 1")
        return v
