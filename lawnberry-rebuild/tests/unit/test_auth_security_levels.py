"""
Unit tests for enhanced authentication security levels
Tests the configurable authentication system with multiple security levels
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone, timedelta

from backend.src.services.auth_service import auth_service, AuthenticationError
from backend.src.models.auth_security_config import (
    AuthSecurityConfig, SecurityLevel, TOTPConfig, GoogleAuthConfig
)


class TestAuthSecurityLevels:
    """Test authentication security levels configuration and enforcement."""
    
    @pytest.fixture
    def auth_config_password(self):
        """Basic password-only authentication config."""
        return AuthSecurityConfig(
            security_level=SecurityLevel.PASSWORD,
            password_hash="$2b$12$test_hash",
            require_password_change=False,
            session_timeout_minutes=60
        )
    
    @pytest.fixture
    def auth_config_totp(self):
        """TOTP-enabled authentication config."""
        return AuthSecurityConfig(
            security_level=SecurityLevel.TOTP,
            password_hash="$2b$12$test_hash",
            totp_config=TOTPConfig(
                secret="JBSWY3DPEHPK3PXP",
                enabled=True,
                backup_codes=["123456", "789012"]
            ),
            require_password_change=False,
            session_timeout_minutes=30
        )
    
    @pytest.fixture
    def auth_config_google(self):
        """Google OAuth authentication config."""
        return AuthSecurityConfig(
            security_level=SecurityLevel.GOOGLE_OAUTH,
            google_auth_config=GoogleAuthConfig(
                client_id="test_client_id.googleusercontent.com",
                enabled=True,
                allowed_domains=["example.com"]
            ),
            session_timeout_minutes=15
        )
    
    @pytest.fixture
    def auth_config_tunnel(self):
        """Cloudflare tunnel authentication config."""
        return AuthSecurityConfig(
            security_level=SecurityLevel.TUNNEL_AUTH,
            tunnel_auth_enabled=True,
            required_headers={"CF-Access-Authenticated-User-Email": "user@example.com"},
            session_timeout_minutes=120
        )

    def test_password_level_validation(self, auth_config_password):
        """Test password-only security level validation."""
        assert auth_config_password.security_level == SecurityLevel.PASSWORD
        assert auth_config_password.password_required()
        assert not auth_config_password.totp_required()
        assert not auth_config_password.google_auth_required()
        assert not auth_config_password.tunnel_auth_required()

    def test_totp_level_validation(self, auth_config_totp):
        """Test TOTP security level validation."""
        assert auth_config_totp.security_level == SecurityLevel.TOTP
        assert auth_config_totp.password_required()
        assert auth_config_totp.totp_required()
        assert not auth_config_totp.google_auth_required()
        assert not auth_config_totp.tunnel_auth_required()

    def test_google_oauth_level_validation(self, auth_config_google):
        """Test Google OAuth security level validation."""
        assert auth_config_google.security_level == SecurityLevel.GOOGLE_OAUTH
        assert not auth_config_google.password_required()
        assert not auth_config_google.totp_required()
        assert auth_config_google.google_auth_required()
        assert not auth_config_google.tunnel_auth_required()

    def test_tunnel_auth_level_validation(self, auth_config_tunnel):
        """Test tunnel authentication level validation."""
        assert auth_config_tunnel.security_level == SecurityLevel.TUNNEL_AUTH
        assert not auth_config_tunnel.password_required()
        assert not auth_config_tunnel.totp_required()
        assert not auth_config_tunnel.google_auth_required()
        assert auth_config_tunnel.tunnel_auth_required()

    @pytest.mark.asyncio
    async def test_password_authentication_success(self, auth_config_password):
        """Test successful password authentication."""
        with patch.object(auth_service, 'config', auth_config_password):
            with patch('bcrypt.checkpw', return_value=True):
                result = await auth_service.authenticate_password("admin", "test_password")
                
                assert result is not None
                assert result.username == "admin"
                assert result.security_level == SecurityLevel.PASSWORD
                assert result.expires_at > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_password_authentication_failure(self, auth_config_password):
        """Test failed password authentication."""
        with patch.object(auth_service, 'config', auth_config_password):
            with patch('bcrypt.checkpw', return_value=False):
                with pytest.raises(AuthenticationError, match="Invalid credentials"):
                    await auth_service.authenticate_password("admin", "wrong_password")

    @pytest.mark.asyncio
    async def test_totp_authentication_success(self, auth_config_totp):
        """Test successful TOTP authentication."""
        with patch.object(auth_service, 'config', auth_config_totp):
            with patch('bcrypt.checkpw', return_value=True):
                with patch('pyotp.TOTP.verify', return_value=True):
                    result = await auth_service.authenticate_totp("admin", "test_password", "123456")
                    
                    assert result is not None
                    assert result.username == "admin"
                    assert result.security_level == SecurityLevel.TOTP
                    assert result.mfa_verified is True

    @pytest.mark.asyncio
    async def test_totp_authentication_invalid_code(self, auth_config_totp):
        """Test TOTP authentication with invalid code."""
        with patch.object(auth_service, 'config', auth_config_totp):
            with patch('bcrypt.checkpw', return_value=True):
                with patch('pyotp.TOTP.verify', return_value=False):
                    with pytest.raises(AuthenticationError, match="Invalid TOTP code"):
                        await auth_service.authenticate_totp("admin", "test_password", "000000")

    @pytest.mark.asyncio
    async def test_totp_backup_code_authentication(self, auth_config_totp):
        """Test authentication with TOTP backup code."""
        with patch.object(auth_service, 'config', auth_config_totp):
            with patch('bcrypt.checkpw', return_value=True):
                result = await auth_service.authenticate_totp("admin", "test_password", "123456")
                
                assert result is not None
                assert result.backup_code_used is True
                # Backup code should be marked as used
                assert "123456" not in auth_config_totp.totp_config.backup_codes

    @pytest.mark.asyncio
    async def test_google_oauth_authentication_success(self, auth_config_google):
        """Test successful Google OAuth authentication."""
        mock_token_info = {
            "aud": "test_client_id.googleusercontent.com",
            "email": "user@example.com",
            "email_verified": True,
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "iss": "https://accounts.google.com",
            "sub": "12345678901234567890"
        }
        
        with patch.object(auth_service, 'config', auth_config_google):
            with patch('google.auth.transport.requests.Request'):
                with patch('google.oauth2.id_token.verify_oauth2_token', return_value=mock_token_info):
                    result = await auth_service.authenticate_google_oauth("mock_id_token")
                    
                    assert result is not None
                    assert result.username == "user@example.com"
                    assert result.security_level == SecurityLevel.GOOGLE_OAUTH
                    assert result.oauth_provider == "google"

    @pytest.mark.asyncio
    async def test_google_oauth_domain_restriction(self, auth_config_google):
        """Test Google OAuth domain restriction enforcement."""
        mock_token_info = {
            "aud": "test_client_id.googleusercontent.com",
            "email": "user@unauthorized.com",  # Not in allowed domains
            "email_verified": True,
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "iss": "https://accounts.google.com",
            "sub": "12345678901234567890"
        }
        
        with patch.object(auth_service, 'config', auth_config_google):
            with patch('google.auth.transport.requests.Request'):
                with patch('google.oauth2.id_token.verify_oauth2_token', return_value=mock_token_info):
                    with pytest.raises(AuthenticationError, match="Domain not allowed"):
                        await auth_service.authenticate_google_oauth("mock_id_token")

    @pytest.mark.asyncio
    async def test_tunnel_authentication_success(self, auth_config_tunnel):
        """Test successful tunnel authentication."""
        headers = {
            "CF-Access-Authenticated-User-Email": "user@example.com",
            "CF-Ray": "mock-ray-id"
        }
        
        with patch.object(auth_service, 'config', auth_config_tunnel):
            result = await auth_service.authenticate_tunnel(headers)
            
            assert result is not None
            assert result.username == "user@example.com"
            assert result.security_level == SecurityLevel.TUNNEL_AUTH
            assert result.tunnel_authenticated is True

    @pytest.mark.asyncio
    async def test_tunnel_authentication_missing_headers(self, auth_config_tunnel):
        """Test tunnel authentication with missing required headers."""
        headers = {}  # Missing required headers
        
        with patch.object(auth_service, 'config', auth_config_tunnel):
            with pytest.raises(AuthenticationError, match="Required tunnel headers missing"):
                await auth_service.authenticate_tunnel(headers)

    @pytest.mark.asyncio
    async def test_session_timeout_enforcement(self, auth_config_password):
        """Test session timeout enforcement."""
        # Create expired session
        expired_session = Mock()
        expired_session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        expired_session.username = "admin"
        
        with patch.object(auth_service, 'config', auth_config_password):
            is_valid = await auth_service.validate_session(expired_session)
            assert not is_valid

    @pytest.mark.asyncio
    async def test_security_level_upgrade_required(self):
        """Test that upgrading security level invalidates existing sessions."""
        # Create session with lower security level
        low_sec_session = Mock()
        low_sec_session.security_level = SecurityLevel.PASSWORD
        low_sec_session.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        
        # Config requires higher security
        high_sec_config = AuthSecurityConfig(
            security_level=SecurityLevel.TOTP,
            password_hash="$2b$12$test_hash",
            totp_config=TOTPConfig(secret="JBSWY3DPEHPK3PXP", enabled=True)
        )
        
        with patch.object(auth_service, 'config', high_sec_config):
            is_valid = await auth_service.validate_session(low_sec_session)
            assert not is_valid

    @pytest.mark.asyncio
    async def test_concurrent_session_limit(self, auth_config_password):
        """Test concurrent session limits."""
        auth_config_password.max_concurrent_sessions = 2
        
        with patch.object(auth_service, 'config', auth_config_password):
            # Create maximum allowed sessions
            session1 = await auth_service.create_session("admin", SecurityLevel.PASSWORD)
            session2 = await auth_service.create_session("admin", SecurityLevel.PASSWORD)
            
            # Third session should fail or invalidate oldest
            with patch.object(auth_service, 'active_sessions', {"admin": [session1, session2]}):
                session3 = await auth_service.create_session("admin", SecurityLevel.PASSWORD)
                
                # Should have exactly max_concurrent_sessions
                assert len(auth_service.active_sessions.get("admin", [])) <= 2

    def test_security_level_hierarchy(self):
        """Test security level hierarchy validation."""
        # Test security level ordering
        assert SecurityLevel.PASSWORD < SecurityLevel.TOTP
        assert SecurityLevel.TOTP < SecurityLevel.GOOGLE_OAUTH
        assert SecurityLevel.GOOGLE_OAUTH < SecurityLevel.TUNNEL_AUTH
        
        # Test that higher levels meet lower requirements
        config = AuthSecurityConfig(security_level=SecurityLevel.TUNNEL_AUTH)
        assert config.meets_security_level(SecurityLevel.PASSWORD)
        assert config.meets_security_level(SecurityLevel.TOTP)
        assert config.meets_security_level(SecurityLevel.GOOGLE_OAUTH)
        assert config.meets_security_level(SecurityLevel.TUNNEL_AUTH)

    @pytest.mark.asyncio
    async def test_auth_config_update_invalidates_sessions(self, auth_config_password):
        """Test that updating auth config invalidates existing sessions."""
        with patch.object(auth_service, 'config', auth_config_password):
            # Create session
            session = await auth_service.create_session("admin", SecurityLevel.PASSWORD)
            
            # Update config
            new_config = AuthSecurityConfig(
                security_level=SecurityLevel.TOTP,
                password_hash="$2b$12$new_hash",
                totp_config=TOTPConfig(secret="NEWSECRET123", enabled=True)
            )
            
            await auth_service.update_config(new_config)
            
            # Old session should be invalidated
            is_valid = await auth_service.validate_session(session)
            assert not is_valid

    @pytest.mark.asyncio
    async def test_rate_limiting_authentication(self, auth_config_password):
        """Test authentication rate limiting."""
        with patch.object(auth_service, 'config', auth_config_password):
            with patch('bcrypt.checkpw', return_value=False):
                # Simulate multiple failed attempts
                for _ in range(5):
                    with pytest.raises(AuthenticationError):
                        await auth_service.authenticate_password("admin", "wrong_password")
                
                # Next attempt should be rate limited
                with pytest.raises(AuthenticationError, match="Too many attempts"):
                    await auth_service.authenticate_password("admin", "wrong_password")

    def test_backup_code_generation(self):
        """Test TOTP backup code generation."""
        config = AuthSecurityConfig(
            security_level=SecurityLevel.TOTP,
            totp_config=TOTPConfig(secret="JBSWY3DPEHPK3PXP", enabled=True)
        )
        
        backup_codes = config.generate_backup_codes(count=10)
        
        assert len(backup_codes) == 10
        assert all(len(code) == 6 and code.isdigit() for code in backup_codes)
        assert len(set(backup_codes)) == 10  # All unique

    @pytest.mark.asyncio
    async def test_security_audit_logging(self, auth_config_totp):
        """Test that security events are properly logged."""
        with patch.object(auth_service, 'config', auth_config_totp):
            with patch('bcrypt.checkpw', return_value=True):
                with patch('pyotp.TOTP.verify', return_value=True):
                    with patch.object(auth_service, '_log_security_event') as mock_log:
                        await auth_service.authenticate_totp("admin", "password", "123456")
                        
                        # Should log successful authentication
                        mock_log.assert_called_with(
                            event_type="authentication_success",
                            username="admin",
                            security_level=SecurityLevel.TOTP,
                            details={"mfa_verified": True}
                        )


class TestAuthServiceIntegration:
    """Integration tests for auth service with different configurations."""
    
    @pytest.mark.asyncio
    async def test_auth_service_initialization(self):
        """Test auth service initialization with different configs."""
        config = AuthSecurityConfig(
            security_level=SecurityLevel.PASSWORD,
            password_hash="$2b$12$test_hash"
        )
        
        await auth_service.initialize(config)
        
        assert auth_service.config == config
        assert auth_service.initialized is True

    @pytest.mark.asyncio
    async def test_auth_service_config_validation(self):
        """Test auth service config validation."""
        # Invalid config - TOTP level without TOTP config
        invalid_config = AuthSecurityConfig(
            security_level=SecurityLevel.TOTP,
            password_hash="$2b$12$test_hash"
            # Missing totp_config
        )
        
        with pytest.raises(ValueError, match="TOTP configuration required"):
            await auth_service.initialize(invalid_config)

    @pytest.mark.asyncio
    async def test_end_to_end_authentication_flow(self):
        """Test complete authentication flow from config to session."""
        config = AuthSecurityConfig(
            security_level=SecurityLevel.TOTP,
            password_hash="$2b$12$LQV3c7yqbczUQWNKlbZp5OXYgUvyYKNfkU9IvTyUkvqhzMBw5RpT6",  # "password"
            totp_config=TOTPConfig(
                secret="JBSWY3DPEHPK3PXP",
                enabled=True,
                backup_codes=["123456", "789012"]
            )
        )
        
        await auth_service.initialize(config)
        
        with patch('pyotp.TOTP.verify', return_value=True):
            # Authenticate with TOTP
            session = await auth_service.authenticate_totp("admin", "password", "123456")
            
            assert session is not None
            assert session.username == "admin"
            assert session.security_level == SecurityLevel.TOTP
            
            # Validate session
            is_valid = await auth_service.validate_session(session)
            assert is_valid
            
            # Logout
            await auth_service.logout(session.session_id)
            
            # Session should be invalidated
            is_valid = await auth_service.validate_session(session)
            assert not is_valid