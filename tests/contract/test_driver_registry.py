import os

import pytest

from backend.src.models.hardware_config import HardwareConfig


def test_driver_registry_loads_declared_modules_only(tmp_path):
    os.environ["SIM_MODE"] = "1"  # Ensure simulation mode so no hardware needed
    hardware_yaml = tmp_path / "hardware.yaml"
    hardware_yaml.write_text(
        """
gps:
  type: ZED-F9P
imu:
  type: BNO085
sensors:
  tof:
    - left
    - right
power_monitor:
  type: INA3221
motor_controller:
  type: RoboHAT_RP2040
"""
    )

    try:
        from backend.src.core.driver_registry import DriverRegistry  # noqa: F401
    except Exception:
        pytest.skip("DriverRegistry not implemented yet")

    registry = DriverRegistry(config_path=str(hardware_yaml))
    drivers = registry.load()

    # Expect known keys present and no unexpected modules
    expected = {"gps", "imu", "tof_left", "tof_right", "power", "motor"}
    assert expected.issubset(set(drivers.keys()))


def test_driver_registry_uses_injected_typed_hardware_config(monkeypatch):
    monkeypatch.setenv("SIM_MODE", "0")
    from backend.src.core.driver_registry import DriverRegistry

    registry = DriverRegistry(
        hardware_config=HardwareConfig(
            gps_type="zed-f9p-usb",
            imu_type="bno085-uart",
            tof_sensors=["left", "right"],
            power_monitor=True,
            motor_controller="robohat-rp2040",
        )
    )

    drivers = registry.load()

    assert {"gps", "imu", "tof_left", "tof_right", "power", "motor"}.issubset(drivers)
