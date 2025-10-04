"""INA3221 triple-channel current/voltage monitor driver (T048) - simulation stub.

Channels per design (FR-024):
  - Channel 1: Battery
  - Channel 3: Solar Input
Channel 2 unused. This stub produces plausible metrics; real implementation
would use smbus2 to read shunt/bus voltage registers and compute current.
"""
from __future__ import annotations

import os
import time
from typing import Any

from ...core.simulation import is_simulation_mode
from ..base import HardwareDriver


class INA3221Driver(HardwareDriver):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config=config)
        self._last_power: dict[str, float] | None = None
        self._cycle: int = 0
        self._last_read_ts: float | None = None

    async def initialize(self) -> None:  # noqa: D401
        self.initialized = True

    async def start(self) -> None:  # noqa: D401
        self.running = True

    async def stop(self) -> None:  # noqa: D401
        self.running = False

    async def health_check(self) -> dict[str, Any]:  # noqa: D401
        return {
            "sensor": "ina3221_power",
            "initialized": self.initialized,
            "running": self.running,
            "last_power": self._last_power,
            "last_read_age_s": (time.time() - self._last_read_ts) if self._last_read_ts else None,
            "simulation": is_simulation_mode(),
        }

    async def read_power(self) -> dict[str, float] | None:
        if not self.initialized:
            return None
        if is_simulation_mode() or os.environ.get("SIM_MODE") == "1":
            # Battery voltage slowly decreases, solar varies
            base_voltage = 12.6 - (self._cycle * 0.005)
            if base_voltage < 11.0:
                base_voltage = 12.6  # reset cycle to simulate charge
                self._cycle = 0
            solar_voltage = 18.0 + (self._cycle % 10) * 0.05
            battery_current = -2.0 + (self._cycle % 5) * 0.1  # negative = discharging
            solar_current = 1.5 + (self._cycle % 7) * 0.05
            self._cycle += 1
            self._last_power = {
                "battery_voltage": round(base_voltage, 2),
                "battery_current_amps": round(battery_current, 2),
                "solar_voltage": round(solar_voltage, 2),
                "solar_current_amps": round(solar_current, 2),
            }
            self._last_read_ts = time.time()
            return self._last_power
        if self._last_power is None:
            self._last_power = {
                "battery_voltage": 12.6,
                "battery_current_amps": -2.5,
                "solar_voltage": 18.3,
                "solar_current_amps": 1.2,
            }
        self._last_read_ts = time.time()
        return self._last_power


__all__ = ["INA3221Driver"]
