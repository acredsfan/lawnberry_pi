"""Pydantic models for map configuration exposed to contract tests.

These models intentionally mirror the simplified schema used by the
contract/unit tests so the MapsService can validate and persist data in
memory or with a mocked persistence layer. The production persistence
path continues to use the richer Zone-based models stored in
``backend.src.models.zone``.  Having a dedicated module keeps the test
fixtures lightweight while still allowing the service to bridge the two
representations when necessary.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Dict

from pydantic import BaseModel, Field, field_validator


class LatLng(BaseModel):
    """Geographic coordinate point in degrees."""

    lat: float
    lng: float

    @field_validator("lat")
    def _validate_lat(cls, value: float) -> float:  # noqa: D401 - short validator
        if not -90.0 <= value <= 90.0:
            raise ValueError("Latitude must be between -90 and 90 degrees")
        return value

    @field_validator("lng")
    def _validate_lng(cls, value: float) -> float:  # noqa: D401 - short validator
        if not -180.0 <= value <= 180.0:
            raise ValueError("Longitude must be between -180 and 180 degrees")
        return value


class WorkingBoundary(BaseModel):
    """Closed polygon describing the working area."""

    polygon: List[LatLng]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("polygon")
    def _validate_polygon(cls, value: List[LatLng]) -> List[LatLng]:
        if len(value) < 3:
            raise ValueError("Boundary polygon must contain at least 3 points")
        return value


class ExclusionZone(BaseModel):
    """Polygon representing an area the mower should avoid."""

    zone_id: str
    name: str
    polygon: List[LatLng]
    metadata: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Marker(BaseModel):
    """Marker rendered on the map (e.g. charging station)."""

    marker_id: str
    name: str
    position: LatLng
    icon: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MapConfiguration(BaseModel):
    """Lightweight contract configuration consumed by unit/contract tests."""

    config_id: str
    provider: str = "leaflet"
    api_key: Optional[str] = None
    working_boundary: Optional[WorkingBoundary] = None
    exclusion_zones: List[ExclusionZone] = Field(default_factory=list)
    markers: List[Marker] = Field(default_factory=list)
    last_modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    validated: bool = False
    config_version: int = 1

    def touch(self) -> None:
        """Update the modification timestamp."""
        self.last_modified = datetime.now(timezone.utc)

    def add_exclusion_zone(self, zone: ExclusionZone) -> None:
        self.exclusion_zones.append(zone)
        self.touch()

    def add_marker(self, marker: Marker) -> None:
        self.markers.append(marker)
        self.touch()
