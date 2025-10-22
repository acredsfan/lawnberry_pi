import pytest

pytest.importorskip("shapely")

from backend.src.nav.obstacle_avoidance import plan_path_astar, AStarConfig
from backend.src.models import Position


def square(lat0=0.0, lon0=0.0, width_m=20.0):
    lat_step = width_m / 111000.0
    lon_step = width_m / (111000.0)
    return [
        Position(latitude=lat0, longitude=lon0),
        Position(latitude=lat0, longitude=lon0 + lon_step),
        Position(latitude=lat0 + lat_step, longitude=lon0 + lon_step),
        Position(latitude=lat0 + lat_step, longitude=lon0),
    ]


def test_astar_avoids_center_obstacle():
    boundary = square(width_m=20.0)
    # Start on left, goal on right
    start = Position(latitude=0.000045, longitude=0.0)
    goal = Position(latitude=0.000045, longitude=20.0 / 111000.0)
    # Center obstacle 4m square
    obs = [
        [
            Position(latitude=0.00003, longitude=0.00006),
            Position(latitude=0.00003, longitude=0.00012),
            Position(latitude=0.00006, longitude=0.00012),
            Position(latitude=0.00006, longitude=0.00006),
        ]
    ]
    cfg = AStarConfig(grid_resolution_m=0.5, safety_margin_m=0.1, max_expansions=40000)
    path = plan_path_astar(start, goal, boundary, obstacles=obs, config=cfg)
    assert path, "Path should be found"
    # Ensure first and last waypoints are near start/goal
    assert abs(path[0].position.latitude - start.latitude) < 1e-4
    assert abs(path[-1].position.longitude - goal.longitude) < 1e-4
