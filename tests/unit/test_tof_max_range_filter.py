"""Unit tests for VL53L0X ToF 8190 mm out-of-range sentinel filtering.

Covers:
- TOF_SENSOR_MAX_VALID_MM constant equals 8190
- Driver returns None (not 8190) for exact sentinel readings
- Driver returns None for any value >= 8190
- Driver does NOT cache the sentinel as _last_distance_mm
- Driver increments fail_count on sentinel readings (not resets it)
- ObstacleDetector treats None distance as "unknown" (no false positive)
- ObstacleDetector still detects real obstacles below the safety threshold
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.src.drivers.sensors.vl53l0x_driver import TOF_SENSOR_MAX_VALID_MM, VL53L0XDriver
from backend.src.models.sensor_data import SensorData, TofReading
from backend.src.services.navigation_service import ObstacleDetector


# ---------------------------------------------------------------------------
# Constant
# ---------------------------------------------------------------------------

class TestTofSentinelConstant:
    def test_sentinel_value_is_8190(self):
        assert TOF_SENSOR_MAX_VALID_MM == 8190

    def test_sentinel_exported_in_all(self):
        from backend.src.drivers.sensors import vl53l0x_driver
        assert "TOF_SENSOR_MAX_VALID_MM" in vl53l0x_driver.__all__


# ---------------------------------------------------------------------------
# VL53L0XDriver — pololu/alt backend (get_distance)
# ---------------------------------------------------------------------------

def _make_pololu_driver(return_value: int) -> VL53L0XDriver:
    """Build a non-sim VL53L0XDriver with a mock pololu-style hardware backend."""
    drv = VL53L0XDriver("left")
    drv.initialized = True
    drv._driver_backend = "pololu"
    mock_hw = MagicMock()
    mock_hw.get_distance.return_value = return_value
    drv._driver = mock_hw
    return drv


@pytest.mark.asyncio
async def test_exact_sentinel_8190_returns_none():
    """read_distance_mm() must return None for the exact 8190 sentinel."""
    drv = _make_pololu_driver(8190)
    with patch.dict("os.environ", {"SIM_MODE": "0"}):
        result = await drv.read_distance_mm()
    assert result is None


@pytest.mark.asyncio
async def test_value_above_sentinel_returns_none():
    """Any value >= 8190 is treated as a sentinel and returns None."""
    drv = _make_pololu_driver(9999)
    with patch.dict("os.environ", {"SIM_MODE": "0"}):
        result = await drv.read_distance_mm()
    assert result is None


@pytest.mark.asyncio
async def test_valid_distance_below_sentinel_returned():
    """Normal in-range distance (< 8190) is returned as-is."""
    drv = _make_pololu_driver(450)
    with patch.dict("os.environ", {"SIM_MODE": "0"}):
        result = await drv.read_distance_mm()
    assert result == 450


@pytest.mark.asyncio
async def test_sentinel_does_not_overwrite_last_cached_distance():
    """An 8190 reading must NOT replace the previously cached valid distance."""
    drv = _make_pololu_driver(8190)
    drv._last_distance_mm = 500  # prior valid reading
    with patch.dict("os.environ", {"SIM_MODE": "0"}):
        await drv.read_distance_mm()
    assert drv._last_distance_mm == 500


@pytest.mark.asyncio
async def test_sentinel_increments_fail_count():
    """8190 is a measurement failure — fail_count must increase, not reset."""
    drv = _make_pololu_driver(8190)
    drv._fail_count = 0
    with patch.dict("os.environ", {"SIM_MODE": "0"}):
        await drv.read_distance_mm()
    assert drv._fail_count == 1


@pytest.mark.asyncio
async def test_valid_read_resets_fail_count():
    """A successful valid reading resets fail_count to zero."""
    drv = _make_pololu_driver(300)
    drv._fail_count = 5
    with patch.dict("os.environ", {"SIM_MODE": "0"}):
        await drv.read_distance_mm()
    assert drv._fail_count == 0


# ---------------------------------------------------------------------------
# VL53L0XDriver — Adafruit backend (.range property)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adafruit_backend_sentinel_returns_none():
    """Adafruit backend reads via getattr(.range); 8190 must also return None."""
    drv = VL53L0XDriver("right")
    drv.initialized = True
    drv._driver_backend = "adafruit"
    mock_hw = MagicMock()
    mock_hw.range = 8190  # getattr(mock_hw, "range") → 8190
    drv._driver = mock_hw
    with patch.dict("os.environ", {"SIM_MODE": "0"}):
        result = await drv.read_distance_mm()
    assert result is None


@pytest.mark.asyncio
async def test_adafruit_backend_valid_distance_returned():
    """Adafruit backend with a valid distance returns that distance."""
    drv = VL53L0XDriver("right")
    drv.initialized = True
    drv._driver_backend = "adafruit"
    mock_hw = MagicMock()
    mock_hw.range = 750
    drv._driver = mock_hw
    with patch.dict("os.environ", {"SIM_MODE": "0"}):
        result = await drv.read_distance_mm()
    assert result == 750


# ---------------------------------------------------------------------------
# ObstacleDetector — None / sentinel distance handling
# ---------------------------------------------------------------------------

def _sensor_data(left: float | None, right: float | None) -> SensorData:
    return SensorData(
        tof_left=TofReading(distance=left, sensor_side="left"),
        tof_right=TofReading(distance=right, sensor_side="right"),
    )


def test_both_none_tof_no_obstacle():
    """Both ToF readings unavailable (None) → no obstacle (unknown, not blocked)."""
    detector = ObstacleDetector(safety_distance=0.2)
    obstacles = detector.update_obstacles_from_sensors(_sensor_data(None, None))
    assert obstacles == []


def test_left_none_right_clear_no_obstacle():
    """Left sensor unavailable, right is clear → no obstacle reported."""
    detector = ObstacleDetector(safety_distance=0.2)
    obstacles = detector.update_obstacles_from_sensors(_sensor_data(None, 1500.0))
    assert obstacles == []


def test_right_none_left_obstacle_detects_left():
    """Left shows real obstacle, right is unavailable → only left obstacle."""
    detector = ObstacleDetector(safety_distance=0.2)
    obstacles = detector.update_obstacles_from_sensors(_sensor_data(150.0, None))
    assert len(obstacles) == 1
    assert "tof_left" in obstacles[0].id


def test_both_below_threshold_detects_two_obstacles():
    """Both sensors within threshold → two obstacles detected."""
    detector = ObstacleDetector(safety_distance=0.2)
    obstacles = detector.update_obstacles_from_sensors(_sensor_data(100.0, 180.0))
    assert len(obstacles) == 2


def test_large_valid_distance_not_obstacle():
    """A large but valid distance (1500 mm) well above threshold is not an obstacle."""
    detector = ObstacleDetector(safety_distance=0.2)  # threshold = 200 mm
    obstacles = detector.update_obstacles_from_sensors(_sensor_data(1500.0, 2000.0))
    assert obstacles == []


def test_exact_threshold_boundary_is_obstacle():
    """Distance equal to threshold (200 mm) is detected as obstacle (<=, inclusive)."""
    detector = ObstacleDetector(safety_distance=0.2)  # threshold = 200 mm
    obstacles = detector.update_obstacles_from_sensors(_sensor_data(200.0, 1000.0))
    assert len(obstacles) == 1
