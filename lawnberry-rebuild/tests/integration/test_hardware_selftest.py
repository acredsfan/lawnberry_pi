import os
import pytest
import httpx
import asyncio
from backend.src.main import app


RUN_HW = os.getenv("RUN_HW_TESTS", "0") == "1"


@pytest.mark.skipif(not RUN_HW, reason="Hardware self-test disabled by default; set RUN_HW_TESTS=1")
@pytest.mark.asyncio
async def test_system_selftest_endpoint():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/system/selftest")
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        # summary should contain expected keys
        summary = data["summary"]
        assert "i2c_bus_present" in summary
        assert "serial_port_present" in summary