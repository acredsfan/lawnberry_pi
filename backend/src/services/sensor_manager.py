"""
SensorManager service for LawnBerry Pi v2
Hardware sensor interfaces with I2C/UART coordination and validation
"""

import asyncio
import logging
import math
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from datetime import date as _date
from typing import Any

from ..models import (
    ComponentId,
    ComponentStatus,
    EnvironmentalReading,
    GPSData,
    GpsMode,
    GpsReading,
    HardwareTelemetryStream,
    IMUData,
    ImuReading,
    PowerData,
    PowerReading,
    RtkFixType,
    SensorData,
    SensorStatus,
    SensorType,
    ToFData,
    TofReading,
)
from ..utils.battery import battery_health_label, voltage_current_to_soc, voltage_to_soc

logger = logging.getLogger(__name__)


class SensorCoordinator:
    """Coordinates access to shared I2C/UART resources"""

    def __init__(self):
        self._i2c_lock = asyncio.Lock()
        self._uart_locks = {
            "UART0": asyncio.Lock(),
            "UART1": asyncio.Lock(),
            "UART4": asyncio.Lock(),
        }
        self._active_sensors = set()

    @asynccontextmanager
    async def acquire_i2c(self, sensor_name: str):
        """Acquire I2C bus access"""
        async with self._i2c_lock:
            self._active_sensors.add(sensor_name)
            try:
                yield
            finally:
                self._active_sensors.discard(sensor_name)

    @asynccontextmanager
    async def acquire_uart(self, uart_port: str, sensor_name: str):
        """Acquire UART port access"""
        if uart_port not in self._uart_locks:
            raise ValueError(f"Unknown UART port: {uart_port}")

        async with self._uart_locks[uart_port]:
            self._active_sensors.add(sensor_name)
            try:
                yield
            finally:
                self._active_sensors.discard(sensor_name)


class GPSSensorInterface:
    """GPS sensor interface supporting multiple modules"""

    def __init__(
        self, gps_mode: GpsMode, coordinator: SensorCoordinator, usb_device: str | None = None
    ):
        self.gps_mode = gps_mode
        self.coordinator = coordinator
        self.last_reading: GpsReading | None = None
        self.status = SensorStatus.OFFLINE
        self._ntrip_forwarder: object | None = None  # NtripForwarder, set after init
        # Concrete driver (lazy, SIM-safe)
        try:
            from ..drivers.sensors.gps_driver import GPSDriver  # type: ignore

            driver_cfg: dict = {"mode": gps_mode}
            if usb_device:
                driver_cfg["usb_device"] = usb_device
            self._driver = GPSDriver(driver_cfg)
        except Exception:  # pragma: no cover - keep SIM-safe
            self._driver = None

    async def initialize(self) -> bool:
        """Initialize GPS sensor"""
        try:
            if self._driver is not None:
                await self._driver.initialize()
                await self._driver.start()
                self.status = SensorStatus.ONLINE
            else:
                # Fallback placeholder
                self.status = SensorStatus.ONLINE
            return True

        except Exception as e:
            logger.error(f"Failed to initialize GPS: {e}")
            self.status = SensorStatus.ERROR
            return False

    async def read_gps(self) -> GpsReading | None:
        """Read GPS data"""
        if self.status != SensorStatus.ONLINE:
            return None

        try:
            if getattr(self, "_driver", None) is not None:
                reading = await self._driver.read_position()
                if reading is None:
                    # Keep last_reading if available
                    reading = (
                        self.last_reading.model_copy(update={"cached": True})
                        if self.last_reading is not None
                        else None
                    )
            else:
                # No driver available — return None so the dashboard shows "—"
                reading = (
                    self.last_reading.model_copy(update={"cached": True})
                    if self.last_reading is not None
                    else None
                )

            self.last_reading = reading
            if (
                reading is not None
                and reading.latitude is not None
                and reading.longitude is not None
                and self._ntrip_forwarder is not None
            ):
                try:
                    self._ntrip_forwarder.update_gga_from_position(  # type: ignore[attr-defined]
                        reading.latitude,
                        reading.longitude,
                        reading.altitude or 0.0,
                    )
                except Exception:
                    pass
            return reading

        except Exception as e:
            logger.error(f"GPS reading failed: {e}")
            self.status = SensorStatus.ERROR
            return None


class IMUSensorInterface:
    """BNO085 IMU sensor interface"""

    def __init__(self, coordinator: SensorCoordinator, imu_config: dict | None = None):
        self.coordinator = coordinator
        self.last_reading: ImuReading | None = None
        self.status = SensorStatus.OFFLINE
        try:
            from ..drivers.sensors.bno085_driver import BNO085Driver  # type: ignore

            self._driver = BNO085Driver(imu_config or {})
        except Exception:  # pragma: no cover
            self._driver = None

    async def initialize(self) -> bool:
        """Initialize BNO085 IMU"""
        try:
            if self._driver is not None:
                await self._driver.initialize()
                await self._driver.start()
                self.status = SensorStatus.ONLINE
                return True
            else:
                self.status = SensorStatus.ONLINE
                return True

        except Exception as e:
            logger.error(f"Failed to initialize IMU: {e}")
            self.status = SensorStatus.ERROR
            return False

    async def read_imu(self) -> ImuReading | None:
        """Read IMU data"""
        if self.status != SensorStatus.ONLINE:
            return None

        try:
            if getattr(self, "_driver", None) is not None:
                o = await self._driver.read_orientation()
                if o is not None:
                    cal = o.get("calibration_status") or "uncalibrated"
                    reading = ImuReading(
                        roll=o.get("roll"),
                        pitch=o.get("pitch"),
                        yaw=o.get("yaw"),
                        accel_x=o.get("accel_x"),
                        accel_y=o.get("accel_y"),
                        accel_z=o.get("accel_z"),
                        gyro_x=o.get("gyro_x"),
                        gyro_y=o.get("gyro_y"),
                        gyro_z=o.get("gyro_z"),
                        calibration_status=cal,
                        monotonic_received_s=o.get("monotonic_received_s"),
                        cached=bool(o.get("cached", False)),
                        imu_epoch_id=o.get("imu_epoch_id"),
                    )
                else:
                    reading = (
                        self.last_reading.model_copy(update={"cached": True})
                        if self.last_reading is not None
                        else None
                    )
            else:
                # Driver unavailable but interface is ONLINE -- report
                # "uncalibrated" rather than "unknown".
                reading = ImuReading(
                    roll=0.0,
                    pitch=0.0,
                    yaw=0.0,
                    calibration_status="uncalibrated",
                    monotonic_received_s=None,
                    cached=True,
                )

            if reading is not None:
                self.last_reading = reading
            return reading

        except Exception as e:
            logger.error(f"IMU reading failed: {e}")
            self.status = SensorStatus.ERROR
            return None


class ToFSensorInterface:
    """VL53L0X Time-of-Flight sensor interface"""

    def __init__(self, coordinator: SensorCoordinator, tof_config: dict | None = None):
        self.coordinator = coordinator
        self.left_reading: TofReading | None = None
        self.right_reading: TofReading | None = None
        self.status = SensorStatus.OFFLINE
        self._owner_task: asyncio.Task | None = None
        self._owner_stopping = False
        self._sample_id = 0
        self._outcomes: dict[str, deque[bool]] = {
            "left": deque(maxlen=20),
            "right": deque(maxlen=20),
        }
        self._last_sample_monotonic_s: dict[str, float | None] = {
            "left": None,
            "right": None,
        }
        cfg = tof_config or {}
        timing_budget_s = max(0.0, float(cfg.get("timing_budget_us") or 33000) / 1_000_000.0)
        self._sample_timeout_s = max(0.08, timing_budget_s + 0.05)
        self._poll_interval_s = max(0.01, min(0.05, timing_budget_s / 2.0))
        try:
            from ..drivers.sensors.vl53l0x_driver import VL53L0XDriver  # type: ignore

            cfg = tof_config or {}
            left_cfg = {
                "bus": cfg.get("bus"),
                "address": cfg.get("left_address"),
                "shutdown_gpio": cfg.get("left_shutdown_gpio"),
                "ranging_mode": cfg.get("ranging_mode"),
                "timing_budget_us": cfg.get("timing_budget_us"),
            }
            right_cfg = {
                "bus": cfg.get("bus"),
                "address": cfg.get("right_address"),
                "shutdown_gpio": cfg.get("right_shutdown_gpio"),
                "ranging_mode": cfg.get("ranging_mode"),
                "timing_budget_us": cfg.get("timing_budget_us"),
            }
            self._left = VL53L0XDriver("left", left_cfg)
            self._right = VL53L0XDriver("right", right_cfg)
        except Exception:  # pragma: no cover
            self._left = None
            self._right = None

    async def initialize(self) -> bool:
        """Initialize VL53L0X sensors"""
        try:
            if self._left is not None and self._right is not None:
                # Run the XSHUT pair-addressing sequence before individual inits.
                # Both sensors boot at 0x29; the sequence holds one in reset while
                # the other is assigned its unique address.
                try:
                    from ..drivers.sensors.vl53l0x_driver import ensure_pair_addressing
                    left_gpio = getattr(self._left, "_xshut_gpio", None)
                    right_gpio = getattr(self._right, "_xshut_gpio", None)
                    right_addr = getattr(self._right, "_i2c_address", 0x30)
                    if left_gpio is not None and right_gpio is not None:
                        paired = await ensure_pair_addressing(left_gpio, right_gpio, right_addr)
                        if not paired:
                            logger.warning(
                                "VL53L0X XSHUT pair-addressing failed (GPIO %s/%s) — "
                                "attempting single-sensor init",
                                left_gpio, right_gpio,
                            )
                except Exception as pair_exc:
                    logger.warning("VL53L0X pair-addressing error: %s — falling back to individual init", pair_exc)
                await self._left.initialize()
                await self._right.initialize()
                await self._left.start()
                await self._right.start()
                left_ok = bool(
                    getattr(self._left, "initialized", False)
                    and getattr(self._left, "running", False)
                )
                right_ok = bool(
                    getattr(self._right, "initialized", False)
                    and getattr(self._right, "running", False)
                )
                if left_ok and right_ok:
                    self.status = SensorStatus.ONLINE
                    await self._acquire_pair_once()
                    self._owner_stopping = False
                    self._owner_task = asyncio.create_task(
                        self._acquisition_loop(),
                        name="tof_acquisition_owner",
                    )
                    return True
                self.status = SensorStatus.ERROR
                logger.warning(
                    "VL53L0X initialization incomplete: left=%s right=%s left_backend=%s "
                    "right_backend=%s left_error=%s right_error=%s",
                    left_ok,
                    right_ok,
                    getattr(self._left, "_driver_backend", None),
                    getattr(self._right, "_driver_backend", None),
                    getattr(self._left, "_last_error", None),
                    getattr(self._right, "_last_error", None),
                )
                return False
            else:
                self.status = SensorStatus.OFFLINE
                return False

        except Exception as e:
            logger.error(f"Failed to initialize ToF sensors: {e}")
            self.status = SensorStatus.ERROR
            return False

    async def read_tof_sensors(self) -> tuple[TofReading | None, TofReading | None]:
        """Return immutable owner-produced samples without touching I2C."""
        left = self.left_reading.model_copy(deep=True) if self.left_reading else None
        right = self.right_reading.model_copy(deep=True) if self.right_reading else None
        return left, right

    async def _acquisition_loop(self) -> None:
        """Continuously acquire both sensors as the sole I2C-reading owner."""
        while not self._owner_stopping:
            try:
                await self._acquire_pair_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("ToF acquisition owner failed: %s", exc)
            await asyncio.sleep(self._poll_interval_s)

    async def _acquire_pair_once(self) -> None:
        if self._left is None or self._right is None:
            return
        async with self.coordinator.acquire_i2c("vl53l0x_owner"):
            await self._acquire_sensor("left", self._left)
            await self._acquire_sensor("right", self._right)

    async def _acquire_sensor(self, side: str, driver: Any) -> None:
        started = time.monotonic()
        try:
            distance = await driver.read_distance_mm()
            elapsed = time.monotonic() - started
            valid_distance = isinstance(distance, int) and 0 < distance < 8000
            successful = bool(
                valid_distance
                and int(getattr(driver, "_fail_count", 0) or 0) == 0
                and elapsed <= self._sample_timeout_s
            )
        except Exception as exc:
            logger.warning("ToF %s acquisition failed: %s", side, exc)
            distance = None
            successful = False

        self._outcomes[side].append(successful)
        if not successful:
            return
        now_mono = time.monotonic()
        self._sample_id += 1
        reading = TofReading(
            distance=float(distance),
            signal_strength=None,
            range_status="valid",
            sensor_side=side,
            sample_id=self._sample_id,
            monotonic_received_s=now_mono,
            cached=False,
        )
        self._last_sample_monotonic_s[side] = now_mono
        if side == "left":
            self.left_reading = reading
        else:
            self.right_reading = reading

    def health_snapshot(self) -> dict[str, Any]:
        now = time.monotonic()

        def side_payload(side: str, reading: TofReading | None, driver: Any) -> dict[str, Any]:
            outcomes = self._outcomes[side]
            failures = sum(1 for ok in outcomes if not ok)
            sample_time = self._last_sample_monotonic_s[side]
            return {
                "sample_id": reading.sample_id if reading else None,
                "sample_age_s": None if sample_time is None else max(0.0, now - sample_time),
                "window_samples": len(outcomes),
                "failure_rate": failures / len(outcomes) if outcomes else None,
                "last_error": getattr(driver, "_last_error", None),
            }

        return {
            "owner_running": bool(self._owner_task and not self._owner_task.done()),
            "left": side_payload("left", self.left_reading, self._left),
            "right": side_payload("right", self.right_reading, self._right),
        }

    async def shutdown(self) -> None:
        self._owner_stopping = True
        if self._owner_task and not self._owner_task.done():
            self._owner_task.cancel()
            try:
                await self._owner_task
            except asyncio.CancelledError:
                pass
        self._owner_task = None
        for driver in (self._left, self._right):
            if driver is not None:
                await driver.stop()
        self.status = SensorStatus.OFFLINE


class EnvironmentalSensorInterface:
    """BME280 environmental sensor interface"""

    def __init__(self, coordinator: SensorCoordinator, config: dict | None = None):
        self.coordinator = coordinator
        self.last_reading: EnvironmentalReading | None = None
        self.status = SensorStatus.OFFLINE
        self._config = config or {}
        try:
            from ..drivers.sensors.bme280_driver import BME280Driver  # type: ignore

            self._driver = BME280Driver(self._config)
        except Exception:  # pragma: no cover
            self._driver = None

    async def initialize(self) -> bool:
        """Initialize BME280 sensor"""
        try:
            if self._driver is not None:
                await self._driver.initialize()
                await self._driver.start()
                self.status = SensorStatus.ONLINE
                return True
            else:
                self.status = SensorStatus.ONLINE
                return True

        except Exception as e:
            logger.error(f"Failed to initialize BME280: {e}")
            self.status = SensorStatus.ERROR
            return False

    async def read_environmental(self) -> EnvironmentalReading | None:
        """Read environmental data"""
        if self.status != SensorStatus.ONLINE:
            return None

        try:
            if getattr(self, "_driver", None) is not None:
                env = await self._driver.read_environment()
                if env is not None:
                    reading = EnvironmentalReading(
                        temperature=env.get("temperature_celsius"),
                        humidity=env.get("humidity_percent"),
                        pressure=env.get("pressure_hpa"),
                        altitude=env.get("altitude_meters"),
                    )
                else:
                    reading = self.last_reading
            else:
                reading = self.last_reading

            if reading is not None:
                self.last_reading = reading
            return reading

        except Exception as e:
            logger.error(f"Environmental reading failed: {e}")
            self.status = SensorStatus.ERROR
            return None


class PowerSensorInterface:
    """Aggregated power monitoring interface (INA3221 + optional Victron)."""

    def __init__(self, coordinator: SensorCoordinator, driver_config: dict[str, Any] | None = None):
        self.coordinator = coordinator
        self.last_reading: PowerReading | None = None
        self.status = SensorStatus.OFFLINE
        self._driver_config = driver_config or {}
        self._ina_driver = None
        self._victron_driver = None
        self._prefer_battery = False
        self._prefer_solar = False
        self._prefer_load = False

        # Battery consumption accumulator (reset daily at midnight)
        self._battery_consumed_today_wh: float = 0.0
        # Solar yield accumulator — fallback when Victron doesn't report yield_today
        self._solar_yield_today_wh: float = 0.0
        self._last_power_read_dt: datetime | None = None
        self._last_accumulation_date: _date | None = None

        ina_cfg = self._extract_ina_config(self._driver_config)
        victron_cfg = self._extract_victron_config(self._driver_config)

        if ina_cfg is not None:
            try:
                from ..drivers.sensors.ina3221_driver import INA3221Driver  # type: ignore

                self._ina_driver = INA3221Driver(ina_cfg)
            except Exception as exc:  # pragma: no cover - hardware optional
                logger.warning("INA3221 driver unavailable: %s", exc)
                self._ina_driver = None

        if victron_cfg is not None and bool(victron_cfg.get("enabled", True)):
            try:
                from ..drivers.sensors.victron_vedirect import VictronVeDirectDriver  # type: ignore

                self._victron_driver = VictronVeDirectDriver(victron_cfg)
                self._prefer_battery = bool(victron_cfg.get("prefer_battery", False))
                self._prefer_solar = bool(victron_cfg.get("prefer_solar", False))
                self._prefer_load = bool(victron_cfg.get("prefer_load", False))
            except Exception as exc:  # pragma: no cover - optional hardware
                logger.warning("Victron VE.Direct driver unavailable: %s", exc)
                self._victron_driver = None

        self._drivers = [d for d in (self._ina_driver, self._victron_driver) if d is not None]

    async def initialize(self) -> bool:
        """Initialize INA3221 power monitor"""
        if not self._drivers:
            self.status = SensorStatus.OFFLINE
            return False

        any_success = False
        for driver in self._drivers:
            try:
                await driver.initialize()
                await driver.start()
                any_success = True
            except Exception as exc:  # pragma: no cover - hardware dependent
                logger.error(
                    "Failed to initialize power driver %s: %s", driver.__class__.__name__, exc
                )

        self.status = SensorStatus.ONLINE if any_success else SensorStatus.ERROR
        return any_success

    async def read_power(self) -> PowerReading | None:
        """Read power monitoring data"""
        if self.status != SensorStatus.ONLINE:
            return None

        try:
            # Per-driver timeouts allow a stalled Victron BLE read to be cancelled
            # without discarding INA3221 data that already succeeded.
            _INA_TIMEOUT_S = 1.0
            _VICTRON_TIMEOUT_S = 4.0

            async def _safe_driver_read(name: str, driver, timeout: float):
                if driver is None:
                    return None
                try:
                    return await asyncio.wait_for(driver.read_power(), timeout=timeout)
                except TimeoutError:
                    logger.warning("%s read timed out after %.1fs; using last known", name, timeout)
                    return None
                except Exception as exc:
                    logger.error("%s read failed: %s", name, exc)
                    return None

            ina_payload, victron_payload = await asyncio.gather(
                _safe_driver_read("INA3221", self._ina_driver, _INA_TIMEOUT_S),
                _safe_driver_read("Victron", self._victron_driver, _VICTRON_TIMEOUT_S),
            )

            merged = self._merge_power_payload(
                ina_payload,
                victron_payload,
                prefer_battery=self._prefer_battery,
                prefer_solar=self._prefer_solar,
                prefer_load=self._prefer_load,
            )

            if merged is None:
                reading = self.last_reading
            else:
                reading = merged

            # Accumulate battery consumption and solar yield for fresh readings
            if merged is not None and reading is not None:
                now_dt = datetime.now(UTC)
                now_date = now_dt.date()
                if (
                    self._last_accumulation_date is not None
                    and now_date != self._last_accumulation_date
                ):
                    self._battery_consumed_today_wh = 0.0
                    self._solar_yield_today_wh = 0.0
                self._last_accumulation_date = now_date
                if self._last_power_read_dt is not None:
                    elapsed_s = (now_dt - self._last_power_read_dt).total_seconds()
                    if 0 < elapsed_s < 300:
                        lc = reading.load_current
                        bv = reading.battery_voltage
                        if (
                            lc is not None
                            and bv is not None
                            and abs(lc) > 0.01
                            and bv > 0
                        ):
                            self._battery_consumed_today_wh += abs(lc) * bv * elapsed_s / 3600
                        sp = reading.solar_power
                        if sp is not None and sp > 0:
                            self._solar_yield_today_wh += sp * elapsed_s / 3600
                self._last_power_read_dt = now_dt
            if reading is not None:
                reading.battery_consumed_today_wh = self._battery_consumed_today_wh
                if reading.solar_yield_today_wh is None:
                    reading.solar_yield_today_wh = self._solar_yield_today_wh

            self.last_reading = reading
            return reading

        except Exception as e:
            logger.error(f"Power reading failed: {e}")
            self.status = SensorStatus.ERROR
            return None

    @staticmethod
    def _extract_ina_config(config: dict[str, Any]) -> dict[str, Any] | None:
        if not config:
            return None
        direct_keys = {
            "address",
            "bus",
            "shunt_ohms_ch1",
            "shunt_ohms_ch2",
            "shunt_ohms_ch3",
            "shunt_spec_ch1",
            "shunt_spec_ch2",
            "shunt_spec_ch3",
        }
        if any(key in config for key in direct_keys):
            return {k: config[k] for k in config if k in direct_keys or k.startswith("shunt_")}
        candidate = config.get("ina3221") or config.get("ina") or config.get("ina_config")
        if isinstance(candidate, dict):
            return candidate
        return None

    @staticmethod
    def _extract_victron_config(config: dict[str, Any]) -> dict[str, Any] | None:
        if not config:
            return None
        candidate = (
            config.get("victron") or config.get("victron_vedirect") or config.get("victron_config")
        )
        if isinstance(candidate, dict):
            return candidate
        return None

    @staticmethod
    def _valid_number(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, (int, float)):
            if isinstance(value, float) and math.isnan(value):
                return False
            return True
        return False

    @classmethod
    def _pick(cls, *values: Any, min_abs: float | None = None) -> float | None:
        for value in values:
            if cls._valid_number(value):
                numeric = float(value)
                if min_abs is not None and abs(numeric) < min_abs:
                    continue
                return numeric
        return None

    @classmethod
    def _source_for(
        cls,
        candidates: list[tuple[str, Any]],
        *,
        min_abs: float | None = None,
    ) -> str | None:
        for source, value in candidates:
            if not cls._valid_number(value):
                continue
            if min_abs is not None and abs(float(value)) < min_abs:
                continue
            return source
        return None

    @staticmethod
    def _combine_sources(*sources: str | None) -> str | None:
        expanded: list[str] = []
        for source in sources:
            if not source:
                continue
            if source.startswith("mixed:"):
                expanded.extend(part for part in source.removeprefix("mixed:").split("+") if part)
            else:
                expanded.append(source)
        unique = list(dict.fromkeys(expanded))
        if not unique:
            return None
        if len(unique) == 1:
            return unique[0]
        return "mixed:" + "+".join(unique)

    @classmethod
    def _merge_power_payload(
        cls,
        ina: dict[str, Any] | None,
        victron: dict[str, Any] | None,
        *,
        prefer_battery: bool = False,
        prefer_solar: bool = False,
        prefer_load: bool = False,
    ) -> PowerReading | None:
        if not ina and not victron:
            return None

        battery_voltage_candidates = [
            ("victron", victron.get("battery_voltage") if victron else None)
        ]
        if not prefer_battery:
            battery_voltage_candidates.append(
                ("ina3221", ina.get("battery_voltage") if ina else None)
            )
        battery_voltage = cls._pick(
            *(value for _, value in battery_voltage_candidates), min_abs=0.05
        )
        battery_voltage_source = cls._source_for(
            battery_voltage_candidates, min_abs=0.05
        )
        battery_current_candidates: list[tuple[str, Any]] = []
        if prefer_battery:
            battery_current_candidates.extend(
                [
                    ("victron", victron.get("battery_current_amps") if victron else None),
                    ("victron", victron.get("battery_current") if victron else None),
                ]
            )
        battery_current_candidates.extend(
            [
                ("ina3221", ina.get("battery_current") if ina else None),
                ("ina3221", ina.get("battery_current_amps") if ina else None),
            ]
        )
        if not prefer_battery:
            battery_current_candidates.extend(
                [
                    ("victron", victron.get("battery_current_amps") if victron else None),
                    ("victron", victron.get("battery_current") if victron else None),
                ]
            )
        battery_current = cls._pick(
            *(value for _, value in battery_current_candidates)
        )
        battery_current_source = cls._source_for(battery_current_candidates)
        solar_voltage_candidates = [
            ("victron", victron.get("solar_voltage") if victron else None),
            ("ina3221", ina.get("solar_voltage") if ina else None),
        ]
        solar_voltage = cls._pick(
            *(value for _, value in solar_voltage_candidates), min_abs=0.05
        )
        solar_voltage_source = cls._source_for(solar_voltage_candidates, min_abs=0.05)
        # Capture per-source solar current/power to avoid cross-source derivations
        victron_solar_current = victron.get("solar_current_amps") if victron else None
        ina_solar_current = ina.get("solar_current_amps") if ina else None
        solar_current_candidates: list[tuple[str, Any]] = []
        # Prefer Victron for PV-side semantics when present
        solar_current_candidates.append(("victron", victron_solar_current))
        solar_current_candidates.append(("ina3221", ina_solar_current))
        solar_current = cls._pick(*(value for _, value in solar_current_candidates))
        solar_current_source = cls._source_for(solar_current_candidates)

        victron_solar_power = (
            (victron.get("solar_power_w") if victron else None) if victron else None
        )
        if victron_solar_power is None and victron:
            victron_solar_power = victron.get("solar_power")
        ina_solar_power = ina.get("solar_power_w") if ina else None
        solar_power_candidates: list[tuple[str, Any]] = []
        # Prefer Victron for PV-side power as well
        solar_power_candidates.append(("victron", victron_solar_power))
        solar_power_candidates.append(("ina3221", ina_solar_power))
        solar_power = cls._pick(*(value for _, value in solar_power_candidates))
        solar_power_source = cls._source_for(solar_power_candidates)

        battery_power_candidates: list[tuple[str, Any]] = []
        if prefer_battery:
            battery_power_candidates.extend(
                [
                    ("victron", victron.get("battery_power_w") if victron else None),
                    ("victron", victron.get("battery_power") if victron else None),
                ]
            )
        battery_power_candidates.append(
            ("ina3221", ina.get("battery_power_w") if ina else None)
        )
        if not prefer_battery:
            battery_power_candidates.extend(
                [
                    ("victron", victron.get("battery_power_w") if victron else None),
                    ("victron", victron.get("battery_power") if victron else None),
                ]
            )
        battery_power = cls._pick(*(value for _, value in battery_power_candidates))
        battery_power_source = cls._source_for(battery_power_candidates)

        if battery_power is None and battery_voltage is not None and battery_current is not None:
            battery_power = round(battery_voltage * battery_current, 3)
            battery_power_source = cls._combine_sources(
                battery_voltage_source, battery_current_source
            )
        # Prefer computing missing solar metrics only when both operands come from the same source
        if solar_power is None and solar_voltage is not None and solar_current is not None:
            # Derive power only when voltage/current share origin
            same_origin = False
            try:
                same_origin = (
                    # Both from Victron
                    (
                        victron is not None
                        and victron.get("solar_voltage") is not None
                        and victron_solar_current is not None
                    )
                    # Or both from INA
                    or (
                        victron is None
                        and ina is not None
                        and ina.get("solar_voltage") is not None
                        and ina_solar_current is not None
                    )
                )
            except Exception:
                same_origin = False
            if same_origin:
                solar_power = round(solar_voltage * solar_current, 3)
                solar_power_source = cls._combine_sources(
                    solar_voltage_source, solar_current_source
                )

        if (
            solar_voltage is None
            and solar_power is not None
            and solar_current is not None
            and abs(solar_current) > 1e-6
        ):
            # Derive panel voltage from P/I. Prefer same-source pairs; fall back to
            # cross-source (Victron panel power + INA panel-side current) because the
            # INA3221 is wired low-side on the solar negative return — it measures real
            # panel current even though it cannot measure panel voltage directly.
            ina_solar_v_raw = ina.get("solar_voltage") if ina else None
            ina_bus_valid = ina_solar_v_raw is not None and abs(float(ina_solar_v_raw)) >= 0.05
            ina_current_val = ina_solar_current if ina_solar_current is not None else None
            derived = None
            try:
                if victron_solar_power is not None and victron_solar_current is not None:
                    # Both from Victron (e.g. VE.Direct)
                    derived = float(victron_solar_power) / float(victron_solar_current)
                elif (
                    ina_bus_valid
                    and ina_solar_power is not None
                    and ina_solar_current is not None
                    and abs(float(ina_solar_current)) > 1e-6
                ):
                    # Both from INA (high-side wiring)
                    derived = float(ina_solar_power) / float(ina_solar_current)
                elif (
                    victron_solar_power is not None
                    and ina_current_val is not None
                    and abs(float(ina_current_val)) > 1e-6
                ):
                    # Cross-source: Victron panel power + INA low-side panel current.
                    # Low-side shunt convention makes current sign negative; use abs
                    # so derived panel voltage is always positive (V = P / |I|).
                    derived = float(victron_solar_power) / abs(float(ina_current_val))
            except Exception:
                derived = None
            # Solar panel voltage is always positive — discard non-positive derived values
            if derived is not None and derived >= 0.05:
                solar_voltage = round(derived, 3)
                solar_voltage_source = cls._combine_sources(
                    solar_power_source, solar_current_source
                )

        load_current_candidates: list[tuple[str, Any]] = []
        if prefer_load:
            load_current_candidates.append(
                ("victron", victron.get("load_current_amps") if victron else None)
            )
        load_current_candidates.append(
            ("ina3221", ina.get("load_current_amps") if ina else None)
        )
        if not prefer_load:
            load_current_candidates.append(
                ("victron", victron.get("load_current_amps") if victron else None)
            )
        load_current = cls._pick(*(value for _, value in load_current_candidates))
        load_source = cls._source_for(load_current_candidates)

        # Daily solar yield (Wh) when available from Victron
        solar_yield_today_wh = None
        try:
            if victron and isinstance(victron, dict):
                solar_yield_today_wh = cls._pick(victron.get("solar_yield_today_wh"))
        except Exception:
            solar_yield_today_wh = None

        # Coherence guard: INA3221 ch1 reports physically-impossible current/power when
        # its bus voltage pin is ≤0.05 V (PV sense wire absent or panel disconnected).
        # Victron BLE provides solar_power and yield_today independently of PV voltage —
        # those are always valid and must pass through even when solar_voltage is null.
        if solar_voltage is None:
            ina_solar_v_raw = ina.get("solar_voltage") if ina else None
            ina_bus_zero = ina_solar_v_raw is None or abs(float(ina_solar_v_raw or 0)) < 0.05
            if ina_bus_zero:
                solar_current = None  # suppress physically-impossible INA ch1 current
                if victron_solar_power is None:
                    # No Victron power measurement — INA-derived power is garbage at 0 V bus
                    solar_power = None

        reading = PowerReading(
            battery_voltage=battery_voltage,
            battery_current=battery_current,
            battery_power=battery_power,
            solar_voltage=solar_voltage,
            solar_current=solar_current,
            solar_power=solar_power,
            solar_yield_today_wh=solar_yield_today_wh,
            load_current=load_current,
            battery_source=cls._combine_sources(
                battery_voltage_source,
                battery_current_source,
                battery_power_source,
            ),
            solar_source=cls._combine_sources(
                solar_voltage_source,
                solar_current_source,
                solar_power_source,
            ),
            load_source=load_source,
        )

        return reading


class SensorManager:
    """Main sensor manager coordinating all sensor interfaces"""

    # BNO085 uses SHTP Game Rotation Vector (1.0s per-read); GPS F9P_USB is fast.
    # 2.5 s is ample for all non-BLE sensors.
    SENSOR_READ_TIMEOUT_SECONDS = 2.5
    # Inner driver timeouts sum to ≤5 s (INA 1 s + Victron 4 s, parallel).
    # The outer budget is kept slightly above that as a backstop.
    POWER_READ_TIMEOUT_SECONDS = 5.0

    def __init__(
        self,
        gps_mode: GpsMode = GpsMode.F9P_USB,
        tof_config: dict | None = None,
        power_config: dict | None = None,
        battery_config=None,  # Optional[BatteryConfig]
        imu_config: dict | None = None,
        environmental_config: dict | None = None,
        gps_usb_device: str | None = None,
    ):
        self.coordinator = SensorCoordinator()

        # Battery spec — used for SOC estimation and health classification
        self._battery_config = battery_config  # BatteryConfig | None

        # Initialize sensor interfaces
        self.gps = GPSSensorInterface(gps_mode, self.coordinator, usb_device=gps_usb_device)
        self.imu = IMUSensorInterface(self.coordinator, imu_config=imu_config)
        self.tof = ToFSensorInterface(self.coordinator, tof_config=tof_config)
        self.environmental = EnvironmentalSensorInterface(
            self.coordinator,
            config=environmental_config,
        )
        self.power = PowerSensorInterface(self.coordinator, driver_config=power_config)

        self.initialized = False
        self.validation_enabled = True

        # Serialize concurrent reads: only one real hardware read at a time.
        # Rapid callers get the cached result if it is fresh enough.
        self._read_lock: asyncio.Lock = asyncio.Lock()
        self._read_cache: SensorData | None = None
        self._read_cache_ts: float = 0.0
        # 180 ms — slightly less than the 200 ms telemetry-loop period so the
        # loop always gets a fresh read while HTTP bursts are served from cache.
        _CACHE_TTL_S: float = 0.18
        self._CACHE_TTL_S = _CACHE_TTL_S

    async def initialize(self) -> bool:
        """Initialize all sensors"""
        logger.info("Initializing sensor manager")

        results = await asyncio.gather(
            self.gps.initialize(),
            self.imu.initialize(),
            self.tof.initialize(),
            self.environmental.initialize(),
            self.power.initialize(),
            return_exceptions=True,
        )

        success_count = sum(1 for result in results if result is True)
        total_sensors = len(results)

        logger.info(f"Sensor initialization: {success_count}/{total_sensors} successful")

        # Consider initialized if at least core sensors are working
        self.initialized = success_count >= 3
        return self.initialized

    async def read_all_sensors(self, bootstrap_mode: bool = False) -> SensorData:
        """Read data from all sensors.

        Only one hardware read is allowed in-flight at a time.  Concurrent
        callers wait on ``_read_lock`` then receive the cached result if it is
        still fresh (< ``_CACHE_TTL_S`` seconds old).  This prevents thread-pool
        exhaustion when the BNO085 or another blocking driver is slow.
        
        Args:
            bootstrap_mode: If True, extend GPS timeout to 2.0s for heading bootstrap.
        """
        if not self.initialized:
            logger.warning("Sensor manager not initialized")
            return SensorData()

        async with self._read_lock:
            now = time.monotonic()
            if self._read_cache is not None and (now - self._read_cache_ts) < self._CACHE_TTL_S:
                return self._read_cache

            result = await self._do_read_all_sensors(bootstrap_mode=bootstrap_mode)
            self._read_cache = result
            self._read_cache_ts = time.monotonic()
            return result

    async def read_fast_safety_sensors(self) -> SensorData:
        """Read only fast safety-critical sensors without waiting on slow telemetry.

        This path intentionally excludes GPS, environmental, power/Victron,
        camera, history, and WebSocket work. It is used by the live safety loop
        so tilt and near-field obstacle decisions are not delayed by aggregate
        telemetry reads.
        """

        async def _read_with_timeout(name: str, coro: Any, timeout: float) -> Any:
            try:
                return await asyncio.wait_for(coro, timeout=timeout)
            except TimeoutError:
                logger.warning("Timed out reading fast safety %s after %.2fs", name, timeout)
                return None

        imu_timeout_s = 0.08
        tof_timeout_s = min(0.20, max(0.05, float(self._CACHE_TTL_S)))
        imu_data, tof_data = await asyncio.gather(
            _read_with_timeout("imu", self.imu.read_imu(), imu_timeout_s),
            _read_with_timeout("tof", self.tof.read_tof_sensors(), tof_timeout_s),
        )
        tof_left, tof_right = (None, None)
        if isinstance(tof_data, tuple):
            tof_left, tof_right = tof_data
        return SensorData(
            imu=imu_data,
            tof_left=tof_left,
            tof_right=tof_right,
            sensor_health={
                SensorType.IMU: self.imu.status,
                SensorType.TOF_LEFT: self.tof.status,
                SensorType.TOF_RIGHT: self.tof.status,
            },
        )

    async def read_slow_safety_sensors(self) -> SensorData:
        """Read slower safety-relevant samples without blocking the fast loop."""

        async def _read_with_timeout(name: str, coro: Any, timeout: float) -> Any:
            try:
                return await asyncio.wait_for(coro, timeout=timeout)
            except TimeoutError:
                logger.warning("Timed out reading slow safety %s after %.1fs", name, timeout)
                return None

        env_data, power_data = await asyncio.gather(
            _read_with_timeout("environmental", self.environmental.read_environmental(), 1.0),
            _read_with_timeout("power", self.power.read_power(), self.POWER_READ_TIMEOUT_SECONDS),
        )
        return SensorData(
            environmental=env_data,
            power=power_data,
            sensor_health={
                SensorType.ENVIRONMENTAL: self.environmental.status,
                SensorType.POWER: self.power.status,
            },
        )

    async def _do_read_all_sensors(self, bootstrap_mode: bool = False) -> SensorData:
        """Perform a real hardware read of all sensors (called under _read_lock).
        
        Args:
            bootstrap_mode: If True, use extended GPS timeout (2.0s) for heading bootstrap.
                           This allows GPS COG snaps to complete reliably during the
                           ~15s bootstrap drive, where GPS may transition between RTK states.
        """

        async def _read_with_timeout(name: str, coro: Any, timeout: float | None = None) -> Any:
            t = timeout if timeout is not None else self.SENSOR_READ_TIMEOUT_SECONDS
            try:
                return await asyncio.wait_for(coro, timeout=t)
            except TimeoutError:
                logger.warning(
                    "Timed out reading %s after %.1fs; continuing with partial telemetry",
                    name,
                    t,
                )
                return None

        # Read all sensors concurrently; power and GPS get custom timeouts.
        # GPS timeout is reduced from 2.5s to 1.5s to prevent watchdog starvation
        # when consecutive sensor timeouts occur. With 5000ms watchdog and 1250ms
        # heartbeat interval, a 2.5s GPS timeout leaves no margin for the next
        # heartbeat. Reduced to 1.5s ensures heartbeat window is maintained.
        # HOWEVER, during heading bootstrap (bootstrap_mode=True), GPS COG snaps need
        # more lenient conditions. Use 2.0s during bootstrap to allow RTK transitions
        # to settle and COG data to flow reliably to the snap logic.
        GPS_READ_TIMEOUT_SECONDS = 2.0 if bootstrap_mode else 1.5
        tasks = [
            _read_with_timeout("gps", self.gps.read_gps(), timeout=GPS_READ_TIMEOUT_SECONDS),
            _read_with_timeout("imu", self.imu.read_imu()),
            _read_with_timeout("tof", self.tof.read_tof_sensors()),
            _read_with_timeout("environmental", self.environmental.read_environmental()),
            _read_with_timeout(
                "power", self.power.read_power(), timeout=self.POWER_READ_TIMEOUT_SECONDS
            ),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        gps_data = results[0] if not isinstance(results[0], Exception) else None
        imu_data = results[1] if not isinstance(results[1], Exception) else None
        tof_data = results[2] if not isinstance(results[2], Exception) else (None, None)
        env_data = results[3] if not isinstance(results[3], Exception) else None
        power_data = results[4] if not isinstance(results[4], Exception) else None

        # Create sensor health status
        sensor_health = {
            SensorType.GPS: self.gps.status,
            SensorType.IMU: self.imu.status,
            SensorType.TOF_LEFT: self.tof.status,
            SensorType.TOF_RIGHT: self.tof.status,
            SensorType.ENVIRONMENTAL: self.environmental.status,
            SensorType.POWER: self.power.status,
        }

        sensor_data = SensorData(
            gps=gps_data,
            imu=imu_data,
            tof_left=tof_data[0] if tof_data else None,
            tof_right=tof_data[1] if tof_data else None,
            environmental=env_data,
            power=power_data,
            sensor_health=sensor_health,
        )

        if self.validation_enabled:
            self._validate_sensor_data(sensor_data)

        return sensor_data

    def _validate_sensor_data(self, sensor_data: SensorData):
        """Validate sensor data for consistency and reasonable values"""
        # GPS validation
        if sensor_data.gps:
            gps = sensor_data.gps
            if gps.latitude and (gps.latitude < -90 or gps.latitude > 90):
                logger.warning(f"Invalid GPS latitude: {gps.latitude}")
            if gps.longitude and (gps.longitude < -180 or gps.longitude > 180):
                logger.warning(f"Invalid GPS longitude: {gps.longitude}")
            if gps.accuracy and gps.accuracy > 50.0:
                logger.warning(f"Poor GPS accuracy: {gps.accuracy}m")

        # Power validation
        if sensor_data.power:
            power = sensor_data.power
            if power.battery_voltage and power.battery_voltage < 9.0:
                logger.warning(f"Low battery voltage: {power.battery_voltage}V")
            if power.battery_voltage and power.battery_voltage > 16.0:
                logger.warning(f"High battery voltage: {power.battery_voltage}V")

        # Environmental validation
        if sensor_data.environmental:
            env = sensor_data.environmental
            if env.temperature and (env.temperature < -40 or env.temperature > 80):
                logger.warning(f"Extreme temperature: {env.temperature}°C")

    async def get_sensor_status(self) -> dict[str, Any]:
        """Get status of all sensors"""
        imu_reading = getattr(self.imu, "last_reading", None)
        return {
            "initialized": self.initialized,
            "gps_status": self.gps.status,
            "gps_mode": self.gps.gps_mode,
            "imu_status": self.imu.status,
            "imu_calibration": getattr(imu_reading, "calibration_status", None),
            "tof_status": self.tof.status,
            "environmental_status": self.environmental.status,
            "power_status": self.power.status,
            "active_sensors": list(self.coordinator._active_sensors),
            "validation_enabled": self.validation_enabled,
        }

    async def shutdown(self):
        """Shutdown sensor manager"""
        logger.info("Shutting down sensor manager")
        await self.tof.shutdown()
        self.initialized = False

    async def generate_telemetry_streams(self) -> list[HardwareTelemetryStream]:
        """Generate HardwareTelemetryStream objects from current sensor readings"""
        if not self.initialized:
            logger.warning("Sensor manager not initialized")
            return []

        streams = []
        start_time = datetime.now(UTC)

        # Read all sensors
        sensor_data = await self.read_all_sensors()
        end_time = datetime.now(UTC)
        latency_ms = (end_time - start_time).total_seconds() * 1000

        # GPS stream
        if sensor_data.gps:
            gps_reading = sensor_data.gps
            gps_data = GPSData(
                latitude=gps_reading.latitude or 0.0,
                longitude=gps_reading.longitude or 0.0,
                altitude_m=gps_reading.altitude or 0.0,
                speed_mps=0.0,
                heading_deg=0.0,
                # Use true HDOP from the receiver if available; do NOT substitute
                # the estimated accuracy here. The UI displays both Accuracy and HDOP.
                hdop=gps_reading.hdop or 99.9,
                satellites=gps_reading.satellites or 0,
                fix_type=self._map_rtk_fix_type(gps_reading),
                rtk_status_message=self._get_rtk_status_message(gps_reading),
            )
            streams.append(
                HardwareTelemetryStream(
                    timestamp=start_time,
                    component_id=ComponentId.GPS,
                    value=f"{gps_data.latitude},{gps_data.longitude}",
                    status=self._map_sensor_status(sensor_data.sensor_health.get(SensorType.GPS)),
                    latency_ms=latency_ms,
                    gps_data=gps_data,
                )
            )

        # IMU stream
        if sensor_data.imu:
            imu_reading = sensor_data.imu
            # Map calibration_status string to numeric level (0-3).
            # "rvc_active" means the BNO085 is streaming in RVC mode;
            # the protocol does not expose calibration registers so we
            # report level 2 (operational, not fully verified).
            _CAL_LEVEL = {
                "fully_calibrated": 3,
                "calibrated": 3,
                "calibrating": 2,
                "partial": 1,
                "rvc_active": 2,  # legacy: BNO085 RVC mode fallback
                "uncalibrated": 0,
            }
            cal_sys = _CAL_LEVEL.get(imu_reading.calibration_status or "", 1)
            imu_data = IMUData(
                roll_deg=imu_reading.roll,
                pitch_deg=imu_reading.pitch,
                yaw_deg=imu_reading.yaw,
                accel_x=imu_reading.accel_x,
                accel_y=imu_reading.accel_y,
                accel_z=imu_reading.accel_z,
                gyro_x=imu_reading.gyro_x,
                gyro_y=imu_reading.gyro_y,
                gyro_z=imu_reading.gyro_z,
                calibration_sys=cal_sys,
            )
            streams.append(
                HardwareTelemetryStream(
                    timestamp=start_time,
                    component_id=ComponentId.IMU,
                    value=f"{imu_data.roll_deg:.2f},{imu_data.pitch_deg:.2f},{imu_data.yaw_deg:.2f}",
                    status=self._map_sensor_status(sensor_data.sensor_health.get(SensorType.IMU)),
                    latency_ms=latency_ms,
                    imu_data=imu_data,
                )
            )

        if sensor_data.power:
            power_reading = sensor_data.power
            bc = self._battery_config
            soc = voltage_to_soc(
                power_reading.battery_voltage,
                min_voltage=bc.min_voltage if bc else None,
                max_voltage=bc.max_voltage if bc else None,
                chemistry=bc.chemistry if bc else "lifepo4",
            )
            health_str = battery_health_label(power_reading.battery_voltage)
            health_status = (
                ComponentStatus.HEALTHY
                if health_str == "healthy"
                else ComponentStatus.WARNING
                if health_str == "warning"
                else ComponentStatus.FAULT
            )
            power_data = PowerData(
                battery_voltage=power_reading.battery_voltage,
                battery_current=power_reading.battery_current,
                battery_power=power_reading.battery_power,
                solar_voltage=power_reading.solar_voltage,
                solar_current=power_reading.solar_current,
                solar_power=power_reading.solar_power,
                battery_soc_percent=soc,
                battery_health=health_status,
            )
            streams.append(
                HardwareTelemetryStream(
                    timestamp=start_time,
                    component_id=ComponentId.POWER,
                    value=power_data.battery_voltage,
                    status=power_data.battery_health,
                    latency_ms=latency_ms,
                    power_data=power_data,
                )
            )

        # ToF left stream
        if sensor_data.tof_left:
            tof_left = sensor_data.tof_left
            tof_data = ToFData(
                distance_mm=int(tof_left.distance) if tof_left.distance is not None else None,
                range_status=tof_left.range_status or "no_target",
                signal_rate=tof_left.signal_strength or 0.0,
            )
            streams.append(
                HardwareTelemetryStream(
                    timestamp=start_time,
                    component_id=ComponentId.TOF_LEFT,
                    value=tof_data.distance_mm if tof_data.distance_mm is not None else 0,
                    status=self._map_sensor_status(
                        sensor_data.sensor_health.get(SensorType.TOF_LEFT)
                    ),
                    latency_ms=latency_ms,
                    tof_data=tof_data,
                )
            )

        # ToF right stream
        if sensor_data.tof_right:
            tof_right = sensor_data.tof_right
            tof_data = ToFData(
                distance_mm=int(tof_right.distance) if tof_right.distance is not None else None,
                range_status=tof_right.range_status or "no_target",
                signal_rate=tof_right.signal_strength or 0.0,
            )
            streams.append(
                HardwareTelemetryStream(
                    timestamp=start_time,
                    component_id=ComponentId.TOF_RIGHT,
                    value=tof_data.distance_mm if tof_data.distance_mm is not None else 0,
                    status=self._map_sensor_status(
                        sensor_data.sensor_health.get(SensorType.TOF_RIGHT)
                    ),
                    latency_ms=latency_ms,
                    tof_data=tof_data,
                )
            )

        return streams

    def _map_rtk_fix_type(self, gps_reading: GpsReading) -> RtkFixType:
        """Map GPS reading to RTK fix type"""
        if hasattr(gps_reading, "rtk_status"):
            status = gps_reading.rtk_status.upper() if gps_reading.rtk_status else ""
            if "FIXED" in status or "RTK_FIXED" in status:
                return RtkFixType.RTK_FIXED
            elif "FLOAT" in status or "RTK_FLOAT" in status:
                return RtkFixType.RTK_FLOAT
            elif "DGPS" in status:
                return RtkFixType.DGPS_FIX

        # Fallback to satellites count
        if gps_reading.satellites and gps_reading.satellites >= 6:
            return RtkFixType.GPS_FIX
        return RtkFixType.NO_FIX

    def _get_rtk_status_message(self, gps_reading: GpsReading) -> str:
        """Generate human-readable RTK status message"""
        fix_type = self._map_rtk_fix_type(gps_reading)
        satellites = gps_reading.satellites or 0
        accuracy = gps_reading.accuracy or 99.9

        if fix_type == RtkFixType.RTK_FIXED:
            return f"RTK Fixed - {satellites} satellites, {accuracy:.1f}m accuracy"
        elif fix_type == RtkFixType.RTK_FLOAT:
            return f"RTK Float - {satellites} satellites, {accuracy:.1f}m accuracy"
        elif fix_type == RtkFixType.GPS_FIX:
            return f"GPS Fix - {satellites} satellites, {accuracy:.1f}m accuracy"
        elif fix_type == RtkFixType.DGPS_FIX:
            return f"DGPS Fix - {satellites} satellites, {accuracy:.1f}m accuracy"
        else:
            return f"No GPS fix - {satellites} satellites visible"

    def _map_sensor_status(self, status: SensorStatus | None) -> ComponentStatus:
        """Map SensorStatus to ComponentStatus"""
        if status == SensorStatus.ONLINE:
            return ComponentStatus.HEALTHY
        elif status == SensorStatus.ERROR:
            return ComponentStatus.FAULT
        else:
            return ComponentStatus.WARNING

    def _estimate_battery_soc(
        self,
        voltage: float | None,
        battery_current_a: float | None = None,
        solar_current_a: float | None = None,
    ) -> float | None:
        """Estimate SOC using the shared battery utility with tail-current heuristic."""
        bc = self._battery_config
        return voltage_current_to_soc(
            voltage,
            battery_current_a=battery_current_a,
            solar_current_a=solar_current_a,
            min_voltage=bc.min_voltage if bc else None,
            max_voltage=bc.max_voltage if bc else None,
            chemistry=bc.chemistry if bc else "lifepo4",
        )
