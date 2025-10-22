import httpx
import pytest

from backend.src.main import app


@pytest.mark.asyncio
async def test_auth_login_rate_limit():
    transport = httpx.ASGITransport(app=app)
    headers = {"X-Client-Id": "rate-test-1"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Hit rate limit with valid credentials to isolate rate limiting from lockout
        for _ in range(3):
            resp = await client.post(
                "/api/v2/auth/login",
                json={"credential": "ok"},
                headers=headers,
            )
            assert resp.status_code == 200

        # Next request should be rate limited
        resp = await client.post(
            "/api/v2/auth/login",
            json={"credential": "ok"},
            headers=headers,
        )
        assert resp.status_code == 429
        # Retry-After header is recommended
        assert "retry-after" in {k.lower(): v for k, v in resp.headers.items()}


@pytest.mark.asyncio
async def test_auth_login_lockout_on_failed_attempts():
    transport = httpx.ASGITransport(app=app)
    headers = {"X-Client-Id": "lockout-test-1"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Three failed attempts (empty credential) triggers lockout
        for _ in range(3):
            resp = await client.post(
                "/api/v2/auth/login",
                json={"credential": ""},
                headers=headers,
            )
            assert resp.status_code == 401

        # Now even with correct credential, expect lockout (429)
        resp = await client.post(
            "/api/v2/auth/login",
            json={"credential": "ok"},
            headers=headers,
        )
        assert resp.status_code == 429
        assert "retry-after" in {k.lower(): v for k, v in resp.headers.items()}
