"""
Configuration Validator - Comprehensive validation system for all LawnBerry configurations
Prevents invalid settings and provides detailed error reporting with suggestions
"""

import asyncio
import logging
import json
import yaml
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass
from enum import Enum
import ipaddress
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """Validation severity levels"""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationCategory(Enum):
    """Configuration validation categories"""
    SYNTAX = "syntax"
    SCHEMA = "schema"
    SECURITY = "security"
    HARDWARE = "hardware"
    NETWORK = "network"
    PERFORMANCE = "performance"
    COMPATIBILITY = "compatibility"


@dataclass
class ValidationResult:
    """Configuration validation result"""
    level: ValidationLevel
    category: ValidationCategory
    message: str
    field_path: str
    current_value: Any
    suggested_value: Optional[Any] = None
    fix_command: Optional[str] = None
    documentation_link: Optional[str] = None


@dataclass
class ValidationSummary:
    """Summary of validation results"""
    total_checks: int
    errors: int
    warnings: int
    infos: int
    valid: bool
    results: List[ValidationResult]


class ConfigValidator:
    """
    Comprehensive configuration validation system
    """
    
    def __init__(self):
        self.validation_rules = self._load_validation_rules()
        self.hardware_constraints = self._load_hardware_constraints()
        self.security_rules = self._load_security_rules()
        
    def _load_validation_rules(self) -> Dict[str, Dict[str, Any]]:
        """Load configuration validation rules"""
        return {
            'system': {
                'required_fields': [
                    'system_id', 'operation_mode', 'log_level',
                    'data_directory', 'config_directory'
                ],
                'field_validators': {
                    'operation_mode': {
                        'type': 'enum',
                        'values': ['development', 'production', 'maintenance', 'debug']
                    },
                    'log_level': {
                        'type': 'enum',
                        'values': ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
                    },
                    'data_directory': {
                        'type': 'path',
                        'must_exist': True,
                        'permissions': 'rw'
                    },
                    'config_directory': {
                        'type': 'path',
                        'must_exist': True,
                        'permissions': 'r'
                    },
                    'max_memory_usage_mb': {
                        'type': 'int',
                        'min': 512,
                        'max': 7900  # For 8GB system (leave headroom below 8192)
                    },
                    'max_cpu_usage_percent': {
                        'type': 'float',
                        'min': 10.0,
                        'max': 95.0
                    }
                }
            },
            'hardware': {
                'required_fields': [
                    'gpio_pins', 'i2c_devices', 'uart_devices',
                    'camera_device', 'update_rate_hz'
                ],
                'field_validators': {
                    'gpio_pins': {
                        'type': 'dict',
                        'required_keys': ['motor_left_dir', 'motor_right_dir', 'motor_left_pwm', 'motor_right_pwm', 'safety_stop', 'emergency_stop']
                    },
                    'i2c_devices': {
                        'type': 'dict',
                        'address_range': (0x03, 0x77)
                    },
                    'uart_devices': {
                        'type': 'dict',
                        'device_pattern': r'^/dev/tty[A-Z]+\d+$'
                    },
                    'camera_device': {
                        'type': 'string',
                        'pattern': r'^/dev/video\d+$'
                    },
                    'update_rate_hz': {
                        'type': 'int',
                        'min': 1,
                        'max': 100
                    }
                }
            },
            'safety': {
                'required_fields': [
                    'emergency_stop_enabled', 'obstacle_detection_enabled',
                    'safety_boundaries', 'max_tilt_angle', 'min_battery_voltage'
                ],
                'field_validators': {
                    'emergency_stop_enabled': {
                        'type': 'bool',
                        'must_be': True
                    },
                    'obstacle_detection_enabled': {
                        'type': 'bool',
                        'must_be': True
                    },
                    'max_tilt_angle': {
                        'type': 'float',
                        'min': 5.0,
                        'max': 45.0
                    },
                    'min_battery_voltage': {
                        'type': 'float',
                        'min': 10.0,
                        'max': 15.0
                    },
                    'safety_boundaries': {
                        'type': 'list',
                        'min_items': 3  # Minimum triangle
                    }
                }
            },
            'network': {
                'required_fields': ['web_api_port', 'websocket_port'],
                'field_validators': {
                    'web_api_port': {
                        'type': 'int',
                        'min': 1024,
                        'max': 65535
                    },
                    'websocket_port': {
                        'type': 'int',
                        'min': 1024,
                        'max': 65535
                    },
                    'mqtt_broker_host': {
                        'type': 'hostname_or_ip',
                        'optional': True
                    },
                    'mqtt_broker_port': {
                        'type': 'int',
                        'min': 1,
                        'max': 65535,
                        'optional': True
                    }
                }
            },
            'weather': {
                'required_fields': ['api_key', 'location'],
                'field_validators': {
                    'api_key': {
                        'type': 'string',
                        'min_length': 32,
                        'pattern': r'^[a-f0-9]+$'
                    },
                    'location': {
                        'type': 'dict',
                        'required_keys': ['latitude', 'longitude']
                    },
                    'update_interval': {
                        'type': 'int',
                        'min': 300,  # 5 minutes minimum
                        'max': 3600  # 1 hour maximum
                    }
                }
            }
        }
    
    def _load_hardware_constraints(self) -> Dict[str, Any]:
        """Load hardware-specific constraints"""
        return {
            'raspberry_pi_4b': {
                'gpio_pins': {
                    'available': list(range(2, 28)),
                    'reserved': [1, 6, 9, 14, 20, 25],  # Power, ground pins
                    'i2c': [2, 3],  # I2C pins
                    'spi': [7, 8, 9, 10, 11],  # SPI pins
                    'uart': [14, 15]  # UART pins
                },
                'memory': {
                    'total_mb': 8192,  # 8GB model
                    'gpu_split_mb': [64, 128, 256],
                    'available_for_apps': 7000  # Conservative estimate
                },
                'i2c_addresses': {
                    'reserved': [0x00, 0x01, 0x02, 0x78, 0x79, 0x7A, 0x7B, 0x7C, 0x7D, 0x7E, 0x7F],
                    'common_devices': {
                        0x29: 'VL53L0X ToF sensor',
                        0x30: 'VL53L0X ToF sensor (alt)',
                        0x40: 'INA3221 power monitor',
                        0x3C: 'SSD1306 OLED display',
                        0x76: 'BME280 environmental sensor'
                    }
                }
            }
        }
    
    def _load_security_rules(self) -> Dict[str, Any]:
        """Load security validation rules"""
        return {
            'api_keys': {
                'min_length': 16,
                'must_not_contain': ['password', 'secret', 'key'],
                'pattern': r'^[A-Za-z0-9+/=]+$'
            },
            'passwords': {
                'min_length': 12,
                'require_uppercase': True,
                'require_lowercase': True,
                'require_numbers': True,
                'require_special': True
            },
            'file_permissions': {
                'config_files': 0o644,
                'secret_files': 0o600,
                'executable_files': 0o755,
                'data_directories': 0o755
            },
            'network_security': {
                'require_https_for_external': True,
                'allow_weak_ciphers': False,
                'require_certificate_validation': True
            }
        }
    
    async def validate_configuration(self, config_name: str, config_data: Dict[str, Any], 
                                   config_path: Optional[Path] = None) -> ValidationSummary:
        """Validate a complete configuration"""
        results = []
        
        logger.info(f"Validating configuration: {config_name}")
        
        # Syntax validation
        syntax_results = await self._validate_syntax(config_name, config_data, config_path)
        results.extend(syntax_results)
        
        # Schema validation
        schema_results = await self._validate_schema(config_name, config_data)
        results.extend(schema_results)
        
        # Security validation
        security_results = await self._validate_security(config_name, config_data)
        results.extend(security_results)
        
        # Hardware validation
        if config_name == 'hardware':
            hardware_results = await self._validate_hardware(config_data)
            results.extend(hardware_results)
        
        # Network validation
        if config_name in ['system', 'communication', 'web_api']:
            network_results = await self._validate_network(config_data)
            results.extend(network_results)
        
        # Performance validation
        performance_results = await self._validate_performance(config_name, config_data)
        results.extend(performance_results)
        
        # Cross-configuration validation
        if config_name == 'system':
            cross_results = await self._validate_cross_configuration(config_data)
            results.extend(cross_results)
        
        # Calculate summary
        error_count = sum(1 for r in results if r.level == ValidationLevel.ERROR)
        warning_count = sum(1 for r in results if r.level == ValidationLevel.WARNING)
        info_count = sum(1 for r in results if r.level == ValidationLevel.INFO)
        
        summary = ValidationSummary(
            total_checks=len(results),
            errors=error_count,
            warnings=warning_count,
            infos=info_count,
            valid=error_count == 0,
            results=results
        )
        
        logger.info(f"Configuration validation completed: {error_count} errors, {warning_count} warnings")
        
        return summary
    
    async def _validate_syntax(self, config_name: str, config_data: Dict[str, Any], 
                              config_path: Optional[Path]) -> List[ValidationResult]:
        """Validate configuration syntax"""
        results = []
        
        # Check if config_data is valid dict
        if not isinstance(config_data, dict):
            results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                category=ValidationCategory.SYNTAX,
                message="Configuration must be a dictionary/object",
                field_path="<root>",
                current_value=type(config_data).__name__
            ))
            return results
        
        # Check for empty configuration
        if not config_data:
            results.append(ValidationResult(
                level=ValidationLevel.WARNING,
                category=ValidationCategory.SYNTAX,
                message="Configuration is empty",
                field_path="<root>",
                current_value=config_data
            ))
        
        # Validate YAML syntax if file path provided
        if config_path and config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    yaml.safe_load(f)
            except yaml.YAMLError as e:
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.SYNTAX,
                    message=f"Invalid YAML syntax: {str(e)}",
                    field_path="<file>",
                    current_value=str(config_path),
                    fix_command=f"yamllint {config_path}"
                ))
        
        return results
    
    async def _validate_schema(self, config_name: str, config_data: Dict[str, Any]) -> List[ValidationResult]:
        """Validate configuration schema"""
        results = []
        
        if config_name not in self.validation_rules:
            results.append(ValidationResult(
                level=ValidationLevel.INFO,
                category=ValidationCategory.SCHEMA,
                message=f"No validation rules defined for configuration: {config_name}",
                field_path="<config>",
                current_value=config_name
            ))
            return results
        
        rules = self.validation_rules[config_name]
        
        # Check required fields
        required_fields = rules.get('required_fields', [])
        for field in required_fields:
            if field not in config_data:
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.SCHEMA,
                    message=f"Required field missing: {field}",
                    field_path=field,
                    current_value=None,
                    suggested_value="<required>",
                    documentation_link=f"/docs/configuration/{config_name}#{field}"
                ))
        
        # Validate field types and constraints
        field_validators = rules.get('field_validators', {})
        for field_path, value in self._flatten_dict(config_data):
            field_name = field_path.split('.')[-1]
            
            if field_name in field_validators:
                validator = field_validators[field_name]
                field_results = await self._validate_field(field_path, value, validator)
                results.extend(field_results)
        
        return results
    
    async def _validate_field(self, field_path: str, value: Any, validator: Dict[str, Any]) -> List[ValidationResult]:
        """Validate individual field"""
        results = []
        
        # Skip validation if field is optional and not present
        if validator.get('optional', False) and value is None:
            return results
        
        field_type = validator.get('type')
        
        # Type validation
        if field_type == 'string' and not isinstance(value, str):
            results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                category=ValidationCategory.SCHEMA,
                message=f"Field must be a string",
                field_path=field_path,
                current_value=value,
                suggested_value="<string>"
            ))
        elif field_type == 'int' and not isinstance(value, int):
            results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                category=ValidationCategory.SCHEMA,
                message=f"Field must be an integer",
                field_path=field_path,
                current_value=value,
                suggested_value="<integer>"
            ))
        elif field_type == 'float' and not isinstance(value, (int, float)):
            results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                category=ValidationCategory.SCHEMA,
                message=f"Field must be a number",
                field_path=field_path,
                current_value=value,
                suggested_value="<number>"
            ))
        elif field_type == 'bool' and not isinstance(value, bool):
            results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                category=ValidationCategory.SCHEMA,
                message=f"Field must be a boolean",
                field_path=field_path,
                current_value=value,
                suggested_value="true or false"
            ))
        elif field_type == 'list' and not isinstance(value, list):
            results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                category=ValidationCategory.SCHEMA,
                message=f"Field must be a list/array",
                field_path=field_path,
                current_value=value,
                suggested_value="[]"
            ))
        elif field_type == 'dict' and not isinstance(value, dict):
            results.append(ValidationResult(
                level=ValidationLevel.ERROR,
                category=ValidationCategory.SCHEMA,
                message=f"Field must be a dictionary/object",
                field_path=field_path,
                current_value=value,
                suggested_value="{}"
            ))
        
        # Value constraints
        if isinstance(value, (int, float)):
            if 'min' in validator and value < validator['min']:
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.SCHEMA,
                    message=f"Value must be >= {validator['min']}",
                    field_path=field_path,
                    current_value=value,
                    suggested_value=validator['min']
                ))
            
            if 'max' in validator and value > validator['max']:
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.SCHEMA,
                    message=f"Value must be <= {validator['max']}",
                    field_path=field_path,
                    current_value=value,
                    suggested_value=validator['max']
                ))
        
        # String constraints
        if isinstance(value, str):
            if 'min_length' in validator and len(value) < validator['min_length']:
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.SCHEMA,
                    message=f"String must be at least {validator['min_length']} characters",
                    field_path=field_path,
                    current_value=value
                ))
            
            if 'pattern' in validator:
                if not re.match(validator['pattern'], value):
                    results.append(ValidationResult(
                        level=ValidationLevel.ERROR,
                        category=ValidationCategory.SCHEMA,
                        message=f"String must match pattern: {validator['pattern']}",
                        field_path=field_path,
                        current_value=value
                    ))
        
        # Enum validation
        if 'values' in validator:
            if value not in validator['values']:
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.SCHEMA,
                    message=f"Value must be one of: {', '.join(map(str, validator['values']))}",
                    field_path=field_path,
                    current_value=value,
                    suggested_value=validator['values'][0]
                ))
        
        # Must be validation
        if 'must_be' in validator:
            if value != validator['must_be']:
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.SCHEMA,
                    message=f"Value must be: {validator['must_be']}",
                    field_path=field_path,
                    current_value=value,
                    suggested_value=validator['must_be']
                ))
        
        # Path validation
        if field_type == 'path':
            path_results = await self._validate_path(field_path, value, validator)
            results.extend(path_results)
        
        # Hostname or IP validation
        if field_type == 'hostname_or_ip':
            if not self._is_valid_hostname_or_ip(value):
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.NETWORK,
                    message="Invalid hostname or IP address",
                    field_path=field_path,
                    current_value=value
                ))
        
        return results
    
    async def _validate_path(self, field_path: str, value: str, validator: Dict[str, Any]) -> List[ValidationResult]:
        """Validate file/directory path"""
        results = []
        
        if not isinstance(value, str):
            return results
        
        path = Path(value)
        
        # Check if path must exist
        if validator.get('must_exist', False):
            if not path.exists():
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.SCHEMA,
                    message=f"Path does not exist: {value}",
                    field_path=field_path,
                    current_value=value,
                    fix_command=f"mkdir -p {path.parent}" if validator.get('create_if_missing') else None
                ))
        
        # Check permissions
        if path.exists() and 'permissions' in validator:
            required_perms = validator['permissions']
            
            if 'r' in required_perms and not path.is_readable():
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.SECURITY,
                    message=f"Path is not readable: {value}",
                    field_path=field_path,
                    current_value=value,
                    fix_command=f"chmod +r {value}"
                ))
            
            if 'w' in required_perms and not path.is_writable():
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.SECURITY,
                    message=f"Path is not writable: {value}",
                    field_path=field_path,
                    current_value=value,
                    fix_command=f"chmod +w {value}"
                ))
        
        return results
    
    def _is_valid_hostname_or_ip(self, value: str) -> bool:
        """Check if value is valid hostname or IP address"""
        # Try IP address first
        try:
            ipaddress.ip_address(value)
            return True
        except ValueError:
            pass
        
        # Try hostname
        hostname_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
        return bool(re.match(hostname_pattern, value))
    
    async def _validate_security(self, config_name: str, config_data: Dict[str, Any]) -> List[ValidationResult]:
        """Validate security aspects of configuration"""
        results = []
        
        # Check for hardcoded secrets
        for field_path, value in self._flatten_dict(config_data):
            if isinstance(value, str):
                # Check for potential API keys or passwords in configuration
                if any(keyword in field_path.lower() for keyword in ['key', 'password', 'secret', 'token']):
                    if self._looks_like_hardcoded_secret(value):
                        results.append(ValidationResult(
                            level=ValidationLevel.ERROR,
                            category=ValidationCategory.SECURITY,
                            message="Hardcoded secret detected in configuration",
                            field_path=field_path,
                            current_value="<redacted>",
                            suggested_value="Use environment variable",
                            fix_command=f"Move to environment variable: {field_path.upper().replace('.', '_')}"
                        ))
        
        return results
    
    def _looks_like_hardcoded_secret(self, value: str) -> bool:
        """Check if string looks like a hardcoded secret"""
        if len(value) < 8:
            return False
        
        # Check for common secret patterns
        secret_patterns = [
            r'^[A-Za-z0-9+/=]{20,}$',  # Base64-like
            r'^[a-f0-9]{32,}$',        # Hex
            r'^[A-Z0-9]{20,}$',        # API key-like
        ]
        
        for pattern in secret_patterns:
            if re.match(pattern, value):
                return True
        
        return False
    
    async def _validate_hardware(self, config_data: Dict[str, Any]) -> List[ValidationResult]:
        """Validate hardware-specific configuration"""
        results = []
        
        # Validate GPIO pin assignments
        if 'gpio_pins' in config_data:
            gpio_results = await self._validate_gpio_pins(config_data['gpio_pins'])
            results.extend(gpio_results)
        
        # Validate I2C device addresses
        if 'i2c_devices' in config_data:
            i2c_results = await self._validate_i2c_addresses(config_data['i2c_devices'])
            results.extend(i2c_results)
        
        return results
    
    async def _validate_gpio_pins(self, gpio_config: Dict[str, Any]) -> List[ValidationResult]:
        """Validate GPIO pin configuration"""
        results = []
        
        if not isinstance(gpio_config, dict):
            return results
        
        hardware_info = self.hardware_constraints.get('raspberry_pi_4b', {})
        available_pins = hardware_info.get('gpio_pins', {}).get('available', [])
        reserved_pins = hardware_info.get('gpio_pins', {}).get('reserved', [])
        
        used_pins = []
        
        for pin_name, pin_number in gpio_config.items():
            if not isinstance(pin_number, int):
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.HARDWARE,
                    message=f"GPIO pin must be an integer",
                    field_path=f"gpio_pins.{pin_name}",
                    current_value=pin_number
                ))
                continue
            
            # Check if pin is available
            if pin_number not in available_pins:
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.HARDWARE,
                    message=f"GPIO pin {pin_number} is not available",
                    field_path=f"gpio_pins.{pin_name}",
                    current_value=pin_number,
                    suggested_value=f"Use one of: {available_pins[:5]}"
                ))
            
            # Check if pin is reserved
            if pin_number in reserved_pins:
                results.append(ValidationResult(
                    level=ValidationLevel.WARNING,
                    category=ValidationCategory.HARDWARE,
                    message=f"GPIO pin {pin_number} is reserved (power/ground)",
                    field_path=f"gpio_pins.{pin_name}",
                    current_value=pin_number
                ))
            
            # Check for duplicate pin assignments
            if pin_number in used_pins:
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.HARDWARE,
                    message=f"GPIO pin {pin_number} is assigned multiple times",
                    field_path=f"gpio_pins.{pin_name}",
                    current_value=pin_number
                ))
            else:
                used_pins.append(pin_number)
        
        return results
    
    async def _validate_i2c_addresses(self, i2c_config: Dict[str, Any]) -> List[ValidationResult]:
        """Validate I2C device addresses"""
        results = []
        
        if not isinstance(i2c_config, dict):
            return results
        
        hardware_info = self.hardware_constraints.get('raspberry_pi_4b', {})
        reserved_addresses = hardware_info.get('i2c_addresses', {}).get('reserved', [])
        common_devices = hardware_info.get('i2c_addresses', {}).get('common_devices', {})
        
        used_addresses = []
        
        for device_name, address in i2c_config.items():
            if isinstance(address, str) and address.startswith('0x'):
                try:
                    address = int(address, 16)
                except ValueError:
                    results.append(ValidationResult(
                        level=ValidationLevel.ERROR,
                        category=ValidationCategory.HARDWARE,
                        message=f"Invalid I2C address format",
                        field_path=f"i2c_devices.{device_name}",
                        current_value=address,
                        suggested_value="0x29 (hex format)"
                    ))
                    continue
            
            if not isinstance(address, int):
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.HARDWARE,
                    message=f"I2C address must be an integer or hex string",
                    field_path=f"i2c_devices.{device_name}",
                    current_value=address
                ))
                continue
            
            # Check address range
            if not (0x03 <= address <= 0x77):
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.HARDWARE,
                    message=f"I2C address {hex(address)} is outside valid range (0x03-0x77)",
                    field_path=f"i2c_devices.{device_name}",
                    current_value=hex(address)
                ))
            
            # Check if address is reserved
            if address in reserved_addresses:
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.HARDWARE,
                    message=f"I2C address {hex(address)} is reserved",
                    field_path=f"i2c_devices.{device_name}",
                    current_value=hex(address)
                ))
            
            # Check for conflicts with known devices
            if address in common_devices and device_name.lower() not in common_devices[address].lower():
                results.append(ValidationResult(
                    level=ValidationLevel.WARNING,
                    category=ValidationCategory.HARDWARE,
                    message=f"I2C address {hex(address)} typically used for {common_devices[address]}",
                    field_path=f"i2c_devices.{device_name}",
                    current_value=hex(address)
                ))
            
            # Check for duplicate addresses
            if address in used_addresses:
                results.append(ValidationResult(
                    level=ValidationLevel.ERROR,
                    category=ValidationCategory.HARDWARE,
                    message=f"I2C address {hex(address)} is assigned to multiple devices",
                    field_path=f"i2c_devices.{device_name}",
                    current_value=hex(address)
                ))
            else:
                used_addresses.append(address)
        
        return results
    
    async def _validate_network(self, config_data: Dict[str, Any]) -> List[ValidationResult]:
        """Validate network configuration"""
        results = []
        
        # Check for port conflicts
        ports_used = []
        for field_path, value in self._flatten_dict(config_data):
            if 'port' in field_path.lower() and isinstance(value, int):
                if value in ports_used:
                    results.append(ValidationResult(
                        level=ValidationLevel.ERROR,
                        category=ValidationCategory.NETWORK,
                        message=f"Port {value} is assigned multiple times",
                        field_path=field_path,
                        current_value=value
                    ))
                else:
                    ports_used.append(value)
                
                # Check for well-known ports
                if value < 1024:
                    results.append(ValidationResult(
                        level=ValidationLevel.WARNING,
                        category=ValidationCategory.NETWORK,
                        message=f"Port {value} is in well-known port range (<1024), may require root privileges",
                        field_path=field_path,
                        current_value=value,
                        suggested_value=f"{value + 8000}"
                    ))
        
        return results
    
    async def _validate_performance(self, config_name: str, config_data: Dict[str, Any]) -> List[ValidationResult]:
        """Validate performance-related configuration"""
        results = []
        
        # Check update rates for potential performance issues
        for field_path, value in self._flatten_dict(config_data):
            if 'rate' in field_path.lower() or 'interval' in field_path.lower():
                if isinstance(value, (int, float)):
                    if 'rate' in field_path.lower() and value > 50:
                        results.append(ValidationResult(
                            level=ValidationLevel.WARNING,
                            category=ValidationCategory.PERFORMANCE,
                            message=f"High update rate may impact performance",
                            field_path=field_path,
                            current_value=value,
                            suggested_value=20
                        ))
                    elif 'interval' in field_path.lower() and value < 0.1:
                        results.append(ValidationResult(
                            level=ValidationLevel.WARNING,
                            category=ValidationCategory.PERFORMANCE,
                            message=f"Very short interval may impact performance",
                            field_path=field_path,
                            current_value=value,
                            suggested_value=0.5
                        ))
        
        return results
    
    async def _validate_cross_configuration(self, config_data: Dict[str, Any]) -> List[ValidationResult]:
        """Validate cross-configuration dependencies"""
        results = []
        
        # This is a placeholder for cross-configuration validation
        # In a real implementation, this would check consistency across multiple config files
        
        return results
    
    def _flatten_dict(self, d: Dict[str, Any], parent_key: str = '', sep: str = '.') -> List[Tuple[str, Any]]:
        """Flatten nested dictionary for easier validation"""
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep))
            else:
                items.append((new_key, v))
        return items
    
    async def generate_fix_script(self, validation_results: List[ValidationResult]) -> str:
        """Generate shell script to fix validation issues"""
        script_lines = [
            "#!/bin/bash",
            "# Auto-generated configuration fix script",
            "set -e",
            "",
            "echo 'Applying configuration fixes...'",
            ""
        ]
        
        for result in validation_results:
            if result.fix_command and result.level == ValidationLevel.ERROR:
                script_lines.append(f"# Fix: {result.message}")
                script_lines.append(result.fix_command)
                script_lines.append("")
        
        script_lines.append("echo 'Configuration fixes applied successfully!'")
        
        return "\n".join(script_lines)
    
    async def export_validation_report(self, validation_summary: ValidationSummary, 
                                     format: str = 'json') -> str:
        """Export validation report in specified format"""
        if format == 'json':
            return json.dumps({
                'summary': {
                    'total_checks': validation_summary.total_checks,
                    'errors': validation_summary.errors,
                    'warnings': validation_summary.warnings,
                    'infos': validation_summary.infos,
                    'valid': validation_summary.valid
                },
                'results': [
                    {
                        'level': r.level.value,
                        'category': r.category.value,
                        'message': r.message,
                        'field_path': r.field_path,
                        'current_value': r.current_value,
                        'suggested_value': r.suggested_value,
                        'fix_command': r.fix_command,
                        'documentation_link': r.documentation_link
                    }
                    for r in validation_summary.results
                ]
            }, indent=2)
        elif format == 'text':
            lines = [
                "Configuration Validation Report",
                "=" * 35,
                f"Total checks: {validation_summary.total_checks}",
                f"Errors: {validation_summary.errors}",
                f"Warnings: {validation_summary.warnings}",
                f"Info: {validation_summary.infos}",
                f"Valid: {'Yes' if validation_summary.valid else 'No'}",
                "",
                "Details:",
                "-" * 8
            ]
            
            for result in validation_summary.results:
                lines.extend([
                    f"[{result.level.value.upper()}] {result.field_path}",
                    f"  Message: {result.message}",
                    f"  Current: {result.current_value}",
                    f"  Suggested: {result.suggested_value}" if result.suggested_value else "",
                    f"  Fix: {result.fix_command}" if result.fix_command else "",
                    ""
                ])
            
            return "\n".join(lines)
        else:
            raise ValueError(f"Unsupported format: {format}")
