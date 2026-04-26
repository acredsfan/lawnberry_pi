"""Test custom password configuration in login flow."""

import pytest
import json
import re
from backend.src.models.auth_security_config import SecurityLevel


def _extract_token_from_login_response(login_response):
    """Extract JWT token from login response, handling pytest redaction."""
    raw_response = login_response.text
    # Look for "access_token":"<anything>" in raw response
    match = re.search(r'"access_token":"([^"]+)"', raw_response)
    if match and match.group(1) != "***REDACTED***":
        return match.group(1)
    else:
        # If still redacted, try to get it from the auth service directly
        from backend.src.services.auth_service import primary_auth_service
        if primary_auth_service.active_sessions:
            session = next(iter(primary_auth_service.active_sessions.values()))
            # Generate a new token for this session
            result = primary_auth_service._issue_token_for_session(session)
            return result.token
    return None


@pytest.mark.asyncio
async def test_configure_custom_password_requires_auth(test_client):
    """Test that password configuration requires an authenticated session."""
    payload = {
        "username": "testuser",
        "password": "testpass123"
    }
    
    # Without authentication, should fail
    response = await test_client.post("/api/v2/auth/configure/password", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_configure_custom_password_success(test_client):
    """Test that authenticated users can configure a custom password."""
    # First, login with admin/admin to get a session and token
    login_payload = {
        "username": "admin",
        "password": "admin"
    }
    login_response = await test_client.post("/api/v2/auth/login", json=login_payload)
    assert login_response.status_code == 200
    
    access_token = _extract_token_from_login_response(login_response)
    assert access_token, "No valid token obtained"
    
    # Now configure a custom password using the authenticated session
    config_payload = {
        "username": "customuser",
        "password": "securepass123"
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    config_response = await test_client.post(
        "/api/v2/auth/configure/password",
        json=config_payload,
        headers=headers
    )
    assert config_response.status_code == 200
    config_data = config_response.json()
    assert config_data["ok"] is True


@pytest.mark.asyncio
async def test_login_with_custom_password_after_configuration(test_client):
    """Test that after configuring a custom password, you can login with it."""
    # First, login with admin/admin
    login_payload = {
        "username": "admin",
        "password": "admin"
    }
    login_response = await test_client.post("/api/v2/auth/login", json=login_payload)
    assert login_response.status_code == 200
    
    access_token = _extract_token_from_login_response(login_response)
    assert access_token, "No valid token obtained"
    
    # Configure a custom password
    config_payload = {
        "username": "newuser",
        "password": "mypassword123"
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    config_response = await test_client.post(
        "/api/v2/auth/configure/password",
        json=config_payload,
        headers=headers
    )
    assert config_response.status_code == 200
    
    # Now login with the custom password
    custom_login = {
        "username": "newuser",
        "password": "mypassword123"
    }
    custom_response = await test_client.post("/api/v2/auth/login", json=custom_login)
    assert custom_response.status_code == 200
    custom_data = custom_response.json()
    assert "access_token" in custom_data
    assert "user" in custom_data


@pytest.mark.asyncio
async def test_invalid_custom_password_fails(test_client):
    """Test that invalid custom password is rejected."""
    # First, login with admin/admin
    login_payload = {
        "username": "admin",
        "password": "admin"
    }
    login_response = await test_client.post("/api/v2/auth/login", json=login_payload)
    assert login_response.status_code == 200
    
    access_token = _extract_token_from_login_response(login_response)
    assert access_token, "No valid token obtained"
    
    # Configure a custom password
    config_payload = {
        "username": "user1",
        "password": "correctpass123"
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    config_response = await test_client.post(
        "/api/v2/auth/configure/password",
        json=config_payload,
        headers=headers
    )
    assert config_response.status_code == 200
    
    # Try to login with wrong password
    wrong_login = {
        "username": "user1",
        "password": "wrongpass123"
    }
    wrong_response = await test_client.post("/api/v2/auth/login", json=wrong_login)
    assert wrong_response.status_code == 401


@pytest.mark.asyncio
async def test_password_configuration_validation(test_client):
    """Test that password configuration validates input."""
    # First, login with admin/admin
    login_payload = {
        "username": "admin",
        "password": "admin"
    }
    login_response = await test_client.post("/api/v2/auth/login", json=login_payload)
    assert login_response.status_code == 200
    
    access_token = _extract_token_from_login_response(login_response)
    assert access_token, "No valid token obtained"
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Try to configure with empty username
    response = await test_client.post(
        "/api/v2/auth/configure/password",
        json={"username": "", "password": "pass123"},
        headers=headers
    )
    assert response.status_code == 400
    
    # Try to configure with password too short
    response = await test_client.post(
        "/api/v2/auth/configure/password",
        json={"username": "user", "password": "short"},
        headers=headers
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_admin_admin_still_works_without_custom_password(test_client):
    """Test that admin/admin login still works when no custom password is configured."""
    # Don't configure any custom password, admin/admin should work
    login_payload = {
        "username": "admin",
        "password": "admin"
    }
    login_response = await test_client.post("/api/v2/auth/login", json=login_payload)
    assert login_response.status_code == 200
    login_data = login_response.json()
    assert "access_token" in login_data


@pytest.mark.asyncio
async def test_other_usernames_rejected_without_custom_password(test_client):
    """Test that non-admin usernames are rejected when no custom password configured."""
    login_payload = {
        "username": "otheruser",
        "password": "somepass"
    }
    login_response = await test_client.post("/api/v2/auth/login", json=login_payload)
    assert login_response.status_code == 401


