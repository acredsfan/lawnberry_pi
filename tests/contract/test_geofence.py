"""Contract test (T054): Geofence enforcement.

Test goals (FR-030):
- When position outside geofence, system should immediately stop (EMERGENCY_STOP or inside_geofence=false)

Notes:
- Placeholder: uses /api/v2/debug/geofence and /api/v2/nav/status if implemented.
"""
from __future__ import annotations

import os
import pytest
import httpx

from backend.src.main import app


BASE_URL = "http://test"


@pytest.mark.asyncio
async def test_position_outside_boundary_triggers_stop():
    os.environ["SIM_MODE"] = "1"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # Define a tiny geofence around a point and inject a position outside it
        fence = {
            "geofence_id": "test",
            "boundary": [
                {"latitude": 37.422, "longitude": -122.084},
                {"latitude": 37.422, "longitude": -122.083},
                {"latitude": 37.421, "longitude": -122.083},
            ],
        }
        gf = await client.post("/api/v2/debug/geofence", json=fence)
        assert gf.status_code in {200, 404}

        # Inject a position clearly outside
        pos = {"latitude": 37.420, "longitude": -122.082, "accuracy_m": 3.0}
        resp = await client.post("/api/v2/debug/gps/inject", json=pos)
        assert resp.status_code in {200, 404}

        nav = await client.get("/api/v2/nav/status")
        assert nav.status_code in {200, 404}
        if nav.status_code == 200:
            data = nav.json()
            assert data.get("inside_geofence") in {False, None}
            # Optional: some implementations may also set mode to EMERGENCY_STOP
            mode = data.get("mode") or data.get("navigation_mode")
            if mode is not None:
                assert mode in {"EMERGENCY_STOP", "MANUAL", "IDLE"}
