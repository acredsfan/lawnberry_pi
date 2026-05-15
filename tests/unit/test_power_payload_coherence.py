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


def test_victron_solar_power_and_voltage_derived_from_ina_current():
    """Victron solar_power + INA current derive panel voltage; yield passes through."""
    ina = {
        "battery_voltage": 13.06,
        "battery_current_amps": -0.2,
        "solar_voltage": 0.0,  # rejected — low-side wiring, bus always 0 V
        "solar_current_amps": 1.4,
    }
    victron = {
        "battery_voltage": 13.31,
        "solar_voltage": None,  # SmartSolar BLE has no panel voltage field
        "solar_power_w": 6.0,   # MPPT controller measurement
        "solar_yield_today_wh": 40.0,
    }
    result = _merge(ina=ina, victron=victron)
    assert result is not None
    # solar_voltage derived from Victron power / INA current: 6.0 / 1.4 ≈ 4.286 V
    assert result.solar_voltage == pytest.approx(6.0 / 1.4, rel=1e-3)
    assert result.solar_current == pytest.approx(1.4)   # INA current valid (voltage now derived)
    assert result.solar_power == pytest.approx(6.0)
    assert result.solar_yield_today_wh == pytest.approx(40.0)


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
