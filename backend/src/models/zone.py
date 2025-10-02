from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator


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
    altitude: Optional[float] = None


class ZoneSettings(BaseModel):
    """Zone-specific mowing settings."""
    cutting_height_mm: Optional[int] = None
    cutting_pattern: str = "parallel"  # "parallel", "spiral", "random"
    cutting_speed_ms: Optional[float] = None
    overlap_factor: float = 0.1
    avoid_wet_grass: bool = True
    

class ZoneStatistics(BaseModel):
    """Zone usage and maintenance statistics."""
    total_mows: int = 0
    last_mowed: Optional[datetime] = None
    average_mow_time_minutes: Optional[float] = None
    total_area_covered_sqm: float = 0.0
    grass_growth_rate: Optional[str] = None  # "slow", "medium", "fast"
    

class Zone(BaseModel):
    """Geographic zone definition for mowing areas."""
    
    # Zone identification
    id: str
    name: str
    zone_type: ZoneType = ZoneType.MOW_ZONE
    
    # Geographic definition
    polygon: List[Point] = Field(min_items=3)  # At least 3 points for a polygon
    area_sqm: Optional[float] = None
    perimeter_m: Optional[float] = None
    
    # Zone properties
    priority: int = Field(default=1, ge=1, le=10)
    enabled: bool = True
    exclusion_zone: bool = False  # Backward compatibility
    
    # Mowing configuration
    settings: Optional[ZoneSettings] = None
    
    # Schedule preferences
    preferred_mow_times: List[str] = Field(default_factory=list)  # ["08:00", "14:00"]
    avoid_days: List[int] = Field(default_factory=list)  # Days of week to avoid
    
    # Environmental conditions
    sun_exposure: Optional[str] = None  # "full_sun", "partial_shade", "full_shade"
    grass_type: Optional[str] = None
    soil_type: Optional[str] = None
    slope_angle_degrees: Optional[float] = None
    
    # Statistics and history
    statistics: Optional[ZoneStatistics] = None
    
    # Metadata
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    custom_properties: Dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @validator('polygon')
    def validate_polygon(cls, v):
        if len(v) < 3:
            raise ValueError('Polygon must have at least 3 points')
        return v
        
    @validator('priority')
    def validate_priority(cls, v):
        if not (1 <= v <= 10):
            raise ValueError('Priority must be between 1 and 10')
        return v
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}


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
    label: Optional[str] = None
    icon: Optional[str] = None  # Icon identifier for UI rendering
    metadata: Dict[str, Any] = Field(default_factory=dict)


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
    provider_metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Zones and boundaries
    boundary_zone: Optional[Zone] = None  # Primary yard boundary
    exclusion_zones: List[Zone] = Field(default_factory=list)
    mowing_zones: List[Zone] = Field(default_factory=list)
    
    # Special markers
    markers: List[MapMarker] = Field(default_factory=list)
    
    # Map view settings
    center_point: Optional[Point] = None
    zoom_level: int = 18
    map_rotation_deg: float = 0.0
    
    # Validation and metadata
    validation_errors: List[str] = Field(default_factory=list)
    last_modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}
    
    def add_marker(self, marker_type: MarkerType, position: Point, label: Optional[str] = None) -> MapMarker:
        """Add a special marker to the map"""
        import uuid
        marker_id = str(uuid.uuid4())
        marker = MapMarker(
            marker_id=marker_id,
            marker_type=marker_type,
            position=position,
            label=label or marker_type.value
        )
        self.markers.append(marker)
        self.last_modified = datetime.now(timezone.utc)
        return marker
    
    def get_marker(self, marker_type: MarkerType) -> Optional[MapMarker]:
        """Get marker by type"""
        return next(
            (m for m in self.markers if m.marker_type == marker_type),
            None
        )
    
    def add_exclusion_zone(self, zone: Zone) -> bool:
        """Add exclusion zone with overlap validation"""
        # Check for overlaps with existing zones (basic validation)
        if self.boundary_zone and not self._is_within_boundary(zone):
            self.validation_errors.append(
                f"Exclusion zone {zone.id} extends outside boundary"
            )
            return False
        
        # Check for overlaps with other exclusion zones
        for existing_zone in self.exclusion_zones:
            if self._zones_overlap(zone, existing_zone):
                self.validation_errors.append(
                    f"Exclusion zone {zone.id} overlaps with {existing_zone.id}"
                )
                return False
        
        self.exclusion_zones.append(zone)
        self.last_modified = datetime.now(timezone.utc)
        return True
    
    def _is_within_boundary(self, zone: Zone) -> bool:
        """Check if zone is within boundary (simplified check)"""
        if not self.boundary_zone:
            return True
        
        # Simplified: check if all zone points are roughly within boundary
        # Real implementation would use shapely or similar library
        try:
            from shapely.geometry import Polygon as ShapelyPolygon
            from shapely.geometry import Point as ShapelyPoint
            
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
                self.validation_errors.append(
                    f"Exclusion zone {zone.id} outside boundary"
                )
        
        # Check for marker overlaps (basic validation)
        marker_types = [m.marker_type for m in self.markers]
        required_markers = [MarkerType.HOME]
        for required in required_markers:
            if required not in marker_types:
                self.validation_errors.append(f"Missing required marker: {required.value}")
        
        return len(self.validation_errors) == 0