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
from dataclasses import dataclass, field
from typing import Any

from backend.src.models.mission import MissionWaypoint
from backend.src.nav.coverage_planner import plan_coverage

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
              - ``blade_on``    (bool, default True)  — set on every waypoint.
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
            if z["id"] == zone_id and not z.get("exclusion_zone", False):
                boundary_zone = z
                break

        if boundary_zone is None:
            raise KeyError(f"Boundary zone not found: {zone_id!r}")

        # Collect exclusion zones
        exclusion_zones = [z for z in all_zones if z.get("exclusion_zone", False)]

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

        # Dispatch to coverage planner
        if pattern == "parallel":
            path_points, _row_count, length_m = plan_coverage(
                boundary=boundary,
                exclusion_polys=exclusions if exclusions else None,
                spacing_m=spacing_m,
                angle_deg=angle_deg,
            )
        else:  # pragma: no cover — guarded by pattern validation above
            raise ValueError(f"unknown pattern: {pattern!r}")

        # Convert path points to MissionWaypoint objects
        waypoints: list[MissionWaypoint] = [
            MissionWaypoint(lat=lat, lon=lon, blade_on=blade_on, speed=speed_pct)
            for lat, lon in path_points
        ]

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


# ---------------------------------------------------------------------------
# Module-level singleton and factory
# ---------------------------------------------------------------------------

planning_service = PlanningService()


def get_planning_service() -> PlanningService:
    """Return the module-level PlanningService singleton."""
    return planning_service
