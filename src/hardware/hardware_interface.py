"""Main hardware interface layer coordinating all managers"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from pathlib import Path

from .managers import I2CManager, SerialManager, CameraManager, GPIOManager
from .display_manager import OLEDDisplayManager
from .plugin_system import PluginManager, HardwarePlugin
from .config import ConfigManager, HardwareInterfaceConfig
from .data_structures import SensorReading, DeviceHealth
from .exceptions import HardwareError, DeviceNotFoundError
from .tof_manager import ToFSensorManager


class HardwareInterface:
    """Main hardware interface coordinating all subsystems"""
    
    def __init__(self, config_path: Optional[Union[str, Dict[str, Any]]] = None):
        self.logger = logging.getLogger(__name__)

        # Configuration
        # Accept either a path to config or an in-memory dict for tests
        if isinstance(config_path, dict):
            # Create a ConfigManager with default path but inject the provided dict
            self.config_manager = ConfigManager(None)
            try:
                # Build HardwareInterfaceConfig from provided dict
                self.config = HardwareInterfaceConfig(**config_path)
            except Exception:
                # Fallback: load defaults if provided dict is incomplete
                self.config = self.config_manager.get_default_config()
            # Store into manager for later updates
            self.config_manager._config = self.config
        else:
            self.config_manager = ConfigManager(config_path)
            self.config = self.config_manager.load_config()
        
        # Hardware managers
        self.i2c_manager = I2CManager()
        self.serial_manager = SerialManager()
        # Apply serial device mapping from configuration so plugins use correct ports/bauds
        try:
            if self.config and getattr(self.config, 'serial', None):
                # Ensure we copy to avoid accidental shared mutations
                self.serial_manager.devices = dict(self.config.serial.devices or {})
                # Diagnostics: log effective serial mapping for verification under systemd
                try:
                    self.logger.info(
                        "Serial mapping applied from config: %s",
                        {k: {"port": v.get("port"), "baud": v.get("baud"), "timeout": v.get("timeout")} for k, v in self.serial_manager.devices.items()}
                    )
                except Exception:
                    pass
        except Exception:
            # Fall back to defaults if config mapping is unavailable
            pass

        # Apply I2C device mapping from configuration to the I2C manager
        try:
            if self.config and getattr(self.config, 'i2c', None):
                cfg_i2c_devices = dict(self.config.i2c.devices or {})
                if cfg_i2c_devices:
                    self.i2c_manager.devices.update(cfg_i2c_devices)
                    try:
                        self.logger.info(
                            "I2C mapping applied from config: %s",
                            {name: f"0x{addr:02x}" for name, addr in self.i2c_manager.devices.items()}
                        )
                    except Exception:
                        pass
        except Exception:
            pass

        # Managers that depend on config but are not bus-mapped
        self.camera_manager = CameraManager(self.config.camera.device_path)
        self.gpio_manager = GPIOManager()
        self.tof_manager = ToFSensorManager(gpio_manager=self.gpio_manager)
        self.display_manager = OLEDDisplayManager()

        # Plugin system
        self.plugin_manager = PluginManager({
            'i2c': self.i2c_manager,
            'serial': self.serial_manager,
            'camera': self.camera_manager,
            'gpio': self.gpio_manager,
            'tof': self.tof_manager
        })
        
        # Set the shared ToF manager to avoid double initialization
        self.plugin_manager._shared_tof_manager = self.tof_manager
        
        # State
        self._initialized = False
        self._initialized_at: Optional[datetime] = None
        self._shutdown_event = asyncio.Event()
        self._health_check_task = None
        self._sensor_data_cache: Dict[str, SensorReading] = {}
        self._cache_lock = asyncio.Lock()
        
        # Setup logging
        try:
            logging.basicConfig(level=getattr(logging, self.config.logging_level))
        except Exception:
            # Fallback to INFO if config is missing or malformed
            logging.basicConfig(level=logging.INFO)
        # Always log config source path and basic I2C map for visibility
        try:
            self.logger.info("HardwareInterface using config at: %s", getattr(self.config_manager, 'config_path', 'unknown'))
        except Exception:
            pass
    
    async def initialize(self) -> bool:
        """Initialize all hardware components"""
        if self._initialized:
            return True
        
        try:
            self.logger.info("Initializing hardware interface layer...")
            
            # Initialize managers
            await self.i2c_manager.initialize(self.config.i2c.bus_number)
            # Diagnostics: log effective I2C device map
            try:
                self.logger.info(
                    "I2C device map: %s",
                    {name: f"0x{addr:02x}" for name, addr in self.i2c_manager.devices.items()}
                )
            except Exception:
                pass
            await self.gpio_manager.initialize()
            # OLED is optional; initialize but continue on failure
            try:
                await self.display_manager.initialize()
            except Exception as e:
                self.logger.warning(f"OLED display not available: {e}")
            # Register serial write listener to mirror RoboHAT commands
            try:
                async def _on_serial_write(device_name: str, command: str, success: bool):
                    if device_name == 'robohat' and self.display_manager.enabled:
                        await self.display_manager.log_robohat_command(command, success)
                self.serial_manager.add_write_listener(_on_serial_write)
            except Exception:
                pass
            
            # Initialize ToF sensor manager (non-fatal)
            try:
                tof_success = await self.tof_manager.initialize()
                if tof_success:
                    self.logger.info("ToF sensor manager initialized successfully")
                else:
                    self.logger.warning("ToF sensor manager initialization failed - continuing without ToF sensors")
            except Exception as e:
                self.logger.warning(f"ToF manager init error - continuing without ToF: {e}")
            
            # Camera may be owned by the Web API process; allow disabling here via env
            import os
            disable_camera = os.environ.get("LAWNBERY_DISABLE_CAMERA", "0").lower() in ("1", "true", "yes")
            if disable_camera:
                self.logger.info("Camera initialization disabled by LAWNBERY_DISABLE_CAMERA")
            else:
                # Camera is optional for sensor publishing; continue if absent
                try:
                    await self.camera_manager.initialize(
                        width=self.config.camera.width,
                        height=self.config.camera.height,
                        fps=self.config.camera.fps
                    )
                except Exception as e:
                    self.logger.warning(f"Camera not available: {e}")
            
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
            
            # Start camera capture only if camera manager initialized successfully
            try:
                if not disable_camera:
                    if getattr(self.camera_manager, '_camera', None) is not None or getattr(self.camera_manager, '_picam2', None) is not None:
                        await self.camera_manager.start_capture()
                    else:
                        self.logger.debug("Camera manager not initialized; skipping start_capture")
            except Exception as e:
                self.logger.debug(f"Skipping camera start_capture due to error: {e}")
            
            # Start health monitoring
            self._health_check_task = asyncio.create_task(self._health_check_loop())

            # Record the time of initialization to allow a short grace period
            try:
                self._initialized_at = datetime.now()
            except Exception:
                self._initialized_at = None
            
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
        # Shutdown plugins with bounded timeout to avoid blocking
        try:
            await asyncio.wait_for(self.plugin_manager.shutdown_all(), timeout=10.0)
        except asyncio.TimeoutError:
            self.logger.warning("Plugin manager shutdown timed out; proceeding with cleanup")
        except Exception as e:
            self.logger.warning(f"Plugin manager shutdown error: {e}")
        
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
            # Mirror high-level command intent on OLED (pre-send)
            if self.display_manager.enabled:
                try:
                    await self.display_manager.log_robohat_command(f"CMD {command} {','.join(map(str, args))}", None)
                except Exception:
                    pass
            if command == 'pwm' and len(args) == 2:
                return await robohat.send_pwm_command(args[0], args[1])
            elif command == 'rc_disable':
                return await robohat.enable_rc_control(False)
            elif command == 'rc_enable':
                return await robohat.enable_rc_control(True)
            elif command == 'rc_mode' and len(args) == 1:
                return await robohat.set_rc_mode(args[0])
            elif command == 'blade_control' and len(args) == 1:
                return await robohat.set_blade_control(args[0] == 'true')
            elif command == 'configure_channel' and len(args) >= 2:
                channel = int(args[0])
                function = args[1]
                min_val = int(args[2]) if len(args) > 2 else 1000
                max_val = int(args[3]) if len(args) > 3 else 2000
                center_val = int(args[4]) if len(args) > 4 else 1500
                if hasattr(robohat, 'configure_channel'):
                    return await robohat.configure_channel(channel, function, min_val, max_val, center_val)
                return False
            elif command == 'get_rc_status':
                status = await robohat.get_rc_status() if hasattr(robohat, 'get_rc_status') else None
                return status is not None
            elif command == 'enc_zero':
                return await robohat.managers['serial'].write_command('robohat', 'enc=zero')
            else:
                raise ValueError(f"Unknown RoboHAT command: {command}")
                
        except Exception as e:
            self.logger.error(f"RoboHAT command failed: {e}")
            return False
    
    async def get_rc_status_data(self) -> Dict[str, Any]:
        """Get RC status data for API responses"""
        robohat = self.plugin_manager.get_plugin('robohat')
        if robohat and hasattr(robohat, 'get_rc_status'):
            status = await robohat.get_rc_status()
            return status or {}
        return {}

    async def get_camera_frame(self):
        """Get latest camera frame"""
        return await self.camera_manager.get_latest_frame()
    
    async def control_gpio_pin(self, pin_name: str, value: int):
        """Control GPIO pin by name"""
        if pin_name not in self.config.gpio.pins:
            raise DeviceNotFoundError(f"GPIO pin not found: {pin_name}")
        
        pin_number = self.config.gpio.pins[pin_name]
        await self.gpio_manager.write_pin(pin_number, value)


    def set_manual_override(self, component: str, override_config: Dict[str, Any]) -> None:
        """Set manual override for hardware component"""
        # Store manual overrides in the interface for now
        if not hasattr(self, 'manual_overrides'):
            self.manual_overrides = {}
        self.manual_overrides[component] = override_config
        self.logger.info(f"Manual override set for {component}")
    
    def get_hardware_capabilities(self) -> Dict[str, Any]:
        """Get current hardware capabilities and feature matrix"""
        capabilities: Dict[str, Any] = {
            'available_features': [],
            'degraded_features': [],
            'unavailable_features': [],
            'component_status': {},
            'alternative_hardware': {},
            'software_fallbacks': {}
        }
        
        # Check component status
        for name in self.plugin_manager.list_plugins():
            plugin = self.plugin_manager.get_plugin(name)
            if plugin and hasattr(plugin, 'health') and hasattr(plugin.health, 'is_healthy'):
                capabilities['component_status'][name] = plugin.health.is_healthy()
            else:
                capabilities['component_status'][name] = False
        
        # Define feature matrix
        feature_matrix = {
            'obstacle_detection': {
                'required': ['camera'],
                'optional': ['tof_left', 'tof_right'],
                'alternatives': ['ultrasonic_sensors', 'lidar'],
                'fallback': 'vision_only_detection'
            },
            'navigation': {
                'required': ['gps'],
                'optional': ['imu'],
                'alternatives': ['rtk_gps', 'dual_gps'],
                'fallback': 'dead_reckoning'
            },
            'power_monitoring': {
                'required': ['power_monitor'],
                'optional': ['voltage_sensor'],
                'alternatives': ['ina219', 'voltage_divider'],
                'fallback': 'software_estimation'
            },
            'environmental_sensing': {
                'required': [],
                'optional': ['environmental'],
                'alternatives': ['dht22', 'bmp280'],
                'fallback': 'weather_api'
            },
            'communication': {
                'required': ['robohat'],
                'optional': [],
                'alternatives': ['arduino', 'pico'],
                'fallback': 'direct_gpio'
            }
        }
        
        # Evaluate features
        for feature_name, requirements in feature_matrix.items():
            required_available = all(
                capabilities['component_status'].get(comp, False)
                for comp in requirements['required']
            )
            
            if required_available:
                optional_available = any(
                    capabilities['component_status'].get(comp, False)
                    for comp in requirements['optional']
                ) if requirements['optional'] else True
                
                if optional_available:
                    capabilities['available_features'].append(feature_name)
                else:
                    capabilities['degraded_features'].append(feature_name)
            else:
                capabilities['unavailable_features'].append(feature_name)
                capabilities['alternative_hardware'][feature_name] = requirements['alternatives']
                capabilities['software_fallbacks'][feature_name] = requirements['fallback']
        
        return capabilities
    
    def validate_hardware_configuration(self, component: str, config: Dict[str, Any]) -> List[str]:
        """Validate hardware configuration with comprehensive checks"""
        errors = []
        
        # Basic validation
        if not component:
            errors.append("Component name is required")
        
        if not config:
            errors.append("Configuration is required")
            return errors
        
        # Component-specific validation
        component_type = self._determine_plugin_type_from_name(component)
        
        if component_type == 'tof_sensor':
            if 'address' not in config:
                errors.append("I2C address required for ToF sensor")
            elif not isinstance(config['address'], int) or not (0x08 <= config['address'] <= 0x77):
                errors.append("Invalid I2C address for ToF sensor")
        
        elif component_type == 'camera':
            if 'device_path' not in config:
                errors.append("Device path required for camera")
            elif not Path(config['device_path']).exists():
                errors.append(f"Camera device not found: {config['device_path']}")
        
        elif component_type in ['gps_sensor', 'communication']:
            if 'port' not in config:
                errors.append("Serial port required")
            elif not Path(config['port']).exists():
                errors.append(f"Serial port not found: {config['port']}")
        
        return errors
    
    def _determine_plugin_type_from_name(self, component_name: str) -> str:
        """Determine plugin type from component name"""
        name = component_name.lower()
        
        if 'tof' in name:
            return 'tof_sensor'
        elif 'power' in name:
            return 'power_sensor'
        elif 'camera' in name:
            return 'camera'
        elif 'gps' in name:
            return 'gps_sensor'
        elif 'imu' in name:
            return 'imu_sensor'
        elif 'environmental' in name or 'weather' in name:
            return 'environmental_sensor'
        elif 'robohat' in name:
            return 'communication'
        else:
            return 'generic'
    
    def get_alternative_configurations(self, component: str) -> List[Dict[str, Any]]:
        """Get alternative hardware configurations for component"""
        component_type = self._determine_plugin_type_from_name(component)
        alternatives = []
        
        if component_type == 'tof_sensor':
            alternatives = [
                {'model': 'VL53L1X', 'address': 0x29, 'description': 'Enhanced ToF sensor'},
                {'model': 'HC-SR04', 'trigger_pin': 18, 'echo_pin': 24, 'description': 'Ultrasonic sensor'},
                {'model': 'VL53L4CD', 'address': 0x52, 'description': 'Long-range ToF sensor'}
            ]
        elif component_type == 'camera':
            alternatives = [
                {'model': 'Pi Camera v3', 'device_path': '/dev/video0', 'description': 'Latest Pi Camera'},
                {'model': 'USB Camera', 'device_path': '/dev/video1', 'description': 'Generic USB camera'},
                {'model': 'IP Camera', 'url': 'rtsp://192.168.1.100', 'description': 'Network camera'}
            ]
        elif component_type == 'gps_sensor':
            alternatives = [
                {'model': 'Generic GPS', 'port': '/dev/ttyUSB0', 'baud': 9600, 'description': 'Standard GPS receiver'},
                {'model': 'Pi Hat GPS', 'port': '/dev/ttyAMA0', 'baud': 9600, 'description': 'Pi Hat GPS module'}
            ]
        elif component_type == 'power_sensor':
            alternatives = [
                {'model': 'INA219', 'address': 0x41, 'description': 'Alternative power monitor'},
                {'model': 'Voltage Divider', 'pin': 'A0', 'description': 'Simple voltage monitoring'}
            ]
        
        return alternatives

    
    async def read_gpio_pin(self, pin_name: str) -> int:
        """Read GPIO pin by name"""
        if pin_name not in self.config.gpio.pins:
            raise DeviceNotFoundError(f"GPIO pin not found: {pin_name}")
        
        pin_number = self.config.gpio.pins[pin_name]
        return await self.gpio_manager.read_pin(pin_number)
    
    async def read_tof_sensor(self, sensor_name: str) -> Optional[Dict[str, Any]]:
        """Read distance from a specific ToF sensor"""
        if not self.tof_manager._initialized:
            self.logger.warning("ToF manager not initialized")
            return None
        
        try:
            reading = await self.tof_manager.read_sensor(sensor_name)
            if reading:
                return {
                    'sensor_name': reading.sensor_name,
                    'distance_mm': reading.distance_mm,
                    'range_status': reading.range_status,
                    'address': reading.address,
                    'timestamp': reading.timestamp
                }
            return None
        except Exception as e:
            self.logger.error(f"Failed to read ToF sensor {sensor_name}: {e}")
            return None
    
    async def read_all_tof_sensors(self) -> Dict[str, Dict[str, Any]]:
        """Read distances from all ToF sensors"""
        if not self.tof_manager._initialized:
            self.logger.warning("ToF manager not initialized")
            return {}
        
        try:
            readings = await self.tof_manager.read_all_sensors()
            result = {}
            
            for sensor_name, reading in readings.items():
                result[sensor_name] = {
                    'distance_mm': reading.distance_mm,
                    'range_status': reading.range_status,
                    'address': reading.address,
                    'timestamp': reading.timestamp
                }
            
            return result
        except Exception as e:
            self.logger.error(f"Failed to read ToF sensors: {e}")
            return {}
    
    def get_tof_sensor_status(self) -> Dict[str, Dict]:
        """Get status of all ToF sensors. Always ask the manager for status -
        the manager can surface lifecycle information even before marking
        itself fully initialized (useful for health aggregation and diagnostics).
        """
        try:
            return self.tof_manager.get_sensor_status()
        except Exception:
            return {"status": "not_initialized"}
    
    async def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health status"""
        health_status = {
            'overall_healthy': True,
            'timestamp': datetime.now(),
            'managers': {},
            'plugins': {},
            'devices': {},
            'sensors': {}
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
        
        # Check ToF sensors specifically. Ask manager for per-sensor lifecycle
        # statuses and decide whether ToF health should factor into overall
        # system health. This is more flexible than requiring the manager's
        # `_initialized` flag because it surfaces progress (initializing -> ok).
        try:
            tof_status = self.get_tof_sensor_status()
            health_status['sensors']['tof'] = tof_status

            grace_seconds = getattr(self.config, 'health_grace_seconds', 5)
            now = datetime.now()
            initialized_age = None
            if self._initialized_at:
                try:
                    initialized_age = (now - self._initialized_at).total_seconds()
                except Exception:
                    initialized_age = None

            # Collect lifecycle statuses reported by the manager
            if isinstance(tof_status, dict):
                sensor_statuses = [s.get('status', 'unknown') for s in tof_status.values()]
            else:
                sensor_statuses = []

            sensor_ok = any(st == 'ok' for st in sensor_statuses)
            sensor_initializing = any(st == 'initializing' for st in sensor_statuses)

            # If any sensor is 'ok', consider ToF portion healthy. If none are 'ok'
            # but some are 'initializing', allow a grace period after interface
            # startup before declaring overall unhealthy.
            if sensor_ok:
                # nothing to change - sensors are producing valid reads
                pass
            else:
                # No sensor reported 'ok'
                if initialized_age is None or (initialized_age < grace_seconds):
                    # Within grace - don't mark overall unhealthy yet
                    health_status['sensors']['tof_status'] = 'initializing'
                else:
                    # Past grace period - mark overall unhealthy
                    health_status['overall_healthy'] = False

        except Exception:
            # If we can't query ToF manager at all, conservatively mark unhealthy
            health_status['sensors']['tof'] = {"status": "not_initialized"}
            health_status['overall_healthy'] = False
        
        # Overall health check
        # Require core plugins to be healthy (robohat/power_monitor if present) and
        # require at least one device health to be True (to avoid false negatives
        # from optional/unavailable devices). Finally combine with sensor checks
        try:
            core_plugins_ok = True
            # If these plugins exist, prefer them as core checks
            for core in ('robohat', 'power_monitor'):
                if core in plugin_health:
                    core_plugins_ok = core_plugins_ok and bool(plugin_health.get(core))
        except Exception:
            core_plugins_ok = all(plugin_health.values()) if plugin_health else True

        try:
            any_device_ok = any(dev.get('healthy', False) for dev in health_status['devices'].values()) if health_status['devices'] else True
        except Exception:
            any_device_ok = True

        all_healthy = core_plugins_ok and any_device_ok and health_status['overall_healthy']
        health_status['overall_healthy'] = bool(all_healthy)
        
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

    async def cleanup(self):
        """Clean up all hardware resources"""
        self.logger.info("Starting hardware interface cleanup...")
        
        try:
            # Signal shutdown
            self._shutdown_event.set()
            
            # Stop health check task if running
            if self._health_check_task and not self._health_check_task.done():
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
            
            # Cleanup all managers with timeout protection
            cleanup_tasks = []
            
            # ToF manager cleanup (use _cleanup if available else shutdown)
            try:
                if hasattr(self.tof_manager, '_cleanup'):
                    cleanup_tasks.append(
                        asyncio.create_task(
                            asyncio.wait_for(self.tof_manager._cleanup(), timeout=10.0),
                            name="tof_cleanup"
                        )
                    )
                elif hasattr(self.tof_manager, 'shutdown'):
                    cleanup_tasks.append(
                        asyncio.create_task(
                            asyncio.wait_for(self.tof_manager.shutdown(), timeout=10.0),
                            name="tof_shutdown"
                        )
                    )
            except Exception as e:
                self.logger.debug(f"Error scheduling ToF cleanup: {e}")
            
            # GPIO manager cleanup  
            if hasattr(self.gpio_manager, 'cleanup'):
                cleanup_tasks.append(
                    asyncio.create_task(
                        asyncio.wait_for(self.gpio_manager.cleanup(), timeout=5.0),
                        name="gpio_cleanup"
                    )
                )
            
            # Serial manager cleanup
            if hasattr(self.serial_manager, 'cleanup'):
                cleanup_tasks.append(
                    asyncio.create_task(
                        asyncio.wait_for(self.serial_manager.cleanup(), timeout=5.0),
                        name="serial_cleanup"
                    )
                )
            
            # I2C manager cleanup
            if hasattr(self.i2c_manager, 'cleanup'):
                cleanup_tasks.append(
                    asyncio.create_task(
                        asyncio.wait_for(self.i2c_manager.cleanup(), timeout=5.0),
                        name="i2c_cleanup"
                    )
                )
            
            # Camera manager cleanup
            if hasattr(self.camera_manager, 'cleanup'):
                cleanup_tasks.append(
                    asyncio.create_task(
                        asyncio.wait_for(self.camera_manager.cleanup(), timeout=5.0),
                        name="camera_cleanup"
                    )
                )
            # Display manager has no explicit cleanup; screen remains with last frame
            
            # Wait for all cleanup tasks to complete
            if cleanup_tasks:
                results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        self.logger.warning(f"Cleanup task {cleanup_tasks[i].get_name()} failed: {result}")
                    else:
                        self.logger.debug(f"Cleanup task {cleanup_tasks[i].get_name()} completed successfully")
            
            # Clear state
            self._sensor_data_cache.clear()
            self._initialized = False
            
            self.logger.info("Hardware interface cleanup completed")
            
        except Exception as e:
            self.logger.error(f"Error during hardware cleanup: {e}")
            raise


# Module-level registry for shared hardware interface instances
_shared_hardware_interfaces: Dict[Optional[str], HardwareInterface] = {}


def create_hardware_interface(config_path: Optional[str] = None, *, shared: bool = True, force_new: bool = False) -> HardwareInterface:
    """Create and return a HardwareInterface instance.

    By default this returns a process-wide shared instance for a given
    `config_path` to avoid multiple components initializing the same
    hardware devices. Pass `shared=False` or `force_new=True` to get a
    fresh instance (useful for tests).
    """
    # Normalize the config_path to a hashable key. If a dict/list is provided
    # (e.g., tests passing an in-memory config), convert to a stable JSON string.
    import json
    if config_path is None:
        key = '__default__'
    elif isinstance(config_path, (dict, list)):
        try:
            key = json.dumps(config_path, sort_keys=True)
        except Exception:
            # Fallback to string representation if it can't be JSON serialized
            key = str(config_path)
    else:
        key = str(config_path)
    if not shared or force_new:
        return HardwareInterface(config_path)

    # Return existing shared instance if present
    existing = _shared_hardware_interfaces.get(key)
    if existing is not None:
        return existing

    # Create, cache and return shared instance
    hw = HardwareInterface(config_path)
    _shared_hardware_interfaces[key] = hw
    return hw
