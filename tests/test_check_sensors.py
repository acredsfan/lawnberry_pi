import asyncio
import pytest

from src.hardware import create_hardware_interface


@pytest.mark.asyncio
async def test_check_sensors_smoke():
    """Initialize in-memory HardwareInterface and assert expected sensors present in readings"""
    hw = create_hardware_interface({})
    success = await hw.initialize()
    assert success, "HardwareInterface failed to initialize in simulation"
    data = await hw.get_all_sensor_data()
    # Ensure keys exist in returned mapping
    assert 'tof_left' in data
    assert 'tof_right' in data
    assert 'power_monitor' in data
    await hw.cleanup()
