"""Configuration management for hardware interface layer"""

import json
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import logging

from .plugin_system import PluginConfig
from .exceptions import DeviceConfigurationError


@dataclass
class I2CConfig:
    """I2C bus configuration"""
    bus_number: int = 1
    devices: Dict[str, int] = None
    
    def __post_init__(self):
        if self.devices is None:
            self.devices = {
                'tof_left': 0x29,
                'tof_right': 0x30,
                'power_monitor': 0x40,
                'environmental': 0x76,
                'display': 0x3c
            }


@dataclass
class SerialConfig:
    """Serial device configuration"""
    devices: Dict[str, Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.devices is None:
            self.devices = {
                'robohat': {'port': '/dev/ttyACM1', 'baud': 115200, 'timeout': 1.0},
                'gps': {'port': '/dev/ttyACM0', 'baud': 38400, 'timeout': 1.0},
                'imu': {'port': '/dev/ttyAMA4', 'baud': 3000000, 'timeout': 0.1}
            }


@dataclass
class GPIOConfig:
    """GPIO pin configuration"""
    pins: Dict[str, int] = None
    
    def __post_init__(self):
        if self.pins is None:
            self.pins = {
                'tof_left_shutdown': 22,
                'tof_right_shutdown': 23,
                'tof_left_interrupt': 6,
                'tof_right_interrupt': 12,
                'blade_enable': 24,
                'blade_direction': 25
            }


@dataclass
class CameraConfig:
    """Camera configuration"""
    device_path: str = '/dev/video0'
    width: int = 1920
    height: int = 1080
    fps: int = 30
    buffer_size: int = 5


@dataclass
class HardwareInterfaceConfig:
    """Main hardware interface configuration"""
    i2c: I2CConfig
    serial: SerialConfig
    gpio: GPIOConfig
    camera: CameraConfig
    plugins: List[PluginConfig]
    logging_level: str = 'INFO'
    retry_attempts: int = 3
    retry_base_delay: float = 0.1
    retry_max_delay: float = 5.0
    
    def __post_init__(self):
        if not isinstance(self.i2c, I2CConfig):
            self.i2c = I2CConfig(**self.i2c if isinstance(self.i2c, dict) else {})
        if not isinstance(self.serial, SerialConfig):
            self.serial = SerialConfig(**self.serial if isinstance(self.serial, dict) else {})
        if not isinstance(self.gpio, GPIOConfig):
            self.gpio = GPIOConfig(**self.gpio if isinstance(self.gpio, dict) else {})
        if not isinstance(self.camera, CameraConfig):
            self.camera = CameraConfig(**self.camera if isinstance(self.camera, dict) else {})


class ConfigManager:
    """Manages hardware interface configuration"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path or Path("config/hardware.yaml")
        self._config: Optional[HardwareInterfaceConfig] = None
    
    def load_config(self) -> HardwareInterfaceConfig:
        """Load configuration from file"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    if self.config_path.suffix.lower() == '.json':
                        data = json.load(f)
                    else:
                        data = yaml.safe_load(f)
                
                # Convert plugin configs
                if 'plugins' in data:
                    plugins = []
                    for plugin_data in data['plugins']:
                        plugins.append(PluginConfig(**plugin_data))
                    data['plugins'] = plugins
                else:
                    data['plugins'] = []
                
                self._config = HardwareInterfaceConfig(**data)
                self.logger.info(f"Configuration loaded from {self.config_path}")
            else:
                self._config = self.get_default_config()
                self.save_config()
                self.logger.info("Using default configuration")
            
            return self._config
            
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            raise DeviceConfigurationError(f"Configuration load error: {e}")
    
    def save_config(self):
        """Save configuration to file"""
        if self._config is None:
            return
        
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to dict and handle special types
            data = asdict(self._config)
            
            with open(self.config_path, 'w') as f:
                if self.config_path.suffix.lower() == '.json':
                    json.dump(data, f, indent=2)
                else:
                    yaml.dump(data, f, default_flow_style=False, indent=2)
            
            self.logger.info(f"Configuration saved to {self.config_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to save configuration: {e}")
            raise DeviceConfigurationError(f"Configuration save error: {e}")
    
    def get_default_config(self) -> HardwareInterfaceConfig:
        """Get default hardware configuration"""
        default_plugins = [
            PluginConfig(
                name="tof_left",
                enabled=True,
                parameters={
                    "i2c_address": 0x29,
                    "shutdown_pin": 22,
                    "interrupt_pin": 6
                }
            ),
            PluginConfig(
                name="tof_right", 
                enabled=True,
                parameters={
                    "i2c_address": 0x30,
                    "shutdown_pin": 23,
                    "interrupt_pin": 12
                }
            ),
            PluginConfig(
                name="power_monitor",
                enabled=True,
                parameters={
                    "i2c_address": 0x40,
                    "channel": 1
                }
            ),
            PluginConfig(
                name="robohat",
                enabled=True,
                parameters={}
            )
        ]
        
        return HardwareInterfaceConfig(
            i2c=I2CConfig(),
            serial=SerialConfig(), 
            gpio=GPIOConfig(),
            camera=CameraConfig(),
            plugins=default_plugins
        )
    
    def update_plugin_config(self, plugin_name: str, parameters: Dict[str, Any]):
        """Update plugin configuration"""
        if self._config is None:
            self.load_config()
        
        for plugin in self._config.plugins:
            if plugin.name == plugin_name:
                plugin.parameters.update(parameters)
                break
        else:
            # Plugin not found, add new one
            self._config.plugins.append(PluginConfig(
                name=plugin_name,
                enabled=True,
                parameters=parameters
            ))
        
        self.save_config()
    
    def enable_plugin(self, plugin_name: str, enabled: bool = True):
        """Enable or disable a plugin"""
        if self._config is None:
            self.load_config()
        
        for plugin in self._config.plugins:
            if plugin.name == plugin_name:
                plugin.enabled = enabled
                break
        
        self.save_config()
    
    def get_plugin_config(self, plugin_name: str) -> Optional[PluginConfig]:
        """Get configuration for specific plugin"""
        if self._config is None:
            self.load_config()
        
        for plugin in self._config.plugins:
            if plugin.name == plugin_name:
                return plugin
        
        return None
    
    @property
    def config(self) -> HardwareInterfaceConfig:
        """Get current configuration"""
        if self._config is None:
            self.load_config()
        return self._config
