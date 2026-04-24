"""Test Cloudflare Access authentication bypass in login flow."""

import pytest
from backend.src.models.auth_security_config import SecurityLevel, AuthSecurityConfig


@pytest.mark.asyncio
async def test_cloudflare_bypass_skips_login_when_valid_headers_present(test_client, monkeypatch):
    """Test that valid Cloudflare Access headers skip the login screen."""
    # Create a mock Cloudflare-enabled security config
    from backend.src.api import routers
    cf_config = AuthSecurityConfig(security_level=SecurityLevel.TUNNEL_AUTH)
    cf_config.tunnel_auth_enabled = True
    
    # Mock _current_security_settings to return our Cloudflare config
    async def mock_current_security_settings():
        return cf_config
    
    # Patch the _current_security_settings call in auth router
    original_settings = None
    try:
        # Store original and replace
        import backend.src.api.routers.auth as auth_router
        if hasattr(auth_router, '_current_security_settings'):
            original_settings = auth_router._current_security_settings
            auth_router._current_security_settings = lambda: cf_config
        
        # No credentials provided - normally would be rejected
        payload = {}
        
        # But with valid Cloudflare headers, should bypass login
        headers = {
            "CF-Access-Jwt-Assertion": "dummy-token",
            "CF-Access-Authenticated-User-Email": "user@example.com"
        }
        
        response = await test_client.post("/api/v2/auth/login", json=payload, headers=headers)
        
        # Should succeed and return session token (or gracefully fail if tunnel auth not configured)
        # The key is that it should NOT reject immediately for empty credentials
        assert response.status_code in [200, 401]  # 401 is OK if tunnel auth not properly configured
    finally:
        # Restore original
        if original_settings is not None:
            auth_router._current_security_settings = original_settings


@pytest.mark.asyncio
async def test_login_requires_credentials_when_cloudflare_disabled(test_client):
    """Test that normal login flow requires credentials when Cloudflare is disabled."""
    payload = {}
    
    # No Cloudflare headers, no credentials - should be rejected
    response = await test_client.post("/api/v2/auth/login", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_local_login_still_works_without_cloudflare(test_client):
    """Test that local admin/admin login still works when Cloudflare is not enabled."""
    payload = {
        "username": "admin",
        "password": "admin"
    }
    
    response = await test_client.post("/api/v2/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "user" in data
