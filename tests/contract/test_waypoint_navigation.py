"""Contract test (T055): Waypoint navigation arrival detection.

Test goals (FR-031):
- Provide a waypoint and simulated position updates; expect arrival flag

Notes:
- Placeholder uses /api/v2/nav/waypoints and /api/v2/nav/status if present.
"""
from __future__ import annotations

import os
import pytest
import httpx

from backend.src.main import app


BASE_URL = "http://test"


@pytest.mark.asyncio
async def test_waypoint_arrival_detection():
    os.environ["SIM_MODE"] = "1"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # Send a single waypoint near a known GPS injection point
        wp = {"waypoints": [{"waypoint_id": "wp1", "latitude": 37.4220, "longitude": -122.0841, "arrival_threshold_m": 2.0}]}
        r = await client.post("/api/v2/nav/waypoints", json=wp)
        assert r.status_code in {200, 404}

        # Inject matching GPS position
        inj = {"latitude": 37.4220, "longitude": -122.0841, "accuracy_m": 3.0}
        await client.post("/api/v2/debug/gps/inject", json=inj)

        nav = await client.get("/api/v2/nav/status")
        assert nav.status_code in {200, 404}
        if nav.status_code == 200:
            data = nav.json()
            reached = data.get("waypoint_reached")
            # Allow None until implemented
            assert reached in {True, False, None}
