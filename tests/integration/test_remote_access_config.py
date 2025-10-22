import httpx
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_remote_access_configurations_documented_and_toggleable():
    from backend.src.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Default should be disabled
        resp = await client.get("/api/v2/settings/remote-access")
        assert resp.status_code == 200
        cfg = resp.json()
        assert cfg["enabled"] is False
        assert cfg["provider"] in {"disabled", "cloudflare", "ngrok", "custom"}

        # Enable Cloudflare provider config (scaffold doesn't start tunnel, just stores)
        put = await client.put(
            "/api/v2/settings/remote-access",
            json={
                "provider": "cloudflare",
                "enabled": True,
                "cloudflare": {
                    "tunnel_name": "lb-tun",
                    "hostname": "mower.example.com",
                },
            },
        )
        assert put.status_code == 200
        body = put.json()
        assert body["enabled"] is True
        assert body["provider"] == "cloudflare"
        assert body["cloudflare"]["tunnel_name"] == "lb-tun"

        # Switch to ngrok, remains enabled
        put2 = await client.put(
            "/api/v2/settings/remote-access",
            json={
                "provider": "ngrok",
                "enabled": True,
                "ngrok": {"region": "us"},
            },
        )
        assert put2.status_code == 200
        body2 = put2.json()
        assert body2["provider"] == "ngrok"
        assert body2["enabled"] is True

        # Disable remote access
        put3 = await client.put(
            "/api/v2/settings/remote-access",
            json={"enabled": False, "provider": "disabled"},
        )
        assert put3.status_code == 200
        body3 = put3.json()
        assert body3["enabled"] is False
        assert body3["provider"] == "disabled"
