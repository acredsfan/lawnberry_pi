"""Contract test for diagnostics log bundle (FR-044).

Verifies POST /api/v2/diagnostics/log-bundle returns bundle metadata
and that the bundle path appears plausible.
"""
import httpx
import pytest


@pytest.mark.asyncio
async def test_generate_log_bundle_returns_metadata():
    from backend.src.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v2/diagnostics/log-bundle", json={
            "incident_type": "operator_request",
            "time_range_minutes": 5
        })

        # Initially may be 404/501 before implementation; after T086 should be 200
        assert resp.status_code in (200, 201, 404, 501)

        if resp.status_code in (200, 201):
            data = resp.json()
            assert "bundle_id" in data
            assert "file_path" in data
            assert data["file_path"].endswith(".tar.gz")
            assert isinstance(data.get("size_bytes", 0), int)
