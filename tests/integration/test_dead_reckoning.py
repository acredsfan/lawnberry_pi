import pytest
from datetime import datetime, timezone

from backend.src.services.navigation_service import NavigationService
from backend.src.models import Position, SensorData, ImuReading


@pytest.mark.asyncio
async def test_dead_reckoning_activates_without_gps():
    nav = NavigationService()
    # Seed heading
    nav.navigation_state.heading = 90.0  # east

    sd = SensorData(imu=ImuReading(yaw=90.0))
    state = await nav.update_navigation_state(sd)
    assert state.dead_reckoning_active is True
    assert state.current_position is not None


@pytest.mark.asyncio
async def test_dead_reckoning_resets_with_gps_fix():
    nav = NavigationService()
    # First, run without GPS
    nav.navigation_state.heading = 0.0
    await nav.update_navigation_state(SensorData(imu=ImuReading(yaw=0.0)))
    assert nav.navigation_state.dead_reckoning_active is True

    # Provide a GPS fix; dead reckoning should disable
    gps_pos = Position(latitude=37.0, longitude=-122.0)
    sd = SensorData()
    sd.gps = type("GpsMock", (), {"latitude": gps_pos.latitude, "longitude": gps_pos.longitude, "altitude": None, "accuracy": 2.0})()
    state = await nav.update_navigation_state(sd)
    assert state.dead_reckoning_active is False
    assert state.current_position is not None
    assert abs(state.current_position.latitude - 37.0) < 1e-6


@pytest.mark.asyncio
async def test_dead_reckoning_drift_bound_progression():
    nav = NavigationService()
    nav.navigation_state.heading = 45.0
    # Run several updates without GPS; drift estimate should remain bounded
    drifts = []
    for _ in range(10):
        state = await nav.update_navigation_state(SensorData(imu=ImuReading(yaw=45.0)))
        drifts.append(state.dead_reckoning_drift)
    # non-decreasing, bounded by logic in service
    assert all(drifts[i] <= drifts[i+1] for i in range(len(drifts)-1))
    assert drifts[-1] <= 1.0  # sanity bound for test given placeholder calc
