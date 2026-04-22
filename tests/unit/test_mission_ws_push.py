"""Tests for ARCH-007: MissionService WebSocket push on lifecycle transitions."""
import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.src.models.mission import MissionWaypoint


class _DummyNav:
    """Minimal nav stub for WS push tests — no hardware, no side-effects."""

    def __init__(self):
        from types import SimpleNamespace
        from backend.src.models import NavigationMode

        self.navigation_state = SimpleNamespace(
            navigation_mode=NavigationMode.IDLE,
            planned_path=[],
            current_waypoint_index=0,
            safety_boundaries=[],
        )

    async def execute_mission(self, mission, mission_service=None):
        return None

    async def stop_navigation(self):
        return True

    async def emergency_stop(self):
        return True

    async def set_speed(self, left, right):
        pass


_WAYPOINTS = [MissionWaypoint(lat=1.0, lon=1.0, blade_on=False, speed=50)]


@pytest.mark.asyncio
async def test_mission_start_broadcasts_status_event():
    """MissionService.start_mission must emit mission.status WS event."""
    from backend.src.services.mission_service import MissionService

    mock_hub = MagicMock()
    mock_hub.broadcast_to_topic = AsyncMock()

    svc = MissionService(navigation_service=_DummyNav(), websocket_hub=mock_hub)
    mission = await svc.create_mission("Test Mission", _WAYPOINTS)
    await svc.start_mission(mission.id)

    mock_hub.broadcast_to_topic.assert_called()
    call_topics = [c.args[0] for c in mock_hub.broadcast_to_topic.call_args_list]
    assert "mission.status" in call_topics


@pytest.mark.asyncio
async def test_mission_abort_broadcasts_status_event():
    """MissionService.abort_mission must emit mission.status WS event."""
    from backend.src.services.mission_service import MissionService

    mock_hub = MagicMock()
    mock_hub.broadcast_to_topic = AsyncMock()

    svc = MissionService(navigation_service=_DummyNav(), websocket_hub=mock_hub)
    mission = await svc.create_mission("Test Mission", _WAYPOINTS)
    await svc.start_mission(mission.id)
    await svc.abort_mission(mission.id)

    topics = [c.args[0] for c in mock_hub.broadcast_to_topic.call_args_list]
    assert topics.count("mission.status") >= 2  # one for start, one for abort


@pytest.mark.asyncio
async def test_mission_without_hub_does_not_raise():
    """MissionService with no websocket_hub must not raise on lifecycle transitions."""
    from backend.src.services.mission_service import MissionService

    svc = MissionService(navigation_service=_DummyNav(), websocket_hub=None)
    mission = await svc.create_mission("Test Mission", _WAYPOINTS)
    await svc.start_mission(mission.id)  # Must not raise
    await svc.abort_mission(mission.id)  # Must not raise

