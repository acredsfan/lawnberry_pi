"""BNO085 IMU driver (T046) - simulation stub.

Provides minimal async lifecycle and a `read_orientation` method returning
roll/pitch/yaw plus calibration data. SIM_MODE yields stable baseline with
occasional tilt excursions (>30°) to support contract test scaffolding.

Safety Requirement (FR-022): Tilt >30° must trigger blade stop within 200ms.
This stub only supplies data; enforcement occurs in safety triggers (T051).
"""
from __future__ import annotations

import math
import os
import random
import time
from typing import Any

from ...core.simulation import is_simulation_mode
from ..base import HardwareDriver


class BNO085Driver(HardwareDriver):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config=config)
        self._last_orientation: dict[str, float] | None = None
        self._last_read_ts: float | None = None
        self._cycle: int = 0

    async def initialize(self) -> None:  # noqa: D401
        self.initialized = True

    async def start(self) -> None:  # noqa: D401
        self.running = True

    async def stop(self) -> None:  # noqa: D401
        self.running = False

    async def health_check(self) -> dict[str, Any]:  # noqa: D401
        return {
            "sensor": "bno085_imu",
            "initialized": self.initialized,
            "running": self.running,
            "last_orientation": self._last_orientation,
            "last_read_age_s": (time.time() - self._last_read_ts) if self._last_read_ts else None,
            "simulation": is_simulation_mode(),
        }

    async def read_orientation(self) -> dict[str, float] | None:
        if not self.initialized:
            return None
        if is_simulation_mode() or os.environ.get("SIM_MODE") == "1":
            # Produce a smooth yaw change and periodic tilt spike
            yaw = (self._cycle * 3) % 360
            roll = math.sin(self._cycle / 20) * 5
            pitch = math.cos(self._cycle / 25) * 3
            if self._cycle % 50 == 10:
                roll = 35.0 + random.uniform(0, 2)  # simulate unsafe tilt
            calibration_state = "calibrating" if self._cycle < 80 else "fully_calibrated"
            self._cycle += 1
            self._last_orientation = {
                "roll": roll,
                "pitch": pitch,
                "yaw": yaw,
                "calibration_status": calibration_state,
            }
            self._last_read_ts = time.time()
            return self._last_orientation
        # Real hardware: read quaternion → convert to Euler
        if self._last_orientation is None:
            self._last_orientation = {
                "roll": 0.0,
                "pitch": 0.0,
                "yaw": 0.0,
                "calibration_status": "unknown",
            }
        self._last_read_ts = time.time()
        return self._last_orientation


__all__ = ["BNO085Driver"]
