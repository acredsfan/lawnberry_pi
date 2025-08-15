#!/usr/bin/env python3
import sys
from datetime import datetime

from src.hardware.sensor_service import SensorService
from src.hardware.data_structures import SensorReading


def main() -> int:
    svc = SensorService()
    raw = {
        'power_monitor': SensorReading(timestamp=datetime.utcnow(), sensor_id='power_monitor', value={'voltage': 12.3, 'current': 1.5}, unit='mixed'),
        'environmental_bme280': SensorReading(timestamp=datetime.utcnow(), sensor_id='environmental_bme280', value={'temperature': 25.1, 'humidity': 50.2, 'pressure': 1012.3}, unit='mixed'),
        'tof_left': SensorReading(timestamp=datetime.utcnow(), sensor_id='tof_left', value=345, unit='mm'),
        'tof_right': SensorReading(timestamp=datetime.utcnow(), sensor_id='tof_right', value=678, unit='mm'),
    }
    out = svc.__class__.__dict__['format_sensor_data']
    # call bound method
    formatted = None
    try:
        # bind coroutine
        import asyncio
        formatted = asyncio.get_event_loop().run_until_complete(svc.format_sensor_data(raw))
    except RuntimeError:
        # no running loop
        formatted = asyncio.run(svc.format_sensor_data(raw))

    assert abs(formatted['power']['battery_voltage'] - 12.3) < 1e-6
    assert abs(formatted['power']['battery_current'] - 1.5) < 1e-6
    assert formatted['tof']['left_distance'] == 345
    assert formatted['tof']['right_distance'] == 678
    print("OK: sensor_service formatting and aliases validated")
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"FAIL: {e}")
        raise
