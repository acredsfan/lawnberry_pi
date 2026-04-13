import asyncio
from types import SimpleNamespace

import pytest

from backend.src.models import GpsMode, GpsReading, SensorStatus
from backend.src.services.sensor_manager import SensorManager


@pytest.mark.asyncio
async def test_read_all_sensors_returns_partial_data_when_one_sensor_times_out():
    manager = SensorManager(gps_mode=GpsMode.F9P_USB)
    manager.initialized = True
    manager.validation_enabled = False
    manager.SENSOR_READ_TIMEOUT_SECONDS = 0.05

    async def slow_power():
        await asyncio.sleep(0.2)
        return None

    async def read_gps():
        return GpsReading(latitude=39.0, longitude=-84.0, accuracy=0.2, mode=GpsMode.F9P_USB)

    async def read_imu():
        return None

    async def read_tof():
        return (None, None)

    async def read_environmental():
        return None

    manager.gps = SimpleNamespace(status=SensorStatus.ONLINE, read_gps=read_gps)
    manager.imu = SimpleNamespace(status=SensorStatus.ONLINE, read_imu=read_imu)
    manager.tof = SimpleNamespace(status=SensorStatus.ONLINE, read_tof_sensors=read_tof)
    manager.environmental = SimpleNamespace(status=SensorStatus.ONLINE, read_environmental=read_environmental)
    manager.power = SimpleNamespace(status=SensorStatus.ONLINE, read_power=slow_power)

    sensor_data = await manager.read_all_sensors()

    assert sensor_data.gps is not None
    assert sensor_data.gps.latitude == 39.0
    assert sensor_data.power is None
