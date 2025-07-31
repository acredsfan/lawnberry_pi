"""
Health Monitor - Comprehensive system health monitoring with automatic recovery
"""

import asyncio
import logging
import psutil
import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ServiceHealth:
    """Health status of a service"""
    name: str
    is_healthy: bool
    status_message: str
    last_check: datetime
    response_time_ms: Optional[float]
    restart_count: int
    error_count: int
    cpu_percent: float
    memory_mb: float


@dataclass
class ResourceUsage:
    """System resource usage metrics"""
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    network_bytes_sent: int
    network_bytes_recv: int
    temperature_celsius: Optional[float]
    timestamp: datetime


@dataclass
class SystemHealth:
    """Overall system health status"""
    is_healthy: bool
    service_health: Dict[str, ServiceHealth]
    resource_usage: ResourceUsage
    alerts: List[str]
    errors: List[str]
    uptime_seconds: float
    last_update: datetime


class HealthMonitor:
    """
    Comprehensive health monitoring system
    Monitors services, resources, and system metrics with alerting
    """
    
    def __init__(self):
        self.running = False
        self.service_health: Dict[str, ServiceHealth] = {}
        self.resource_history: List[ResourceUsage] = []
        self.alert_thresholds = {
            'cpu_percent': 90.0,
            'memory_percent': 85.0,
            'disk_percent': 90.0,
            'service_restart_limit': 3,
            'temperature_celsius': 75.0
        }
        
        # Health check intervals
        self.service_check_interval = 5.0  # seconds
        self.resource_check_interval = 10.0  # seconds
        
        # Circuit breaker for services
        self.circuit_breakers: Dict[str, Dict] = {}
        
        # Metrics storage
        self.metrics_file = Path('/var/lib/lawnberry/health_metrics.json')
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        
        # System start time
        self.system_start_time = time.time()
    
    async def initialize(self):
        """Initialize the health monitor"""
        logger.info("Initializing Health Monitor")
        
        # Load historical metrics if available
        await self._load_metrics_history()
        
        # Initialize service health tracking
        await self._initialize_service_tracking()
        
        logger.info("Health Monitor initialized")
    
    async def _load_metrics_history(self):
        """Load historical metrics from file"""
        try:
            if self.metrics_file.exists():
                with open(self.metrics_file, 'r') as f:
                    data = json.load(f)
                    # Convert timestamps back to datetime objects
                    for metric in data.get('resource_history', []):
                        metric['timestamp'] = datetime.fromisoformat(metric['timestamp'])
                    self.resource_history = data.get('resource_history', [])[-100:]  # Keep last 100
                    logger.info(f"Loaded {len(self.resource_history)} historical metrics")
        except Exception as e:
            logger.warning(f"Could not load metrics history: {e}")
    
    async def _save_metrics_history(self):
        """Save metrics history to file"""
        try:
            data = {
                'resource_history': [
                    {
                        **metric.__dict__,
                        'timestamp': metric.timestamp.isoformat()
                    } for metric in self.resource_history[-100:]  # Save last 100
                ]
            }
            with open(self.metrics_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save metrics history: {e}")
    
    async def _initialize_service_tracking(self):
        """Initialize service health tracking"""
        # Define services to monitor
        services_to_monitor = [
            'communication', 'data_management', 'hardware',
            'sensor_fusion', 'weather', 'power_management',
            'safety', 'vision', 'web_api'
        ]
        
        for service_name in services_to_monitor:
            self.service_health[service_name] = ServiceHealth(
                name=service_name,
                is_healthy=False,
                status_message="Not checked",
                last_check=datetime.now(),
                response_time_ms=None,
                restart_count=0,
                error_count=0,
                cpu_percent=0.0,
                memory_mb=0.0
            )
            
            # Initialize circuit breaker
            self.circuit_breakers[service_name] = {
                'state': 'CLOSED',  # CLOSED, OPEN, HALF_OPEN
                'failure_count': 0,
                'last_failure': None,
                'timeout': 30.0  # seconds
            }
    
    async def run(self):
        """Main health monitoring loop"""
        self.running = True
        logger.info("Starting health monitoring")
        
        # Start monitoring tasks
        tasks = [
            asyncio.create_task(self._service_health_loop()),
            asyncio.create_task(self._resource_monitoring_loop()),
            asyncio.create_task(self._metrics_persistence_loop())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Error in health monitoring: {e}")
        finally:
            self.running = False
    
    async def _service_health_loop(self):
        """Monitor service health"""
        while self.running:
            try:
                for service_name in self.service_health.keys():
                    await self._check_service_health(service_name)
                await asyncio.sleep(self.service_check_interval)
            except Exception as e:
                logger.error(f"Error in service health loop: {e}")
                await asyncio.sleep(5.0)
    
    async def _check_service_health(self, service_name: str):
        """Check health of a specific service"""
        circuit_breaker = self.circuit_breakers[service_name]
        
        # Skip if circuit breaker is OPEN
        if circuit_breaker['state'] == 'OPEN':
            if time.time() - circuit_breaker['last_failure'] > circuit_breaker['timeout']:
                circuit_breaker['state'] = 'HALF_OPEN'
                logger.info(f"Circuit breaker for {service_name} moved to HALF_OPEN")
            else:
                return  # Skip check while circuit is open
        
        try:
            start_time = time.time()
            is_healthy = await self._perform_service_health_check(service_name)
            response_time = (time.time() - start_time) * 1000  # ms
            
            # Update service health
            service_health = self.service_health[service_name]
            service_health.is_healthy = is_healthy
            service_health.last_check = datetime.now()
            service_health.response_time_ms = response_time
            
            if is_healthy:
                service_health.status_message = "Healthy"
                # Reset circuit breaker on success
                if circuit_breaker['state'] != 'CLOSED':
                    circuit_breaker['state'] = 'CLOSED'
                    circuit_breaker['failure_count'] = 0
                    logger.info(f"Circuit breaker for {service_name} reset to CLOSED")
            else:
                service_health.status_message = "Unhealthy - service not responding"
                service_health.error_count += 1
                await self._handle_service_failure(service_name)
                
        except Exception as e:
            logger.error(f"Error checking health of {service_name}: {e}")
            service_health = self.service_health[service_name]
            service_health.is_healthy = False
            service_health.status_message = f"Health check failed: {e}"
            service_health.error_count += 1
            await self._handle_service_failure(service_name)
    
    async def _perform_service_health_check(self, service_name: str) -> bool:
        """Perform actual health check for a service"""
        try:
            # Check if systemd service is active
            proc = await asyncio.create_subprocess_exec(
                'systemctl', 'is-active', f'lawnberry-{service_name}.service',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await proc.communicate()
            is_active = stdout.decode().strip() == 'active'
            
            if is_active:
                # Get process metrics
                await self._update_service_metrics(service_name)
                return True
            else:
                return False
                
        except Exception as e:
            logger.debug(f"Service health check failed for {service_name}: {e}")
            return False
    
    async def _update_service_metrics(self, service_name: str):
        """Update CPU and memory metrics for a service"""
        try:
            # Get service PID
            proc = await asyncio.create_subprocess_exec(
                'systemctl', 'show', '--property=MainPID', f'lawnberry-{service_name}.service',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await proc.communicate()
            output = stdout.decode().strip()
            
            if output.startswith('MainPID='):
                pid_str = output.split('=')[1]
                if pid_str != '0':
                    pid = int(pid_str)
                    
                    # Get process metrics
                    process = psutil.Process(pid)
                    service_health = self.service_health[service_name]
                    service_health.cpu_percent = process.cpu_percent()
                    service_health.memory_mb = process.memory_info().rss / 1024 / 1024
                    
        except Exception as e:
            logger.debug(f"Could not update metrics for {service_name}: {e}")
    
    async def _handle_service_failure(self, service_name: str):
        """Handle service failure with circuit breaker logic"""
        circuit_breaker = self.circuit_breakers[service_name]
        circuit_breaker['failure_count'] += 1
        circuit_breaker['last_failure'] = time.time()
        
        # Open circuit breaker if too many failures
        if circuit_breaker['failure_count'] >= 3 and circuit_breaker['state'] == 'CLOSED':
            circuit_breaker['state'] = 'OPEN'
            logger.warning(f"Circuit breaker OPENED for {service_name} due to repeated failures")
    
    async def _resource_monitoring_loop(self):
        """Monitor system resource usage"""
        while self.running:
            try:
                resource_usage = await self._collect_resource_metrics()
                self.resource_history.append(resource_usage)
                
                # Keep only recent history
                if len(self.resource_history) > 1000:
                    self.resource_history = self.resource_history[-500:]
                
                # Check for alerts
                await self._check_resource_alerts(resource_usage)
                
                await asyncio.sleep(self.resource_check_interval)
                
            except Exception as e:
                logger.error(f"Error in resource monitoring loop: {e}")
                await asyncio.sleep(10.0)
    
    async def _collect_resource_metrics(self) -> ResourceUsage:
        """Collect current resource usage metrics"""
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        
        # Disk usage (root filesystem)
        disk = psutil.disk_usage('/')
        
        # Network statistics
        network = psutil.net_io_counters()
        
        # Temperature (if available)
        temperature = None
        try:
            if hasattr(psutil, 'sensors_temperatures'):
                temps = psutil.sensors_temperatures()
                if 'cpu_thermal' in temps:
                    temperature = temps['cpu_thermal'][0].current
        except Exception:
            pass
        
        return ResourceUsage(
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            disk_percent=(disk.used / disk.total) * 100,
            network_bytes_sent=network.bytes_sent,
            network_bytes_recv=network.bytes_recv,
            temperature_celsius=temperature,
            timestamp=datetime.now()
        )
    
    async def _check_resource_alerts(self, resource_usage: ResourceUsage):
        """Check for resource usage alerts"""
        alerts = []
        
        if resource_usage.cpu_percent > self.alert_thresholds['cpu_percent']:
            alerts.append(f"High CPU usage: {resource_usage.cpu_percent:.1f}%")
        
        if resource_usage.memory_percent > self.alert_thresholds['memory_percent']:
            alerts.append(f"High memory usage: {resource_usage.memory_percent:.1f}%")
        
        if resource_usage.disk_percent > self.alert_thresholds['disk_percent']:
            alerts.append(f"High disk usage: {resource_usage.disk_percent:.1f}%")
        
        if (resource_usage.temperature_celsius and 
            resource_usage.temperature_celsius > self.alert_thresholds['temperature_celsius']):
            alerts.append(f"High temperature: {resource_usage.temperature_celsius:.1f}°C")
        
        if alerts:
            for alert in alerts:
                logger.warning(f"RESOURCE ALERT: {alert}")
    
    async def _metrics_persistence_loop(self):
        """Periodically save metrics to file"""
        while self.running:
            try:
                await asyncio.sleep(300)  # Save every 5 minutes
                await self._save_metrics_history()
            except Exception as e:
                logger.error(f"Error saving metrics: {e}")
    
    async def get_system_health(self) -> SystemHealth:
        """Get comprehensive system health status"""
        # Determine overall health
        service_health_ok = all(
            health.is_healthy for health in self.service_health.values()
        )
        
        current_resources = self.resource_history[-1] if self.resource_history else None
        resource_health_ok = True
        
        if current_resources:
            resource_health_ok = (
                current_resources.cpu_percent < self.alert_thresholds['cpu_percent'] and
                current_resources.memory_percent < self.alert_thresholds['memory_percent'] and
                current_resources.disk_percent < self.alert_thresholds['disk_percent']
            )
        
        is_healthy = service_health_ok and resource_health_ok
        
        # Collect alerts and errors
        alerts = []
        errors = []
        
        for service_name, health in self.service_health.items():
            if not health.is_healthy:
                errors.append(f"Service {service_name}: {health.status_message}")
            
            if health.restart_count > self.alert_thresholds['service_restart_limit']:
                alerts.append(f"Service {service_name} has restarted {health.restart_count} times")
        
        uptime = time.time() - self.system_start_time
        
        return SystemHealth(
            is_healthy=is_healthy,
            service_health=self.service_health.copy(),
            resource_usage=current_resources or ResourceUsage(
                cpu_percent=0, memory_percent=0, disk_percent=0,
                network_bytes_sent=0, network_bytes_recv=0,
                temperature_celsius=None, timestamp=datetime.now()
            ),
            alerts=alerts,
            errors=errors,
            uptime_seconds=uptime,
            last_update=datetime.now()
        )
    
    async def is_service_healthy(self, service_name: str) -> bool:
        """Check if a specific service is healthy"""
        service_health = self.service_health.get(service_name)
        return service_health.is_healthy if service_health else False
    
    def get_service_health(self, service_name: str) -> Optional[ServiceHealth]:
        """Get health status of a specific service"""
        return self.service_health.get(service_name)
    
    def get_resource_history(self, hours: int = 1) -> List[ResourceUsage]:
        """Get resource usage history for the specified number of hours"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [
            usage for usage in self.resource_history
            if usage.timestamp >= cutoff_time
        ]
    
    def update_alert_thresholds(self, thresholds: Dict[str, float]):
        """Update alert thresholds"""
        self.alert_thresholds.update(thresholds)
        logger.info(f"Updated alert thresholds: {thresholds}")
    
    async def shutdown(self):
        """Shutdown health monitor"""
        logger.info("Shutting down health monitor")
        self.running = False
        
        # Save final metrics
        await self._save_metrics_history()
        
        logger.info("Health monitor shut down")
