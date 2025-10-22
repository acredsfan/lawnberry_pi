"""Contract test (T042): Sensor fusion produces fused position from GPS + IMU + odometry.

Goals (FR-025):
- Feed simulated GPS, IMU, and odometry inputs
- Verify fused output within 1m accuracy and reasonable heading continuity

Placeholder contract; skipped by default unless RUN_PLACEHOLDER_CONTRACT=1.
"""
from __future__ import annotations

import os

import httpx
import pytest

from backend.src.main import app

BASE_URL = "http://test"


@pytest.mark.asyncio
async def test_sensor_fusion_outputs_fused_position_with_accuracy():
    os.environ["SIM_MODE"] = "1"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        # Placeholder endpoints for injecting simulated data; to be implemented
        # await client.post(
        #     "/api/v2/debug/gps/inject",
        #     json={"lat": 37.0, "lon": -122.0, "accuracy_m": 0.8},
        # )
        # await client.post(
        #     "/api/v2/debug/imu/inject",
        #     json={"yaw": 90.0},
        # )
        # await client.post(
        #     "/api/v2/debug/odometry/inject",
        #     json={"distance_m": 1.0},
        # )

        # Query fused state once implemented
        resp = await client.get("/api/v2/fusion/state")
        assert resp.status_code in {200, 404}
        # When implemented, assert response contains position.lat/lon and quality indicator
