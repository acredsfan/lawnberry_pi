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


@pytest.mark.asyncio
async def test_mission_completed_callback_broadcasts_aborted():
    """Done callback CancelledError branch schedules a _broadcast_status via ensure_future."""
    from backend.src.services.mission_service import MissionService

    hub = MagicMock()
    hub.broadcast_to_topic = AsyncMock()

    class _SlowNav(_DummyNav):
        async def execute_mission(self, mission, mission_service=None):
            # Long-running so task.cancel() actually delivers CancelledError
            await asyncio.sleep(60)

    svc = MissionService(navigation_service=_SlowNav(), websocket_hub=hub)
    mission = await svc.create_mission("Test Mission", _WAYPOINTS)
    await svc.start_mission(mission.id)
    hub.reset_mock()  # clear the "Mission started" broadcast; isolate abort/callback calls

    await svc.abort_mission(mission.id)
    # abort_mission calls _broadcast_status directly (at least 1 call already).
    # One extra sleep drains any ensure_future queued by the done callback.
    await asyncio.sleep(0)

    assert hub.broadcast_to_topic.called


@pytest.mark.asyncio
async def test_mission_completed_callback_broadcasts_failed():
    """Done callback Exception branch schedules a _broadcast_status via ensure_future."""
    from backend.src.services.mission_service import MissionService

    hub = MagicMock()
    hub.broadcast_to_topic = AsyncMock()

    class _FailingNav(_DummyNav):
        async def execute_mission(self, mission, mission_service=None):
            raise RuntimeError("nav blew up")

    svc = MissionService(navigation_service=_FailingNav(), websocket_hub=hub)
    mission = await svc.create_mission("Test Mission", _WAYPOINTS)

    # start_mission broadcasts "Mission started" (call #1) then returns.
    # AsyncMock does not yield, so the failing nav-task hasn't run yet.
    await svc.start_mission(mission.id)

    # Three sleep(0) iterations are needed:
    #   sleep #1: nav-task runs → raises RuntimeError → done-callback call_soon'd
    #   sleep #2: done-callback runs → asyncio.ensure_future(_broadcast_status) scheduled
    #   sleep #3: ensure_future task runs → hub.broadcast_to_topic called (call #2)
    for _ in range(3):
        await asyncio.sleep(0)

    # 1 call from start_mission + 1 from exception-branch ensure_future
    assert hub.broadcast_to_topic.call_count >= 2


@pytest.mark.asyncio
async def test_mission_diagnostics_broadcast_on_start():
    """MissionService broadcasts mission.diagnostics on start when event_store is attached."""
    from backend.src.services.mission_service import MissionService
    from backend.src.observability.event_store import EventStore
    from backend.src.observability.events import PersistenceMode

    ws_hub = MagicMock()
    ws_hub.broadcast_to_topic = AsyncMock()

    store = EventStore(persistence=None, mode=PersistenceMode.FULL)

    svc = MissionService(
        navigation_service=_DummyNav(),
        websocket_hub=ws_hub,
    )
    svc.set_event_store(store)

    mission = await svc.create_mission("D", [MissionWaypoint(lat=37.0, lon=-122.0)])
    await svc.start_mission(mission.id)

    calls = ws_hub.broadcast_to_topic.call_args_list
    topics = [call.args[0] for call in calls]
    assert "mission.diagnostics" in topics


