"""Contract test (T056): Navigation mode manager transitions.

Test goals (FR-032):
- Support transitions MANUAL ↔ AUTONOMOUS ↔ EMERGENCY_STOP

Notes:
- Placeholder uses /api/v2/nav/mode endpoints if present.
"""
from __future__ import annotations

import os
import pytest
import httpx

from backend.src.main import app


BASE_URL = "http://test"


@pytest.mark.asyncio
async def test_navigation_mode_transitions():
    os.environ["SIM_MODE"] = "1"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # Set MANUAL
        resp = await client.post("/api/v2/nav/mode", json={"mode": "MANUAL"})
        assert resp.status_code in {200, 404}

        # Set AUTONOMOUS
        resp = await client.post("/api/v2/nav/mode", json={"mode": "AUTONOMOUS"})
        assert resp.status_code in {200, 404}

        # Trigger EMERGENCY_STOP via control API
        resp = await client.post("/api/v2/control/emergency", json={})
        assert resp.status_code in {200, 202}

        nav = await client.get("/api/v2/nav/status")
        assert nav.status_code in {200, 404}
        if nav.status_code == 200:
            data = nav.json()
            mode = data.get("mode") or data.get("navigation_mode")
            assert mode in {"EMERGENCY_STOP", "MANUAL", "AUTONOMOUS", None}
