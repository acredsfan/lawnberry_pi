"""Contract test for dashboard metrics (FR-045).

Validates GET /api/v2/dashboard/metrics returns key performance indicators.
The endpoint should be resilient in SIM/CI environments and return sensible
defaults when hardware services are unavailable.
"""

import httpx
import pytest


@pytest.mark.asyncio
async def test_dashboard_metrics_endpoint_shape():
    from backend.src.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v2/dashboard/metrics")
        assert resp.status_code == 200
        data = resp.json()

        # Top-level keys
        for key in ("battery", "coverage", "safety", "uptime"):
            assert key in data

        # Battery
        bat = data["battery"]
        assert isinstance(bat.get("percentage", 0.0), (int, float))
        assert isinstance(bat.get("voltage", 0.0), (int, float))
        assert isinstance(bat.get("current", 0.0), (int, float))
        assert bat.get("health") in {"healthy", "warning", "critical", "unknown"}

        # Coverage
        cov = data["coverage"]
        assert isinstance(cov.get("area_covered_sqm", 0.0), (int, float))
        assert isinstance(cov.get("efficiency_percent", 0.0), (int, float))

        # Safety
        saf = data["safety"]
        assert isinstance(saf.get("interlocks_active", 0), int)
        assert isinstance(saf.get("emergency_stops", 0), int)

        # Uptime
        up = data["uptime"]
        assert "since" in up and isinstance(up.get("uptime_percent_24h", 0.0), (int, float))
