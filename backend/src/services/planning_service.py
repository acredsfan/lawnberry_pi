"""PlanningService — generates mowing paths for named zones.

Public API
----------
    async def plan_path_for_zone(
        self,
        zone_id: str,
        pattern: str,
        params: dict,
    ) -> PlannedPath

Module-level singleton
----------------------
    planning_service = PlanningService()

    def get_planning_service() -> PlanningService: ...

Late dependency injection (call from lifespan before first use)
---------------------------------------------------------------
    planning_service.set_map_repository(map_repository)
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from backend.src.models import Position
from backend.src.models.mission import MissionLegType, MissionWaypoint
from backend.src.nav.coverage_planner import plan_coverage_segments
from backend.src.nav.path_planner import PathPlanner
from backend.src.services.operating_area_service import load_operating_area_snapshot

logger = logging.getLogger(__name__)

# LatLng as used by plan_coverage: (lat, lon) tuples
LatLng = tuple[float, float]


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------


@dataclass
class PlannedPath:
    """Result of a coverage path planning operation."""

    waypoints: list[MissionWaypoint] = field(default_factory=list)
    length_m: float = 0.0
    est_duration_s: float = 0.0
    row_count: int = 0
    clearance_m: float = 0.0
    capabilities: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

_IMPLEMENTED_PATTERNS = {"parallel"}
_NOT_IMPLEMENTED_PATTERNS = {"spiral", "random"}


class PlanningService:
    """Generates serpentine coverage paths for a named boundary zone."""

    def __init__(self) -> None:
        self._map_repository: Any | None = None

    def set_map_repository(self, map_repository: Any) -> None:
        """Inject the MapRepository after construction (called from lifespan)."""
        self._map_repository = map_repository

    # ------------------------------------------------------------------
    # Main public method
    # ------------------------------------------------------------------

    async def plan_path_for_zone(
        self,
        zone_id: str,
        pattern: str,
        params: dict,
    ) -> PlannedPath:
        """Generate a coverage path for the zone identified by *zone_id*.

        Parameters
        ----------
        zone_id:
            ID of the boundary zone to plan for (``exclusion_zone=False``).
        pattern:
            ``"parallel"`` — serpentine boustrophedon scanlines.
            ``"spiral"`` or ``"random"`` — raise ``NotImplementedError``.
            Anything else — raise ``ValueError``.
        params:
            Planning parameters (all optional):
              - ``spacing_m``   (float, default 0.35) — scanline spacing in metres.
              - ``angle_deg``   (float, default 0.0)  — scanline bearing.
              - ``speed_ms``    (float, default 0.5)  — travel speed m/s for duration estimate.
              - ``blade_on``    (bool, default True)  — set only on declared mow legs.
              - ``speed_pct``   (int,  default 50)    — waypoint speed 0-100 %.

        Returns
        -------
        PlannedPath
            Dataclass with ``waypoints``, ``length_m``, ``est_duration_s``.

        Raises
        ------
        KeyError
            Zone not found or is an exclusion zone.
        NotImplementedError
            ``pattern`` is ``"spiral"`` or ``"random"``.
        ValueError
            ``pattern`` is not recognised at all.
        """
        # Validate pattern before touching the repository
        if pattern in _NOT_IMPLEMENTED_PATTERNS:
            raise NotImplementedError(f"pattern not implemented: {pattern!r}")
        if pattern not in _IMPLEMENTED_PATTERNS:
            raise ValueError(f"unknown pattern: {pattern!r}")

        # Load zones from the repository
        if self._map_repository is None:
            raise RuntimeError("PlanningService: map_repository not set — call set_map_repository()")

        all_zones: list[dict] = self._map_repository.list_zones()

        # Find the requested boundary zone (exclusion_zone must be False / absent)
        boundary_zone: dict | None = None
        for z in all_zones:
            if z["id"] == zone_id and _zone_kind(z) != "exclusion":
                boundary_zone = z
                break

        if boundary_zone is None:
            raise KeyError(f"Boundary zone not found: {zone_id!r}")

        # Collect exclusion zones
        exclusion_zones = [z for z in all_zones if _zone_kind(z) == "exclusion"]

        # Convert polygon storage format to list[LatLng]
        # MapRepository stores polygons as list of [lat, lon] (JSON arrays)
        boundary: list[LatLng] = _polygon_to_latlng(boundary_zone["polygon"])
        exclusions: list[list[LatLng]] = [
            _polygon_to_latlng(ez["polygon"]) for ez in exclusion_zones
        ]

        # Planning parameters
        spacing_m = float(params.get("spacing_m", 0.35))
        angle_deg = float(params.get("angle_deg", 0.0))
        speed_ms = float(params.get("speed_ms", 0.5))
        blade_on = bool(params.get("blade_on", True))
        speed_pct = int(params.get("speed_pct", 50))

        clearance_m = max(0.0, float(params.get("endpoint_clearance_m", 0.25) or 0.0))

        # Dispatch to the footprint-eroded coverage planner. It returns only
        # independent mow segments; every inter-segment connector is planned
        # and typed blade-off below.
        if pattern == "parallel":
            segments, _row_count, mow_length_m = plan_coverage_segments(
                boundary=boundary,
                exclusion_polys=exclusions if exclusions else None,
                spacing_m=spacing_m,
                angle_deg=angle_deg,
                # Keep a small numeric cushion so the subsequent swept-footprint
                # ``covers`` check is not balanced exactly on a GEOS boundary.
                clearance_m=clearance_m + 0.10,
            )
        else:  # pragma: no cover — guarded by pattern validation above
            raise ValueError(f"unknown pattern: {pattern!r}")

        if not segments:
            raise ValueError("Coverage area collapses after required footprint clearance")

        snapshot = load_operating_area_snapshot(
            map_repository=self._map_repository,
            selected_mow_zone_id=zone_id,
            allow_zone_fallback=True,
            prefer_zone_fallback=os.getenv("SIM_MODE", "0") == "1",
        )
        if not snapshot.valid:
            raise ValueError(f"Safe operating area unavailable: {snapshot.validity_state}")

        # Convert mow segments and safe A* connectors to typed mission legs.
        waypoints: list[MissionWaypoint] = []
        route_positions: list[Position] = []

        def append_waypoint(position: Position, leg_type: MissionLegType) -> None:
            if route_positions and PathPlanner.calculate_distance(route_positions[-1], position) < 0.02:
                return
            route_positions.append(position)
            waypoints.append(
                MissionWaypoint(
                    lat=position.latitude,
                    lon=position.longitude,
                    blade_on=blade_on and leg_type == MissionLegType.MOW,
                    leg_type=leg_type,
                    speed=speed_pct,
                )
            )

        for segment_index, segment in enumerate(segments):
            start = Position(latitude=segment.start[0], longitude=segment.start[1])
            end = Position(latitude=segment.end[0], longitude=segment.end[1])
            if not snapshot.contains_footprint(start, clearance_m) or not snapshot.contains_footprint(
                end, clearance_m
            ):
                raise ValueError("Coverage endpoint leaves footprint-safe free space")

            if segment_index == 0:
                append_waypoint(start, MissionLegType.TRANSIT)
            elif route_positions and PathPlanner.calculate_distance(route_positions[-1], start) >= 0.02:
                connector_start = route_positions[-1]
                if snapshot.segment_is_safe(connector_start, start, clearance_m):
                    append_waypoint(start, MissionLegType.TURN)
                else:
                    connector = PathPlanner.find_path(
                        connector_start,
                        start,
                        snapshot.safe_boundary,
                        obstacles=snapshot.exclusions,
                        grid_resolution_m=0.50,
                        safety_margin_m=clearance_m,
                        boundary_margin_m=clearance_m,
                    )
                    connector_positions = [waypoint.position for waypoint in connector]
                    if not connector_positions or not snapshot.path_is_safe(
                        connector_positions, clearance_m
                    ):
                        raise ValueError("No footprint-safe connector between coverage rows")
                    for position in connector_positions[1:]:
                        append_waypoint(position, MissionLegType.TURN)

            append_waypoint(end, MissionLegType.MOW)

        if not route_positions or not snapshot.path_is_safe(route_positions, clearance_m):
            raise ValueError("Generated coverage path leaves footprint-safe free space")

        length_m = sum(
            PathPlanner.calculate_distance(route_positions[index], route_positions[index + 1])
            for index in range(len(route_positions) - 1)
        )

        # Estimate duration
        est_duration_s = (length_m / speed_ms) if speed_ms > 0 else 0.0

        logger.info(
            "PlanningService: planned %d waypoints, %.1f m for zone %r (pattern=%s)",
            len(waypoints),
            length_m,
            zone_id,
            pattern,
        )

        return PlannedPath(
            waypoints=waypoints,
            length_m=length_m,
            est_duration_s=est_duration_s,
            row_count=_row_count,
            clearance_m=clearance_m,
            capabilities={
                "coverage_patterns": sorted(_IMPLEMENTED_PATTERNS),
                "blade_safe_connectors": True,
                "footprint_clearance": True,
                "dynamic_obstacle_replan": True,
                "mow_length_m": round(mow_length_m, 3),
            },
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _polygon_to_latlng(polygon: list) -> list[LatLng]:
    """Convert a stored polygon (list of [lat,lon] or (lat,lon)) to list[LatLng]."""
    result: list[LatLng] = []
    for point in polygon:
        if isinstance(point, (list, tuple)):
            result.append((float(point[0]), float(point[1])))
        elif isinstance(point, dict):
            # Support {"lat": ..., "lon": ...} or {"latitude": ..., "longitude": ...}
            lat = point.get("lat", point.get("latitude"))
            lon = point.get("lon", point.get("longitude"))
            result.append((float(lat), float(lon)))
        else:
            raise ValueError(f"Unsupported polygon point format: {point!r}")
    return result


def _zone_kind(zone: dict) -> str:
    kind = str(zone.get("zone_kind") or "").strip().lower()
    if kind:
        return "exclusion" if kind == "exclusion_zone" else kind
    return "exclusion" if bool(zone.get("exclusion_zone", False)) else "boundary"


# ---------------------------------------------------------------------------
# Module-level singleton and factory
# ---------------------------------------------------------------------------

planning_service = PlanningService()


def get_planning_service() -> PlanningService:
    """Return the module-level PlanningService singleton."""
    return planning_service
