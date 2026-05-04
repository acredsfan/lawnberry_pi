"""Tests: MissionService emits MissionStateChanged and WaypointTargetChanged events."""
import asyncio
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.src.models import NavigationMode
from backend.src.models.mission import MissionWaypoint


class _DummyNav:
    """Minimal navigation stub for MissionService unit tests."""
    def __init__(self):
        self.navigation_state = SimpleNamespace(
            navigation_mode=NavigationMode.IDLE,
            planned_path=[],
            current_waypoint_index=0,
            safety_boundaries=[],
        )

    async def execute_mission(self, mission, mission_service=None):
        return None

    async def stop_navigation(self):
        self.navigation_state.navigation_mode = NavigationMode.IDLE
        return True

    async def set_speed(self, left: float, right: float):
        pass

    async def emergency_stop(self):
        return True

    def set_event_store(self, store, run_id, mission_id):
        pass


def _make_service_with_store():
    from backend.src.services.mission_service import MissionService
    from backend.src.observability.event_store import EventStore
    from backend.src.observability.events import PersistenceMode

    emitted = []
    store = EventStore(persistence=None, mode=PersistenceMode.FULL)
    store.emit = lambda evt: emitted.append(evt)

    ws_hub = MagicMock()
    ws_hub.broadcast_to_topic = AsyncMock()

    svc = MissionService(
        navigation_service=_DummyNav(),
        websocket_hub=ws_hub,
    )
    svc.set_event_store(store)
    return svc, emitted


@pytest.mark.asyncio
async def test_start_mission_emits_mission_state_changed():
    svc, emitted = _make_service_with_store()
    mission = await svc.create_mission("Test", [MissionWaypoint(lat=37.0, lon=-122.0)])
    await svc.start_mission(mission.id)
    state_events = [e for e in emitted if e.event_type == "mission_state_changed"]
    assert any(e.new_state == "running" for e in state_events)


@pytest.mark.asyncio
async def test_pause_mission_emits_mission_state_changed():
    svc, emitted = _make_service_with_store()
    mission = await svc.create_mission("Test2", [MissionWaypoint(lat=37.0, lon=-122.0)])
    await svc.start_mission(mission.id)
    await svc.pause_mission(mission.id)
    state_events = [e for e in emitted if e.event_type == "mission_state_changed"]
    assert any(e.new_state == "paused" for e in state_events)


@pytest.mark.asyncio
async def test_abort_mission_emits_mission_state_changed():
    svc, emitted = _make_service_with_store()
    mission = await svc.create_mission("Test3", [MissionWaypoint(lat=37.0, lon=-122.0)])
    await svc.start_mission(mission.id)
    await svc.abort_mission(mission.id)
    state_events = [e for e in emitted if e.event_type == "mission_state_changed"]
    assert any(e.new_state == "aborted" for e in state_events)


@pytest.mark.asyncio
async def test_update_waypoint_progress_emits_waypoint_target_changed():
    svc, emitted = _make_service_with_store()
    mission = await svc.create_mission(
        "Test4",
        [MissionWaypoint(lat=37.0, lon=-122.0), MissionWaypoint(lat=37.01, lon=-122.01)],
    )
    await svc.start_mission(mission.id)
    await svc.update_waypoint_progress(mission.id, 1)
    wp_events = [e for e in emitted if e.event_type == "waypoint_target_changed"]
    assert len(wp_events) >= 1
    assert wp_events[-1].waypoint_index == 1
