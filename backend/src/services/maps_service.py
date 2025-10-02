import httpx
import json
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class MapProvider(str, Enum):
    GOOGLE = "google"
    OSM = "osm"


class MapsService:
    """Maps service with provider switching and API key management."""
    
    def __init__(self):
        self.provider = MapProvider.GOOGLE
        self.google_api_key: Optional[str] = None
        self.bypass_external = False
        self.usage_stats = {
            "google_requests": 0,
            "osm_requests": 0,
            "cached_requests": 0,
            "failed_requests": 0
        }
        self._tile_cache: Dict[str, Any] = {}
        
    def configure(self, provider: str, api_key: Optional[str] = None, bypass_external: bool = False):
        """Configure maps provider and settings."""
        if provider not in [MapProvider.GOOGLE, MapProvider.OSM]:
            raise ValueError(f"Invalid provider: {provider}")
            
        self.provider = MapProvider(provider)
        self.google_api_key = api_key
        self.bypass_external = bypass_external
        
    def validate_api_key(self, api_key: str) -> bool:
        """Validate Google Maps API key."""
        if not api_key or not api_key.startswith("AIza"):
            return False
            
        # In production, this would make a test request to Google's API
        # For now, accept any key starting with "AIza"
        return True
        
    async def get_map_tile(self, zoom: int, x: int, y: int) -> Optional[bytes]:
        """Get map tile from configured provider."""
        if self.bypass_external:
            return self._get_minimal_tile()
            
        cache_key = f"{self.provider}_{zoom}_{x}_{y}"
        if cache_key in self._tile_cache:
            self.usage_stats["cached_requests"] += 1
            return self._tile_cache[cache_key]
            
        try:
            if self.provider == MapProvider.GOOGLE:
                tile_data = await self._get_google_tile(zoom, x, y)
            else:
                tile_data = await self._get_osm_tile(zoom, x, y)
                
            # Cache the tile
            self._tile_cache[cache_key] = tile_data
            return tile_data
            
        except Exception as e:
            self.usage_stats["failed_requests"] += 1
            # Fallback to other provider
            if self.provider == MapProvider.GOOGLE:
                try:
                    tile_data = await self._get_osm_tile(zoom, x, y)
                    self._tile_cache[cache_key] = tile_data
                    return tile_data
                except Exception:
                    pass
            return self._get_minimal_tile()
            
    async def geocode(self, address: str) -> Optional[Dict[str, Any]]:
        """Geocode address to coordinates."""
        if self.bypass_external:
            return None
            
        try:
            if self.provider == MapProvider.GOOGLE and self.google_api_key:
                return await self._google_geocode(address)
            else:
                return await self._osm_geocode(address)
        except Exception:
            self.usage_stats["failed_requests"] += 1
            return None
            
    async def reverse_geocode(self, lat: float, lng: float) -> Optional[Dict[str, Any]]:
        """Reverse geocode coordinates to address."""
        if self.bypass_external:
            return None
            
        try:
            if self.provider == MapProvider.GOOGLE and self.google_api_key:
                return await self._google_reverse_geocode(lat, lng)
            else:
                return await self._osm_reverse_geocode(lat, lng)
        except Exception:
            self.usage_stats["failed_requests"] += 1
            return None
            
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get usage statistics."""
        return {
            **self.usage_stats,
            "provider": self.provider,
            "api_key_configured": bool(self.google_api_key),
            "bypass_external": self.bypass_external,
            "cache_size": len(self._tile_cache)
        }
        
    def clear_cache(self):
        """Clear tile cache."""
        self._tile_cache.clear()
        
    async def _get_google_tile(self, zoom: int, x: int, y: int) -> bytes:
        """Get tile from Google Maps."""
        if not self.google_api_key:
            raise ValueError("Google API key not configured")
            
        url = f"https://maps.googleapis.com/maps/api/staticmap"
        params = {
            "center": f"{self._tile_to_lat_lng(zoom, x, y)[0]},{self._tile_to_lat_lng(zoom, x, y)[1]}",
            "zoom": zoom,
            "size": "256x256",
            "maptype": "satellite",
            "key": self.google_api_key
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            self.usage_stats["google_requests"] += 1
            return response.content
            
    async def _get_osm_tile(self, zoom: int, x: int, y: int) -> bytes:
        """Get tile from OpenStreetMap."""
        url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers={
                "User-Agent": "LawnBerry-Pi/2.0"
            })
            response.raise_for_status()
            self.usage_stats["osm_requests"] += 1
            return response.content
            
    async def _google_geocode(self, address: str) -> Dict[str, Any]:
        """Geocode using Google Maps API."""
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "address": address,
            "key": self.google_api_key
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data["status"] == "OK" and data["results"]:
                result = data["results"][0]
                return {
                    "lat": result["geometry"]["location"]["lat"],
                    "lng": result["geometry"]["location"]["lng"],
                    "formatted_address": result["formatted_address"]
                }
        return None
        
    async def _osm_geocode(self, address: str) -> Dict[str, Any]:
        """Geocode using Nominatim (OSM)."""
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": address,
            "format": "json",
            "limit": 1
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers={
                "User-Agent": "LawnBerry-Pi/2.0"
            })
            response.raise_for_status()
            data = response.json()
            
            if data:
                result = data[0]
                return {
                    "lat": float(result["lat"]),
                    "lng": float(result["lon"]),
                    "formatted_address": result["display_name"]
                }
        return None
        
    async def _google_reverse_geocode(self, lat: float, lng: float) -> Dict[str, Any]:
        """Reverse geocode using Google Maps API."""
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            "latlng": f"{lat},{lng}",
            "key": self.google_api_key
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            if data["status"] == "OK" and data["results"]:
                result = data["results"][0]
                return {
                    "formatted_address": result["formatted_address"],
                    "components": result["address_components"]
                }
        return None
        
    async def _osm_reverse_geocode(self, lat: float, lng: float) -> Dict[str, Any]:
        """Reverse geocode using Nominatim (OSM)."""
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lon": lng,
            "format": "json"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers={
                "User-Agent": "LawnBerry-Pi/2.0"
            })
            response.raise_for_status()
            data = response.json()
            
            return {
                "formatted_address": data.get("display_name"),
                "components": data.get("address", {})
            }
            
    def _get_minimal_tile(self) -> bytes:
        """Return minimal placeholder tile when bypassing external services."""
        # Return a simple 256x256 gray tile (placeholder)
        return b"minimal_tile_placeholder"
        
    def _tile_to_lat_lng(self, zoom: int, x: int, y: int) -> tuple:
        """Convert tile coordinates to lat/lng."""
        import math
        n = 2.0 ** zoom
        lon_deg = x / n * 360.0 - 180.0
        lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
        lat_deg = math.degrees(lat_rad)
        return (lat_deg, lon_deg)


    async def save_map_configuration(self, config: 'MapConfiguration', persistence) -> 'MapConfiguration':
        """Save map configuration to persistence layer."""
        from ..models.zone import MapConfiguration
        
        # Validate configuration before saving
        if not config.validate_configuration():
            raise ValueError(f"Invalid map configuration: {config.validation_errors}")
        
        # Increment version on update
        config.config_version += 1
        config.last_modified = datetime.now(timezone.utc)
        
        # Persist to database
        config_json = config.json()
        await persistence.save_map_configuration(config.config_id, config_json)
        
        logger.info(f"Saved map configuration {config.config_id} v{config.config_version}")
        return config
    
    async def load_map_configuration(self, config_id: str, persistence) -> Optional['MapConfiguration']:
        """Load map configuration from persistence layer."""
        from ..models.zone import MapConfiguration
        
        config_json = await persistence.load_map_configuration(config_id)
        if not config_json:
            return None
        
        config = MapConfiguration.parse_raw(config_json)
        logger.info(f"Loaded map configuration {config.config_id} v{config.config_version}")
        return config
    
    def validate_geojson_zone(self, geojson: Dict[str, Any]) -> bool:
        """Validate GeoJSON polygon/point structure."""
        if geojson.get('type') not in ['Polygon', 'Point', 'MultiPolygon']:
            return False
        
        coordinates = geojson.get('coordinates')
        if not coordinates:
            return False
        
        # Basic validation - can be extended with more rigorous checks
        if geojson['type'] == 'Polygon':
            # Polygon should have at least one ring with at least 3 points
            if not isinstance(coordinates, list) or len(coordinates) < 1:
                return False
            if not isinstance(coordinates[0], list) or len(coordinates[0]) < 3:
                return False
        
        return True
    
    def check_overlap(self, zone1: 'Zone', zone2: 'Zone') -> bool:
        """Check if two zones overlap using shapely if available."""
        try:
            from shapely.geometry import Polygon
            
            coords1 = [(p.longitude, p.latitude) for p in zone1.polygon]
            coords2 = [(p.longitude, p.latitude) for p in zone2.polygon]
            
            poly1 = Polygon(coords1)
            poly2 = Polygon(coords2)
            
            return poly1.intersects(poly2)
        except ImportError:
            logger.warning("Shapely not available, skipping overlap check")
            return False
    
    def attempt_provider_fallback(self) -> bool:
        """Attempt to fallback from Google Maps to OSM."""
        if self.provider == MapProvider.GOOGLE:
            logger.info("Falling back from Google Maps to OSM")
            self.provider = MapProvider.OSM
            return True
        return False


# Global instance  
maps_service = MapsService()