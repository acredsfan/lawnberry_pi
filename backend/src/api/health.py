from fastapi import APIRouter

from ..core.health import HealthService

router = APIRouter()


health_service = HealthService()


@router.get("/health")
def health_root() -> dict:
    """Return aggregated health status for platform monitoring."""

    return health_service.evaluate()


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
