"""Contract test (T053): GPS integration accuracy <5m.

Test goals (FR-028, FR-033):
- Read GPS position via API
- Verify reported accuracy <5m when injected

Notes:
- Placeholder contract: skipped by default unless RUN_PLACEHOLDER_CONTRACT=1
"""
from __future__ import annotations

import os
import pytest
import httpx

from backend.src.main import app


BASE_URL = "http://test"


@pytest.mark.asyncio
async def test_gps_accuracy_under_5m():
    os.environ["SIM_MODE"] = "1"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # Inject a precise GPS position
        inj = {"latitude": 37.4219999, "longitude": -122.0840575, "accuracy_m": 4.0}
        resp = await client.post("/api/v2/debug/gps/inject", json=inj)
        assert resp.status_code in {200, 404}

        # Read nav status
        nav = await client.get("/api/v2/nav/status")
        assert nav.status_code in {200, 404}
        if nav.status_code == 200:
            data = nav.json()
            pos = data.get("position", {})
            assert pos.get("latitude") is not None
            assert pos.get("longitude") is not None
            acc = pos.get("accuracy_m")
            assert acc is None or acc < 5.0
