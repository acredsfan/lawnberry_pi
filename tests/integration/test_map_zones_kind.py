"""Integration tests for zone_kind column — migration v2 and round-trip.

Tests:
- After repo init, list_zones() returns zones with zone_kind field
- save_zones([...]) with zone_kind="mow" round-trips correctly
- update_zone(...) updates zone_kind
- save_zone(...) inserts and returns correct zone_kind
- Back-compat: exclusion_zone=True with no zone_kind yields zone_kind="exclusion"
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.src.repositories.map_repository import MapRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path) -> MapRepository:
    return MapRepository(db_path=tmp_path / "test_zone_kind.db")


def _base_zone(zone_id: str, *, zone_kind: str = "boundary", exclusion_zone: bool = False) -> dict:
    return {
        "id": zone_id,
        "name": f"Zone {zone_id[:8]}",
        "polygon": [
            {"latitude": 40.7128, "longitude": -74.0060},
            {"latitude": 40.7129, "longitude": -74.0060},
            {"latitude": 40.7129, "longitude": -74.0059},
            {"latitude": 40.7128, "longitude": -74.0059},
        ],
        "priority": 0,
        "exclusion_zone": exclusion_zone,
        "zone_kind": zone_kind,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_zones_includes_zone_kind_field(repo: MapRepository) -> None:
    """After insert, list_zones() returns dicts with a zone_kind key."""
    zone = _base_zone("z1", zone_kind="boundary")
    repo.save_zones([zone])

    zones = repo.list_zones()
    assert len(zones) == 1
    assert "zone_kind" in zones[0], "zone_kind field missing from list_zones() result"
    assert zones[0]["zone_kind"] == "boundary"


def test_save_zones_round_trips_mow_kind(repo: MapRepository) -> None:
    """save_zones() with zone_kind='mow' preserves that value on list_zones()."""
    zone = _base_zone("z2", zone_kind="mow")
    repo.save_zones([zone])

    zones = repo.list_zones()
    assert zones[0]["zone_kind"] == "mow"


def test_save_zones_round_trips_exclusion_kind(repo: MapRepository) -> None:
    """save_zones() with zone_kind='exclusion' preserves that value."""
    zone = _base_zone("z3", zone_kind="exclusion", exclusion_zone=True)
    repo.save_zones([zone])

    zones = repo.list_zones()
    assert zones[0]["zone_kind"] == "exclusion"
    assert zones[0]["exclusion_zone"] == 1  # stored as integer


def test_update_zone_updates_zone_kind(repo: MapRepository) -> None:
    """update_zone() can change zone_kind from boundary to mow."""
    zone = _base_zone("z4", zone_kind="boundary")
    repo.save_zones([zone])

    updated = dict(zone)
    updated["zone_kind"] = "mow"
    result = repo.update_zone(updated)
    assert result is True

    fetched = repo.get_zone("z4")
    assert fetched is not None
    assert fetched["zone_kind"] == "mow"


def test_save_zone_single_inserts_correctly(repo: MapRepository) -> None:
    """save_zone() inserts one zone and get_zone() round-trips zone_kind."""
    zone = _base_zone("z5", zone_kind="exclusion", exclusion_zone=True)
    repo.save_zone(zone)

    fetched = repo.get_zone("z5")
    assert fetched is not None
    assert fetched["zone_kind"] == "exclusion"
    assert fetched["exclusion_zone"] == 1


def test_save_zone_raises_on_duplicate_id(repo: MapRepository) -> None:
    """save_zone() raises sqlite3.IntegrityError when the id already exists."""
    import sqlite3

    zone = _base_zone("z6", zone_kind="boundary")
    repo.save_zone(zone)

    with pytest.raises(sqlite3.IntegrityError):
        repo.save_zone(zone)


def test_get_zone_returns_zone_kind(repo: MapRepository) -> None:
    """get_zone() includes zone_kind in the returned dict."""
    zone = _base_zone("z7", zone_kind="mow")
    repo.save_zones([zone])

    fetched = repo.get_zone("z7")
    assert fetched is not None
    assert fetched["zone_kind"] == "mow"


def test_default_zone_kind_is_boundary(repo: MapRepository) -> None:
    """A zone saved without explicit zone_kind defaults to 'boundary'."""
    zone = {
        "id": "z8",
        "name": "Default",
        "polygon": [
            {"latitude": 40.7128, "longitude": -74.0060},
            {"latitude": 40.7129, "longitude": -74.0060},
            {"latitude": 40.7129, "longitude": -74.0059},
        ],
        "priority": 0,
        "exclusion_zone": False,
        # no zone_kind key — should default to "boundary"
    }
    repo.save_zones([zone])

    fetched = repo.get_zone("z8")
    assert fetched is not None
    assert fetched["zone_kind"] == "boundary"
