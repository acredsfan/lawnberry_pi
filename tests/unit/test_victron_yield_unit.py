"""Tests for Victron yield_today unit handling."""
import pytest
from unittest.mock import MagicMock


def _make_driver(cfg=None):
    from backend.src.drivers.sensors.victron_vedirect import VictronVeDirectDriver
    return VictronVeDirectDriver(cfg or {})


def test_unit_wh_default():
    drv = _make_driver()
    assert drv._yield_today_unit == "wh"


def test_unit_kwh_config():
    drv = _make_driver({"yield_today_unit": "kwh"})
    assert drv._yield_today_unit == "kwh"


def test_solar_panel_max_wh_default():
    drv = _make_driver()
    assert drv._solar_panel_max_wh == 1000.0


def test_solar_panel_max_wh_config():
    drv = _make_driver({"solar_panel_max_wh": 400.0})
    assert drv._solar_panel_max_wh == 400.0


def test_yield_today_wh_passthrough():
    """When unit is wh, value is used as-is."""
    from backend.src.drivers.sensors.victron_vedirect import VictronVeDirectDriver
    frame = {"battery_voltage": 13.1, "yield_today": 250.0}
    result = VictronVeDirectDriver._convert_frame(frame, yield_today_unit="wh", solar_panel_max_wh=1000.0)
    assert result is not None
    assert result["solar_yield_today_wh"] == 250.0


def test_yield_today_kwh_converted():
    """When unit is kwh, value is multiplied by 1000."""
    from backend.src.drivers.sensors.victron_vedirect import VictronVeDirectDriver
    frame = {"battery_voltage": 13.1, "yield_today": 0.25}
    result = VictronVeDirectDriver._convert_frame(frame, yield_today_unit="kwh", solar_panel_max_wh=2000.0)
    assert result is not None
    assert result["solar_yield_today_wh"] == 250.0


def test_yield_today_10_wh_not_multiplied():
    """Critical regression: value of 10.0 Wh is no longer incorrectly multiplied by 1000."""
    from backend.src.drivers.sensors.victron_vedirect import VictronVeDirectDriver
    frame = {"battery_voltage": 13.1, "yield_today": 10.0}
    result = VictronVeDirectDriver._convert_frame(frame, yield_today_unit="wh", solar_panel_max_wh=1000.0)
    assert result is not None
    # With the old heuristic this would have been 10000.0; now it should be 10.0
    assert result["solar_yield_today_wh"] == 10.0
