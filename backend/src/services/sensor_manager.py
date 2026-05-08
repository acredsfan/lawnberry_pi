"""
SensorManager service for LawnBerry Pi v2
Hardware sensor interfaces with I2C/UART coordination and validation
"""

import asyncio
import logging
import math
import time
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
from ..utils.battery import battery_health_label, voltage_to_soc

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
                    reading = self.last_reading
            else:
                # Placeholder data
                reading = GpsReading(
                    latitude=40.7128,
                    longitude=-74.0060,
                    altitude=10.0,
                    accuracy=3.0,
                    satellites=8,
                    mode=self.gps_mode,
                )

            self.last_reading = reading
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
                    )
                else:
                    reading = self.last_reading
            else:
                # Driver unavailable but interface is ONLINE -- report
                # "uncalibrated" rather than "unknown".
                reading = ImuReading(
                    roll=0.0, pitch=0.0, yaw=0.0, calibration_status="uncalibrated"
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
        try:
            from ..drivers.sensors.vl53l0x_driver import VL53L0XDriver  # type: ignore

            cfg = tof_config or {}
            left_cfg = {
                "bus": cfg.get("bus"),
                "address": cfg.get("left_address"),
                "shutdown_gpio": cfg.get("left_shutdown_gpio"),
                "ranging_mode": cfg.get("ranging_mode"),
            }
            right_cfg = {
                "bus": cfg.get("bus"),
                "address": cfg.get("right_address"),
                "shutdown_gpio": cfg.get("right_shutdown_gpio"),
                "ranging_mode": cfg.get("ranging_mode"),
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
                await self._left.initialize()
                await self._right.initialize()
                await self._left.start()
                await self._right.start()
                self.status = SensorStatus.ONLINE
                return True
            else:
                self.status = SensorStatus.ONLINE
                return True

        except Exception as e:
            logger.error(f"Failed to initialize ToF sensors: {e}")
            self.status = SensorStatus.ERROR
            return False

    async def read_tof_sensors(self) -> tuple[TofReading | None, TofReading | None]:
        """Read both ToF sensors"""
        if self.status != SensorStatus.ONLINE:
            return None, None

        try:
            if self._left is not None and self._right is not None:
                # Coordinate I2C access across sensors
                async with self.coordinator.acquire_i2c("vl53l0x_pair"):
                    dl = await self._left.read_distance_mm()
                    dr = await self._right.read_distance_mm()
                # Defense-in-depth: filter VL53L0X out-of-range sentinel (≥ 8000 mm)
                # in case the driver layer didn't catch it (e.g. a library wrapping the raw value).
                if isinstance(dl, int) and dl >= 8000:
                    dl = None
                if isinstance(dr, int) and dr >= 8000:
                    dr = None
                left_reading = TofReading(
                    distance=float(dl) if dl is not None else None,
                    signal_strength=None,
                    range_status="valid" if dl is not None else "no_target",
                    sensor_side="left",
                )
                right_reading = TofReading(
                    distance=float(dr) if dr is not None else None,
                    signal_strength=None,
                    range_status="valid" if dr is not None else "no_target",
                    sensor_side="right",
                )
                self.left_reading = left_reading
                self.right_reading = right_reading
                return left_reading, right_reading
            else:
                return self.left_reading, self.right_reading

        except Exception as e:
            logger.error(f"ToF reading failed: {e}")
            self.status = SensorStatus.ERROR
            return None, None


class EnvironmentalSensorInterface:
    """BME280 environmental sensor interface"""

    def __init__(self, coordinator: SensorCoordinator):
        self.coordinator = coordinator
        self.last_reading: EnvironmentalReading | None = None
        self.status = SensorStatus.OFFLINE
        try:
            from ..drivers.sensors.bme280_driver import BME280Driver  # type: ignore

            self._driver = BME280Driver({})
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
            ina_payload: dict[str, Any] | None = None
            victron_payload: dict[str, Any] | None = None

            if self._ina_driver is not None:
                try:
                    ina_payload = await self._ina_driver.read_power()
                except Exception as exc:  # pragma: no cover - hardware dependent
                    logger.error("INA3221 read failed: %s", exc)

            if self._victron_driver is not None:
                try:
                    victron_payload = await self._victron_driver.read_power()
                except Exception as exc:  # pragma: no cover - optional hardware
                    logger.error("Victron VE.Direct read failed: %s", exc)

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
                if isinstance(self.last_reading, PowerReading):
                    # Carry forward stable values when current sample omits them.
                    if reading.battery_voltage is None:
                        reading.battery_voltage = self.last_reading.battery_voltage
                    if reading.battery_current is None:
                        reading.battery_current = self.last_reading.battery_current
                    if reading.solar_voltage is None:
                        reading.solar_voltage = self.last_reading.solar_voltage
                    if reading.solar_current is None:
                        reading.solar_current = self.last_reading.solar_current
                    if (
                        reading.battery_power is None
                        and self.last_reading.battery_power is not None
                    ):
                        reading.battery_power = self.last_reading.battery_power
                    if reading.solar_power is None and self.last_reading.solar_power is not None:
                        reading.solar_power = self.last_reading.solar_power

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

        battery_voltage = cls._pick(
            victron.get("battery_voltage") if victron else None,
            ina.get("battery_voltage") if ina else None,
            min_abs=0.05,
        )
        battery_current_sources: list[Any] = []
        if prefer_battery:
            battery_current_sources.extend(
                [
                    victron.get("battery_current_amps") if victron else None,
                    victron.get("battery_current") if victron else None,
                ]
            )
        battery_current_sources.extend(
            [
                ina.get("battery_current") if ina else None,
                ina.get("battery_current_amps") if ina else None,
            ]
        )
        if not prefer_battery:
            battery_current_sources.extend(
                [
                    victron.get("battery_current_amps") if victron else None,
                    victron.get("battery_current") if victron else None,
                ]
            )
        battery_current = cls._pick(*battery_current_sources)
        solar_voltage = cls._pick(
            victron.get("solar_voltage") if victron else None,
            ina.get("solar_voltage") if ina else None,
            min_abs=0.05,
        )
        # Capture per-source solar current/power to avoid cross-source derivations
        victron_solar_current = victron.get("solar_current_amps") if victron else None
        ina_solar_current = ina.get("solar_current_amps") if ina else None
        solar_current_sources: list[Any] = []
        # Prefer Victron for PV-side semantics when present
        solar_current_sources.append(victron_solar_current)
        solar_current_sources.append(ina_solar_current)
        solar_current = cls._pick(*solar_current_sources)

        victron_solar_power = (
            (victron.get("solar_power_w") if victron else None) if victron else None
        )
        if victron_solar_power is None and victron:
            victron_solar_power = victron.get("solar_power")
        ina_solar_power = ina.get("solar_power_w") if ina else None
        solar_power_sources: list[Any] = []
        # Prefer Victron for PV-side power as well
        solar_power_sources.append(victron_solar_power)
        solar_power_sources.append(ina_solar_power)
        solar_power = cls._pick(*solar_power_sources)

        battery_power_sources: list[Any] = []
        if prefer_battery:
            battery_power_sources.extend(
                [
                    victron.get("battery_power_w") if victron else None,
                    victron.get("battery_power") if victron else None,
                ]
            )
        battery_power_sources.append(ina.get("battery_power_w") if ina else None)
        if not prefer_battery:
            battery_power_sources.extend(
                [
                    victron.get("battery_power_w") if victron else None,
                    victron.get("battery_power") if victron else None,
                ]
            )
        battery_power = cls._pick(*battery_power_sources)

        if battery_power is None and battery_voltage is not None and battery_current is not None:
            battery_power = round(battery_voltage * battery_current, 3)
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

        if (
            solar_voltage is None
            and solar_power is not None
            and solar_current is not None
            and abs(solar_current) > 1e-6
        ):
            # Derive voltage from power/current only when both came from Victron or both from INA.
            # Skip INA-based derivation when INA bus voltage is 0.0 — that indicates a bad/missing
            # bus-voltage reference wire, and INA solar_power_w would also be 0.0 (0V × current),
            # which would produce a spurious 0.0V result.
            ina_solar_v_raw = ina.get("solar_voltage") if ina else None
            ina_bus_valid = ina_solar_v_raw is not None and abs(float(ina_solar_v_raw)) >= 0.05
            derived = None
            try:
                if victron_solar_power is not None and victron_solar_current is not None:
                    derived = float(victron_solar_power) / float(victron_solar_current)
                elif (
                    ina_bus_valid
                    and ina_solar_power is not None
                    and ina_solar_current is not None
                    and abs(float(ina_solar_current)) > 1e-6
                ):
                    derived = float(ina_solar_power) / float(ina_solar_current)
            except Exception:
                derived = None
            # Guard against zero or near-zero derived values that signal bad source data
            if derived is not None and abs(derived) >= 0.05:
                solar_voltage = round(derived, 3)

        load_current_sources: list[Any] = []
        if prefer_load:
            load_current_sources.append(victron.get("load_current_amps") if victron else None)
        load_current_sources.append(ina.get("load_current_amps") if ina else None)
        if not prefer_load:
            load_current_sources.append(victron.get("load_current_amps") if victron else None)
        load_current = cls._pick(*load_current_sources)

        # Daily solar yield (Wh) when available from Victron
        solar_yield_today_wh = None
        try:
            if victron and isinstance(victron, dict):
                solar_yield_today_wh = cls._pick(victron.get("solar_yield_today_wh"))
        except Exception:
            solar_yield_today_wh = None

        reading = PowerReading(
            battery_voltage=battery_voltage,
            battery_current=battery_current,
            battery_power=battery_power,
            solar_voltage=solar_voltage,
            solar_current=solar_current,
            solar_power=solar_power,
            solar_yield_today_wh=solar_yield_today_wh,
            load_current=load_current,
        )

        return reading


class SensorManager:
    """Main sensor manager coordinating all sensor interfaces"""

    # BNO085 uses SHTP Game Rotation Vector (1.0s per-read); GPS F9P_USB is fast.
    # 2.5 s is ample for all non-BLE sensors.
    SENSOR_READ_TIMEOUT_SECONDS = 2.5
    # Inner _read_victron_cli_frame deadline is 8.0 s; subprocess cleanup adds ≤2 s.
    # 11 s covers the realistic worst case with 1 s of margin.
    POWER_READ_TIMEOUT_SECONDS = 11.0

    def __init__(
        self,
        gps_mode: GpsMode = GpsMode.F9P_USB,
        tof_config: dict | None = None,
        power_config: dict | None = None,
        battery_config=None,  # Optional[BatteryConfig]
        imu_config: dict | None = None,
        gps_usb_device: str | None = None,
    ):
        self.coordinator = SensorCoordinator()

        # Battery spec — used for SOC estimation and health classification
        self._battery_config = battery_config  # BatteryConfig | None

        # Initialize sensor interfaces
        self.gps = GPSSensorInterface(gps_mode, self.coordinator, usb_device=gps_usb_device)
        self.imu = IMUSensorInterface(self.coordinator, imu_config=imu_config)
        self.tof = ToFSensorInterface(self.coordinator, tof_config=tof_config)
        self.environmental = EnvironmentalSensorInterface(self.coordinator)
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

    async def read_all_sensors(self) -> SensorData:
        """Read data from all sensors.

        Only one hardware read is allowed in-flight at a time.  Concurrent
        callers wait on ``_read_lock`` then receive the cached result if it is
        still fresh (< ``_CACHE_TTL_S`` seconds old).  This prevents thread-pool
        exhaustion when the BNO085 or another blocking driver is slow.
        """
        if not self.initialized:
            logger.warning("Sensor manager not initialized")
            return SensorData()

        async with self._read_lock:
            now = time.monotonic()
            if self._read_cache is not None and (now - self._read_cache_ts) < self._CACHE_TTL_S:
                return self._read_cache

            result = await self._do_read_all_sensors()
            self._read_cache = result
            self._read_cache_ts = time.monotonic()
            return result

    async def _do_read_all_sensors(self) -> SensorData:
        """Perform a real hardware read of all sensors (called under _read_lock)."""

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

        # Read all sensors concurrently; power gets a longer budget for BLE
        tasks = [
            _read_with_timeout("gps", self.gps.read_gps()),
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
        return {
            "initialized": self.initialized,
            "gps_status": self.gps.status,
            "gps_mode": self.gps.gps_mode,
            "imu_status": self.imu.status,
            "tof_status": self.tof.status,
            "environmental_status": self.environmental.status,
            "power_status": self.power.status,
            "active_sensors": list(self.coordinator._active_sensors),
            "validation_enabled": self.validation_enabled,
        }

    async def shutdown(self):
        """Shutdown sensor manager"""
        logger.info("Shutting down sensor manager")
        # Sensor shutdown logic would go here
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

    def _estimate_battery_soc(self, voltage: float | None) -> float | None:
        """Estimate SOC using the shared battery utility (LiFePO4 OCV table by default)."""
        bc = self._battery_config
        return voltage_to_soc(
            voltage,
            min_voltage=bc.min_voltage if bc else None,
            max_voltage=bc.max_voltage if bc else None,
            chemistry=bc.chemistry if bc else "lifepo4",
        )
