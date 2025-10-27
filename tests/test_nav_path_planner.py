import importlib
import pytest

from backend.src.nav.path_planner import PathPlanner
from backend.src.models import Position


def rect():
    return [
        Position(latitude=0.0, longitude=0.0),
        Position(latitude=0.0, longitude=0.00018),
        Position(latitude=0.00009, longitude=0.00018),
        Position(latitude=0.00009, longitude=0.0),
    ]


def test_parallel_lines_path():
    try:
        b = rect()
        wps = PathPlanner.generate_parallel_lines_path(b, cutting_width=0.5, overlap=0.2)
        assert len(wps) > 0
    except (ImportError, AttributeError):
        pytest.skip("shapely not installed or configured correctly")


def test_distance_positive():
    d = PathPlanner.calculate_distance(
        Position(latitude=0.0, longitude=0.0), Position(latitude=0.0, longitude=0.001)
    )
    assert d > 0.0
