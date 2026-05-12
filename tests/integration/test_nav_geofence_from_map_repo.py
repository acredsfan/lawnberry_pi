"""Integration tests: NavigationService._load_boundaries_from_zones reads from MapRepository.

T4: Retarget nav geofence loader from _zones_store to MapRepository.

Tests:
- Zones saved via MapRepository appear as safety_boundaries (non-exclusion zones).
- Exclusion zones saved via MapRepository appear in no_go_zones.
- Empty MapRepository gracefully results in empty boundaries (no crash).
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

# SIM_MODE must be set before importing any backend module that touches hardware.
os.environ.setdefault("SIM_MODE", "1")


@pytest.fixture()
def map_repo(tmp_path: Path):
    """Return a fresh MapRepository backed by a temp SQLite file."""
    from backend.src.repositories.map_repository import MapRepository

    return MapRepository(db_path=tmp_path / "test_geofence.db")


@pytest.fixture()
def nav_service(map_repo):
    """Return a fresh NavigationService with the temp MapRepository attached."""
    # Reset singleton so each test starts clean.
    from backend.src.services.navigation_service import NavigationService

    NavigationService._instance = None
    nav = NavigationService()
    nav.attach_map_repository(map_repo)
    yield nav
    # Cleanup singleton after test.
    NavigationService._instance = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_square_zone(
    zone_id: str,
    name: str,
    lat: float = 40.0,
    lon: float = -75.0,
    size: float = 0.001,
    exclusion_zone: bool = False,
    priority: int = 1,
) -> dict:
    """Build a minimal zone dict compatible with MapRepository.save_zones."""
    polygon = [
        {"latitude": lat, "longitude": lon},
        {"latitude": lat + size, "longitude": lon},
        {"latitude": lat + size, "longitude": lon + size},
        {"latitude": lat, "longitude": lon + size},
    ]
    return {
        "id": zone_id,
        "name": name,
        "polygon": polygon,
        "exclusion_zone": exclusion_zone,
        "priority": priority,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_boundaries_loaded_from_persisted_zones(map_repo, nav_service):
    """Non-exclusion zones saved via MapRepository appear in safety_boundaries."""
    zone = _make_square_zone("z1", "Front Lawn", exclusion_zone=False)
    map_repo.save_zones([zone])

    # Boundaries should be empty before loading.
    assert nav_service.navigation_state.safety_boundaries == []

    nav_service._load_boundaries_from_zones()

    boundaries = nav_service.navigation_state.safety_boundaries
    assert len(boundaries) == 1, f"Expected 1 boundary polygon, got {len(boundaries)}"
    # Each boundary is a list of Position objects.
    pts = boundaries[0]
    assert len(pts) == 4, f"Expected 4 polygon points, got {len(pts)}"
    # Spot-check that coordinates round-trip correctly.
    lats = {round(p.latitude, 6) for p in pts}
    lons = {round(p.longitude, 6) for p in pts}
    assert 40.0 in lats
    assert -75.0 in lons


def test_exclusion_zones_become_no_go_zones(map_repo, nav_service):
    """Exclusion zones saved via MapRepository appear in no_go_zones."""
    excl = _make_square_zone("ex1", "Flower Bed", lat=40.01, exclusion_zone=True)
    map_repo.save_zones([excl])

    nav_service._load_boundaries_from_zones()

    no_go = nav_service.navigation_state.no_go_zones
    assert len(no_go) == 1, f"Expected 1 no-go zone, got {len(no_go)}"
    pts = no_go[0]
    assert len(pts) == 4

    # safety_boundaries should remain empty (no mowing zones were saved).
    assert nav_service.navigation_state.safety_boundaries == []


def test_mixed_zones_separated_correctly(map_repo, nav_service):
    """Mowing zones go to safety_boundaries; exclusion zones go to no_go_zones."""
    mow = _make_square_zone("m1", "Main Lawn", lat=40.0, exclusion_zone=False)
    excl = _make_square_zone("ex1", "Pond", lat=40.01, exclusion_zone=True)
    map_repo.save_zones([mow, excl])

    nav_service._load_boundaries_from_zones()

    assert len(nav_service.navigation_state.safety_boundaries) == 1
    assert len(nav_service.navigation_state.no_go_zones) == 1


def test_empty_map_repo_gracefully_no_boundaries(map_repo, nav_service):
    """Empty MapRepository (no zones) does not crash and leaves boundaries empty."""
    # Nothing saved.
    nav_service._load_boundaries_from_zones()

    assert nav_service.navigation_state.safety_boundaries == []
    assert nav_service.navigation_state.no_go_zones == []


def test_multiple_mowing_zones_all_become_boundaries(map_repo, nav_service):
    """Multiple non-exclusion zones all appear as separate boundary polygons."""
    zones = [
        _make_square_zone(f"m{i}", f"Zone {i}", lat=40.0 + i * 0.01, exclusion_zone=False)
        for i in range(3)
    ]
    map_repo.save_zones(zones)

    nav_service._load_boundaries_from_zones()

    assert len(nav_service.navigation_state.safety_boundaries) == 3


def test_load_boundaries_does_not_require_rest_api(map_repo, nav_service, monkeypatch):
    """_load_boundaries_from_zones must NOT import backend.src.api.rest."""
    import sys

    # Block the rest module import to confirm it is not used.
    original = sys.modules.get("backend.src.api.rest")
    # If not imported yet, block it; if already imported, ensure _zones_store is not read.
    monkeypatch.setitem(sys.modules, "backend.src.api.rest", None)  # type: ignore[arg-type]

    mow = _make_square_zone("m1", "Lawn", exclusion_zone=False)
    map_repo.save_zones([mow])

    # Should succeed even though rest is blocked.
    nav_service._load_boundaries_from_zones()

    assert len(nav_service.navigation_state.safety_boundaries) == 1
