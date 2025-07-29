"""Main hardware interface layer coordinating all managers"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from .managers import I2CManager, SerialManager, CameraManager, GPIOManager
from .plugin_system import PluginManager, HardwarePlugin
from .config import ConfigManager, HardwareInterfaceConfig
from .data_structures import SensorReading, DeviceHealth
from .exceptions import HardwareError, DeviceNotFoundError


class HardwareInterface:
    """Main hardware interface coordinating all subsystems"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.load_config()
        
        # Hardware managers
        self.i2c_manager = I2CManager()
        self.serial_manager = SerialManager()
        self.camera_manager = CameraManager(self.config.camera.device_path)
        self.gpio_manager = GPIOManager()
        
        # Plugin system
        self.plugin_manager = PluginManager({
            'i2c': self.i2c_manager,
            'serial': self.serial_manager,
            'camera': self.camera_manager,
            'gpio': self.gpio_manager
        })
        
        # State
        self._initialized = False
        self._shutdown_event = asyncio.Event()
        self._health_check_task = None
        self._sensor_data_cache: Dict[str, SensorReading] = {}
        self._cache_lock = asyncio.Lock()
        
        # Setup logging
        logging.basicConfig(level=getattr(logging, self.config.logging_level))
    
    async def initialize(self) -> bool:
        """Initialize all hardware components"""
        if self._initialized:
            return True
        
        try:
            self.logger.info("Initializing hardware interface layer...")
            
            # Initialize managers
            await self.i2c_manager.initialize(self.config.i2c.bus_number)
            await self.gpio_manager.initialize()
            
            await self.camera_manager.initialize(
                width=self.config.camera.width,
                height=self.config.camera.height,
                fps=self.config.camera.fps
            )
            
            # Load enabled plugins
            for plugin_config in self.config.plugins:
                if plugin_config.enabled:
                    # Determine plugin type based on name/parameters
                    plugin_type = self._determine_plugin_type(plugin_config)
                    success = await self.plugin_manager.load_plugin(
                        plugin_config.name, plugin_type, plugin_config
                    )
                    
                    if not success:
                        self.logger.warning(
                            f"Failed to load plugin: {plugin_config.name}"
                        )
            
            # Start camera capture
            await self.camera_manager.start_capture()
            
            # Start health monitoring
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            
            self._initialized = True
            self.logger.info("Hardware interface layer initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize hardware interface: {e}")
            return False
    
    def _determine_plugin_type(self, plugin_config) -> str:
        """Determine plugin type from configuration"""
        name = plugin_config.name.lower()
        
        if 'tof' in name:
            return 'tof_sensor'
        elif 'power' in name:
            return 'power_monitor'
        elif 'robohat' in name:
            return 'robohat'
        elif 'gps' in name:
            return 'gps_sensor'
        elif 'imu' in name:
            return 'imu_sensor'
        elif 'environmental' in name or 'bme' in name:
            return 'environmental_sensor'
        elif 'weather' in name:
            return 'weather_service'
        else:
            return 'generic_sensor'
    
    async def shutdown(self):
        """Shutdown all hardware components"""
        self.logger.info("Shutting down hardware interface layer...")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Stop health checking
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Shutdown plugins
        await self.plugin_manager.shutdown_all()
        
        # Stop camera
        await self.camera_manager.stop_capture()
        
        self._initialized = False
        self.logger.info("Hardware interface layer shut down")
    
    async def get_sensor_data(self, sensor_name: str) -> Optional[SensorReading]:
        """Get latest sensor data"""
        plugin = self.plugin_manager.get_plugin(sensor_name)
        if plugin is None:
            raise DeviceNotFoundError(f"Sensor not found: {sensor_name}")
        
        try:
            reading = await plugin.read_data()
            if reading:
                async with self._cache_lock:
                    self._sensor_data_cache[sensor_name] = reading
            return reading
            
        except Exception as e:
            self.logger.error(f"Failed to read sensor {sensor_name}: {e}")
            return None
    
    async def get_all_sensor_data(self) -> Dict[str, SensorReading]:
        """Get data from all sensors"""
        tasks = []
        plugin_names = []
        
        for plugin_name in self.plugin_manager.list_plugins():
            plugin = self.plugin_manager.get_plugin(plugin_name)
            if plugin and plugin.plugin_type in ['i2c_sensor', 'serial_device']:
                tasks.append(plugin.read_data())
                plugin_names.append(plugin_name)
        
        if not tasks:
            return {}
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        sensor_data = {}
        
        for name, result in zip(plugin_names, results):
            if isinstance(result, Exception):
                self.logger.error(f"Error reading {name}: {result}")
            elif result is not None:
                sensor_data[name] = result
        
        # Update cache
        async with self._cache_lock:
            self._sensor_data_cache.update(sensor_data)
        
        return sensor_data
    
    async def get_cached_sensor_data(self) -> Dict[str, SensorReading]:
        """Get cached sensor data"""
        async with self._cache_lock:
            return self._sensor_data_cache.copy()
    
    async def send_robohat_command(self, command: str, *args) -> bool:
        """Send command to RoboHAT controller"""
        robohat = self.plugin_manager.get_plugin('robohat')
        if robohat is None:
            raise DeviceNotFoundError("RoboHAT plugin not found")
        
        try:
            if command == 'pwm' and len(args) == 2:
                return await robohat.send_pwm_command(args[0], args[1])
            elif command == 'rc_disable':
                return await robohat.managers['serial'].write_command('robohat', 'rc=disable')
            elif command == 'rc_enable':
                return await robohat.managers['serial'].write_command('robohat', 'rc=enable')
            elif command == 'enc_zero':
                return await robohat.managers['serial'].write_command('robohat', 'enc=zero')
            else:
                raise ValueError(f"Unknown RoboHAT command: {command}")
                
        except Exception as e:
            self.logger.error(f"RoboHAT command failed: {e}")
            return False
    
    async def get_camera_frame(self):
        """Get latest camera frame"""
        return await self.camera_manager.get_latest_frame()
    
    async def control_gpio_pin(self, pin_name: str, value: int):
        """Control GPIO pin by name"""
        if pin_name not in self.config.gpio.pins:
            raise DeviceNotFoundError(f"GPIO pin not found: {pin_name}")
        
        pin_number = self.config.gpio.pins[pin_name]
        await self.gpio_manager.write_pin(pin_number, value)
    
    async def read_gpio_pin(self, pin_name: str) -> int:
        """Read GPIO pin by name"""
        if pin_name not in self.config.gpio.pins:
            raise DeviceNotFoundError(f"GPIO pin not found: {pin_name}")
        
        pin_number = self.config.gpio.pins[pin_name]
        return await self.gpio_manager.read_pin(pin_number)
    
    async def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health status"""
        health_status = {
            'overall_healthy': True,
            'timestamp': datetime.now(),
            'managers': {},
            'plugins': {},
            'devices': {}
        }
        
        # Check plugin health
        plugin_health = await self.plugin_manager.health_check_all()
        health_status['plugins'] = plugin_health
        
        # Check I2C devices
        for device_name, address in self.i2c_manager.devices.items():
            device_health = self.i2c_manager.get_device_health(address)
            health_status['devices'][device_name] = {
                'healthy': device_health.is_healthy,
                'success_rate': device_health.success_rate,
                'consecutive_failures': device_health.consecutive_failures,
                'last_success': device_health.last_successful_read
            }
        
        # Overall health check
        all_healthy = all(plugin_health.values()) and all(
            dev['healthy'] for dev in health_status['devices'].values()
        )
        health_status['overall_healthy'] = all_healthy
        
        return health_status
    
    async def _health_check_loop(self):
        """Periodic health check loop"""
        while not self._shutdown_event.is_set():
            try:
                health_status = await self.get_system_health()
                
                if not health_status['overall_healthy']:
                    self.logger.warning("System health check failed")
                    
                    # Attempt to recover unhealthy plugins
                    for plugin_name, healthy in health_status['plugins'].items():
                        if not healthy:
                            self.logger.info(f"Attempting to recover plugin: {plugin_name}")
                            success = await self.plugin_manager.reload_plugin(plugin_name)
                            if success:
                                self.logger.info(f"Plugin {plugin_name} recovered")
                            else:
                                self.logger.error(f"Failed to recover plugin {plugin_name}")
                
                # Wait before next check
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Health check error: {e}")
                await asyncio.sleep(5)  # Short delay on error
    
    async def scan_i2c_devices(self) -> List[int]:
        """Scan for I2C devices"""
        return await self.i2c_manager.scan_devices()
    
    def is_initialized(self) -> bool:
        """Check if hardware interface is initialized"""
        return self._initialized
    
    def list_available_sensors(self) -> List[str]:
        """List all available sensors"""
        return self.plugin_manager.list_plugins()
    
    async def add_sensor(self, sensor_name: str, sensor_type: str, 
                        parameters: Dict[str, Any]) -> bool:
        """Dynamically add a new sensor"""
        from .plugin_system import PluginConfig
        
        config = PluginConfig(
            name=sensor_name,
            enabled=True,
            parameters=parameters
        )
        
        success = await self.plugin_manager.load_plugin(sensor_name, sensor_type, config)
        
        if success:
            # Update configuration
            self.config_manager.update_plugin_config(sensor_name, parameters)
            self.logger.info(f"Sensor {sensor_name} added successfully")
        
        return success
    
    async def remove_sensor(self, sensor_name: str) -> bool:
        """Dynamically remove a sensor"""
        success = await self.plugin_manager.unload_plugin(sensor_name)
        
        if success:
            # Update configuration
            self.config_manager.enable_plugin(sensor_name, False)
            self.logger.info(f"Sensor {sensor_name} removed successfully")
        
        return success


# Convenience function for creating hardware interface
def create_hardware_interface(config_path: Optional[str] = None) -> HardwareInterface:
    """Create and return hardware interface instance"""
    return HardwareInterface(config_path)
