"""Contract test for 8-hour soak (FR-043).

This contract focuses on the existence of a soak harness and its behavior.
In CI, enable a short-run version by setting RUN_SOAK_CI=1. The long 8h run
is covered by tests/soak/test_8hour_operation.py and is gated by RUN_8H_SOAK=1.
"""

import os
import time

import httpx
import pytest


def _read_mem_kb() -> int:
    # Use /proc/self/status if available
    try:
        with open("/proc/self/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return int(parts[1])  # kB
    except Exception:
        pass
    return 0


@pytest.mark.asyncio
async def test_soak_quick_mode_contract():
    if os.environ.get("RUN_SOAK_CI") != "1":
        pytest.skip("Quick soak mode not enabled (set RUN_SOAK_CI=1)")

    from backend.src.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=5.0
    ) as client:
        duration_s = int(os.environ.get("SOAK_CI_SECONDS", "6"))
        start_mem = _read_mem_kb()
        start = time.time()
        ok = 0
        while time.time() - start < duration_s:
            r1 = await client.get("/health")
            r2 = await client.get("/api/v2/dashboard/metrics")
            assert r1.status_code == 200
            assert r2.status_code == 200
            ok += 1
            await client.get("/api/v2/health/liveness")
            await client.get("/api/v2/health/readiness")
            time.sleep(0.2)

        end_mem = _read_mem_kb()
        # Allow small growth in CI quick mode (<5%)
        if start_mem > 0 and end_mem > 0:
            growth_pct = (end_mem - start_mem) / max(1, start_mem) * 100.0
            assert growth_pct < 5.0, f"Memory growth too high: {growth_pct:.2f}%"
        assert ok > 0
