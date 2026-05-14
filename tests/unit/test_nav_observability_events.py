"""Tests: NavigationService emits PoseUpdated and HeadingAligned events."""
import pytest
from unittest.mock import MagicMock


def _make_store():
    from backend.src.observability.event_store import EventStore
    from backend.src.observability.events import PersistenceMode
    store = EventStore(persistence=None, mode=PersistenceMode.FULL)
    return store


@pytest.mark.asyncio
async def test_pose_updated_event_emitted_after_gps_fix():
    """A PoseUpdated event is emitted after update_navigation_state processes a GPS fix."""
    from backend.src.observability.events import PoseUpdated
    from backend.src.services.navigation_service import NavigationService
    from backend.src.models import GpsReading, SensorData

    emitted = []
    store = _make_store()
    original_emit = store.emit
    store.emit = lambda evt: emitted.append(evt) or original_emit(evt)  # spy

    nav = NavigationService()
    nav.set_event_store(store, run_id="run-test", mission_id="m-test")

    sensor_data = SensorData(gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=0.5))
    await nav.update_navigation_state(sensor_data)

    pose_events = [e for e in emitted if e.event_type == "pose_updated"]
    assert len(pose_events) >= 1
    assert pose_events[0].run_id == "run-test"
    assert pose_events[0].mission_id == "m-test"
    assert pose_events[0].lat == pytest.approx(37.0, abs=0.001)


@pytest.mark.asyncio
async def test_heading_aligned_event_emitted_after_gps_cog_snap():
    """A HeadingAligned event is emitted when heading bootstrap completes."""
    from backend.src.observability.events import HeadingAligned
    from backend.src.services.navigation_service import NavigationService
    from backend.src.models import GpsReading, ImuReading, SensorData

    emitted = []
    store = _make_store()
    store.emit = lambda evt: emitted.append(evt)

    nav = NavigationService()
    nav.set_event_store(store, run_id="run-hdg", mission_id="m-hdg")
    nav._require_gps_heading_alignment = True
    nav._heading_alignment_sample_count = 0
    nav._bootstrap_start_time = 1.0

    # Simulate a GPS COG snap by providing moving GPS + IMU.
    # going_straight requires >= 5 consecutive entries in _gps_cog_history.
    for _ in range(5):
        sensor_data = SensorData(
            gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=0.5,
                           speed=0.6, heading=90.0),
            imu=ImuReading(yaw=5.0, calibration_status="calibrated"),
        )
        await nav.update_navigation_state(sensor_data)

    heading_events = [e for e in emitted if e.event_type == "heading_aligned"]
    assert len(heading_events) >= 1
    assert heading_events[0].alignment_source == "gps_cog_snap"
    assert heading_events[0].sample_count == 1
