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
import re
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
    # Defaults tuned for recent hardware changes:
    #  - Solar side: 30 A / 75 mV -> R = 0.075 V / 30 A = 0.0025 ohm
    #  - Battery side: 50 A / 75 mV -> R = 0.075 V / 50 A = 0.0015 ohm
    shunt_ohms_ch1: float = 0.0025  # Solar input (default for new hardware)
    shunt_ohms_ch2: float = 0.01    # Reserved
    shunt_ohms_ch3: float = 0.0015  # Battery pack (default for new hardware)


class INA3221Driver(HardwareDriver):
    _REG_BUS_VOLTAGES = (0x02, 0x04, 0x06)
    _REG_SHUNT_VOLTAGES = (0x01, 0x03, 0x05)
    _REG_CONFIG = 0x00
    _CONFIG_DEFAULT = 0x7127  # Continuous mode, 1.1 ms conversion, 64 avg (datasheet)

    @staticmethod
    def _parse_shunt_value(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value) if value > 0 else None
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                f_val = float(stripped)
                return f_val if f_val > 0 else None
            except ValueError:
                match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*A\s*/\s*([0-9]+(?:\.[0-9]+)?)\s*mV", stripped, re.IGNORECASE)
                if not match:
                    return None
                amps = float(match.group(1))
                mv = float(match.group(2))
                if amps <= 0:
                    return None
                return (mv / 1000.0) / amps
        return None

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config=config)
        cfg = config or {}
        base_cfg = _Ina3221Config()

        def _resolve_shunt(channel: int, default: float) -> float:
            direct_key = f"shunt_ohms_ch{channel}"
            spec_key = f"shunt_spec_ch{channel}"
            if direct_key in cfg:
                parsed = self._parse_shunt_value(cfg.get(direct_key))
                if parsed is not None:
                    return parsed
            if spec_key in cfg:
                parsed = self._parse_shunt_value(cfg.get(spec_key))
                if parsed is not None:
                    return parsed
            return default

        address = cfg.get("address", base_cfg.address)
        bus = cfg.get("bus", base_cfg.bus)
        self._cfg = _Ina3221Config(
            address=int(address) if address is not None else base_cfg.address,
            bus=int(bus) if bus is not None else base_cfg.bus,
            shunt_ohms_ch1=_resolve_shunt(1, base_cfg.shunt_ohms_ch1),
            shunt_ohms_ch2=_resolve_shunt(2, base_cfg.shunt_ohms_ch2),
            shunt_ohms_ch3=_resolve_shunt(3, base_cfg.shunt_ohms_ch3),
        )
        # Allow environment overrides. Two forms are supported:
        #  - Direct ohms value: INA3221_SHUNT_OHMS_CH1=0.0025
        #  - Shunt spec: INA3221_SHUNT_SPEC_CH1="30A/75mV" (will be parsed to ohms)
        # Channel mapping: ch1 = solar, ch3 = battery (per driver wiring)
        env_mappings = [
            (1, "INA3221_SHUNT_OHMS_CH1", "INA3221_SHUNT_SPEC_CH1"),
            (2, "INA3221_SHUNT_OHMS_CH2", "INA3221_SHUNT_SPEC_CH2"),
            (3, "INA3221_SHUNT_OHMS_CH3", "INA3221_SHUNT_SPEC_CH3"),
        ]

        for ch, env_ohm, env_spec in env_mappings:
            val = self._parse_shunt_value(os.environ.get(env_ohm))
            if val is None:
                val = self._parse_shunt_value(os.environ.get(env_spec))
            if val is not None and val > 0.0:
                setattr(self._cfg, f"shunt_ohms_ch{ch}", val)
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
