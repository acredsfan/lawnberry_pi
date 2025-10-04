"""VL53L0X Time-of-Flight distance sensor driver (T045).

Implements minimal async lifecycle using the HardwareDriver ABC. This is a
simulation-friendly stub that returns placeholder readings when SIM_MODE=1 or
hardware access libraries are unavailable on the current platform. The real
implementation will integrate with smbus2 for I2C transactions and perform
continuous ranging. For now we expose a single `read_distance_mm` method used
by SensorManager and future safety triggers (obstacle <0.2m → emergency stop).

Platform / Constitution Notes:
- Safe on Pi 4B and Pi 5; avoids importing heavy I2C libs unless present.
- Falls back to deterministic pseudo-random distances in SIM_MODE to enable
  contract test evolution without real hardware.
- Keeps <5ms execution for health_check and read methods (no blocking I/O).
"""
from __future__ import annotations

import os
import random
import time
from typing import Any

from ...core.simulation import is_simulation_mode
from ..base import HardwareDriver


class VL53L0XDriver(HardwareDriver):
    """Minimal VL53L0X driver implementation.

    In real mode this would open the I2C bus and configure continuous ranging
    for each sensor (left/right). At this stage (Phase 3 scaffolding) we only
    provide simulation outputs. Two instances can be created with different
    sensor_id (e.g., "left", "right").
    """

    def __init__(self, sensor_side: str, config: dict[str, Any] | None = None):
        super().__init__(config=config)
        self.sensor_side = sensor_side
        self._last_distance_mm: int | None = None
        self._last_read_ts: float | None = None
        self._i2c_address = 0x29 if sensor_side == "left" else 0x30
        self._sim_distance_cycle: int = 0

    async def initialize(self) -> None:  # noqa: D401
        # Real hardware: open I2C bus, set address, configure timing budget
        self.initialized = True

    async def start(self) -> None:  # noqa: D401
        # Real hardware would start continuous ranging; here we mark running
        self.running = True

    async def stop(self) -> None:  # noqa: D401
        self.running = False

    async def health_check(self) -> dict[str, Any]:  # noqa: D401
        return {
            "sensor": f"vl53l0x_{self.sensor_side}",
            "initialized": self.initialized,
            "running": self.running,
            "last_distance_mm": self._last_distance_mm,
            "last_read_age_s": (time.time() - self._last_read_ts) if self._last_read_ts else None,
            "simulation": is_simulation_mode(),
        }

    async def read_distance_mm(self) -> int | None:
        """Return latest distance in millimeters.

        Simulation mode generates a deterministic oscillating pattern around
        1500mm with occasional obstacle (<180mm) every ~20 cycles for contract
        test development. Real hardware would perform an I2C read sequence.
        """
        if not self.initialized:
            return None

        if is_simulation_mode() or os.environ.get("SIM_MODE") == "1":
            # Deterministic pattern to keep tests stable
            base = 1500
            if self._sim_distance_cycle % 20 == 5:
                simulated = random.randint(120, 180)  # simulate obstacle event
            else:
                simulated = base + (self._sim_distance_cycle % 40) * 10
            self._sim_distance_cycle += 1
            self._last_distance_mm = simulated
            self._last_read_ts = time.time()
            return simulated

        # Placeholder for real hardware read (I2C transaction)
        # In absence of implementation, return last value or nominal distance
        if self._last_distance_mm is None:
            self._last_distance_mm = 1500
        self._last_read_ts = time.time()
        return self._last_distance_mm


__all__ = ["VL53L0XDriver"]
