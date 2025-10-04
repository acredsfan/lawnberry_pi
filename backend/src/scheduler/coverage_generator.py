from __future__ import annotations

import math
from typing import Iterable, List, Tuple


def _meters_per_degree_lat() -> float:
    # Approximate meters per degree latitude
    return 111_320.0


def _meters_per_degree_lon(lat: float) -> float:
    # Approximate meters per degree longitude at given latitude
    return 111_320.0 * math.cos(math.radians(lat))


def generate_parallel_lines(
    *,
    geofence_vertices: Iterable[Tuple[float, float]],
    cutting_width_m: float,
    overlap_m: float,
    heading_degrees: float = 0.0,
) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Generate a simple parallel-line coverage pattern inside a geofence bbox.

    Notes:
    - Minimal implementation to satisfy contract tests (T067/T075).
    - Supports heading 0 (north-south lines) and 90 (east-west lines).
    - Uses geofence bounding box; polygon clipping is out-of-scope for now.
    """

    pts = list(geofence_vertices)
    if len(pts) < 3:
        return []

    lats = [lat for lat, _ in pts]
    lons = [lon for _, lon in pts]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    lat0 = (min_lat + max_lat) / 2.0

    spacing_m = max(1e-3, float(cutting_width_m) - float(overlap_m))

    lines: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []

    # Normalize heading to [0, 180) since 180 mirrors 0, etc.
    h = heading_degrees % 180.0

    # Case 1: Heading approximately 0 degrees (north-south lines)
    if abs(h - 0.0) < 1e-6 or abs(h - 180.0) < 1e-6:
        m_per_deg_lon = _meters_per_degree_lon(lat0)
        if m_per_deg_lon <= 0:
            return []
        dlon = spacing_m / m_per_deg_lon
        if dlon <= 0:
            return []

        # Start half a spacing inside the min boundary for better containment
        cur_lon = min_lon + dlon / 2.0
        while cur_lon <= max_lon - 1e-12:
            # Clamp to bounds just in case of floating errors
            L = min(max(cur_lon, min_lon), max_lon)
            a = (min_lat, L)
            b = (max_lat, L)
            lines.append((a, b))
            cur_lon += dlon
        return lines

    # Case 2: Heading approximately 90 degrees (east-west lines)
    if abs(h - 90.0) < 1e-6:
        m_per_deg_lat = _meters_per_degree_lat()
        dlat = spacing_m / m_per_deg_lat
        if dlat <= 0:
            return []
        cur_lat = min_lat + dlat / 2.0
        while cur_lat <= max_lat - 1e-12:
            L = min(max(cur_lat, min_lat), max_lat)
            a = (L, min_lon)
            b = (L, max_lon)
            lines.append((a, b))
            cur_lat += dlat
        return lines

    # Fallback: For arbitrary heading, return empty for now (future enhancement)
    return []
