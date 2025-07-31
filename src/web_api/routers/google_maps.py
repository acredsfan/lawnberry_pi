"""
Google Maps API Router
Backend endpoints for Google Maps integration with caching and cost optimization.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Tuple
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from pydantic import BaseModel, Field

from ..models import SuccessResponse, Position
from ..auth import get_current_user, require_permission
from ..exceptions import ServiceUnavailableError
from ..services.google_maps_service import GoogleMapsService, UsageLevel
from ..config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()


class GeocodeRequest(BaseModel):
    """Request model for geocoding"""
    address: str = Field(..., description="Address to geocode")


class ReverseGeocodeRequest(BaseModel):
    """Request model for reverse geocoding"""
    lat: float = Field(..., description="Latitude")
    lng: float = Field(..., description="Longitude")


class PlacesSearchRequest(BaseModel):
    """Request model for places search"""
    query: str = Field(..., description="Search query")
    location: Optional[Tuple[float, float]] = Field(None, description="Optional location bias")
    radius: int = Field(5000, description="Search radius in meters")


class GeocodeResponse(BaseModel):
    """Response model for geocoding"""
    address: str
    location: Dict[str, float]
    place_id: str
    types: List[str]


class PlaceResult(BaseModel):
    """Model for place search result"""
    name: Optional[str]
    address: Optional[str]
    location: Optional[Dict[str, float]]
    place_id: Optional[str]
    rating: Optional[float]
    types: List[str]


class UsageStatsResponse(BaseModel):
    """Response model for usage statistics"""
    geocoding_calls: int
    reverse_geocoding_calls: int
    places_calls: int
    tiles_calls: int
    total_calls: int
    cost_estimate: float
    period_start: Optional[str]


async def get_google_maps_service(request: Request) -> GoogleMapsService:
    """Dependency to get Google Maps service instance"""
    settings = get_settings()
    
    # Get Redis client from app state
    redis_client = getattr(request.app.state, 'redis_client', None)
    
    # Determine usage level
    usage_level = UsageLevel.MEDIUM
    if settings.google_maps.usage_level == "low":
        usage_level = UsageLevel.LOW
    elif settings.google_maps.usage_level == "high":
        usage_level = UsageLevel.HIGH
    
    service = GoogleMapsService(
        api_key=settings.google_maps.api_key,
        redis_client=redis_client,
        usage_level=usage_level,
        cost_alert_threshold=settings.google_maps.cost_alert_threshold
    )
    
    return service


@router.get("/status")
async def get_google_maps_status(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get Google Maps API status and configuration"""
    settings = get_settings()
    
    return {
        "available": settings.google_maps.is_available(),
        "usage_level": settings.google_maps.usage_level,
        "cost_alert_threshold": settings.google_maps.cost_alert_threshold,
        "fallback_enabled": True  # OpenStreetMap fallback always available
    }


@router.post("/geocode", response_model=GeocodeResponse)
async def geocode_address(
    request: GeocodeRequest,
    gmaps_service: GoogleMapsService = Depends(get_google_maps_service),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Convert address to coordinates"""
    if not gmaps_service.is_available():
        raise HTTPException(
            status_code=503, 
            detail="Google Maps API not configured. Using OpenStreetMap fallback."
        )
    
    async with gmaps_service:
        result = await gmaps_service.geocode(request.address)
        
        if not result:
            raise HTTPException(
                status_code=404,
                detail="Address not found"
            )
        
        return GeocodeResponse(**result)


@router.post("/reverse-geocode", response_model=GeocodeResponse)
async def reverse_geocode_coordinates(
    request: ReverseGeocodeRequest,
    gmaps_service: GoogleMapsService = Depends(get_google_maps_service),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Convert coordinates to address"""
    if not gmaps_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Google Maps API not configured. Using OpenStreetMap fallback."
        )
    
    async with gmaps_service:
        result = await gmaps_service.reverse_geocode(request.lat, request.lng)
        
        if not result:
            raise HTTPException(
                status_code=404,
                detail="No address found for coordinates"
            )
        
        return GeocodeResponse(**result)


@router.post("/places/search", response_model=List[PlaceResult])
async def search_places(
    request: PlacesSearchRequest,
    gmaps_service: GoogleMapsService = Depends(get_google_maps_service),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Search for places using Google Places API"""
    if not gmaps_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Google Maps API not configured"
        )
    
    async with gmaps_service:
        results = await gmaps_service.search_places(
            request.query,
            request.location,
            request.radius
        )
        
        return [PlaceResult(**result) for result in results]


@router.get("/static-map-url")
async def get_static_map_url(
    lat: float = Query(..., description="Center latitude"),
    lng: float = Query(..., description="Center longitude"),
    zoom: int = Query(15, description="Zoom level"),
    width: int = Query(640, description="Image width"),
    height: int = Query(640, description="Image height"),
    map_type: str = Query("satellite", description="Map type"),
    gmaps_service: GoogleMapsService = Depends(get_google_maps_service),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Generate URL for Google Static Maps API"""
    if not gmaps_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Google Maps API not configured"
        )
    
    async with gmaps_service:
        url = await gmaps_service.get_static_map_url(
            center=(lat, lng),
            zoom=zoom,
            size=(width, height),
            map_type=map_type
        )
        
        if not url:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate static map URL"
            )
        
        return {"url": url}


@router.get("/usage-stats", response_model=UsageStatsResponse)
async def get_usage_statistics(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    gmaps_service: GoogleMapsService = Depends(get_google_maps_service),
    current_user: Dict[str, Any] = Depends(require_permission("admin"))
):
    """Get API usage statistics for monitoring"""
    async with gmaps_service:
        stats = await gmaps_service.get_usage_stats(date)
        
        if 'error' in stats:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get usage stats: {stats['error']}"
            )
        
        return UsageStatsResponse(**stats)


@router.post("/clear-cache", response_model=SuccessResponse)
async def clear_cache(
    pattern: str = Query("gmaps:*", description="Cache key pattern to clear"),
    gmaps_service: GoogleMapsService = Depends(get_google_maps_service),
    current_user: Dict[str, Any] = Depends(require_permission("admin"))
):
    """Clear cached Google Maps data"""
    async with gmaps_service:
        await gmaps_service.clear_cache(pattern)
        
        return SuccessResponse(
            success=True,
            message=f"Cache cleared for pattern: {pattern}"
        )


@router.get("/validate-coordinates")
async def validate_gps_coordinates(
    lat: float = Query(..., description="Latitude to validate"),
    lng: float = Query(..., description="Longitude to validate"),
    gmaps_service: GoogleMapsService = Depends(get_google_maps_service),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Validate GPS coordinates and get location info"""
    # Basic coordinate validation
    if not (-90 <= lat <= 90):
        raise HTTPException(
            status_code=400,
            detail="Invalid latitude: must be between -90 and 90"
        )
    
    if not (-180 <= lng <= 180):
        raise HTTPException(
            status_code=400,
            detail="Invalid longitude: must be between -180 and 180"
        )
    
    result = {
        "valid": True,
        "latitude": lat,
        "longitude": lng
    }
    
    # If Google Maps is available, try to get address info
    if gmaps_service.is_available():
        async with gmaps_service:
            address_info = await gmaps_service.reverse_geocode(lat, lng)
            if address_info:
                result["address"] = address_info.get("address")
                result["place_id"] = address_info.get("place_id")
    
    return result


@router.get("/cost-monitoring")
async def get_cost_monitoring_dashboard(
    gmaps_service: GoogleMapsService = Depends(get_google_maps_service),
    current_user: Dict[str, Any] = Depends(require_permission("admin"))
):
    """Get cost monitoring dashboard data"""
    settings = get_settings()
    
    # Get current day stats
    async with gmaps_service:
        today_stats = await gmaps_service.get_usage_stats()
    
    return {
        "current_cost": today_stats.get("cost_estimate", 0.0),
        "alert_threshold": settings.google_maps.cost_alert_threshold,
        "usage_level": settings.google_maps.usage_level,
        "api_available": gmaps_service.is_available(),
        "daily_stats": today_stats,
        "cost_breakdown": {
            "geocoding": today_stats.get("geocoding_calls", 0) * GoogleMapsService.PRICING["geocoding"] / 1000,
            "reverse_geocoding": today_stats.get("reverse_geocoding_calls", 0) * GoogleMapsService.PRICING["reverse_geocoding"] / 1000,
            "places": today_stats.get("places_calls", 0) * GoogleMapsService.PRICING["places"] / 1000,
            "static_maps": today_stats.get("tiles_calls", 0) * GoogleMapsService.PRICING["static_maps"] / 1000
        }
    }
