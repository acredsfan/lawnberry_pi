# tests/unit/test_map_repository.py
"""Unit tests for MapRepository.

All tests use tmp_path so real data/ is never touched.
Run: SIM_MODE=1 uv run pytest tests/unit/test_map_repository.py -v
"""
import pytest
from pathlib import Path
from backend.src.repositories.map_repository import MapRepository


@pytest.fixture
def repo(tmp_path: Path) -> MapRepository:
    return MapRepository(db_path=tmp_path / "map.db")


def test_list_zones_empty(repo: MapRepository) -> None:
    assert repo.list_zones() == []


def test_save_and_list_zones(repo: MapRepository) -> None:
    zone = {
        "id": "z1",
        "name": "Front lawn",
        "polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        "priority": 1,
        "exclusion_zone": False,
    }
    repo.save_zones([zone])
    zones = repo.list_zones()
    assert len(zones) == 1
    assert zones[0]["id"] == "z1"
    assert zones[0]["polygon"] == [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]]


def test_save_zones_replaces_all(repo: MapRepository) -> None:
    repo.save_zones([{"id": "z1", "name": "A", "polygon": [[0, 0], [1, 0], [1, 1]], "priority": 0, "exclusion_zone": False}])
    repo.save_zones([{"id": "z2", "name": "B", "polygon": [[0, 0], [2, 0], [2, 2]], "priority": 0, "exclusion_zone": False}])
    zones = repo.list_zones()
    assert len(zones) == 1
    assert zones[0]["id"] == "z2"


def test_save_and_load_map_config(repo: MapRepository) -> None:
    config = {"provider": "osm", "zoom": 15, "center": [40.0, -75.0]}
    repo.save_map_config("default", config)
    loaded = repo.load_map_config("default")
    assert loaded is not None
    assert loaded["provider"] == "osm"
    assert loaded["zoom"] == 15


def test_load_map_config_missing(repo: MapRepository) -> None:
    assert repo.load_map_config("nonexistent") is None


def test_save_map_config_overwrites(repo: MapRepository) -> None:
    repo.save_map_config("cfg1", {"provider": "google"})
    repo.save_map_config("cfg1", {"provider": "osm"})
    loaded = repo.load_map_config("cfg1")
    assert loaded["provider"] == "osm"


def test_delete_zone(repo: MapRepository) -> None:
    repo.save_zones([{"id": "z1", "name": "X", "polygon": [[0, 0], [1, 0], [1, 1]], "priority": 0, "exclusion_zone": False}])
    deleted = repo.delete_zone("z1")
    assert deleted is True
    assert repo.list_zones() == []


def test_delete_zone_missing(repo: MapRepository) -> None:
    assert repo.delete_zone("does_not_exist") is False
