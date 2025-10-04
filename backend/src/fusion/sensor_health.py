"""Sensor health monitoring scaffolding (T050).

Tracks basic quality metrics for sensors. This scaffold returns static quality
ratings suitable for diagnostics and can be expanded alongside the real EKF.
"""
from __future__ import annotations

from typing import Dict


class SensorHealthMonitor:
    def __init__(self) -> None:
        self._qualities: Dict[str, float] = {
            "gps": 0.8,
            "imu": 0.9,
            "odometry": 0.7,
        }

    def set_quality(self, sensor: str, quality_0_to_1: float) -> None:
        self._qualities[sensor] = max(0.0, min(1.0, quality_0_to_1))

    def get_snapshot(self) -> Dict[str, float]:
        return dict(self._qualities)


__all__ = ["SensorHealthMonitor"]
