"""
SensorManager service for LawnBerry Pi v2
Hardware sensor interfaces with I2C/UART coordination and validation
"""

import asyncio
import logging
import math
from datetime import datetime, timezone
from typing import Dict, Optional, List, Any
from contextlib import asynccontextmanager

from ..models import (
    SensorData, GpsReading, ImuReading, TofReading, EnvironmentalReading, 
    PowerReading, SensorType, SensorStatus, GpsMode,
    HardwareTelemetryStream, ComponentId, ComponentStatus, RtkFixType,
    GPSData, IMUData, PowerData, ToFData
)

logger = logging.getLogger(__name__)


class SensorCoordinator:
    """Coordinates access to shared I2C/UART resources"""
    
    def __init__(self):
        self._i2c_lock = asyncio.Lock()
        self._uart_locks = {
            "UART0": asyncio.Lock(),
            "UART1": asyncio.Lock(), 
            "UART4": asyncio.Lock()
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
    
    def __init__(self, gps_mode: GpsMode, coordinator: SensorCoordinator):
        self.gps_mode = gps_mode
        self.coordinator = coordinator
        self.last_reading: Optional[GpsReading] = None
        self.status = SensorStatus.OFFLINE
        # Concrete driver (lazy, SIM-safe)
        try:
            from ..drivers.sensors.gps_driver import GPSDriver  # type: ignore
            self._driver = GPSDriver({"mode": gps_mode})
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
    
    async def read_gps(self) -> Optional[GpsReading]:
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
                    mode=self.gps_mode
                )
            
            self.last_reading = reading
            return reading
            
        except Exception as e:
            logger.error(f"GPS reading failed: {e}")
            self.status = SensorStatus.ERROR
            return None


class IMUSensorInterface:
    """BNO085 IMU sensor interface"""
    
    def __init__(self, coordinator: SensorCoordinator):
        self.coordinator = coordinator
        self.last_reading: Optional[ImuReading] = None
        self.status = SensorStatus.OFFLINE
        try:
            from ..drivers.sensors.bno085_driver import BNO085Driver  # type: ignore
            self._driver = BNO085Driver({})
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
    
    async def read_imu(self) -> Optional[ImuReading]:
        """Read IMU data"""
        if self.status != SensorStatus.ONLINE:
            return None
        
        try:
            if getattr(self, "_driver", None) is not None:
                o = await self._driver.read_orientation()
                if o is not None:
                    reading = ImuReading(
                        roll=o.get("roll"),
                        pitch=o.get("pitch"),
                        yaw=o.get("yaw"),
                        accel_z=9.8,  # minimal gravity placeholder
                        calibration_status=o.get("calibration_status") or "unknown"
                    )
                else:
                    reading = self.last_reading
            else:
                reading = ImuReading(roll=0.0, pitch=0.0, yaw=0.0, calibration_status="unknown")

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
        self.left_reading: Optional[TofReading] = None
        self.right_reading: Optional[TofReading] = None
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
    
    async def read_tof_sensors(self) -> tuple[Optional[TofReading], Optional[TofReading]]:
        """Read both ToF sensors"""
        if self.status != SensorStatus.ONLINE:
            return None, None
        
        try:
            if self._left is not None and self._right is not None:
                # Coordinate I2C access across sensors
                async with self.coordinator.acquire_i2c("vl53l0x_pair"):
                    dl = await self._left.read_distance_mm()
                    dr = await self._right.read_distance_mm()
                left_reading = TofReading(
                    distance=float(dl) if dl is not None else None,
                    signal_strength=None,
                    range_status="valid" if dl else "unknown",
                    sensor_side="left",
                )
                right_reading = TofReading(
                    distance=float(dr) if dr is not None else None,
                    signal_strength=None,
                    range_status="valid" if dr else "unknown",
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
        self.last_reading: Optional[EnvironmentalReading] = None
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
    
    async def read_environmental(self) -> Optional[EnvironmentalReading]:
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
        self.last_reading: Optional[PowerReading] = None
        self.status = SensorStatus.OFFLINE
        self._driver_config = driver_config or {}
        self._ina_driver = None
        self._victron_driver = None
        self._prefer_battery = False
        self._prefer_solar = False
        self._prefer_load = False

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
                logger.error("Failed to initialize power driver %s: %s", driver.__class__.__name__, exc)

        self.status = SensorStatus.ONLINE if any_success else SensorStatus.ERROR
        return any_success
    
    async def read_power(self) -> Optional[PowerReading]:
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
                    if reading.battery_power is None and self.last_reading.battery_power is not None:
                        reading.battery_power = self.last_reading.battery_power
                    if reading.solar_power is None and self.last_reading.solar_power is not None:
                        reading.solar_power = self.last_reading.solar_power
            
            self.last_reading = reading
            return reading
                
        except Exception as e:
            logger.error(f"Power reading failed: {e}")
            self.status = SensorStatus.ERROR
            return None

    @staticmethod
    def _extract_ina_config(config: dict[str, Any]) -> Optional[dict[str, Any]]:
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
    def _extract_victron_config(config: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not config:
            return None
        candidate = config.get("victron") or config.get("victron_vedirect") or config.get("victron_config")
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
    def _pick(cls, *values: Any, min_abs: float | None = None) -> Optional[float]:
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
        ina: Optional[dict[str, Any]],
        victron: Optional[dict[str, Any]],
        *,
        prefer_battery: bool = False,
        prefer_solar: bool = False,
        prefer_load: bool = False,
    ) -> Optional[PowerReading]:
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
        victron_solar_current = (
            victron.get("solar_current_amps") if victron else None
        )
        ina_solar_current = (
            ina.get("solar_current_amps") if ina else None
        )
        solar_current_sources: list[Any] = []
        # Prefer Victron for PV-side semantics when present
        solar_current_sources.append(victron_solar_current)
        solar_current_sources.append(ina_solar_current)
        solar_current = cls._pick(*solar_current_sources)

        victron_solar_power = (
            victron.get("solar_power_w") if victron else None
        ) if victron else None
        if victron_solar_power is None and victron:
            victron_solar_power = victron.get("solar_power")
        ina_solar_power = (
            ina.get("solar_power_w") if ina else None
        )
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
                    (victron is not None and victron.get("solar_voltage") is not None and victron_solar_current is not None)
                    # Or both from INA
                    or (victron is None and ina is not None and ina.get("solar_voltage") is not None and ina_solar_current is not None)
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
            # Derive voltage from power/current only when both came from Victron or both from INA
            derived = None
            try:
                if victron_solar_power is not None and victron_solar_current is not None:
                    derived = float(victron_solar_power) / float(victron_solar_current)
                elif ina_solar_power is not None and ina_solar_current is not None and abs(float(ina_solar_current)) > 1e-6:
                    derived = float(ina_solar_power) / float(ina_solar_current)
            except Exception:
                derived = None
            if derived is not None:
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
    
    def __init__(
        self,
        gps_mode: GpsMode = GpsMode.NEO8M_UART,
        tof_config: dict | None = None,
        power_config: dict | None = None,
    ):
        self.coordinator = SensorCoordinator()
        
        # Initialize sensor interfaces
        self.gps = GPSSensorInterface(gps_mode, self.coordinator)
        self.imu = IMUSensorInterface(self.coordinator)
        self.tof = ToFSensorInterface(self.coordinator, tof_config=tof_config)
        self.environmental = EnvironmentalSensorInterface(self.coordinator)
        self.power = PowerSensorInterface(self.coordinator, driver_config=power_config)
        
        self.initialized = False
        self.validation_enabled = True
        
    async def initialize(self) -> bool:
        """Initialize all sensors"""
        logger.info("Initializing sensor manager")
        
        results = await asyncio.gather(
            self.gps.initialize(),
            self.imu.initialize(),
            self.tof.initialize(),
            self.environmental.initialize(),
            self.power.initialize(),
            return_exceptions=True
        )
        
        success_count = sum(1 for result in results if result is True)
        total_sensors = len(results)
        
        logger.info(f"Sensor initialization: {success_count}/{total_sensors} successful")
        
        # Consider initialized if at least core sensors are working
        self.initialized = success_count >= 3
        return self.initialized
    
    async def read_all_sensors(self) -> SensorData:
        """Read data from all sensors"""
        if not self.initialized:
            logger.warning("Sensor manager not initialized")
            return SensorData()
        
        # Read all sensors concurrently where possible
        tasks = [
            self.gps.read_gps(),
            self.imu.read_imu(),
            self.tof.read_tof_sensors(),
            self.environmental.read_environmental(),
            self.power.read_power()
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
            SensorType.POWER: self.power.status
        }
        
        sensor_data = SensorData(
            gps=gps_data,
            imu=imu_data,
            tof_left=tof_data[0] if tof_data else None,
            tof_right=tof_data[1] if tof_data else None,
            environmental=env_data,
            power=power_data,
            sensor_health=sensor_health
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
    
    async def get_sensor_status(self) -> Dict[str, Any]:
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
            "validation_enabled": self.validation_enabled
        }
    
    async def shutdown(self):
        """Shutdown sensor manager"""
        logger.info("Shutting down sensor manager")
        # Sensor shutdown logic would go here
        self.initialized = False
    
    async def generate_telemetry_streams(self) -> List[HardwareTelemetryStream]:
        """Generate HardwareTelemetryStream objects from current sensor readings"""
        if not self.initialized:
            logger.warning("Sensor manager not initialized")
            return []
        
        streams = []
        start_time = datetime.now(timezone.utc)
        
        # Read all sensors
        sensor_data = await self.read_all_sensors()
        end_time = datetime.now(timezone.utc)
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
                hdop=gps_reading.accuracy or 99.9,
                satellites=gps_reading.satellites or 0,
                fix_type=self._map_rtk_fix_type(gps_reading),
                rtk_status_message=self._get_rtk_status_message(gps_reading)
            )
            streams.append(HardwareTelemetryStream(
                timestamp=start_time,
                component_id=ComponentId.GPS,
                value=f"{gps_data.latitude},{gps_data.longitude}",
                status=self._map_sensor_status(sensor_data.sensor_health.get(SensorType.GPS)),
                latency_ms=latency_ms,
                gps_data=gps_data
            ))
        
        # IMU stream
        if sensor_data.imu:
            imu_reading = sensor_data.imu
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
                calibration_sys=3 if imu_reading.calibration_status == "fully_calibrated" else 1
            )
            streams.append(HardwareTelemetryStream(
                timestamp=start_time,
                component_id=ComponentId.IMU,
                value=f"{imu_data.roll_deg:.2f},{imu_data.pitch_deg:.2f},{imu_data.yaw_deg:.2f}",
                status=self._map_sensor_status(sensor_data.sensor_health.get(SensorType.IMU)),
                latency_ms=latency_ms,
                imu_data=imu_data
            ))
        
        # Power stream
        if sensor_data.power:
            power_reading = sensor_data.power
            power_data = PowerData(
                battery_voltage=power_reading.battery_voltage,
                battery_current=power_reading.battery_current,
                battery_power=power_reading.battery_power,
                solar_voltage=power_reading.solar_voltage,
                solar_current=power_reading.solar_current,
                solar_power=power_reading.solar_power,
                battery_soc_percent=self._estimate_battery_soc(power_reading.battery_voltage),
                battery_health=ComponentStatus.HEALTHY if power_reading.battery_voltage > 11.0 else ComponentStatus.WARNING
            )
            streams.append(HardwareTelemetryStream(
                timestamp=start_time,
                component_id=ComponentId.POWER,
                value=power_data.battery_voltage,
                status=power_data.battery_health,
                latency_ms=latency_ms,
                power_data=power_data
            ))
        
        # ToF left stream
        if sensor_data.tof_left:
            tof_left = sensor_data.tof_left
            tof_data = ToFData(
                distance_mm=int(tof_left.distance),
                range_status=tof_left.range_status,
                signal_rate=tof_left.signal_strength
            )
            streams.append(HardwareTelemetryStream(
                timestamp=start_time,
                component_id=ComponentId.TOF_LEFT,
                value=tof_data.distance_mm,
                status=self._map_sensor_status(sensor_data.sensor_health.get(SensorType.TOF_LEFT)),
                latency_ms=latency_ms,
                tof_data=tof_data
            ))
        
        # ToF right stream
        if sensor_data.tof_right:
            tof_right = sensor_data.tof_right
            tof_data = ToFData(
                distance_mm=int(tof_right.distance),
                range_status=tof_right.range_status,
                signal_rate=tof_right.signal_strength
            )
            streams.append(HardwareTelemetryStream(
                timestamp=start_time,
                component_id=ComponentId.TOF_RIGHT,
                value=tof_data.distance_mm,
                status=self._map_sensor_status(sensor_data.sensor_health.get(SensorType.TOF_RIGHT)),
                latency_ms=latency_ms,
                tof_data=tof_data
            ))
        
        return streams
    
    def _map_rtk_fix_type(self, gps_reading: GpsReading) -> RtkFixType:
        """Map GPS reading to RTK fix type"""
        if hasattr(gps_reading, 'rtk_status'):
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
    
    def _map_sensor_status(self, status: Optional[SensorStatus]) -> ComponentStatus:
        """Map SensorStatus to ComponentStatus"""
        if status == SensorStatus.ONLINE:
            return ComponentStatus.HEALTHY
        elif status == SensorStatus.ERROR:
            return ComponentStatus.FAULT
        else:
            return ComponentStatus.WARNING
    
    def _estimate_battery_soc(self, voltage: Optional[float]) -> Optional[float]:
        """Estimate battery state-of-charge using a clamped linear model."""
        if voltage is None:
            return None
        try:
            value = float(voltage)
        except (TypeError, ValueError):
            return None

        min_v = 11.5
        max_v = 13.0
        if value <= min_v:
            return 0.0
        if value >= max_v:
            return 100.0

        ratio = (value - min_v) / (max_v - min_v)
        return round(ratio * 100.0, 1)