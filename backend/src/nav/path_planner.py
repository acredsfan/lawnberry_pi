"""High-level path planner that composes coverage, avoidance, and utilities.

Provides a stable API used by NavigationService.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, List, Sequence

from ..models import Position, Waypoint
from .coverage_patterns import CoverageConfig, generate_lawnmower
from .obstacle_avoidance import AStarConfig, plan_path_astar


class PathPlanner:
    """Path planning algorithms and utilities"""

    @staticmethod
    def calculate_distance(pos1: Position, pos2: Position) -> float:
        """Calculate distance between two positions in meters.

        Uses the Haversine formula suitable for short-distance path segments.
        """
        lat1 = math.radians(pos1.latitude)
        lat2 = math.radians(pos2.latitude)
        dlat = lat2 - lat1
        dlon = math.radians(pos2.longitude - pos1.longitude)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return 6_371_000.0 * c

    @staticmethod
    def calculate_bearing(pos1: Position, pos2: Position) -> float:
        lat1 = math.radians(pos1.latitude)
        lat2 = math.radians(pos2.latitude)
        dlon = math.radians(pos2.longitude - pos1.longitude)
        x = math.sin(dlon) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        bearing = math.degrees(math.atan2(x, y))
        return (bearing + 360.0) % 360.0

    # Coverage
    @staticmethod
    def generate_parallel_lines_path(
        boundaries: Sequence[Position], *, cutting_width: float = 0.3, overlap: float = 0.1
    ) -> List[Waypoint]:
        cfg = CoverageConfig(swath_width_m=cutting_width, overlap=overlap)
        return generate_lawnmower(boundaries, config=cfg)

    # Boundary following
    @staticmethod
    def boundary_follow(boundary: Sequence[Position], *, waypoint_speed_ms: float = 0.3) -> List[Waypoint]:
        if len(boundary) < 2:
            return []
        wps: List[Waypoint] = []
        for p in boundary + boundary[:1]:  # close loop implicitly
            wps.append(Waypoint(position=p, target_speed=waypoint_speed_ms, action="edge"))
        return wps

    # Point-to-point with avoidance
    @staticmethod
    def find_path(
        start: Position,
        goal: Position,
        boundary: Sequence[Position],
        *,
        obstacles: Iterable[Sequence[Position]] | None = None,
        grid_resolution_m: float = 0.25,
    ) -> List[Waypoint]:
        cfg = AStarConfig(grid_resolution_m=grid_resolution_m)
        return plan_path_astar(start, goal, boundary, obstacles=obstacles, config=cfg)

    # Return-to-base helper
    @staticmethod
    def return_to_base(
        current: Position,
        home: Position,
        boundary: Sequence[Position] | None,
        obstacles: Iterable[Sequence[Position]] | None = None,
    ) -> List[Waypoint]:
        if boundary is None or len(boundary) < 3:
            # Direct path fallback
            return [Waypoint(position=home, target_speed=0.5, action="dock")]
        path = PathPlanner.find_path(current, home, boundary, obstacles=obstacles, grid_resolution_m=0.3)
        if not path:
            return [Waypoint(position=home, target_speed=0.5, action="dock")]
        # Ensure final docking action
        path[-1].action = "dock"
        if path[-1].target_speed is None:
            path[-1].target_speed = 0.5
        return path


__all__ = ["PathPlanner"]
