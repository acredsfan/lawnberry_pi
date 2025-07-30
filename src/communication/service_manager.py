"""
Service Manager
Coordinates microservices communication and lifecycle management
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Set, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from datetime import datetime, timedelta

from .client import MQTTClient
from .message_protocols import (
    MessageProtocol, StatusMessage, EventMessage, AlertMessage,
    MessageType, Priority
)
from .topic_manager import topic_manager


class ServiceState(Enum):
    """Service state enumeration"""
    STARTING = "starting"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    ERROR = "error"
    OFFLINE = "offline"
    SHUTTING_DOWN = "shutting_down"


@dataclass
class ServiceInfo:
    """Service information"""
    service_id: str
    service_type: str
    version: str
    start_time: float
    last_heartbeat: float
    state: ServiceState
    dependencies: List[str]
    endpoints: Dict[str, str]
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'service_id': self.service_id,
            'service_type': self.service_type,
            'version': self.version,
            'start_time': self.start_time,
            'last_heartbeat': self.last_heartbeat,
            'state': self.state.value,
            'uptime': time.time() - self.start_time,
            'dependencies': self.dependencies,
            'endpoints': self.endpoints,
            'metadata': self.metadata
        }


class ServiceManager:
    """Manages microservices coordination and communication"""
    
    def __init__(self, service_id: str, service_type: str, 
                 mqtt_config: Dict[str, Any] = None):
        self.service_id = service_id
        self.service_type = service_type
        self.logger = logging.getLogger(f"{__name__}.{service_id}")
        
        # MQTT client
        self.mqtt_client = MQTTClient(service_id, mqtt_config)
        
        # Service registry
        self.services: Dict[str, ServiceInfo] = {}
        self.service_dependencies: Dict[str, Set[str]] = {}
        
        # Service state
        self.start_time = time.time()
        self.state = ServiceState.STARTING
        self.version = "1.0.0"
        self.dependencies: List[str] = []
        self.endpoints: Dict[str, str] = {}
        self.metadata: Dict[str, Any] = {}
        
        # Health monitoring
        self.heartbeat_interval = 30  # seconds
        self.heartbeat_timeout = 90   # seconds
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._health_monitor_task: Optional[asyncio.Task] = None
        
        # Event handlers
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._shutdown_handlers: List[Callable] = []
        
        # Service discovery
        self._discovery_cache: Dict[str, float] = {}
        self._discovery_timeout = 300  # 5 minutes
        
        # Performance metrics
        self.metrics = {
            'messages_sent': 0,
            'messages_received': 0,
            'commands_processed': 0,
            'errors': 0,
            'last_error': None
        }
        
        self._setup_mqtt_handlers()
    
    def _setup_mqtt_handlers(self):
        """Setup MQTT message handlers"""
        # Service discovery
        self.mqtt_client.add_message_handler(
            topic_manager.get_full_topic("system/services/+/status"),
            self._handle_service_status
        )
        
        # System events
        self.mqtt_client.add_message_handler(
            topic_manager.get_full_topic("system/events/+"),
            self._handle_system_event
        )
        
        # Health checks
        self.mqtt_client.add_message_handler(
            topic_manager.get_full_topic("system/health_check"),
            self._handle_health_check
        )
        
        # Service commands
        self.mqtt_client.add_command_handler("ping", self._handle_ping_command)
        self.mqtt_client.add_command_handler("status", self._handle_status_command)
        self.mqtt_client.add_command_handler("shutdown", self._handle_shutdown_command)
    
    async def initialize(self, dependencies: List[str] = None, 
                        endpoints: Dict[str, str] = None,
                        metadata: Dict[str, Any] = None) -> bool:
        """Initialize service manager"""
        try:
            self.logger.info(f"Initializing service manager for {self.service_id}")
            
            # Set service info
            self.dependencies = dependencies or []
            self.endpoints = endpoints or {}
            self.metadata = metadata or {}
            
            # Initialize MQTT client
            if not await self.mqtt_client.initialize():
                self.logger.error("Failed to initialize MQTT client")
                return False
            
            # Subscribe to relevant topics
            topics = topic_manager.get_topics_for_service(self.service_type)
            for topic in topics:
                await self.mqtt_client.subscribe(topic)
            
            # Start background tasks
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._health_monitor_task = asyncio.create_task(self._health_monitor_loop())
            
            # Wait for dependencies
            if self.dependencies:
                self.logger.info(f"Waiting for dependencies: {self.dependencies}")
                if not await self._wait_for_dependencies():
                    self.logger.error("Failed to resolve dependencies")
                    return False
            
            # Announce service availability
            self.state = ServiceState.HEALTHY
            await self._announce_service()
            
            self.logger.info("Service manager initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize service manager: {e}")
            self.state = ServiceState.ERROR
            return False
    
    async def shutdown(self):
        """Shutdown service manager gracefully"""
        self.logger.info("Shutting down service manager...")
        
        self.state = ServiceState.SHUTTING_DOWN
        
        # Call shutdown handlers
        for handler in self._shutdown_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
            except Exception as e:
                self.logger.error(f"Shutdown handler error: {e}")
        
        # Announce shutdown
        await self._announce_service()
        
        # Cancel background tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._health_monitor_task:
            self._health_monitor_task.cancel()
        
        # Wait for tasks to complete
        for task in [self._heartbeat_task, self._health_monitor_task]:
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Shutdown MQTT client
        await self.mqtt_client.shutdown()
        
        self.logger.info("Service manager shut down")
    
    async def _wait_for_dependencies(self, timeout: float = 60) -> bool:
        """Wait for service dependencies to be available"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            missing_deps = []
            
            for dep in self.dependencies:
                if not self._is_service_available(dep):
                    missing_deps.append(dep)
            
            if not missing_deps:
                self.logger.info("All dependencies resolved")
                return True
            
            self.logger.debug(f"Waiting for dependencies: {missing_deps}")
            await asyncio.sleep(5)
        
        self.logger.error(f"Timeout waiting for dependencies: {missing_deps}")
        return False
    
    def _is_service_available(self, service_id: str) -> bool:
        """Check if service is available"""
        if service_id not in self.services:
            return False
        
        service = self.services[service_id]
        if service.state in [ServiceState.OFFLINE, ServiceState.ERROR]:
            return False
        
        # Check heartbeat timeout
        if time.time() - service.last_heartbeat > self.heartbeat_timeout:
            return False
        
        return True
    
    async def _announce_service(self):
        """Announce service status"""
        service_info = ServiceInfo(
            service_id=self.service_id,
            service_type=self.service_type,
            version=self.version,
            start_time=self.start_time,
            last_heartbeat=time.time(),
            state=self.state,
            dependencies=self.dependencies,
            endpoints=self.endpoints,
            metadata=self.metadata
        )
        
        # Update local registry
        self.services[self.service_id] = service_info
        
        # Publish status
        status_msg = StatusMessage.create(
            sender=self.service_id,
            status=self.state.value,
            details=service_info.to_dict()
        )
        
        topic = f"system/services/{self.service_id}/status"
        await self.mqtt_client.publish(
            topic_manager.get_full_topic(topic),
            status_msg,
            retain=True
        )
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats"""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self._announce_service()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Heartbeat error: {e}")
                await asyncio.sleep(5)
    
    async def _health_monitor_loop(self):
        """Monitor service health"""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                # Check for stale services
                current_time = time.time()
                stale_services = []
                
                for service_id, service in self.services.items():
                    if service_id == self.service_id:
                        continue
                    
                    if current_time - service.last_heartbeat > self.heartbeat_timeout:
                        stale_services.append(service_id)
                
                # Mark stale services as offline
                for service_id in stale_services:
                    if self.services[service_id].state != ServiceState.OFFLINE:
                        self.logger.warning(f"Service {service_id} appears to be offline")
                        self.services[service_id].state = ServiceState.OFFLINE
                        
                        # Emit event
                        await self.emit_event("service_offline", {
                            'service_id': service_id,
                            'last_seen': self.services[service_id].last_heartbeat
                        })
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(10)
    
    async def _handle_service_status(self, topic: str, message: MessageProtocol):
        """Handle service status updates"""
        try:
            if message.metadata.message_type != MessageType.STATUS:
                return
            
            service_id = message.metadata.sender
            status_data = message.payload.get('details', {})
            
            # Update service registry
            if 'service_type' in status_data:
                service_info = ServiceInfo(
                    service_id=service_id,
                    service_type=status_data['service_type'],
                    version=status_data.get('version', '1.0.0'),
                    start_time=status_data.get('start_time', time.time()),
                    last_heartbeat=message.metadata.timestamp,
                    state=ServiceState(status_data.get('state', 'healthy')),
                    dependencies=status_data.get('dependencies', []),
                    endpoints=status_data.get('endpoints', {}),
                    metadata=status_data.get('metadata', {})
                )
                
                # Check for state changes
                old_service = self.services.get(service_id)
                if old_service and old_service.state != service_info.state:
                    await self.emit_event("service_state_change", {
                        'service_id': service_id,
                        'old_state': old_service.state.value,
                        'new_state': service_info.state.value
                    })
                
                self.services[service_id] = service_info
                
                # Cache for discovery
                self._discovery_cache[service_id] = time.time()
            
        except Exception as e:
            self.logger.error(f"Error handling service status: {e}")
    
    async def _handle_system_event(self, topic: str, message: MessageProtocol):
        """Handle system events"""
        try:
            if message.metadata.message_type != MessageType.EVENT:
                return
            
            event_type = message.payload.get('event_type')
            if event_type in self._event_handlers:
                for handler in self._event_handlers[event_type]:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(message.payload)
                        else:
                            handler(message.payload)
                    except Exception as e:
                        self.logger.error(f"Event handler error: {e}")
            
        except Exception as e:
            self.logger.error(f"Error handling system event: {e}")
    
    async def _handle_health_check(self, topic: str, message: Any):
        """Handle health check requests"""
        try:
            # Respond with current status
            await self._announce_service()
        except Exception as e:
            self.logger.error(f"Health check error: {e}")
    
    async def _handle_ping_command(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ping command"""
        return {
            'pong': True,
            'timestamp': time.time(),
            'service_id': self.service_id,
            'uptime': time.time() - self.start_time
        }
    
    async def _handle_status_command(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle status command"""
        return {
            'service_id': self.service_id,
            'state': self.state.value,
            'uptime': time.time() - self.start_time,
            'metrics': self.metrics.copy(),
            'mqtt_stats': self.mqtt_client.get_stats()
        }
    
    async def _handle_shutdown_command(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle shutdown command"""
        asyncio.create_task(self.shutdown())
        return {'shutting_down': True}
    
    # Public API methods
    
    def add_event_handler(self, event_type: str, handler: Callable):
        """Add event handler"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    def add_shutdown_handler(self, handler: Callable):
        """Add shutdown handler"""
        self._shutdown_handlers.append(handler)
    
    async def emit_event(self, event_type: str, event_data: Dict[str, Any], 
                        priority: Priority = Priority.NORMAL):
        """Emit system event"""
        event_msg = EventMessage.create(
            sender=self.service_id,
            event_type=event_type,
            event_data=event_data,
            priority=priority
        )
        
        topic = f"system/events/{event_type}"
        await self.mqtt_client.publish(
            topic_manager.get_full_topic(topic),
            event_msg
        )
    
    async def emit_alert(self, alert_type: str, message: str, 
                        severity: str = 'warning'):
        """Emit alert"""
        alert_msg = AlertMessage.create(
            sender=self.service_id,
            alert_type=alert_type,
            message=message,
            severity=severity
        )
        
        topic = f"safety/alerts/{alert_type}"
        await self.mqtt_client.publish(
            topic_manager.get_full_topic(topic),
            alert_msg,
            retain=True
        )
    
    async def send_command(self, target: str, command: str, 
                          parameters: Dict[str, Any] = None, 
                          timeout: float = 30) -> Any:
        """Send command to another service"""
        return await self.mqtt_client.send_command(target, command, parameters, timeout)
    
    def discover_services(self, service_type: str = None) -> List[ServiceInfo]:
        """Discover available services"""
        services = []
        for service in self.services.values():
            if service_type is None or service.service_type == service_type:
                if self._is_service_available(service.service_id):
                    services.append(service)
        return services
    
    def get_service(self, service_id: str) -> Optional[ServiceInfo]:
        """Get specific service info"""
        return self.services.get(service_id)
    
    def set_state(self, state: ServiceState):
        """Update service state"""
        if self.state != state:
            old_state = self.state
            self.state = state
            self.logger.info(f"Service state changed: {old_state.value} -> {state.value}")
            
            # Announce state change
            asyncio.create_task(self._announce_service())
    
    def update_metrics(self, **kwargs):
        """Update service metrics"""
        for key, value in kwargs.items():
            if key in self.metrics:
                self.metrics[key] = value
    
    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            'service_id': self.service_id,
            'service_type': self.service_type,
            'state': self.state.value,
            'uptime': time.time() - self.start_time,
            'known_services': len(self.services),
            'dependencies': self.dependencies,
            'metrics': self.metrics.copy(),
            'mqtt_stats': self.mqtt_client.get_stats()
        }
