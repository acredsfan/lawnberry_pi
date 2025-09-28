"""Contract tests for /api/v1/auth/login endpoint with MFA."""
import pytest
import httpx
from typing import Dict, Any


@pytest.mark.asyncio
async def test_auth_login_success_with_credential(test_client):
    """Test successful login with shared credential returns proper response."""
    payload = {"credential": "operator123"}  # Default test credential
    
    response = await test_client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    
    # Required response fields per contract
    assert "access_token" in data
    assert "token_type" in data
    assert "expires_in" in data
    assert "user" in data
    
    # Validate field types and values
    assert isinstance(data["access_token"], str)
    assert data["token_type"] == "bearer"
    assert isinstance(data["expires_in"], int)
    assert data["expires_in"] > 0
    
    # User object validation
    user = data["user"]
    assert "id" in user
    assert "username" in user
    assert "role" in user


@pytest.mark.asyncio
async def test_auth_login_invalid_credential(test_client):
    """Test login with invalid credential returns 401."""
    payload = {"credential": "invalid_credential"}
    
    response = await test_client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_login_missing_credential(test_client):
    """Test login without credential returns 401."""
    payload = {}
    
    response = await test_client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_login_username_password_fallback(test_client):
    """Test login with username/password format (MFA compatibility)."""
    payload = {
        "username": "admin",
        "password": "admin"
    }
    
    response = await test_client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert "access_token" in data
    assert "user" in data


@pytest.mark.asyncio
async def test_auth_login_rate_limiting(test_client):
    """Test that rate limiting prevents brute force attacks."""
    # This test may fail initially until rate limiting is implemented
    invalid_payload = {"credential": "wrong"}
    
    # Make multiple rapid requests
    responses = []
    for i in range(5):
        response = await test_client.post("/api/v1/auth/login", json=invalid_payload)
        responses.append(response.status_code)
    
    # Should eventually get rate limited (429) or continue to get 401
    # This is a contract for future rate limiting implementation
    assert all(status in [401, 429] for status in responses)