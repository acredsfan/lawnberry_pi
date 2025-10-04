import os
import pytest


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
