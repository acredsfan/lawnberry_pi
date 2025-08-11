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

            # Convert to plugin SensorReading format
            from .data_structures import SensorReading

            sensor_reading = SensorReading(
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
                address = self.config.parameters.get("i2c_address", 0x40)

                # Configure INA3221 (simplified)
                config_value = 0x7127  # Default configuration
                await i2c_manager.write_register(
                    address, 0x00, [config_value >> 8, config_value & 0xFF]
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
            address = self.config.parameters.get("i2c_address", 0x40)
            channel = self.config.parameters.get("channel", 1)

            # Read voltage and current for specified channel
            voltage_reg = 0x02 + (channel - 1) * 2
            current_reg = 0x01 + (channel - 1) * 2

            voltage_data = await i2c_manager.read_register(address, voltage_reg, 2)
            current_data = await i2c_manager.read_register(address, current_reg, 2)

            # Convert to actual values (simplified)
            voltage = ((voltage_data[0] << 8) | voltage_data[1]) * 0.008  # V
            current = ((current_data[0] << 8) | current_data[1]) * 0.04  # mA
            power = voltage * current / 1000  # W

            from .data_structures import PowerReading

            reading = PowerReading(
                timestamp=datetime.now(),
                sensor_id=self.config.name,
                value={"voltage": voltage, "current": current, "power": power},
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
                from .data_structures import RoboHATStatus

                status = RoboHATStatus(
                    timestamp=datetime.now(),
                    rc_enabled=rc_status.get("rc_enabled", True),
                    steer_pwm=rc_status.get("channels", {}).get(1, 1500),
                    throttle_pwm=rc_status.get("channels", {}).get(2, 1500),
                    encoder_position=rc_status.get("encoder", 0),
                    connection_active=True,
                )

                reading = SerialDeviceReading(
                    timestamp=datetime.now(),
                    sensor_id=self.config.name,
                    value=status,
                    unit="status",
                    port="/dev/ttyACM1",
                    baud_rate=115200,
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
                port = self.config.parameters.get("port")
                baud = self.config.parameters.get("baud", 38400)
                timeout = self.config.parameters.get("timeout", 1.0)
                await serial_manager.initialize_device("gps", port=port, baud=baud, timeout=timeout)
                self.device_name = "gps"
                self._initialized = True
                await self.health.record_success()
                self.logger.info(f"GPS plugin initialized on {port}")
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
                return None
            if "GGA" not in line:
                return None
            data = line.split(",")
            if len(data) < 15:
                return None
            lat = self._convert_to_decimal(data[2], data[3])
            lon = self._convert_to_decimal(data[4], data[5])
            quality = data[6]
            satellites = int(data[7] or 0)
            hdop = float(data[8] or 0.0)
            altitude = float(data[9] or 0.0)
            fix_map = {
                "0": "none",
                "1": "gps",
                "2": "dgps",
                "4": "rtk",
                "5": "rtk",
                "9": "rtk",
            }
            fix_type = fix_map.get(quality, "none")
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
                accuracy=hdop,
                satellites=satellites,
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
                port = self.config.parameters.get("port")
                baud = self.config.parameters.get("baud", 115200)
                timeout = self.config.parameters.get("timeout", 0.1)
                await serial_manager.initialize_device("imu", port=port, baud=baud, timeout=timeout)
                self.device_name = "imu"
                self._initialized = True
                await self.health.record_success()
                self.logger.info(f"IMU plugin initialized on {port}")
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
            line = await serial_manager.read_line(self.device_name, timeout=0.1)
            if not line:
                return None
            parts = line.split(",")
            if len(parts) < 9:
                return None
            roll, pitch, yaw, ax, ay, az, gx, gy, gz = map(float, parts[:9])
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
