"""Structured logging and observability for LawnBerry Pi v2.

This module provides comprehensive logging, metrics collection, and observability
features for the robotic lawn mower system, including structured JSON logging,
performance metrics, system health monitoring, and log rotation.
"""
import json
import logging
import logging.handlers
import os
import sys
import threading
import time
import traceback
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any

import yaml

try:  # pragma: no cover - psutil may be unavailable during tests
    import psutil  # type: ignore
except Exception:  # pragma: no cover - fallback when psutil is missing
    psutil = None  # type: ignore

from .context import get_correlation_id
from .logging import apply_privacy_filter

DEFAULT_LOG_CONFIG_PATH = Path("/home/pi/lawnberry/config/logging.yaml")


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
    metrics_interval_seconds: int = 10
    metrics_error_backoff_seconds: int = 30
    retention_days: int = 7
    performance_warning_ms: int = 750
    event_history_limit: int = 500
    error_rate_alert_threshold: float = 5.0
    error_rate_alert_cooldown_seconds: int = 300
    extend_default_redactions: bool = True
    redact_fields: list[str] = field(default_factory=list)
    redact_patterns: list[str] = field(default_factory=list)


@dataclass
class ObservabilityEvent:
    """Captured observability event for diagnostics and health reporting."""

    timestamp: datetime
    event_type: str
    level: str
    message: str
    correlation_id: str | None
    origin: str
    remediation: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


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
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        correlation_id = getattr(record, "correlation_id", None)
        if correlation_id:
            log_entry["correlation_id"] = correlation_id

        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        ignored_fields = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "exc_info",
            "exc_text",
            "stack_info",
            "getMessage",
            "correlation_id",
        }

        for key, value in record.__dict__.items():
            if key not in ignored_fields:
                log_entry[f"extra_{key}"] = value

        return json.dumps(log_entry)


class CorrelationIdFilter(logging.Filter):
    """Injects the active correlation identifier onto log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()
        return True


class MetricsCollector:
    """Tracks runtime metrics with configurable retention."""

    def __init__(self, retention_minutes: int = 60) -> None:
        self.retention_minutes = max(1, retention_minutes)
        self._system_metrics: deque[SystemMetrics] = deque()
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._timers: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "total": 0.0, "min": None, "max": None}
        )
        self._lock = threading.Lock()

    def increment_counter(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] += value

    def record_metric(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = float(value)

    def record_timer(self, name: str, duration_ms: float) -> None:
        with self._lock:
            stats = self._timers[name]
            stats["count"] += 1
            stats["total"] += float(duration_ms)
            stats["min"] = (
                float(duration_ms)
                if stats["min"] is None
                else min(float(duration_ms), stats["min"])
            )
            stats["max"] = (
                float(duration_ms)
                if stats["max"] is None
                else max(float(duration_ms), stats["max"])
            )

    def collect_system_metrics(self) -> SystemMetrics:
        timestamp = time.time()
        cpu_usage = 0.0
        memory_usage_mb = 0.0
        disk_usage_percent = 0.0
        network_connections = 0

        try:
            use_psutil = bool(psutil) and Path("/proc/meminfo").exists()
            if use_psutil:
                cpu_usage = float(psutil.cpu_percent(interval=None))
                try:
                    memory_usage_mb = float(psutil.virtual_memory().used) / (1024 ** 2)
                except Exception:  # pragma: no cover - psutil fallback
                    memory_usage_mb = 0.0
                disk_usage_percent = float(psutil.disk_usage("/").percent)
                try:
                    network_connections = len(psutil.net_connections(kind="inet"))
                except Exception:  # pragma: no cover - may require permissions
                    network_connections = 0
            else:
                if hasattr(os, "getloadavg"):
                    load1, _, _ = os.getloadavg()
                    cpu_count = os.cpu_count() or 1
                    cpu_usage = min(100.0, (load1 / cpu_count) * 100)
                stat = os.statvfs("/home/pi/lawnberry")
                total = stat.f_blocks * stat.f_frsize
                free = stat.f_bavail * stat.f_frsize
                used = total - free
                disk_usage_percent = (used / total) * 100 if total else 0.0
        except Exception:  # pragma: no cover - metrics best effort
            pass

        metric = SystemMetrics(
            timestamp=timestamp,
            cpu_usage=cpu_usage,
            memory_usage_mb=memory_usage_mb,
            disk_usage_percent=disk_usage_percent,
            network_connections=network_connections,
            active_websocket_clients=int(self._gauges.get("websocket_clients", 0)),
            telemetry_broadcast_rate=float(self._gauges.get("telemetry_broadcast_rate", 0.0)),
            api_request_count=int(self._counters.get("api_requests", 0)),
            api_error_count=int(self._counters.get("api_errors", 0)),
            database_query_time_ms=self._timer_average("database_query_duration"),
        )

        with self._lock:
            self._system_metrics.append(metric)
            self._prune_system_metrics_locked(timestamp)

        return metric

    def _timer_average(self, name: str) -> float:
        stats = self._timers.get(name)
        if not stats or stats["count"] == 0:
            return 0.0
        return stats["total"] / stats["count"]

    def _prune_system_metrics_locked(self, now: float) -> None:
        cutoff = now - (self.retention_minutes * 60)
        while self._system_metrics and self._system_metrics[0].timestamp < cutoff:
            self._system_metrics.popleft()

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            system_snapshot = [asdict(metric) for metric in self._system_metrics]
            counters_snapshot = dict(self._counters)
            gauges_snapshot = dict(self._gauges)
            timers_snapshot: dict[str, dict[str, float]] = {}
            for name, stats in self._timers.items():
                count = stats["count"]
                avg = stats["total"] / count if count else 0.0
                timers_snapshot[name] = {
                    "count": count,
                    "avg": avg,
                    "min": stats["min"] if stats["min"] is not None else 0.0,
                    "max": stats["max"] if stats["max"] is not None else 0.0,
                }

        return {
            "system": system_snapshot,
            "counters": counters_snapshot,
            "gauges": gauges_snapshot,
            "timers": timers_snapshot,
        }

    def reset_for_testing(self) -> None:
        with self._lock:
            self._system_metrics.clear()
            self._counters.clear()
            self._gauges.clear()
            self._timers.clear()


class ObservabilityManager:
    """Central observability, logging, and metrics orchestration."""

    _ERROR_REMEDIATION_LINKS: dict[str, str] = {
        "database": "docs/OPERATIONS.md#database-health-checks",
        "http_request": "docs/OPERATIONS.md#api-troubleshooting",
        "sensor": "docs/hardware-integration.md#sensor-health",
        "camera": "docs/hardware-integration.md#camera",
        "metrics": "docs/OPERATIONS.md#metrics",
        "performance": "docs/OPERATIONS.md#performance-monitoring",
    }

    def __init__(self, config: LogConfig | None = None, config_path: Path | None = None) -> None:
        self._config_path = Path(config_path) if config_path else DEFAULT_LOG_CONFIG_PATH
        self.config = config or self._load_config()
        self.metrics = MetricsCollector(self.config.metrics_retention_minutes)
        self._event_history: deque[ObservabilityEvent] = deque(
            maxlen=self.config.event_history_limit
        )
        self._event_lock = threading.Lock()
        self._metrics_thread: threading.Thread | None = None
        self._correlation_filter = CorrelationIdFilter()
        self._logger = logging.getLogger(__name__)
        self._event_logger = logging.getLogger("observability.events")
        self._api_logger = logging.getLogger("api.requests")
        self._ws_logger = logging.getLogger("websocket.events")
        self._health_logger = logging.getLogger("system.health")
        self._last_error_alerts: dict[str, datetime] = {}
        self._setup_logging()
        if self.config.enable_metrics:
            self._start_metrics_collection()

    def _load_config(self) -> LogConfig:
        try:
            if self._config_path.exists():
                with self._config_path.open("r", encoding="utf-8") as handle:
                    data = yaml.safe_load(handle) or {}
                if not isinstance(data, dict):
                    raise ValueError("Logging configuration must be a mapping")
                allowed_keys = set(LogConfig.__dataclass_fields__.keys())
                filtered = {key: value for key, value in data.items() if key in allowed_keys}
                return LogConfig(**filtered)
        except Exception as exc:  # pragma: no cover - configuration best effort
            logging.getLogger(__name__).warning("Failed to load logging configuration: %s", exc)
        return LogConfig()

    def _get_formatter(self) -> logging.Formatter:
        if self.config.log_format.lower() == "structured":
            return StructuredFormatter()
        return logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    def _setup_logging(self) -> None:
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, self.config.log_level.upper(), logging.INFO))

        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

        if self.config.log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(self._get_formatter())
            console_handler.addFilter(self._correlation_filter)
            root_logger.addHandler(console_handler)

        if self.config.log_to_file:
            log_path = Path(self.config.log_file_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=self.config.max_file_size_mb * 1024 * 1024,
                backupCount=self.config.backup_count,
            )
            file_handler.setFormatter(self._get_formatter())
            file_handler.addFilter(self._correlation_filter)
            root_logger.addHandler(file_handler)
            self._enforce_log_retention(log_path)

        root_logger.addFilter(self._correlation_filter)
        apply_privacy_filter(
            root_logger,
            sensitive_keys=self.config.redact_fields,
            sensitive_patterns=self.config.redact_patterns,
            include_default_keys=self.config.extend_default_redactions,
            include_default_patterns=self.config.extend_default_redactions,
        )

    def _enforce_log_retention(self, log_path: Path) -> None:
        try:
            retention_days = max(1, int(self.config.retention_days))
        except Exception:
            retention_days = 1

        cutoff = datetime.now(UTC) - timedelta(days=retention_days)

        try:
            for candidate in log_path.parent.glob(f"{log_path.name}*"):
                if candidate == log_path:
                    continue
                try:
                    modified = datetime.fromtimestamp(candidate.stat().st_mtime, tz=UTC)
                except FileNotFoundError:
                    continue
                if modified < cutoff:
                    try:
                        candidate.unlink()
                    except FileNotFoundError:
                        continue
        except Exception as exc:  # pragma: no cover - retention best effort
            self._logger.debug("Log retention cleanup failed: %s", exc)

    def _start_metrics_collection(self) -> None:
        if self._metrics_thread and self._metrics_thread.is_alive():
            return

        def collect_metrics() -> None:
            while True:
                interval = max(1, int(self.config.metrics_interval_seconds))
                backoff = max(interval, int(self.config.metrics_error_backoff_seconds))

                if not self.config.enable_metrics:
                    time.sleep(interval)
                    continue

                try:
                    metrics = self.metrics.collect_system_metrics()
                    self.metrics.record_metric(
                        "system_cpu_usage",
                        metrics.cpu_usage,
                    )
                    self.metrics.record_metric(
                        "system_memory_usage_mb",
                        metrics.memory_usage_mb,
                    )
                    self.metrics.record_metric(
                        "system_disk_usage_percent",
                        metrics.disk_usage_percent,
                    )
                    window = max(interval * 6, 60)
                    self._update_error_metrics(window_seconds=window)
                    time.sleep(interval)
                except Exception as exc:  # pragma: no cover - metrics best effort
                    self.record_error(
                        origin="metrics",
                        message="Error collecting system metrics",
                        exception=exc,
                        severity="WARNING",
                    )
                    time.sleep(backoff)

        self._metrics_thread = threading.Thread(target=collect_metrics, daemon=True)
        self._metrics_thread.start()

    def configure(self, config: LogConfig) -> None:
        self.config = config
        self.metrics = MetricsCollector(self.config.metrics_retention_minutes)
        self._event_history = deque(maxlen=self.config.event_history_limit)
        self._setup_logging()
        if self.config.enable_metrics:
            self._start_metrics_collection()

    def reload_config(self) -> None:
        self.configure(self._load_config())

    def get_logger(self, name: str) -> logging.Logger:
        return logging.getLogger(name)

    def log_api_request(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        self.metrics.increment_counter("api_requests")
        self.metrics.record_timer("api_request_duration", duration_ms)
        if status_code >= 400:
            self.metrics.increment_counter("api_errors")

        self._api_logger.info(
            "API request",
            extra={
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
        )

    def log_websocket_event(
        self,
        event_type: str,
        client_count: int,
        topic: str | None = None,
    ) -> None:
        self.metrics.record_metric("websocket_clients", client_count)
        self._ws_logger.info(
            "WebSocket event",
            extra={"event_type": event_type, "client_count": client_count, "topic": topic},
        )

    def log_system_health(
        self,
        component: str,
        status: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = {"component": component, "status": status, "details": details or {}}
        self._health_logger.info("System health check", extra=payload)
        self.record_event(
            event_type="health",
            level="INFO",
            message=f"{component} status: {status}",
            origin=component,
            metadata=payload["details"],
        )

    def create_performance_decorator(self, operation_name: str):
        def decorator(func: Callable):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    duration_ms = (time.perf_counter() - start) * 1000
                    self.metrics.record_timer(f"{operation_name}_duration", duration_ms)
                    self._logger.debug(
                        "Performance measurement",
                        extra={
                            "operation": operation_name,
                            "duration_ms": duration_ms,
                            "status": "success",
                        },
                    )
                    if duration_ms >= self.config.performance_warning_ms:
                        self.record_performance_issue(
                            origin=operation_name,
                            message=f"{operation_name} exceeded threshold",
                            duration_ms=duration_ms,
                            metadata={"operation": operation_name},
                        )
                    return result
                except Exception as exc:
                    duration_ms = (time.perf_counter() - start) * 1000
                    self.metrics.increment_counter(f"{operation_name}_errors")
                    self.record_error(
                        origin=operation_name,
                        message=f"{operation_name} failed",
                        exception=exc,
                        metadata={"operation": operation_name, "duration_ms": duration_ms},
                    )
                    raise

            return wrapper

        return decorator

    def record_event(
        self,
        *,
        event_type: str,
        level: str,
        message: str,
        origin: str,
        remediation: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ObservabilityEvent:
        remediation_link = remediation or self._ERROR_REMEDIATION_LINKS.get(origin)
        event = ObservabilityEvent(
            timestamp=datetime.now(UTC),
            event_type=event_type,
            level=level.upper(),
            message=message,
            correlation_id=get_correlation_id(),
            origin=origin,
            remediation=remediation_link,
            metadata=metadata or {},
        )

        with self._event_lock:
            self._event_history.append(event)

        if event.event_type == "error":
            self.metrics.increment_counter("backend_error_events")
            if event.level.upper() == "CRITICAL":
                self.metrics.increment_counter("backend_error_events_critical")
        if event.event_type == "performance":
            self.metrics.increment_counter("backend_performance_degradations")

        level_value = getattr(logging, event.level.upper(), logging.INFO)
        self._event_logger.log(
            level_value,
            event.message,
            extra={
                "event_type": event.event_type,
                "origin": event.origin,
                "remediation": event.remediation,
                "metadata": event.metadata,
            },
        )

        return event

    def record_error(
        self,
        *,
        origin: str,
        message: str,
        exception: BaseException | None = None,
        severity: str = "ERROR",
        metadata: dict[str, Any] | None = None,
        remediation: str | None = None,
    ) -> ObservabilityEvent:
        meta = dict(metadata or {})
        if exception is not None:
            meta.setdefault("exception_type", type(exception).__name__)
            meta.setdefault("exception_message", str(exception))
            meta.setdefault(
                "stacktrace",
                traceback.format_exception(type(exception), exception, exception.__traceback__),
            )

        return self.record_event(
            event_type="error",
            level=severity,
            message=message,
            origin=origin,
            remediation=remediation,
            metadata=meta,
        )

    def record_performance_issue(
        self,
        *,
        origin: str,
        message: str,
        duration_ms: float,
        metadata: dict[str, Any] | None = None,
    ) -> ObservabilityEvent:
        meta = dict(metadata or {})
        meta.setdefault("duration_ms", duration_ms)
        return self.record_event(
            event_type="performance",
            level="WARNING",
            message=message,
            origin=origin,
            metadata=meta,
        )

    def get_recent_events(
        self,
        *,
        event_type: str | None = None,
        within_seconds: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        with self._event_lock:
            events = list(self._event_history)

        if event_type:
            events = [evt for evt in events if evt.event_type == event_type]

        if within_seconds is not None:
            cutoff = datetime.now(UTC) - timedelta(seconds=max(0, within_seconds))
            events = [evt for evt in events if evt.timestamp >= cutoff]

        if limit is not None and limit >= 0:
            events = events[-limit:]

        return [self._event_to_dict(evt) for evt in events]

    def get_recent_errors(
        self,
        within_seconds: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.get_recent_events(
            event_type="error",
            within_seconds=within_seconds,
            limit=limit,
        )

    def get_recent_performance_issues(
        self,
        within_seconds: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.get_recent_events(
            event_type="performance",
            within_seconds=within_seconds,
            limit=limit,
        )

    def calculate_error_rates(
        self,
        window_seconds: int = 300,
    ) -> tuple[dict[str, float], dict[str, int]]:
        window_seconds = max(1, int(window_seconds))
        cutoff = datetime.now(UTC) - timedelta(seconds=window_seconds)

        with self._event_lock:
            error_events = [
                evt
                for evt in self._event_history
                if evt.event_type == "error" and evt.timestamp >= cutoff
            ]

        counts: dict[str, int] = defaultdict(int)
        for evt in error_events:
            origin = evt.origin or "unknown"
            counts[origin] += 1

        minutes = max(window_seconds / 60.0, 1.0 / 60.0)
        rates: dict[str, float] = {origin: count / minutes for origin, count in counts.items()}
        return rates, counts

    def _update_error_metrics(self, *, window_seconds: int) -> dict[str, Any]:
        rates, counts = self.calculate_error_rates(window_seconds)
        total_errors = float(sum(counts.values()))
        total_rate = float(sum(rates.values()))

        self.metrics.record_metric("error_events_last_window", total_errors)
        self.metrics.record_metric("error_rate_per_minute_total", total_rate)

        for origin, rate in rates.items():
            self.metrics.record_metric(f"error_rate_per_minute_{origin}", float(rate))
        for origin, count in counts.items():
            self.metrics.record_metric(f"errors_last_window_{origin}", float(count))

        self._evaluate_error_alerts(rates, counts, window_seconds)
        return {"window_seconds": window_seconds, "rates": rates, "counts": counts}

    def _evaluate_error_alerts(
        self,
        rates: dict[str, float],
        counts: dict[str, int],
        window_seconds: int,
    ) -> None:
        threshold = float(self.config.error_rate_alert_threshold)
        if threshold <= 0:
            return

        cooldown = max(30, int(self.config.error_rate_alert_cooldown_seconds or 0))
        now = datetime.now(UTC)

        for origin, rate in rates.items():
            if rate < threshold:
                continue

            last_alert = self._last_error_alerts.get(origin)
            if last_alert and (now - last_alert).total_seconds() < cooldown:
                continue

            self._last_error_alerts[origin] = now
            metadata = {
                "rate_per_minute": rate,
                "errors_last_window": counts.get(origin, 0),
                "window_seconds": window_seconds,
            }
            self.record_event(
                event_type="alert",
                level="WARNING",
                message=f"High error rate detected for {origin}",
                origin=origin,
                metadata=metadata,
            )

    def update_error_metrics_for_testing(self, window_seconds: int = 300) -> dict[str, Any]:
        return self._update_error_metrics(window_seconds=window_seconds)

    def get_metrics_snapshot(self) -> dict[str, Any]:
        return self.metrics.get_snapshot()

    def reset_events_for_testing(self) -> None:
        with self._event_lock:
            self._event_history.clear()
        self.metrics.reset_for_testing()
        self._last_error_alerts.clear()

    def _event_to_dict(self, event: ObservabilityEvent) -> dict[str, Any]:
        payload = asdict(event)
        payload["timestamp"] = event.timestamp.isoformat()
        return payload


observability = ObservabilityManager()
logger = observability.get_logger(__name__)
monitor_performance = observability.create_performance_decorator