"""BME280 environmental sensor driver (T047) - simulation stub.

Returns temperature (°C), humidity (%), pressure (hPa). Simulation mode cycles
values within reasonable ranges. Real implementation would use smbus2.
"""
from __future__ import annotations

import os
import time
from typing import Any

from ...core.simulation import is_simulation_mode
from ..base import HardwareDriver


class BME280Driver(HardwareDriver):
    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config=config)
        self._last_env: dict[str, float] | None = None
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
            "sensor": "bme280_env",
            "initialized": self.initialized,
            "running": self.running,
            "last_env": self._last_env,
            "last_read_age_s": (time.time() - self._last_read_ts) if self._last_read_ts else None,
            "simulation": is_simulation_mode(),
        }

    async def read_environment(self) -> dict[str, float] | None:
        if not self.initialized:
            return None
        if is_simulation_mode() or os.environ.get("SIM_MODE") == "1":
            temp = 22.0 + (self._cycle % 10) * 0.1
            humidity = 55.0 + (self._cycle % 20) * 0.2
            pressure = 1013.0 + (self._cycle % 5) * 0.5
            self._cycle += 1
            self._last_env = {
                "temperature_celsius": temp,
                "humidity_percent": humidity,
                "pressure_hpa": pressure,
            }
            self._last_read_ts = time.time()
            return self._last_env
        if self._last_env is None:
            self._last_env = {
                "temperature_celsius": 22.5,
                "humidity_percent": 60.0,
                "pressure_hpa": 1013.25,
            }
        self._last_read_ts = time.time()
        return self._last_env


__all__ = ["BME280Driver"]
