"""Health evaluation helpers for LawnBerry Pi backend."""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from .observability import observability
from .tls_status import get_tls_status

logger = logging.getLogger(__name__)


class HealthLevel(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


_STATUS_ORDER: dict[HealthLevel, int] = {
    HealthLevel.HEALTHY: 0,
    HealthLevel.UNKNOWN: 1,
    HealthLevel.DEGRADED: 2,
    HealthLevel.CRITICAL: 3,
}


def _merge_status(current: HealthLevel, incoming: HealthLevel) -> HealthLevel:
    if _STATUS_ORDER[incoming] > _STATUS_ORDER[current]:
        return incoming
    return current


def _coerce_level(value: Any) -> HealthLevel:
    normalized = str(value).lower()
    for candidate in HealthLevel:
        if candidate.value == normalized:
            return candidate
    return HealthLevel.UNKNOWN


class HealthService:
    """Aggregate health checker across subsystems, hardware, and dependencies."""

    def __init__(
        self,
        *,
        hardware_config_path: Path = Path("./config/hardware.yaml"),
        system_config_path: Path = Path("./config/default.json"),
        remote_access_status_path: Path = Path("./data/remote_access_status.json"),
        database_path: Path = Path("./data/lawnberry.db"),
        error_window_seconds: int = 300,
        degrade_error_rate_threshold: float = 0.5,
        critical_error_rate_threshold: float = 2.0,
        sensor_probe_timeout: float = 2.0,
        sensor_health_provider: Callable[[], dict[str, Any]] | None = None,
        dependency_provider: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.hardware_config_path = hardware_config_path
        self.system_config_path = system_config_path
        self.remote_access_status_path = remote_access_status_path
        self.database_path = database_path
        self.error_window_seconds = max(30, error_window_seconds)
        self.degrade_error_rate_threshold = max(0.0, degrade_error_rate_threshold)
        self.critical_error_rate_threshold = max(
            self.degrade_error_rate_threshold, critical_error_rate_threshold
        )
        self.sensor_probe_timeout = max(0.5, float(sensor_probe_timeout))
        self._sensor_health_provider = sensor_health_provider
        self._dependency_provider = dependency_provider

    def evaluate(self) -> dict[str, Any]:
        now = datetime.now(UTC)

        observability.update_error_metrics_for_testing(
            window_seconds=self.error_window_seconds
        )

        rates, counts = observability.calculate_error_rates(self.error_window_seconds)
        recent_errors = observability.get_recent_errors(
            within_seconds=self.error_window_seconds
        )
        alerts = observability.get_recent_events(
            event_type="alert", within_seconds=self.error_window_seconds, limit=5
        )
        metrics_snapshot = observability.get_metrics_snapshot()

        system_config = self._load_system_config()
        hardware = self._evaluate_hardware()
        sensor_health = self._evaluate_sensor_health()
        subsystems = self._evaluate_subsystems(
            system_config, rates, counts, recent_errors, sensor_health
        )
        metrics = self._build_metrics_section(metrics_snapshot)
        dependencies = self._evaluate_dependencies(metrics_snapshot)

        overall = HealthLevel.HEALTHY
        overall = _merge_status(overall, _coerce_level(hardware.get("status")))
        overall = _merge_status(overall, _coerce_level(sensor_health.get("status")))
        for subsystem in subsystems.values():
            overall = _merge_status(overall, _coerce_level(subsystem.get("status")))
        for dependency in dependencies.values():
            overall = _merge_status(overall, _coerce_level(dependency.get("status")))

        error_rates = {
            origin: {
                "rate_per_minute": round(rate, 3),
                "errors_last_window": counts.get(origin, 0),
            }
            for origin, rate in rates.items()
        }

        return {
            "timestamp": now.isoformat(),
            "overall_status": overall.value,
            "hardware": hardware,
            "sensor_health": sensor_health,
            "subsystems": subsystems,
            "dependencies": dependencies,
            "metrics": metrics,
            "alerts": alerts,
            "error_rates": error_rates,
        }

    def _evaluate_sensor_health(self) -> dict[str, Any]:
        if self._sensor_health_provider:
            try:
                payload = self._sensor_health_provider()
            except Exception as exc:
                logger.debug("Custom sensor health provider failed: %s", exc, exc_info=exc)
            else:
                if isinstance(payload, dict):
                    return self._normalize_sensor_health(payload)
        return self._default_sensor_health()

    def _normalize_sensor_health(self, payload: dict[str, Any]) -> dict[str, Any]:
        components = payload.get("components")
        if not isinstance(components, dict):
            components = {}
        last_checked = payload.get("last_checked")
        if not isinstance(last_checked, str):
            last_checked = datetime.now(UTC).isoformat()
        return {
            "status": _coerce_level(payload.get("status", HealthLevel.UNKNOWN.value)).value,
            "detail": str(payload.get("detail", "")),
            "components": components,
            "initialized": payload.get("initialized"),
            "last_checked": last_checked,
        }

    def _default_sensor_health(self) -> dict[str, Any]:
        try:
            return asyncio.run(self._async_sensor_health_probe())
        except RuntimeError:
            logger.debug("Event loop running; skipping sensor health probe")
            return self._sensor_health_payload(
                HealthLevel.UNKNOWN,
                "Sensor health probe skipped (event loop active)",
                {},
            )
        except Exception as exc:
            logger.debug("Sensor health probe failed: %s", exc)
            return self._sensor_health_payload(
                HealthLevel.UNKNOWN,
                f"Sensor health unavailable: {exc}",
                {},
            )

    def _sensor_health_payload(
        self,
        status: HealthLevel,
        detail: str,
        components: dict[str, Any],
        *,
        initialized: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": status.value,
            "detail": detail,
            "components": components,
            "last_checked": datetime.now(UTC).isoformat(),
        }
        if initialized is not None:
            payload["initialized"] = initialized
        return payload

    async def _async_sensor_health_probe(self) -> dict[str, Any]:
        manager: Any | None = None
        created_manager = False

        existing_manager: Any | None = None
        try:
            from ..api import rest as api_rest  # type: ignore
        except Exception:
            api_rest = None  # type: ignore
        else:
            existing_manager = getattr(
                getattr(api_rest, "websocket_hub", None), "_sensor_manager", None
            )

        if existing_manager is not None:
            manager = existing_manager
        else:
            try:
                from ..services.sensor_manager import SensorManager  # type: ignore
            except Exception as exc:
                return self._sensor_health_payload(
                    HealthLevel.UNKNOWN,
                    f"Sensor manager unavailable: {exc}",
                    {},
                )
            manager = SensorManager()
            created_manager = True

        try:
            if not getattr(manager, "initialized", False):
                ready = await asyncio.wait_for(
                    manager.initialize(),
                    timeout=self.sensor_probe_timeout,
                )
                if not ready:
                    return self._sensor_health_payload(
                        HealthLevel.DEGRADED,
                        "Sensor manager failed to initialize",
                        {},
                        initialized=False,
                    )
            status = await asyncio.wait_for(
                manager.get_sensor_status(),
                timeout=self.sensor_probe_timeout,
            )
        except TimeoutError:
            return self._sensor_health_payload(
                HealthLevel.DEGRADED,
                "Sensor manager timed out collecting status",
                {},
                initialized=getattr(manager, "initialized", False),
            )
        except Exception as exc:
            return self._sensor_health_payload(
                HealthLevel.DEGRADED,
                f"Sensor status unavailable: {exc}",
                {},
                initialized=getattr(manager, "initialized", False),
            )
        finally:
            if created_manager:
                with suppress(Exception):
                    await asyncio.wait_for(manager.shutdown(), timeout=1.0)

        if not isinstance(status, dict):
            return self._sensor_health_payload(
                HealthLevel.UNKNOWN,
                "Sensor status payload not available",
                {},
                initialized=getattr(manager, "initialized", False),
            )

        return self._sensor_status_to_payload(status)

    def _sensor_status_to_payload(self, status: dict[str, Any]) -> dict[str, Any]:
        components: dict[str, Any] = {}
        overall = HealthLevel.HEALTHY
        for key, value in status.items():
            if not key.endswith("_status"):
                continue
            component_name = key.removesuffix("_status")
            component_status = str(value).lower()
            component_level = self._map_sensor_status_to_health(component_status)
            components[component_name] = {
                "status": component_status,
                "health": component_level.value,
            }
            overall = _merge_status(overall, component_level)

        if not components:
            overall = HealthLevel.UNKNOWN
            detail = "No sensor components reported status"
        elif overall is HealthLevel.HEALTHY:
            detail = "All sensors reporting healthy"
        else:
            detail = "Sensor issues detected"

        return self._sensor_health_payload(
            overall,
            detail,
            components,
            initialized=bool(status.get("initialized")),
        )

    def _map_sensor_status_to_health(self, status: str) -> HealthLevel:
        normalized = status.lower()
        if normalized in {"online", "ok", "healthy", "ready", "running"}:
            return HealthLevel.HEALTHY
        if normalized in {"calibrating", "initializing", "unknown", "standby", "warning"}:
            return HealthLevel.DEGRADED
        if normalized in {"offline", "error", "fault", "timeout", "failed"}:
            return HealthLevel.CRITICAL
        return HealthLevel.UNKNOWN

    def _evaluate_dependencies(self, metrics_snapshot: dict[str, Any]) -> dict[str, Any]:
        if self._dependency_provider:
            try:
                payload = self._dependency_provider(metrics_snapshot)
            except Exception as exc:
                logger.debug("Custom dependency provider failed: %s", exc, exc_info=exc)
            else:
                if isinstance(payload, dict):
                    return payload

        return {
            "metrics_collector": self._check_metrics_dependency(metrics_snapshot),
            "log_storage": self._check_log_storage(),
        }

    def _check_metrics_dependency(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        config = observability.config
        if not getattr(config, "enable_metrics", True):
            return {
                "status": HealthLevel.UNKNOWN.value,
                "detail": "Metrics collection disabled",
            }

        system_metrics = snapshot.get("system")
        if not isinstance(system_metrics, list) or not system_metrics:
            return {
                "status": HealthLevel.DEGRADED.value,
                "detail": "No system metrics collected",
            }

        latest = system_metrics[-1]
        timestamp_value = latest.get("timestamp")
        try:
            last_sample = datetime.fromtimestamp(float(timestamp_value), tz=UTC)
        except Exception:
            return {
                "status": HealthLevel.DEGRADED.value,
                "detail": "Latest metrics sample missing timestamp",
            }

        age_seconds = (datetime.now(UTC) - last_sample).total_seconds()
        interval = float(getattr(config, "metrics_interval_seconds", 10))
        freshness_budget = max(interval * 3, 30.0)

        status = HealthLevel.HEALTHY
        if age_seconds > freshness_budget * 2:
            status = HealthLevel.CRITICAL
        elif age_seconds > freshness_budget:
            status = HealthLevel.DEGRADED

        detail = (
            "Metrics thread healthy"
            if status is HealthLevel.HEALTHY
            else f"Metrics sample stale ({age_seconds:.1f}s old)"
        )

        return {
            "status": status.value,
            "detail": detail,
            "last_sample": last_sample.isoformat(),
            "age_seconds": round(age_seconds, 1),
        }

    def _check_log_storage(self) -> dict[str, Any]:
        log_file = Path(
            getattr(
                observability.config,
                "log_file_path",
                "./logs/lawnberry.log",
            )
        )
        target_dir = log_file.parent
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            probe_path = target_dir / ".health_log_probe"
            probe_path.write_text("ok", encoding="utf-8")
            probe_path.unlink()
            status = HealthLevel.HEALTHY
            detail = "Log directory writable"
        except Exception as exc:
            status = HealthLevel.CRITICAL
            detail = f"Log directory not writable: {exc}"
        return {
            "status": status.value,
            "detail": detail,
            "path": str(target_dir),
        }

    def _load_system_config(self) -> dict[str, Any]:
        path = self.system_config_path
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except Exception as exc:
            logger.debug("Failed to read system config: %s", exc)
            return {}

    def _load_hardware_config(self) -> tuple[dict[str, Any] | None, str | None]:
        path = self.hardware_config_path
        if not path.exists():
            return None, f"Hardware configuration not found at {path}"
        try:
            data = yaml.safe_load(path.read_text()) or {}
            if not isinstance(data, dict):
                return None, "Hardware configuration must be a mapping"
            return data, None
        except Exception as exc:  # pragma: no cover - defensive
            return None, f"Unable to parse hardware configuration: {exc}"

    def _evaluate_hardware(self) -> dict[str, Any]:
        config, error = self._load_hardware_config()
        checks: list[dict[str, Any]] = []
        status = HealthLevel.HEALTHY

        if error:
            checks.append({"component": "configuration", "status": "error", "detail": error})
            return {"status": HealthLevel.CRITICAL.value, "checks": checks}

        assert config is not None

        gps_config = config.get("gps") or config.get("gps_type")
        if gps_config:
            checks.append(
                {
                    "component": "gps",
                    "status": "configured",
                    "detail": gps_config,
                }
            )
        else:
            checks.append(
                {"component": "gps", "status": "missing", "detail": "GPS section not configured"}
            )
            status = _merge_status(status, HealthLevel.CRITICAL)

        imu_config = config.get("imu") or config.get("imu_type")
        if imu_config:
            checks.append(
                {
                    "component": "imu",
                    "status": "configured",
                    "detail": imu_config,
                }
            )
        else:
            checks.append(
                {"component": "imu", "status": "missing", "detail": "IMU section not configured"}
            )
            status = _merge_status(status, HealthLevel.CRITICAL)

        sensors_config = config.get("sensors") or {}
        if not isinstance(sensors_config, dict):
            sensors_config = {}
        tof_config = sensors_config.get("tof") or config.get("tof_sensors")
        if tof_config:
            checks.append(
                {
                    "component": "tof_sensors",
                    "status": "configured",
                    "detail": tof_config,
                }
            )
        else:
            checks.append(
                {
                    "component": "tof_sensors",
                    "status": "missing",
                    "detail": "No Time-of-Flight sensors declared",
                }
            )
            status = _merge_status(status, HealthLevel.DEGRADED)

        power_monitor_enabled = bool(
            config.get("power_monitor", sensors_config.get("power_monitor", False))
        )
        if power_monitor_enabled:
            checks.append(
                {
                    "component": "power_monitor",
                    "status": "configured",
                    "detail": True,
                }
            )
        else:
            checks.append(
                {
                    "component": "power_monitor",
                    "status": "disabled",
                    "detail": "Power monitoring disabled; battery telemetry limited",
                }
            )
            status = _merge_status(status, HealthLevel.DEGRADED)

        motor_controller = config.get("motor_controller")
        if motor_controller:
            checks.append(
                {
                    "component": "motor_controller",
                    "status": "configured",
                    "detail": motor_controller,
                }
            )
        else:
            checks.append(
                {
                    "component": "motor_controller",
                    "status": "missing",
                    "detail": "Motor controller not declared",
                }
            )
            status = _merge_status(status, HealthLevel.DEGRADED)

        return {"status": status.value, "checks": checks}

    def _evaluate_subsystems(
        self,
        system_config: dict[str, Any],
        rates: dict[str, float],
        counts: dict[str, int],
        recent_errors: list[dict[str, Any]],
        sensor_health: dict[str, Any],
    ) -> dict[str, Any]:
        subsystems: dict[str, Any] = {}

        subsystems["api"] = self._status_from_errors(
            "http_request", rates, counts, recent_errors
        )
        subsystems["metrics"] = self._status_from_errors(
            "metrics", rates, counts, recent_errors
        )
        subsystems["job_scheduler"] = self._status_from_errors(
            "job_scheduler", rates, counts, recent_errors
        )
        subsystems["telemetry"] = self._status_from_errors(
            "telemetry", rates, counts, recent_errors
        )
        subsystems["acme"] = self._status_from_errors(
            "acme", rates, counts, recent_errors
        )
        # TLS/HTTPS certificate status
        try:
            tls = get_tls_status()
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("TLS status probe failed: %s", exc)
            tls = {"status": HealthLevel.UNKNOWN.value, "detail": "TLS probe failed"}
        else:
            # normalize status to HealthLevel
            tls_status = _coerce_level(tls.get("status"))
            tls["status"] = tls_status.value
        subsystems["tls"] = tls
        subsystems["database"] = self._check_database()
        subsystems["remote_access"] = self._check_remote_access(system_config)
        subsystems["sensors"] = {
            "status": sensor_health.get("status", HealthLevel.UNKNOWN.value),
            "detail": sensor_health.get("detail"),
            "components": sensor_health.get("components"),
            "initialized": sensor_health.get("initialized"),
            "last_checked": sensor_health.get("last_checked"),
        }

        return subsystems

    def _status_from_errors(
        self,
        origin: str,
        rates: dict[str, float],
        counts: dict[str, int],
        recent_errors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        rate = rates.get(origin, 0.0)
        count = counts.get(origin, 0)
        window_minutes = max(self.error_window_seconds / 60.0, 1.0)

        matching_errors = [
            {
                "timestamp": err.get("timestamp"),
                "level": err.get("level"),
                "message": err.get("message"),
            }
            for err in recent_errors
            if err.get("origin") == origin
        ][:5]

        status = HealthLevel.HEALTHY
        if matching_errors:
            levels = {entry.get("level", "ERROR") for entry in matching_errors}
            if any(level in {"CRITICAL", "FATAL"} for level in levels):
                status = HealthLevel.CRITICAL
            else:
                status = HealthLevel.DEGRADED

        if status == HealthLevel.HEALTHY:
            if rate >= self.critical_error_rate_threshold:
                status = HealthLevel.CRITICAL
            elif rate >= self.degrade_error_rate_threshold or count > 0:
                status = HealthLevel.DEGRADED

        detail = (
            "no recent errors"
            if count == 0
            else f"{count} errors in last {window_minutes:.1f} minutes"
        )
        payload: dict[str, Any] = {
            "status": status.value,
            "error_rate_per_minute": round(rate, 3),
            "errors_last_window": count,
            "detail": detail,
        }
        if matching_errors:
            payload["recent_errors"] = matching_errors
        return payload

    def _check_database(self) -> dict[str, Any]:
        path = self.database_path
        if not path.exists():
            return {
                "status": HealthLevel.CRITICAL.value,
                "detail": "Database file missing",
                "meta": {"path": str(path)},
            }

        try:
            size = path.stat().st_size
            with sqlite3.connect(path) as conn:
                conn.execute("PRAGMA quick_check")
            return {
                "status": HealthLevel.HEALTHY.value,
                "detail": "SQLite database accessible",
                "meta": {"path": str(path), "size_bytes": size},
            }
        except Exception as exc:
            return {
                "status": HealthLevel.DEGRADED.value,
                "detail": f"Database check failed: {exc}",
                "meta": {"path": str(path)},
            }

    def _check_remote_access(self, system_config: dict[str, Any]) -> dict[str, Any]:
        enabled = bool(system_config.get("system", {}).get("remote_access"))
        path = self.remote_access_status_path
        if not enabled:
            return {
                "status": HealthLevel.HEALTHY.value,
                "detail": "Remote access disabled in configuration",
                "meta": {"enabled": False},
            }

        if not path.exists():
            return {
                "status": HealthLevel.DEGRADED.value,
                "detail": "Remote access status file missing",
                "meta": {"path": str(path)},
            }

        try:
            payload = json.loads(path.read_text())
        except Exception as exc:
            return {
                "status": HealthLevel.DEGRADED.value,
                "detail": f"Unable to parse remote access status: {exc}",
                "meta": {"path": str(path)},
            }

        health_state = (payload.get("health") or "unknown").lower()
        detail = payload.get("message") or "remote access status loaded"
        meta = {
            "provider": payload.get("provider"),
            "url": payload.get("url"),
            "active": payload.get("active"),
        }

        if health_state == "healthy":
            status = HealthLevel.HEALTHY
        elif health_state in {"starting", "restarting", "degraded"}:
            status = HealthLevel.DEGRADED
        elif health_state in {"error", "failed"}:
            status = HealthLevel.CRITICAL
        else:
            status = HealthLevel.UNKNOWN

        return {"status": status.value, "detail": detail, "meta": meta}

    def _build_metrics_section(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        system_metrics: list[dict[str, Any]] = snapshot.get("system", []) if snapshot else []
        latest = system_metrics[-1] if system_metrics else {}

        sample_time = latest.get("timestamp")
        if isinstance(sample_time, (int, float)):
            sample_iso = datetime.fromtimestamp(sample_time, tz=UTC).isoformat()
        else:
            sample_iso = None

        return {
            "samples_collected": len(system_metrics),
            "latest_sample": sample_iso,
            "cpu_usage_percent": latest.get("cpu_usage"),
            "memory_usage_mb": latest.get("memory_usage_mb"),
            "disk_usage_percent": latest.get("disk_usage_percent"),
            "network_connections": latest.get("network_connections"),
            "active_websocket_clients": latest.get("active_websocket_clients"),
            "telemetry_broadcast_rate": latest.get("telemetry_broadcast_rate"),
            "api_request_count": latest.get("api_request_count"),
            "api_error_count": latest.get("api_error_count"),
            "database_query_time_ms_avg": latest.get("database_query_time_ms"),
        }