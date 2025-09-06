"""
Comprehensive Plugin Architecture for System-wide Extensibility
Provides framework for third-party development and core system extension
"""

import asyncio
import hashlib
import importlib
import inspect
import json
import logging
import shutil
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import yaml
from packaging import version

logger = logging.getLogger(__name__)


class PluginType(Enum):
    """Plugin types supported by the architecture"""

    HARDWARE = "hardware"
    SERVICE = "service"
    UI_COMPONENT = "ui_component"
    DATA_PROCESSOR = "data_processor"
    SAFETY_EXTENSION = "safety_extension"
    PATTERN_ALGORITHM = "pattern_algorithm"
    NOTIFICATION = "notification"
    INTEGRATION = "integration"


class PluginState(Enum):
    """Plugin lifecycle states"""

    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"
    UNLOADING = "unloading"


@dataclass
class PluginMetadata:
    """Plugin metadata and information"""

    name: str
    version: str
    author: str
    description: str
    plugin_type: PluginType
    api_version: str
    dependencies: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    configuration_schema: Dict[str, Any] = field(default_factory=dict)
    entry_point: str = "main"
    min_system_version: str = "1.0.0"
    max_system_version: Optional[str] = None
    license: str = "MIT"
    homepage: Optional[str] = None
    support_email: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class PluginSandbox:
    """Plugin sandbox configuration for security"""

    allow_file_access: bool = False
    allowed_paths: List[str] = field(default_factory=list)
    allow_network_access: bool = False
    allowed_hosts: List[str] = field(default_factory=list)
    allow_system_calls: bool = False
    resource_limits: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 30


@dataclass
class PluginPerformanceMetrics:
    """Plugin performance tracking"""

    load_time_ms: float = 0.0
    init_time_ms: float = 0.0
    avg_execution_time_ms: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    error_count: int = 0
    success_count: int = 0
    last_executed: Optional[datetime] = None


class BasePlugin(ABC):
    """Abstract base class for all system plugins"""

    def __init__(self, metadata: PluginMetadata, config: Dict[str, Any]):
        self.metadata = metadata
        self.config = config
        self.logger = logging.getLogger(f"plugin.{metadata.name}")
        self.state = PluginState.UNLOADED
        self.metrics = PluginPerformanceMetrics()
        self._hooks: Dict[str, List[Callable]] = {}
        self._api_endpoints: Dict[str, Callable] = {}

    @property
    @abstractmethod
    def plugin_info(self) -> Dict[str, Any]:
        """Return plugin information"""
        pass

    @abstractmethod
    async def initialize(self, system_context: Dict[str, Any]) -> bool:
        """Initialize the plugin with system context"""
        pass

    @abstractmethod
    async def start(self) -> bool:
        """Start the plugin operations"""
        pass

    @abstractmethod
    async def stop(self) -> bool:
        """Stop the plugin operations"""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Perform plugin health check"""
        pass

    def register_hook(self, event: str, callback: Callable):
        """Register a callback for system events"""
        if event not in self._hooks:
            self._hooks[event] = []
        self._hooks[event].append(callback)

    def register_api_endpoint(self, path: str, handler: Callable):
        """Register an API endpoint"""
        self._api_endpoints[path] = handler

    async def emit_event(self, event: str, data: Any = None):
        """Emit an event to registered hooks"""
        if event in self._hooks:
            for callback in self._hooks[event]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception as e:
                    self.logger.error(f"Hook callback failed for {event}: {e}")


class PluginValidator:
    """Validates plugin security and compatibility"""

    def __init__(self, system_version: str):
        self.system_version = system_version
        self.required_permissions = {
            "file_access": ["read_config", "write_logs"],
            "network_access": ["http_client", "mqtt_publish"],
            "system_calls": ["subprocess", "hardware_control"],
            "data_access": ["database_read", "database_write"],
        }

    async def validate_plugin(self, plugin_path: Path, metadata: PluginMetadata) -> Dict[str, Any]:
        """Comprehensive plugin validation"""
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "security_score": 100,
            "compatibility_score": 100,
        }

        # Version compatibility check
        if not self._check_version_compatibility(metadata):
            validation_result["errors"].append("Incompatible system version")
            validation_result["valid"] = False

        # Security validation
        security_issues = await self._validate_security(plugin_path, metadata)
        validation_result["errors"].extend(security_issues.get("errors", []))
        validation_result["warnings"].extend(security_issues.get("warnings", []))
        validation_result["security_score"] = security_issues.get("score", 100)

        # Code quality validation
        quality_issues = await self._validate_code_quality(plugin_path)
        validation_result["warnings"].extend(quality_issues.get("warnings", []))

        # Dependency validation
        dep_issues = await self._validate_dependencies(metadata.dependencies)
        validation_result["errors"].extend(dep_issues.get("errors", []))
        validation_result["warnings"].extend(dep_issues.get("warnings", []))

        if validation_result["errors"]:
            validation_result["valid"] = False

        return validation_result

    def _check_version_compatibility(self, metadata: PluginMetadata) -> bool:
        """Check if plugin is compatible with system version"""
        try:
            system_ver = version.parse(self.system_version)
            min_ver = version.parse(metadata.min_system_version)

            if system_ver < min_ver:
                return False

            if metadata.max_system_version:
                max_ver = version.parse(metadata.max_system_version)
                if system_ver > max_ver:
                    return False

            return True
        except Exception:
            return False

    async def _validate_security(
        self, plugin_path: Path, metadata: PluginMetadata
    ) -> Dict[str, Any]:
        """Validate plugin security aspects"""
        issues = {"errors": [], "warnings": [], "score": 100}

        # Check for dangerous imports
        dangerous_imports = ["os.system", "subprocess.call", "eval", "exec"]
        try:
            with open(plugin_path / "main.py", "r") as f:
                content = f.read()
                for dangerous in dangerous_imports:
                    if dangerous in content:
                        issues["warnings"].append(f"Potentially dangerous import: {dangerous}")
                        issues["score"] -= 10
        except Exception:
            issues["errors"].append("Cannot read plugin main file")

        # Validate permissions
        for permission in metadata.permissions:
            if permission not in self.required_permissions:
                issues["warnings"].append(f"Unknown permission: {permission}")
                issues["score"] -= 5

        return issues

    async def _validate_code_quality(self, plugin_path: Path) -> Dict[str, Any]:
        """Basic code quality validation"""
        issues = {"warnings": []}

        # Check for basic Python syntax
        try:
            with open(plugin_path / "main.py", "r") as f:
                compile(f.read(), plugin_path / "main.py", "exec")
        except SyntaxError as e:
            issues["warnings"].append(f"Syntax error: {e}")
        except Exception:
            issues["warnings"].append("Cannot validate code syntax")

        return issues

    async def _validate_dependencies(self, dependencies: List[str]) -> Dict[str, Any]:
        """Validate plugin dependencies"""
        issues = {"errors": [], "warnings": []}

        for dep in dependencies:
            try:
                importlib.import_module(dep)
            except ImportError:
                issues["warnings"].append(f"Dependency not available: {dep}")

        return issues


class PluginManager:
    """Comprehensive plugin management system"""

    def __init__(self, system_version: str = "1.0.0"):
        self.system_version = system_version
        self.plugins: Dict[str, BasePlugin] = {}
        self.plugin_metadata: Dict[str, PluginMetadata] = {}
        self.plugin_states: Dict[str, PluginState] = {}
        self.validator = PluginValidator(system_version)

        # Plugin directories
        self.system_plugin_dir = Path("/opt/lawnberry/plugins")
        self.user_plugin_dir = Path("/var/lib/lawnberry/plugins")
        self.temp_plugin_dir = Path("/tmp/lawnberry_plugins")

        # Create directories
        for directory in [self.system_plugin_dir, self.user_plugin_dir, self.temp_plugin_dir]:
            directory.mkdir(parents=True, exist_ok=True)

        # Event system
        self.event_handlers: Dict[str, List[Callable]] = {}

        self.logger = logger

    async def discover_plugins(self) -> List[Path]:
        """Discover available plugins in system and user directories"""
        plugins = []

        for plugin_dir in [self.system_plugin_dir, self.user_plugin_dir]:
            if plugin_dir.exists():
                for item in plugin_dir.iterdir():
                    if item.is_dir() and (item / "plugin.yaml").exists():
                        plugins.append(item)

        return plugins

    async def load_plugin(self, plugin_path: Path, enable: bool = True) -> bool:
        """Load a plugin from path"""
        try:
            # Load metadata
            metadata_file = plugin_path / "plugin.yaml"
            if not metadata_file.exists():
                self.logger.error(f"Plugin metadata not found: {metadata_file}")
                return False

            with open(metadata_file, "r") as f:
                metadata_dict = yaml.safe_load(f)

            metadata = PluginMetadata(**metadata_dict)

            # Validate plugin
            validation_result = await self.validator.validate_plugin(plugin_path, metadata)
            if not validation_result["valid"]:
                self.logger.error(f"Plugin validation failed: {validation_result['errors']}")
                return False

            # Load plugin configuration
            config_file = plugin_path / "config.yaml"
            config = {}
            if config_file.exists():
                with open(config_file, "r") as f:
                    config = yaml.safe_load(f) or {}

            # Import plugin module
            spec = importlib.util.spec_from_file_location(
                f"plugin_{metadata.name}", plugin_path / f"{metadata.entry_point}.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Get plugin class
            plugin_class = getattr(module, f"{metadata.name.title()}Plugin")

            # Create plugin instance
            plugin_instance = plugin_class(metadata, config)

            # Store plugin
            self.plugins[metadata.name] = plugin_instance
            self.plugin_metadata[metadata.name] = metadata
            self.plugin_states[metadata.name] = PluginState.LOADED

            if enable:
                return await self.enable_plugin(metadata.name)

            self.logger.info(f"Plugin loaded: {metadata.name}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to load plugin from {plugin_path}: {e}")
            return False

    async def enable_plugin(self, plugin_name: str) -> bool:
        """Enable and start a loaded plugin"""
        if plugin_name not in self.plugins:
            self.logger.error(f"Plugin not found: {plugin_name}")
            return False

        plugin = self.plugins[plugin_name]

        try:
            self.plugin_states[plugin_name] = PluginState.INITIALIZING

            # Initialize plugin
            system_context = await self._get_system_context()
            start_time = time.time()

            if await plugin.initialize(system_context):
                plugin.metrics.init_time_ms = (time.time() - start_time) * 1000

                # Start plugin
                if await plugin.start():
                    self.plugin_states[plugin_name] = PluginState.ACTIVE
                    plugin.state = PluginState.ACTIVE

                    # Register plugin hooks and endpoints
                    await self._register_plugin_integrations(plugin)

                    self.logger.info(f"Plugin enabled: {plugin_name}")
                    return True

            self.plugin_states[plugin_name] = PluginState.ERROR
            return False

        except Exception as e:
            self.plugin_states[plugin_name] = PluginState.ERROR
            self.logger.error(f"Failed to enable plugin {plugin_name}: {e}")
            return False

    async def disable_plugin(self, plugin_name: str) -> bool:
        """Disable and stop a plugin"""
        if plugin_name not in self.plugins:
            return False

        plugin = self.plugins[plugin_name]

        try:
            self.plugin_states[plugin_name] = PluginState.UNLOADING

            # Stop plugin
            await plugin.stop()

            # Unregister integrations
            await self._unregister_plugin_integrations(plugin)

            self.plugin_states[plugin_name] = PluginState.DISABLED
            plugin.state = PluginState.DISABLED

            self.logger.info(f"Plugin disabled: {plugin_name}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to disable plugin {plugin_name}: {e}")
            return False

    async def unload_plugin(self, plugin_name: str) -> bool:
        """Unload a plugin completely"""
        if plugin_name in self.plugins:
            await self.disable_plugin(plugin_name)

            del self.plugins[plugin_name]
            del self.plugin_metadata[plugin_name]
            del self.plugin_states[plugin_name]

            self.logger.info(f"Plugin unloaded: {plugin_name}")
            return True

        return False

    async def get_plugin_status(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive plugin status"""
        if plugin_name not in self.plugins:
            return None

        plugin = self.plugins[plugin_name]
        metadata = self.plugin_metadata[plugin_name]

        health = await plugin.health_check()

        return {
            "name": plugin_name,
            "version": metadata.version,
            "state": self.plugin_states[plugin_name].value,
            "health": health,
            "metrics": {
                "load_time_ms": plugin.metrics.load_time_ms,
                "init_time_ms": plugin.metrics.init_time_ms,
                "avg_execution_time_ms": plugin.metrics.avg_execution_time_ms,
                "memory_usage_mb": plugin.metrics.memory_usage_mb,
                "cpu_usage_percent": plugin.metrics.cpu_usage_percent,
                "error_count": plugin.metrics.error_count,
                "success_count": plugin.metrics.success_count,
                "last_executed": plugin.metrics.last_executed.isoformat()
                if plugin.metrics.last_executed
                else None,
            },
            "metadata": {
                "author": metadata.author,
                "description": metadata.description,
                "plugin_type": metadata.plugin_type.value,
                "api_version": metadata.api_version,
                "dependencies": metadata.dependencies,
                "permissions": metadata.permissions,
            },
        }

    async def list_plugins(self) -> List[Dict[str, Any]]:
        """List all plugins with their status"""
        plugins = []
        for plugin_name in self.plugins:
            status = await self.get_plugin_status(plugin_name)
            if status:
                plugins.append(status)
        return plugins

    async def _get_system_context(self) -> Dict[str, Any]:
        """Get system context for plugin initialization"""
        return {
            "system_version": self.system_version,
            "plugin_manager": self,
            "logger": self.logger,
            "config_paths": {"system": "/etc/lawnberry", "user": "/var/lib/lawnberry"},
        }

    async def _register_plugin_integrations(self, plugin: BasePlugin):
        """Register plugin hooks and API endpoints"""
        # Register event hooks
        for event, handlers in plugin._hooks.items():
            if event not in self.event_handlers:
                self.event_handlers[event] = []
            self.event_handlers[event].extend(handlers)

        # Register API endpoints (would integrate with web API)
        # This would be implemented based on the web API framework
        pass

    async def _unregister_plugin_integrations(self, plugin: BasePlugin):
        """Unregister plugin hooks and API endpoints"""
        # Unregister event hooks
        for event, handlers in plugin._hooks.items():
            if event in self.event_handlers:
                for handler in handlers:
                    if handler in self.event_handlers[event]:
                        self.event_handlers[event].remove(handler)

        # Unregister API endpoints
        pass

    async def emit_system_event(self, event: str, data: Any = None):
        """Emit system event to all registered handlers"""
        if event in self.event_handlers:
            for handler in self.event_handlers[event]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception as e:
                    self.logger.error(f"Event handler failed for {event}: {e}")


# Example plugin implementations
class SampleServicePlugin(BasePlugin):
    """Sample service plugin implementation"""

    @property
    def plugin_info(self) -> Dict[str, Any]:
        return {
            "name": self.metadata.name,
            "type": "service",
            "capabilities": ["data_processing", "event_handling"],
        }

    async def initialize(self, system_context: Dict[str, Any]) -> bool:
        self.logger.info("Sample service plugin initializing")
        # Register for system events
        self.register_hook("mowing_started", self._on_mowing_started)
        self.register_hook("mowing_stopped", self._on_mowing_stopped)
        return True

    async def start(self) -> bool:
        self.logger.info("Sample service plugin started")
        return True

    async def stop(self) -> bool:
        self.logger.info("Sample service plugin stopped")
        return True

    async def health_check(self) -> Dict[str, Any]:
        return {"status": "healthy", "checks": {"connectivity": True, "resources": True}}

    async def _on_mowing_started(self, data):
        self.logger.info("Handling mowing started event")

    async def _on_mowing_stopped(self, data):
        self.logger.info("Handling mowing stopped event")


# Plugin development utilities
def create_plugin_template(plugin_name: str, plugin_type: PluginType, output_dir: Path):
    """Create a plugin template for development"""
    plugin_dir = output_dir / plugin_name
    plugin_dir.mkdir(parents=True, exist_ok=True)

    # Create plugin.yaml
    metadata = {
        "name": plugin_name,
        "version": "1.0.0",
        "author": "Plugin Developer",
        "description": f"A {plugin_type.value} plugin for LawnBerry",
        "plugin_type": plugin_type.value,
        "api_version": "1.0.0",
        "dependencies": [],
        "permissions": [],
        "entry_point": "main",
        "min_system_version": "1.0.0",
    }

    with open(plugin_dir / "plugin.yaml", "w") as f:
        yaml.dump(metadata, f, default_flow_style=False)

    # Create main.py template
    template_code = f'''"""
{plugin_name} Plugin for LawnBerry System
"""

from system_integration.plugin_architecture import BasePlugin
import logging


class {plugin_name.title()}Plugin(BasePlugin):
    """
    {plugin_name} plugin implementation
    """

    def __init__(self, metadata, config):
        super().__init__(metadata, config)
        self.logger = logging.getLogger(f"plugin.{plugin_name}")

    @property
    def plugin_info(self):
        return {{
            "name": self.metadata.name,
            "type": "{plugin_type.value}",
            "capabilities": ["example_capability"]
        }}

    async def initialize(self, system_context):
        """Initialize the plugin"""
        self.logger.info("Initializing {plugin_name} plugin")
        # Add your initialization code here
        return True

    async def start(self):
        """Start the plugin"""
        self.logger.info("Starting {plugin_name} plugin")
        # Add your startup code here
        return True

    async def stop(self):
        """Stop the plugin"""
        self.logger.info("Stopping {plugin_name} plugin")
        # Add your cleanup code here
        return True

    async def health_check(self):
        """Perform health check"""
        return {{
            "status": "healthy",
            "checks": {{
                "initialization": True,
                "resources": True
            }}
        }}
'''

    with open(plugin_dir / "main.py", "w") as f:
        f.write(template_code)

    # Create empty config.yaml
    with open(plugin_dir / "config.yaml", "w") as f:
        yaml.dump({}, f)

    # Create README.md
    readme_content = f"""# {plugin_name} Plugin

## Description
{metadata["description"]}

## Installation
Copy this plugin directory to your LawnBerry plugins folder and restart the system.

## Configuration
Edit `config.yaml` to configure the plugin settings.

## Usage
The plugin will automatically load when the system starts.

## Development
This plugin was created using the LawnBerry plugin template.
"""

    with open(plugin_dir / "README.md", "w") as f:
        f.write(readme_content)

    print(f"Plugin template created at: {plugin_dir}")


if __name__ == "__main__":
    # Example usage for plugin development
    import argparse

    parser = argparse.ArgumentParser(description="LawnBerry Plugin Development Tools")
    parser.add_argument("--create-template", help="Create plugin template")
    parser.add_argument(
        "--plugin-type",
        choices=[t.value for t in PluginType],
        default="service",
        help="Plugin type",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("."), help="Output directory")

    args = parser.parse_args()

    if args.create_template:
        plugin_type = PluginType(args.plugin_type)
        create_plugin_template(args.create_template, plugin_type, args.output_dir)
