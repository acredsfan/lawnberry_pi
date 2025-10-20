import math

from backend.src.services.sensor_manager import PowerSensorInterface
from backend.src.drivers.sensors.victron_vedirect import VictronVeDirectDriver


def test_merge_prefers_victron_battery_current_when_requested():
    ina_payload = {"battery_current": 3.0, "battery_voltage": 12.8}
    victron_payload = {"battery_current_amps": 1.2, "battery_voltage": 12.6}

    reading = PowerSensorInterface._merge_power_payload(
        ina_payload,
        victron_payload,
        prefer_battery=True,
    )

    assert reading is not None
    assert math.isclose(reading.battery_current, 1.2, rel_tol=1e-6)
    assert math.isclose(reading.battery_voltage, 12.6, rel_tol=1e-6)


def test_merge_prefers_ina_battery_current_by_default():
    ina_payload = {"battery_current": 2.5, "battery_voltage": 12.7}
    victron_payload = {"battery_current_amps": 1.1, "battery_voltage": 12.6}

    reading = PowerSensorInterface._merge_power_payload(ina_payload, victron_payload)

    assert reading is not None
    assert math.isclose(reading.battery_current, 2.5, rel_tol=1e-6)


def test_merge_prefers_victron_load_when_enabled():
    ina_payload = {"load_current_amps": 0.2}
    victron_payload = {"load_current_amps": 0.6}

    default_reading = PowerSensorInterface._merge_power_payload(ina_payload, victron_payload)
    preferred_reading = PowerSensorInterface._merge_power_payload(
        ina_payload,
        victron_payload,
        prefer_load=True,
    )

    assert default_reading is not None
    assert math.isclose(default_reading.load_current, 0.2, rel_tol=1e-6)
    assert preferred_reading is not None
    assert math.isclose(preferred_reading.load_current, 0.6, rel_tol=1e-6)


def test_convert_frame_handles_ble_payload():
    frame = {
        "name": "SmartSolar",
        "address": "EC:1A:A8:DD:99:C2",
        "payload": {
            "battery_voltage": 13.5,
            "battery_charging_current": 0.7,
            "solar_power": 15.0,
            "external_device_load": 0.4,
            "charge_state": "float",
        },
    }

    converted = VictronVeDirectDriver._convert_frame(frame)

    assert converted is not None
    assert math.isclose(converted["battery_voltage"], 13.5, rel_tol=1e-6)
    assert math.isclose(converted["battery_current_amps"], 0.7, rel_tol=1e-6)
    assert math.isclose(converted["solar_power_w"], 15.0, rel_tol=1e-6)
    assert math.isclose(converted["load_current_amps"], 0.4, rel_tol=1e-6)
    assert converted.get("meta", {}).get("charge_state") == "float"
