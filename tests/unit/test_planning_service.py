# tests/unit/test_planning_service.py
"""Unit tests for PlanningService.plan_path_for_zone.

Run: SIM_MODE=1 pytest tests/unit/test_planning_service.py -v --tb=short
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from backend.src.services.planning_service import PlanningService
from backend.src.nav.geoutils import point_in_polygon


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A 0.001° square (~111 m × ~111 m) around (10.0, 20.0)
BOUNDARY_ZONE = {
    "id": "boundary-1",
    "name": "Front Lawn",
    "polygon": [
        [10.000, 20.000],
        [10.001, 20.000],
        [10.001, 20.001],
        [10.000, 20.001],
    ],
    "exclusion_zone": False,
    "priority": 1,
}

# A small exclusion zone in the centre of the boundary square.
# Coordinates chosen so no scanline endpoint lands exactly on the boundary
# (scanline endpoints fall at boundary edges after interval subtraction).
EXCLUSION_ZONE = {
    "id": "excl-1",
    "name": "Flower Bed",
    "polygon": [
        [10.00031, 20.00031],
        [10.00069, 20.00031],
        [10.00069, 20.00069],
        [10.00031, 20.00069],
    ],
    "exclusion_zone": True,
    "priority": 0,
}


def _make_repo(zones: list[dict]) -> MagicMock:
    """Return a mock MapRepository whose list_zones() returns zones."""
    repo = MagicMock()
    repo.list_zones.return_value = zones
    return repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plan_path_for_zone_returns_waypoints_inside_boundary() -> None:
    """plan_path_for_zone should return non-empty waypoints all inside boundary."""
    repo = _make_repo([BOUNDARY_ZONE])
    svc = PlanningService()
    svc.set_map_repository(repo)

    boundary_poly = [(p[0], p[1]) for p in BOUNDARY_ZONE["polygon"]]

    result = await svc.plan_path_for_zone(
        zone_id="boundary-1",
        pattern="parallel",
        params={"spacing_m": 5.0},
    )

    assert result.waypoints, "waypoints list must be non-empty"
    for wp in result.waypoints:
        assert point_in_polygon(wp.lat, wp.lon, boundary_poly), (
            f"Waypoint ({wp.lat}, {wp.lon}) is outside boundary"
        )


def _strictly_inside_exclusion(lat: float, lon: float, excl: list[list[float]]) -> bool:
    """Return True only if (lat, lon) is strictly inside the exclusion AABB
    (all four coordinates comfortably within the boundary, not on the edge).

    The scanline interval-subtraction algorithm intentionally produces
    waypoints on the exact exclusion boundary edge (that is the cut point).
    We therefore only flag points that are clearly *inside*, not edge-touching.
    """
    lats = [p[0] for p in excl]
    lons = [p[1] for p in excl]
    lat_min, lat_max = min(lats), max(lats)
    lon_min, lon_max = min(lons), max(lons)
    tol = 1e-9  # floating-point tolerance: ignore points within 1e-9° of the boundary
    return (
        lat > lat_min + tol
        and lat < lat_max - tol
        and lon > lon_min + tol
        and lon < lon_max - tol
    )


@pytest.mark.asyncio
async def test_plan_path_for_zone_skips_exclusion_zones() -> None:
    """Waypoints must not fall strictly inside the exclusion polygon.

    The coverage planner carves the exclusion zone out of each scanline.
    Points that fall on the exact exclusion boundary edge are acceptable
    (they are the last point of a trimmed scanline segment); only interior
    points would indicate a planning bug.
    """
    repo = _make_repo([BOUNDARY_ZONE, EXCLUSION_ZONE])
    svc = PlanningService()
    svc.set_map_repository(repo)

    result = await svc.plan_path_for_zone(
        zone_id="boundary-1",
        pattern="parallel",
        params={"spacing_m": 5.0},
    )

    assert result.waypoints, "waypoints list must be non-empty"
    for wp in result.waypoints:
        assert not _strictly_inside_exclusion(wp.lat, wp.lon, EXCLUSION_ZONE["polygon"]), (
            f"Waypoint ({wp.lat}, {wp.lon}) falls strictly inside exclusion zone"
        )


@pytest.mark.asyncio
async def test_unimplemented_pattern_raises_not_implemented() -> None:
    """Calling with pattern='spiral' should raise NotImplementedError."""
    repo = _make_repo([BOUNDARY_ZONE])
    svc = PlanningService()
    svc.set_map_repository(repo)

    with pytest.raises(NotImplementedError):
        await svc.plan_path_for_zone(
            zone_id="boundary-1",
            pattern="spiral",
            params={},
        )


@pytest.mark.asyncio
async def test_unknown_pattern_raises_value_error() -> None:
    """Calling with an unknown pattern string should raise ValueError."""
    repo = _make_repo([BOUNDARY_ZONE])
    svc = PlanningService()
    svc.set_map_repository(repo)

    with pytest.raises(ValueError):
        await svc.plan_path_for_zone(
            zone_id="boundary-1",
            pattern="zigzag",
            params={},
        )


@pytest.mark.asyncio
async def test_zone_not_found_raises_key_error() -> None:
    """Requesting a non-existent zone_id should raise KeyError."""
    repo = _make_repo([BOUNDARY_ZONE])
    svc = PlanningService()
    svc.set_map_repository(repo)

    with pytest.raises(KeyError):
        await svc.plan_path_for_zone(
            zone_id="does-not-exist",
            pattern="parallel",
            params={"spacing_m": 5.0},
        )


@pytest.mark.asyncio
async def test_planned_path_length_and_duration_positive() -> None:
    """length_m and est_duration_s should be positive for a valid zone."""
    repo = _make_repo([BOUNDARY_ZONE])
    svc = PlanningService()
    svc.set_map_repository(repo)

    result = await svc.plan_path_for_zone(
        zone_id="boundary-1",
        pattern="parallel",
        params={"spacing_m": 5.0, "speed_ms": 0.5},
    )

    assert result.length_m > 0
    assert result.est_duration_s > 0
