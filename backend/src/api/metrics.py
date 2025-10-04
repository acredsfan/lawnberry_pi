from fastapi import APIRouter, Response
from ..core.observability import observability

router = APIRouter()


@router.get("/metrics")
def metrics() -> Response:
    """Expose a minimal Prometheus-compatible metrics snapshot.

    NOTE: This is a lightweight exporter summarizing counters/timers collected
    by ObservabilityManager. It can be expanded later.
    """
    metrics = observability.metrics.get_metrics_summary()

    lines: list[str] = []
    sysm = metrics.get("system", {})
    lines.append(f"lawnberry_system_cpu_usage_percent {sysm.get('cpu_usage', 0.0):.2f}")
    lines.append(f"lawnberry_system_memory_usage_mb {sysm.get('memory_usage_mb', 0.0):.2f}")
    lines.append(f"lawnberry_system_disk_usage_percent {sysm.get('disk_usage_percent', 0.0):.2f}")
    lines.append(f"lawnberry_api_request_count {metrics.get('counters', {}).get('api_requests', 0)}")
    lines.append(f"lawnberry_api_error_count {metrics.get('counters', {}).get('api_errors', 0)}")
    timers = metrics.get("timers", {})
    api_req = timers.get("api_request_duration", {"avg": 0.0})
    lines.append(f"lawnberry_api_request_duration_ms_avg {api_req.get('avg', 0.0):.2f}")

    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4")
