"""Plugin system for modular hardware components"""

import asyncio
import logging
import importlib
import inspect
from abc import ABC, abstractmethod
from typing import Dict, Type, List, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

from .exceptions import HardwareError, DeviceNotFoundError
from .data_structures import SensorReading, DeviceHealth


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
    """VL53L0X Time-of-Flight sensor plugin"""
    
    @property
    def plugin_type(self) -> str:
        return "i2c_sensor"
    
    @property
    def required_managers(self) -> List[str]:
        return ["i2c", "gpio"]
    
    async def initialize(self) -> bool:
        """Initialize ToF sensor"""
        async with self._lock:
            if self._initialized:
                return True
            
            try:
                i2c_manager = self.managers["i2c"]
                gpio_manager = self.managers["gpio"]
                
                # Get configuration
                address = self.config.parameters.get("i2c_address", 0x29)
                shutdown_pin = self.config.parameters.get("shutdown_pin")
                interrupt_pin = self.config.parameters.get("interrupt_pin")
                
                # Setup GPIO pins if specified
                if shutdown_pin:
                    await gpio_manager.setup_pin(shutdown_pin, "output", initial=1)
                if interrupt_pin:
                    await gpio_manager.setup_pin(interrupt_pin, "input", pull_up_down="up")
                
                # Initialize sensor (simplified - would include actual VL53L0X init sequence)
                await i2c_manager.write_register(address, 0x00, 0x01)  # Power on
                await asyncio.sleep(0.1)
                
                # Verify sensor ID
                sensor_id = await i2c_manager.read_register(address, 0xC0, 1)
                if sensor_id[0] != 0xEE:  # VL53L0X ID
                    raise HardwareError(f"Invalid sensor ID: 0x{sensor_id[0]:02x}")
                
                self._initialized = True
                await self.health.record_success()
                self.logger.info(f"ToF sensor initialized at address 0x{address:02x}")
                return True
                
            except Exception as e:
                await self.health.record_failure()
                self.logger.error(f"Failed to initialize ToF sensor: {e}")
                return False
    
    async def read_data(self) -> Optional[SensorReading]:
        """Read distance measurement from ToF sensor"""
        if not self._initialized:
            if not await self.initialize():
                return None
        
        try:
            i2c_manager = self.managers["i2c"]
            address = self.config.parameters.get("i2c_address", 0x29)
            
            # Start measurement (simplified)
            await i2c_manager.write_register(address, 0x00, 0x01)
            await asyncio.sleep(0.03)  # 30ms measurement time
            
            # Read distance (simplified - actual VL53L0X has complex protocol)
            distance_data = await i2c_manager.read_register(address, 0x1E, 2)
            distance_mm = (distance_data[0] << 8) | distance_data[1]
            
            from .data_structures import ToFReading
            reading = ToFReading(
                timestamp=datetime.now(),
                sensor_id=self.config.name,
                value=distance_mm,
                unit="mm",
                i2c_address=address,
                distance_mm=distance_mm,
                range_status="valid" if distance_mm < 2000 else "out_of_range"
            )
            
            await self.health.record_success()
            return reading
            
        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to read ToF sensor: {e}")
            return None


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
                await i2c_manager.write_register(address, 0x00, 
                    [config_value >> 8, config_value & 0xFF])
                
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
            current = ((current_data[0] << 8) | current_data[1]) * 0.04   # mA
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
                power=power
            )
            
            await self.health.record_success()
            return reading
            
        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to read power monitor: {e}")
            return None


class RoboHATPlugin(HardwarePlugin):
    """RoboHAT controller plugin"""
    
    @property
    def plugin_type(self) -> str:
        return "serial_device"
    
    @property
    def required_managers(self) -> List[str]:
        return ["serial"]
    
    async def initialize(self) -> bool:
        """Initialize RoboHAT connection"""
        async with self._lock:
            if self._initialized:
                return True
            
            try:
                serial_manager = self.managers["serial"]
                await serial_manager.initialize_device("robohat")
                
                # Send initial command to verify connection
                await serial_manager.write_command("robohat", "rc=disable")
                await asyncio.sleep(0.1)
                
                self._initialized = True
                await self.health.record_success()
                self.logger.info("RoboHAT initialized")
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
    
    async def read_data(self) -> Optional[SensorReading]:
        """Read status from RoboHAT"""
        if not self._initialized:
            if not await self.initialize():
                return None
        
        try:
            serial_manager = self.managers["serial"]
            line = await serial_manager.read_line("robohat", timeout=0.5)
            
            if line and line.startswith("["):
                # Parse status line: [RC] steer=1500 µs thr=1500 µs enc=0
                parts = line.split()
                mode = parts[0].strip("[]")
                
                steer_val = int(parts[1].split("=")[1])
                thr_val = int(parts[2].split("=")[1])  
                enc_val = int(parts[3].split("=")[1])
                
                from .data_structures import RoboHATStatus
                status = RoboHATStatus(
                    timestamp=datetime.now(),
                    rc_enabled=(mode == "RC"),
                    steer_pwm=steer_val,
                    throttle_pwm=thr_val,
                    encoder_position=enc_val,
                    connection_active=True
                )
                
                reading = SerialDeviceReading(
                    timestamp=datetime.now(),
                    sensor_id=self.config.name,
                    value=status,
                    unit="status",
                    port="/dev/ttyACM1",
                    baud_rate=115200
                )
                
                await self.health.record_success()
                return reading
            
            return None
            
        except Exception as e:
            await self.health.record_failure()
            self.logger.error(f"Failed to read RoboHAT status: {e}")
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
            "robohat": RoboHATPlugin
        }
    
    async def load_plugin(self, plugin_name: str, plugin_type: str, 
                         config: PluginConfig) -> bool:
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
                        raise HardwareError(
                            f"Required manager '{manager_type}' not available"
                        )
                
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
