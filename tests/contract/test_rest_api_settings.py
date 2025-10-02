"""Contract tests for settings profile endpoints."""

import pytest
import httpx

from backend.src.main import app


BASE_URL = "http://test"


def _bump_patch(version: str) -> str:
    major, minor, patch = version.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


@pytest.mark.asyncio
async def test_get_settings_profile_returns_expected_sections():
    """GET /api/v2/settings should expose profile metadata and latency targets."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        response = await client.get("/api/v2/settings")

        assert response.status_code == 200, response.text
        payload = response.json()

        for key in (
            "profile_version",
            "hardware",
            "network",
            "telemetry",
            "simulation_mode",
            "ai_acceleration",
            "branding_checksum",
        ):
            assert key in payload, f"Missing {key}"

        telemetry = payload["telemetry"]
        assert telemetry.get("cadence_hz")
        latency_targets = telemetry.get("latency_targets", {})
        assert latency_targets.get("pi5_ms") <= 250
        assert latency_targets.get("pi4b_ms") <= 350

        checksum = payload.get("branding_checksum")
        assert isinstance(checksum, str) and len(checksum) == 64


@pytest.mark.asyncio
async def test_put_settings_profile_updates_version_and_persists_changes():
    """PUT /api/v2/settings should bump profile version and persist telemetry cadence."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        current = (await client.get("/api/v2/settings")).json()

        new_version = _bump_patch(current["profile_version"])
        update_payload = {
            **current,
            "profile_version": new_version,
        }
        update_payload["telemetry"]["cadence_hz"] = 7
        update_payload["simulation_mode"] = True

        response = await client.put("/api/v2/settings", json=update_payload)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get("profile_version") == new_version
        assert body.get("updated_at"), "updated_at missing in response"

        refreshed = (await client.get("/api/v2/settings")).json()
        assert refreshed["telemetry"]["cadence_hz"] == 7
        assert refreshed["simulation_mode"] is True


@pytest.mark.asyncio
async def test_put_settings_profile_detects_version_conflict():
    """Submitting a stale profile_version should return HTTP 409 with conflict detail."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        current = (await client.get("/api/v2/settings")).json()
        stale_payload = {
            **current,
            "profile_version": "0.0.1",  # guaranteed older than active semver
        }

        response = await client.put("/api/v2/settings", json=stale_payload)

        assert response.status_code == 409, response.text
        detail = response.json()
        assert detail.get("error_code") == "PROFILE_VERSION_CONFLICT"
        assert detail.get("current_version") == current["profile_version"]


@pytest.mark.asyncio
async def test_put_settings_profile_enforces_latency_targets():
    """Latency guardrails >250/350 ms should be rejected with validation error."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        current = (await client.get("/api/v2/settings")).json()
        new_version = _bump_patch(current["profile_version"])
        invalid_payload = {
            **current,
            "profile_version": new_version,
        }
        invalid_payload["telemetry"]["latency_targets"] = {"pi5_ms": 400, "pi4b_ms": 500}

        response = await client.put("/api/v2/settings", json=invalid_payload)

        assert response.status_code == 422, response.text
        detail = response.json()
        assert detail.get("error_code") == "LATENCY_GUARDRAIL_EXCEEDED"


@pytest.mark.asyncio
async def test_put_settings_profile_validates_branding_checksum():
    """Invalid branding checksum should surface remediation info."""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
        current = (await client.get("/api/v2/settings")).json()
        new_version = _bump_patch(current["profile_version"])
        invalid_payload = {
            **current,
            "profile_version": new_version,
            "branding_checksum": "deadbeef",
        }

        response = await client.put("/api/v2/settings", json=invalid_payload)

        assert response.status_code == 422, response.text
        detail = response.json()
        assert detail.get("error_code") == "BRANDING_ASSET_MISMATCH"
        assert "remediation_url" in detail
