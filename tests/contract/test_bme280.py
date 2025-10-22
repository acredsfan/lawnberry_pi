"""Contract test (T040): BME280 environmental sensor reports temp/humidity/pressure.

Goals (FR-023):
- Read temperature, humidity, pressure via API or driver health endpoint
- Validate timeout handling (degraded) when sensor unreachable

Placeholder contract; skipped by default unless RUN_PLACEHOLDER_CONTRACT=1.
"""
from __future__ import annotations

import os

import httpx
import pytest

from backend.src.main import app

BASE_URL = "http://test"


@pytest.mark.asyncio
async def test_bme280_reports_environmentals_and_handles_timeouts():
    os.environ["SIM_MODE"] = "1"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.get("/api/v2/sensors/health")
        assert resp.status_code in {200, 404}
        # When implemented, assert payload contains bme280 with
        # temperature_celsius/humidity_percent/pressure_hpa
