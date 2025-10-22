"""Geofence validation and enforcement helpers.

- Validates polygons using shapely
- Supports buffer zones (positive -> expansion, negative -> contraction)
- Provides point-in-geofence checks and violation detection
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

from typing import TYPE_CHECKING
if TYPE_CHECKING:  # pragma: no cover
    from shapely.geometry import Point as SPoint  # type: ignore
    from shapely.geometry import Polygon  # type: ignore

from ..models import Geofence, LatLng


@dataclass(frozen=True)
class GeofenceShape:
    polygon: "Polygon"
    buffered: "Polygon"
    origin_lat: float
    origin_lon: float


def _deg_lat_m() -> float:
    return 111_000.0


def _deg_lon_m_at_lat(lat: float) -> float:
    from math import cos, radians

    return 111_000.0 * cos(radians(lat))


def _to_xy(lat: float, lon: float, olat: float, olon: float) -> Tuple[float, float]:
    return ((lon - olon) * _deg_lon_m_at_lat(olat), (lat - olat) * _deg_lat_m())


def _to_ll(x: float, y: float, olat: float, olon: float) -> Tuple[float, float]:
    return (olat + y / _deg_lat_m(), olon + x / _deg_lon_m_at_lat(olat))


def _polygon_from_latlngs(points: Sequence[LatLng]):
    from shapely.geometry import Polygon  # type: ignore
    if len(points) < 3:
        raise ValueError("Geofence must have >= 3 points")
    olat, olon = points[0].latitude, points[0].longitude
    xy = [_to_xy(p.latitude, p.longitude, olat, olon) for p in points]
    poly = Polygon(xy)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if not poly.is_valid or poly.area <= 0:
        raise ValueError("Invalid geofence polygon")
    return poly, olat, olon


def build_shape(geofence: Geofence) -> GeofenceShape:
    """Create a shapely polygon for the geofence and its buffered version."""
    base, olat, olon = _polygon_from_latlngs(geofence.boundary)
    buffered = base
    if geofence.buffer_distance_m and geofence.buffer_distance_m != 0.0:
        buffered = base.buffer(geofence.buffer_distance_m)
        if buffered.is_empty:
            buffered = base
    return GeofenceShape(polygon=base, buffered=buffered, origin_lat=olat, origin_lon=olon)


def contains(shape: GeofenceShape, point: LatLng, use_buffer: bool = True) -> bool:
    from shapely.geometry import Point as SPoint  # type: ignore
    x, y = _to_xy(point.latitude, point.longitude, shape.origin_lat, shape.origin_lon)
    poly = shape.buffered if use_buffer else shape.polygon
    return poly.contains(SPoint(x, y))


__all__ = ["GeofenceShape", "build_shape", "contains"]
