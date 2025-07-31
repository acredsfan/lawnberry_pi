"""
Comprehensive System Reliability Service
Provides health monitoring, alerting, and automatic service recovery
"""

import asyncio
import logging
import psutil
import time
import json
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
import subprocess
import threading
from collections import deque, defaultdict
import aiofiles
import yaml


logger = logging.getLogger(__name__)


class ServiceState(Enum):
    """Service states"""
    RUNNING = "running"
    STOPPED = "stopped"
    STARTING = "starting"
    STOPPING = "stopping"
    FAILED = "failed"
    UNKNOWN = "unknown"


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"


@dataclass
class ServiceConfig:
    """Service configuration"""
    name: str
    executable: str
    working_directory: str
    environment: Dict[str, str] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    restart_policy: str = "always"  # always, on-failure, never
    max_restarts: int = 5
    restart_delay: int = 5
    health_check_interval: int = 30
    health_check_timeout: int = 10
    health_check_command: Optional[str] = None
    resource_limits: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceMetrics:
    """Service performance metrics"""
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_percent: float = 0.0
    disk_io_read: int = 0
    disk_io_write: int = 0
    network_bytes_sent: int = 0
    network_bytes_recv: int = 0
    uptime_seconds: float = 0.0
    restart_count: int = 0
    last_restart: Optional[datetime] = None
    response_time_ms: Optional[float] = None


@dataclass
class HealthCheckResult:
    """Health check result"""
    service_name: str
    timestamp: datetime
    status: HealthStatus
    response_time_ms: float
    details: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None


@dataclass
class SystemAlert:
    """System alert"""
    alert_id: str
    timestamp: datetime
    level: AlertLevel
    component: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    resolved: bool = False
    resolution_time: Optional[datetime] = None


@dataclass
class BackupConfig:
    """Backup configuration"""
    enabled: bool = True
    backup_directory: str = "/var/backups/lawnberry"
    retention_days: int = 30
    schedule: str = "0 2 * * *"  # Daily at 2 AM
    compress: bool = True
    include_logs: bool = True
    include_database: bool = True
    include_config: bool = True


class SystemReliabilityService:
    """Comprehensive system reliability and monitoring service"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "/etc/lawnberry/reliability.yaml"
        
        # Service management
        self.services: Dict[str, ServiceConfig] = {}
        self.service_processes: Dict[str, subprocess.Popen] = {}
        self.service_metrics: Dict[str, ServiceMetrics] = {}
        self.service_states: Dict[str, ServiceState] = {}
        
        # Health monitoring
        self.health_checks: Dict[str, HealthCheckResult] = {}
        self.health_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
        # Alerting
        self.alerts: Dict[str, SystemAlert] = {}
        self.alert_handlers: Dict[AlertLevel, List[Callable]] = defaultdict(list)
        self.notification_throttle: Dict[str, datetime] = {}
        
        # System monitoring
        self.system_metrics_history: deque = deque(maxlen=1000)
        self.performance_baseline: Dict[str, float] = {}
        
        # Backup system
        self.backup_config = BackupConfig()
        self.last_backup: Optional[datetime] = None
        
        # Configuration
        self.config = {
            "monitoring_interval": 10,
            "health_check_interval": 30,
            "metrics_retention_hours": 24,
            "auto_restart_enabled": True,
            "notification_cooldown": 300,  # 5 minutes
            "performance_threshold_cpu": 80.0,
            "performance_threshold_memory": 80.0,
            "performance_threshold_disk": 90.0
        }
        
        # State
        self.running = False
        self.monitoring_tasks: Set[asyncio.Task] = set()
        
        self.logger = logger
    
    async def initialize(self):
        """Initialize the reliability service"""
        self.logger.info("Initializing System Reliability Service")
        
        # Load configuration
        await self._load_configuration()
        
        # Load service configurations
        await self._load_service_configurations()
        
        # Initialize monitoring
        await self._initialize_monitoring()
        
        # Start background tasks
        self.running = True
        await self._start_monitoring_tasks()
        
        self.logger.info("System Reliability Service initialized")
    
    async def _load_configuration(self):
        """Load service configuration"""
        try:
            if Path(self.config_path).exists():
                async with aiofiles.open(self.config_path, 'r') as f:
                    content = await f.read()
                    config_data = yaml.safe_load(content)
                    self.config.update(config_data.get('reliability', {}))
                    
                    if 'backup' in config_data:
                        backup_data = config_data['backup']
                        self.backup_config = BackupConfig(**backup_data)
        except Exception as e:
            self.logger.warning(f"Failed to load configuration: {e}")
    
    async def _load_service_configurations(self):
        """Load service configurations"""
        try:
            service_config_dir = Path("/etc/lawnberry/services")
            if service_config_dir.exists():
                for config_file in service_config_dir.glob("*.yaml"):
                    async with aiofiles.open(config_file, 'r') as f:
                        content = await f.read()
                        service_data = yaml.safe_load(content)
                        
                        service_config = ServiceConfig(**service_data)
                        self.services[service_config.name] = service_config
                        self.service_states[service_config.name] = ServiceState.UNKNOWN
                        self.service_metrics[service_config.name] = ServiceMetrics()
        except Exception as e:
            self.logger.error(f"Failed to load service configurations: {e}")
    
    async def _initialize_monitoring(self):
        """Initialize monitoring systems"""
        # Initialize performance baseline
        await self._establish_performance_baseline()
        
        # Initialize health checks
        for service_name in self.services:
            await self._perform_health_check(service_name)
    
    async def _start_monitoring_tasks(self):
        """Start background monitoring tasks"""
        tasks = [
            asyncio.create_task(self._system_monitoring_loop()),
            asyncio.create_task(self._service_monitoring_loop()),
            asyncio.create_task(self._health_check_loop()),
            asyncio.create_task(self._alert_processing_loop()),
            asyncio.create_task(self._backup_scheduler_loop())
        ]
        
        self.monitoring_tasks.update(tasks)
    
    async def _system_monitoring_loop(self):
        """System-wide monitoring loop"""
        while self.running:
            try:
                await self._collect_system_metrics()
                await self._check_system_thresholds()
                await asyncio.sleep(self.config["monitoring_interval"])
            except Exception as e:
                self.logger.error(f"System monitoring loop error: {e}")
                await asyncio.sleep(5)
    
    async def _service_monitoring_loop(self):
        """Service monitoring loop"""
        while self.running:
            try:
                await self._monitor_all_services()
                await asyncio.sleep(self.config["monitoring_interval"])
            except Exception as e:
                self.logger.error(f"Service monitoring loop error: {e}")
                await asyncio.sleep(5)
    
    async def _health_check_loop(self):
        """Health check loop"""
        while self.running:
            try:
                await self._perform_all_health_checks()
                await asyncio.sleep(self.config["health_check_interval"])
            except Exception as e:
                self.logger.error(f"Health check loop error: {e}")
                await asyncio.sleep(10)
    
    async def _alert_processing_loop(self):
        """Alert processing loop"""
        while self.running:
            try:
                await self._process_pending_alerts()
                await self._cleanup_old_alerts()
                await asyncio.sleep(30)
            except Exception as e:
                self.logger.error(f"Alert processing loop error: {e}")
                await asyncio.sleep(10)
    
    async def _backup_scheduler_loop(self):
        """Backup scheduler loop"""
        while self.running:
            try:
                await self._check_backup_schedule()
                await asyncio.sleep(3600)  # Check every hour
            except Exception as e:
                self.logger.error(f"Backup scheduler loop error: {e}")
                await asyncio.sleep(1800)  # Retry in 30 minutes
    
    async def _collect_system_metrics(self):
        """Collect system-wide metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            load_avg = psutil.getloadavg() if hasattr(psutil, 'getloadavg') else (0, 0, 0)
            
            # Memory metrics
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            # Disk metrics
            disk_usage = psutil.disk_usage('/')
            disk_io = psutil.disk_io_counters()
            
            # Network metrics
            network_io = psutil.net_io_counters()
            
            # Temperature (if available)
            temperature = None
            try:
                if hasattr(psutil, 'sensors_temperatures'):
                    temps = psutil.sensors_temperatures()
                    if 'cpu_thermal' in temps:
                        temperature = temps['cpu_thermal'][0].current
            except Exception:
                pass
            
            metrics = {
                "timestamp": datetime.now(),
                "cpu": {
                    "percent": cpu_percent,
                    "count": cpu_count,
                    "load_avg": load_avg
                },
                "memory": {
                    "total_mb": memory.total / 1024 / 1024,
                    "used_mb": memory.used / 1024 / 1024,
                    "percent": memory.percent,
                    "available_mb": memory.available / 1024 / 1024
                },
                "swap": {
                    "total_mb": swap.total / 1024 / 1024,
                    "used_mb": swap.used / 1024 / 1024,
                    "percent": swap.percent
                },
                "disk": {
                    "total_gb": disk_usage.total / 1024 / 1024 / 1024,
                    "used_gb": disk_usage.used / 1024 / 1024 / 1024,
                    "free_gb": disk_usage.free / 1024 / 1024 / 1024,
                    "percent": (disk_usage.used / disk_usage.total) * 100,
                    "read_mb": disk_io.read_bytes / 1024 / 1024 if disk_io else 0,
                    "write_mb": disk_io.write_bytes / 1024 / 1024 if disk_io else 0
                },
                "network": {
                    "bytes_sent": network_io.bytes_sent if network_io else 0,
                    "bytes_recv": network_io.bytes_recv if network_io else 0,
                    "packets_sent": network_io.packets_sent if network_io else 0,
                    "packets_recv": network_io.packets_recv if network_io else 0
                },
                "temperature": temperature
            }
            
            self.system_metrics_history.append(metrics)
            
        except Exception as e:
            self.logger.error(f"Failed to collect system metrics: {e}")
    
    async def _check_system_thresholds(self):
        """Check system metrics against thresholds"""
        if not self.system_metrics_history:
            return
        
        current_metrics = self.system_metrics_history[-1]
        
        # CPU threshold check
        if current_metrics["cpu"]["percent"] > self.config["performance_threshold_cpu"]:
            await self._create_alert(
                AlertLevel.WARNING,
                "system",
                f"High CPU usage: {current_metrics['cpu']['percent']:.1f}%",
                {"cpu_percent": current_metrics["cpu"]["percent"]}
            )
        
        # Memory threshold check
        if current_metrics["memory"]["percent"] > self.config["performance_threshold_memory"]:
            await self._create_alert(
                AlertLevel.WARNING,
                "system",
                f"High memory usage: {current_metrics['memory']['percent']:.1f}%",
                {"memory_percent": current_metrics["memory"]["percent"]}
            )
        
        # Disk threshold check
        if current_metrics["disk"]["percent"] > self.config["performance_threshold_disk"]:
            await self._create_alert(
                AlertLevel.CRITICAL,
                "system",
                f"High disk usage: {current_metrics['disk']['percent']:.1f}%",
                {"disk_percent": current_metrics["disk"]["percent"]}
            )
        
        # Temperature check
        if current_metrics["temperature"] and current_metrics["temperature"] > 80.0:
            await self._create_alert(
                AlertLevel.CRITICAL,
                "system",
                f"High temperature: {current_metrics['temperature']:.1f}°C",
                {"temperature": current_metrics["temperature"]}
            )
    
    async def _monitor_all_services(self):
        """Monitor all configured services"""
        for service_name in self.services:
            await self._monitor_service(service_name)
    
    async def _monitor_service(self, service_name: str):
        """Monitor a specific service"""
        try:
            service_config = self.services[service_name]
            
            # Check if service process exists and is running
            is_running = await self._is_service_running(service_name)
            
            if is_running:
                self.service_states[service_name] = ServiceState.RUNNING
                
                # Collect service metrics
                await self._collect_service_metrics(service_name)
                
            else:
                if self.service_states[service_name] == ServiceState.RUNNING:
                    # Service just stopped
                    self.logger.warning(f"Service {service_name} stopped unexpectedly")
                    self.service_states[service_name] = ServiceState.STOPPED
                    
                    await self._create_alert(
                        AlertLevel.WARNING,
                        service_name,
                        f"Service {service_name} stopped unexpectedly"
                    )
                    
                    # Attempt restart if configured
                    if (self.config["auto_restart_enabled"] and 
                        service_config.restart_policy in ["always", "on-failure"]):
                        await self._restart_service(service_name)
        
        except Exception as e:
            self.logger.error(f"Failed to monitor service {service_name}: {e}")
    
    async def _is_service_running(self, service_name: str) -> bool:
        """Check if a service is running"""
        try:
            # Check systemd service status
            result = subprocess.run(
                ["systemctl", "is-active", f"lawnberry-{service_name}"],
                capture_output=True,
                text=True
            )
            return result.returncode == 0 and result.stdout.strip() == "active"
        except Exception:
            return False
    
    async def _collect_service_metrics(self, service_name: str):
        """Collect metrics for a specific service"""
        try:
            # Find service process
            service_pid = await self._get_service_pid(service_name)
            if not service_pid:
                return
            
            process = psutil.Process(service_pid)
            
            # Collect metrics
            metrics = self.service_metrics[service_name]
            metrics.cpu_percent = process.cpu_percent()
            
            memory_info = process.memory_info()
            metrics.memory_mb = memory_info.rss / 1024 / 1024
            metrics.memory_percent = process.memory_percent()
            
            io_counters = process.io_counters()
            metrics.disk_io_read = io_counters.read_bytes
            metrics.disk_io_write = io_counters.write_bytes
            
            # Calculate uptime
            create_time = process.create_time()
            metrics.uptime_seconds = time.time() - create_time
            
        except Exception as e:
            self.logger.error(f"Failed to collect metrics for service {service_name}: {e}")
    
    async def _get_service_pid(self, service_name: str) -> Optional[int]:
        """Get PID for a service"""
        try:
            result = subprocess.run(
                ["systemctl", "show", f"lawnberry-{service_name}", "--property=MainPID"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                pid_line = result.stdout.strip()
                if pid_line.startswith("MainPID="):
                    pid = int(pid_line.split("=")[1])
                    return pid if pid > 0 else None
        except Exception:
            pass
        return None
    
    async def _perform_all_health_checks(self):
        """Perform health checks on all services"""
        for service_name in self.services:
            await self._perform_health_check(service_name)
    
    async def _perform_health_check(self, service_name: str):
        """Perform health check on a specific service"""
        try:
            service_config = self.services[service_name]
            start_time = time.time()
            
            # Default health check - check if service is running
            is_running = await self._is_service_running(service_name)
            response_time = (time.time() - start_time) * 1000
            
            if is_running:
                status = HealthStatus.HEALTHY
                details = {"running": True}
                error_message = None
            else:
                status = HealthStatus.CRITICAL
                details = {"running": False}
                error_message = "Service not running"
            
            # Custom health check if configured
            if service_config.health_check_command:
                try:
                    result = subprocess.run(
                        service_config.health_check_command.split(),
                        capture_output=True,
                        text=True,
                        timeout=service_config.health_check_timeout
                    )
                    
                    if result.returncode == 0:
                        status = HealthStatus.HEALTHY
                        details.update({"custom_check": True, "output": result.stdout.strip()})
                        error_message = None
                    else:
                        status = HealthStatus.UNHEALTHY
                        details.update({"custom_check": False, "error": result.stderr.strip()})
                        error_message = f"Health check failed: {result.stderr.strip()}"
                        
                except subprocess.TimeoutExpired:
                    status = HealthStatus.UNHEALTHY
                    error_message = "Health check timed out"
                except Exception as e:
                    status = HealthStatus.UNHEALTHY
                    error_message = f"Health check error: {e}"
            
            # Create health check result
            health_result = HealthCheckResult(
                service_name=service_name,
                timestamp=datetime.now(),
                status=status,
                response_time_ms=response_time,
                details=details,
                error_message=error_message
            )
            
            self.health_checks[service_name] = health_result
            self.health_history[service_name].append(health_result)
            
            # Create alert if unhealthy
            if status in [HealthStatus.UNHEALTHY, HealthStatus.CRITICAL]:
                await self._create_alert(
                    AlertLevel.CRITICAL if status == HealthStatus.CRITICAL else AlertLevel.WARNING,
                    service_name,
                    f"Health check failed: {error_message}",
                    {"health_status": status.value, "response_time_ms": response_time}
                )
        
        except Exception as e:
            self.logger.error(f"Health check failed for service {service_name}: {e}")
    
    async def _restart_service(self, service_name: str) -> bool:
        """Restart a service"""
        try:
            service_config = self.services[service_name]
            metrics = self.service_metrics[service_name]
            
            # Check restart limits
            if metrics.restart_count >= service_config.max_restarts:
                self.logger.error(f"Service {service_name} exceeded restart limit")
                await self._create_alert(
                    AlertLevel.CRITICAL,
                    service_name,
                    f"Service {service_name} exceeded restart limit ({service_config.max_restarts})"
                )
                return False
            
            self.logger.info(f"Restarting service: {service_name}")
            self.service_states[service_name] = ServiceState.STARTING
            
            # Stop service
            stop_result = subprocess.run(
                ["systemctl", "stop", f"lawnberry-{service_name}"],
                capture_output=True,
                text=True
            )
            
            # Wait for restart delay
            await asyncio.sleep(service_config.restart_delay)
            
            # Start service
            start_result = subprocess.run(
                ["systemctl", "start", f"lawnberry-{service_name}"],
                capture_output=True,
                text=True
            )
            
            if start_result.returncode == 0:
                metrics.restart_count += 1
                metrics.last_restart = datetime.now()
                
                self.logger.info(f"Service {service_name} restarted successfully")
                await self._create_alert(
                    AlertLevel.INFO,
                    service_name,
                    f"Service {service_name} restarted successfully (attempt {metrics.restart_count})"
                )
                
                return True
            else:
                self.service_states[service_name] = ServiceState.FAILED
                self.logger.error(f"Failed to restart service {service_name}: {start_result.stderr}")
                await self._create_alert(
                    AlertLevel.CRITICAL,
                    service_name,
                    f"Failed to restart service {service_name}: {start_result.stderr}"
                )
                return False
        
        except Exception as e:
            self.logger.error(f"Exception during service restart {service_name}: {e}")
            self.service_states[service_name] = ServiceState.FAILED
            return False
    
    async def _create_alert(self, level: AlertLevel, component: str, message: str, details: Dict[str, Any] = None):
        """Create a system alert"""
        alert_id = f"{component}_{int(time.time())}"
        
        # Check notification throttling
        throttle_key = f"{component}_{message}"
        now = datetime.now()
        
        if throttle_key in self.notification_throttle:
            last_notification = self.notification_throttle[throttle_key]
            if (now - last_notification).total_seconds() < self.config["notification_cooldown"]:
                return  # Skip duplicate alert
        
        alert = SystemAlert(
            alert_id=alert_id,
            timestamp=now,
            level=level,
            component=component,
            message=message,
            details=details or {}
        )
        
        self.alerts[alert_id] = alert
        self.notification_throttle[throttle_key] = now
        
        # Log alert
        log_level = {
            AlertLevel.INFO: logging.INFO,
            AlertLevel.WARNING: logging.WARNING,
            AlertLevel.CRITICAL: logging.ERROR,
            AlertLevel.EMERGENCY: logging.CRITICAL
        }.get(level, logging.INFO)
        
        self.logger.log(log_level, f"ALERT [{level.value.upper()}] {component}: {message}")
        
        # Trigger alert handlers
        await self._trigger_alert_handlers(alert)
    
    async def _trigger_alert_handlers(self, alert: SystemAlert):
        """Trigger alert handlers"""
        handlers = self.alert_handlers.get(alert.level, [])
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(alert)
                else:
                    handler(alert)
            except Exception as e:
                self.logger.error(f"Alert handler failed: {e}")
    
    async def _process_pending_alerts(self):
        """Process pending alerts"""
        # Implementation for alert processing logic
        pass
    
    async def _cleanup_old_alerts(self):
        """Clean up old resolved alerts"""
        cutoff_time = datetime.now() - timedelta(days=7)
        
        old_alerts = [
            alert_id for alert_id, alert in self.alerts.items()
            if alert.resolved and alert.resolution_time and alert.resolution_time < cutoff_time
        ]
        
        for alert_id in old_alerts:
            del self.alerts[alert_id]
    
    async def _check_backup_schedule(self):
        """Check if backup should be performed"""
        if not self.backup_config.enabled:
            return
        
        now = datetime.now()
        
        # Simple daily backup check (would implement proper cron parsing)
        if self.last_backup is None or (now - self.last_backup).days >= 1:
            await self._perform_backup()
    
    async def _perform_backup(self):
        """Perform system backup"""
        try:
            self.logger.info("Starting system backup")
            
            backup_dir = Path(self.backup_config.backup_directory)
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = backup_dir / f"lawnberry_backup_{timestamp}"
            backup_path.mkdir()
            
            # Backup configuration files
            if self.backup_config.include_config:
                config_backup = backup_path / "config"
                config_backup.mkdir()
                
                # Copy configuration files
                import shutil
                for config_source in ["/etc/lawnberry", "/var/lib/lawnberry"]:
                    if Path(config_source).exists():
                        shutil.copytree(config_source, config_backup / Path(config_source).name, dirs_exist_ok=True)
            
            # Backup logs
            if self.backup_config.include_logs:
                log_backup = backup_path / "logs"
                log_backup.mkdir()
                
                # Copy log files
                log_source = Path("/var/log/lawnberry")
                if log_source.exists():
                    shutil.copytree(log_source, log_backup / "lawnberry", dirs_exist_ok=True)
            
            # Backup database
            if self.backup_config.include_database:
                db_backup = backup_path / "database"
                db_backup.mkdir()
                
                # Database backup would be implemented based on database type
                # For now, just create a placeholder
                (db_backup / "placeholder.txt").write_text("Database backup placeholder")
            
            # Compress if enabled
            if self.backup_config.compress:
                import tarfile
                archive_path = backup_dir / f"lawnberry_backup_{timestamp}.tar.gz"
                
                with tarfile.open(archive_path, "w:gz") as tar:
                    tar.add(backup_path, arcname=backup_path.name)
                
                # Remove uncompressed backup
                shutil.rmtree(backup_path)
                
                self.logger.info(f"Backup completed: {archive_path}")
            else:
                self.logger.info(f"Backup completed: {backup_path}")
            
            self.last_backup = datetime.now()
            
            # Clean up old backups
            await self._cleanup_old_backups()
            
        except Exception as e:
            self.logger.error(f"Backup failed: {e}")
            await self._create_alert(
                AlertLevel.WARNING,
                "backup",
                f"System backup failed: {e}"
            )
    
    async def _cleanup_old_backups(self):
        """Clean up old backup files"""
        try:
            backup_dir = Path(self.backup_config.backup_directory)
            if not backup_dir.exists():
                return
            
            cutoff_time = datetime.now() - timedelta(days=self.backup_config.retention_days)
            
            for backup_item in backup_dir.iterdir():
                if backup_item.is_file() and backup_item.name.startswith("lawnberry_backup_"):
                    if datetime.fromtimestamp(backup_item.stat().st_mtime) < cutoff_time:
                        backup_item.unlink()
                        self.logger.info(f"Deleted old backup: {backup_item}")
                elif backup_item.is_dir() and backup_item.name.startswith("lawnberry_backup_"):
                    if datetime.fromtimestamp(backup_item.stat().st_mtime) < cutoff_time:
                        shutil.rmtree(backup_item)
                        self.logger.info(f"Deleted old backup directory: {backup_item}")
        
        except Exception as e:
            self.logger.error(f"Failed to cleanup old backups: {e}")
    
    async def _establish_performance_baseline(self):
        """Establish performance baseline metrics"""
        try:
            # Collect several samples to establish baseline
            samples = []
            for _ in range(10):
                await self._collect_system_metrics()
                if self.system_metrics_history:
                    samples.append(self.system_metrics_history[-1])
                await asyncio.sleep(1)
            
            if samples:
                # Calculate baseline averages
                self.performance_baseline = {
                    "cpu_percent": sum(s["cpu"]["percent"] for s in samples) / len(samples),
                    "memory_percent": sum(s["memory"]["percent"] for s in samples) / len(samples),
                    "disk_percent": sum(s["disk"]["percent"] for s in samples) / len(samples)
                }
                
                self.logger.info(f"Performance baseline established: {self.performance_baseline}")
        
        except Exception as e:
            self.logger.error(f"Failed to establish performance baseline: {e}")
    
    # Public API methods
    
    def register_alert_handler(self, level: AlertLevel, handler: Callable):
        """Register an alert handler"""
        self.alert_handlers[level].append(handler)
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health status"""
        # Calculate overall health
        healthy_services = sum(1 for h in self.health_checks.values() if h.status == HealthStatus.HEALTHY)
        total_services = len(self.health_checks)
        health_percentage = (healthy_services / total_services * 100) if total_services > 0 else 100
        
        # Get current system metrics
        current_metrics = self.system_metrics_history[-1] if self.system_metrics_history else None
        
        # Count alerts by level
        alert_counts = {level.value: 0 for level in AlertLevel}
        for alert in self.alerts.values():
            if not alert.resolved:
                alert_counts[alert.level.value] += 1
        
        return {
            "overall_health": "healthy" if health_percentage >= 90 else "degraded" if health_percentage >= 70 else "unhealthy",
            "health_percentage": health_percentage,
            "services": {
                "total": total_services,
                "healthy": healthy_services,
                "unhealthy": total_services - healthy_services
            },
            "system_metrics": current_metrics,
            "alerts": alert_counts,
            "uptime_seconds": time.time() - (time.time() - 86400),  # Placeholder
            "last_backup": self.last_backup.isoformat() if self.last_backup else None
        }
    
    def get_service_status(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get status for a specific service"""
        if service_name not in self.services:
            return None
        
        health = self.health_checks.get(service_name)
        metrics = self.service_metrics.get(service_name)
        state = self.service_states.get(service_name)
        
        return {
            "name": service_name,
            "state": state.value if state else "unknown",
            "health": {
                "status": health.status.value if health else "unknown",
                "last_check": health.timestamp.isoformat() if health else None,
                "response_time_ms": health.response_time_ms if health else None,
                "error_message": health.error_message if health else None
            },
            "metrics": {
                "cpu_percent": metrics.cpu_percent if metrics else 0,
                "memory_mb": metrics.memory_mb if metrics else 0,
                "memory_percent": metrics.memory_percent if metrics else 0,
                "uptime_seconds": metrics.uptime_seconds if metrics else 0,
                "restart_count": metrics.restart_count if metrics else 0,
                "last_restart": metrics.last_restart.isoformat() if metrics and metrics.last_restart else None
            }
        }
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active alerts"""
        active_alerts = []
        
        for alert in self.alerts.values():
            if not alert.resolved:
                active_alerts.append({
                    "alert_id": alert.alert_id,
                    "timestamp": alert.timestamp.isoformat(),
                    "level": alert.level.value,
                    "component": alert.component,
                    "message": alert.message,
                    "details": alert.details,
                    "acknowledged": alert.acknowledged
                })
        
        # Sort by timestamp (newest first)
        active_alerts.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return active_alerts
    
    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert"""
        if alert_id in self.alerts:
            self.alerts[alert_id].acknowledged = True
            return True
        return False
    
    async def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert"""
        if alert_id in self.alerts:
            alert = self.alerts[alert_id]
            alert.resolved = True
            alert.resolution_time = datetime.now()
            return True
        return False
    
    async def manual_service_restart(self, service_name: str) -> bool:
        """Manually restart a service"""
        if service_name in self.services:
            return await self._restart_service(service_name)
        return False
    
    async def emergency_shutdown(self):
        """Perform emergency system shutdown"""
        self.logger.critical("Emergency shutdown initiated")
        
        await self._create_alert(
            AlertLevel.EMERGENCY,
            "system",
            "Emergency shutdown initiated"
        )
        
        # Stop all services gracefully
        for service_name in self.services:
            try:
                subprocess.run(
                    ["systemctl", "stop", f"lawnberry-{service_name}"],
                    timeout=30
                )
            except Exception as e:
                self.logger.error(f"Failed to stop service {service_name}: {e}")
        
        # Perform emergency backup
        try:
            await self._perform_backup()
        except Exception as e:
            self.logger.error(f"Emergency backup failed: {e}")
    
    async def safe_shutdown(self):
        """Perform safe system shutdown"""
        self.logger.info("Safe shutdown initiated")
        
        # Stop monitoring
        self.running = False
        
        # Cancel monitoring tasks
        for task in self.monitoring_tasks:
            if not task.done():
                task.cancel()
        
        # Stop services in reverse dependency order
        # This would be implemented based on service dependencies
        
        self.logger.info("Safe shutdown completed")
    
    async def shutdown(self):
        """Shutdown the reliability service"""
        await self.safe_shutdown()
