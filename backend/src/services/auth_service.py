"""
AuthService for LawnBerry Pi v2
Authentication service with shared operator credential and JWT tokens
"""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

try:
    import jwt
except ImportError:
    jwt = None

from ..models import (
    UserSession, SecurityContext, UserRole, AuthenticationMethod, 
    Permission, SessionStatus
)

logger = logging.getLogger(__name__)


class PasswordManager:
    """Simple password hashing and verification"""
    
    def __init__(self):
        self.salt = b"lawnberry_pi_v2_salt"  # In production, use random salt
    
    def hash_password(self, password: str) -> str:
        """Hash a password using SHA256"""
        password_bytes = password.encode('utf-8')
        return hashlib.pbkdf2_hmac('sha256', password_bytes, self.salt, 100000).hex()
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash"""
        return self.hash_password(plain_password) == hashed_password


class JWTManager:
    """JWT token management"""
    
    def __init__(self, secret_key: str = None):
        self.secret_key = secret_key or secrets.token_urlsafe(32)
        self.algorithm = "HS256"
        self.token_expiry_hours = 8
    
    def create_token(self, user_id: str, role: UserRole = UserRole.OPERATOR) -> str:
        """Create a simple token"""
        if jwt:
            now = datetime.now(timezone.utc)
            payload = {
                "user_id": user_id,
                "role": role.value,
                "iat": now,
                "exp": now + timedelta(hours=self.token_expiry_hours),
                "iss": "lawnberry-pi-v2"
            }
            return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        else:
            # Fallback simple token
            return f"{user_id}:{role.value}:{secrets.token_urlsafe(32)}"
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode a token"""
        if jwt:
            try:
                payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
                return payload
            except jwt.ExpiredSignatureError:
                logger.warning("JWT token expired")
                return None
            except jwt.InvalidTokenError as e:
                logger.warning(f"Invalid JWT token: {e}")
                return None
        else:
            # Simple token verification
            parts = token.split(":")
            if len(parts) == 3:
                return {"user_id": parts[0], "role": parts[1]}
            return None


class RateLimiter:
    """Rate limiting for login attempts"""
    
    def __init__(self):
        self.attempts: Dict[str, list] = {}  # IP -> list of attempt timestamps
        self.max_attempts = 5
        self.window_minutes = 15
        self.lockout_minutes = 30
    
    def is_rate_limited(self, ip_address: str) -> bool:
        """Check if IP is rate limited"""
        now = datetime.now(timezone.utc)
        
        if ip_address not in self.attempts:
            return False
        
        # Clean old attempts
        cutoff_time = now - timedelta(minutes=self.window_minutes)
        self.attempts[ip_address] = [
            attempt for attempt in self.attempts[ip_address]
            if attempt > cutoff_time
        ]
        
        # Check if rate limited
        return len(self.attempts[ip_address]) >= self.max_attempts
    
    def record_attempt(self, ip_address: str):
        """Record a login attempt"""
        now = datetime.now(timezone.utc)
        
        if ip_address not in self.attempts:
            self.attempts[ip_address] = []
        
        self.attempts[ip_address].append(now)
    
    def get_lockout_remaining(self, ip_address: str) -> Optional[int]:
        """Get remaining lockout time in minutes"""
        if ip_address not in self.attempts:
            return None
        
        if not self.attempts[ip_address]:
            return None
        
        last_attempt = max(self.attempts[ip_address])
        lockout_end = last_attempt + timedelta(minutes=self.lockout_minutes)
        now = datetime.now(timezone.utc)
        
        if now < lockout_end:
            return int((lockout_end - now).total_seconds() / 60)
        
        return None


class AuthService:
    """Main authentication service"""
    
    def __init__(self, operator_credential: str = "operator123"):
        # Managers
        self.password_manager = PasswordManager()
        self.jwt_manager = JWTManager()
        self.rate_limiter = RateLimiter()
        
        # Single shared operator credential (per constitutional requirement)
        self.operator_credential_hash = self._hash_credential(operator_credential)
        
        # Active sessions
        self.active_sessions: Dict[str, UserSession] = {}
        
        # Configuration
        self.session_timeout_hours = 8
        self.require_https = False  # Would be True in production
        self.audit_logging_enabled = True
        
    def _hash_credential(self, credential: str) -> str:
        """Hash the operator credential"""
        return self.password_manager.hash_password(credential)
    
    async def authenticate(self, credential: str, client_ip: str = None, 
                          user_agent: str = None) -> Optional[UserSession]:
        """Authenticate with shared operator credential"""
        
        # Check rate limiting
        if client_ip and self.rate_limiter.is_rate_limited(client_ip):
            lockout_remaining = self.rate_limiter.get_lockout_remaining(client_ip)
            logger.warning(f"Rate limited login attempt from {client_ip}, "
                          f"{lockout_remaining} minutes remaining")
            return None
        
        # Record attempt
        if client_ip:
            self.rate_limiter.record_attempt(client_ip)
        
        # Verify credential
        if not self.password_manager.verify_password(credential, self.operator_credential_hash):
            logger.warning(f"Failed login attempt from {client_ip}")
            return None
        
        # Create new session
        session = UserSession.create_operator_session(client_ip, user_agent)
        
        # Generate JWT token
        token = self.jwt_manager.create_token(session.user_id, session.security_context.role)
        session.security_context.credential_hash = self._hash_credential(credential)
        session.security_context.token_expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=self.session_timeout_hours)
        )
        
        # Store session
        self.active_sessions[session.session_id] = session
        
        # Audit log
        if self.audit_logging_enabled:
            session.update_activity(
                "login",
                method="shared_credential",
                ip_address=client_ip,
                user_agent=user_agent
            )
        
        logger.info(f"Successful login from {client_ip}, session {session.session_id}")
        return session
    
    async def verify_token(self, token: str) -> Optional[UserSession]:
        """Verify JWT token and return session"""
        payload = self.jwt_manager.verify_token(token)
        if not payload:
            return None
        
        user_id = payload.get("user_id")
        if not user_id:
            return None
        
        # Find active session for user
        for session in self.active_sessions.values():
            if (session.user_id == user_id and 
                session.status == SessionStatus.ACTIVE and
                not session.is_expired()):
                return session
        
        return None
    
    async def verify_session(self, session_id: str) -> Optional[UserSession]:
        """Verify session by ID"""
        if session_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[session_id]
        
        # Check if session is expired or idle
        if session.is_expired():
            await self.terminate_session(session_id, "expired")
            return None
        
        if session.is_idle():
            session.status = SessionStatus.IDLE
            logger.info(f"Session {session_id} marked as idle")
        
        return session
    
    async def terminate_session(self, session_id: str, reason: str = "user_logout") -> bool:
        """Terminate a session"""
        if session_id not in self.active_sessions:
            return False
        
        session = self.active_sessions[session_id]
        session.terminate(reason)
        
        # Audit log
        if self.audit_logging_enabled:
            session.update_activity("logout", metadata={"reason": reason})
        
        # Remove from active sessions
        del self.active_sessions[session_id]
        
        logger.info(f"Session {session_id} terminated: {reason}")
        return True
    
    async def extend_session(self, session_id: str, hours: int = 8) -> bool:
        """Extend session expiration"""
        if session_id not in self.active_sessions:
            return False
        
        session = self.active_sessions[session_id]
        session.extend_session(hours)
        
        # Update JWT expiration
        session.security_context.token_expires_at = (
            datetime.now(timezone.utc) + timedelta(hours=hours)
        )
        
        logger.info(f"Session {session_id} extended by {hours} hours")
        return True
    
    def check_permission(self, session: UserSession, permission: Permission) -> bool:
        """Check if session has required permission"""
        return session.security_context.has_permission(permission)
    
    def require_permission(self, permission: Permission):
        """Decorator to require specific permission"""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                # Extract session from request (would be implemented based on framework)
                session = kwargs.get('current_session')
                if not session or not self.check_permission(session, permission):
                    raise PermissionError(f"Permission required: {permission}")
                return await func(*args, **kwargs)
            return wrapper
        return decorator
    
    async def update_operator_credential(self, current_credential: str, 
                                       new_credential: str) -> bool:
        """Update the operator credential"""
        # Verify current credential
        if not self.password_manager.verify_password(current_credential, 
                                                    self.operator_credential_hash):
            logger.warning("Failed attempt to update operator credential")
            return False
        
        # Update credential
        self.operator_credential_hash = self._hash_credential(new_credential)
        
        # Invalidate all active sessions (force re-authentication)
        session_ids = list(self.active_sessions.keys())
        for session_id in session_ids:
            await self.terminate_session(session_id, "credential_changed")
        
        logger.info("Operator credential updated, all sessions terminated")
        return True
    
    async def cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        expired_sessions = []
        
        for session_id, session in self.active_sessions.items():
            if session.is_expired():
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            await self.terminate_session(session_id, "expired")
        
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
    
    async def get_active_sessions(self) -> Dict[str, Dict[str, Any]]:
        """Get information about active sessions"""
        sessions_info = {}
        
        for session_id, session in self.active_sessions.items():
            sessions_info[session_id] = {
                "user_id": session.user_id,
                "status": session.status,
                "created_at": session.created_at,
                "last_activity": session.last_activity,
                "expires_at": session.expires_at,
                "client_ip": session.client_ip,
                "connection_type": session.connection_type,
                "websocket_connections": len(session.websocket_connections),
                "activity_count": len(session.activity_log)
            }
        
        return sessions_info
    
    async def get_auth_statistics(self) -> Dict[str, Any]:
        """Get authentication statistics"""
        return {
            "active_sessions": len(self.active_sessions),
            "total_rate_limited_ips": len([
                ip for ip, attempts in self.rate_limiter.attempts.items()
                if len(attempts) >= self.rate_limiter.max_attempts
            ]),
            "session_timeout_hours": self.session_timeout_hours,
            "rate_limit_max_attempts": self.rate_limiter.max_attempts,
            "rate_limit_window_minutes": self.rate_limiter.window_minutes,
            "audit_logging_enabled": self.audit_logging_enabled
        }
    
    async def generate_api_key(self, session_id: str, description: str = "") -> Optional[str]:
        """Generate API key for programmatic access"""
        if session_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[session_id]
        
        # Generate API key
        api_key = f"lbpi_{secrets.token_urlsafe(32)}"
        
        # Log API key generation
        session.update_activity(
            "api_key_generated",
            metadata={"description": description}
        )
        
        logger.info(f"API key generated for session {session_id}")
        return api_key
    
    async def revoke_api_key(self, api_key: str) -> bool:
        """Revoke an API key"""
        # API key revocation logic would go here
        logger.info(f"API key revoked: {api_key[:12]}...")
        return True