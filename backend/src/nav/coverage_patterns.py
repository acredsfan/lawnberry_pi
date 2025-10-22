"""Coverage pattern generation algorithms.

Implements boustrophedon (lawnmower) coverage within a polygon boundary,
optionally subtracting obstacle polygons. Uses shapely for robust clipping.

All public functions are pure and typed to ease testing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

# Shapely is a required dependency in production, but we avoid importing at
# module import time to keep test environments without Shapely importable.
from typing import TYPE_CHECKING
if TYPE_CHECKING:  # pragma: no cover - import only for type checking
    from shapely.affinity import rotate as _rotate  # type: ignore
    from shapely.geometry import LineString as _LineString, Polygon as _Polygon  # type: ignore
    from shapely.ops import unary_union as _unary_union  # type: ignore

from ..models import Position, Waypoint


@dataclass(frozen=True)
class CoverageConfig:
    swath_width_m: float = 0.4
    overlap: float = 0.1  # fraction 0..1
    heading_deg: float = 0.0  # 0 -> lines run E/W, sweep N/S
    waypoint_speed_ms: float = 0.5


def _deg_lat_m() -> float:
    # Approximate meters per degree latitude at mid-latitudes
    return 111_000.0


def _deg_lon_m_at_lat(lat: float) -> float:
    # Longitude meters per degree varies with latitude; crude cosine model
    from math import cos, radians

    return 111_000.0 * cos(radians(lat))


def _to_xy(lat: float, lon: float, origin_lat: float, origin_lon: float) -> Tuple[float, float]:
    mx = (lon - origin_lon) * _deg_lon_m_at_lat(origin_lat)
    my = (lat - origin_lat) * _deg_lat_m()
    return (mx, my)


def _to_ll(x: float, y: float, origin_lat: float, origin_lon: float) -> Tuple[float, float]:
    lat = origin_lat + y / _deg_lat_m()
    lon = origin_lon + x / _deg_lon_m_at_lat(origin_lat)
    return (lat, lon)


def _poly_from_positions(boundary: Sequence[Position]):
    from shapely.geometry import Polygon  # type: ignore
    if len(boundary) < 3:
        raise ValueError("boundary must have at least 3 vertices")
    origin_lat = boundary[0].latitude
    origin_lon = boundary[0].longitude
    pts = [_to_xy(p.latitude, p.longitude, origin_lat, origin_lon) for p in boundary]
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)  # fix simple self-intersections if possible
    if not poly.is_valid:
        raise ValueError("Invalid boundary polygon")
    # Store origin as attribute for back-conversion
    poly.origin_lat = origin_lat  # type: ignore[attr-defined]
    poly.origin_lon = origin_lon  # type: ignore[attr-defined]
    return poly


def _obstacles_union(obstacles: Iterable[Sequence[Position]] | None, origin_lat: float, origin_lon: float):
    from shapely.ops import unary_union  # type: ignore
    from shapely.geometry import Polygon  # type: ignore
    if not obstacles:
        return None
    polys: List[Polygon] = []
    for obs in obstacles:
        if len(obs) < 3:
            continue
        pts = [_to_xy(p.latitude, p.longitude, origin_lat, origin_lon) for p in obs]
        po = Polygon(pts)
        if po.is_valid and po.area > 0:
            polys.append(po)
    if not polys:
        return None
    return unary_union(polys)  # type: ignore[no-any-return]


def generate_lawnmower(
    boundary: Sequence[Position],
    *,
    config: CoverageConfig | None = None,
    obstacles: Iterable[Sequence[Position]] | None = None,
) -> List[Waypoint]:
    """Generate lawnmower coverage waypoints within a boundary.

    - Boundary is a polygon in lat/lon Positions (not closed).
    - Obstacles are optional polygons to subtract from coverage area.
    - Returns ordered waypoints that alternate sweep direction.
    """
    cfg = config or CoverageConfig()
    poly = _poly_from_positions(boundary)

    origin_lat = poly.origin_lat  # type: ignore[attr-defined]
    origin_lon = poly.origin_lon  # type: ignore[attr-defined]

    obs_union = _obstacles_union(obstacles, origin_lat, origin_lon)
    cover_area = poly
    if obs_union is not None:
        cover_area = poly.difference(obs_union)
        if cover_area.is_empty:
            return []

    # Align stripes by rotating so that stripes are axis-aligned in local frame
    from shapely.affinity import rotate  # type: ignore
    rotated = rotate(cover_area, -cfg.heading_deg, origin=(0, 0), use_radians=False)

    effective_width = max(0.01, cfg.swath_width_m * (1.0 - cfg.overlap))
    minx, miny, maxx, maxy = rotated.bounds

    y = miny + effective_width / 2.0
    direction = 1

    waypoints: List[Waypoint] = []

    while y <= maxy:
        from shapely.geometry import LineString  # type: ignore
        line = LineString([(minx - 1.0, y), (maxx + 1.0, y)])
        segs = rotated.intersection(line)
        if segs.is_empty:
            y += effective_width
            continue
        if segs.geom_type == "LineString":
            segments = [segs]
        elif segs.geom_type == "MultiLineString":
            segments = list(segs.geoms)
        else:
            segments = []

        # For each segment across current stripe, add two waypoints in alternating direction
        for seg in segments:
            xs, ys = list(seg.coords)[0]
            xe, ye = list(seg.coords)[-1]
            if direction == 1:
                ordered = [(xs, ys), (xe, ye)]
            else:
                ordered = [(xe, ye), (xs, ys)]
            for x, yv in ordered:
                # Un-rotate back to original orientation
                ls = LineString([(0.0, 0.0), (x, yv)])
                ls = rotate(ls, cfg.heading_deg, origin=(0, 0), use_radians=False)
                xx, yy = list(ls.coords)[-1]
                lat, lon = _to_ll(xx, yy, origin_lat, origin_lon)
                waypoints.append(Waypoint(position=Position(latitude=lat, longitude=lon), target_speed=cfg.waypoint_speed_ms))
        direction *= -1
        y += effective_width

    return waypoints


__all__ = ["CoverageConfig", "generate_lawnmower"]
