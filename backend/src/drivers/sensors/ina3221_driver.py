"""INA3221 triple-channel current/voltage monitor driver (T048).

Channels per deployed wiring (FR-024 hardware rev B):
    - Channel 1: Solar input
    - Channel 3: Battery pack
Channel 2 unused. Uses smbus2 to read shunt/bus voltage registers and compute
approximate currents with configurable shunt resistors. Falls back to the last
known reading if hardware access fails so higher layers remain resilient.
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

from ...core.simulation import is_simulation_mode
from ..base import HardwareDriver


@dataclass(slots=True)
class _Ina3221Config:
    address: int = 0x40
    bus: int = 1
    # Ohmic values for each channel shunt resistor; tune via config if wiring differs
    shunt_ohms_ch1: float = 0.01  # Solar input
    shunt_ohms_ch2: float = 0.01  # Reserved
    shunt_ohms_ch3: float = 0.01  # Battery pack


class INA3221Driver(HardwareDriver):
    _REG_BUS_VOLTAGES = (0x02, 0x04, 0x06)
    _REG_SHUNT_VOLTAGES = (0x01, 0x03, 0x05)
    _REG_CONFIG = 0x00
    _CONFIG_DEFAULT = 0x7127  # Continuous mode, 1.1 ms conversion, 64 avg (datasheet)

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config=config)
        cfg = config or {}
        self._cfg = _Ina3221Config(
            address=int(cfg.get("address", 0x40)),
            bus=int(cfg.get("bus", 1)),
            shunt_ohms_ch1=float(cfg.get("shunt_ohms_ch1", 0.01)),
            shunt_ohms_ch2=float(cfg.get("shunt_ohms_ch2", 0.01)),
            shunt_ohms_ch3=float(cfg.get("shunt_ohms_ch3", 0.01)),
        )
        self._last_power: dict[str, float] | None = None
        self._last_read_ts: float | None = None
        self._cycle: int = 0  # retained for SIM_MODE behaviour

    async def initialize(self) -> None:  # noqa: D401
        self.initialized = True
        if is_simulation_mode() or os.environ.get("SIM_MODE") == "1":
            return
        try:
            from smbus2 import SMBus  # type: ignore

            def _write_config() -> None:
                with SMBus(self._cfg.bus) as bus:
                    raw = ((self._CONFIG_DEFAULT & 0xFF) << 8) | (self._CONFIG_DEFAULT >> 8)
                    bus.write_word_data(self._cfg.address, self._REG_CONFIG, raw)

            await asyncio.to_thread(_write_config)
        except Exception:
            # Leave initialized True but rely on graceful fallback during reads
            pass

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
            # Retain previous deterministic simulation for CI
            base_voltage = 12.6 - (self._cycle * 0.005)
            if base_voltage < 11.0:
                base_voltage = 12.6
                self._cycle = 0
            solar_voltage = 18.0 + (self._cycle % 10) * 0.05
            battery_current = -2.0 + (self._cycle % 5) * 0.1
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

        try:
            from smbus2 import SMBus  # type: ignore
        except Exception:
            return self._last_power

        try:
            def _read_all() -> dict[str, float]:
                with SMBus(self._cfg.bus) as bus:
                    def _read_word(register: int) -> int:
                        raw = bus.read_word_data(self._cfg.address, register)
                        return ((raw & 0xFF) << 8) | (raw >> 8)

                    def _decode_bus(raw: int) -> float:
                        return ((raw >> 3) * 0.008)  # 8 mV per bit

                    def _decode_shunt(raw: int) -> float:
                        if raw & 0x8000:
                            raw -= 1 << 16
                        return raw * 0.00004  # 40 µV per bit

                    bus_voltages = [_decode_bus(_read_word(reg)) for reg in self._REG_BUS_VOLTAGES]
                    shunt_voltages = [_decode_shunt(_read_word(reg)) for reg in self._REG_SHUNT_VOLTAGES]

                currents = []
                shunts = [
                    self._cfg.shunt_ohms_ch1,
                    self._cfg.shunt_ohms_ch2,
                    self._cfg.shunt_ohms_ch3,
                ]
                for sv, sh in zip(shunt_voltages, shunts, strict=False):
                    if sh <= 0.0:
                        currents.append(None)
                    else:
                        currents.append(sv / sh)

                battery_voltage = bus_voltages[2]
                battery_current = currents[2] if currents[2] is not None else None
                solar_voltage = bus_voltages[0]
                solar_current = currents[0] if currents[0] is not None else None

                return {
                    "battery_voltage": battery_voltage,
                    "battery_current_amps": battery_current,
                    "battery_power_w": (battery_voltage * battery_current) if battery_current is not None else None,
                    "solar_voltage": solar_voltage,
                    "solar_current_amps": solar_current,
                    "solar_power_w": (solar_voltage * solar_current) if solar_current is not None else None,
                }

            result = await asyncio.to_thread(_read_all)
            if result:
                self._last_power = {
                    k: (round(v, 3) if isinstance(v, float) else v)
                    for k, v in result.items()
                }
                self._last_read_ts = time.time()
            return self._last_power
        except Exception:
            return self._last_power


__all__ = ["INA3221Driver"]
