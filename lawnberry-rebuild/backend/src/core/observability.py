"""Structured logging and observability for LawnBerry Pi v2.

This module provides comprehensive logging, metrics collection, and observability
features for the robotic lawn mower system, including structured JSON logging,
performance metrics, system health monitoring, and log rotation.
"""
import json
import logging
import logging.handlers
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass, asdict
from functools import wraps
import traceback
import sys
import os
from .logging import apply_privacy_filter

# System metrics
from collections import defaultdict, deque


@dataclass
class LogConfig:
    """Logging configuration."""
    log_level: str = "INFO"
    log_format: str = "structured"  # "structured" or "plain"
    log_to_file: bool = True
    log_to_console: bool = True
    log_file_path: str = "/home/pi/lawnberry/logs/lawnberry.log"
    max_file_size_mb: int = 10
    backup_count: int = 5
    enable_metrics: bool = True
    metrics_retention_minutes: int = 60


@dataclass
class SystemMetrics:
    """System performance metrics."""
    timestamp: float
    cpu_usage: float = 0.0
    memory_usage_mb: float = 0.0
    disk_usage_percent: float = 0.0
    network_connections: int = 0
    active_websocket_clients: int = 0
    telemetry_broadcast_rate: float = 0.0
    api_request_count: int = 0
    api_error_count: int = 0
    database_query_time_ms: float = 0.0


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        # Base log entry
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 
                          'filename', 'module', 'lineno', 'funcName', 'created', 'msecs',
                          'relativeCreated', 'thread', 'threadName', 'processName', 
                          'process', 'exc_info', 'exc_text', 'stack_info', 'getMessage']:
                log_entry[f"extra_{key}"] = value
        
        return json.dumps(log_entry)


class MetricsCollector:
    """System metrics collection and monitoring."""
    
    def __init__(self, retention_minutes: int = 60):
        self.retention_minutes = retention_minutes
        self._metrics_history: deque = deque(maxlen=retention_minutes * 60)  # 1 per second
        self._counters: Dict[str, int] = defaultdict(int)
        self._timers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self._lock = threading.Lock()
    
    def record_metric(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """Record a metric value."""
        with self._lock:
            metric_entry = {
                "timestamp": time.time(),
                "name": name,
                "value": value,
                "tags": tags or {}
            }
            self._metrics_history.append(metric_entry)
    
    def increment_counter(self, name: str, value: int = 1):
        """Increment a counter metric."""
        with self._lock:
            self._counters[name] += value
    
    def record_timer(self, name: str, duration_ms: float):
        """Record a timer metric."""
        with self._lock:
            self._timers[name].append(duration_ms)
    
    def get_counter(self, name: str) -> int:
        """Get counter value."""
        with self._lock:
            return self._counters.get(name, 0)
    
    def get_timer_stats(self, name: str) -> Dict[str, float]:
        """Get timer statistics."""
        with self._lock:
            timings = list(self._timers.get(name, []))
            if not timings:
                return {"count": 0, "avg": 0.0, "min": 0.0, "max": 0.0}
            
            return {
                "count": len(timings),
                "avg": sum(timings) / len(timings),
                "min": min(timings),
                "max": max(timings)
            }
    
    def collect_system_metrics(self) -> SystemMetrics:
        """Collect current system metrics."""
        metrics = SystemMetrics(timestamp=time.time())
        
        try:
            # CPU usage (basic approximation)
            load_avg = os.getloadavg()[0] if hasattr(os, 'getloadavg') else 0.0
            metrics.cpu_usage = min(load_avg * 100, 100.0)
            
            # Memory usage
            if Path("/proc/meminfo").exists():
                with open("/proc/meminfo", "r") as f:
                    meminfo = f.read()
                    for line in meminfo.split("\n"):
                        if line.startswith("MemTotal:"):
                            total_kb = int(line.split()[1])
                        elif line.startswith("MemAvailable:"):
                            available_kb = int(line.split()[1])
                    
                    used_kb = total_kb - available_kb
                    metrics.memory_usage_mb = used_kb / 1024
            
            # Disk usage
            if Path("/home/pi/lawnberry").exists():
                stat = os.statvfs("/home/pi/lawnberry")
                total = stat.f_blocks * stat.f_frsize
                free = stat.f_available * stat.f_frsize
                used = total - free
                metrics.disk_usage_percent = (used / total) * 100 if total > 0 else 0
            
            # Application metrics from counters
            metrics.api_request_count = self.get_counter("api_requests")
            metrics.api_error_count = self.get_counter("api_errors")
            
            # Database query performance
            db_stats = self.get_timer_stats("database_query")
            metrics.database_query_time_ms = db_stats.get("avg", 0.0)
            
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
        
        return metrics
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get summary of all metrics."""
        with self._lock:
            return {
                "system": asdict(self.collect_system_metrics()),
                "counters": dict(self._counters),
                "timers": {name: self.get_timer_stats(name) for name in self._timers.keys()},
                "metrics_count": len(self._metrics_history)
            }


class ObservabilityManager:
    """Central observability and logging management."""
    
    def __init__(self, config: LogConfig = None):
        self.config = config or LogConfig()
        self.metrics = MetricsCollector(self.config.metrics_retention_minutes)
        self._setup_logging()
        
        # Start metrics collection if enabled
        if self.config.enable_metrics:
            self._start_metrics_collection()
    
    def _setup_logging(self):
        """Configure logging infrastructure."""
        # Create log directory
        log_path = Path(self.config.log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Root logger configuration
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, self.config.log_level.upper()))
        
        # Clear existing handlers
        root_logger.handlers.clear()
        
        # Console handler
        if self.config.log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            if self.config.log_format == "structured":
                console_handler.setFormatter(StructuredFormatter())
            else:
                console_handler.setFormatter(logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                ))
            root_logger.addHandler(console_handler)
        
        # File handler with rotation
        if self.config.log_to_file:
            file_handler = logging.handlers.RotatingFileHandler(
                self.config.log_file_path,
                maxBytes=self.config.max_file_size_mb * 1024 * 1024,
                backupCount=self.config.backup_count
            )
            
            if self.config.log_format == "structured":
                file_handler.setFormatter(StructuredFormatter())
            else:
                file_handler.setFormatter(logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                ))
            root_logger.addHandler(file_handler)

        # Apply privacy redaction filter
        apply_privacy_filter(root_logger)
    
    def _start_metrics_collection(self):
        """Start background metrics collection."""
        def collect_metrics():
            while True:
                try:
                    metrics = self.metrics.collect_system_metrics()
                    self.metrics.record_metric("system_cpu_usage", metrics.cpu_usage)
                    self.metrics.record_metric("system_memory_usage", metrics.memory_usage_mb)
                    self.metrics.record_metric("system_disk_usage", metrics.disk_usage_percent)
                    time.sleep(10)  # Collect every 10 seconds
                except Exception as e:
                    logger.error(f"Error in metrics collection: {e}")
                    time.sleep(30)  # Back off on error
        
        metrics_thread = threading.Thread(target=collect_metrics, daemon=True)
        metrics_thread.start()
    
    def get_logger(self, name: str) -> logging.Logger:
        """Get a logger instance."""
        return logging.getLogger(name)
    
    def log_api_request(self, method: str, path: str, status_code: int, duration_ms: float):
        """Log API request with metrics."""
        self.metrics.increment_counter("api_requests")
        self.metrics.record_timer("api_request_duration", duration_ms)
        
        if status_code >= 400:
            self.metrics.increment_counter("api_errors")
        
        logger.info("API request", extra={
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": duration_ms
        })
    
    def log_websocket_event(self, event_type: str, client_count: int, topic: str = None):
        """Log WebSocket events with metrics."""
        self.metrics.record_metric("websocket_clients", client_count)
        
        logger.info("WebSocket event", extra={
            "event_type": event_type,
            "client_count": client_count,
            "topic": topic
        })
    
    def log_system_health(self, component: str, status: str, details: Dict[str, Any] = None):
        """Log system health status."""
        logger.info("System health check", extra={
            "component": component,
            "status": status,
            "details": details or {}
        })
    
    def create_performance_decorator(self, operation_name: str):
        """Create a decorator for performance monitoring."""
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration_ms = (time.time() - start_time) * 1000
                    self.metrics.record_timer(f"{operation_name}_duration", duration_ms)
                    
                    logger.debug(f"Performance: {operation_name}", extra={
                        "operation": operation_name,
                        "duration_ms": duration_ms,
                        "status": "success"
                    })
                    
                    return result
                except Exception as e:
                    duration_ms = (time.time() - start_time) * 1000
                    self.metrics.increment_counter(f"{operation_name}_errors")
                    
                    logger.error(f"Performance: {operation_name} failed", extra={
                        "operation": operation_name,
                        "duration_ms": duration_ms,
                        "status": "error",
                        "error": str(e)
                    })
                    raise
            
            return wrapper
        return decorator


# Global observability manager
observability = ObservabilityManager()

# Get logger for this module
logger = observability.get_logger(__name__)

# Performance decorators
monitor_performance = observability.create_performance_decorator