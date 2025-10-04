from __future__ import annotations

from backend.src.cli.sensor_commands import _format_table

def test_format_table_basic():
    snapshot = {
        "tof_left": {"value": 0.25, "unit": "m", "status": "ok"},
        "imu_roll": {"value": 5.0, "unit": "deg", "status": "ok"},
    }
    out = _format_table(snapshot)
    assert "SENSOR" in out and "VALUE" in out
    assert "tof_left" in out and "imu_roll" in out
