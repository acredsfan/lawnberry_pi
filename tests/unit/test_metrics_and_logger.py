import logging

from backend.src.api.metrics import metrics
from backend.src.core import logger as lb_logger
from backend.src.core.observability import observability


def test_metrics_endpoint_basic():
    observability.reset_events_for_testing()
    observability.metrics.increment_counter("api_requests", 5)
    observability.metrics.record_metric("websocket_clients", 3)
    observability.metrics.record_timer("api_request_duration", 120.0)
    observability.metrics.collect_system_metrics()

    resp = metrics()
    assert resp.status_code == 200
    body = resp.body.decode()
    assert "lawnberry_system_cpu_usage_percent" in body
    assert "lawnberry_system_websocket_clients" in body
    assert "lawnberry_counter_api_requests 5" in body
    assert "lawnberry_timer_api_request_duration_count 1" in body
    assert "lawnberry_timer_api_request_duration_avg_ms 120.00" in body


def test_logger_wrapper_returns_logger():
    log = lb_logger.get_logger("unit-test")
    assert isinstance(log, logging.Logger)
    # Ensure we can log without raising
    log.info("unit test log message", extra={"test_key": "value"})
