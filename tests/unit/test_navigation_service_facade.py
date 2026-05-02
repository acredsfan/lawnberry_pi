"""Tests for NavigationService facade delegation to LocalizationService.

These tests verify the wiring contract: when USE_LEGACY_NAVIGATION is not set,
NavigationService must delegate localization calls and mirror state back.

Run with:
    SIM_MODE=1 uv run pytest tests/unit/test_navigation_service_facade.py -v
"""
import pytest

from backend.src.models import GpsReading, ImuReading, SensorData
from backend.src.services.navigation_service import NavigationService


@pytest.fixture(autouse=True)
def unset_legacy_flag(monkeypatch):
    """Ensure legacy mode is disabled for all tests in this module."""
    monkeypatch.delenv("USE_LEGACY_NAVIGATION", raising=False)


@pytest.fixture()
def nav_with_localization():
    """NavigationService with a LocalizationService attached."""
    from backend.src.services.localization_service import LocalizationService
    nav = NavigationService()
    loc = LocalizationService(
        imu_yaw_offset=0.0,
        antenna_forward_m=0.0,
        antenna_right_m=0.0,
        max_fix_age_seconds=2.0,
        max_accuracy_m=5.0,
        alignment_file=None,
    )
    nav.attach_localization(loc)
    return nav, loc


@pytest.mark.asyncio
async def test_update_navigation_state_delegates_position(nav_with_localization):
    nav, loc = nav_with_localization
    await nav.update_navigation_state(
        SensorData(gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=1.0))
    )
    # NavigationService state should mirror LocalizationService state
    assert nav.navigation_state.current_position is not None
    assert nav.navigation_state.current_position.latitude == pytest.approx(37.0)
    assert loc.state.current_position is not None
    assert loc.state.current_position.latitude == pytest.approx(37.0)


@pytest.mark.asyncio
async def test_update_navigation_state_delegates_heading(nav_with_localization):
    nav, loc = nav_with_localization
    await nav.update_navigation_state(
        SensorData(
            gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=1.0),
            imu=ImuReading(yaw=0.0, calibration_status="fully_calibrated"),
        )
    )
    # Both nav and loc should agree on heading
    assert nav.navigation_state.heading == loc.state.heading


@pytest.mark.asyncio
async def test_legacy_mode_does_not_delegate(monkeypatch):
    monkeypatch.setenv("USE_LEGACY_NAVIGATION", "1")
    from backend.src.services.localization_service import LocalizationService

    nav = NavigationService()
    loc = LocalizationService(
        imu_yaw_offset=0.0,
        antenna_forward_m=0.0,
        antenna_right_m=0.0,
        max_fix_age_seconds=2.0,
        max_accuracy_m=5.0,
        alignment_file=None,
    )
    nav.attach_localization(loc)

    await nav.update_navigation_state(
        SensorData(gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=1.0))
    )
    # In legacy mode, LocalizationService.update() should NOT have been called
    # so loc.state remains at its initial stale value
    from backend.src.services.localization_service import PoseQuality
    assert loc.state.quality == PoseQuality.STALE


@pytest.mark.asyncio
async def test_gps_fix_is_fresh_delegates_to_localization(nav_with_localization):
    nav, loc = nav_with_localization
    assert nav._gps_fix_is_fresh() is False
    await nav.update_navigation_state(
        SensorData(gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=1.0))
    )
    assert nav._gps_fix_is_fresh() is True
    assert loc.gps_fix_is_fresh() is True


@pytest.mark.asyncio
async def test_position_is_verified_delegates_to_localization(nav_with_localization):
    nav, loc = nav_with_localization
    assert nav._position_is_verified_for_waypoint() is False
    await nav.update_navigation_state(
        SensorData(gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=1.0))
    )
    # After fresh GPS, both should agree
    assert nav._position_is_verified_for_waypoint() == loc.position_is_verified()
