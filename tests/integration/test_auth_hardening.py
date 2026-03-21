import httpx
import pytest

from backend.src.main import app


@pytest.mark.asyncio
async def test_auth_login_repeated_successes_are_allowed():
    transport = httpx.ASGITransport(app=app)
    headers = {"X-Client-Id": "rate-test-1"}
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Successful re-authentication should not trigger the brute-force protections.
        for _ in range(4):
            resp = await client.post(
                "/api/v2/auth/login",
                json={"credential": "ok"},
                headers=headers,
            )
            assert resp.status_code == 200


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
