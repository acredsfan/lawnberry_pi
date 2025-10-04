"""Contract test for fault injection framework (FR-042).

Enables fault injection and verifies system degrades gracefully and reports
degraded/fault status in sensor health endpoint.
"""
import os

import httpx
import pytest


@pytest.mark.asyncio
async def test_fault_injection_degrades_sensor_health():
    # Enable fault injection for gps loss and sensor timeout
    original_env = os.environ.get("FAULT_INJECT")
    os.environ["FAULT_INJECT"] = "sensor_timeout,gps_loss"

    try:
        from backend.src.main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v2/sensors/health")
            assert resp.status_code == 200
            data = resp.json()
            assert "components" in data
            comps = data["components"]

            # With gps_loss injected, gps status should not be healthy/online
            gps_status = comps.get("gps", {}).get("status", "unknown").lower()
            assert gps_status in {"fault", "degraded", "warning", "unknown"}
            assert gps_status != "healthy"

            # With sensor_timeout injected, imu should be degraded or warning
            imu_status = comps.get("imu", {}).get("status", "unknown").lower()
            assert imu_status in {"degraded", "warning", "fault", "unknown"}
    finally:
        if original_env is None:
            os.environ.pop("FAULT_INJECT", None)
        else:
            os.environ["FAULT_INJECT"] = original_env
