from __future__ import annotations

import math
from collections.abc import Iterable

METERS_PER_DEGREE_LATITUDE = 111_320.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in meters between two WGS84 coords."""
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def offset_lat_lon(
    latitude: float,
    longitude: float,
    *,
    north_m: float = 0.0,
    east_m: float = 0.0,
) -> tuple[float, float]:
    """Apply a small local tangent-plane offset to a WGS84 coordinate."""
    meters_per_degree_lon = METERS_PER_DEGREE_LATITUDE * math.cos(math.radians(latitude))
    latitude += north_m / METERS_PER_DEGREE_LATITUDE
    if abs(meters_per_degree_lon) > 1.0:
        longitude += east_m / meters_per_degree_lon
    return latitude, longitude


def body_offset_to_north_east(
    *,
    forward_m: float,
    right_m: float,
    heading_degrees: float,
) -> tuple[float, float]:
    """Convert mower body-frame offset to north/east meters.

    Heading uses navigation compass convention: north=0°, east=90°.
    """
    heading_rad = math.radians(heading_degrees)
    north_m = forward_m * math.cos(heading_rad) - right_m * math.sin(heading_rad)
    east_m = forward_m * math.sin(heading_rad) + right_m * math.cos(heading_rad)
    return north_m, east_m


def point_in_polygon(lat: float, lon: float, polygon: Iterable[tuple[float, float]]) -> bool:
    """Ray casting algorithm for point-in-polygon.

    Args:
        lat, lon: point to test
        polygon: iterable of (lat, lon) vertices (not necessarily closed)
    Returns True if inside; False otherwise. Edges are treated as inside.
    """
    pts = list(polygon)
    n = len(pts)
    if n < 3:
        return False
    inside = False
    for i in range(n):
        lat1, lon1 = pts[i]
        lat2, lon2 = pts[(i + 1) % n]
        # Check if point is on vertex/edge (approx) - treat as inside
        if (abs(lat - lat1) < 1e-12 and abs(lon - lon1) < 1e-12) or _on_segment(
            lat, lon, lat1, lon1, lat2, lon2
        ):
            return True
        # Ray cast to the east
        intersects = ((lon1 > lon) != (lon2 > lon)) and (
            lat < (lat2 - lat1) * (lon - lon1) / (lon2 - lon1 + 1e-18) + lat1
        )
        if intersects:
            inside = not inside
    return inside


def latlon_to_enu(
    lat: float,
    lon: float,
    origin_lat: float,
    origin_lon: float,
) -> tuple[float, float]:
    """Convert a WGS84 (lat, lon) point to local ENU meters relative to origin.

    Returns (east_m, north_m).  Accuracy is good for small areas (< a few km).
    """
    north_m = (lat - origin_lat) * METERS_PER_DEGREE_LATITUDE
    meters_per_deg_lon = METERS_PER_DEGREE_LATITUDE * math.cos(math.radians(origin_lat))
    east_m = (lon - origin_lon) * meters_per_deg_lon
    return east_m, north_m


def enu_to_latlon(
    east_m: float,
    north_m: float,
    origin_lat: float,
    origin_lon: float,
) -> tuple[float, float]:
    """Convert local ENU meters back to WGS84 (lat, lon).

    Inverse of :func:`latlon_to_enu`.
    """
    lat = origin_lat + north_m / METERS_PER_DEGREE_LATITUDE
    meters_per_deg_lon = METERS_PER_DEGREE_LATITUDE * math.cos(math.radians(origin_lat))
    lon = origin_lon + (east_m / meters_per_deg_lon if abs(meters_per_deg_lon) > 1.0 else 0.0)
    return lat, lon


def rotate_enu(east_m: float, north_m: float, angle_deg: float) -> tuple[float, float]:
    """Rotate an ENU point (east_m, north_m) around the origin by angle_deg.

    Positive angle rotates counter-clockwise in the ENU plane (east=x, north=y).
    """
    theta = math.radians(angle_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    new_east = east_m * cos_t - north_m * sin_t
    new_north = east_m * sin_t + north_m * cos_t
    return new_east, new_north


def _on_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> bool:
    """Return True if P lies on segment (X1,Y1)-(X2,Y2) within epsilon."""
    eps = 1e-9
    cross = (py - y1) * (x2 - x1) - (px - x1) * (y2 - y1)
    if abs(cross) > eps:
        return False
    dot = (px - x1) * (px - x2) + (py - y1) * (py - y2)
    return dot <= eps
