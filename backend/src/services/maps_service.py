"""Maps service implementation that supports both production and test flows."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx

from ..core.persistence import persistence as default_persistence
from ..models.maps import (
    MapConfiguration as ContractMapConfiguration,
    ExclusionZone as ContractExclusionZone,
)
from ..models.zone import MapConfiguration as ZoneMapConfiguration, Zone

logger = logging.getLogger(__name__)


class MapProvider(str, Enum):
    """Supported map providers for tile/geocode operations."""

    GOOGLE = "google"
    OSM = "osm"


def _resolve_persistence(custom: Any | None) -> Any:
    return custom if custom is not None else persistence


class MapsService:
    """Coordinate map provider usage and persistence bridging.

    The service exposes synchronous helpers used by unit/contract tests that
    work with the simplified models in :mod:`backend.src.models.maps`, while the
    asynchronous counterparts support the richer zone-based models leveraged by
    the FastAPI layer. This keeps backward compatibility with existing
    endpoints and allows the lighter-weight contract fixtures to operate in
    isolation.
    """

    def __init__(
        self,
        provider: str = "leaflet",
        api_key: Optional[str] = None,
        bypass_external: bool = False,
        persistence: Any | None = None,
    ) -> None:
        self._default_persistence = _resolve_persistence(persistence)
        self._tile_cache: Dict[str, bytes] = {}
        self.usage_stats: Dict[str, int | str | bool] = {
            "google_requests": 0,
            "osm_requests": 0,
            "cached_requests": 0,
            "failed_requests": 0,
        }
        self.google_api_key: Optional[str] = None
        self.bypass_external = bypass_external
        self.current_provider: str = "leaflet"
        self._provider_enum = MapProvider.OSM
        self.configure(provider, api_key=api_key, bypass_external=bypass_external)

    # ------------------------------------------------------------------
    # Provider configuration
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_provider(value: str) -> Tuple[MapProvider, str]:
        normalized = value.replace("_", "-").lower()
        if normalized in {"google", "google-maps"}:
            return MapProvider.GOOGLE, "google"
        if normalized in {"leaflet", "osm", "openstreetmap"}:
            return MapProvider.OSM, "leaflet"
        raise ValueError(f"Invalid provider: {value}")

    def _set_provider(self, provider: str, api_key: Optional[str]) -> None:
        enum_value, label = self._normalize_provider(provider)
        if enum_value == MapProvider.GOOGLE and not api_key:
            raise ValueError("Google Maps requires an API key")
        self._provider_enum = enum_value
        self.current_provider = label
        self.google_api_key = api_key if enum_value == MapProvider.GOOGLE else None

    @property
    def provider(self) -> str:
        """Return the current provider label used in responses."""

        return self.current_provider

    def configure(
        self,
        provider: str,
        api_key: Optional[str] = None,
        bypass_external: Optional[bool] = None,
    ) -> None:
        """Configure provider, API key, and optional bypass flag."""

        self._set_provider(provider, api_key)
        if bypass_external is not None:
            self.bypass_external = bypass_external

    def validate_api_key(self, api_key: str) -> bool:
        """Perform basic API key validation (Google keys start with ``AIza``)."""

        return bool(api_key and api_key.startswith("AIza"))

    def get_usage_stats(self) -> Dict[str, Any]:
        """Return high-level usage information for diagnostics."""

        return {
            **self.usage_stats,
            "provider": self.current_provider,
            "api_key_configured": bool(self.google_api_key),
            "bypass_external": self.bypass_external,
            "cache_size": len(self._tile_cache),
        }

    def clear_cache(self) -> None:
        """Clear the in-memory tile cache."""

        self._tile_cache.clear()

    # ------------------------------------------------------------------
    # Tile + geocode helpers
    # ------------------------------------------------------------------
    async def get_map_tile(self, zoom: int, x: int, y: int) -> Optional[bytes]:
        if self.bypass_external:
            return self._get_minimal_tile()

        cache_key = f"{self._provider_enum.value}:{zoom}:{x}:{y}"
        cached = self._tile_cache.get(cache_key)
        if cached is not None:
            self.usage_stats["cached_requests"] += 1
            return cached

        try:
            if self._provider_enum == MapProvider.GOOGLE:
                tile_data = await self._get_google_tile(zoom, x, y)
            else:
                tile_data = await self._get_osm_tile(zoom, x, y)
            self._tile_cache[cache_key] = tile_data
            return tile_data
        except Exception as exc:  # pragma: no cover - network failure path
            logger.debug("Tile fetch failed, attempting fallback: %s", exc)
            self.usage_stats["failed_requests"] += 1
            if self._provider_enum == MapProvider.GOOGLE:
                try:
                    tile_data = await self._get_osm_tile(zoom, x, y)
                    self._tile_cache[cache_key] = tile_data
                    return tile_data
                except Exception:
                    pass
            return self._get_minimal_tile()

    async def geocode(self, address: str) -> Optional[Dict[str, Any]]:
        if self.bypass_external:
            return None
        try:
            if self._provider_enum == MapProvider.GOOGLE and self.google_api_key:
                return await self._google_geocode(address)
            return await self._osm_geocode(address)
        except Exception as exc:  # pragma: no cover - network failure path
            logger.debug("Geocode failed: %s", exc)
            self.usage_stats["failed_requests"] += 1
            return None

    async def reverse_geocode(self, lat: float, lng: float) -> Optional[Dict[str, Any]]:
        if self.bypass_external:
            return None
        try:
            if self._provider_enum == MapProvider.GOOGLE and self.google_api_key:
                return await self._google_reverse_geocode(lat, lng)
            return await self._osm_reverse_geocode(lat, lng)
        except Exception as exc:  # pragma: no cover - network failure path
            logger.debug("Reverse geocode failed: %s", exc)
            self.usage_stats["failed_requests"] += 1
            return None

    async def _get_google_tile(self, zoom: int, x: int, y: int) -> bytes:
        if not self.google_api_key:
            raise ValueError("Google API key not configured")
        url = "https://maps.googleapis.com/maps/api/staticmap"
        lat, lng = self._tile_to_lat_lng(zoom, x, y)
        params = {
            "center": f"{lat},{lng}",
            "zoom": zoom,
            "size": "256x256",
            "maptype": "satellite",
            "key": self.google_api_key,
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            self.usage_stats["google_requests"] += 1
            return response.content

    async def _get_osm_tile(self, zoom: int, x: int, y: int) -> bytes:
        url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={"User-Agent": "LawnBerry-Pi/2.0"},
            )
            response.raise_for_status()
            self.usage_stats["osm_requests"] += 1
            return response.content

    async def _google_geocode(self, address: str) -> Optional[Dict[str, Any]]:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"address": address, "key": self.google_api_key}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "OK" and data.get("results"):
                result = data["results"][0]
                location = result.get("geometry", {}).get("location", {})
                return {
                    "lat": location.get("lat"),
                    "lng": location.get("lng"),
                    "formatted_address": result.get("formatted_address"),
                }
        return None

    async def _osm_geocode(self, address: str) -> Optional[Dict[str, Any]]:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": address, "format": "json", "limit": 1}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params=params,
                headers={"User-Agent": "LawnBerry-Pi/2.0"},
            )
            response.raise_for_status()
            data = response.json()
            if data:
                result = data[0]
                return {
                    "lat": float(result["lat"]),
                    "lng": float(result["lon"]),
                    "formatted_address": result.get("display_name"),
                }
        return None

    async def _google_reverse_geocode(self, lat: float, lng: float) -> Optional[Dict[str, Any]]:
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {"latlng": f"{lat},{lng}", "key": self.google_api_key}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "OK" and data.get("results"):
                result = data["results"][0]
                return {
                    "formatted_address": result.get("formatted_address"),
                    "components": result.get("address_components"),
                }
        return None

    async def _osm_reverse_geocode(self, lat: float, lng: float) -> Optional[Dict[str, Any]]:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {"lat": lat, "lon": lng, "format": "json"}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params=params,
                headers={"User-Agent": "LawnBerry-Pi/2.0"},
            )
            response.raise_for_status()
            data = response.json()
            return {
                "formatted_address": data.get("display_name"),
                "components": data.get("address", {}),
            }

    def _get_minimal_tile(self) -> bytes:
        return b"minimal_tile_placeholder"

    @staticmethod
    def _tile_to_lat_lng(zoom: int, x: int, y: int) -> Tuple[float, float]:
        import math

        n = 2.0 ** zoom
        lon_deg = x / n * 360.0 - 180.0
        lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
        lat_deg = math.degrees(lat_rad)
        return lat_deg, lon_deg

    # ------------------------------------------------------------------
    # Persistence helpers (synchronous contract + async production)
    # ------------------------------------------------------------------
    @staticmethod
    def _ensure_not_running_loop() -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():  # pragma: no cover - defensive guard
            raise RuntimeError(
                "Cannot execute synchronous MapsService persistence helper inside running event loop",
            )

    @staticmethod
    def _serialize_contract(config: ContractMapConfiguration, mode: str = "python") -> Dict[str, Any]:
        if mode == "json":
            return config.model_dump(mode="json")
        return config.model_dump(mode="python")

    @staticmethod
    def _contract_from_payload(payload: Dict[str, Any]) -> ContractMapConfiguration:
        return ContractMapConfiguration(**payload)

    def save_map_configuration(
        self,
        config: ContractMapConfiguration,
        persistence: Any = None,
    ) -> ContractMapConfiguration:
        persistence = _resolve_persistence(persistence) or self._default_persistence
        config.touch()
        payload = self._serialize_contract(config)

        handler = getattr(persistence, "save_map_configuration", None)
        if handler is None:
            raise AttributeError("Persistence object lacks save_map_configuration")

        try:
            result = handler(payload)
        except TypeError:
            # Fallback to production signature (config_id, json_str)
            json_payload = json.dumps(self._serialize_contract(config, mode="json"))
            result = handler(config.config_id, json_payload)

        if asyncio.iscoroutine(result):
            self._ensure_not_running_loop()
            asyncio.run(result)
        return config

    def load_map_configuration(
        self,
        config_id: str,
        persistence: Any = None,
    ) -> Optional[ContractMapConfiguration]:
        persistence = _resolve_persistence(persistence) or self._default_persistence
        handler = getattr(persistence, "load_map_configuration", None)
        if handler is None:
            raise AttributeError("Persistence object lacks load_map_configuration")

        result = handler(config_id)
        if asyncio.iscoroutine(result):
            self._ensure_not_running_loop()
            result = asyncio.run(result)

        if not result:
            return None

        if isinstance(result, dict):
            return self._contract_from_payload(result)

        try:
            payload = json.loads(result)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid map configuration payload") from exc
        return self._contract_from_payload(payload)

    async def save_map_configuration_async(
        self,
        config: ZoneMapConfiguration | ContractMapConfiguration,
        persistence: Any | None = None,
    ) -> ZoneMapConfiguration | ContractMapConfiguration:
        persistence = _resolve_persistence(persistence) or self._default_persistence

        if isinstance(config, ContractMapConfiguration):
            payload = json.dumps(self._serialize_contract(config, mode="json"))
            await persistence.save_map_configuration(config.config_id, payload)
            return config

        # Zone-based configuration used in production
        if not config.validate_configuration():
            raise ValueError(f"Invalid map configuration: {config.validation_errors}")
        config.config_version += 1
        config.last_modified = datetime.now(timezone.utc)
        await persistence.save_map_configuration(
            config.config_id,
            config.model_dump_json(),
        )
        logger.info("Saved map configuration %s v%s", config.config_id, config.config_version)
        return config

    async def load_map_configuration_async(
        self,
        config_id: str,
        persistence: Any | None = None,
    ) -> Optional[ZoneMapConfiguration | ContractMapConfiguration]:
        persistence = _resolve_persistence(persistence) or self._default_persistence

        config_json = await persistence.load_map_configuration(config_id)
        if not config_json:
            return None
        try:
            zone_cfg = ZoneMapConfiguration.model_validate_json(config_json)
            logger.info(
                "Loaded map configuration %s v%s",
                zone_cfg.config_id,
                zone_cfg.config_version,
            )
            return zone_cfg
        except Exception:
            # Fallback to contract payload
            payload = json.loads(config_json)
            return ContractMapConfiguration(**payload)

    # ------------------------------------------------------------------
    # Geometry helpers for contract tests
    # ------------------------------------------------------------------
    @staticmethod
    def _zone_to_coords(zone: ContractExclusionZone) -> List[Tuple[float, float]]:
        return [(point.lng, point.lat) for point in zone.polygon]

    def validate_geojson_zone(
        self,
        zone: ContractExclusionZone,
    ) -> Tuple[bool, Optional[str]]:
        points = zone.polygon
        if len(points) < 3:
            return False, "Polygon must have at least 3 points"

        try:
            from shapely.geometry import Polygon  # type: ignore
        except Exception:
            return True, None

        try:
            poly = Polygon(self._zone_to_coords(zone))
        except Exception as exc:
            return False, f"Invalid polygon: {exc}"  # pragma: no cover - shapely raises

        if not poly.is_valid:
            return False, "Polygon is self-intersecting"
        if poly.area <= 0:
            return False, "Polygon area must be positive"
        return True, None

    def check_overlap(
        self,
        zone: ContractExclusionZone,
        others: Sequence[ContractExclusionZone],
    ) -> bool:
        if not others:
            return False
        try:
            from shapely.geometry import Polygon  # type: ignore
        except Exception:
            # Bounding-box fallback when shapely is unavailable
            minx, miny, maxx, maxy = self._bounding_box(zone)
            for other in others:
                ominx, ominy, omaxx, omaxy = self._bounding_box(other)
                if not (maxx < ominx or omaxx < minx or maxy < ominy or omaxy < miny):
                    return True
            return False

        try:
            base = Polygon(self._zone_to_coords(zone))
        except Exception:  # pragma: no cover - invalid polygon
            return False

        for other in others:
            try:
                poly = Polygon(self._zone_to_coords(other))
            except Exception:
                continue
            if base.intersects(poly):
                return True
        return False

    @staticmethod
    def _bounding_box(zone: ContractExclusionZone) -> Tuple[float, float, float, float]:
        lats = [pt.lat for pt in zone.polygon]
        lngs = [pt.lng for pt in zone.polygon]
        return min(lngs), min(lats), max(lngs), max(lats)

    def attempt_provider_fallback(self) -> bool:
        if self._provider_enum == MapProvider.GOOGLE:
            logger.info("Falling back from Google Maps to OpenStreetMap/Leaflet provider")
            self._provider_enum = MapProvider.OSM
            self.current_provider = "leaflet"
            self.google_api_key = None
            return True
        return False


persistence = default_persistence

maps_service = MapsService()