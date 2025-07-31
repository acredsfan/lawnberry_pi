"""
Enhanced System Integration Service
Coordinates all system improvements with plugin architecture, error recovery, and performance optimization
"""

import asyncio
import logging
import json
import time
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
import yaml

from .plugin_architecture import PluginManager, BasePlugin, PluginType, PluginState
from .error_recovery_system import ErrorRecoverySystem, ErrorSeverity, ErrorCategory, ErrorContext
from .reliability_service import SystemReliabilityService, AlertLevel
from .performance_service import PerformanceService, PerformanceCategory, MetricType


logger = logging.getLogger(__name__)


class SystemMode(Enum):
    """System operation modes"""
    STARTUP = "startup"
    NORMAL = "normal"
    MAINTENANCE = "maintenance"
    EMERGENCY = "emergency"
    SHUTDOWN = "shutdown"


class FeatureFlag(Enum):
    """System feature flags"""
    PLUGIN_SYSTEM = "plugin_system"
    AUTO_RECOVERY = "auto_recovery"
    PERFORMANCE_OPTIMIZATION = "performance_optimization"
    PREDICTIVE_MAINTENANCE = "predictive_maintenance"
    ADVANCED_MONITORING = "advanced_monitoring"
    USER_EXPERIENCE_ENHANCEMENTS = "user_experience_enhancements"


@dataclass
class SystemConfiguration:
    """System-wide configuration"""
    debug_mode: bool = False
    log_level: str = "INFO"
    feature_flags: Dict[str, bool] = field(default_factory=dict)
    plugin_directories: List[str] = field(default_factory=list)
    performance_profile: str = "balanced"
    auto_recovery_enabled: bool = True
    maintenance_window: Optional[str] = None
    backup_schedule: str = "0 2 * * *"
    monitoring_interval: int = 10
    alert_thresholds: Dict[str, float] = field(default_factory=dict)


@dataclass
class SystemStatus:
    """Current system status"""
    mode: SystemMode
    health_score: float
    active_plugins: int
    active_alerts: int
    performance_score: float
    uptime_seconds: float
    last_backup: Optional[datetime]
    memory_usage_mb: float
    cpu_usage_percent: float
    error_count_24h: int
    recovery_count_24h: int


@dataclass
class SystemMetrics:
    """Comprehensive system metrics"""
    timestamp: datetime
    system_status: SystemStatus
    component_health: Dict[str, float]
    performance_metrics: Dict[str, float]
    plugin_metrics: Dict[str, Dict[str, Any]]
    error_summary: Dict[str, int]
    optimization_summary: Dict[str, Any]


class EnhancedSystemService:
    """
    Enhanced system integration service that coordinates all system improvements
    Provides unified management of plugins, error recovery, performance optimization, and reliability
    """
    
    def __init__(self, config_path: str = "/etc/lawnberry/system.yaml"):
        self.config_path = config_path
        self.config = SystemConfiguration()
        
        # Core services
        self.plugin_manager: Optional[PluginManager] = None
        self.error_recovery: Optional[ErrorRecoverySystem] = None
        self.reliability_service: Optional[SystemReliabilityService] = None
        self.performance_service: Optional[PerformanceService] = None
        
        # System state
        self.current_mode = SystemMode.STARTUP
        self.start_time = datetime.now()
        self.enabled_features: Set[FeatureFlag] = set()
        self.system_metrics_history: List[SystemMetrics] = []
        
        # Service registry
        self.registered_services: Dict[str, Any] = {}
        self.service_dependencies: Dict[str, List[str]] = {}
        
        # Event system
        self.event_handlers: Dict[str, List[callable]] = {}
        
        # Background tasks
        self.monitoring_tasks: Set[asyncio.Task] = set()
        self.running = False
        
        self.logger = logger
        
        # Initialize default feature flags
        self._setup_default_features()
    
    def _setup_default_features(self):
        """Setup default feature flag states"""
        default_features = {
            FeatureFlag.PLUGIN_SYSTEM: True,
            FeatureFlag.AUTO_RECOVERY: True,
            FeatureFlag.PERFORMANCE_OPTIMIZATION: True,
            FeatureFlag.PREDICTIVE_MAINTENANCE: True,
            FeatureFlag.ADVANCED_MONITORING: True,
            FeatureFlag.USER_EXPERIENCE_ENHANCEMENTS: True
        }
        
        for feature, enabled in default_features.items():
            if enabled:
                self.enabled_features.add(feature)
    
    async def initialize(self):
        """Initialize the enhanced system service"""
        try:
            self.logger.info("Initializing Enhanced System Service")
            
            # Load configuration
            await self._load_configuration()
            
            # Initialize core services based on feature flags
            await self._initialize_core_services()
            
            # Setup service integrations
            await self._setup_service_integrations()
            
            # Start monitoring and background tasks
            await self._start_background_tasks()
            
            # Transition to normal mode
            await self._transition_to_mode(SystemMode.NORMAL)
            
            self.logger.info("Enhanced System Service initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Enhanced System Service: {e}")
            await self._handle_initialization_failure(e)
            raise
    
    async def _load_configuration(self):
        """Load system configuration"""
        try:
            if Path(self.config_path).exists():
                with open(self.config_path, 'r') as f:
                    config_data = yaml.safe_load(f)
                
                # Update configuration
                if 'system' in config_data:
                    system_config = config_data['system']
                    
                    # Update basic settings
                    for field_name in ['debug_mode', 'log_level', 'performance_profile', 
                                     'auto_recovery_enabled', 'maintenance_window', 
                                     'backup_schedule', 'monitoring_interval']:
                        if field_name in system_config:
                            setattr(self.config, field_name, system_config[field_name])
                    
                    # Update feature flags
                    if 'feature_flags' in system_config:
                        for flag_name, enabled in system_config['feature_flags'].items():
                            try:
                                flag = FeatureFlag(flag_name)
                                if enabled:
                                    self.enabled_features.add(flag)
                                else:
                                    self.enabled_features.discard(flag)
                            except ValueError:
                                self.logger.warning(f"Unknown feature flag: {flag_name}")
                    
                    # Update other configurations
                    if 'plugin_directories' in system_config:
                        self.config.plugin_directories = system_config['plugin_directories']
                    
                    if 'alert_thresholds' in system_config:
                        self.config.alert_thresholds = system_config['alert_thresholds']
                
                self.logger.info("System configuration loaded successfully")
            else:
                self.logger.info("Using default system configuration")
        
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            # Continue with default configuration
    
    async def _initialize_core_services(self):
        """Initialize core services based on enabled features"""
        try:
            # Initialize Plugin Manager
            if FeatureFlag.PLUGIN_SYSTEM in self.enabled_features:
                self.plugin_manager = PluginManager("1.0.0")
                await self.plugin_manager.initialize()
                self.registered_services['plugin_manager'] = self.plugin_manager
                self.logger.info("Plugin Manager initialized")
            
            # Initialize Error Recovery System
            if FeatureFlag.AUTO_RECOVERY in self.enabled_features:
                self.error_recovery = ErrorRecoverySystem()
                await self.error_recovery.initialize()
                self.registered_services['error_recovery'] = self.error_recovery
                self.logger.info("Error Recovery System initialized")
            
            # Initialize Reliability Service
            if FeatureFlag.ADVANCED_MONITORING in self.enabled_features:
                self.reliability_service = SystemReliabilityService()
                await self.reliability_service.initialize()
                self.registered_services['reliability_service'] = self.reliability_service
                self.logger.info("Reliability Service initialized")
            
            # Initialize Performance Service
            if FeatureFlag.PERFORMANCE_OPTIMIZATION in self.enabled_features:
                self.performance_service = PerformanceService()
                await self.performance_service.initialize()
                self.registered_services['performance_service'] = self.performance_service
                self.logger.info("Performance Service initialized")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize core services: {e}")
            raise
    
    async def _setup_service_integrations(self):
        """Setup integrations between services"""
        try:
            # Integrate error recovery with reliability service
            if self.error_recovery and self.reliability_service:
                self.error_recovery.notification_system = self.reliability_service
                self.reliability_service.register_alert_handler(
                    AlertLevel.CRITICAL, 
                    self._handle_critical_alert
                )
            
            # Integrate performance service with error recovery
            if self.performance_service and self.error_recovery:
                # Register performance-related error handlers
                pass
            
            # Setup plugin system integrations
            if self.plugin_manager:
                # Auto-discover and load plugins
                await self._discover_and_load_plugins()
            
            self.logger.info("Service integrations setup completed")
            
        except Exception as e:
            self.logger.error(f"Failed to setup service integrations: {e}")
    
    async def _discover_and_load_plugins(self):
        """Discover and load system plugins"""
        try:
            if not self.plugin_manager:
                return
            
            # Discover plugins
            plugin_paths = await self.plugin_manager.discover_plugins()
            
            # Load discovered plugins
            loaded_count = 0
            for plugin_path in plugin_paths:
                try:
                    if await self.plugin_manager.load_plugin(plugin_path, enable=True):
                        loaded_count += 1
                except Exception as e:
                    self.logger.error(f"Failed to load plugin from {plugin_path}: {e}")
            
            self.logger.info(f"Loaded {loaded_count} plugins from {len(plugin_paths)} discovered")
            
        except Exception as e:
            self.logger.error(f"Failed to discover and load plugins: {e}")
    
    async def _start_background_tasks(self):
        """Start background monitoring and maintenance tasks"""
        self.running = True
        
        tasks = [
            asyncio.create_task(self._system_monitoring_loop()),
            asyncio.create_task(self._health_check_loop()),
            asyncio.create_task(self._metrics_collection_loop()),
            asyncio.create_task(self._maintenance_loop()),
            asyncio.create_task(self._event_processing_loop())
        ]
        
        # Add feature-specific tasks
        if FeatureFlag.PREDICTIVE_MAINTENANCE in self.enabled_features:
            tasks.append(asyncio.create_task(self._predictive_maintenance_loop()))
        
        self.monitoring_tasks.update(tasks)
        self.logger.info(f"Started {len(tasks)} background monitoring tasks")
    
    async def _system_monitoring_loop(self):
        """Main system monitoring loop"""
        while self.running:
            try:
                # Collect comprehensive system metrics
                metrics = await self._collect_system_metrics()
                self.system_metrics_history.append(metrics)
                
                # Keep history manageable
                if len(self.system_metrics_history) > 1000:
                    self.system_metrics_history = self.system_metrics_history[-1000:]
                
                # Emit system metrics event
                await self._emit_event("system_metrics_collected", metrics)
                
                await asyncio.sleep(self.config.monitoring_interval)
                
            except Exception as e:
                await self._handle_monitoring_error("system_monitoring", e)
                await asyncio.sleep(30)
    
    async def _health_check_loop(self):
        """System health check loop"""
        while self.running:
            try:
                # Perform comprehensive health checks
                health_results = await self._perform_system_health_checks()
                
                # Process health check results
                await self._process_health_results(health_results)
                
                await asyncio.sleep(30)
                
            except Exception as e:
                await self._handle_monitoring_error("health_check", e)
                await asyncio.sleep(60)
    
    async def _metrics_collection_loop(self):
        """Metrics collection and analysis loop"""
        while self.running:
            try:
                # Collect performance metrics
                if self.performance_service:
                    with self.performance_service.timer("system_metrics_collection", PerformanceCategory.CPU):
                        await self._collect_performance_metrics()
                
                await asyncio.sleep(60)
                
            except Exception as e:
                await self._handle_monitoring_error("metrics_collection", e)
                await asyncio.sleep(120)
    
    async def _maintenance_loop(self):
        """System maintenance loop"""
        while self.running:
            try:
                # Check if we're in maintenance window
                if await self._is_maintenance_window():
                    await self._perform_routine_maintenance()
                
                await asyncio.sleep(3600)  # Check every hour
                
            except Exception as e:
                await self._handle_monitoring_error("maintenance", e)
                await asyncio.sleep(1800)
    
    async def _predictive_maintenance_loop(self):
        """Predictive maintenance loop"""
        while self.running:
            try:
                # Analyze trends and predict maintenance needs
                await self._analyze_predictive_indicators()
                
                await asyncio.sleep(1800)  # Run every 30 minutes
                
            except Exception as e:
                await self._handle_monitoring_error("predictive_maintenance", e)
                await asyncio.sleep(3600)
    
    async def _event_processing_loop(self):
        """Event processing loop"""
        while self.running:
            try:
                # Process system events
                await self._process_pending_events()
                
                await asyncio.sleep(5)
                
            except Exception as e:
                await self._handle_monitoring_error("event_processing", e)
                await asyncio.sleep(10)
    
    async def _collect_system_metrics(self) -> SystemMetrics:
        """Collect comprehensive system metrics"""
        try:
            # Get system status
            system_status = await self._get_system_status()
            
            # Get component health scores
            component_health = await self._get_component_health()
            
            # Get performance metrics
            performance_metrics = {}
            if self.performance_service:
                performance_summary = await self.performance_service.get_performance_summary()
                performance_metrics = performance_summary.get('current_metrics', {})
            
            # Get plugin metrics
            plugin_metrics = {}
            if self.plugin_manager:
                plugin_list = await self.plugin_manager.list_plugins()
                for plugin in plugin_list:
                    plugin_metrics[plugin['name']] = {
                        'state': plugin['state'],
                        'health': plugin['health'],
                        'metrics': plugin['metrics']
                    }
            
            # Get error summary
            error_summary = {}
            if self.error_recovery:
                error_summary = self.error_recovery.get_error_summary()
            
            # Get optimization summary
            optimization_summary = {}
            if self.performance_service:
                perf_summary = await self.performance_service.get_performance_summary()
                optimization_summary = {
                    'active_optimizations': perf_summary.get('active_optimizations', []),
                    'current_profile': perf_summary.get('current_profile', 'unknown')
                }
            
            return SystemMetrics(
                timestamp=datetime.now(),
                system_status=system_status,
                component_health=component_health,
                performance_metrics=performance_metrics,
                plugin_metrics=plugin_metrics,
                error_summary=error_summary,
                optimization_summary=optimization_summary
            )
            
        except Exception as e:
            self.logger.error(f"Failed to collect system metrics: {e}")
            # Return minimal metrics on error
            return SystemMetrics(
                timestamp=datetime.now(),
                system_status=SystemStatus(
                    mode=self.current_mode,
                    health_score=0.0,
                    active_plugins=0,
                    active_alerts=0,
                    performance_score=0.0,
                    uptime_seconds=(datetime.now() - self.start_time).total_seconds(),
                    last_backup=None,
                    memory_usage_mb=0.0,
                    cpu_usage_percent=0.0,
                    error_count_24h=0,
                    recovery_count_24h=0
                ),
                component_health={},
                performance_metrics={},
                plugin_metrics={},
                error_summary={},
                optimization_summary={}
            )
    
    async def _get_system_status(self) -> SystemStatus:
        """Get current system status"""
        try:
            # Calculate health score
            health_score = 100.0
            if self.reliability_service:
                system_health = self.reliability_service.get_system_health()
                health_score = system_health.get('health_percentage', 100.0)
            
            # Get performance score
            performance_score = 100.0
            if self.performance_service:
                performance_score = await self.performance_service.get_current_performance_score()
            
            # Count active plugins
            active_plugins = 0
            if self.plugin_manager:
                plugin_list = await self.plugin_manager.list_plugins()
                active_plugins = sum(1 for p in plugin_list if p['state'] == 'active')
            
            # Count active alerts
            active_alerts = 0
            if self.reliability_service:
                alerts = self.reliability_service.get_active_alerts()
                active_alerts = len(alerts)
            
            # Get resource usage
            import psutil
            memory = psutil.virtual_memory()
            cpu_percent = psutil.cpu_percent()
            
            # Get error counts
            error_count_24h = 0
            recovery_count_24h = 0
            if self.error_recovery:
                error_summary = self.error_recovery.get_error_summary()
                error_count_24h = error_summary.get('recent_errors', 0)
                
                # Count recoveries from component health
                for component, health in error_summary.get('component_health', {}).items():
                    recovery_count_24h += health.get('recovery_count', 0)
            
            return SystemStatus(
                mode=self.current_mode,
                health_score=health_score,
                active_plugins=active_plugins,
                active_alerts=active_alerts,
                performance_score=performance_score,
                uptime_seconds=(datetime.now() - self.start_time).total_seconds(),
                last_backup=None,  # Would get from reliability service
                memory_usage_mb=memory.used / 1024 / 1024,
                cpu_usage_percent=cpu_percent,
                error_count_24h=error_count_24h,
                recovery_count_24h=recovery_count_24h
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get system status: {e}")
            return SystemStatus(
                mode=self.current_mode,
                health_score=0.0,
                active_plugins=0,
                active_alerts=0,
                performance_score=0.0,
                uptime_seconds=0.0,
                last_backup=None,
                memory_usage_mb=0.0,
                cpu_usage_percent=0.0,
                error_count_24h=0,
                recovery_count_24h=0
            )
    
    async def _get_component_health(self) -> Dict[str, float]:
        """Get health scores for all components"""
        component_health = {}
        
        # Get health from reliability service
        if self.reliability_service:
            system_health = self.reliability_service.get_system_health()
            services = system_health.get('services', {})
            if services:
                healthy_count = services.get('healthy', 0)
                total_count = services.get('total', 1)
                component_health['services'] = (healthy_count / total_count) * 100.0
        
        # Get health from error recovery
        if self.error_recovery:
            error_summary = self.error_recovery.get_error_summary()
            for component, health_info in error_summary.get('component_health', {}).items():
                component_health[component] = health_info.get('health_score', 100.0)
        
        return component_health
    
    async def _perform_system_health_checks(self) -> Dict[str, Any]:
        """Perform comprehensive system health checks"""
        health_results = {}
        
        try:
            # Check core services
            for service_name, service in self.registered_services.items():
                try:
                    if hasattr(service, 'get_system_health'):
                        health_results[service_name] = await service.get_system_health()
                    elif hasattr(service, 'health_check'):
                        health_results[service_name] = await service.health_check()
                    else:
                        health_results[service_name] = {"status": "unknown"}
                except Exception as e:
                    health_results[service_name] = {"status": "error", "error": str(e)}
            
            # Check plugin health
            if self.plugin_manager:
                plugin_list = await self.plugin_manager.list_plugins()
                health_results['plugins'] = {
                    plugin['name']: plugin['health'] for plugin in plugin_list
                }
            
            return health_results
            
        except Exception as e:
            self.logger.error(f"Failed to perform system health checks: {e}")
            return {"error": str(e)}
    
    async def _process_health_results(self, health_results: Dict[str, Any]):
        """Process health check results and take actions"""
        try:
            for component, health in health_results.items():
                if isinstance(health, dict):
                    status = health.get('status', 'unknown')
                    
                    if status == 'error':
                        await self._handle_component_error(component, health.get('error', 'Unknown error'))
                    elif status in ['unhealthy', 'critical']:
                        await self._handle_unhealthy_component(component, health)
        
        except Exception as e:
            self.logger.error(f"Failed to process health results: {e}")
    
    async def _handle_component_error(self, component: str, error: str):
        """Handle component error"""
        if self.error_recovery:
            context = ErrorContext(
                component=component,
                operation="health_check",
                system_state={"mode": self.current_mode.value}
            )
            
            await self.error_recovery.handle_error(
                Exception(f"Health check failed: {error}"),
                context,
                ErrorSeverity.HIGH,
                ErrorCategory.SOFTWARE
            )
    
    async def _handle_unhealthy_component(self, component: str, health_info: Dict[str, Any]):
        """Handle unhealthy component"""
        self.logger.warning(f"Component {component} is unhealthy: {health_info}")
        
        # Emit event for unhealthy component
        await self._emit_event("component_unhealthy", {
            "component": component,
            "health_info": health_info
        })
    
    async def _collect_performance_metrics(self):
        """Collect and analyze performance metrics"""
        if not self.performance_service:
            return
        
        try:
            # Record system integration metrics
            await self.performance_service.record_metric(
                "active_plugins",
                PerformanceCategory.CPU,
                MetricType.GAUGE,
                len(self.registered_services),
                {"service": "system_integration"},
                "count"
            )
            
            # Record uptime
            uptime_hours = (datetime.now() - self.start_time).total_seconds() / 3600
            await self.performance_service.record_metric(
                "system_uptime",
                PerformanceCategory.CPU,
                MetricType.GAUGE,
                uptime_hours,
                {"service": "system_integration"},
                "hours"
            )
            
        except Exception as e:
            self.logger.error(f"Failed to collect performance metrics: {e}")
    
    async def _is_maintenance_window(self) -> bool:
        """Check if we're currently in a maintenance window"""
        if not self.config.maintenance_window:
            return False
        
        # Simple time-based check (would implement proper cron parsing)
        current_hour = datetime.now().hour
        return current_hour == 2  # 2 AM maintenance window
    
    async def _perform_routine_maintenance(self):
        """Perform routine system maintenance"""
        try:
            self.logger.info("Starting routine maintenance")
            
            # Transition to maintenance mode
            await self._transition_to_mode(SystemMode.MAINTENANCE)
            
            # Perform maintenance tasks
            maintenance_tasks = []
            
            # Plugin maintenance
            if self.plugin_manager:
                maintenance_tasks.append(self._maintain_plugins())
            
            # Performance optimization
            if self.performance_service:
                maintenance_tasks.append(self.performance_service.force_optimization_run())
            
            # Error recovery maintenance
            if self.error_recovery:
                # Could include log cleanup, metric aggregation, etc.
                pass
            
            # Execute maintenance tasks
            if maintenance_tasks:
                await asyncio.gather(*maintenance_tasks, return_exceptions=True)
            
            # Return to normal mode
            await self._transition_to_mode(SystemMode.NORMAL)
            
            self.logger.info("Routine maintenance completed")
            
        except Exception as e:
            self.logger.error(f"Routine maintenance failed: {e}")
            await self._transition_to_mode(SystemMode.NORMAL)
    
    async def _maintain_plugins(self):
        """Perform plugin maintenance"""
        if not self.plugin_manager:
            return
        
        try:
            # Get plugin health status
            plugin_list = await self.plugin_manager.list_plugins()
            
            for plugin in plugin_list:
                if plugin['state'] == 'error':
                    # Attempt to restart failed plugins
                    self.logger.info(f"Attempting to restart failed plugin: {plugin['name']}")
                    await self.plugin_manager.disable_plugin(plugin['name'])
                    await asyncio.sleep(2)
                    await self.plugin_manager.enable_plugin(plugin['name'])
        
        except Exception as e:
            self.logger.error(f"Plugin maintenance failed: {e}")
    
    async def _analyze_predictive_indicators(self):
        """Analyze predictive maintenance indicators"""
        try:
            if len(self.system_metrics_history) < 10:
                return  # Need more data for analysis
            
            recent_metrics = self.system_metrics_history[-10:]
            
            # Analyze trends
            health_trend = [m.system_status.health_score for m in recent_metrics]
            performance_trend = [m.system_status.performance_score for m in recent_metrics]
            
            # Check for declining trends
            if len(health_trend) >= 5:
                health_slope = self._calculate_trend_slope(health_trend[-5:])
                if health_slope < -2.0:  # Health declining by >2 points per measurement
                    await self._emit_event("predictive_maintenance_alert", {
                        "type": "health_decline",
                        "trend": health_slope,
                        "current_score": health_trend[-1]
                    })
            
            if len(performance_trend) >= 5:
                perf_slope = self._calculate_trend_slope(performance_trend[-5:])
                if perf_slope < -2.0:  # Performance declining
                    await self._emit_event("predictive_maintenance_alert", {
                        "type": "performance_decline",
                        "trend": perf_slope,
                        "current_score": performance_trend[-1]
                    })
        
        except Exception as e:
            self.logger.error(f"Predictive analysis failed: {e}")
    
    def _calculate_trend_slope(self, values: List[float]) -> float:
        """Calculate the slope of a trend line"""
        if len(values) < 2:
            return 0.0
        
        n = len(values)
        x_sum = sum(range(n))
        y_sum = sum(values)
        xy_sum = sum(i * values[i] for i in range(n))
        x2_sum = sum(i * i for i in range(n))
        
        denominator = n * x2_sum - x_sum * x_sum
        if denominator == 0:
            return 0.0
        
        slope = (n * xy_sum - x_sum * y_sum) / denominator
        return slope
    
    async def _process_pending_events(self):
        """Process pending system events"""
        # Implementation would process event queue
        pass
    
    async def _emit_event(self, event_type: str, data: Any = None):
        """Emit system event"""
        try:
            # Emit to plugin manager
            if self.plugin_manager:
                await self.plugin_manager.emit_system_event(event_type, data)
            
            # Process internal event handlers
            if event_type in self.event_handlers:
                for handler in self.event_handlers[event_type]:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(data)
                        else:
                            handler(data)
                    except Exception as e:
                        self.logger.error(f"Event handler failed for {event_type}: {e}")
        
        except Exception as e:
            self.logger.error(f"Failed to emit event {event_type}: {e}")
    
    async def _transition_to_mode(self, new_mode: SystemMode):
        """Transition system to a new mode"""
        if self.current_mode == new_mode:
            return
        
        old_mode = self.current_mode
        self.logger.info(f"Transitioning from {old_mode.value} to {new_mode.value} mode")
        
        try:
            # Emit mode transition event
            await self._emit_event("mode_transition", {
                "old_mode": old_mode.value,
                "new_mode": new_mode.value
            })
            
            # Update current mode
            self.current_mode = new_mode
            
            # Perform mode-specific actions
            if new_mode == SystemMode.EMERGENCY:
                await self._enter_emergency_mode()
            elif new_mode == SystemMode.MAINTENANCE:
                await self._enter_maintenance_mode()
            elif new_mode == SystemMode.NORMAL:
                await self._enter_normal_mode()
            
        except Exception as e:
            self.logger.error(f"Failed to transition to {new_mode.value} mode: {e}")
            self.current_mode = old_mode  # Revert on failure
    
    async def _enter_emergency_mode(self):
        """Enter emergency mode"""
        self.logger.critical("Entering emergency mode")
        
        # Disable non-critical plugins
        if self.plugin_manager:
            plugin_list = await self.plugin_manager.list_plugins()
            for plugin in plugin_list:
                if not plugin.get('critical', False):
                    await self.plugin_manager.disable_plugin(plugin['name'])
        
        # Set conservative performance profile
        if self.performance_service:
            await self.performance_service.set_performance_profile("power_saving")
    
    async def _enter_maintenance_mode(self):
        """Enter maintenance mode"""
        self.logger.info("Entering maintenance mode")
        
        # Reduce monitoring frequency
        # Pause non-essential services
        pass
    
    async def _enter_normal_mode(self):
        """Enter normal operation mode"""
        self.logger.info("Entering normal operation mode")
        
        # Restore normal operations
        # Re-enable plugins if they were disabled
        pass
    
    async def _handle_critical_alert(self, alert):
        """Handle critical system alert"""
        self.logger.critical(f"Critical alert received: {alert.message}")
        
        # Consider emergency mode transition
        if alert.component in ['power_management', 'safety']:
            await self._transition_to_mode(SystemMode.EMERGENCY)
    
    async def _handle_monitoring_error(self, loop_name: str, error: Exception):
        """Handle errors in monitoring loops"""
        if self.error_recovery:
            context = ErrorContext(
                component="enhanced_system_service",
                operation=loop_name,
                system_state={"mode": self.current_mode.value}
            )
            
            await self.error_recovery.handle_error(
                error,
                context,
                ErrorSeverity.MEDIUM,
                ErrorCategory.SOFTWARE
            )
        else:
            self.logger.error(f"Error in {loop_name}: {error}")
    
    async def _handle_initialization_failure(self, error: Exception):
        """Handle initialization failure"""
        self.logger.critical(f"System initialization failed: {error}")
        
        # Attempt minimal safe mode initialization
        try:
            await self._transition_to_mode(SystemMode.EMERGENCY)
        except Exception as e:
            self.logger.critical(f"Failed to enter emergency mode: {e}")
    
    # Public API methods
    
    def register_service(self, name: str, service: Any, dependencies: List[str] = None):
        """Register a service with the system"""
        self.registered_services[name] = service
        if dependencies:
            self.service_dependencies[name] = dependencies
        
        self.logger.info(f"Registered service: {name}")
    
    def register_event_handler(self, event_type: str, handler: callable):
        """Register an event handler"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        try:
            if self.system_metrics_history:
                latest_metrics = self.system_metrics_history[-1]
                return {
                    "mode": self.current_mode.value,
                    "status": latest_metrics.system_status.__dict__,
                    "component_health": latest_metrics.component_health,
                    "performance_metrics": latest_metrics.performance_metrics,
                    "enabled_features": [f.value for f in self.enabled_features],
                    "registered_services": list(self.registered_services.keys()),
                    "uptime_seconds": (datetime.now() - self.start_time).total_seconds()
                }
            else:
                return {
                    "mode": self.current_mode.value,
                    "status": "initializing",
                    "uptime_seconds": (datetime.now() - self.start_time).total_seconds()
                }
        
        except Exception as e:
            self.logger.error(f"Failed to get system status: {e}")
            return {"error": str(e)}
    
    async def enable_feature(self, feature: FeatureFlag) -> bool:
        """Enable a system feature"""
        try:
            self.enabled_features.add(feature)
            
            # Initialize feature if not already done
            if feature == FeatureFlag.PLUGIN_SYSTEM and not self.plugin_manager:
                self.plugin_manager = PluginManager("1.0.0")
                await self.plugin_manager.initialize()
                self.registered_services['plugin_manager'] = self.plugin_manager
            
            # Add similar initialization for other features
            
            self.logger.info(f"Enabled feature: {feature.value}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to enable feature {feature.value}: {e}")
            return False
    
    async def disable_feature(self, feature: FeatureFlag) -> bool:
        """Disable a system feature"""
        try:
            self.enabled_features.discard(feature)
            
            # Shutdown feature components if needed
            if feature == FeatureFlag.PLUGIN_SYSTEM and self.plugin_manager:
                await self.plugin_manager.shutdown_all()
                self.plugin_manager = None
                del self.registered_services['plugin_manager']
            
            self.logger.info(f"Disabled feature: {feature.value}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to disable feature {feature.value}: {e}")
            return False
    
    async def emergency_shutdown(self):
        """Perform emergency system shutdown"""
        self.logger.critical("Emergency shutdown initiated")
        
        await self._transition_to_mode(SystemMode.EMERGENCY)
        
        # Shutdown all services
        if self.reliability_service:
            await self.reliability_service.emergency_shutdown()
        
        await self.shutdown()
    
    async def shutdown(self):
        """Graceful system shutdown"""
        self.logger.info("Initiating graceful shutdown")
        
        await self._transition_to_mode(SystemMode.SHUTDOWN)
        
        # Stop background tasks
        self.running = False
        for task in self.monitoring_tasks:
            if not task.done():
                task.cancel()
        
        # Shutdown services in reverse order of dependencies
        shutdown_order = self._calculate_shutdown_order()
        
        for service_name in shutdown_order:
            if service_name in self.registered_services:
                service = self.registered_services[service_name]
                try:
                    if hasattr(service, 'shutdown'):
                        await service.shutdown()
                except Exception as e:
                    self.logger.error(f"Error shutting down {service_name}: {e}")
        
        self.logger.info("System shutdown completed")
    
    def _calculate_shutdown_order(self) -> List[str]:
        """Calculate optimal shutdown order based on dependencies"""
        # Simple reverse order for now
        # Would implement proper dependency resolution
        return list(reversed(list(self.registered_services.keys())))
