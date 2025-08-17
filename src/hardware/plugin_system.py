"""Plugin system for modular hardware components"""

import asyncio
import importlib
import inspect
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from .data_structures import DeviceHealth, SensorReading
from .exceptions import DeviceNotFoundError, HardwareError


@dataclass
class PluginConfig:
    """Configuration for hardware plugin"""

    name: str
    enabled: bool = True
    parameters: Dict[str, Any] = None

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


class HardwarePlugin(ABC):
    """Abstract base class for hardware plugins"""

    def __init__(self, config: PluginConfig, managers: Dict[str, Any]):
        self.config = config
        self.managers = managers
        self.logger = logging.getLogger(f"{__name__}.{config.name}")
        self.health = DeviceHealth(config.name)
        self._initialized = False
        self._lock = asyncio.Lock()

    @property
    @abstractmethod
    def plugin_type(self) -> str:
        """Plugin type identifier (e.g., 'i2c_sensor', 'serial_device')"""
        pass

    @property
    @abstractmethod
    def required_managers(self) -> List[str]:
        """List of required manager types (e.g., ['i2c', 'gpio'])"""
        pass

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the hardware component"""
        pass

    async def set_rc_mode(self, mode: str) -> bool:
        """Set RC control mode"""
        if not self._initialized:
            if not await self.initialize():
                return False

        valid_modes = ["emergency", "manual", "assisted", "training"]
        if mode not in valid_modes:
            self.logger.error(f"Invalid RC mode: {mode}")
            return False

        try:
            serial_manager = self.managers["serial"]
            success = await serial_manager.write_command("robohat", f"rc_mode={mode}")

            if success:
                self.rc_mode = mode
                await self.health.record_success()
                self.logger.info(f"RC mode set to: {mode}")
            else:
                await self.health.record_failure()

            return success

        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to set RC mode: {e}")
            return False

    async def enable_rc_control(self, enabled: bool = True) -> bool:
        """Enable or disable RC control"""
        if not self._initialized:
            if not await self.initialize():
                return False

        try:
            serial_manager = self.managers["serial"]
            command = "rc=enable" if enabled else "rc=disable"
            success = await serial_manager.write_command("robohat", command)

            if success:
                self.rc_enabled = enabled
                await self.health.record_success()
                self.logger.info(f"RC control {'enabled' if enabled else 'disabled'}")
            else:
                await self.health.record_failure()

            return success

        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to set RC control state: {e}")
            return False

    async def set_blade_control(self, enabled: bool) -> bool:
        """Control blade motor"""
        if not self._initialized:
            if not await self.initialize():
                return False

        try:
            serial_manager = self.managers["serial"]
            command = "blade=on" if enabled else "blade=off"
            success = await serial_manager.write_command("robohat", command)

            if success:
                self.blade_enabled = enabled
                await self.health.record_success()
                self.logger.info(f"Blade {'enabled' if enabled else 'disabled'}")
            else:
                await self.health.record_failure()

            return success

        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to control blade: {e}")
            return False

    async def get_rc_status(self) -> Optional[Dict[str, Any]]:
        """Get comprehensive RC control status"""
        if not self._initialized:
            if not await self.initialize():
                return None

        try:
            serial_manager = self.managers["serial"]
            success = await serial_manager.write_command("robohat", "get_rc_status")

            if success:
                # Read status response
                line = await serial_manager.read_line("robohat", timeout=1.0)
                if line and line.startswith("[STATUS]"):
                    # Parse status response
                    import ast

                    status_str = line.replace("[STATUS] ", "")
                    status = ast.literal_eval(status_str)

                    await self.health.record_success()
                    return status

            await self.health.record_failure()
            return None

        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to get RC status: {e}")
            return None

    async def configure_rc_channel(self, channel: int, function: str) -> bool:
        """Configure RC channel function mapping"""
        if not self._initialized:
            if not await self.initialize():
                return False

        try:
            serial_manager = self.managers["serial"]
            command = f"rc_config={channel},{function}"
            success = await serial_manager.write_command("robohat", command)

            if success:
                if channel in self.channel_config:
                    self.channel_config[channel]["function"] = function
                await self.health.record_success()
                self.logger.info(f"RC channel {channel} configured for {function}")
            else:
                await self.health.record_failure()

            return success

        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to configure RC channel: {e}")
            return False

    @abstractmethod
    async def read_data(self) -> Optional[SensorReading]:
        """Read data from the hardware component"""
        pass

    async def shutdown(self):
        """Shutdown the hardware component"""
        self._initialized = False
        self.logger.info(f"Plugin {self.config.name} shut down")

    async def health_check(self) -> bool:
        """Perform health check on the component"""
        return self.health.is_healthy

    @property
    def is_initialized(self) -> bool:
        return self._initialized


class ToFSensorPlugin(HardwarePlugin):
    """VL53L0X Time-of-Flight sensor plugin using Adafruit CircuitPython library"""

    @property
    def plugin_type(self) -> str:
        return "i2c_sensor"

    @property
    def required_managers(self) -> List[str]:
        return ["i2c", "gpio"]

    async def initialize(self) -> bool:
        """Initialize ToF sensor using proper VL53L0X library"""
        async with self._lock:
            if self._initialized:
                return True

            try:
                # Import ToF manager
                from .tof_manager import ToFSensorConfig, ToFSensorManager

                # Get configuration parameters
                sensor_name = self.config.name
                shutdown_pin = self.config.parameters.get("shutdown_pin")
                interrupt_pin = self.config.parameters.get("interrupt_pin")
                target_address = self.config.parameters.get("i2c_address", 0x29)

                if not shutdown_pin:
                    raise HardwareError(
                        f"ToF sensor {sensor_name} missing shutdown_pin configuration"
                    )

                # Create sensor configuration
                sensor_config = ToFSensorConfig(
                    name=sensor_name,
                    shutdown_pin=shutdown_pin,
                    interrupt_pin=interrupt_pin,
                    target_address=target_address,
                )

                # Create or get shared ToF manager instance
                if (
                    not hasattr(self.__class__, "_shared_tof_manager")
                    or self.__class__._shared_tof_manager is None
                ):
                    # Pass shared GPIO manager from system managers so ToF manager
                    # uses centralized GPIO claims and avoids double-claiming pins.
                    gpio_mgr = self.managers.get("gpio")
                    try:
                        self.__class__._shared_tof_manager = ToFSensorManager(gpio_manager=gpio_mgr)
                    except Exception:
                        # Fallback to default constructor if signature differs
                        self.__class__._shared_tof_manager = ToFSensorManager()

                tof_manager = self.__class__._shared_tof_manager

                # Initialize manager if not already done
                if not tof_manager._initialized:
                    # Get all ToF sensor configs from hardware interface
                    all_configs = self._get_all_tof_configs()
                    success = await tof_manager.initialize(all_configs)
                    if not success:
                        raise HardwareError("Failed to initialize ToF manager")

                # Store reference to manager and sensor name
                self._tof_manager = tof_manager
                self._sensor_name = sensor_name

                self._initialized = True
                await self.health.record_success()
                self.logger.info(f"ToF sensor {sensor_name} plugin initialized")
                return True

            except Exception as e:
                await self.health.record_failure()
                self.logger.error(f"Failed to initialize ToF sensor plugin: {e}")
                return False

    def _get_all_tof_configs(self) -> List:
        """Get all ToF sensor configurations from the system"""
        from .tof_manager import ToFSensorConfig

        # Default configuration based on hardware setup
        # This should ideally come from the hardware interface configuration
        return [
            ToFSensorConfig(name="tof_left", shutdown_pin=22, interrupt_pin=6, target_address=0x29),
            ToFSensorConfig(
                name="tof_right", shutdown_pin=23, interrupt_pin=12, target_address=0x30
            ),
        ]

    async def read_data(self) -> Optional[SensorReading]:
        """Read distance measurement from ToF sensor"""
        if not self._initialized:
            if not await self.initialize():
                return None

        try:
            # Read from the specific sensor via ToF manager
            reading = await self._tof_manager.read_sensor(self._sensor_name)

            if not reading:
                raise HardwareError(f"No reading from ToF sensor {self._sensor_name}")

            # Convert to standardized ToFReading format
            from .data_structures import ToFReading as StdToFReading

            sensor_reading = StdToFReading(
                timestamp=reading.timestamp,
                sensor_id=self._sensor_name,
                value=reading.distance_mm,
                unit="mm",
                i2c_address=reading.address,
                distance_mm=reading.distance_mm,
                range_status=reading.range_status,
            )

            await self.health.record_success()
            return sensor_reading

        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to read ToF sensor {self._sensor_name}: {e}")
            return None

    async def shutdown(self):
        """Shutdown ToF sensor plugin"""
        if hasattr(self, "_tof_manager") and self._tof_manager:
            # Only shutdown if this is the last ToF sensor plugin
            # In a real implementation, we'd track active plugins
            pass  # Manager handles its own lifecycle

        await super().shutdown()


class PowerMonitorPlugin(HardwarePlugin):
    """INA3221 power monitor plugin"""

    @property
    def plugin_type(self) -> str:
        return "i2c_sensor"

    @property
    def required_managers(self) -> List[str]:
        return ["i2c"]

    async def initialize(self) -> bool:
        """Initialize power monitor"""
        async with self._lock:
            if self._initialized:
                return True

            try:
                i2c_manager = self.managers["i2c"]
                configured_addr = self.config.parameters.get("i2c_address")
                autodetect = bool(self.config.parameters.get("auto_detect_address", True))
                address = int(configured_addr, 0) if isinstance(configured_addr, str) else (
                    int(configured_addr) if configured_addr is not None else 0x40
                )

                # Try auto-detection among common INA3221 addresses 0x40-0x43 by reading config register
                if autodetect:
                    detected = None
                    for probe in (address, 0x40, 0x41, 0x42, 0x43):
                        # Debug: record each probe attempt to aid diagnostics
                        self.logger.debug(f"Probing INA3221 at 0x{probe:02x}")
                        try:
                            data = await i2c_manager.read_register(probe, 0x00, 2)
                            if len(data) == 2:
                                detected = probe
                                break
                        except Exception:
                            continue
                    if detected is not None:
                        address = detected

                self._address = address

                self.logger.info(f"Power monitor: initialized with I2C address 0x{address:02x}")

                # Configure INA3221: reset and set average/convert times, enable channels (conservative defaults)
                config_value = 0x7127  # Averaging 64, VBUS/VSH CT 1.1ms, mode: shunt and bus, continuous
                await i2c_manager.write_register(
                    address, 0x00, [config_value >> 8 & 0xFF, config_value & 0xFF]
                )

                self._initialized = True
                await self.health.record_success()
                self.logger.info(f"Power monitor initialized at address 0x{address:02x}")
                return True

            except Exception as e:
                await self.health.record_failure()
                self.logger.error(f"Failed to initialize power monitor: {e}")
                return False

    async def read_data(self) -> Optional[SensorReading]:
        """Read power data from INA3221"""
        if not self._initialized:
            if not await self.initialize():
                return None

        try:
            i2c_manager = self.managers["i2c"]
            address = getattr(self, "_address", int(self.config.parameters.get("i2c_address", 0x40)))
            channel = int(self.config.parameters.get("channel", 1))

            # Read bus and shunt registers for specified channel
            bus_reg = 0x02 + (channel - 1) * 2
            shunt_reg = 0x01 + (channel - 1) * 2

            bus_raw = await i2c_manager.read_register(address, bus_reg, 2)
            shunt_raw = await i2c_manager.read_register(address, shunt_reg, 2)

            # Combine bytes
            bus_val = (bus_raw[0] << 8) | bus_raw[1]
            shunt_val = (shunt_raw[0] << 8) | shunt_raw[1]

            # Per datasheet: bus voltage is a 13-bit value (bits 15..3), LSB=8mV
            bus_val >>= 3
            voltage = bus_val * 0.008  # V

            # Shunt voltage is signed 16-bit, LSB = 40uV
            if shunt_val & 0x8000:
                shunt_val = shunt_val - 0x10000
            shunt_v = shunt_val * 0.00004  # V

            shunt_ohms = float(self.config.parameters.get("shunt_resistance", 0.1))
            current = shunt_v / shunt_ohms  # A
            power = voltage * current  # W

            from .data_structures import PowerReading

            reading = PowerReading(
                timestamp=datetime.now(),
                sensor_id=self.config.name,
                value={
                    "voltage": voltage,
                    "current": current,
                    "power": power,
                    # Provide commonly expected aliases used by UI/service
                    "battery_voltage": voltage,
                    "battery_current": current,
                },
                unit="mixed",
                i2c_address=address,
                voltage=voltage,
                current=current,
                power=power,
            )

            await self.health.record_success()
            return reading

        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to read power monitor: {e}")
            return None


class EnvironmentalSensorPlugin(HardwarePlugin):
    """BME280 environmental sensor plugin (temperature, humidity, pressure)"""

    @property
    def plugin_type(self) -> str:
        return "i2c_sensor"

    @property
    def required_managers(self) -> List[str]:
        return ["i2c"]

    async def initialize(self) -> bool:
        async with self._lock:
            if self._initialized:
                return True
            try:
                # Prefer Adafruit CircuitPython driver when available
                try:
                    import board  # type: ignore
                    from adafruit_bme280 import basic as adafruit_bme280  # type: ignore
                    use_adafruit = True
                except Exception as e:  # pragma: no cover - missing Blinka
                    self.logger.warning(f"BME280 Adafruit driver unavailable, fallback to smbus2 path: {e}")
                    use_adafruit = False

                # Determine I2C address: respect configured address, or auto-detect 0x76/0x77 by chip ID
                configured_addr = self.config.parameters.get("i2c_address")
                autodetect = bool(self.config.parameters.get("auto_detect_address", True))
                address = int(configured_addr, 0) if isinstance(configured_addr, str) else (
                    int(configured_addr) if configured_addr is not None else 0x76
                )

                detected_addr = None
                if autodetect:
                    try:
                        i2c_mgr = self.managers["i2c"]
                        probes = (address, 0x76, 0x77)
                        self.logger.debug(f"BME280 autodetect probes={[hex(p) for p in probes]}")
                        for probe in probes:
                            try:
                                self.logger.debug(f"Probing BME280 at 0x{probe:02x}")
                                chip_id = await i2c_mgr.read_register(probe, 0xD0, 1)
                                if chip_id and chip_id[0] == 0x60:  # BME280 chip id
                                    detected_addr = probe
                                    self.logger.info(f"BME280 detected at 0x{probe:02x}")
                                    break
                            except Exception as e:
                                self.logger.debug(f"BME280 probe 0x{probe:02x} failed: {e}")
                    except Exception as e:
                        self.logger.debug(f"BME280 autodetect skipped: {e}")
                self._address = detected_addr if detected_addr is not None else address

                if use_adafruit:
                    try:
                        import busio  # type: ignore
                        i2c = busio.I2C(board.SCL, board.SDA)
                        sensor = adafruit_bme280.Adafruit_BME280_I2C(i2c, address=self._address)
                        # Optional oversampling/tuning from config
                        osrs_t = self.config.parameters.get("temperature_oversample")
                        if osrs_t is not None:
                            sensor.temperature_oversample = int(osrs_t)
                        osrs_h = self.config.parameters.get("humidity_oversample")
                        if osrs_h is not None:
                            sensor.humidity_oversample = int(osrs_h)
                        osrs_p = self.config.parameters.get("pressure_oversample")
                        if osrs_p is not None:
                            sensor.pressure_oversample = int(osrs_p)
                        self._driver = ("adafruit", sensor)
                        self.logger.info("Environmental sensor: using Adafruit driver path")
                    except Exception as e:
                        self.logger.warning(f"Adafruit BME280 init failed, will try smbus2: {e}")
                        self._driver = None
                        use_adafruit = False

                if not use_adafruit:
                    # Ensure I2C bus exists via I2CManager
                    _ = self.managers["i2c"]
                    # We'll do on-demand reads using I2CManager in read_data()
                    self._driver = ("raw", None)
                    self.logger.info("Environmental sensor: using raw smbus2 read path")

                self._initialized = True
                await self.health.record_success()
                self.logger.info(f"Environmental sensor (BME280) initialized at 0x{address:02x}")
                self.logger.debug(f"Environmental sensor driver={self._driver[0]} address=0x{self._address:02x}")
                return True
            except Exception as e:
                await self.health.record_failure()
                self.logger.error(f"Failed to initialize environmental sensor: {e}")
                return False

    async def read_data(self) -> Optional[SensorReading]:
        if not self._initialized:
            if not await self.initialize():
                return None
        try:
            from .data_structures import EnvironmentalReading
            if self._driver and self._driver[0] == "adafruit":
                sensor = self._driver[1]
                temperature = float(sensor.temperature)
                humidity = float(sensor.humidity)
                pressure = float(sensor.pressure)
            else:
                # Minimal raw read via smbus2 using I2CManager
                # This block implements a simple read leveraging common BME280 drivers logic.
                # Read calibration and raw data each time for simplicity; cache could be added later.
                i2c = self.managers["i2c"]
                addr = getattr(self, "_address", 0x76)

                # Read calibration data
                calib = await i2c.read_register(addr, 0x88, 26)
                dig_T1 = calib[1] << 8 | calib[0]
                dig_T2 = self._to_signed(calib[3] << 8 | calib[2], 16)
                dig_T3 = self._to_signed(calib[5] << 8 | calib[4], 16)
                dig_P1 = calib[7] << 8 | calib[6]
                dig_P2 = self._to_signed(calib[9] << 8 | calib[8], 16)
                dig_P3 = self._to_signed(calib[11] << 8 | calib[10], 16)
                dig_P4 = self._to_signed(calib[13] << 8 | calib[12], 16)
                dig_P5 = self._to_signed(calib[15] << 8 | calib[14], 16)
                dig_P6 = self._to_signed(calib[17] << 8 | calib[16], 16)
                dig_P7 = self._to_signed(calib[19] << 8 | calib[18], 16)
                dig_P8 = self._to_signed(calib[21] << 8 | calib[20], 16)
                dig_P9 = self._to_signed(calib[23] << 8 | calib[22], 16)
                dig_H1 = await i2c.read_register(addr, 0xA1, 1)
                dig_H1 = dig_H1[0]
                calib_h = await i2c.read_register(addr, 0xE1, 7)
                dig_H2 = self._to_signed(calib_h[1] << 8 | calib_h[0], 16)
                dig_H3 = calib_h[2]
                e4 = calib_h[3]
                e5 = calib_h[4]
                e6 = calib_h[5]
                dig_H4 = self._to_signed((e4 << 4) | (e5 & 0x0F), 12)
                dig_H5 = self._to_signed((e6 << 4) | (e5 >> 4), 12)
                dig_H6 = self._to_signed(calib_h[6], 8)

                # Force mode, normal oversampling (temp x1, press x1, hum x1)
                await i2c.write_register(addr, 0xF2, 0x01)
                await i2c.write_register(addr, 0xF4, 0x27)
                await i2c.write_register(addr, 0xF5, 0xA0)
                await asyncio.sleep(0.01)

                data = await i2c.read_register(addr, 0xF7, 8)
                adc_P = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
                adc_T = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
                adc_H = (data[6] << 8) | data[7]

                # Temperature compensation (per datasheet)
                var1 = (adc_T / 16384.0 - dig_T1 / 1024.0) * dig_T2
                var2 = ((adc_T / 131072.0 - dig_T1 / 8192.0) * (adc_T / 131072.0 - dig_T1 / 8192.0)) * dig_T3
                t_fine = var1 + var2
                temperature = t_fine / 5120.0
                # Pressure compensation
                var1_p = t_fine / 2.0 - 64000.0
                var2_p = var1_p * var1_p * dig_P6 / 32768.0
                var2_p = var2_p + var1_p * dig_P5 * 2.0
                var2_p = var2_p / 4.0 + dig_P4 * 65536.0
                var1_p = (dig_P3 * var1_p * var1_p / 524288.0 + dig_P2 * var1_p) / 524288.0
                var1_p = (1.0 + var1_p / 32768.0) * dig_P1
                if var1_p == 0:
                    pressure = 0.0
                else:
                    p = 1048576.0 - adc_P
                    p = ((p - var2_p / 4096.0) * 6250.0) / var1_p
                    var1_p = dig_P9 * p * p / 2147483648.0
                    var2_p = p * dig_P8 / 32768.0
                    pressure = p + (var1_p + var2_p + dig_P7) / 16.0
                    pressure = pressure / 100.0  # Pa -> hPa
                # Humidity compensation (per datasheet)
                var_h = t_fine - 76800.0
                var_h = (adc_H - (dig_H4 * 64.0 + (dig_H5 / 16384.0) * var_h)) * (
                    dig_H2 / 65536.0 * (1.0 + (dig_H6 / 67108864.0) * var_h * (1.0 + (dig_H3 / 67108864.0) * var_h))
                )
                var_h = var_h * (1.0 - dig_H1 * var_h / 524288.0)
                humidity = max(0.0, min(100.0, var_h))

            reading = EnvironmentalReading(
                timestamp=datetime.now(),
                sensor_id=self.config.name,
                value={
                    "temperature": float(temperature),
                    "humidity": float(humidity),
                    "pressure": float(pressure),
                },
                unit="mixed",
                i2c_address=self._address,
                temperature=float(temperature),
                humidity=float(humidity),
                pressure=float(pressure),
            )

            await self.health.record_success()
            return reading
        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to read environmental sensor: {e}")
            return None

    @staticmethod
    def _to_signed(val: int, bits: int) -> int:
        """Convert unsigned to signed integer of given bit width."""
        if val & (1 << (bits - 1)):
            val -= 1 << bits
        return val


class RoboHATPlugin(HardwarePlugin):
    """Enhanced RoboHAT controller plugin with RC control support"""

    def __init__(self, config: PluginConfig, managers: Dict[str, Any]):
        super().__init__(config, managers)
        self.rc_mode = "emergency"
        self.rc_enabled = True
        self.blade_enabled = False
        self.channel_config = {
            1: {"function": "steer", "min": 1000, "max": 2000, "center": 1500},
            2: {"function": "throttle", "min": 1000, "max": 2000, "center": 1500},
            3: {"function": "blade", "min": 1000, "max": 2000, "center": 1500},
            4: {"function": "speed_adj", "min": 1000, "max": 2000, "center": 1500},
            5: {"function": "emergency", "min": 1000, "max": 2000, "center": 1500},
            6: {"function": "mode_switch", "min": 1000, "max": 2000, "center": 1500},
        }

    @property
    def plugin_type(self) -> str:
        return "serial_device"

    @property
    def required_managers(self) -> List[str]:
        return ["serial"]

    async def initialize(self) -> bool:
        """Initialize RoboHAT connection with RC control support"""
        async with self._lock:
            if self._initialized:
                return True

            try:
                serial_manager = self.managers["serial"]
                await serial_manager.initialize_device("robohat")

                # Send initial commands to configure RC system
                await serial_manager.write_command("robohat", "rc=enable")
                await asyncio.sleep(0.1)
                await serial_manager.write_command("robohat", f"rc_mode={self.rc_mode}")
                await asyncio.sleep(0.1)

                self._initialized = True
                await self.health.record_success()
                self.logger.info(f"RoboHAT initialized with RC mode: {self.rc_mode}")
                return True

            except Exception as e:
                await self.health.record_failure()
                self.logger.error(f"Failed to initialize RoboHAT: {e}")
                return False

    async def send_pwm_command(self, steer: int, throttle: int) -> bool:
        """Send PWM command to RoboHAT"""
        if not self._initialized:
            if not await self.initialize():
                return False

        try:
            # Validate PWM values
            if not (1000 <= steer <= 2000 and 1000 <= throttle <= 2000):
                raise ValueError(f"Invalid PWM values: steer={steer}, throttle={throttle}")

            serial_manager = self.managers["serial"]
            command = f"pwm,{steer},{throttle}"
            success = await serial_manager.write_command("robohat", command)

            if success:
                await self.health.record_success()
            else:
                await self.health.record_failure()

            return success

        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to send PWM command: {e}")
            return False

    async def get_rc_status(self) -> Optional[Dict[str, Any]]:
        """Get comprehensive RC status from RoboHAT"""
        if not self._initialized:
            if not await self.initialize():
                return None

        try:
            serial_manager = self.managers["serial"]
            success = await serial_manager.write_command("robohat", "get_rc_status")

            if success:
                # Wait for status response
                await asyncio.sleep(0.1)
                line = await serial_manager.read_line("robohat", timeout=1.0)

                if line and line.startswith("[STATUS]"):
                    # Parse status response
                    status_str = line.replace("[STATUS] ", "")
                    try:
                        import ast

                        status_dict = ast.literal_eval(status_str)
                        await self.health.record_success()
                        return status_dict
                    except Exception as parse_error:
                        self.logger.error(f"Failed to parse RC status: {parse_error}")

            return None

        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to get RC status: {e}")
            return None

    async def configure_channel(
        self,
        channel: int,
        function: str,
        min_val: int = 1000,
        max_val: int = 2000,
        center_val: int = 1500,
    ) -> bool:
        """Configure RC channel function mapping"""
        if not self._initialized:
            if not await self.initialize():
                return False

        valid_functions = ["steer", "throttle", "blade", "speed_adj", "emergency", "mode_switch"]
        if function not in valid_functions:
            self.logger.error(f"Invalid RC function: {function}")
            return False

        if not (1 <= channel <= 6):
            self.logger.error(f"Invalid RC channel: {channel}")
            return False

        try:
            serial_manager = self.managers["serial"]
            command = f"rc_config={channel},{function}"
            success = await serial_manager.write_command("robohat", command)

            if success:
                # Update local channel config
                self.channel_config[channel] = {
                    "function": function,
                    "min": min_val,
                    "max": max_val,
                    "center": center_val,
                }
                await self.health.record_success()
                self.logger.info(f"RC channel {channel} configured for {function}")
            else:
                await self.health.record_failure()

            return success

        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to configure RC channel: {e}")
            return False

    async def read_data(self) -> Optional[SensorReading]:
        """Read status from RoboHAT"""
        if not self._initialized:
            if not await self.initialize():
                return None

        try:
            # Get comprehensive RC status
            rc_status = await self.get_rc_status()

            if rc_status:
                from .data_structures import RoboHATStatus, SerialDeviceReading

                status = RoboHATStatus(
                    timestamp=datetime.now(),
                    rc_enabled=rc_status.get("rc_enabled", True),
                    steer_pwm=rc_status.get("channels", {}).get(1, 1500),
                    throttle_pwm=rc_status.get("channels", {}).get(2, 1500),
                    encoder_position=rc_status.get("encoder", 0),
                    connection_active=True,
                )

                # Use actual serial device settings
                serial_manager = self.managers.get("serial")
                port = None
                baud = None
                try:
                    if serial_manager and hasattr(serial_manager, 'devices'):
                        port = serial_manager.devices.get("robohat", {}).get("port")
                        baud = serial_manager.devices.get("robohat", {}).get("baud")
                except Exception:
                    pass

                reading = SerialDeviceReading(
                    timestamp=datetime.now(),
                    sensor_id=self.config.name,
                    value=status,
                    unit="status",
                    port=port or "/dev/ttyACM1",
                    baud_rate=baud or 115200,
                )

                await self.health.record_success()
                return reading

            return None

        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to read RoboHAT status: {e}")
            return None


class GPSPlugin(HardwarePlugin):
    """GPS plugin that reads NMEA sentences from serial and outputs GPSReading"""

    @property
    def plugin_type(self) -> str:
        return "serial_device"

    @property
    def required_managers(self) -> List[str]:
        return ["serial"]

    async def initialize(self) -> bool:
        async with self._lock:
            if self._initialized:
                return True
            try:
                serial_manager = self.managers["serial"]
                self.device_name = "gps"
                self._timeout = float(self.config.parameters.get("timeout", 1.0))
                # Start with configured values
                cfg_port = self.config.parameters.get("port")
                cfg_baud = int(self.config.parameters.get("baud", 38400))
                import glob

                async def try_init(port: str, baud: int) -> bool:
                    try:
                        await serial_manager.initialize_device("gps", port=port, baud=baud, timeout=self._timeout)
                        # quick sanity read - look for any NMEA sentence
                        for _ in range(5):
                            line = await serial_manager.read_line("gps", timeout=0.6)
                            if line and line.startswith("$"):
                                return True
                        # no NMEA seen; close connection to avoid stealing port
                        try:
                            conn = serial_manager._connections.get("gps")
                            if conn and conn.is_open:
                                conn.close()
                        except Exception:
                            pass
                        return False
                    except Exception:
                        return False

                # Start with configured candidates then broaden to all tty nodes
                candidates_ports = []
                if cfg_port:
                    candidates_ports.append(cfg_port)
                candidates_ports += ["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyAMA0", "/dev/ttyAMA4"]
                # Add any discovered device nodes
                for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*", "/dev/ttyAMA*"):
                    for p in glob.glob(pattern):
                        if p not in candidates_ports:
                            candidates_ports.append(p)

                # Prefer 115200 first (user observed RMC at 115200), then configured baud, then common baud rates
                candidates_bauds = [115200, cfg_baud, 9600, 38400]

                selected = None
                for p in candidates_ports:
                    for b in candidates_bauds:
                        if await try_init(p, b):
                            selected = (p, b)
                            break
                    if selected:
                        break

                if selected:
                    self._port, self._baud = selected
                    self._last_failures = 0
                    self._last_hdop = 0.0
                    self._last_sats = 0
                    self._initialized = True
                    await self.health.record_success()
                    self.logger.info(f"GPS plugin initialized on {self._port} @ {self._baud}")
                    return True

                # Broadened scan failed — don't bind to an incorrect default port that may be RoboHAT.
                # Mark plugin loaded but not yet initialized and start a background re-detect loop.
                self._initialized = False
                self._last_failures = getattr(self, "_last_failures", 0)
                await self.health.record_failure()
                self.logger.warning("GPS auto-detect failed; will continue background re-detect")

                # background re-detection task
                async def _redetect_loop():
                    try:
                        while not self._initialized:
                            for p in candidates_ports:
                                for b in candidates_bauds:
                                    if await try_init(p, b):
                                        try:
                                            await serial_manager.initialize_device("gps", port=p, baud=b, timeout=self._timeout)
                                            self._port, self._baud = (p, b)
                                            self._initialized = True
                                            await self.health.record_success()
                                            self.logger.info(f"GPS plugin background-initialized on {p} @ {b}")
                                            return
                                        except Exception:
                                            continue
                            await asyncio.sleep(10.0)
                    except asyncio.CancelledError:
                        return

                # launch background re-detect without blocking initialization
                try:
                    self._redetect_task = asyncio.create_task(_redetect_loop())
                except Exception:
                    pass

                return True
            except Exception as e:
                await self.health.record_failure()
                self.logger.error(f"Failed to initialize GPS plugin: {e}")
                return False

    async def read_data(self) -> Optional[SensorReading]:
        if not self._initialized:
            if not await self.initialize():
                return None
        try:
            serial_manager = self.managers["serial"]
            line = await serial_manager.read_line(self.device_name, timeout=1.0)
            if not line:
                self._last_failures = getattr(self, "_last_failures", 0) + 1
                if self._last_failures % 20 == 0:
                    # Periodically attempt re-detect
                    self._initialized = False
                    self.logger.debug("GPS no data; attempting auto re-detect")
                    await self.initialize()
                return None

            # Debug: log raw NMEA sentences seen so we can diagnose parse failures
            try:
                self.logger.debug(f"GPS raw sentence: {line}")
            except Exception:
                pass

            lat = lon = altitude = hdop = 0.0
            satellites = 0
            fix_type = "none"

            if "$GPGGA" in line or "$GNGGA" in line:
                data = line.split(",")
                if len(data) >= 15:
                    lat = self._convert_to_decimal(data[2], data[3])
                    lon = self._convert_to_decimal(data[4], data[5])
                    quality = data[6]
                    satellites = int(data[7] or 0)
                    hdop = float(data[8] or 0.0)
                    altitude = float(data[9] or 0.0)
                    fix_map = {"0": "none", "1": "gps", "2": "dgps", "4": "rtk", "5": "rtk", "9": "rtk"}
                    fix_type = fix_map.get(quality, "none")
            elif "$GPRMC" in line or "$GNRMC" in line:
                data = line.split(",")
                if len(data) >= 12:
                    status = data[2]
                    if status == "A":
                        lat = self._convert_to_decimal(data[3], data[4])
                        lon = self._convert_to_decimal(data[5], data[6])
                        fix_type = "gps"
            elif "$GPGLL" in line or "$GNGLL" in line:
                data = line.split(",")
                if len(data) >= 7:
                    status = data[6]
                    if status in ("A", "D"):
                        lat = self._convert_to_decimal(data[1], data[2])
                        lon = self._convert_to_decimal(data[3], data[4])
                        fix_type = "gps"
            elif "$GPGSA" in line or "$GNGSA" in line:
                # DOP and active satellites
                try:
                    data = line.split(",")
                    # PDOP, HDOP, VDOP at indices -3, -2, -1 before checksum
                    if len(data) >= 17:
                        hdop_val = data[16].split("*")[0] if "*" in data[16] else data[16]
                        self._last_hdop = float(hdop_val or 0.0)
                except Exception:
                    pass
                return None
            elif "$GPGSV" in line or "$GLGSV" in line or "$GAGSV" in line or "$BDGSV" in line or "$GNGSV" in line:
                # Satellites in view; we can approximate satellites used after a few frames
                try:
                    data = line.split(",")
                    # total satellites in view at index 3 for many talkers
                    if len(data) >= 4:
                        total = data[3]
                        # Strip checksum if present
                        total = total.split("*")[0]
                        self._last_sats = max(self._last_sats, int(total or 0))
                except Exception:
                    pass
                return None
            else:
                # Unrecognized sentence; count as a soft failure
                self._last_failures = getattr(self, "_last_failures", 0) + 1
                if self._last_failures % 40 == 0:
                    self.logger.debug("GPS unrecognized sentences; attempting auto re-detect")
                    self._initialized = False
                    await self.initialize()
                return None

            if lat == 0.0 and lon == 0.0:
                self._last_failures = getattr(self, "_last_failures", 0) + 1
                return None
            from .data_structures import GPSReading

            reading = GPSReading(
                timestamp=datetime.now(),
                sensor_id=self.config.name,
                value={
                    "latitude": lat,
                    "longitude": lon,
                    "altitude": altitude,
                    "accuracy": hdop,
                    "satellites": satellites,
                    "fix_type": fix_type,
                },
                unit="degrees",
                port=serial_manager.devices[self.device_name]["port"],
                baud_rate=serial_manager.devices[self.device_name]["baud"],
                latitude=lat,
                longitude=lon,
                altitude=altitude,
                accuracy=hdop if hdop > 0 else getattr(self, "_last_hdop", 0.0),
                satellites=satellites if satellites > 0 else getattr(self, "_last_sats", 0),
                fix_type=fix_type,
            )
            await self.health.record_success()
            return reading
        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to read GPS data: {e}")
            return None

    def _convert_to_decimal(self, raw: str, direction: str) -> float:
        if not raw:
            return 0.0
        try:
            if direction in ["N", "S"]:
                degrees = float(raw[:2])
                minutes = float(raw[2:])
            else:
                degrees = float(raw[:3])
                minutes = float(raw[3:])
            decimal = degrees + minutes / 60.0
            if direction in ["S", "W"]:
                decimal *= -1
            return decimal
        except Exception:
            return 0.0


class IMUPlugin(HardwarePlugin):
    """Simple IMU plugin parsing comma-separated orientation and motion data"""

    @property
    def plugin_type(self) -> str:
        return "serial_device"

    @property
    def required_managers(self) -> List[str]:
        return ["serial"]

    async def initialize(self) -> bool:
        async with self._lock:
            if self._initialized:
                return True
            try:
                serial_manager = self.managers["serial"]
                self.device_name = "imu"
                self._timeout = float(self.config.parameters.get("timeout", 0.1))
                cfg_port = self.config.parameters.get("port")
                cfg_baud = int(self.config.parameters.get("baud", 115200))

                async def try_init(port: str, baud: int) -> bool:
                    try:
                        await serial_manager.initialize_device("imu", port=port, baud=baud, timeout=self._timeout)
                        # quick sanity read
                        for _ in range(3):
                            line = await serial_manager.read_line("imu", timeout=self._timeout)
                            if line:
                                return True
                        return False
                    except Exception:
                        return False

                candidates_ports = list(dict.fromkeys([cfg_port, "/dev/ttyAMA4", "/dev/ttyAMA0"]))
                candidates_ports = [p for p in candidates_ports if p]
                candidates_bauds = [cfg_baud, 3000000, 921600, 115200]

                selected = None
                for p in candidates_ports:
                    for b in candidates_bauds:
                        if await try_init(p, b):
                            selected = (p, b)
                            break
                    if selected:
                        break

                if not selected:
                    # Initialize anyway to allow later re-detect
                    await serial_manager.initialize_device("imu", port=cfg_port or "/dev/ttyAMA4", baud=cfg_baud, timeout=self._timeout)
                    self._last_failures = 0
                    self._initialized = True
                    await self.health.record_failure()
                    self.logger.warning("IMU auto-detect failed; initialized with configured defaults")
                    return True

                self._port, self._baud = selected
                self._last_failures = 0
                self._initialized = True
                await self.health.record_success()
                self.logger.info(f"IMU plugin initialized on {self._port} @ {self._baud}")
                return True
            except Exception as e:
                await self.health.record_failure()
                self.logger.error(f"Failed to initialize IMU plugin: {e}")
                return False

    async def read_data(self) -> Optional[SensorReading]:
        if not self._initialized:
            if not await self.initialize():
                return None
        try:
            serial_manager = self.managers["serial"]
            line = await serial_manager.read_line(self.device_name, timeout=self._timeout)
            if not line:
                self._last_failures = getattr(self, "_last_failures", 0) + 1
                if self._last_failures % 50 == 0:
                    # Periodically attempt re-detect if no data
                    self._initialized = False
                    self.logger.debug("IMU no data; attempting auto re-detect")
                    await self.initialize()
                return None
            parts = line.split(",")
            if len(parts) < 9:
                self._last_failures = getattr(self, "_last_failures", 0) + 1
                if self._last_failures % 50 == 0:
                    self.logger.debug("IMU short/invalid line; attempting auto re-detect")
                    self._initialized = False
                    await self.initialize()
                return None
            try:
                roll, pitch, yaw, ax, ay, az, gx, gy, gz = map(float, parts[:9])
            except Exception:
                self._last_failures = getattr(self, "_last_failures", 0) + 1
                if self._last_failures % 50 == 0:
                    self.logger.debug("IMU parse error; attempting auto re-detect")
                    self._initialized = False
                    await self.initialize()
                return None
            from .data_structures import IMUReading

            reading = IMUReading(
                timestamp=datetime.now(),
                sensor_id=self.config.name,
                value={
                    "orientation": {"roll": roll, "pitch": pitch, "yaw": yaw},
                    "acceleration": {"x": ax, "y": ay, "z": az},
                    "gyroscope": {"x": gx, "y": gy, "z": gz},
                },
                unit="mixed",
                port=serial_manager.devices[self.device_name]["port"],
                baud_rate=serial_manager.devices[self.device_name]["baud"],
                quaternion=(0.0, 0.0, 0.0, 1.0),
                acceleration=(ax, ay, az),
                angular_velocity=(gx, gy, gz),
            )
            await self.health.record_success()
            return reading
        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to read IMU data: {e}")
            return None


class PluginManager:
    """Manages hardware plugins with hot-swap support"""

    def __init__(self, managers: Dict[str, Any]):
        self.managers = managers
        self.logger = logging.getLogger(__name__)
        self._plugins: Dict[str, HardwarePlugin] = {}
        self._plugin_configs: Dict[str, PluginConfig] = {}
        self._lock = asyncio.Lock()

        # Built-in plugin classes
        self._builtin_plugins = {
            "tof_sensor": ToFSensorPlugin,
            "power_monitor": PowerMonitorPlugin,
            "robohat": RoboHATPlugin,
            "gps_sensor": GPSPlugin,
            "imu_sensor": IMUPlugin,
            "environmental_sensor": EnvironmentalSensorPlugin,
        }

        # Add weather service plugin if available
        try:
            from ..weather.weather_plugin import WeatherPlugin

            self._builtin_plugins["weather_service"] = WeatherPlugin
        except ImportError:
            self.logger.warning("Weather service plugin not available")

    async def load_plugin(self, plugin_name: str, plugin_type: str, config: PluginConfig) -> bool:
        """Load and initialize a hardware plugin"""
        async with self._lock:
            try:
                # Get plugin class
                if plugin_type in self._builtin_plugins:
                    plugin_class = self._builtin_plugins[plugin_type]
                else:
                    # Try to import custom plugin
                    module = importlib.import_module(f"plugins.{plugin_type}")
                    plugin_class = getattr(module, f"{plugin_type.title()}Plugin")

                # Verify required managers are available
                plugin_instance = plugin_class(config, self.managers)
                for manager_type in plugin_instance.required_managers:
                    if manager_type not in self.managers:
                        raise HardwareError(f"Required manager '{manager_type}' not available")

                # Initialize plugin
                if await plugin_instance.initialize():
                    self._plugins[plugin_name] = plugin_instance
                    self._plugin_configs[plugin_name] = config
                    self.logger.info(f"Plugin '{plugin_name}' loaded successfully")
                    return True
                else:
                    self.logger.error(f"Failed to initialize plugin '{plugin_name}'")
                    return False

            except Exception as e:
                self.logger.error(f"Failed to load plugin '{plugin_name}': {e}")
                return False

    async def unload_plugin(self, plugin_name: str) -> bool:
        """Unload a hardware plugin"""
        async with self._lock:
            if plugin_name not in self._plugins:
                return False

            try:
                plugin = self._plugins[plugin_name]
                await plugin.shutdown()

                del self._plugins[plugin_name]
                del self._plugin_configs[plugin_name]

                self.logger.info(f"Plugin '{plugin_name}' unloaded")
                return True

            except Exception as e:
                self.logger.error(f"Error unloading plugin '{plugin_name}': {e}")
                return False

    async def reload_plugin(self, plugin_name: str) -> bool:
        """Reload a hardware plugin"""
        if plugin_name not in self._plugins:
            return False

        config = self._plugin_configs[plugin_name]
        plugin_type = self._plugins[plugin_name].plugin_type

        await self.unload_plugin(plugin_name)
        return await self.load_plugin(plugin_name, plugin_type, config)

    def get_plugin(self, plugin_name: str) -> Optional[HardwarePlugin]:
        """Get plugin instance by name"""
        return self._plugins.get(plugin_name)

    def list_plugins(self) -> List[str]:
        """List all loaded plugins"""
        return list(self._plugins.keys())

    async def health_check_all(self) -> Dict[str, bool]:
        """Perform health check on all plugins"""
        results = {}
        for name, plugin in self._plugins.items():
            try:
                results[name] = await plugin.health_check()
            except Exception as e:
                self.logger.error(f"Health check failed for '{name}': {e}")
                results[name] = False
        return results

    async def shutdown_all(self):
        """Shutdown all plugins"""
        for name in list(self._plugins.keys()):
            await self.unload_plugin(name)
