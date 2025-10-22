from datetime import UTC, datetime

import pytest

from backend.src.models import NavigationMode, PathStatus, Position, Waypoint
from backend.src.services.navigation_service import NavigationService


class FakeWeatherService:
    def __init__(self, advice: str):
        self._advice = advice

    def get_current(self, latitude=None, longitude=None):
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "fake",
            "temperature_c": 20.0,
            "humidity_percent": 50.0,
            "pressure_hpa": 1013.0,
        }

    def get_planning_advice(self, current):
        if self._advice == "avoid":
            return {"advice": "avoid", "reasons": ["rain"]}
        return {"advice": "proceed", "reasons": []}


@pytest.mark.asyncio
async def test_start_navigation_blocked_by_weather_avoid():
    nav = NavigationService(weather=FakeWeatherService("avoid"))
    # Prepare planned path and current position
    nav.navigation_state.planned_path = [
        Waypoint(position=Position(latitude=1.0, longitude=2.0), target_speed=0.5)
    ]
    nav.navigation_state.current_waypoint_index = 0
    nav.navigation_state.path_status = PathStatus.PLANNED
    nav.navigation_state.current_position = Position(latitude=1.0, longitude=2.0)

    ok = await nav.start_autonomous_navigation()
    assert ok is False
    # Remains not started due to weather
    assert nav.navigation_state.navigation_mode == NavigationMode.IDLE
    assert nav.navigation_state.path_status == PathStatus.PLANNED


@pytest.mark.asyncio
async def test_start_navigation_allows_when_weather_proceed():
    nav = NavigationService(weather=FakeWeatherService("proceed"))
    nav.navigation_state.planned_path = [
        Waypoint(position=Position(latitude=1.0, longitude=2.0), target_speed=0.5)
    ]
    nav.navigation_state.current_waypoint_index = 0
    nav.navigation_state.path_status = PathStatus.PLANNED
    nav.navigation_state.current_position = Position(latitude=1.0, longitude=2.0)

    ok = await nav.start_autonomous_navigation()
    assert ok is True
    assert nav.navigation_state.navigation_mode != NavigationMode.IDLE
    assert nav.navigation_state.path_status == PathStatus.EXECUTING
