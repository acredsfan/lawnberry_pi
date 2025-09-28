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