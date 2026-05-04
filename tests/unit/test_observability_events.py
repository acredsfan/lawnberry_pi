"""Unit tests for structured observability event dataclasses."""
from dataclasses import asdict
from datetime import datetime


def test_pose_updated_fields():
    from backend.src.observability.events import PoseUpdated

    evt = PoseUpdated(
        run_id="run-abc",
        mission_id="m1",
        lat=37.0,
        lon=-122.0,
        heading_deg=90.0,
        pose_quality="gps_float",
        source="gps",
    )
    d = asdict(evt)
    assert d["event_type"] == "pose_updated"
    assert "timestamp" in d
    assert d["pose_quality"] == "gps_float"


def test_heading_aligned_fields():
    from backend.src.observability.events import HeadingAligned

    evt = HeadingAligned(
        run_id="run-abc",
        mission_id="m1",
        aligned_heading_deg=45.0,
        sample_count=1,
        alignment_source="gps_cog_snap",
    )
    assert evt.event_type == "heading_aligned"
    assert evt.sample_count == 1


def test_waypoint_target_changed_fields():
    from backend.src.observability.events import WaypointTargetChanged

    evt = WaypointTargetChanged(
        run_id="run-abc",
        mission_id="m1",
        waypoint_index=3,
        waypoint_lat=37.01,
        waypoint_lon=-122.01,
        distance_to_target_m=12.5,
    )
    assert evt.event_type == "waypoint_target_changed"
    assert evt.waypoint_index == 3


def test_motion_command_issued_fields():
    from backend.src.observability.events import MotionCommandIssued

    evt = MotionCommandIssued(
        run_id="run-abc",
        mission_id="m1",
        audit_id="audit-1",
        left=0.5,
        right=0.5,
        source="mission",
        duration_ms=500,
    )
    assert evt.event_type == "motion_command_issued"
    assert evt.left == 0.5


def test_motion_command_acked_fields():
    from backend.src.observability.events import MotionCommandAcked

    evt = MotionCommandAcked(
        run_id="run-abc",
        mission_id="m1",
        audit_id="audit-1",
        watchdog_latency_ms=3.2,
        hardware_confirmed=True,
    )
    assert evt.event_type == "motion_command_acked"
    assert evt.hardware_confirmed is True


def test_safety_gate_blocked_fields():
    from backend.src.observability.events import SafetyGateBlocked

    evt = SafetyGateBlocked(
        run_id="run-abc",
        mission_id="m1",
        audit_id="audit-2",
        reason="emergency_stop_active",
        interlocks=["emergency_stop_active"],
        source="manual",
    )
    assert evt.event_type == "safety_gate_blocked"
    assert "emergency_stop_active" in evt.interlocks


def test_mission_state_changed_fields():
    from backend.src.observability.events import MissionStateChanged

    evt = MissionStateChanged(
        run_id="run-abc",
        mission_id="m1",
        previous_state="idle",
        new_state="running",
        detail="Mission started",
    )
    assert evt.event_type == "mission_state_changed"
    assert evt.new_state == "running"


def test_all_events_have_timestamp():
    """Timestamps are auto-populated and timezone-aware."""
    from backend.src.observability.events import (
        HeadingAligned,
        MissionStateChanged,
        MotionCommandAcked,
        MotionCommandIssued,
        PoseUpdated,
        SafetyGateBlocked,
        WaypointTargetChanged,
    )

    events = [
        PoseUpdated(run_id="r", mission_id="m", lat=0.0, lon=0.0,
                    heading_deg=0.0, pose_quality="gps_float", source="gps"),
        HeadingAligned(run_id="r", mission_id="m", aligned_heading_deg=0.0,
                       sample_count=1, alignment_source="gps_cog_snap"),
        WaypointTargetChanged(run_id="r", mission_id="m", waypoint_index=0,
                              waypoint_lat=0.0, waypoint_lon=0.0, distance_to_target_m=0.0),
        MotionCommandIssued(run_id="r", mission_id="m", audit_id="a",
                            left=0.0, right=0.0, source="mission", duration_ms=100),
        MotionCommandAcked(run_id="r", mission_id="m", audit_id="a",
                           watchdog_latency_ms=1.0, hardware_confirmed=True),
        SafetyGateBlocked(run_id="r", mission_id="m", audit_id="a",
                          reason="estop", interlocks=[], source="manual"),
        MissionStateChanged(run_id="r", mission_id="m", previous_state="idle",
                            new_state="running", detail=""),
    ]
    for evt in events:
        assert isinstance(evt.timestamp, datetime)
        assert evt.timestamp.tzinfo is not None
