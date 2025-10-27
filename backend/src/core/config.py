"""Configuration management with atomic writes and validation.

This module provides thread-safe configuration management for the LawnBerry Pi v2 system,
supporting JSON-based configuration files with atomic writes, validation, and fallback
to default values when configuration is missing or invalid.
"""
import json
import logging
import tempfile
import shutil
from pathlib import Path
from threading import Lock
from typing import Dict, Any, Optional, Union
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class SystemConfigDefaults:
    """Default system configuration values."""
    mowing_height_mm: int = 30
    cutting_speed: float = 0.8
    edge_cutting_enabled: bool = True
    weather_pause_enabled: bool = True
    rain_threshold_mm: float = 2.0
    wind_threshold_kmh: float = 25.0
    charging_return_threshold: float = 20.0
    safety_tilt_threshold_degrees: float = 30.0
    gps_required_accuracy_m: float = 2.0
    obstacle_detection_sensitivity: str = "medium"
    blade_engagement_delay_ms: int = 500
    emergency_stop_timeout_s: int = 30
    telemetry_cadence_hz: float = 5.0
    log_level: str = "INFO"
    data_retention_days: int = 7


@dataclass
class NetworkConfig:
    """Network configuration."""
    wifi_ssid: str = ""
    wifi_password: str = ""
    webui_port: int = 8080
    api_port: int = 8081
    websocket_port: int = 8082
    enable_hotspot: bool = False
    hotspot_ssid: str = "LawnBerry-Pi"
    hotspot_password: str = "lawnberry123"


@dataclass
class HardwareConfig:
    """Hardware configuration and calibration."""
    imu_calibration_offset: Dict[str, float] = None
    motor_left_max_pwm: int = 255
    motor_right_max_pwm: int = 255
    blade_motor_max_pwm: int = 255
    battery_voltage_divider: float = 0.5
    current_sensor_scale: float = 1.0
    gps_baud_rate: int = 9600
    i2c_bus: int = 1
    spi_bus: int = 0
    
    def __post_init__(self):
        if self.imu_calibration_offset is None:
            self.imu_calibration_offset = {"x": 0.0, "y": 0.0, "z": 0.0}


class ConfigurationManager:
    """Thread-safe configuration management with atomic writes."""
    
    def __init__(self, config_dir: str = "./config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self._lock = Lock()
        self._config_cache: Dict[str, Dict[str, Any]] = {}
        self._load_all_configs()
    
    def _load_all_configs(self):
        """Load all configuration files into cache."""
        config_files = {
            "system": "system.json",
            "network": "network.json", 
            "hardware": "hardware.json"
        }
        
        for config_name, filename in config_files.items():
            self._load_config_file(config_name, filename)
    
    def _load_config_file(self, config_name: str, filename: str):
        """Load a specific configuration file."""
        config_path = self.config_dir / filename
        
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
                self._config_cache[config_name] = config_data
                logger.info(f"Loaded {config_name} configuration from {filename}")
            else:
                # Create default configuration
                default_config = self._get_default_config(config_name)
                self._config_cache[config_name] = default_config
                self._save_config_file(config_name, filename, default_config)
                logger.info(f"Created default {config_name} configuration")
                
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading {config_name} config: {e}")
            # Fall back to defaults
            self._config_cache[config_name] = self._get_default_config(config_name)
    
    def _get_default_config(self, config_name: str) -> Dict[str, Any]:
        """Get default configuration for a given config type."""
        defaults = {
            "system": asdict(SystemConfigDefaults()),
            "network": asdict(NetworkConfig()),
            "hardware": asdict(HardwareConfig())
        }
        return defaults.get(config_name, {})
    
    def _save_config_file(self, config_name: str, filename: str, config_data: Dict[str, Any]):
        """Atomically save configuration file."""
        config_path = self.config_dir / filename
        
        # Add metadata
        config_with_metadata = {
            "config": config_data,
            "metadata": {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "version": "2.0.0"
            }
        }
        
        # Atomic write using temporary file
        with tempfile.NamedTemporaryFile(
            mode='w', 
            dir=self.config_dir, 
            delete=False,
            suffix='.tmp'
        ) as temp_file:
            json.dump(config_with_metadata, temp_file, indent=2)
            temp_path = Path(temp_file.name)
        
        try:
            # Atomic move
            shutil.move(str(temp_path), str(config_path))
            logger.info(f"Saved {config_name} configuration to {filename}")
        except Exception as e:
            # Clean up on failure
            if temp_path.exists():
                temp_path.unlink()
            raise e
    
    def get_config(self, config_name: str) -> Dict[str, Any]:
        """Get configuration by name (thread-safe)."""
        with self._lock:
            return self._config_cache.get(config_name, {}).copy()
    
    def update_config(self, config_name: str, updates: Dict[str, Any]) -> bool:
        """Update configuration with partial updates (thread-safe)."""
        with self._lock:
            try:
                current_config = self._config_cache.get(config_name, {}).copy()
                
                # Apply updates
                current_config.update(updates)
                
                # Validate configuration
                if not self._validate_config(config_name, current_config):
                    logger.error(f"Configuration validation failed for {config_name}")
                    return False
                
                # Save to file
                filename = self._get_filename(config_name)
                self._save_config_file(config_name, filename, current_config)
                
                # Update cache
                self._config_cache[config_name] = current_config
                
                return True
                
            except Exception as e:
                logger.error(f"Error updating {config_name} config: {e}")
                return False
    
    def _get_filename(self, config_name: str) -> str:
        """Get filename for configuration type."""
        filenames = {
            "system": "system.json",
            "network": "network.json",
            "hardware": "hardware.json"
        }
        return filenames.get(config_name, f"{config_name}.json")
    
    def _validate_config(self, config_name: str, config_data: Dict[str, Any]) -> bool:
        """Validate configuration data."""
        if config_name == "system":
            return self._validate_system_config(config_data)
        elif config_name == "network":
            return self._validate_network_config(config_data)
        elif config_name == "hardware":
            return self._validate_hardware_config(config_data)
        return True
    
    def _validate_system_config(self, config: Dict[str, Any]) -> bool:
        """Validate system configuration."""
        try:
            # Validate numeric ranges
            if "mowing_height_mm" in config:
                if not (10 <= config["mowing_height_mm"] <= 100):
                    return False
            
            if "cutting_speed" in config:
                if not (0.1 <= config["cutting_speed"] <= 2.0):
                    return False
            
            if "telemetry_cadence_hz" in config:
                if not (1.0 <= config["telemetry_cadence_hz"] <= 10.0):
                    return False
            
            # Validate enum values
            if "obstacle_detection_sensitivity" in config:
                if config["obstacle_detection_sensitivity"] not in ["low", "medium", "high"]:
                    return False
            
            if "log_level" in config:
                if config["log_level"] not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
                    return False
            
            return True
            
        except (TypeError, ValueError):
            return False
    
    def _validate_network_config(self, config: Dict[str, Any]) -> bool:
        """Validate network configuration."""
        try:
            # Validate port ranges
            ports = ["webui_port", "api_port", "websocket_port"]
            for port_key in ports:
                if port_key in config:
                    port = config[port_key]
                    if not (1024 <= port <= 65535):
                        return False
            
            # Validate WiFi settings if provided
            if "wifi_ssid" in config and config["wifi_ssid"]:
                if len(config["wifi_ssid"]) > 32:
                    return False
            
            return True
            
        except (TypeError, ValueError):
            return False
    
    def _validate_hardware_config(self, config: Dict[str, Any]) -> bool:
        """Validate hardware configuration."""
        try:
            # Validate PWM values
            pwm_keys = ["motor_left_max_pwm", "motor_right_max_pwm", "blade_motor_max_pwm"]
            for pwm_key in pwm_keys:
                if pwm_key in config:
                    if not (0 <= config[pwm_key] <= 255):
                        return False
            
            # Validate bus numbers
            if "i2c_bus" in config:
                if not (0 <= config["i2c_bus"] <= 10):
                    return False
            
            if "spi_bus" in config:
                if not (0 <= config["spi_bus"] <= 2):
                    return False
            
            return True
            
        except (TypeError, ValueError):
            return False
    
    def reload_config(self, config_name: str) -> bool:
        """Reload configuration from disk."""
        with self._lock:
            try:
                filename = self._get_filename(config_name)
                self._load_config_file(config_name, filename)
                return True
            except Exception as e:
                logger.error(f"Error reloading {config_name} config: {e}")
                return False
    
    def backup_config(self, backup_dir: str) -> bool:
        """Create backup of all configuration files."""
        try:
            backup_path = Path(backup_dir)
            backup_path.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_subdir = backup_path / f"config_backup_{timestamp}"
            backup_subdir.mkdir()
            
            # Copy all config files
            for config_file in self.config_dir.glob("*.json"):
                shutil.copy2(config_file, backup_subdir)
            
            logger.info(f"Configuration backup created at {backup_subdir}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating config backup: {e}")
            return False


# Global configuration manager instance
config_manager = ConfigurationManager()