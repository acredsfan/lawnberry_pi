"""
Configuration Manager - Centralized configuration system with validation and hot reloading
"""

import asyncio
import logging
import yaml
import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass, asdict
import os
from datetime import datetime
import shutil

logger = logging.getLogger(__name__)


@dataclass
class ConfigFile:
    """Configuration file metadata"""
    path: Path
    last_modified: float
    content: Dict[str, Any]
    validated: bool = False
    errors: List[str] = None


class ConfigManager:
    """
    Centralized configuration management system
    Handles loading, validation, hot reloading, and backup/restore
    """
    
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.configs: Dict[str, ConfigFile] = {}
        self.config_schema: Dict[str, Any] = {}
        self.watchers: Dict[str, asyncio.Task] = {}
        self.change_callbacks: Dict[str, List] = {}
        
        # Environment-specific overrides
        self.environment = os.getenv('LAWNBERRY_ENV', 'production')
        self.override_dir = self.config_dir / 'overrides' / self.environment
        
        # Backup configuration
        self.backup_dir = Path('/var/lib/lawnberry/config_backups')
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    async def load_all_configs(self):
        """Load all configuration files"""
        logger.info("Loading all configuration files")
        
        # Define expected config files
        config_files = [
            'hardware.yaml',
            'communication.yaml', 
            'data_management.yaml',
            'safety.yaml',
            'sensor_fusion.yaml',
            'weather.yaml',
            'vision.yaml',
            'power_management.yaml',
            'system.yaml'  # Main system configuration
        ]
        
        # Load each config file
        for config_file in config_files:
            config_path = self.config_dir / config_file
            if config_path.exists():
                await self.load_config(config_file)
            else:
                logger.warning(f"Configuration file not found: {config_path}")
        
        # Create system.yaml if it doesn't exist
        if 'system.yaml' not in self.configs:
            await self._create_default_system_config()
        
        # Validate all configurations
        await self._validate_all_configs()
        
        logger.info(f"Loaded {len(self.configs)} configuration files")
    
    async def load_config(self, config_name: str) -> Dict[str, Any]:
        """Load a specific configuration file"""
        config_path = self.config_dir / config_name
        
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        try:
            # Load base configuration
            with open(config_path, 'r') as f:
                content = yaml.safe_load(f) or {}
            
            # Apply environment overrides if they exist  
            override_path = self.override_dir / config_name
            if override_path.exists():
                with open(override_path, 'r') as f:
                    overrides = yaml.safe_load(f) or {}
                content = self._merge_configs(content, overrides)
                logger.info(f"Applied {self.environment} overrides to {config_name}")
            
            # Store configuration
            self.configs[config_name] = ConfigFile(
                path=config_path,
                last_modified=config_path.stat().st_mtime,
                content=content,
                validated=False
            )
            
            logger.info(f"Loaded configuration: {config_name}")
            return content
            
        except Exception as e:
            logger.error(f"Failed to load configuration {config_name}: {e}")
            raise
    
    def _merge_configs(self, base: Dict, override: Dict) -> Dict:
        """Recursively merge configuration dictionaries"""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result
    
    async def _create_default_system_config(self):
        """Create default system configuration"""
        default_config = {
            'system': {
                'name': 'lawnberry-mower',
                'version': '1.0.0',
                'environment': self.environment,
                'log_level': 'INFO',
                'max_cpu_percent': 80.0,
                'max_memory_percent': 75.0,
                'health_check_interval': 5.0,
                'service_start_timeout': 30.0
            },
            'services': {
                'communication': {
                    'critical': True,
                    'restart_policy': 'always',
                    'max_restarts': 5,
                    'restart_delay': 2.0
                },
                'data_management': {
                    'critical': True,
                    'restart_policy': 'always', 
                    'max_restarts': 3,
                    'restart_delay': 5.0
                },
                'hardware': {
                    'critical': True,
                    'restart_policy': 'always',
                    'max_restarts': 3,
                    'restart_delay': 3.0
                },
                'safety': {
                    'critical': True,
                    'restart_policy': 'always',
                    'max_restarts': 5,
                    'restart_delay': 1.0
                },
                'sensor_fusion': {
                    'critical': False,
                    'restart_policy': 'on-failure',
                    'max_restarts': 3,
                    'restart_delay': 5.0
                },
                'weather': {
                    'critical': False,
                    'restart_policy': 'on-failure',
                    'max_restarts': 2,
                    'restart_delay': 10.0
                },
                'power_management': {
                    'critical': False,
                    'restart_policy': 'always',
                    'max_restarts': 3,
                    'restart_delay': 5.0
                },
                'vision': {
                    'critical': False,
                    'restart_policy': 'on-failure',
                    'max_restarts': 2,
                    'restart_delay': 10.0
                },
                'web_api': {
                    'critical': False,
                    'restart_policy': 'always',
                    'max_restarts': 3,
                    'restart_delay': 5.0
                }
            },
            'monitoring': {
                'enabled': True,
                'metrics_retention_days': 30,
                'alert_thresholds': {
                    'cpu_percent': 90.0,
                    'memory_percent': 85.0,
                    'disk_percent': 90.0,
                    'service_restart_count': 3
                }
            }
        }
        
        # Save default configuration
        system_config_path = self.config_dir / 'system.yaml'
        with open(system_config_path, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False, indent=2)
        
        # Load it into memory
        await self.load_config('system.yaml')
        logger.info("Created default system configuration")
    
    async def _validate_all_configs(self):
        """Validate all loaded configurations"""
        validation_errors = []
        
        for config_name, config_file in self.configs.items():
            try:
                await self._validate_config(config_name, config_file.content)
                config_file.validated = True
                config_file.errors = []
            except Exception as e:
                error_msg = f"Validation failed for {config_name}: {e}"
                logger.error(error_msg)
                config_file.validated = False
                config_file.errors = [str(e)]
                validation_errors.append(error_msg)
        
        if validation_errors:
            raise ValueError(f"Configuration validation failed:\n" + "\n".join(validation_errors))
    
    async def _validate_config(self, config_name: str, content: Dict[str, Any]):
        """Validate a specific configuration"""
        # Basic validation - ensure required sections exist
        validation_rules = {
            'system.yaml': ['system', 'services'],
            'hardware.yaml': ['i2c', 'serial', 'gpio'],
            'communication.yaml': ['mqtt'],
            'safety.yaml': ['safety'],
            'data_management.yaml': ['redis', 'sqlite'],
            'sensor_fusion.yaml': ['fusion'],
            'weather.yaml': ['weather'],
            'vision.yaml': ['vision'],
            'power_management.yaml': ['power']
        }
        
        required_sections = validation_rules.get(config_name, [])
        missing_sections = []
        
        for section in required_sections:
            if section not in content:
                missing_sections.append(section)
        
        if missing_sections:
            raise ValueError(f"Missing required sections: {missing_sections}")
        
        # Type-specific validation
        if config_name == 'system.yaml':
            await self._validate_system_config(content)
    
    async def _validate_system_config(self, content: Dict[str, Any]):
        """Validate system configuration specifically"""
        system_config = content.get('system', {})
        
        # Validate numeric ranges
        if 'max_cpu_percent' in system_config:
            cpu_limit = system_config['max_cpu_percent']
            if not (0 < cpu_limit <= 100):
                raise ValueError("max_cpu_percent must be between 0 and 100")
        
        if 'max_memory_percent' in system_config:
            mem_limit = system_config['max_memory_percent']
            if not (0 < mem_limit <= 100):
                raise ValueError("max_memory_percent must be between 0 and 100")
        
        # Validate services configuration
        services_config = content.get('services', {})
        for service_name, service_config in services_config.items():
            if 'max_restarts' in service_config:
                max_restarts = service_config['max_restarts']
                if not isinstance(max_restarts, int) or max_restarts < 0:
                    raise ValueError(f"Invalid max_restarts for {service_name}")
    
    def get_config(self, config_name: str) -> Optional[Dict[str, Any]]:
        """Get a configuration by name"""
        config_file = self.configs.get(config_name)
        return config_file.content if config_file else None
    
    def get_system_config(self) -> Dict[str, Any]:
        """Get system configuration"""
        return self.get_config('system.yaml') or {}
    
    def get_service_config(self, service_name: str) -> Dict[str, Any]:
        """Get configuration for a specific service"""
        system_config = self.get_system_config()
        services = system_config.get('services', {})
        return services.get(service_name, {})
    
    async def update_config(self, config_name: str, updates: Dict[str, Any]):
        """Update a configuration with validation"""
        if config_name not in self.configs:
            raise ValueError(f"Configuration {config_name} not found")
        
        # Create backup before updating
        await self._backup_config(config_name)
        
        # Apply updates
        config_file = self.configs[config_name]
        updated_content = self._merge_configs(config_file.content, updates)
        
        # Validate updated configuration
        await self._validate_config(config_name, updated_content)
        
        # Save to file
        with open(config_file.path, 'w') as f:
            yaml.dump(updated_content, f, default_flow_style=False, indent=2)
        
        # Update in memory
        config_file.content = updated_content
        config_file.last_modified = config_file.path.stat().st_mtime
        config_file.validated = True
        
        # Notify change callbacks
        await self._notify_config_change(config_name, updated_content)
        
        logger.info(f"Updated configuration: {config_name}")
    
    async def _backup_config(self, config_name: str):
        """Create backup of configuration file"""
        config_file = self.configs[config_name]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{config_name}.{timestamp}.backup"
        backup_path = self.backup_dir / backup_name
        
        shutil.copy2(config_file.path, backup_path)
        logger.debug(f"Created backup: {backup_path}")
    
    async def restore_config(self, config_name: str, backup_timestamp: str):
        """Restore configuration from backup"""
        backup_name = f"{config_name}.{backup_timestamp}.backup"
        backup_path = self.backup_dir / backup_name
        
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")
        
        config_file = self.configs[config_name]
        
        # Restore from backup
        shutil.copy2(backup_path, config_file.path)
        
        # Reload configuration
        await self.load_config(config_name)
        
        logger.info(f"Restored configuration {config_name} from backup {backup_timestamp}")
    
    def register_change_callback(self, config_name: str, callback):
        """Register callback for configuration changes"""
        if config_name not in self.change_callbacks:
            self.change_callbacks[config_name] = []
        self.change_callbacks[config_name].append(callback)
    
    async def _notify_config_change(self, config_name: str, new_content: Dict[str, Any]):
        """Notify registered callbacks of configuration changes"""
        callbacks = self.change_callbacks.get(config_name, [])
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(config_name, new_content)
                else:
                    callback(config_name, new_content)
            except Exception as e:
                logger.error(f"Error in config change callback: {e}")
    
    async def start_hot_reload(self, config_name: str):
        """Start hot reloading for a configuration file"""
        if config_name in self.watchers:
            return  # Already watching
        
        async def watch_config():
            config_file = self.configs[config_name]
            last_mtime = config_file.last_modified
            
            while True:
                try:
                    current_mtime = config_file.path.stat().st_mtime
                    if current_mtime > last_mtime:
                        logger.info(f"Configuration file changed: {config_name}")
                        await self.load_config(config_name)
                        last_mtime = current_mtime
                        
                        # Notify callbacks
                        await self._notify_config_change(config_name, config_file.content)
                    
                    await asyncio.sleep(1.0)  # Check every second
                    
                except Exception as e:
                    logger.error(f"Error watching config {config_name}: {e}")
                    await asyncio.sleep(5.0)
        
        self.watchers[config_name] = asyncio.create_task(watch_config())
        logger.info(f"Started hot reload for {config_name}")
    
    async def stop_hot_reload(self, config_name: str):
        """Stop hot reloading for a configuration file"""
        if config_name in self.watchers:
            self.watchers[config_name].cancel()
            del self.watchers[config_name]
            logger.info(f"Stopped hot reload for {config_name}")
    
    async def shutdown(self):
        """Shutdown configuration manager"""
        # Stop all watchers
        for config_name in list(self.watchers.keys()):
            await self.stop_hot_reload(config_name)
        
        logger.info("Configuration manager shut down")
    
    def get_all_configs(self) -> Dict[str, Dict[str, Any]]:
        """Get all configurations"""
        return {name: config.content for name, config in self.configs.items()}
    
    def get_config_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all configurations"""
        status = {}
        for name, config in self.configs.items():
            status[name] = {
                'path': str(config.path),
                'last_modified': config.last_modified,
                'validated': config.validated,
                'errors': config.errors or [],
                'watching': name in self.watchers
            }
        return status
