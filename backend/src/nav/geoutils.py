from __future__ import annotations

import math
from collections.abc import Iterable


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
        if (
            abs(lat - lat1) < 1e-12
            and abs(lon - lon1) < 1e-12
        ) or _on_segment(lat, lon, lat1, lon1, lat2, lon2):
            return True
        # Ray cast to the east
        intersects = ((lon1 > lon) != (lon2 > lon)) and (
            lat < (lat2 - lat1) * (lon - lon1) / (lon2 - lon1 + 1e-18) + lat1
        )
        if intersects:
            inside = not inside
    return inside


def _on_segment(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> bool:
    """Return True if P lies on segment (X1,Y1)-(X2,Y2) within epsilon."""
    eps = 1e-9
    cross = (py - y1) * (x2 - x1) - (px - x1) * (y2 - y1)
    if abs(cross) > eps:
        return False
    dot = (px - x1) * (px - x2) + (py - y1) * (py - y2)
    return dot <= eps
