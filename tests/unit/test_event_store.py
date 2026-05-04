"""Unit tests for EventStore — persistence filter and batch writer."""
import os
import tempfile

import pytest


# WARNING: PersistenceLayer opens a new sqlite3 connection per get_connection() call.
# Using ':memory:' would create a separate empty database for each call, causing migrations
# to run in isolation and data written to one connection to be invisible to others.
# Always pass a real file path (e.g., tempfile) to _make_store.
def _make_store(mode: str = "summary", db_path: str = ":memory:"):
    from backend.src.observability.event_store import EventStore
    from backend.src.observability.events import PersistenceMode
    from backend.src.core.persistence import PersistenceLayer

    persistence = PersistenceLayer(db_path)
    return EventStore(
        persistence=persistence,
        mode=PersistenceMode(mode),
    )


def _pose_event(run_id: str = "run-1", mission_id: str = "m1"):
    from backend.src.observability.events import PoseUpdated
    return PoseUpdated(
        run_id=run_id, mission_id=mission_id,
        lat=37.0, lon=-122.0, heading_deg=90.0,
        pose_quality="gps_float", source="gps",
    )


def _state_changed_event(run_id: str = "run-1", mission_id: str = "m1"):
    from backend.src.observability.events import MissionStateChanged
    return MissionStateChanged(
        run_id=run_id, mission_id=mission_id,
        previous_state="idle", new_state="running", detail="started",
    )


def _blocked_event(run_id: str = "run-1", mission_id: str = "m1"):
    from backend.src.observability.events import SafetyGateBlocked
    return SafetyGateBlocked(
        run_id=run_id, mission_id=mission_id,
        audit_id="a1", reason="estop", interlocks=["emergency_stop_active"],
        source="manual",
    )


def test_summary_mode_suppresses_pose_updated():
    """PoseUpdated is not persisted in summary mode."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        store = _make_store("summary", db_path)
        store.emit(_pose_event())
        rows = store.load_events(run_id="run-1")
        assert len(rows) == 0
    finally:
        os.unlink(db_path)


def test_summary_mode_persists_mission_state_changed():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        store = _make_store("summary", db_path)
        store.emit(_state_changed_event())
        rows = store.load_events(run_id="run-1")
        assert len(rows) == 1
        assert rows[0]["event_type"] == "mission_state_changed"
    finally:
        os.unlink(db_path)


def test_summary_mode_persists_safety_gate_blocked():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        store = _make_store("summary", db_path)
        store.emit(_blocked_event())
        rows = store.load_events(run_id="run-1")
        assert len(rows) == 1
        assert rows[0]["event_type"] == "safety_gate_blocked"
    finally:
        os.unlink(db_path)


def test_full_mode_persists_pose_updated():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        store = _make_store("full", db_path)
        store.emit(_pose_event())
        rows = store.load_events(run_id="run-1")
        assert len(rows) == 1
        assert rows[0]["event_type"] == "pose_updated"
    finally:
        os.unlink(db_path)


def test_full_mode_persists_all_event_types():
    from backend.src.observability.events import (
        HeadingAligned, MotionCommandAcked, MotionCommandIssued,
        WaypointTargetChanged,
    )

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        store = _make_store("full", db_path)
        events = [
            _pose_event(),
            HeadingAligned(run_id="run-1", mission_id="m1",
                           aligned_heading_deg=45.0, sample_count=1,
                           alignment_source="gps_cog_snap"),
            WaypointTargetChanged(run_id="run-1", mission_id="m1",
                                  waypoint_index=0, waypoint_lat=37.0,
                                  waypoint_lon=-122.0, distance_to_target_m=5.0),
            MotionCommandIssued(run_id="run-1", mission_id="m1", audit_id="a1",
                                left=0.5, right=0.5, source="mission", duration_ms=500),
            MotionCommandAcked(run_id="run-1", mission_id="m1", audit_id="a1",
                               watchdog_latency_ms=2.1, hardware_confirmed=True),
            _blocked_event(),
            _state_changed_event(),
        ]
        for evt in events:
            store.emit(evt)
        rows = store.load_events(run_id="run-1")
        assert len(rows) == 7
        types = {r["event_type"] for r in rows}
        assert types == {
            "pose_updated", "heading_aligned", "waypoint_target_changed",
            "motion_command_issued", "motion_command_acked",
            "safety_gate_blocked", "mission_state_changed",
        }
    finally:
        os.unlink(db_path)


def test_load_events_filters_by_run_id():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        store = _make_store("full", db_path)
        store.emit(_state_changed_event(run_id="run-1"))
        store.emit(_state_changed_event(run_id="run-2"))
        rows = store.load_events(run_id="run-1")
        assert len(rows) == 1
        assert rows[0]["run_id"] == "run-1"
    finally:
        os.unlink(db_path)


def test_load_events_filters_by_event_type():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        store = _make_store("full", db_path)
        store.emit(_state_changed_event())
        store.emit(_blocked_event())
        rows = store.load_events(run_id="run-1", event_type="safety_gate_blocked")
        assert len(rows) == 1
        assert rows[0]["event_type"] == "safety_gate_blocked"
    finally:
        os.unlink(db_path)


def test_emit_is_noop_when_persistence_is_none():
    """Emit does not raise if persistence is None (early startup / test convenience)."""
    from backend.src.observability.event_store import EventStore
    from backend.src.observability.events import PersistenceMode

    store = EventStore(persistence=None, mode=PersistenceMode.FULL)
    store.emit(_state_changed_event())  # must not raise
