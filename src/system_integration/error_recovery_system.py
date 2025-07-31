"""
Comprehensive Error Handling and Recovery System
Provides robust error management with automatic recovery mechanisms
"""

import asyncio
import logging
import traceback
import json
import time
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
import psutil
import threading
from collections import deque, defaultdict


logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class RecoveryAction(Enum):
    """Recovery action types"""
    RESTART_SERVICE = "restart_service"
    RESTART_COMPONENT = "restart_component"
    RESET_STATE = "reset_state"
    FALLBACK_MODE = "fallback_mode"
    ALERT_USER = "alert_user"
    SHUTDOWN_SYSTEM = "shutdown_system"
    IGNORE = "ignore"
    CUSTOM = "custom"


class ErrorCategory(Enum):
    """Error categories for classification"""
    HARDWARE = "hardware"
    NETWORK = "network"
    SOFTWARE = "software"
    CONFIGURATION = "configuration"
    RESOURCE = "resource"
    SECURITY = "security"
    USER_INPUT = "user_input"
    EXTERNAL = "external"


@dataclass
class ErrorContext:
    """Error context information"""
    component: str
    operation: str
    user_session: Optional[str] = None
    system_state: Dict[str, Any] = field(default_factory=dict)
    environment: Dict[str, Any] = field(default_factory=dict)
    recent_actions: List[str] = field(default_factory=list)


@dataclass
class ErrorInfo:
    """Comprehensive error information"""
    error_id: str
    timestamp: datetime
    severity: ErrorSeverity
    category: ErrorCategory
    message: str
    exception_type: str
    traceback_str: str
    context: ErrorContext
    count: int = 1
    first_occurrence: Optional[datetime] = None
    last_occurrence: Optional[datetime] = None
    resolved: bool = False
    resolution_time: Optional[datetime] = None
    recovery_attempts: int = 0
    user_notified: bool = False


@dataclass
class RecoveryStrategy:
    """Recovery strategy definition"""
    name: str
    actions: List[RecoveryAction]
    conditions: Dict[str, Any]
    timeout_seconds: int = 30
    max_attempts: int = 3
    cooldown_seconds: int = 60
    success_criteria: Dict[str, Any] = field(default_factory=dict)
    custom_handler: Optional[Callable] = None


@dataclass
class ComponentHealth:
    """Component health tracking"""
    component_name: str
    is_healthy: bool = True
    error_count: int = 0
    warning_count: int = 0
    last_error: Optional[datetime] = None
    recovery_count: int = 0
    uptime_seconds: float = 0
    health_score: float = 100.0
    status_message: str = "OK"


class CircuitBreaker:
    """Circuit breaker pattern implementation"""
    
    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open
        self._lock = threading.Lock()
    
    def can_execute(self) -> bool:
        """Check if execution is allowed"""
        with self._lock:
            if self.state == "closed":
                return True
            elif self.state == "open":
                if time.time() - self.last_failure_time > self.timeout_seconds:
                    self.state = "half_open"
                    return True
                return False
            else:  # half_open
                return True
    
    def record_success(self):
        """Record successful execution"""
        with self._lock:
            self.failure_count = 0
            self.state = "closed"
    
    def record_failure(self):
        """Record failed execution"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "open"


class ErrorRecoverySystem:
    """Comprehensive error handling and recovery system"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        
        # Error tracking
        self.errors: Dict[str, ErrorInfo] = {}
        self.error_history: deque = deque(maxlen=1000)
        self.component_health: Dict[str, ComponentHealth] = {}
        
        # Recovery strategies
        self.recovery_strategies: Dict[str, RecoveryStrategy] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Event handlers
        self.error_handlers: Dict[ErrorCategory, List[Callable]] = defaultdict(list)
        self.recovery_handlers: Dict[str, Callable] = {}
        
        # Configuration
        self.config = {
            "max_recovery_attempts": 3,
            "recovery_timeout": 30,
            "health_check_interval": 10,
            "error_aggregation_window": 300,  # 5 minutes
            "notification_throttle": 60,  # 1 minute
            "log_retention_days": 30
        }
        
        # System integration
        self.service_manager = None
        self.notification_system = None
        self.metrics_collector = None
        
        # State
        self.running = False
        self._recovery_tasks: Dict[str, asyncio.Task] = {}
        
        self.logger = logger
        
        # Initialize default recovery strategies
        self._setup_default_strategies()
    
    def _setup_default_strategies(self):
        """Setup default recovery strategies"""
        
        # Service restart strategy
        self.recovery_strategies["service_restart"] = RecoveryStrategy(
            name="service_restart",
            actions=[RecoveryAction.RESTART_SERVICE],
            conditions={"error_category": ErrorCategory.SOFTWARE},
            timeout_seconds=30,
            max_attempts=3,
            cooldown_seconds=60
        )
        
        # Hardware reset strategy
        self.recovery_strategies["hardware_reset"] = RecoveryStrategy(
            name="hardware_reset",
            actions=[RecoveryAction.RESET_STATE, RecoveryAction.RESTART_COMPONENT],
            conditions={"error_category": ErrorCategory.HARDWARE},
            timeout_seconds=60,
            max_attempts=2,
            cooldown_seconds=120
        )
        
        # Network recovery strategy
        self.recovery_strategies["network_recovery"] = RecoveryStrategy(
            name="network_recovery",
            actions=[RecoveryAction.FALLBACK_MODE, RecoveryAction.ALERT_USER],
            conditions={"error_category": ErrorCategory.NETWORK},
            timeout_seconds=45,
            max_attempts=5,
            cooldown_seconds=30
        )
        
        # Resource exhaustion strategy
        self.recovery_strategies["resource_recovery"] = RecoveryStrategy(
            name="resource_recovery",
            actions=[RecoveryAction.RESET_STATE, RecoveryAction.RESTART_SERVICE],
            conditions={"error_category": ErrorCategory.RESOURCE},
            timeout_seconds=120,
            max_attempts=2,
            cooldown_seconds=300
        )
        
        # Critical system strategy
        self.recovery_strategies["critical_system"] = RecoveryStrategy(
            name="critical_system",
            actions=[RecoveryAction.ALERT_USER, RecoveryAction.SHUTDOWN_SYSTEM],
            conditions={"severity": ErrorSeverity.CRITICAL},
            timeout_seconds=10,
            max_attempts=1,
            cooldown_seconds=0
        )
    
    async def initialize(self, service_manager=None, notification_system=None, metrics_collector=None):
        """Initialize the error recovery system"""
        self.service_manager = service_manager
        self.notification_system = notification_system
        self.metrics_collector = metrics_collector
        
        # Load configuration
        await self._load_configuration()
        
        # Start background tasks
        self.running = True
        asyncio.create_task(self._health_monitor_loop())
        asyncio.create_task(self._error_aggregation_loop())
        
        self.logger.info("Error Recovery System initialized")
    
    async def handle_error(
        self, 
        exception: Exception, 
        context: ErrorContext,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        category: ErrorCategory = ErrorCategory.SOFTWARE,
        auto_recover: bool = True
    ) -> Optional[str]:
        """Handle an error with automatic recovery"""
        
        # Create error ID
        error_id = self._generate_error_id(exception, context)
        
        # Check if error already exists
        if error_id in self.errors:
            error_info = self.errors[error_id]
            error_info.count += 1
            error_info.last_occurrence = datetime.now()
        else:
            # Create new error info
            error_info = ErrorInfo(
                error_id=error_id,
                timestamp=datetime.now(),
                severity=severity,
                category=category,
                message=str(exception),
                exception_type=type(exception).__name__,
                traceback_str=traceback.format_exc(),
                context=context,
                first_occurrence=datetime.now(),
                last_occurrence=datetime.now()
            )
            self.errors[error_id] = error_info
        
        # Add to history
        self.error_history.append(error_info)
        
        # Update component health
        await self._update_component_health(context.component, error_info)
        
        # Log error
        self.logger.error(
            f"Error in {context.component}/{context.operation}: {exception}",
            exc_info=True,
            extra={
                "error_id": error_id,
                "severity": severity.value,
                "category": category.value,
                "context": context.__dict__
            }
        )
        
        # Collect metrics
        if self.metrics_collector:
            await self.metrics_collector.record_error(error_info)
        
        # Trigger error handlers
        await self._trigger_error_handlers(error_info)
        
        # Attempt recovery if enabled
        if auto_recover and not error_info.resolved:
            await self._attempt_recovery(error_info)
        
        return error_id
    
    async def _attempt_recovery(self, error_info: ErrorInfo):
        """Attempt to recover from an error"""
        component = error_info.context.component
        
        # Check circuit breaker
        if component not in self.circuit_breakers:
            self.circuit_breakers[component] = CircuitBreaker()
        
        breaker = self.circuit_breakers[component]
        if not breaker.can_execute():
            self.logger.warning(f"Circuit breaker open for {component}, skipping recovery")
            return
        
        # Find applicable recovery strategies
        strategies = self._find_recovery_strategies(error_info)
        
        for strategy in strategies:
            if error_info.recovery_attempts >= strategy.max_attempts:
                continue
            
            # Check cooldown
            if await self._is_in_cooldown(component, strategy):
                continue
            
            self.logger.info(f"Attempting recovery strategy '{strategy.name}' for {component}")
            
            try:
                success = await self._execute_recovery_strategy(strategy, error_info)
                
                if success:
                    error_info.resolved = True
                    error_info.resolution_time = datetime.now()
                    breaker.record_success()
                    
                    # Update component health
                    if component in self.component_health:
                        self.component_health[component].recovery_count += 1
                        self.component_health[component].health_score = min(100.0, 
                            self.component_health[component].health_score + 10.0)
                    
                    self.logger.info(f"Recovery successful for {component} using strategy '{strategy.name}'")
                    
                    # Notify success
                    if self.notification_system:
                        await self.notification_system.send_notification(
                            "Recovery Successful",
                            f"Component {component} recovered using {strategy.name}",
                            priority="medium"
                        )
                    
                    return
                else:
                    error_info.recovery_attempts += 1
                    breaker.record_failure()
                    
            except Exception as e:
                error_info.recovery_attempts += 1
                breaker.record_failure()
                self.logger.error(f"Recovery strategy '{strategy.name}' failed: {e}")
        
        # All recovery attempts failed
        if not error_info.resolved:
            await self._handle_recovery_failure(error_info)
    
    def _find_recovery_strategies(self, error_info: ErrorInfo) -> List[RecoveryStrategy]:
        """Find applicable recovery strategies for an error"""
        applicable_strategies = []
        
        for strategy in self.recovery_strategies.values():
            # Check conditions
            matches = True
            
            for condition_key, condition_value in strategy.conditions.items():
                if condition_key == "error_category":
                    if error_info.category != condition_value:
                        matches = False
                        break
                elif condition_key == "severity":
                    if error_info.severity != condition_value:
                        matches = False
                        break
                elif condition_key == "component":
                    if error_info.context.component != condition_value:
                        matches = False
                        break
            
            if matches:
                applicable_strategies.append(strategy)
        
        # Sort by priority (strategies with fewer max_attempts first)
        applicable_strategies.sort(key=lambda s: s.max_attempts)
        
        return applicable_strategies
    
    async def _execute_recovery_strategy(self, strategy: RecoveryStrategy, error_info: ErrorInfo) -> bool:
        """Execute a recovery strategy"""
        component = error_info.context.component
        
        try:
            for action in strategy.actions:
                success = await self._execute_recovery_action(action, component, error_info)
                if not success:
                    return False
            
            # Wait for success criteria
            if strategy.success_criteria:
                return await self._check_success_criteria(strategy, component)
            
            return True
            
        except asyncio.TimeoutError:
            self.logger.error(f"Recovery strategy '{strategy.name}' timed out")
            return False
        except Exception as e:
            self.logger.error(f"Recovery strategy '{strategy.name}' failed: {e}")
            return False
    
    async def _execute_recovery_action(self, action: RecoveryAction, component: str, error_info: ErrorInfo) -> bool:
        """Execute a specific recovery action"""
        try:
            if action == RecoveryAction.RESTART_SERVICE:
                if self.service_manager:
                    return await self.service_manager.restart_service(component)
                
            elif action == RecoveryAction.RESTART_COMPONENT:
                # Component-specific restart logic
                return await self._restart_component(component)
                
            elif action == RecoveryAction.RESET_STATE:
                return await self._reset_component_state(component)
                
            elif action == RecoveryAction.FALLBACK_MODE:
                return await self._enable_fallback_mode(component)
                
            elif action == RecoveryAction.ALERT_USER:
                if self.notification_system:
                    await self.notification_system.send_alert(
                        f"System Error in {component}",
                        error_info.message,
                        severity=error_info.severity.value
                    )
                return True
                
            elif action == RecoveryAction.SHUTDOWN_SYSTEM:
                # Critical system shutdown
                self.logger.critical("Initiating emergency system shutdown")
                if self.service_manager:
                    await self.service_manager.emergency_shutdown()
                return True
                
            elif action == RecoveryAction.CUSTOM:
                # Custom recovery handler
                handler_name = f"{component}_recovery"
                if handler_name in self.recovery_handlers:
                    return await self.recovery_handlers[handler_name](error_info)
                
            return False
            
        except Exception as e:
            self.logger.error(f"Recovery action {action.value} failed: {e}")
            return False
    
    async def _restart_component(self, component: str) -> bool:
        """Restart a specific component"""
        try:
            # Component restart logic would be implemented based on component type
            self.logger.info(f"Restarting component: {component}")
            await asyncio.sleep(1)  # Simulate restart time
            return True
        except Exception as e:
            self.logger.error(f"Failed to restart component {component}: {e}")
            return False
    
    async def _reset_component_state(self, component: str) -> bool:
        """Reset component state"""
        try:
            self.logger.info(f"Resetting state for component: {component}")
            await asyncio.sleep(0.5)  # Simulate reset time
            return True
        except Exception as e:
            self.logger.error(f"Failed to reset component {component}: {e}")
            return False
    
    async def _enable_fallback_mode(self, component: str) -> bool:
        """Enable fallback mode for component"""
        try:
            self.logger.info(f"Enabling fallback mode for component: {component}")
            # Implement fallback logic
            return True
        except Exception as e:
            self.logger.error(f"Failed to enable fallback mode for {component}: {e}")
            return False
    
    async def _check_success_criteria(self, strategy: RecoveryStrategy, component: str) -> bool:
        """Check if recovery was successful"""
        # Wait a moment for component to stabilize
        await asyncio.sleep(2)
        
        # Check component health
        if component in self.component_health:
            health = self.component_health[component]
            return health.is_healthy
        
        return True
    
    async def _is_in_cooldown(self, component: str, strategy: RecoveryStrategy) -> bool:
        """Check if component is in cooldown period"""
        # Implementation would track last recovery attempts
        return False
    
    async def _handle_recovery_failure(self, error_info: ErrorInfo):
        """Handle case where all recovery attempts failed"""
        component = error_info.context.component
        
        self.logger.error(f"All recovery attempts failed for {component}")
        
        # Update component health
        if component in self.component_health:
            health = self.component_health[component]
            health.is_healthy = False
            health.health_score = max(0.0, health.health_score - 20.0)
            health.status_message = "Recovery failed"
        
        # Send critical alert
        if self.notification_system and not error_info.user_notified:
            await self.notification_system.send_alert(
                f"Critical: Component {component} Recovery Failed",
                f"Unable to recover from error: {error_info.message}",
                severity="critical"
            )
            error_info.user_notified = True
        
        # Consider component degradation or shutdown
        if error_info.severity == ErrorSeverity.CRITICAL:
            await self._handle_critical_failure(error_info)
    
    async def _handle_critical_failure(self, error_info: ErrorInfo):
        """Handle critical system failures"""
        component = error_info.context.component
        
        self.logger.critical(f"Critical failure in {component}: {error_info.message}")
        
        # Implement critical failure logic (e.g., safe shutdown)
        if component in ["safety", "power_management"]:
            self.logger.critical("Critical component failure - initiating safe shutdown")
            if self.service_manager:
                await self.service_manager.safe_shutdown()
    
    async def _update_component_health(self, component: str, error_info: ErrorInfo):
        """Update component health based on error"""
        if component not in self.component_health:
            self.component_health[component] = ComponentHealth(component_name=component)
        
        health = self.component_health[component]
        health.error_count += 1
        health.last_error = datetime.now()
        
        # Adjust health score based on severity
        severity_penalties = {
            ErrorSeverity.CRITICAL: 30.0,
            ErrorSeverity.HIGH: 20.0,
            ErrorSeverity.MEDIUM: 10.0,
            ErrorSeverity.LOW: 5.0,
            ErrorSeverity.INFO: 1.0
        }
        
        penalty = severity_penalties.get(error_info.severity, 10.0)
        health.health_score = max(0.0, health.health_score - penalty)
        
        # Update health status
        if health.health_score < 30.0:
            health.is_healthy = False
            health.status_message = "Critical"
        elif health.health_score < 60.0:
            health.is_healthy = False
            health.status_message = "Degraded"
        elif health.health_score < 80.0:
            health.status_message = "Warning"
        else:
            health.status_message = "OK"
    
    async def _trigger_error_handlers(self, error_info: ErrorInfo):
        """Trigger registered error handlers"""
        handlers = self.error_handlers.get(error_info.category, [])
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(error_info)
                else:
                    handler(error_info)
            except Exception as e:
                self.logger.error(f"Error handler failed: {e}")
    
    def _generate_error_id(self, exception: Exception, context: ErrorContext) -> str:
        """Generate unique error ID"""
        error_signature = f"{type(exception).__name__}:{context.component}:{context.operation}:{str(exception)}"
        return f"err_{hash(error_signature) & 0x7FFFFFFF:08x}"
    
    async def _health_monitor_loop(self):
        """Background health monitoring loop"""
        while self.running:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.config["health_check_interval"])
            except Exception as e:
                self.logger.error(f"Health monitor loop error: {e}")
                await asyncio.sleep(5)
    
    async def _error_aggregation_loop(self):
        """Background error aggregation loop"""
        while self.running:
            try:
                await self._aggregate_errors()
                await asyncio.sleep(60)  # Run every minute
            except Exception as e:
                self.logger.error(f"Error aggregation loop error: {e}")
                await asyncio.sleep(30)
    
    async def _perform_health_checks(self):
        """Perform health checks on all components"""
        current_time = datetime.now()
        
        for component_name, health in self.component_health.items():
            # Calculate uptime
            if health.last_error:
                health.uptime_seconds = (current_time - health.last_error).total_seconds()
            
            # Improve health score over time for stable components
            if health.is_healthy and health.health_score < 100.0:
                health.health_score = min(100.0, health.health_score + 0.1)
    
    async def _aggregate_errors(self):
        """Aggregate and analyze error patterns"""
        # Clean up old resolved errors
        current_time = datetime.now()
        retention_time = timedelta(days=self.config["log_retention_days"])
        
        expired_errors = [
            error_id for error_id, error_info in self.errors.items()
            if error_info.resolved and (current_time - error_info.resolution_time) > retention_time
        ]
        
        for error_id in expired_errors:
            del self.errors[error_id]
    
    async def _load_configuration(self):
        """Load error recovery configuration"""
        if self.config_manager:
            try:
                config = await self.config_manager.get_config("error_recovery")
                if config:
                    self.config.update(config)
            except Exception as e:
                self.logger.warning(f"Failed to load error recovery config: {e}")
    
    # Public API methods
    
    def register_error_handler(self, category: ErrorCategory, handler: Callable):
        """Register an error handler for a specific category"""
        self.error_handlers[category].append(handler)
    
    def register_recovery_handler(self, component: str, handler: Callable):
        """Register a custom recovery handler for a component"""
        self.recovery_handlers[f"{component}_recovery"] = handler
    
    def add_recovery_strategy(self, strategy: RecoveryStrategy):
        """Add a custom recovery strategy"""
        self.recovery_strategies[strategy.name] = strategy
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get error summary statistics"""
        now = datetime.now()
        recent_errors = [e for e in self.error_history if (now - e.timestamp).total_seconds() < 3600]
        
        return {
            "total_errors": len(self.errors),
            "recent_errors": len(recent_errors),
            "resolved_errors": len([e for e in self.errors.values() if e.resolved]),
            "component_health": {
                name: {
                    "is_healthy": health.is_healthy,
                    "health_score": health.health_score,
                    "error_count": health.error_count,
                    "recovery_count": health.recovery_count,
                    "status_message": health.status_message
                }
                for name, health in self.component_health.items()
            },
            "error_categories": {
                category.value: len([e for e in self.errors.values() if e.category == category])
                for category in ErrorCategory
            }
        }
    
    def get_component_health(self, component: str) -> Optional[Dict[str, Any]]:
        """Get health information for a specific component"""
        if component in self.component_health:
            health = self.component_health[component]
            return {
                "component_name": health.component_name,
                "is_healthy": health.is_healthy,
                "health_score": health.health_score,
                "error_count": health.error_count,
                "warning_count": health.warning_count,
                "last_error": health.last_error.isoformat() if health.last_error else None,
                "recovery_count": health.recovery_count,
                "uptime_seconds": health.uptime_seconds,
                "status_message": health.status_message
            }
        return None
    
    async def shutdown(self):
        """Shutdown the error recovery system"""
        self.running = False
        
        # Cancel recovery tasks
        for task in self._recovery_tasks.values():
            if not task.done():
                task.cancel()
        
        self.logger.info("Error Recovery System shut down")
