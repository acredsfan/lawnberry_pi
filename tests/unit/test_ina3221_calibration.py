"""Tests for INA3221 voltage calibration offset."""
import pytest
import asyncio
from unittest.mock import patch, MagicMock


def test_calibration_offset_applied():
    """Offset is added to raw bus voltage."""
    from backend.src.drivers.sensors.ina3221_driver import INA3221Driver
    drv = INA3221Driver({"battery_voltage_offset_v": 0.17, "battery_voltage_scale": 1.0})
    assert drv._cfg.battery_voltage_offset_v == 0.17


def test_calibration_scale_applied():
    """Scale is multiplied with raw bus voltage."""
    from backend.src.drivers.sensors.ina3221_driver import INA3221Driver
    drv = INA3221Driver({"battery_voltage_scale": 1.01})
    assert drv._cfg.battery_voltage_scale == 1.01


def test_defaults_no_change():
    """Default offset=0 and scale=1 means no change."""
    from backend.src.drivers.sensors.ina3221_driver import INA3221Driver
    drv = INA3221Driver({})
    assert drv._cfg.battery_voltage_offset_v == 0.0
    assert drv._cfg.battery_voltage_scale == 1.0
    assert drv._cfg.solar_voltage_offset_v == 0.0
    assert drv._cfg.solar_voltage_scale == 1.0


def test_current_offset_applied():
    from backend.src.drivers.sensors.ina3221_driver import INA3221Driver
    drv = INA3221Driver({"battery_current_offset_a": -0.05})
    assert drv._cfg.battery_current_offset_a == -0.05
