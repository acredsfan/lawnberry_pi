"""
Google Maps API Service
Comprehensive Google Maps integration with caching, monitoring, and cost optimization.
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from fastapi import HTTPException
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class UsageLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class APIUsageStats:
    """API usage statistics for monitoring"""

    geocoding_calls: int = 0
    reverse_geocoding_calls: int = 0
    places_calls: int = 0
    tiles_calls: int = 0
    total_calls: int = 0
    cost_estimate: float = 0.0
    period_start: datetime = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "period_start": self.period_start.isoformat() if self.period_start else None,
        }


@dataclass
class CacheConfig:
    """Cache configuration for different API types"""

    geocoding_ttl: int = 3600 * 24 * 7  # 7 days
    reverse_geocoding_ttl: int = 3600 * 24  # 1 day
    places_ttl: int = 3600 * 6  # 6 hours
    tiles_ttl: int = 3600 * 24 * 30  # 30 days
    usage_stats_ttl: int = 3600 * 24  # 1 day


class GoogleMapsService:
    """
    Google Maps API service with comprehensive caching and monitoring.
    """

    # API pricing (approximate USD per 1000 requests)
    PRICING = {"geocoding": 5.0, "reverse_geocoding": 5.0, "places": 32.0, "static_maps": 2.0}

    # Rate limits per usage level
    RATE_LIMITS = {
        UsageLevel.LOW: {"requests_per_minute": 10, "requests_per_day": 1000},
        UsageLevel.MEDIUM: {"requests_per_minute": 50, "requests_per_day": 10000},
        UsageLevel.HIGH: {"requests_per_minute": 200, "requests_per_day": 100000},
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        redis_client: Optional[Redis] = None,
        usage_level: UsageLevel = UsageLevel.MEDIUM,
        cost_alert_threshold: float = 50.0,
    ):
        self.api_key = api_key
        self.redis_client = redis_client
        self.usage_level = usage_level
        self.cost_alert_threshold = cost_alert_threshold
        self.cache_config = CacheConfig()
        self.session: Optional[aiohttp.ClientSession] = None
        self._request_counts = {}
        self._last_reset = time.time()

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        if self.session:
            await self.session.close()

    def is_available(self) -> bool:
        """Check if Google Maps API is available"""
        return bool(self.api_key and self.api_key != "your_google_maps_api_key_here")

    async def _get_cache_key(self, prefix: str, **params) -> str:
        """Generate cache key for request"""
        param_str = json.dumps(params, sort_keys=True)
        return f"gmaps:{prefix}:{hash(param_str)}"

    async def _get_from_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get data from Redis cache"""
        if not self.redis_client:
            return None

        try:
            cached_data = await self.redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
        return None

    async def _set_cache(self, cache_key: str, data: Dict[str, Any], ttl: int):
        """Set data in Redis cache"""
        if not self.redis_client:
            return

        try:
            await self.redis_client.setex(cache_key, ttl, json.dumps(data, default=str))
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

    async def _check_rate_limit(self) -> bool:
        """Check if request is within rate limits"""
        now = time.time()
        minute_key = int(now / 60)

        # Reset counters if needed
        if now - self._last_reset > 60:
            self._request_counts.clear()
            self._last_reset = now

        # Check minute limit
        minute_count = self._request_counts.get(minute_key, 0)
        limit = self.RATE_LIMITS[self.usage_level]["requests_per_minute"]

        if minute_count >= limit:
            return False

        # Update counter
        self._request_counts[minute_key] = minute_count + 1
        return True

    async def _make_request(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make HTTP request to Google Maps API"""
        if not self.session:
            raise HTTPException(status_code=500, detail="HTTP session not initialized")

        if not await self._check_rate_limit():
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        params["key"] = self.api_key

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("status") == "OK":
                        return data
                    else:
                        logger.error(
                            f"Google Maps API error: {data.get('status')} - {data.get('error_message', '')}"
                        )
                        raise HTTPException(
                            status_code=400, detail=f"Google Maps API error: {data.get('status')}"
                        )
                else:
                    logger.error(f"HTTP error {response.status}: {await response.text()}")
                    raise HTTPException(
                        status_code=response.status, detail="Google Maps API request failed"
                    )

        except aiohttp.ClientError as e:
            logger.error(f"Network error: {e}")
            raise HTTPException(status_code=503, detail="Network error accessing Google Maps API")

    async def _update_usage_stats(self, api_type: str, cost: float = 0.0):
        """Update API usage statistics"""
        if not self.redis_client:
            return

        stats_key = f"gmaps:usage_stats:{datetime.now().strftime('%Y-%m-%d')}"

        try:
            # Get current stats
            current_stats = await self.redis_client.get(stats_key)
            if current_stats:
                stats = APIUsageStats(**json.loads(current_stats))
            else:
                stats = APIUsageStats(period_start=datetime.now())

            # Update stats
            setattr(stats, f"{api_type}_calls", getattr(stats, f"{api_type}_calls", 0) + 1)
            stats.total_calls += 1
            stats.cost_estimate += cost

            # Save updated stats
            await self.redis_client.setex(
                stats_key, self.cache_config.usage_stats_ttl, json.dumps(stats.to_dict())
            )

            # Check cost alert
            if stats.cost_estimate > self.cost_alert_threshold:
                logger.warning(
                    f"Google Maps API cost alert: ${stats.cost_estimate:.2f} (threshold: ${self.cost_alert_threshold})"
                )

        except Exception as e:
            logger.error(f"Error updating usage stats: {e}")

    async def geocode(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Convert address to coordinates using Google Maps Geocoding API.
        """
        if not self.is_available():
            return None

        cache_key = await self._get_cache_key("geocode", address=address)

        # Try cache first
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            return cached_result

        # Make API request
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"address": address}

        try:
            data = await self._make_request(url, params)

            if data.get("results"):
                result = {
                    "address": data["results"][0]["formatted_address"],
                    "location": data["results"][0]["geometry"]["location"],
                    "place_id": data["results"][0]["place_id"],
                    "types": data["results"][0]["types"],
                }

                # Cache result
                await self._set_cache(cache_key, result, self.cache_config.geocoding_ttl)

                # Update usage stats
                await self._update_usage_stats("geocoding", self.PRICING["geocoding"] / 1000)

                return result

        except Exception as e:
            logger.error(f"Geocoding error: {e}")

        return None

    async def reverse_geocode(self, lat: float, lng: float) -> Optional[Dict[str, Any]]:
        """
        Convert coordinates to address using Google Maps Reverse Geocoding API.
        """
        if not self.is_available():
            return None

        cache_key = await self._get_cache_key("reverse_geocode", lat=lat, lng=lng)

        # Try cache first
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            return cached_result

        # Make API request
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"latlng": f"{lat},{lng}"}

        try:
            data = await self._make_request(url, params)

            if data.get("results"):
                result = {
                    "address": data["results"][0]["formatted_address"],
                    "location": {"lat": lat, "lng": lng},
                    "place_id": data["results"][0]["place_id"],
                    "address_components": data["results"][0]["address_components"],
                }

                # Cache result
                await self._set_cache(cache_key, result, self.cache_config.reverse_geocoding_ttl)

                # Update usage stats
                await self._update_usage_stats(
                    "reverse_geocoding", self.PRICING["reverse_geocoding"] / 1000
                )

                return result

        except Exception as e:
            logger.error(f"Reverse geocoding error: {e}")

        return None

    async def search_places(
        self, query: str, location: Optional[Tuple[float, float]] = None, radius: int = 5000
    ) -> List[Dict[str, Any]]:
        """
        Search for places using Google Maps Places API.
        """
        if not self.is_available():
            return []

        cache_key = await self._get_cache_key(
            "places", query=query, location=location, radius=radius
        )

        # Try cache first
        cached_result = await self._get_from_cache(cache_key)
        if cached_result:
            return cached_result

        # Make API request
        url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        params = {"query": query}

        if location:
            params["location"] = f"{location[0]},{location[1]}"
            params["radius"] = radius

        try:
            data = await self._make_request(url, params)

            results = []
            for place in data.get("results", []):
                results.append(
                    {
                        "name": place.get("name"),
                        "address": place.get("formatted_address"),
                        "location": place.get("geometry", {}).get("location"),
                        "place_id": place.get("place_id"),
                        "rating": place.get("rating"),
                        "types": place.get("types", []),
                    }
                )

            # Cache results
            await self._set_cache(cache_key, results, self.cache_config.places_ttl)

            # Update usage stats
            await self._update_usage_stats("places", self.PRICING["places"] / 1000)

            return results

        except Exception as e:
            logger.error(f"Places search error: {e}")

        return []

    async def get_static_map_url(
        self,
        center: Tuple[float, float],
        zoom: int = 15,
        size: Tuple[int, int] = (640, 640),
        map_type: str = "satellite",
        markers: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        """
        Generate URL for Google Static Maps API.
        """
        if not self.is_available():
            return None

        params = {
            "center": f"{center[0]},{center[1]}",
            "zoom": zoom,
            "size": f"{size[0]}x{size[1]}",
            "maptype": map_type,
            "key": self.api_key,
        }

        if markers:
            marker_strings = []
            for marker in markers:
                marker_str = f"color:{marker.get('color', 'red')}"
                if "label" in marker:
                    marker_str += f"|label:{marker['label']}"
                marker_str += f"|{marker['lat']},{marker['lng']}"
                marker_strings.append(marker_str)
            params["markers"] = "|".join(marker_strings)

        # Update usage stats
        await self._update_usage_stats("static_maps", self.PRICING["static_maps"] / 1000)

        base_url = "https://maps.googleapis.com/maps/api/staticmap"
        param_strings = [f"{k}={v}" for k, v in params.items()]
        return f"{base_url}?{'&'.join(param_strings)}"

    async def get_usage_stats(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get API usage statistics for monitoring.
        """
        if not self.redis_client:
            return {"error": "Redis not available"}

        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        stats_key = f"gmaps:usage_stats:{date}"

        try:
            stats_data = await self.redis_client.get(stats_key)
            if stats_data:
                return json.loads(stats_data)
            else:
                return APIUsageStats(period_start=datetime.now()).to_dict()
        except Exception as e:
            logger.error(f"Error getting usage stats: {e}")
            return {"error": str(e)}

    async def clear_cache(self, pattern: str = "gmaps:*"):
        """
        Clear cached data matching pattern.
        """
        if not self.redis_client:
            return

        try:
            keys = await self.redis_client.keys(pattern)
            if keys:
                await self.redis_client.delete(*keys)
                logger.info(f"Cleared {len(keys)} cache entries matching {pattern}")
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
