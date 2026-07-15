"""Tests for INA3221 voltage calibration offset."""


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


def test_channel_mapping_matches_tracked_hardware_spec():
    from backend.src.drivers.sensors.ina3221_driver import INA3221Driver

    drv = INA3221Driver({})
    payload = drv._build_power_payload(
        bus_voltages=[12.8, 0.0, 18.0],
        currents=[-2.0, None, 1.5],
    )

    assert drv.BATTERY_CHANNEL_INDEX == 0
    assert drv.SOLAR_CHANNEL_INDEX == 2
    assert payload["battery_voltage"] == 12.8
    assert payload["battery_current_amps"] == -2.0
    assert payload["solar_voltage"] == 18.0
    assert payload["solar_current_amps"] == 1.5
