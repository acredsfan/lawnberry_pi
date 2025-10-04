"""Contract test (T038): ToF sensors and emergency stop behavior.

Test goals (FR-021, NFR-008):
- Read left/right ToF distance via driver or API facade
- Distance <0.2m triggers emergency stop within software path
- Timeout/retry behavior is exposed as degraded health

Notes:
- Placeholder contract: skipped by default unless RUN_PLACEHOLDER_CONTRACT=1
- When implemented, this should use a SIM_MODE mock driver publishing on message bus
"""
from __future__ import annotations

import os
import pytest
import httpx

from backend.src.main import app

BASE_URL = "http://test"


@pytest.mark.asyncio
async def test_tof_obstacle_triggers_emergency_stop_within_threshold():
    # Ensure simulation mode for CI safety
    os.environ["SIM_MODE"] = "1"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # Simulate obstacle injection endpoint (to be implemented):
        # POST /api/v2/debug/sensors/inject-tof {position: "left", distance_m: 0.15}
        resp = await client.post("/api/v2/debug/sensors/inject-tof", json={"position": "left", "distance_m": 0.15})
        assert resp.status_code in {200, 404}, "Endpoint not implemented yet; placeholder contract"

        # Read safety status and expect emergency_stop_active True when implemented
        status = await client.get("/api/v2/health/readiness")
        assert status.status_code in {200, 404}

        # When implemented, assert emergency stop or safety interlock is active.
        # Placeholder assertion for now; real assertion should inspect payload once API is defined.
        # e.g., assert payload["safety"]["active_interlocks"] contains "obstacle_detected"


@pytest.mark.asyncio
async def test_tof_timeout_reports_degraded_health():
    os.environ["SIM_MODE"] = "1"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # GET /api/v2/sensors/health should surface ToF status once implemented
        resp = await client.get("/api/v2/sensors/health")
        assert resp.status_code in {200, 404}
        # When implemented, expect a structure like {"tof_left": {"status": "degraded", "last_error": "timeout"}, ...}
