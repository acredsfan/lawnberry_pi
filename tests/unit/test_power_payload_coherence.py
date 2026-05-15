"""Tests for solar field coherence guard in _merge_power_payload."""
import pytest
from backend.src.services.sensor_manager import PowerSensorInterface


def _merge(ina=None, victron=None, **kwargs):
    return PowerSensorInterface._merge_power_payload(ina, victron, **kwargs)


def test_solar_current_and_ina_power_nulled_when_no_voltage():
    """INA3221 current and power are suppressed when INA bus voltage is 0 (no PV sense wire)."""
    # INA returns current/power but bus voltage < 0.05 V → physically impossible
    ina = {
        "battery_voltage": 13.06,
        "battery_current_amps": -0.2,
        "solar_voltage": 0.0,  # rejected by _pick(min_abs=0.05) → solar_voltage=None
        "solar_current_amps": 1.4,
        "solar_power_w": 1.0,
    }
    result = _merge(ina=ina)
    assert result is not None
    assert result.solar_voltage is None
    assert result.solar_current is None
    assert result.solar_power is None  # INA-derived power suppressed when bus is 0 V


def test_victron_solar_power_passes_through_when_voltage_null():
    """Victron solar_power and yield_today are valid without PV voltage (BLE MPPT)."""
    ina = {
        "battery_voltage": 13.06,
        "battery_current_amps": -0.2,
        "solar_voltage": 0.0,  # rejected
        "solar_current_amps": 1.4,
    }
    victron = {
        "battery_voltage": 13.31,
        "solar_voltage": None,  # SmartSolar BLE has no panel voltage field
        "solar_power_w": 6.0,   # MPPT controller measurement — independently valid
        "solar_yield_today_wh": 40.0,
    }
    result = _merge(ina=ina, victron=victron)
    assert result is not None
    assert result.solar_voltage is None      # no PV voltage from any source
    assert result.solar_current is None      # INA current suppressed (bus is 0 V)
    assert result.solar_power == pytest.approx(6.0)      # Victron power passes through
    assert result.solar_yield_today_wh == pytest.approx(40.0)  # Victron yield passes through


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
