"""Tests for TelemetryService power always-emit and power_status contract."""

import pytest
from unittest.mock import MagicMock, patch

from backend.src.models.sensor_data import SensorData, PowerReading
from backend.src.services.telemetry_service import TelemetryService

_FLAT_POWER_KEYS = {
    "battery_voltage",
    "battery_current",
    "battery_power",
    "solar_voltage",
    "solar_current",
    "solar_power",
    "solar_yield_today_wh",
    "battery_consumed_today_wh",
    "load_current",
    "timestamp",
}


def _make_service():
    """Return a TelemetryService with a minimal mocked AppState."""
    svc = TelemetryService.__new__(TelemetryService)
    svc._last_position = {}
    svc._heading_source = None

    mock_app_state = MagicMock()
    mock_app_state.safety_state = {"emergency_stop_active": False}
    mock_app_state.hardware_config = None
    svc.app_state = mock_app_state
    return svc


def _format(svc, power=None):
    data = SensorData(power=power) if power is not None else SensorData()
    with (
        patch.object(svc, "_get_navigation_heading", return_value=None),
        patch.object(svc, "_apply_position_offsets", return_value=({}, None, None)),
    ):
        return svc._format_telemetry(data, sim_mode=False)


def test_power_key_always_present_when_data_missing():
    """power block must be in the telemetry dict even when SensorData.power is None."""
    svc = _make_service()
    result = _format(svc, power=None)

    assert "power" in result, "Expected 'power' key in telemetry when data.power is None"
    assert result.get("power_status") == "unavailable"


def test_power_keys_are_flat_when_data_missing():
    """The empty fallback uses the same flat schema as the live path."""
    svc = _make_service()
    result = _format(svc, power=None)

    assert _FLAT_POWER_KEYS.issubset(result["power"].keys()), (
        f"Missing keys: {_FLAT_POWER_KEYS - set(result['power'].keys())}"
    )
    # All value fields should be None
    for key in _FLAT_POWER_KEYS - {"timestamp"}:
        assert result["power"][key] is None, f"Expected None for {key}, got {result['power'][key]}"


def test_power_status_ok_when_reading_present():
    """power_status is 'ok' when a real PowerReading is supplied."""
    svc = _make_service()
    reading = PowerReading(battery_voltage=12.8, battery_current=1.5)
    result = _format(svc, power=reading)

    assert result.get("power_status") == "ok"
    assert result["power"]["battery_voltage"] == 12.8
    assert result["power"]["battery_current"] == 1.5


def test_power_values_populated_from_reading():
    """_format_power_data transfers all fields correctly."""
    svc = _make_service()
    reading = PowerReading(
        battery_voltage=13.0,
        battery_current=2.1,
        battery_power=27.3,
        solar_voltage=18.5,
        solar_current=1.4,
        solar_power=25.9,
        solar_yield_today_wh=120.0,
        battery_consumed_today_wh=40.0,
        load_current=0.9,
    )
    result = _format(svc, power=reading)

    p = result["power"]
    assert p["battery_voltage"] == 13.0
    assert p["solar_voltage"] == 18.5
    assert p["solar_yield_today_wh"] == 120.0
    assert p["battery_consumed_today_wh"] == 40.0
    assert p["load_current"] == 0.9


def test_empty_power_payload_has_no_nested_objects():
    """The empty fallback must NOT contain nested 'battery' or 'solar' sub-dicts."""
    svc = _make_service()
    result = _format(svc, power=None)

    power = result["power"]
    assert "battery" not in power, "Nested 'battery' sub-object found in empty payload"
    assert "solar" not in power, "Nested 'solar' sub-object found in empty payload"
