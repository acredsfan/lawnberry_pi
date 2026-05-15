"""Tests for solar field coherence guard in _merge_power_payload."""
import pytest
from backend.src.services.sensor_manager import PowerSensorInterface


def _merge(ina=None, victron=None, **kwargs):
    return PowerSensorInterface._merge_power_payload(ina, victron, **kwargs)


def test_solar_current_nulled_when_no_voltage():
    """When solar_voltage is None, solar_current/power/yield must also be None."""
    # INA returns current but voltage < 0.05 threshold → voltage is None
    ina = {
        "battery_voltage": 13.06,
        "battery_current_amps": -0.2,
        "solar_voltage": 0.0,  # will be rejected by _pick(min_abs=0.05)
        "solar_current_amps": 1.4,
        "solar_power_w": 1.0,
    }
    result = _merge(ina=ina)
    assert result is not None
    assert result.solar_voltage is None
    assert result.solar_current is None
    assert result.solar_power is None


def test_solar_all_none_when_both_sources_unavailable():
    ina = {"battery_voltage": 13.06, "battery_current_amps": -0.2}
    result = _merge(ina=ina)
    assert result is not None
    assert result.solar_voltage is None
    assert result.solar_current is None


def test_solar_fields_present_when_voltage_valid():
    ina = {
        "battery_voltage": 13.06,
        "battery_current_amps": -0.2,
        "solar_voltage": 18.5,
        "solar_current_amps": 1.4,
    }
    result = _merge(ina=ina)
    assert result is not None
    assert result.solar_voltage == pytest.approx(18.5)
    assert result.solar_current is not None
