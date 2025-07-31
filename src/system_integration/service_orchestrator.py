"""
Service Orchestrator - Manages individual services with dependency handling and automatic restart
"""

import asyncio
import logging
import subprocess
import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


class ServiceState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"
    RESTARTING = "restarting"


@dataclass
class ServiceConfig:
    """Configuration for a system service"""
    name: str
    service_file: str
    dependencies: List[str]
    critical: bool = False
    restart_policy: str = "always"
    restart_delay: float = 5.0
    max_restarts: int = 3
    timeout: float = 30.0
    resource_limits: Optional[Dict] = None


@dataclass
class ServiceStatus:
    """Status of a system service"""
    name: str
    state: ServiceState
    pid: Optional[int]
    start_time: Optional[float]
    restart_count: int
    last_restart: Optional[float]
    error_message: Optional[str]


class ServiceOrchestrator:
    """
    Orchestrates system services using systemd
    Handles dependencies, restart policies, and health monitoring
    """
    
    def __init__(self):
        self.services: Dict[str, ServiceConfig] = {}
        self.service_status: Dict[str, ServiceStatus] = {}
        self.restart_tasks: Dict[str, asyncio.Task] = {}
        
        # Track service dependencies
        self.dependency_graph: Dict[str, Set[str]] = {}
        self.reverse_dependencies: Dict[str, Set[str]] = {}
        
    async def initialize(self, system_config: Dict):
        """Initialize the service orchestrator"""
        logger.info("Initializing Service Orchestrator")
        
        # Load service configurations
        await self._load_service_configs(system_config)
        
        # Build dependency graph
        self._build_dependency_graph()
        
        # Initialize service status
        for service_name in self.services:
            self.service_status[service_name] = ServiceStatus(
                name=service_name,
                state=ServiceState.STOPPED,
                pid=None,
                start_time=None,
                restart_count=0,
                last_restart=None,
                error_message=None
            )
        
        logger.info(f"Service orchestrator initialized with {len(self.services)} services")
    
    async def _load_service_configs(self, system_config: Dict):
        """Load service configurations"""
        services_config = system_config.get('services', {})
        
        # Define default service configurations
        default_services = {
            'communication': ServiceConfig(
                name='communication',
                service_file='lawnberry-communication.service',
                dependencies=[],
                critical=True
            ),
            'data_management': ServiceConfig(
                name='data_management', 
                service_file='lawnberry-data.service',
                dependencies=['communication'],
                critical=True
            ),
            'hardware': ServiceConfig(
                name='hardware',
                service_file='lawnberry-hardware.service', 
                dependencies=['communication', 'data_management'],
                critical=True
            ),
            'sensor_fusion': ServiceConfig(
                name='sensor_fusion',
                service_file='lawnberry-sensor-fusion.service',
                dependencies=['hardware', 'communication'],
                critical=False
            ),
            'weather': ServiceConfig(
                name='weather',
                service_file='lawnberry-weather.service',
                dependencies=['communication', 'data_management'],
                critical=False
            ),
            'power_management': ServiceConfig(
                name='power_management',
                service_file='lawnberry-power.service',
                dependencies=['hardware', 'communication'],
                critical=False
            ),
            'safety': ServiceConfig(
                name='safety',
                service_file='lawnberry-safety.service',
                dependencies=['hardware', 'sensor_fusion', 'communication'],
                critical=True
            ),
            'vision': ServiceConfig(
                name='vision',
                service_file='lawnberry-vision.service',
                dependencies=['hardware', 'communication'],
                critical=False
            ),
            'web_api': ServiceConfig(
                name='web_api',
                service_file='lawnberry-api.service',
                dependencies=['communication', 'data_management'],
                critical=False
            )
        }
        
        # Merge with user configuration
        for service_name, default_config in default_services.items():
            user_config = services_config.get(service_name, {})
            
            # Update config with user overrides
            config_dict = {
                'name': service_name,
                'service_file': user_config.get('service_file', default_config.service_file),
                'dependencies': user_config.get('dependencies', default_config.dependencies),
                'critical': user_config.get('critical', default_config.critical),
                'restart_policy': user_config.get('restart_policy', default_config.restart_policy),
                'restart_delay': user_config.get('restart_delay', default_config.restart_delay),
                'max_restarts': user_config.get('max_restarts', default_config.max_restarts),
                'timeout': user_config.get('timeout', default_config.timeout),
                'resource_limits': user_config.get('resource_limits')
            }
            
            self.services[service_name] = ServiceConfig(**config_dict)
    
    def _build_dependency_graph(self):
        """Build service dependency graph"""
        for service_name, config in self.services.items():
            self.dependency_graph[service_name] = set(config.dependencies)
            
            # Build reverse dependencies
            for dep in config.dependencies:
                if dep not in self.reverse_dependencies:
                    self.reverse_dependencies[dep] = set()
                self.reverse_dependencies[dep].add(service_name)
    
    async def has_service(self, service_name: str) -> bool:
        """Check if service exists"""
        return service_name in self.services
    
    async def start_service(self, service_name: str):
        """Start a service and its dependencies"""
        if service_name not in self.services:
            raise ValueError(f"Unknown service: {service_name}")
        
        # Start dependencies first
        for dep in self.services[service_name].dependencies:
            if self.service_status[dep].state != ServiceState.RUNNING:
                await self.start_service(dep)
        
        # Start the service itself
        await self._start_single_service(service_name)
    
    async def _start_single_service(self, service_name: str):
        """Start a single service using systemd"""
        config = self.services[service_name]
        status = self.service_status[service_name]
        
        if status.state in [ServiceState.RUNNING, ServiceState.STARTING]:
            logger.debug(f"Service {service_name} already starting/running")
            return
        
        try:
            logger.info(f"Starting service: {service_name}")
            status.state = ServiceState.STARTING
            
            # Use systemctl to start the service
            result = await asyncio.create_subprocess_exec(
                'systemctl', 'start', config.service_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                # Service started successfully
                status.state = ServiceState.RUNNING
                status.start_time = time.time()
                status.error_message = None
                
                # Get PID
                status.pid = await self._get_service_pid(config.service_file)
                
                logger.info(f"Service {service_name} started successfully (PID: {status.pid})")
                
            else:
                # Service failed to start
                error_msg = stderr.decode().strip()
                logger.error(f"Failed to start service {service_name}: {error_msg}")
                status.state = ServiceState.FAILED
                status.error_message = error_msg
                raise RuntimeError(f"Failed to start {service_name}: {error_msg}")
                
        except Exception as e:
            logger.error(f"Exception starting service {service_name}: {e}")
            status.state = ServiceState.FAILED
            status.error_message = str(e)
            raise
    
    async def stop_service(self, service_name: str):
        """Stop a service and its dependents"""
        if service_name not in self.services:
            raise ValueError(f"Unknown service: {service_name}")
        
        # Stop dependents first
        dependents = self.reverse_dependencies.get(service_name, set())
        for dependent in dependents:
            if self.service_status[dependent].state == ServiceState.RUNNING:
                await self.stop_service(dependent)
        
        # Stop the service itself
        await self._stop_single_service(service_name)
    
    async def _stop_single_service(self, service_name: str):
        """Stop a single service using systemd"""
        config = self.services[service_name]
        status = self.service_status[service_name]
        
        if status.state in [ServiceState.STOPPED, ServiceState.STOPPING]:
            logger.debug(f"Service {service_name} already stopped/stopping")
            return
        
        try:
            logger.info(f"Stopping service: {service_name}")
            status.state = ServiceState.STOPPING
            
            # Use systemctl to stop the service
            result = await asyncio.create_subprocess_exec(
                'systemctl', 'stop', config.service_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                status.state = ServiceState.STOPPED
                status.pid = None
                status.error_message = None
                logger.info(f"Service {service_name} stopped successfully")
            else:
                error_msg = stderr.decode().strip()
                logger.error(f"Failed to stop service {service_name}: {error_msg}")
                status.error_message = error_msg
                
        except Exception as e:
            logger.error(f"Exception stopping service {service_name}: {e}")
            status.error_message = str(e)
    
    async def restart_service(self, service_name: str):
        """Restart a service"""
        if service_name not in self.services:
            raise ValueError(f"Unknown service: {service_name}")
        
        config = self.services[service_name]
        status = self.service_status[service_name]
        
        logger.info(f"Restarting service: {service_name}")
        status.state = ServiceState.RESTARTING
        status.restart_count += 1
        status.last_restart = time.time()
        
        try:
            # Stop the service
            await self._stop_single_service(service_name)
            
            # Wait for restart delay
            await asyncio.sleep(config.restart_delay)
            
            # Start the service
            await self._start_single_service(service_name)
            
        except Exception as e:
            logger.error(f"Failed to restart service {service_name}: {e}")
            status.state = ServiceState.FAILED
            status.error_message = str(e)
            raise
    
    async def restart_service_with_backoff(self, service_name: str):
        """Restart service with exponential backoff"""
        if service_name in self.restart_tasks:
            # Already restarting
            return
        
        config = self.services[service_name]
        status = self.service_status[service_name]
        
        if status.restart_count >= config.max_restarts:
            logger.error(f"Service {service_name} exceeded max restart attempts")
            return
        
        # Calculate backoff delay
        backoff_delay = min(
            config.restart_delay * (2 ** status.restart_count),
            60.0  # Max 60 seconds
        )
        
        async def restart_with_delay():
            try:
                logger.info(f"Restarting {service_name} in {backoff_delay}s (attempt {status.restart_count + 1})")
                await asyncio.sleep(backoff_delay)
                await self.restart_service(service_name)
            except Exception as e:
                logger.error(f"Restart attempt failed for {service_name}: {e}")
            finally:
                self.restart_tasks.pop(service_name, None)
        
        self.restart_tasks[service_name] = asyncio.create_task(restart_with_delay())
    
    async def emergency_stop_all(self):
        """Emergency stop all services immediately"""
        logger.critical("Emergency stopping all services")
        
        # Cancel any pending restart tasks
        for task in self.restart_tasks.values():
            task.cancel()
        self.restart_tasks.clear()
        
        # Stop all services in parallel
        stop_tasks = []
        for service_name in self.services:
            if self.service_status[service_name].state == ServiceState.RUNNING:
                task = asyncio.create_task(self._emergency_stop_service(service_name))
                stop_tasks.append(task)
        
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)
    
    async def _emergency_stop_service(self, service_name: str):
        """Emergency stop a single service"""
        try:
            config = self.services[service_name]
            
            # Force stop using systemctl
            result = await asyncio.create_subprocess_exec(
                'systemctl', 'kill', '--signal=SIGKILL', config.service_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await result.communicate()
            
            self.service_status[service_name].state = ServiceState.STOPPED
            self.service_status[service_name].pid = None
            
        except Exception as e:
            logger.error(f"Failed to emergency stop {service_name}: {e}")
    
    async def _get_service_pid(self, service_file: str) -> Optional[int]:
        """Get the PID of a systemd service"""
        try:
            result = await asyncio.create_subprocess_exec(
                'systemctl', 'show', '--property=MainPID', service_file,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                output = stdout.decode().strip()
                if output.startswith('MainPID='):
                    pid_str = output.split('=')[1]
                    return int(pid_str) if pid_str != '0' else None
            
        except Exception:
            pass
        
        return None
    
    def get_service_status(self, service_name: str) -> Optional[ServiceStatus]:
        """Get status of a specific service"""
        return self.service_status.get(service_name)
    
    def get_all_service_status(self) -> Dict[str, ServiceStatus]:
        """Get status of all services"""
        return self.service_status.copy()
    
    async def is_service_running(self, service_name: str) -> bool:
        """Check if a service is running"""
        status = self.service_status.get(service_name)
        return status is not None and status.state == ServiceState.RUNNING
