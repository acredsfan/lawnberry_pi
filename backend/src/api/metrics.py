from fastapi import APIRouter, Response

from ..core.observability import observability
from ..core.tls_status import get_tls_status

router = APIRouter()


def _sanitize_metric_name(name: str) -> str:
    return "lawnberry_" + "".join(ch if ch.isalnum() else "_" for ch in name).lower()


@router.get("/metrics")
def metrics() -> Response:
    """Expose a Prometheus-compatible metrics snapshot."""

    snapshot = observability.get_metrics_snapshot()
    lines: list[str] = []

    system_metrics = snapshot.get("system", [])
    latest_system = system_metrics[-1] if system_metrics else {}

    lines.append(f"lawnberry_system_cpu_usage_percent {latest_system.get('cpu_usage', 0.0):.2f}")
    lines.append(
        f"lawnberry_system_memory_usage_mb {latest_system.get('memory_usage_mb', 0.0):.2f}"
    )
    lines.append(
        f"lawnberry_system_disk_usage_percent {latest_system.get('disk_usage_percent', 0.0):.2f}"
    )
    lines.append(
        f"lawnberry_system_websocket_clients {latest_system.get('active_websocket_clients', 0)}"
    )

    for counter, value in snapshot.get("counters", {}).items():
        metric_name = _sanitize_metric_name(f"counter_{counter}")
        lines.append(f"{metric_name} {value}")

    for gauge, value in snapshot.get("gauges", {}).items():
        metric_name = _sanitize_metric_name(f"gauge_{gauge}")
        lines.append(f"{metric_name} {value}")

    for timer, stats in snapshot.get("timers", {}).items():
        metric_base = _sanitize_metric_name(f"timer_{timer}")
        count = stats.get("count", 0)
        avg = stats.get("avg", 0.0)
        min_v = stats.get("min", 0.0)
        max_v = stats.get("max", 0.0)
        lines.append(f"{metric_base}_count {count}")
        lines.append(f"{metric_base}_avg_ms {avg:.2f}")
        lines.append(f"{metric_base}_min_ms {min_v:.2f}")
        lines.append(f"{metric_base}_max_ms {max_v:.2f}")

    # TLS certificate metrics
    try:
        tls = get_tls_status()
    except Exception:
        tls = {"mode": "unknown", "domain": "", "days_until_expiry": -1, "valid_now": False}
    mode = str(tls.get("mode") or "unknown")
    domain = str(tls.get("domain") or "")
    days = tls.get("days_until_expiry")
    if days is None:
        days = -1
    valid = 1 if tls.get("valid_now") else 0
    # Prometheus-style labels
    lines.append(f'lawnberry_tls_cert_days_until_expiry{{mode="{mode}",domain="{domain}"}} {days}')
    lines.append(f'lawnberry_tls_cert_valid{{mode="{mode}",domain="{domain}"}} {valid}')

    body = "\n".join(lines) + "\n"
    return Response(content=body, media_type="text/plain; version=0.0.4")
