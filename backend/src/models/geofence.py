from __future__ import annotations

"""Geofence model (T057).

Fields:
- geofence_id: unique identifier
- boundary: array of lat/lon vertices (ordered polygon, first != last)
- buffer_distance_m: buffer in meters around the boundary used for enforcement
- violation_count: number of detected geofence violations

Notes:
- Independent of map zone models; minimal surface for navigation enforcement.
- Keep validators lightweight and Pydantic v2 compatible.
"""

from pydantic import BaseModel, Field, field_validator


class LatLng(BaseModel):
    latitude: float
    longitude: float

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


class Geofence(BaseModel):
    geofence_id: str
    boundary: list[LatLng] = Field(default_factory=list, description="Ordered polygon vertices")
    buffer_distance_m: float = Field(0.0, ge=0.0)
    violation_count: int = Field(0, ge=0)

    @field_validator("boundary")
    @classmethod
    def _validate_boundary(cls, v: list[LatLng]) -> list[LatLng]:
        # Require at least 3 vertices for a polygon
        if len(v) < 3:
            raise ValueError("boundary must contain at least 3 vertices")
        # Disallow first == last to avoid duplicate closing vertex; renderer can close implicitly
        if v[0].latitude == v[-1].latitude and v[0].longitude == v[-1].longitude:
            raise ValueError("boundary must not repeat the first vertex as the last element")
        return v
