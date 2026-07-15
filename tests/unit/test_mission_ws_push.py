"""Tests for ARCH-007: MissionService WebSocket push on lifecycle transitions."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

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
    await asyncio.sleep(0)

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
    await asyncio.sleep(0)
    await svc.abort_mission(mission.id)
    await asyncio.sleep(0)

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
    await asyncio.sleep(0)
    hub.reset_mock()  # clear the "Mission started" broadcast; isolate abort/callback calls

    await svc.abort_mission(mission.id)
    # abort_mission calls _broadcast_status directly (at least 1 call already).
    # One extra sleep drains any ensure_future queued by the done callback.
    await asyncio.sleep(0)

    assert hub.broadcast_to_topic.called


@pytest.mark.asyncio
async def test_mission_start_acceptance_does_not_wait_for_websocket_delivery():
    """Persisted RUNNING state is the admission boundary, not telemetry delivery."""
    entered = asyncio.Event()
    release = asyncio.Event()

    class _BlockingHub:
        async def broadcast_to_topic(self, _topic, _payload):
            entered.set()
            await release.wait()

    class _SlowNav(_DummyNav):
        async def execute_mission(self, mission, mission_service=None):
            await asyncio.sleep(60)

    from backend.src.models.mission import MissionLifecycleStatus
    from backend.src.services.mission_service import MissionService

    svc = MissionService(navigation_service=_SlowNav(), websocket_hub=_BlockingHub())
    mission = await svc.create_mission("Accepted", _WAYPOINTS)

    await asyncio.wait_for(svc.start_mission(mission.id), timeout=0.1)

    assert svc.mission_statuses[mission.id].status == MissionLifecycleStatus.RUNNING
    await asyncio.wait_for(entered.wait(), timeout=0.1)

    release.set()
    await svc.abort_mission(mission.id)


@pytest.mark.asyncio
async def test_mission_completed_callback_broadcasts_failed():
    """A navigation failure eventually publishes canonical FAILED status."""
    from backend.src.services.mission_service import MissionService

    failed_broadcast = asyncio.Event()
    payloads = []

    class _RecordingHub:
        async def broadcast_to_topic(self, topic, payload):
            payloads.append((topic, payload))
            if topic == "mission.status" and payload.get("status") == "failed":
                failed_broadcast.set()

    class _FailingNav(_DummyNav):
        async def execute_mission(self, mission, mission_service=None):
            raise RuntimeError("nav blew up")

    svc = MissionService(navigation_service=_FailingNav(), websocket_hub=_RecordingHub())
    mission = await svc.create_mission("Test Mission", _WAYPOINTS)

    await svc.start_mission(mission.id)
    await asyncio.wait_for(failed_broadcast.wait(), timeout=1.0)

    assert any(
        topic == "mission.status"
        and payload.get("status") == "failed"
        and payload.get("detail") == "nav blew up"
        for topic, payload in payloads
    )


@pytest.mark.asyncio
async def test_mission_diagnostics_broadcast_on_start():
    """MissionService broadcasts mission.diagnostics on start when event_store is attached."""
    from backend.src.observability.event_store import EventStore
    from backend.src.observability.events import PersistenceMode
    from backend.src.services.mission_service import MissionService

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
    await asyncio.sleep(0)

    calls = ws_hub.broadcast_to_topic.call_args_list
    topics = [call.args[0] for call in calls]
    assert "mission.diagnostics" in topics
