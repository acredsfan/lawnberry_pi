"""
System Monitor - Comprehensive monitoring for deployment automation
Provides health checks, performance metrics, and alerting for deployment system
"""

import asyncio
import logging
import json
import psutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import aiofiles

from .config_manager import ConfigManager


logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check status"""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class HealthCheck:
    """Health check definition"""
    name: str
    description: str
    check_function: Callable
    interval: int  # seconds
    timeout: int   # seconds
    critical: bool
    enabled: bool


@dataclass
class HealthResult:
    """Health check result"""
    name: str
    status: HealthStatus
    message: str
    timestamp: datetime
    duration: float
    metadata: Dict[str, Any]


@dataclass
class SystemMetrics:
    """System performance metrics"""
    timestamp: datetime
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    network_io: Dict[str, int]
    process_count: int
    load_average: List[float]
    temperature: Optional[float]
    uptime: float


@dataclass
class Alert:
    """System alert"""
    id: str
    level: AlertLevel
    source: str
    message: str
    timestamp: datetime
    acknowledged: bool
    resolved: bool
    metadata: Dict[str, Any]


class SystemMonitor:
    """
    Comprehensive system monitoring for deployment automation
    """
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.config = self._load_monitor_config()
        
        # Health checks
        self.health_checks: Dict[str, HealthCheck] = {}
        self.health_results: Dict[str, HealthResult] = {}
        
        # Metrics collection
        self.metrics_history: List[SystemMetrics] = []
        self.max_metrics_history = self.config.get('max_metrics_history', 1440)  # 24 hours at 1min intervals
        
        # Alerting
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_handlers: List[Callable] = []
        
        # Performance thresholds
        self.cpu_warning_threshold = self.config.get('cpu_warning_threshold', 80.0)
        self.cpu_critical_threshold = self.config.get('cpu_critical_threshold', 95.0)
        self.memory_warning_threshold = self.config.get('memory_warning_threshold', 80.0)
        self.memory_critical_threshold = self.config.get('memory_critical_threshold', 95.0)
        self.disk_warning_threshold = self.config.get('disk_warning_threshold', 85.0)
        self.disk_critical_threshold = self.config.get('disk_critical_threshold', 95.0)
        
        # Background tasks
        self._health_check_tasks: Dict[str, asyncio.Task] = {}
        self._metrics_collector_task: Optional[asyncio.Task] = None
        self._alert_processor_task: Optional[asyncio.Task] = None
        
        # State persistence
        self.state_file = Path("/var/lib/lawnberry/monitor_state.json")
        
    def _load_monitor_config(self) -> Dict[str, Any]:
        """Load monitoring configuration"""
        try:
            config = self.config_manager.get_config('monitoring')
            return config if config else self._default_monitor_config()
        except Exception as e:
            logger.warning(f"Failed to load monitor config, using defaults: {e}")
            return self._default_monitor_config()
    
    def _default_monitor_config(self) -> Dict[str, Any]:
        """Default monitoring configuration"""
        return {
            'enabled': True,
            'metrics_interval': 60,  # 1 minute
            'max_metrics_history': 1440,  # 24 hours
            'cpu_warning_threshold': 80.0,
            'cpu_critical_threshold': 95.0,
            'memory_warning_threshold': 80.0,
            'memory_critical_threshold': 95.0,
            'disk_warning_threshold': 85.0,
            'disk_critical_threshold': 95.0,
            'temperature_warning_threshold': 70.0,
            'temperature_critical_threshold': 80.0,
            'health_checks': {
                'system_resources': {
                    'enabled': True,
                    'interval': 60,
                    'timeout': 10,
                    'critical': True
                },
                'disk_space': {
                    'enabled': True,
                    'interval': 300,  # 5 minutes
                    'timeout': 10,
                    'critical': True
                },
                'network_connectivity': {
                    'enabled': True,
                    'interval': 300,
                    'timeout': 30,
                    'critical': False
                },
                'service_health': {
                    'enabled': True,
                    'interval': 120,  # 2 minutes
                    'timeout': 15,
                    'critical': True
                },
                'deployment_system': {
                    'enabled': True,
                    'interval': 300,
                    'timeout': 20,
                    'critical': True
                }
            },
            'alerting': {
                'enabled': True,
                'email_notifications': False,
                'webhook_notifications': False,
                'alert_cooldown': 300  # 5 minutes
            }
        }
    
    async def initialize(self):
        """Initialize system monitor"""
        try:
            logger.info("Initializing System Monitor")
            
            # Load previous state
            await self._load_state()
            
            # Register health checks
            await self._register_health_checks()
            
            # Start background tasks
            if self.config.get('enabled', True):
                self._metrics_collector_task = asyncio.create_task(self._metrics_collection_loop())
                self._alert_processor_task = asyncio.create_task(self._alert_processing_loop())
                
                # Start health check tasks
                for name, health_check in self.health_checks.items():
                    if health_check.enabled:
                        task = asyncio.create_task(self._health_check_loop(name))
                        self._health_check_tasks[name] = task
            
            logger.info("System Monitor initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize System Monitor: {e}")
            raise
    
    async def shutdown(self):
        """Shutdown system monitor"""
        logger.info("Shutting down System Monitor")
        
        # Save current state
        await self._save_state()
        
        # Cancel all tasks
        all_tasks = list(self._health_check_tasks.values())
        if self._metrics_collector_task:
            all_tasks.append(self._metrics_collector_task)
        if self._alert_processor_task:
            all_tasks.append(self._alert_processor_task)
        
        for task in all_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    async def _load_state(self):
        """Load monitor state from disk"""
        try:
            if self.state_file.exists():
                async with aiofiles.open(self.state_file, 'r') as f:
                    data = json.loads(await f.read())
                
                # Load metrics history
                for metric_data in data.get('metrics_history', []):
                    metric_data['timestamp'] = datetime.fromisoformat(metric_data['timestamp'])
                    metrics = SystemMetrics(**metric_data)
                    self.metrics_history.append(metrics)
                
                # Load active alerts
                for alert_data in data.get('active_alerts', []):
                    alert_data['level'] = AlertLevel(alert_data['level'])
                    alert_data['timestamp'] = datetime.fromisoformat(alert_data['timestamp'])
                    alert = Alert(**alert_data)
                    self.active_alerts[alert.id] = alert
                    
        except Exception as e:
            logger.warning(f"Failed to load monitor state: {e}")
    
    async def _save_state(self):
        """Save monitor state to disk"""
        try:
            state_data = {
                'metrics_history': [],
                'active_alerts': [],
                'last_updated': datetime.now().isoformat()
            }
            
            # Save recent metrics history
            recent_metrics = self.metrics_history[-100:]  # Last 100 entries
            for metrics in recent_metrics:
                metric_data = asdict(metrics)
                metric_data['timestamp'] = metric_data['timestamp'].isoformat()
                state_data['metrics_history'].append(metric_data)
            
            # Save active alerts
            for alert in self.active_alerts.values():
                alert_data = asdict(alert)
                # Normalize enum and datetime fields
                alert_data['level'] = alert_data['level'].value
                alert_data['timestamp'] = alert_data['timestamp'].isoformat()
                # Ensure metadata is JSON-serializable (convert any datetimes)
                metadata = alert_data.get('metadata')
                if isinstance(metadata, dict):
                    for k, v in list(metadata.items()):
                        if isinstance(v, datetime):
                            metadata[k] = v.isoformat()
                state_data['active_alerts'].append(alert_data)
            
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(self.state_file, 'w') as f:
                await f.write(json.dumps(state_data, indent=2))
                
        except Exception as e:
            logger.error(f"Failed to save monitor state: {e}")
    
    async def _register_health_checks(self):
        """Register all health checks"""
        try:
            health_check_configs = self.config.get('health_checks', {})
            
            # System resources check
            if health_check_configs.get('system_resources', {}).get('enabled', True):
                config = health_check_configs['system_resources']
                self.health_checks['system_resources'] = HealthCheck(
                    name='system_resources',
                    description='System CPU, memory, and disk usage',
                    check_function=self._check_system_resources,
                    interval=config.get('interval', 60),
                    timeout=config.get('timeout', 10),
                    critical=config.get('critical', True),
                    enabled=True
                )
            
            # Disk space check
            if health_check_configs.get('disk_space', {}).get('enabled', True):
                config = health_check_configs['disk_space']
                self.health_checks['disk_space'] = HealthCheck(
                    name='disk_space',
                    description='Available disk space',
                    check_function=self._check_disk_space,
                    interval=config.get('interval', 300),
                    timeout=config.get('timeout', 10),
                    critical=config.get('critical', True),
                    enabled=True
                )
            
            # Network connectivity check
            if health_check_configs.get('network_connectivity', {}).get('enabled', True):
                config = health_check_configs['network_connectivity']
                self.health_checks['network_connectivity'] = HealthCheck(
                    name='network_connectivity',
                    description='Network connectivity and DNS resolution',
                    check_function=self._check_network_connectivity,
                    interval=config.get('interval', 300),
                    timeout=config.get('timeout', 30),
                    critical=config.get('critical', False),
                    enabled=True
                )
            
            # Service health check
            if health_check_configs.get('service_health', {}).get('enabled', True):
                config = health_check_configs['service_health']
                self.health_checks['service_health'] = HealthCheck(
                    name='service_health',
                    description='System service status',
                    check_function=self._check_service_health,
                    interval=config.get('interval', 120),
                    timeout=config.get('timeout', 15),
                    critical=config.get('critical', True),
                    enabled=True
                )
            
            # Deployment system check
            if health_check_configs.get('deployment_system', {}).get('enabled', True):
                config = health_check_configs['deployment_system']
                self.health_checks['deployment_system'] = HealthCheck(
                    name='deployment_system',
                    description='Deployment system health',
                    check_function=self._check_deployment_system,
                    interval=config.get('interval', 300),
                    timeout=config.get('timeout', 20),
                    critical=config.get('critical', True),
                    enabled=True
                )
                
        except Exception as e:
            logger.error(f"Failed to register health checks: {e}")
    
    async def _health_check_loop(self, check_name: str):
        """Background loop for individual health check"""
        while True:
            try:
                health_check = self.health_checks.get(check_name)
                if not health_check or not health_check.enabled:
                    break
                
                # Run health check
                result = await self._run_health_check(health_check)
                self.health_results[check_name] = result
                
                # Process result for alerting
                await self._process_health_result(result)
                
                # Wait for next check
                await asyncio.sleep(health_check.interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error for {check_name}: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    async def _run_health_check(self, health_check: HealthCheck) -> HealthResult:
        """Run a single health check"""
        start_time = time.time()
        
        try:
            # Run check with timeout
            result = await asyncio.wait_for(
                health_check.check_function(),
                timeout=health_check.timeout
            )
            
            duration = time.time() - start_time
            
            return HealthResult(
                name=health_check.name,
                status=result.get('status', HealthStatus.UNKNOWN),
                message=result.get('message', 'No message'),
                timestamp=datetime.now(),
                duration=duration,
                metadata=result.get('metadata', {})
            )
            
        except asyncio.TimeoutError:
            duration = time.time() - start_time
            return HealthResult(
                name=health_check.name,
                status=HealthStatus.CRITICAL,
                message=f"Health check timed out after {health_check.timeout}s",
                timestamp=datetime.now(),
                duration=duration,
                metadata={}
            )
        except Exception as e:
            duration = time.time() - start_time
            return HealthResult(
                name=health_check.name,
                status=HealthStatus.CRITICAL,
                message=f"Health check failed: {str(e)}",
                timestamp=datetime.now(),
                duration=duration,
                metadata={'error': str(e)}
            )
    
    async def _check_system_resources(self) -> Dict[str, Any]:
        """Check system resource usage"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Determine status based on thresholds
            status = HealthStatus.HEALTHY
            messages = []
            
            if cpu_percent >= self.cpu_critical_threshold:
                status = HealthStatus.CRITICAL
                messages.append(f"CPU usage critical: {cpu_percent:.1f}%")
            elif cpu_percent >= self.cpu_warning_threshold:
                status = HealthStatus.WARNING
                messages.append(f"CPU usage high: {cpu_percent:.1f}%")
            
            if memory.percent >= self.memory_critical_threshold:
                status = HealthStatus.CRITICAL
                messages.append(f"Memory usage critical: {memory.percent:.1f}%")
            elif memory.percent >= self.memory_warning_threshold:
                if status == HealthStatus.HEALTHY:
                    status = HealthStatus.WARNING
                messages.append(f"Memory usage high: {memory.percent:.1f}%")
            
            if disk.percent >= self.disk_critical_threshold:
                status = HealthStatus.CRITICAL
                messages.append(f"Disk usage critical: {disk.percent:.1f}%")
            elif disk.percent >= self.disk_warning_threshold:
                if status == HealthStatus.HEALTHY:
                    status = HealthStatus.WARNING
                messages.append(f"Disk usage high: {disk.percent:.1f}%")
            
            message = "; ".join(messages) if messages else "System resources normal"
            
            return {
                'status': status,
                'message': message,
                'metadata': {
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'disk_percent': disk.percent,
                    'memory_available': memory.available,
                    'disk_free': disk.free
                }
            }
            
        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL,
                'message': f"Failed to check system resources: {str(e)}",
                'metadata': {'error': str(e)}
            }
    
    async def _check_disk_space(self) -> Dict[str, Any]:
        """Check available disk space"""
        try:
            critical_paths = [
                '/',
                '/var/lib/lawnberry',
                '/opt/lawnberry',
                '/tmp'
            ]
            
            status = HealthStatus.HEALTHY
            messages = []
            disk_info = {}
            
            for path in critical_paths:
                try:
                    if Path(path).exists():
                        disk = psutil.disk_usage(path)
                        disk_info[path] = {
                            'total': disk.total,
                            'used': disk.used,
                            'free': disk.free,
                            'percent': disk.percent
                        }
                        
                        if disk.percent >= self.disk_critical_threshold:
                            status = HealthStatus.CRITICAL
                            messages.append(f"{path}: {disk.percent:.1f}% full")
                        elif disk.percent >= self.disk_warning_threshold:
                            if status == HealthStatus.HEALTHY:
                                status = HealthStatus.WARNING
                            messages.append(f"{path}: {disk.percent:.1f}% full")
                            
                except Exception as e:
                    logger.warning(f"Failed to check disk space for {path}: {e}")
            
            message = "; ".join(messages) if messages else "Disk space normal"
            
            return {
                'status': status,
                'message': message,
                'metadata': {'disk_info': disk_info}
            }
            
        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL,
                'message': f"Failed to check disk space: {str(e)}",
                'metadata': {'error': str(e)}
            }
    
    async def _check_network_connectivity(self) -> Dict[str, Any]:
        """Check network connectivity"""
        try:
            import socket
            
            # Test DNS resolution
            try:
                socket.gethostbyname('google.com')
                dns_ok = True
            except Exception:
                dns_ok = False
            
            # Test internet connectivity
            try:
                sock = socket.create_connection(('8.8.8.8', 53), timeout=10)
                sock.close()
                internet_ok = True
            except Exception:
                internet_ok = False
            
            if not dns_ok and not internet_ok:
                status = HealthStatus.CRITICAL
                message = "No network connectivity"
            elif not dns_ok:
                status = HealthStatus.WARNING
                message = "DNS resolution failed"
            elif not internet_ok:
                status = HealthStatus.WARNING  
                message = "Internet connectivity issues"
            else:
                status = HealthStatus.HEALTHY
                message = "Network connectivity normal"
            
            return {
                'status': status,
                'message': message,
                'metadata': {
                    'dns_resolution': dns_ok,
                    'internet_connectivity': internet_ok
                }
            }
            
        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL,
                'message': f"Failed to check network connectivity: {str(e)}",
                'metadata': {'error': str(e)}
            }
    
    async def _check_service_health(self) -> Dict[str, Any]:
        """Check system service health"""
        try:
            services = [
                'lawnberry-system',
                'lawnberry-hardware',
                'lawnberry-communication',
                'lawnberry-data',
                'lawnberry-sensor-fusion',
                'lawnberry-weather'
            ]
            
            service_status = {}
            failed_services = []
            
            for service in services:
                try:
                    # Check service status using systemctl
                    process = await asyncio.create_subprocess_exec(
                        'systemctl', 'is-active', service,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                    
                    is_active = stdout.decode().strip() == 'active'
                    service_status[service] = is_active
                    
                    if not is_active:
                        failed_services.append(service)
                        
                except Exception as e:
                    service_status[service] = False
                    failed_services.append(service)
                    logger.warning(f"Failed to check service {service}: {e}")
            
            if failed_services:
                status = HealthStatus.CRITICAL
                message = f"Services failed: {', '.join(failed_services)}"
            else:
                status = HealthStatus.HEALTHY
                message = "All services running normally"
            
            return {
                'status': status,
                'message': message,
                'metadata': {
                    'service_status': service_status,
                    'failed_services': failed_services
                }
            }
            
        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL,
                'message': f"Failed to check service health: {str(e)}",
                'metadata': {'error': str(e)}
            }
    
    async def _check_deployment_system(self) -> Dict[str, Any]:
        """Check deployment system health"""
        try:
            deployment_paths = [
                # Deployments and keys live under /var/lib (writable); accept /opt keys as fallback
                Path("/var/lib/lawnberry/deployments"),
                Path("/var/lib/lawnberry/backups"),
                Path("/var/lib/lawnberry/keys")
            ]
            
            issues = []
            path_status = {}
            
            for path in deployment_paths:
                path_status[str(path)] = {
                    'exists': path.exists(),
                    'writable': False,
                    'space_available': 0
                }
                
                if not path.exists():
                    issues.append(f"Missing directory: {path}")
                    continue
                
                # Check write permissions
                try:
                    test_file = path / ".write_test"
                    test_file.write_text("test")
                    test_file.unlink()
                    path_status[str(path)]['writable'] = True
                except Exception:
                    issues.append(f"Not writable: {path}")
                
                # Check available space
                try:
                    if path.exists():
                        disk = psutil.disk_usage(str(path))
                        path_status[str(path)]['space_available'] = disk.free
                        
                        # Check if less than 1GB available
                        if disk.free < 1024**3:  # 1GB
                            issues.append(f"Low disk space for {path}")
                except Exception:
                    pass
            
            # Check deployment keys
            # Prefer keys under /var/lib; accept /opt as fallback for read-only provisioned keys
            private_key_candidates = [
                Path("/var/lib/lawnberry/keys/deployment_private.pem"),
                Path("/opt/lawnberry/keys/deployment_private.pem"),
            ]
            public_key_candidates = [
                Path("/var/lib/lawnberry/keys/deployment_public.pem"),
                Path("/opt/lawnberry/keys/deployment_public.pem"),
            ]
            private_key = next((p for p in private_key_candidates if p.exists()), private_key_candidates[0])
            public_key = next((p for p in public_key_candidates if p.exists()), public_key_candidates[0])
            
            keys_status = {
                'private_key_exists': private_key.exists(),
                'public_key_exists': public_key.exists()
            }
            
            if not private_key.exists() or not public_key.exists():
                issues.append("Deployment keys missing")
            
            if issues:
                status = HealthStatus.WARNING if len(issues) <= 2 else HealthStatus.CRITICAL
                message = f"Deployment issues: {'; '.join(issues)}"
            else:
                status = HealthStatus.HEALTHY
                message = "Deployment system healthy"
            
            return {
                'status': status,
                'message': message,
                'metadata': {
                    'path_status': path_status,
                    'keys_status': keys_status,
                    'issues': issues
                }
            }
            
        except Exception as e:
            return {
                'status': HealthStatus.CRITICAL,
                'message': f"Failed to check deployment system: {str(e)}",
                'metadata': {'error': str(e)}
            }
    
    async def _process_health_result(self, result: HealthResult):
        """Process health check result for alerting"""
        try:
            # Create alert if status is warning or critical
            if result.status in [HealthStatus.WARNING, HealthStatus.CRITICAL]:
                alert_id = f"health_{result.name}_{int(result.timestamp.timestamp())}"
                
                # Check if similar alert already exists
                existing_alert = None
                for alert in self.active_alerts.values():
                    if (alert.source == f"health_check_{result.name}" and 
                        not alert.resolved and
                        (datetime.now() - alert.timestamp).seconds < 300):  # 5 minute cooldown
                        existing_alert = alert
                        break
                
                if not existing_alert:
                    alert_level = AlertLevel.CRITICAL if result.status == HealthStatus.CRITICAL else AlertLevel.WARNING
                    
                    alert = Alert(
                        id=alert_id,
                        level=alert_level,
                        source=f"health_check_{result.name}",
                        message=f"Health check '{result.name}': {result.message}",
                        timestamp=result.timestamp,
                        acknowledged=False,
                        resolved=False,
                        metadata=result.metadata
                    )
                    
                    self.active_alerts[alert_id] = alert
                    await self._send_alert(alert)
                    
        except Exception as e:
            logger.error(f"Failed to process health result: {e}")
    
    async def _metrics_collection_loop(self):
        """Background loop for metrics collection"""
        while True:
            try:
                metrics = await self._collect_system_metrics()
                self.metrics_history.append(metrics)
                
                # Trim history to max size
                if len(self.metrics_history) > self.max_metrics_history:
                    self.metrics_history = self.metrics_history[-self.max_metrics_history:]
                
                # Process metrics for alerting
                await self._process_metrics_alerts(metrics)
                
                await asyncio.sleep(self.config.get('metrics_interval', 60))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metrics collection error: {e}")
                await asyncio.sleep(60)
    
    async def _collect_system_metrics(self) -> SystemMetrics:
        """Collect current system metrics"""
        try:
            # Get network I/O stats
            net_io = psutil.net_io_counters()
            network_io = {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv
            }
            
            # Get temperature (if available)
            temperature = None
            try:
                temps = psutil.sensors_temperatures()
                if 'cpu_thermal' in temps:
                    temperature = temps['cpu_thermal'][0].current
            except Exception:
                pass
            
            return SystemMetrics(
                timestamp=datetime.now(),
                cpu_usage=psutil.cpu_percent(interval=1),
                memory_usage=psutil.virtual_memory().percent,
                disk_usage=psutil.disk_usage('/').percent,
                network_io=network_io,
                process_count=len(psutil.pids()),
                load_average=list(psutil.getloadavg()),
                temperature=temperature,
                uptime=time.time() - psutil.boot_time()
            )
            
        except Exception as e:
            logger.error(f"Failed to collect metrics: {e}")
            return SystemMetrics(
                timestamp=datetime.now(),
                cpu_usage=0.0,
                memory_usage=0.0,
                disk_usage=0.0,
                network_io={},
                process_count=0,
                load_average=[0.0, 0.0, 0.0],
                temperature=None,
                uptime=0.0
            )
    
    async def _process_metrics_alerts(self, metrics: SystemMetrics):
        """Process metrics for alerting"""
        try:
            alerts_to_create = []
            
            # CPU usage alerts
            if metrics.cpu_usage >= self.cpu_critical_threshold:
                alerts_to_create.append({
                    'level': AlertLevel.CRITICAL,
                    'source': 'metrics_cpu',
                    'message': f'Critical CPU usage: {metrics.cpu_usage:.1f}%'
                })
            elif metrics.cpu_usage >= self.cpu_warning_threshold:
                alerts_to_create.append({
                    'level': AlertLevel.WARNING,
                    'source': 'metrics_cpu',
                    'message': f'High CPU usage: {metrics.cpu_usage:.1f}%'
                })
            
            # Memory usage alerts
            if metrics.memory_usage >= self.memory_critical_threshold:
                alerts_to_create.append({
                    'level': AlertLevel.CRITICAL,
                    'source': 'metrics_memory',
                    'message': f'Critical memory usage: {metrics.memory_usage:.1f}%'
                })
            elif metrics.memory_usage >= self.memory_warning_threshold:
                alerts_to_create.append({
                    'level': AlertLevel.WARNING,
                    'source': 'metrics_memory',
                    'message': f'High memory usage: {metrics.memory_usage:.1f}%'
                })
            
            # Temperature alerts
            if metrics.temperature:
                temp_critical = self.config.get('temperature_critical_threshold', 80.0)
                temp_warning = self.config.get('temperature_warning_threshold', 70.0)
                
                if metrics.temperature >= temp_critical:
                    alerts_to_create.append({
                        'level': AlertLevel.CRITICAL,
                        'source': 'metrics_temperature',
                        'message': f'Critical temperature: {metrics.temperature:.1f}°C'
                    })
                elif metrics.temperature >= temp_warning:
                    alerts_to_create.append({
                        'level': AlertLevel.WARNING,
                        'source': 'metrics_temperature',
                        'message': f'High temperature: {metrics.temperature:.1f}°C'
                    })
            
            # Create alerts with cooldown
            for alert_info in alerts_to_create:
                await self._create_metrics_alert(alert_info, metrics)
                
        except Exception as e:
            logger.error(f"Failed to process metrics alerts: {e}")
    
    async def _create_metrics_alert(self, alert_info: Dict[str, Any], metrics: SystemMetrics):
        """Create alert with cooldown check"""
        try:
            # Check cooldown
            cooldown = self.config.get('alerting', {}).get('alert_cooldown', 300)
            
            existing_alert = None
            for alert in self.active_alerts.values():
                if (alert.source == alert_info['source'] and 
                    not alert.resolved and
                    (datetime.now() - alert.timestamp).seconds < cooldown):
                    existing_alert = alert
                    break
            
            if not existing_alert:
                alert_id = f"metrics_{alert_info['source']}_{int(metrics.timestamp.timestamp())}"
                
                alert = Alert(
                    id=alert_id,
                    level=alert_info['level'],
                    source=alert_info['source'],
                    message=alert_info['message'],
                    timestamp=metrics.timestamp,
                    acknowledged=False,
                    resolved=False,
                    metadata=asdict(metrics)
                )
                
                self.active_alerts[alert_id] = alert
                await self._send_alert(alert)
                
        except Exception as e:
            logger.error(f"Failed to create metrics alert: {e}")
    
    async def _alert_processing_loop(self):
        """Background loop for alert processing"""
        while True:
            try:
                # Auto-resolve old alerts
                await self._auto_resolve_alerts()
                
                # Save state periodically
                await self._save_state()
                
                await asyncio.sleep(60)  # Run every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Alert processing error: {e}")
                await asyncio.sleep(60)
    
    async def _auto_resolve_alerts(self):
        """Auto-resolve old alerts"""
        try:
            auto_resolve_age = timedelta(hours=24)  # Auto-resolve after 24 hours
            
            for alert_id, alert in list(self.active_alerts.items()):
                if (not alert.resolved and 
                    datetime.now() - alert.timestamp > auto_resolve_age):
                    alert.resolved = True
                    logger.info(f"Auto-resolved alert: {alert_id}")
                    
        except Exception as e:
            logger.error(f"Auto-resolve alerts failed: {e}")
    
    async def _send_alert(self, alert: Alert):
        """Send alert through configured channels"""
        try:
            logger.warning(f"ALERT [{alert.level.value.upper()}] {alert.source}: {alert.message}")
            
            # Send to registered alert handlers
            for handler in self.alert_handlers:
                try:
                    await handler(alert)
                except Exception as e:
                    logger.error(f"Alert handler failed: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    def register_alert_handler(self, handler: Callable[[Alert], None]):
        """Register alert handler"""
        self.alert_handlers.append(handler)
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        try:
            # Get latest metrics
            latest_metrics = self.metrics_history[-1] if self.metrics_history else None
            
            # Get health check summary
            health_summary = {}
            overall_health = HealthStatus.HEALTHY
            
            for name, result in self.health_results.items():
                health_summary[name] = {
                    'status': result.status.value,
                    'message': result.message,
                    'last_check': result.timestamp.isoformat(),
                    'duration': result.duration
                }
                
                if result.status == HealthStatus.CRITICAL:
                    overall_health = HealthStatus.CRITICAL
                elif result.status == HealthStatus.WARNING and overall_health == HealthStatus.HEALTHY:
                    overall_health = HealthStatus.WARNING
            
            # Get active alerts summary
            alert_summary = {
                'total': len(self.active_alerts),
                'critical': len([a for a in self.active_alerts.values() if a.level == AlertLevel.CRITICAL and not a.resolved]),
                'warning': len([a for a in self.active_alerts.values() if a.level == AlertLevel.WARNING and not a.resolved]),
                'unacknowledged': len([a for a in self.active_alerts.values() if not a.acknowledged and not a.resolved])
            }
            
            return {
                'overall_health': overall_health.value,
                'health_checks': health_summary,
                'latest_metrics': asdict(latest_metrics) if latest_metrics else None,
                'alerts': alert_summary,
                'uptime': time.time() - psutil.boot_time(),
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get system status: {e}")
            return {}
    
    async def get_metrics_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get metrics history"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            filtered_metrics = [
                asdict(metrics) for metrics in self.metrics_history
                if metrics.timestamp >= cutoff_time
            ]
            
            # Convert timestamps to ISO format
            for metrics in filtered_metrics:
                metrics['timestamp'] = metrics['timestamp'].isoformat()
            
            return filtered_metrics
            
        except Exception as e:
            logger.error(f"Failed to get metrics history: {e}")
            return []
    
    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert"""
        try:
            alert = self.active_alerts.get(alert_id)
            if alert:
                alert.acknowledged = True
                await self._save_state()
                logger.info(f"Alert acknowledged: {alert_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to acknowledge alert: {e}")
            return False
    
    async def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert"""
        try:
            alert = self.active_alerts.get(alert_id)
            if alert:
                alert.resolved = True
                await self._save_state()
                logger.info(f"Alert resolved: {alert_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to resolve alert: {e}")
            return False
