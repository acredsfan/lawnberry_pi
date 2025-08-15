import pytest
from datetime import datetime

from src.hardware.sensor_service import SensorService
from src.hardware.data_structures import SensorReading


@pytest.mark.mock
@pytest.mark.asyncio
async def test_formatting_maps_power_and_tof():
    svc = SensorService()
    # Fake raw data: emulate plugins with names and SensorReading payloads
    raw = {
        'power_monitor': SensorReading(timestamp=datetime.utcnow(), sensor_id='power_monitor', value={'voltage': 12.3, 'current': 1.5}, unit='mixed'),
        'environmental_bme280': SensorReading(timestamp=datetime.utcnow(), sensor_id='environmental_bme280', value={'temperature': 25.1, 'humidity': 50.2, 'pressure': 1012.3}, unit='mixed'),
        'tof_left': SensorReading(timestamp=datetime.utcnow(), sensor_id='tof_left', value=345, unit='mm'),
        'tof_right': SensorReading(timestamp=datetime.utcnow(), sensor_id='tof_right', value=678, unit='mm'),
    }
    out = await svc.format_sensor_data(raw)  # type: ignore[arg-type]
    assert out['power']['battery_voltage'] == pytest.approx(12.3)
    assert out['power']['battery_current'] == pytest.approx(1.5)
    assert out['tof']['left_distance'] == 345
    assert out['tof']['right_distance'] == 678
