from __future__ import annotations

"""CoveragePattern model (T070).

Parallel-line coverage representation for a zone.
"""

from typing import List, Tuple
from pydantic import BaseModel, Field, field_validator


class CoveragePattern(BaseModel):
    pattern_id: str
    zone_id: str
    # Each line is a pair of waypoints ((lat1, lon1), (lat2, lon2)) in degrees
    lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = Field(default_factory=list)
    cutting_width_m: float = Field(0.4, gt=0.0)
    overlap_m: float = Field(0.05, ge=0.0)
    coverage_percentage: float = Field(0.0, ge=0.0, le=100.0)
    estimated_duration_s: float = Field(0.0, ge=0.0)

    @field_validator("lines")
    @classmethod
    def _validate_lines(cls, v: List[Tuple[Tuple[float, float], Tuple[float, float]]]):
        for seg in v:
            if len(seg) != 2:
                raise ValueError("each line must contain 2 waypoints")
            for lat, lon in seg:
                if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
                    raise ValueError("waypoint coordinates out of bounds")
        return v
