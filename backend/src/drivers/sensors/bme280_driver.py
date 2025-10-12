"""BME280 environmental sensor driver (T047).

Uses smbus2 for hardware access while keeping deterministic behaviour in
SIM_MODE for CI. Provides temperature (°C), humidity (%RH), and pressure (hPa)
with standard Bosch compensation formulas.
"""
from __future__ import annotations

import asyncio
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Dict

from ...core.simulation import is_simulation_mode
from ..base import HardwareDriver


@dataclass(slots=True)
class _Bme280Calibration:
    dig_T1: int
    dig_T2: int
    dig_T3: int
    dig_P1: int
    dig_P2: int
    dig_P3: int
    dig_P4: int
    dig_P5: int
    dig_P6: int
    dig_P7: int
    dig_P8: int
    dig_P9: int
    dig_H1: int
    dig_H2: int
    dig_H3: int
    dig_H4: int
    dig_H5: int
    dig_H6: int


class BME280Driver(HardwareDriver):
    _CTRL_HUM = 0xF2
    _CTRL_MEAS = 0xF4
    _CONFIG = 0xF5
    _DATA_START = 0xF7

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config=config)
        cfg = config or {}
        self._address = int(cfg.get("address", 0x76))
        self._bus_num = int(cfg.get("bus", 1))
        self._sea_level_hpa = float(cfg.get("sea_level_hpa", 1013.25))
        self._calibration: _Bme280Calibration | None = None
        self._t_fine: float | None = None
        self._last_env: dict[str, float] | None = None
        self._cycle: int = 0
        self._last_read_ts: float | None = None

    async def initialize(self) -> None:  # noqa: D401
        self.initialized = True
        if is_simulation_mode() or os.environ.get("SIM_MODE") == "1":
            return
        try:
            from smbus2 import SMBus  # type: ignore

            def _load() -> _Bme280Calibration:
                with SMBus(self._bus_num) as bus:
                    calib1 = bus.read_i2c_block_data(self._address, 0x88, 24)
                    calib2 = bus.read_i2c_block_data(self._address, 0xA1, 1)
                    calib3 = bus.read_i2c_block_data(self._address, 0xE1, 7)

                def _u16(msb: int, lsb: int) -> int:
                    return (msb << 8) | lsb

                def _s16(msb: int, lsb: int) -> int:
                    value = _u16(msb, lsb)
                    if value & 0x8000:
                        value -= 1 << 16
                    return value

                def _s8(val: int) -> int:
                    return val - 256 if val & 0x80 else val

                dig_T1 = _u16(calib1[1], calib1[0])
                dig_T2 = _s16(calib1[3], calib1[2])
                dig_T3 = _s16(calib1[5], calib1[4])
                dig_P1 = _u16(calib1[7], calib1[6])
                dig_P2 = _s16(calib1[9], calib1[8])
                dig_P3 = _s16(calib1[11], calib1[10])
                dig_P4 = _s16(calib1[13], calib1[12])
                dig_P5 = _s16(calib1[15], calib1[14])
                dig_P6 = _s16(calib1[17], calib1[16])
                dig_P7 = _s16(calib1[19], calib1[18])
                dig_P8 = _s16(calib1[21], calib1[20])
                dig_P9 = _s16(calib1[23], calib1[22])
                dig_H1 = calib2[0]
                dig_H2 = _s16(calib3[1], calib3[0])
                dig_H3 = calib3[2]
                dig_H4 = (calib3[3] << 4) | (calib3[4] & 0x0F)
                dig_H5 = (calib3[5] << 4) | (calib3[4] >> 4)
                dig_H6 = _s8(calib3[6])

                return _Bme280Calibration(
                    dig_T1, dig_T2, dig_T3,
                    dig_P1, dig_P2, dig_P3, dig_P4, dig_P5, dig_P6, dig_P7, dig_P8, dig_P9,
                    dig_H1, dig_H2, dig_H3, dig_H4, dig_H5, dig_H6,
                )

            self._calibration = await asyncio.to_thread(_load)
        except Exception:
            self._calibration = None

    async def start(self) -> None:  # noqa: D401
        self.running = True
        if is_simulation_mode() or os.environ.get("SIM_MODE") == "1":
            return
        try:
            from smbus2 import SMBus  # type: ignore

            def _configure() -> None:
                with SMBus(self._bus_num) as bus:
                    # Humidity oversampling x1
                    bus.write_byte_data(self._address, self._CTRL_HUM, 0x01)
                    # Temp/pressure oversampling x1, mode normal
                    bus.write_byte_data(self._address, self._CTRL_MEAS, 0x27)
                    # IIR filter off, standby 0.5s (config value 0xA0)
                    bus.write_byte_data(self._address, self._CONFIG, 0xA0)

            await asyncio.to_thread(_configure)
        except Exception:
            pass

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

        if self._calibration is None:
            await self.initialize()
            if self._calibration is None:
                return self._last_env

        try:
            from smbus2 import SMBus  # type: ignore
        except Exception:
            return self._last_env

        try:
            def _read_raw() -> Dict[str, int]:
                with SMBus(self._bus_num) as bus:
                    data = bus.read_i2c_block_data(self._address, self._DATA_START, 8)
                adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
                adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
                adc_h = (data[6] << 8) | data[7]
                return {"t": adc_t, "p": adc_p, "h": adc_h}

            raw = await asyncio.to_thread(_read_raw)
            env = self._compensate(raw)
            if env:
                self._last_env = env
                self._last_read_ts = time.time()
            return self._last_env
        except Exception:
            return self._last_env

    def _compensate(self, raw: Dict[str, int]) -> dict[str, float] | None:
        if self._calibration is None:
            return None

        cal = self._calibration
        adc_T = raw["t"]
        adc_P = raw["p"]
        adc_H = raw["h"]

        if adc_T == 0 or adc_P == 0:
            return None

        var1 = (adc_T / 16384.0 - cal.dig_T1 / 1024.0) * cal.dig_T2
        var2 = ((adc_T / 131072.0 - cal.dig_T1 / 8192.0) ** 2) * cal.dig_T3
        self._t_fine = var1 + var2
        temperature = (self._t_fine / 5120.0)

        var1 = self._t_fine / 2.0 - 64000.0
        var2 = var1 * var1 * cal.dig_P6 / 32768.0
        var2 += var1 * cal.dig_P5 * 2.0
        var2 = var2 / 4.0 + cal.dig_P4 * 65536.0
        var1 = (cal.dig_P3 * var1 * var1 / 524288.0 + cal.dig_P2 * var1) / 524288.0
        var1 = (1.0 + var1 / 32768.0) * cal.dig_P1
        if var1 == 0:
            pressure = None
        else:
            pressure = 1048576.0 - adc_P
            pressure = (pressure - var2 / 4096.0) * 6250.0 / var1
            var1 = cal.dig_P9 * pressure * pressure / 2147483648.0
            var2 = pressure * cal.dig_P8 / 32768.0
            pressure = pressure + (var1 + var2 + cal.dig_P7) / 16.0
            pressure = pressure / 100.0

        humidity = None
        if self._t_fine is not None:
            var_h = self._t_fine - 76800.0
            var_h = (adc_H - (cal.dig_H4 * 64.0 + cal.dig_H5 / 16384.0 * var_h)) * (
                cal.dig_H2 / 65536.0
                * (1.0 + cal.dig_H6 / 67108864.0 * var_h * (1.0 + cal.dig_H3 / 67108864.0 * var_h))
            )
            var_h *= 1.0 - cal.dig_H1 * var_h / 524288.0
            if var_h > 100.0:
                var_h = 100.0
            elif var_h < 0.0:
                var_h = 0.0
            humidity = var_h

        altitude = None
        if pressure and pressure > 0:
            altitude = 44330.0 * (1.0 - (pressure / self._sea_level_hpa) ** 0.1903)

        reading = {
            "temperature_celsius": round(temperature, 2),
            "humidity_percent": round(humidity, 2) if humidity is not None else None,
            "pressure_hpa": round(pressure, 2) if pressure is not None else None,
        }
        if altitude is not None and not math.isnan(altitude):
            reading["altitude_meters"] = round(altitude, 2)
        return reading


__all__ = ["BME280Driver"]
