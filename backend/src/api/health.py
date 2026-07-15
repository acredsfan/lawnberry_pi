from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..core.build_info import get_build_info
from ..core.health import HealthService

router = APIRouter()


class SystemInfoResponse(BaseModel):
    version: str
    commit_sha: str | None
    short_sha: str | None
    source: str
    started_at: str


def _robohat_health_provider() -> dict | None:
    try:
        from ..services.robohat_service import get_robohat_service
        svc = get_robohat_service()
        if svc is None:
            return None
        return svc.get_status().to_dict()
    except Exception:
        return None


health_service = HealthService(robohat_provider=_robohat_health_provider)


def _service_for_request(request: Request = None) -> HealthService:
    runtime = getattr(request.app.state, "runtime", None) if request is not None else None
    if runtime is None:
        return health_service
    return HealthService(
        robohat_provider=_robohat_health_provider,
        hardware_config=getattr(runtime, "hardware_config", None),
        config_loader=getattr(runtime, "config_loader", None),
    )


def _with_compatibility_aliases(report: dict) -> dict:
    subsystems = report.get("subsystems") if isinstance(report.get("subsystems"), dict) else {}
    compatibility_status = report.get("overall_status") or "unknown"
    return {
        **report,
        "status": compatibility_status,
        "message_bus": subsystems.get(
            "telemetry",
            {"status": "unknown", "detail": "Message bus health unavailable"},
        ),
        "drivers": report.get("hardware", {"status": "unknown"}),
        "persistence": subsystems.get(
            "database",
            {"status": "unknown", "detail": "Persistence health unavailable"},
        ),
        "safety": {
            "status": compatibility_status,
            "detail": "Safety rollup compatibility alias",
            "sensor_health": report.get("sensor_health", {}).get("status"),
        },
    }


@router.get("/api/v2/system/info", response_model=SystemInfoResponse)
def system_info() -> dict:
    """Expose the exact backend build serving this request."""

    return get_build_info()


def health_root() -> dict:
    """Return the raw aggregated health status."""

    return health_service.evaluate()


@router.get("/health")
def health_root_route(request: Request = None) -> dict:
    """Return aggregated health status for platform monitoring."""

    report = _with_compatibility_aliases(_service_for_request(request).evaluate())
    startup_report = (
        getattr(request.app.state, "startup_config_report", None) if request is not None else None
    )
    report["startup_config_report"] = startup_report
    return report


@router.get("/api/v2/health")
def health_api_v2(request: Request = None) -> dict:
    """Expose health report under the versioned API namespace."""

    return _service_for_request(request).evaluate()


def health_liveness() -> dict:
    """Compatibility helper; the routed probe is owned by maintenance.py."""

    return {"status": "alive"}


def health_readiness(request: Request = None) -> dict:
    """Compatibility helper for direct callers of the aggregate report."""

    report = _service_for_request(request).evaluate()
    return {
        "status": report.get("overall_status"),
        "timestamp": report.get("timestamp"),
        "hardware": report.get("hardware"),
        "sensor_health": report.get("sensor_health"),
        "subsystems": report.get("subsystems"),
        "dependencies": report.get("dependencies"),
    }


@router.get("/healthz")
def healthz() -> dict:
    """Tiny liveness endpoint for cheap probes."""
    return {"status": "ok"}
