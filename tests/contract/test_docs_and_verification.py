"""Contract tests for documentation bundle and verification artifact endpoints."""

import pytest
import httpx

from backend.src.main import app


BASE_URL = "http://test"


@pytest.mark.asyncio
async def test_get_docs_bundle_returns_items_and_offline_header():
    """GET /api/v2/docs/bundle should list documentation entries with offline metadata."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get("/api/v2/docs/bundle")

        assert response.status_code == 200, response.text
        payload = response.json()

        items = payload.get("items")
        assert isinstance(items, list) and items, "Expected docs bundle entries"

        for item in items:
            for field in ("doc_id", "title", "version", "last_updated", "checksum", "offline_available"):
                assert field in item
            assert len(item["checksum"]) == 64

        assert response.headers.get("x-docs-offline-ready") in {"true", "false"}


@pytest.mark.asyncio
async def test_get_docs_bundle_surfaces_checksum_warning():
    """Checksum mismatch should be communicated via response headers for remediation."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get(
            "/api/v2/docs/bundle",
            params={"simulate_checksum_mismatch": "hardware-overview"},
        )

        assert response.status_code == 200, response.text
        warning = response.headers.get("x-docs-checksum-warning")
        assert warning == "hardware-overview"


@pytest.mark.asyncio
async def test_post_verification_artifact_records_metadata():
    """POST /api/v2/verification-artifacts should accept valid metadata and assign ID."""

    payload = {
        "type": "telemetry_log",
        "location": "verification_artifacts/telemetry/pi5-run.json",
        "summary": "Pi5 telemetry evidence run",
        "linked_requirements": ["FR-001", "FR-016"],
        "created_by": "contract-test",
        "metadata": {"latency_ms_p95": 240.0},
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post("/api/v2/verification-artifacts", json=payload)

        assert response.status_code == 201, response.text
        body = response.json()

        assert isinstance(body.get("artifact_id"), str)
        assert body.get("created_at")
        assert body.get("linked_requirements") == payload["linked_requirements"]


@pytest.mark.asyncio
async def test_post_verification_artifact_requires_known_requirements():
    """Submitting unknown requirement IDs should be rejected to keep traceability."""

    payload = {
        "type": "doc_diff",
        "location": "verification_artifacts/docs/changelog.md",
        "linked_requirements": ["FR-999"],
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post("/api/v2/verification-artifacts", json=payload)

        assert response.status_code == 422, response.text
        detail = response.json()
        assert detail.get("error_code") == "UNKNOWN_REQUIREMENT"


@pytest.mark.asyncio
async def test_post_verification_artifact_requires_at_least_one_requirement():
    """Empty linked_requirements collection should raise validation error."""

    payload = {
        "type": "ui_screencast",
        "location": "verification_artifacts/ui/dashboard.mp4",
        "linked_requirements": [],
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.post("/api/v2/verification-artifacts", json=payload)

        assert response.status_code == 422, response.text
        detail = response.json()
        assert detail.get("error_code") == "MISSING_REQUIREMENTS"
        assert "remediation_url" in detail
