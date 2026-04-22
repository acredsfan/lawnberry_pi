from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ZoneType(str, Enum):
    MOW_ZONE = "mow_zone"
    EXCLUSION_ZONE = "exclusion_zone"
    CHARGING_STATION = "charging_station"
    FLOWER_BED = "flower_bed"
    TREE_AREA = "tree_area"
    WATER_FEATURE = "water_feature"
    BOUNDARY = "boundary"


class Point(BaseModel):
    """Geographic coordinate point."""

    latitude: float
    longitude: float
    altitude: float | None = None


class ZoneSettings(BaseModel):
    """Zone-specific mowing settings."""

    cutting_height_mm: int | None = None
    cutting_pattern: str = "parallel"  # "parallel", "spiral", "random"
    cutting_speed_ms: float | None = None
    overlap_factor: float = 0.1
    avoid_wet_grass: bool = True


class ZoneStatistics(BaseModel):
    """Zone usage and maintenance statistics."""

    total_mows: int = 0
    last_mowed: datetime | None = None
    average_mow_time_minutes: float | None = None
    total_area_covered_sqm: float = 0.0
    grass_growth_rate: str | None = None  # "slow", "medium", "fast"


class MarkerTriggerSet(BaseModel):
    """Trigger flags determining when a marker should be visited."""

    needs_charge: bool = False
    precipitation: bool = False
    manual_override: bool = False


class MarkerTimeWindow(BaseModel):
    """Allowed time window in 24h HH:MM format."""

    start: str
    end: str

    @field_validator("start", "end")
    def validate_clock_format(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Time must be a string")
        parts = value.split(":")
        if len(parts) != 2:
            raise ValueError("Time must be in HH:MM format")
        hour, minute = parts
        if not (hour.isdigit() and minute.isdigit()):
            raise ValueError("Time must be numeric HH:MM")
        h = int(hour)
        m = int(minute)
        if h < 0 or h > 23 or m < 0 or m > 59:
            raise ValueError("Time values out of range")
        return f"{h:02d}:{m:02d}"


class MarkerSchedule(BaseModel):
    """Structured schedule definition for a marker."""

    time_windows: list[MarkerTimeWindow] = Field(default_factory=list)
    days_of_week: list[int] = Field(default_factory=list)  # 0 = Sunday
    triggers: MarkerTriggerSet = Field(default_factory=MarkerTriggerSet)

    @field_validator("days_of_week")
    def validate_days(cls, value: list[int]) -> list[int]:
        for day in value:
            if day < 0 or day > 6:
                raise ValueError("days_of_week must be between 0 (Sunday) and 6 (Saturday)")
        return value


class Zone(BaseModel):
    """Geographic zone definition for mowing areas."""

    # Zone identification
    id: str
    name: str
    zone_type: ZoneType = ZoneType.MOW_ZONE

    # Geographic definition
    polygon: list[Point] = Field(min_length=3)  # At least 3 points for a polygon
    area_sqm: float | None = None
    perimeter_m: float | None = None

    # Zone properties
    priority: int = Field(default=1, ge=1, le=10)
    enabled: bool = True
    exclusion_zone: bool = False  # Backward compatibility

    # Mowing configuration
    settings: ZoneSettings | None = None

    # Schedule preferences
    preferred_mow_times: list[str] = Field(default_factory=list)  # ["08:00", "14:00"]
    avoid_days: list[int] = Field(default_factory=list)  # Days of week to avoid

    # Environmental conditions
    sun_exposure: str | None = None  # "full_sun", "partial_shade", "full_shade"
    grass_type: str | None = None
    soil_type: str | None = None
    slope_angle_degrees: float | None = None

    # Statistics and history
    statistics: ZoneStatistics | None = None

    # Metadata
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    custom_properties: dict[str, Any] = Field(default_factory=dict)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("polygon")
    def validate_polygon(cls, v):
        if len(v) < 3:
            raise ValueError("Polygon must have at least 3 points")
        return v

    @field_validator("priority")
    def validate_priority(cls, v):
        if not (1 <= v <= 10):
            raise ValueError("Priority must be between 1 and 10")
        return v

    model_config = ConfigDict(use_enum_values=True)


class MarkerType(str, Enum):
    """Special marker types for map configuration"""

    HOME = "home"
    AM_SUN = "am_sun"
    PM_SUN = "pm_sun"
    CUSTOM = "custom"


class MapMarker(BaseModel):
    """Special marker on the map"""

    marker_id: str
    marker_type: MarkerType
    position: Point
    label: str | None = None
    icon: str | None = None  # Icon identifier for UI rendering
    # Optional scheduling or conditions: e.g., {"use_when": "am|pm|rain|always", "time_window": {"start":"08:00","end":"11:00"}}
    metadata: dict[str, Any] = Field(default_factory=dict)
    schedule: MarkerSchedule | None = None
    is_primary_home: bool = False


class MapProvider(str, Enum):
    """Map provider options"""

    GOOGLE_MAPS = "google_maps"
    OSM = "osm"  # OpenStreetMap fallback


class MapConfiguration(BaseModel):
    """Persisted geospatial definition for mowing area"""

    config_id: str
    config_version: int = 1

    # Map provider
    provider: MapProvider = MapProvider.GOOGLE_MAPS
    provider_metadata: dict[str, Any] = Field(default_factory=dict)

    # Zones and boundaries
    boundary_zone: Zone | None = None  # Primary yard boundary
    exclusion_zones: list[Zone] = Field(default_factory=list)
    mowing_zones: list[Zone] = Field(default_factory=list)

    # Special markers
    markers: list[MapMarker] = Field(default_factory=list)

    # Map view settings
    center_point: Point | None = None
    zoom_level: int = 18
    map_rotation_deg: float = 0.0

    # Validation and metadata
    validation_errors: list[str] = Field(default_factory=list)
    last_modified: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(use_enum_values=True)

    def add_marker(
        self, marker_type: MarkerType, position: Point, label: str | None = None
    ) -> MapMarker:
        """Add a special marker to the map"""
        import uuid

        marker_id = str(uuid.uuid4())
        marker = MapMarker(
            marker_id=marker_id,
            marker_type=marker_type,
            position=position,
            label=label or marker_type.value,
        )
        self.markers.append(marker)
        self.last_modified = datetime.now(UTC)
        return marker

    def get_marker(self, marker_type: MarkerType) -> MapMarker | None:
        """Get marker by type"""
        return next((m for m in self.markers if m.marker_type == marker_type), None)

    def add_exclusion_zone(self, zone: Zone) -> bool:
        """Add exclusion zone with overlap validation"""
        # Check for overlaps with existing zones (basic validation)
        if self.boundary_zone and not self._is_within_boundary(zone):
            self.validation_errors.append(f"Exclusion zone {zone.id} extends outside boundary")
            return False

        # Check for overlaps with other exclusion zones
        for existing_zone in self.exclusion_zones:
            if self._zones_overlap(zone, existing_zone):
                self.validation_errors.append(
                    f"Exclusion zone {zone.id} overlaps with {existing_zone.id}"
                )
                return False

        self.exclusion_zones.append(zone)
        self.last_modified = datetime.now(UTC)
        return True

    def _is_within_boundary(self, zone: Zone) -> bool:
        """Check if zone is within boundary (simplified check)"""
        if not self.boundary_zone:
            return True

        # Simplified: check if all zone points are roughly within boundary
        # Real implementation would use shapely or similar library
        try:
            from shapely.geometry import Point as ShapelyPoint
            from shapely.geometry import Polygon as ShapelyPolygon

            boundary_coords = [(p.longitude, p.latitude) for p in self.boundary_zone.polygon]
            boundary_poly = ShapelyPolygon(boundary_coords)

            zone_coords = [(p.longitude, p.latitude) for p in zone.polygon]
            zone_poly = ShapelyPolygon(zone_coords)

            return boundary_poly.contains(zone_poly)
        except ImportError:
            # If shapely not available, skip validation
            return True

    def _zones_overlap(self, zone1: Zone, zone2: Zone) -> bool:
        """Check if two zones overlap (requires shapely for accurate check)"""
        try:
            from shapely.geometry import Polygon as ShapelyPolygon

            zone1_coords = [(p.longitude, p.latitude) for p in zone1.polygon]
            zone2_coords = [(p.longitude, p.latitude) for p in zone2.polygon]

            poly1 = ShapelyPolygon(zone1_coords)
            poly2 = ShapelyPolygon(zone2_coords)

            return poly1.intersects(poly2)
        except ImportError:
            # If shapely not available, assume no overlap (conservative)
            return False

    def validate_configuration(self) -> bool:
        """Validate complete map configuration"""
        self.validation_errors = []

        # Require boundary zone
        if not self.boundary_zone:
            self.validation_errors.append("Boundary zone is required")
            return False

        # Validate all exclusion zones
        for zone in self.exclusion_zones:
            if not self._is_within_boundary(zone):
                self.validation_errors.append(f"Exclusion zone {zone.id} outside boundary")

        # Check for marker overlaps (basic validation)
        marker_types = [m.marker_type for m in self.markers]
        # HOME marker is strongly recommended for navigation, but keep advisory-only
        if MarkerType.HOME not in marker_types:
            self.validation_errors.append("Missing recommended marker: home")

        fatal_errors = [
            msg
            for msg in self.validation_errors
            if not msg.lower().startswith("missing recommended marker")
        ]
        return len(fatal_errors) == 0
