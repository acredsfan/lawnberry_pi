"""Cloudflare Access to LawnBerry session exchange contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from backend.src.services.cloudflare_access_service import (
    CloudflareAccessError,
    VerifiedCloudflareIdentity,
)


@pytest.mark.asyncio
async def test_verified_cloudflare_exchange_issues_working_local_session(test_client, monkeypatch):
    import backend.src.api.routers.auth as auth_router

    expiry = int((datetime.now(UTC) + timedelta(minutes=5)).timestamp())
    verifier = AsyncMock()
    verifier.verify.return_value = VerifiedCloudflareIdentity(
        principal="operator@example.com",
        expires_at=datetime.fromtimestamp(expiry, tz=UTC),
        claims={"sub": "cf-user", "email": "operator@example.com", "exp": expiry},
    )
    monkeypatch.setattr(auth_router, "cloudflare_access_verifier", verifier)

    response = await test_client.post(
        "/api/v2/auth/cloudflare",
        headers={
            "CF-Access-Jwt-Assertion": "signed-access-token",
            # An unsigned forwarding header must not override the signed claim.
            "CF-Access-Authenticated-User-Email": "attacker@example.com",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] not in {"", "[REDACTED]"}
    assert body["user"]["username"] == "operator@example.com"
    verifier.verify.assert_awaited_once_with("signed-access-token")

    profile = await test_client.get(
        "/api/v2/auth/profile",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert profile.status_code == 200
    assert profile.json()["username"] == "operator@example.com"


@pytest.mark.asyncio
async def test_invalid_cloudflare_assertion_never_falls_through_to_local_login(
    test_client, monkeypatch
):
    import backend.src.api.routers.auth as auth_router

    verifier = AsyncMock()
    verifier.verify.side_effect = CloudflareAccessError("Cloudflare Access signature invalid")
    monkeypatch.setattr(auth_router, "cloudflare_access_verifier", verifier)

    response = await test_client.post(
        "/api/v2/auth/cloudflare",
        headers={"CF-Access-Jwt-Assertion": "forged-token"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Cloudflare Access assertion invalid"
    assert auth_router.primary_auth_service.rate_limiter.locked_clients() == []


@pytest.mark.asyncio
async def test_login_endpoint_does_not_trust_unverified_cloudflare_headers(test_client):
    response = await test_client.post(
        "/api/v2/auth/login",
        json={},
        headers={
            "CF-Access-Jwt-Assertion": "unsigned-token",
            "CF-Access-Authenticated-User-Email": "attacker@example.com",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_cloudflare_exchange_requires_an_assertion_without_consuming_password_quota(
    test_client,
):
    response = await test_client.post("/api/v2/auth/cloudflare")

    assert response.status_code == 401
    assert response.json()["detail"] == "Cloudflare Access assertion missing"


@pytest.mark.asyncio
async def test_cloudflare_refresh_requires_fresh_matching_assertion(test_client, monkeypatch):
    import backend.src.api.routers.auth as auth_router

    principal = "operator@example.com"
    initial_expiry = datetime.now(UTC) + timedelta(minutes=10)
    verifier = AsyncMock()
    verifier.verify.return_value = VerifiedCloudflareIdentity(
        principal=principal,
        expires_at=initial_expiry,
        claims={"email": principal, "exp": int(initial_expiry.timestamp())},
    )
    monkeypatch.setattr(auth_router, "cloudflare_access_verifier", verifier)

    bootstrap = await test_client.post(
        "/api/v2/auth/cloudflare",
        headers={"CF-Access-Jwt-Assertion": "initial-assertion"},
    )
    assert bootstrap.status_code == 200
    token = bootstrap.json()["access_token"]

    missing = await test_client.post(
        "/api/v2/auth/refresh",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing.status_code == 401
    assert missing.json()["detail"] == "Cloudflare Access assertion required for refresh"

    mismatch_expiry = datetime.now(UTC) + timedelta(minutes=20)
    verifier.verify.return_value = VerifiedCloudflareIdentity(
        principal="different@example.com",
        expires_at=mismatch_expiry,
        claims={"email": "different@example.com", "exp": int(mismatch_expiry.timestamp())},
    )
    mismatch = await test_client.post(
        "/api/v2/auth/refresh",
        headers={
            "Authorization": f"Bearer {token}",
            "CF-Access-Jwt-Assertion": "mismatched-assertion",
        },
    )
    assert mismatch.status_code == 401

    refreshed_expiry = datetime.now(UTC) + timedelta(minutes=30)
    verifier.verify.return_value = VerifiedCloudflareIdentity(
        principal=principal,
        expires_at=refreshed_expiry,
        claims={"email": principal, "exp": int(refreshed_expiry.timestamp())},
    )
    refreshed = await test_client.post(
        "/api/v2/auth/refresh",
        headers={
            "Authorization": f"Bearer {token}",
            "CF-Access-Jwt-Assertion": "refreshed-assertion",
        },
    )
    assert refreshed.status_code == 200
    assert datetime.fromisoformat(refreshed.json()["expires_at"]) <= refreshed_expiry
