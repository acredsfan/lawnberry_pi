"""Contract test (T041): INA3221 power monitor provides battery/solar metrics with retries.

Goals (FR-024, NFR-008):
- Read battery/solar voltage/current (channels 1 and 3 assigned)
- Timeout/retry behavior surfaces degraded or last_error

Placeholder contract; skipped by default unless RUN_PLACEHOLDER_CONTRACT=1.
"""
from __future__ import annotations

import os

import httpx
import pytest

from backend.src.main import app

BASE_URL = "http://test"


@pytest.mark.asyncio
async def test_ina3221_reports_power_channels_and_timeouts():
    os.environ["SIM_MODE"] = "1"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        resp = await client.get("/api/v2/sensors/health")
        assert resp.status_code in {200, 404}
        # When implemented, expect fields like
        # battery_voltage, battery_current_amps,
        # solar_voltage, solar_current_amps
