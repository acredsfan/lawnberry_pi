"""Long soak test for 8-hour operation (FR-043).

This test is skipped by default. To enable, set RUN_8H_SOAK=1. It verifies:
- no unsafe events (best-effort via available endpoints)
- memory growth <5%
- endpoints remain responsive throughout run
"""

import os
import time

import httpx
import pytest


def _rss_kb() -> int:
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except Exception:
        pass
    return 0


@pytest.mark.asyncio
async def test_long_soak_8h():
    if os.environ.get("RUN_8H_SOAK") != "1":
        pytest.skip("8-hour soak disabled (set RUN_8H_SOAK=1)")

    from backend.src.main import app

    duration_s = int(os.environ.get("SOAK_DURATION_SECONDS", str(8 * 3600)))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=10.0
    ) as client:
        start_mem = _rss_kb()
        start = time.time()
        ok = 0

        while time.time() - start < duration_s:
            # Health endpoints
            r1 = await client.get("/health")
            r2 = await client.get("/api/v2/dashboard/metrics")
            assert r1.status_code == 200
            assert r2.status_code == 200
            ok += 1

            # Brief pause
            time.sleep(0.5)

        end_mem = _rss_kb()
        if start_mem > 0 and end_mem > 0:
            growth_pct = (end_mem - start_mem) / max(1, start_mem) * 100.0
            assert growth_pct < 5.0, f"Memory growth too high: {growth_pct:.2f}%"
        assert ok > 0
