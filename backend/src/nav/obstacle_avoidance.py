"""Obstacle avoidance path planner using grid-based A* within a polygon.

The planner operates in a local metric frame anchored to the start point's
latitude/longitude. Obstacles and boundary are provided as Position lists.
"""
from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from math import hypot
from typing import Iterable, List, Optional, Sequence, Tuple

# Lazy import shapely to avoid import-time errors when not installed
from typing import TYPE_CHECKING
if TYPE_CHECKING:  # pragma: no cover
    from shapely.geometry import Point as SPoint  # type: ignore
    from shapely.geometry import Polygon  # type: ignore
    from shapely.ops import unary_union  # type: ignore

from ..models import Position, Waypoint


@dataclass(frozen=True)
class AStarConfig:
    grid_resolution_m: float = 0.25
    safety_margin_m: float = 0.1  # Inflate obstacles by this margin
    max_expansions: int = 20000


def _deg_lat_m() -> float:
    return 111_000.0


def _deg_lon_m_at_lat(lat: float) -> float:
    from math import cos, radians

    return 111_000.0 * cos(radians(lat))


def _to_xy(lat: float, lon: float, olat: float, olon: float) -> Tuple[float, float]:
    return ((lon - olon) * _deg_lon_m_at_lat(olat), (lat - olat) * _deg_lat_m())


def _to_ll(x: float, y: float, olat: float, olon: float) -> Tuple[float, float]:
    return (olat + y / _deg_lat_m(), olon + x / _deg_lon_m_at_lat(olat))


def _poly_from_positions(boundary: Sequence[Position], olat: float, olon: float):
    from shapely.geometry import Polygon  # type: ignore
    if len(boundary) < 3:
        raise ValueError("boundary must have at least 3 vertices")
    pts = [_to_xy(p.latitude, p.longitude, olat, olon) for p in boundary]
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if not poly.is_valid:
        raise ValueError("Invalid boundary polygon")
    return poly


def _obstacles_union(obstacles: Iterable[Sequence[Position]] | None, olat: float, olon: float, inflate: float):
    from shapely.ops import unary_union  # type: ignore
    if not obstacles:
        return None
    polys: List["Polygon"] = []
    for obs in obstacles:
        if len(obs) < 3:
            continue
        poly = _poly_from_positions(obs, olat, olon)
        if inflate > 0:
            poly = poly.buffer(inflate)
        if poly.is_valid and poly.area > 0:
            polys.append(poly)
    if not polys:
        return None
    return unary_union(polys)


def plan_path_astar(
    start: Position,
    goal: Position,
    boundary: Sequence[Position],
    *,
    obstacles: Iterable[Sequence[Position]] | None = None,
    config: AStarConfig | None = None,
) -> List[Waypoint]:
    cfg = config or AStarConfig()
    olat = start.latitude
    olon = start.longitude

    area = _poly_from_positions(boundary, olat, olon)
    inflated_obs = _obstacles_union(obstacles, olat, olon, cfg.safety_margin_m)
    if inflated_obs is not None:
        free = area.difference(inflated_obs)
        if free.is_empty:
            return []
        area = free

    sx, sy = _to_xy(start.latitude, start.longitude, olat, olon)
    gx, gy = _to_xy(goal.latitude, goal.longitude, olat, olon)

    step = cfg.grid_resolution_m

    def nbrs(nx: float, ny: float) -> List[Tuple[float, float]]:
        from shapely.geometry import Point as SPoint  # type: ignore
        # 8-connected grid
        dirs = [
            (step, 0), (-step, 0), (0, step), (0, -step),
            (step, step), (step, -step), (-step, step), (-step, -step),
        ]
        res: List[Tuple[float, float]] = []
        for dx, dy in dirs:
            x2, y2 = nx + dx, ny + dy
            if area.contains(SPoint(x2, y2)):
                res.append((x2, y2))
        return res

    # A* search
    open_heap: List[Tuple[float, Tuple[float, float]]] = []
    heappush(open_heap, (0.0, (sx, sy)))
    g: dict[Tuple[float, float], float] = {(sx, sy): 0.0}
    parent: dict[Tuple[float, float], Tuple[float, float]] = {}

    def h(x: float, y: float) -> float:
        return hypot(x - gx, y - gy)

    visited = 0
    closed: set[Tuple[float, float]] = set()

    while open_heap and visited < cfg.max_expansions:
        _, (cx, cy) = heappop(open_heap)
        if (cx, cy) in closed:
            continue
        closed.add((cx, cy))
        visited += 1
        if hypot(cx - gx, cy - gy) <= step:
            # reconstruct
            path: List[Tuple[float, float]] = [(cx, cy)]
            while (cx, cy) in parent:
                cx, cy = parent[(cx, cy)]
                path.append((cx, cy))
            path.reverse()
            # Convert to waypoints in lat/lon
            wps: List[Waypoint] = []
            for x, y in path:
                lat, lon = _to_ll(x, y, olat, olon)
                wps.append(Waypoint(position=Position(latitude=lat, longitude=lon)))
            return wps
        for nx, ny in nbrs(cx, cy):
            tentative = g[(cx, cy)] + hypot(nx - cx, ny - cy)
            if (nx, ny) not in g or tentative < g[(nx, ny)]:
                g[(nx, ny)] = tentative
                parent[(nx, ny)] = (cx, cy)
                heappush(open_heap, (tentative + h(nx, ny), (nx, ny)))

    return []


__all__ = ["AStarConfig", "plan_path_astar"]
