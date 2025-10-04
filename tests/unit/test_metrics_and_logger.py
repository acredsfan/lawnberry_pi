from fastapi.testclient import TestClient
import logging
import sys
from pathlib import Path

# Ensure repository root is on sys.path for 'backend' package imports
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.src.main import app
from backend.src.core import logger as lb_logger


def test_metrics_endpoint_basic():
    client = TestClient(app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    # Basic Prometheus format lines we emit
    assert "lawnberry_system_cpu_usage_percent" in body
    assert "lawnberry_system_memory_usage_mb" in body
    assert "lawnberry_api_request_count" in body


def test_logger_wrapper_returns_logger():
    log = lb_logger.get_logger("unit-test")
    assert isinstance(log, logging.Logger)
    # Ensure we can log without raising
    log.info("unit test log message", extra={"test_key": "value"})
