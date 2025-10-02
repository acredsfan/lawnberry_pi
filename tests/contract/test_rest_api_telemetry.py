"""Contract tests for telemetry REST endpoints."""

import pytest
import httpx

from backend.src.main import app


BASE_URL = "http://test"


@pytest.mark.asyncio
async def test_get_telemetry_stream_includes_rtk_and_orientation_metadata():
    """GET /api/v2/telemetry/stream should return rich telemetry metadata."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get(
            "/api/v2/telemetry/stream",
            params={"limit": 5, "since": "2025-01-01T00:00:00Z"},
        )

        assert response.status_code == 200, response.text
        payload = response.json()

        assert "items" in payload and isinstance(payload["items"], list)
        assert "latency_summary_ms" in payload
        assert "next_since" in payload and payload["next_since"], "pagination cursor missing"

        assert payload["items"], "Expected at least one telemetry item"

        sample = payload["items"][0]
        for field in ("timestamp", "component_id", "latency_ms", "metadata"):
            assert field in sample, f"missing {field}"

        metadata = sample.get("metadata", {})
        # Telemetry metadata needs RTK/IMU context to satisfy FR-004.
        assert "rtk_fix" in metadata, "RTK fix state missing from metadata"
        assert metadata.get("rtk_fix") in {"fixed", "float", "none", "fallback"}
        assert "rtk_fallback_reason" in metadata, "Fallback reason missing"
        status_message = metadata.get("rtk_status_message")
        assert status_message, "Fallback/RTK status messaging missing"
        fallback_reason = metadata.get("rtk_fallback_reason")
        if fallback_reason:
            assert "fallback" in status_message.lower()
        assert "orientation" in metadata, "IMU orientation block missing"
        assert metadata["orientation"].get("type") in {"quaternion", "euler"}


@pytest.mark.asyncio
async def test_get_telemetry_export_returns_diagnostic_download():
    """GET /api/v2/telemetry/export should expose power-metric export with download headers."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get(
            "/api/v2/telemetry/export",
            params={"kind": "power", "window": "15m"},
        )

        assert response.status_code == 200, response.text
        assert "text/csv" in response.headers.get("content-type", ""), response.headers
        assert "attachment" in response.headers.get("content-disposition", "")
        body = response.text
        # CSV export should include INA3221 channel names per FR-003.
        assert "battery_channel" in body
        assert "solar_channel" in body


@pytest.mark.asyncio
async def test_post_telemetry_ping_reports_latency_guardrails():
    """POST /api/v2/telemetry/ping must report latency within constitutional limits."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post(
            "/api/v2/telemetry/ping",
            json={"component_id": "power", "sample_count": 5},
        )

        assert response.status_code == 200, response.text
        payload = response.json()

        for field in ("latency_ms_p95", "latency_ms_p50", "samples"):
            assert field in payload

        assert payload["latency_ms_p95"] <= 250, "Pi 5 latency guardrail exceeded"
        assert payload["latency_ms_p50"] <= 200
        assert isinstance(payload["samples"], list) and payload["samples"], "samples missing"
