from backend.src.models import Position, Waypoint
from backend.src.nav.path_planner import PathPlanner


def test_return_to_base_fails_closed_without_boundary():
    current = Position(latitude=40.0, longitude=-75.0)
    home = Position(latitude=40.0001, longitude=-75.0001)

    assert PathPlanner.return_to_base(current, home, None) == []


def test_return_to_base_fails_closed_when_astar_has_no_route(monkeypatch):
    current = Position(latitude=40.0, longitude=-75.0)
    home = Position(latitude=40.0001, longitude=-75.0001)
    boundary = [
        Position(latitude=39.999, longitude=-75.001),
        Position(latitude=39.999, longitude=-74.999),
        Position(latitude=40.001, longitude=-74.999),
    ]
    monkeypatch.setattr(PathPlanner, "find_path", lambda *args, **kwargs: [])

    assert PathPlanner.return_to_base(current, home, boundary) == []


def test_return_to_base_marks_final_route_leg_as_dock(monkeypatch):
    current = Position(latitude=40.0, longitude=-75.0)
    home = Position(latitude=40.0001, longitude=-75.0001)
    boundary = [
        Position(latitude=39.999, longitude=-75.001),
        Position(latitude=39.999, longitude=-74.999),
        Position(latitude=40.001, longitude=-74.999),
    ]
    route = [Waypoint(position=home, target_speed=0.2)]
    monkeypatch.setattr(PathPlanner, "find_path", lambda *args, **kwargs: route)

    planned = PathPlanner.return_to_base(current, home, boundary)

    assert planned[-1].action == "dock"
