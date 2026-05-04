"""Contract tests: GET /api/v2/missions/{run_id}/summary returns expected shape."""
import os
import uuid

import pytest

os.environ.setdefault("SIM_MODE", "1")


@pytest.fixture()
def client():
    from backend.src.main import app
    from backend.src.core.runtime import get_runtime
    from fastapi.testclient import TestClient

    # Use the real lifespan runtime. Pre-register get_runtime so the contract
    # conftest's autouse mock (which sets event_store=None) does not override us.
    with TestClient(app) as c:
        real_runtime = app.state.runtime
        app.dependency_overrides[get_runtime] = lambda: real_runtime
        try:
            yield c
        finally:
            app.dependency_overrides.pop(get_runtime, None)


def test_summary_unknown_run_returns_404(client):
    resp = client.get("/api/v2/missions/unknown-run-xyz/summary")
    assert resp.status_code == 404


def test_summary_returns_expected_shape(client):
    """Seed events directly and check summary shape and blocked_command_count."""
    from backend.src.main import app
    from backend.src.observability.event_store import EventStore
    from backend.src.observability.events import (
        PersistenceMode, MissionStateChanged, PoseUpdated,
        MotionCommandIssued, SafetyGateBlocked,
    )

    runtime = app.state.runtime
    store = EventStore(persistence=runtime.persistence, mode=PersistenceMode.FULL)

    # Use a unique run_id per test invocation to avoid DB pollution across runs.
    run_id = f"test-run-summary-{uuid.uuid4().hex[:12]}"
    store.emit(MissionStateChanged(run_id=run_id, mission_id="m1",
                                   previous_state="idle", new_state="running", detail=""))
    for i in range(3):
        store.emit(PoseUpdated(run_id=run_id, mission_id="m1",
                               lat=37.0 + i * 0.0001, lon=-122.0,
                               heading_deg=90.0, pose_quality="gps_float", source="gps"))
    store.emit(MotionCommandIssued(run_id=run_id, mission_id="m1",
                                   audit_id="a1", left=0.5, right=0.5,
                                   source="mission", duration_ms=500))
    store.emit(SafetyGateBlocked(run_id=run_id, mission_id="m1", audit_id="a2",
                                 reason="estop", interlocks=["emergency_stop_active"],
                                 source="manual"))

    resp = client.get(f"/api/v2/missions/{run_id}/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_distance_m" in body
    assert "average_pose_quality" in body
    assert "heading_alignment_samples" in body
    assert "blocked_command_count" in body
    assert "waypoint_inefficiency_metrics" in body
    assert body["blocked_command_count"] == 1


def test_summary_full_mode_includes_pose_quality(client):
    """In full mode the summary includes non-None average_pose_quality."""
    from backend.src.main import app
    from backend.src.observability.event_store import EventStore
    from backend.src.observability.events import PersistenceMode, PoseUpdated

    runtime = app.state.runtime
    store = EventStore(persistence=runtime.persistence, mode=PersistenceMode.FULL)

    # Use a unique run_id per test invocation to avoid DB pollution across runs.
    run_id = f"test-run-full-{uuid.uuid4().hex[:12]}"
    store.emit(PoseUpdated(run_id=run_id, mission_id="m2",
                           lat=37.0, lon=-122.0, heading_deg=90.0,
                           pose_quality="gps_float", source="gps",
                           accuracy_m=0.5))
    resp = client.get(f"/api/v2/missions/{run_id}/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["average_pose_quality"] is not None
