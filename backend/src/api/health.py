from fastapi import APIRouter

from ..core.health import HealthService

router = APIRouter()


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


def _with_compatibility_aliases(report: dict) -> dict:
    subsystems = report.get("subsystems") if isinstance(report.get("subsystems"), dict) else {}
    compatibility_status = report.get("overall_status") or "healthy"
    if compatibility_status == "unknown":
        compatibility_status = "healthy"
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


def health_root() -> dict:
    """Return the raw aggregated health status."""

    return health_service.evaluate()


@router.get("/health")
def health_root_route() -> dict:
    """Return aggregated health status for platform monitoring."""

    return _with_compatibility_aliases(health_root())


@router.get("/api/v2/health")
def health_api_v2() -> dict:
    """Expose health report under the versioned API namespace."""

    return health_service.evaluate()


@router.get("/api/v2/health/liveness")
def health_liveness() -> dict:
    """Simple liveness probe for container orchestration."""

    return {"status": "alive"}


@router.get("/api/v2/health/readiness")
def health_readiness() -> dict:
    """Readiness probe including subsystem rollup."""

    report = health_service.evaluate()
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
