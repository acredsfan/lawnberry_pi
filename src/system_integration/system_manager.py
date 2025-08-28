"""
System Manager - Master orchestration for Lawnberry autonomous mower
Coordinates all subsystems with proper startup sequence, health monitoring, and graceful shutdown
Enhanced with dynamic resource management and performance optimization
"""

import asyncio
import logging
import signal
import sys
from typing import Dict, List, Optional, Set, Any
from pathlib import Path
from dataclasses import dataclass
from enum import Enum
import json
from datetime import datetime

from .service_orchestrator import ServiceOrchestrator
from .config_manager import ConfigManager
from .health_monitor import HealthMonitor
from .state_machine import SystemStateMachine, SystemState
from .deployment_manager import DeploymentManager
from .build_system import BuildSystem
from .fleet_manager import FleetManager
from .system_monitor import SystemMonitor
from .enhanced_system_monitor import EnhancedSystemMonitor
from .dynamic_resource_manager import OperationMode


logger = logging.getLogger(__name__)


@dataclass
class SystemStatus:
    """Overall system status with enhanced performance metrics"""
    state: SystemState
    uptime: float
    services_running: int
    services_total: int
    cpu_usage: float
    memory_usage: float
    last_update: datetime
    errors: List[str]
    deployment_status: Optional[Dict[str, str]]
    fleet_status: Optional[Dict[str, str]]
    # Enhanced performance fields
    operation_mode: str
    resource_efficiency: float
    dynamic_optimization_active: bool
    performance_score: float
    active_alerts: int


class SystemManager:
    """
    Master system manager that orchestrates all Lawnberry subsystems
    Enhanced with dynamic resource management and performance optimization
    """
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.service_orchestrator = ServiceOrchestrator()
        self.health_monitor = HealthMonitor()
        self.state_machine = SystemStateMachine()
        
        # Enhanced performance monitoring
        self.enhanced_monitor = EnhancedSystemMonitor(self.config_manager)
        
        # Deployment automation components
        self.deployment_manager = DeploymentManager(
            self.config_manager, 
            self.health_monitor, 
            self.state_machine
        )
        self.build_system = BuildSystem(self.config_manager)
        self.fleet_manager = FleetManager(self.config_manager)
        self.system_monitor = SystemMonitor(self.config_manager)
        
        self.running = False
        self.shutdown_event = asyncio.Event()
        self.start_time = datetime.now()
        
        # Service coordination
        self._service_tasks: Dict[str, asyncio.Task] = {}
        self._critical_services: Set[str] = {
            'safety', 'communication', 'hardware'
        }
        
    async def initialize(self):
        """Initialize the system manager and all subsystems"""
        try:
            logger.info("Initializing Lawnberry System Manager with Enhanced Performance Monitoring")
            
            # Load and validate configuration
            await self.config_manager.load_all_configs()
            
            # Initialize state machine
            await self.state_machine.initialize()
            
            # Initialize health monitor
            await self.health_monitor.initialize()
            
            # Initialize enhanced monitoring system
            await self.enhanced_monitor.initialize()
            
            # Initialize deployment automation components
            await self.system_monitor.initialize()
            await self.deployment_manager.initialize()
            await self.build_system.initialize()
            await self.fleet_manager.initialize()

            # Wire deployment event publisher via communication (MQTT) service if available later.
            # We defer lookup slightly to allow communication service startup to attach MQTT bridge.
            async def _publish_deployment_event(topic: str, payload: dict):
                """Publish deployment events over MQTT if communication layer exposes bridge.

                This function is resilient: it logs on failure instead of raising so deployment
                lifecycle isn't blocked by transport issues.
                """
                try:
                    # Attempt lazy import to avoid circular dependency at module import time
                    from web_api.main import create_app  # type: ignore
                except Exception:
                    create_app = None  # type: ignore
                # If web API already running inside same process with state
                bridge = None
                try:
                    # Potential future integration point: a global registry could expose bridge
                    from web_api.mqtt_bridge import MQTTBridge  # type: ignore
                except Exception:
                    MQTTBridge = None  # type: ignore
                # For now, try to discover an existing bridge cached on config manager (placeholder)
                bridge = getattr(self.config_manager, 'mqtt_bridge', None)
                if bridge and hasattr(bridge, 'publish_message'):
                    await bridge.publish_message(topic, payload, qos=1)
                else:
                    # Fallback: no-op (could enqueue for later retry if needed)
                    pass

            # Register publisher (safe if communication layer not yet available; emits no-ops until bridge attached)
            self.deployment_manager.register_event_publisher(_publish_deployment_event)
            
            # Set up signal handlers
            self._setup_signal_handlers()
            
            # Initialize service orchestrator
            await self.service_orchestrator.initialize(
                self.config_manager.get_system_config()
            )
            
            logger.info("System Manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize System Manager: {e}")
            await self.state_machine.transition_to(SystemState.ERROR)
            raise
    
    async def start_system(self):
        """Start all subsystems in the correct order"""
        try:
            logger.info("Starting Lawnberry system...")
            await self.state_machine.transition_to(SystemState.STARTING)
            
            # Start services in dependency order
            startup_sequence = [
                'communication',  # MQTT broker and messaging
                'data_management',  # Redis cache and database
                'hardware',  # Hardware interface layer
                'sensor_fusion',  # Sensor data processing 
                'weather',  # Weather service
                'power_management',  # Power monitoring
                'safety',  # Safety monitoring (critical)
                'vision',  # Computer vision
                'web_api',  # Web API backend
                'navigation'  # Navigation system (if implemented)
            ]
            
            for service_name in startup_sequence:
                if await self.service_orchestrator.has_service(service_name):
                    logger.info(f"Starting service: {service_name}")
                    await self.service_orchestrator.start_service(service_name)
                    
                    # Wait for service to be healthy
                    await self._wait_for_service_health(service_name)
                    
                    # Brief pause between services
                    await asyncio.sleep(1.0)
            
            # Start health monitoring
            self._service_tasks['health_monitor'] = asyncio.create_task(
                self.health_monitor.run()
            )
            
            # Start system monitoring loop
            self._service_tasks['system_monitor'] = asyncio.create_task(
                self._system_monitor_loop()
            )
            
            self.running = True
            await self.state_machine.transition_to(SystemState.RUNNING)
            
            logger.info("Lawnberry system started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start system: {e}")
            await self.state_machine.transition_to(SystemState.ERROR)
            await self.emergency_shutdown()
            raise
    
    async def _wait_for_service_health(self, service_name: str, timeout: float = 30.0):
        """Wait for a service to become healthy"""
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            if await self.health_monitor.is_service_healthy(service_name):
                return
            await asyncio.sleep(0.5)
        
        raise TimeoutError(f"Service {service_name} failed to become healthy within {timeout}s")
    
    async def _system_monitor_loop(self):
        """Main system monitoring loop"""
        while self.running and not self.shutdown_event.is_set():
            try:
                # Check overall system health
                system_health = await self.health_monitor.get_system_health()
                
                # Handle unhealthy services
                for service_name, health in system_health.service_health.items():
                    if not health.is_healthy:
                        await self._handle_unhealthy_service(service_name, health)
                
                # Update system state based on health
                await self._update_system_state(system_health)
                
                # Log system status periodically
                if int(asyncio.get_event_loop().time()) % 60 == 0:  # Every minute
                    await self._log_system_status()
                
                await asyncio.sleep(5.0)  # Monitor every 5 seconds
                
            except Exception as e:
                logger.error(f"Error in system monitor loop: {e}")
                await asyncio.sleep(10.0)
    
    async def _handle_unhealthy_service(self, service_name: str, health):
        """Handle an unhealthy service"""
        logger.warning(f"Service {service_name} is unhealthy: {health.status_message}")
        
        if service_name in self._critical_services:
            if health.restart_count < 3:  # Max 3 restart attempts
                logger.info(f"Attempting to restart critical service: {service_name}")
                await self.service_orchestrator.restart_service(service_name)
            else:
                logger.critical(f"Critical service {service_name} failed multiple times")
                await self.state_machine.transition_to(SystemState.ERROR)
        else:
            # Non-critical service - attempt restart with exponential backoff
            await self.service_orchestrator.restart_service_with_backoff(service_name)
    
    async def _update_system_state(self, system_health):
        """Update system state based on health metrics"""
        current_state = self.state_machine.current_state
        
        if current_state == SystemState.RUNNING:
            # Check if we should transition to degraded mode
            unhealthy_critical = any(
                not system_health.service_health.get(svc, True) 
                for svc in self._critical_services
            )
            
            if unhealthy_critical:
                await self.state_machine.transition_to(SystemState.DEGRADED)
        
        elif current_state == SystemState.DEGRADED:
            # Check if we can return to running
            all_critical_healthy = all(
                system_health.service_health.get(svc, False) 
                for svc in self._critical_services
            )
            
            if all_critical_healthy:
                await self.state_machine.transition_to(SystemState.RUNNING)
    
    async def _log_system_status(self):
        """Log periodic system status"""
        status = await self.get_system_status()
        logger.info(
            f"System Status - State: {status.state.value}, "
            f"Services: {status.services_running}/{status.services_total}, "
            f"CPU: {status.cpu_usage:.1f}%, Memory: {status.memory_usage:.1f}%, "
            f"Uptime: {status.uptime:.1f}s"
        )
    
    async def get_system_status(self) -> SystemStatus:
        """Get comprehensive system status"""
        system_health = await self.health_monitor.get_system_health()
        
        services_running = sum(
            1 for health in system_health.service_health.values() 
            if health.is_healthy
        )
        services_total = len(system_health.service_health)
        
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        # Get deployment and fleet status
        deployment_status = None
        fleet_status = None
        
        try:
            deployment_status = await self.deployment_manager.get_deployment_status()
        except Exception as e:
            logger.warning(f"Failed to get deployment status: {e}")
            
        try:
            fleet_status = await self.fleet_manager.get_fleet_status()
        except Exception as e:
            logger.warning(f"Failed to get fleet status: {e}")

        # Get enhanced performance metrics
        enhanced_status = await self.enhanced_monitor.get_comprehensive_status()
        system_overview = enhanced_status.get('system_overview', {})
        efficiency_metrics = enhanced_status.get('efficiency_metrics', {})

        return SystemStatus(
            state=self.state_machine.current_state,
            uptime=uptime,
            services_running=services_running,
            services_total=services_total,
            cpu_usage=system_health.resource_usage.cpu_percent,
            memory_usage=system_health.resource_usage.memory_percent,
            last_update=datetime.now(),
            errors=system_health.errors,
            deployment_status=deployment_status,
            fleet_status=fleet_status,
            # Enhanced performance fields
            operation_mode=system_overview.get('operation_mode', 'idle'),
            resource_efficiency=efficiency_metrics.get('overall_efficiency', 0.0),
            dynamic_optimization_active=system_overview.get('monitoring_active', False),
            performance_score=system_overview.get('system_stability', 0.0),
            active_alerts=system_overview.get('active_alerts', 0)
        )
    
    async def graceful_shutdown(self):
        """Gracefully shutdown all services"""
        logger.info("Initiating graceful system shutdown...")
        
        try:
            await self.state_machine.transition_to(SystemState.SHUTTING_DOWN)
            
            # Stop system monitoring
            self.running = False
            self.shutdown_event.set()
            
            # Cancel monitoring tasks
            for task_name, task in self._service_tasks.items():
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            # Shutdown services in reverse order
            shutdown_sequence = [
                'navigation', 'web_api', 'vision', 'safety',
                'power_management', 'weather', 'sensor_fusion',
                'hardware', 'data_management', 'communication'
            ]
            
            for service_name in shutdown_sequence:
                if await self.service_orchestrator.has_service(service_name):
                    logger.info(f"Stopping service: {service_name}")
                    await self.service_orchestrator.stop_service(service_name)
                    await asyncio.sleep(0.5)  # Brief pause
            
            # Stop deployment automation components
            await self.fleet_manager.shutdown()
            await self.deployment_manager.shutdown()
            await self.system_monitor.shutdown()
            
            # Stop enhanced monitoring system
            await self.enhanced_monitor.shutdown()
            
            # Stop health monitor
            await self.health_monitor.shutdown()
            
            # Save final state
            await self.state_machine.save_state()
            
            await self.state_machine.transition_to(SystemState.STOPPED)
            logger.info("System shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")
            await self.emergency_shutdown()
    
    async def emergency_shutdown(self):
        """Emergency shutdown - force stop all services"""
        logger.critical("Emergency system shutdown initiated")
        
        try:
            await self.state_machine.transition_to(SystemState.EMERGENCY_STOP)
            
            # Force stop all services immediately
            await self.service_orchestrator.emergency_stop_all()
            
            # Cancel all tasks
            for task in self._service_tasks.values():
                if not task.done():
                    task.cancel()
            
            self.running = False
            self.shutdown_event.set()
            
            logger.critical("Emergency shutdown completed")
            
        except Exception as e:
            logger.critical(f"Error during emergency shutdown: {e}")
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}")
            asyncio.create_task(self.graceful_shutdown())
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    
    async def run(self):
        """Main run loop - start system and wait for shutdown"""
        try:
            await self.initialize()
            await self.start_system()
            
            # Wait for shutdown event
            await self.shutdown_event.wait()
            
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Unexpected error in system manager: {e}")
        finally:
            if self.running:
                await self.graceful_shutdown()


async def main():
    """Main entry point for system integration"""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('/var/log/lawnberry/system.log')
        ]
    )
    
    # Create and run system manager
    system_manager = SystemManager()
    await system_manager.run()


if __name__ == "__main__":
    asyncio.run(main())
