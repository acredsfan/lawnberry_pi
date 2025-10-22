import httpx
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_authentication_security_levels_enforced():
    from backend.src.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Default level should be password_only
        resp = await client.get("/api/v2/settings/security")
        assert resp.status_code == 200
        sec = resp.json()
        assert sec["level"] in {
            "password_only",
            "password_totp",
            "google_auth",
            "cloudflare_tunnel_auth",
        }

        # Update to password_totp
        put = await client.put(
            "/api/v2/settings/security",
            json={"level": "password_totp", "totp_digits": 6},
        )
        assert put.status_code == 200
        body = put.json()
        assert body["level"] == "password_totp"
        assert body["totp_digits"] == 6

        # Update to google_auth with partial config
        put2 = await client.put(
            "/api/v2/settings/security",
            json={"level": "google_auth", "google_client_id": "id"},
        )
        assert put2.status_code == 200
        body2 = put2.json()
        assert body2["level"] == "google_auth"
        assert body2["google_client_id"] == "id"
