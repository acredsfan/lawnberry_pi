"""
Authentication and Authorization
JWT-based authentication with role-based access control.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import hashlib
import secrets
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from passlib.context import CryptContext


# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


class AuthManager:
    """Authentication and authorization manager"""
    
    def __init__(self, auth_config):
        self.logger = logging.getLogger(__name__)
        self.config = auth_config
        self.users_db: Dict[str, Dict[str, Any]] = {}
        self.active_tokens: Dict[str, Dict[str, Any]] = {}
        
    async def initialize(self):
        """Initialize authentication system"""
        # Create default admin user
        admin_password_hash = pwd_context.hash(self.config.admin_password)
        self.users_db[self.config.admin_username] = {
            'username': self.config.admin_username,
            'password_hash': admin_password_hash,
            'role': 'admin',
            'created_at': datetime.now(),
            'last_login': None,
            'active': True
        }
        
        self.logger.info("Authentication system initialized")
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password against hash"""
        return pwd_context.verify(plain_password, hashed_password)
    
    def get_password_hash(self, password: str) -> str:
        """Generate password hash"""
        return pwd_context.hash(password)
    
    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate user credentials"""
        user = self.users_db.get(username)
        if not user or not user.get('active', False):
            return None
        
        if not self.verify_password(password, user['password_hash']):
            return None
        
        # Update last login
        user['last_login'] = datetime.now()
        
        return {
            'username': user['username'],
            'role': user['role'],
            'last_login': user['last_login']
        }
    
    def create_access_token(self, data: Dict[str, Any]) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(hours=self.config.jwt_expiration_hours)
        to_encode.update({"exp": expire, "iat": datetime.utcnow()})
        
        token = jwt.encode(
            to_encode, 
            self.config.jwt_secret_key, 
            algorithm=self.config.jwt_algorithm
        )
        
        # Store active token
        token_id = secrets.token_hex(16)
        self.active_tokens[token_id] = {
            'token': token,
            'user': data.get('sub'),
            'created_at': datetime.utcnow(),
            'expires_at': expire
        }
        
        return token
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token"""
        try:
            payload = jwt.decode(
                token,
                self.config.jwt_secret_key,
                algorithms=[self.config.jwt_algorithm]
            )
            
            username: str = payload.get("sub")
            if username is None:
                return None
            
            # Check if user still exists and is active
            user = self.users_db.get(username)
            if not user or not user.get('active', False):
                return None
            
            return {
                'username': username,
                'role': user['role'],
                'exp': payload.get('exp'),
                'iat': payload.get('iat')
            }
            
        except jwt.ExpiredSignatureError:
            self.logger.warning("Token expired")
            return None
        except jwt.JWTError as e:
            self.logger.warning(f"Token validation error: {e}")
            return None
    
    def revoke_token(self, token: str) -> bool:
        """Revoke an active token"""
        # Remove from active tokens
        to_remove = []
        for token_id, token_data in self.active_tokens.items():
            if token_data['token'] == token:
                to_remove.append(token_id)
        
        for token_id in to_remove:
            del self.active_tokens[token_id]
        
        return len(to_remove) > 0
    
    def cleanup_expired_tokens(self):
        """Remove expired tokens from active tokens"""
        current_time = datetime.utcnow()
        expired_tokens = []
        
        for token_id, token_data in self.active_tokens.items():
            if current_time > token_data['expires_at']:
                expired_tokens.append(token_id)
        
        for token_id in expired_tokens:
            del self.active_tokens[token_id]
        
        if expired_tokens:
            self.logger.debug(f"Cleaned up {len(expired_tokens)} expired tokens")
    
    def create_user(self, username: str, password: str, role: str = "user") -> bool:
        """Create a new user"""
        if username in self.users_db:
            return False
        
        password_hash = self.get_password_hash(password)
        self.users_db[username] = {
            'username': username,
            'password_hash': password_hash,
            'role': role,
            'created_at': datetime.now(),
            'last_login': None,
            'active': True
        }
        
        self.logger.info(f"Created user: {username} with role: {role}")
        return True
    
    def update_user_password(self, username: str, new_password: str) -> bool:
        """Update user password"""
        user = self.users_db.get(username)
        if not user:
            return False
        
        user['password_hash'] = self.get_password_hash(new_password)
        self.logger.info(f"Updated password for user: {username}")
        return True
    
    def deactivate_user(self, username: str) -> bool:
        """Deactivate a user"""
        user = self.users_db.get(username)
        if not user:
            return False
        
        user['active'] = False
        self.logger.info(f"Deactivated user: {username}")
        return True
    
    def get_user_info(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user information (without password hash)"""
        user = self.users_db.get(username)
        if not user:
            return None
        
        return {
            'username': user['username'],
            'role': user['role'],
            'created_at': user['created_at'],
            'last_login': user['last_login'],
            'active': user['active']
        }
    
    def has_permission(self, user_role: str, required_permission: str) -> bool:
        """Check if user role has required permission"""
        role_permissions = {
            'admin': ['read', 'write', 'delete', 'manage'],
            'operator': ['read', 'write'],
            'viewer': ['read'],
            'user': ['read']
        }
        
        permissions = role_permissions.get(user_role, [])
        return required_permission in permissions


# Global auth manager instance
auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    """Get global auth manager instance"""
    global auth_manager
    if auth_manager is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication system not initialized"
        )
    return auth_manager


def set_auth_manager(manager: AuthManager):
    """Set global auth manager instance"""
    global auth_manager
    auth_manager = manager


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """Get current authenticated user"""
    auth_mgr = get_auth_manager()
    
    if not auth_mgr.config.enabled:
        # Authentication disabled - return default user
        return {
            'username': 'anonymous',
            'role': 'admin',
            'exp': None,
            'iat': None
        }
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = auth_mgr.verify_token(credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


def require_permission(permission: str):
    """Decorator factory for permission-based access control"""
    def permission_dependency(current_user: Dict[str, Any] = Depends(get_current_user)):
        auth_mgr = get_auth_manager()
        
        if not auth_mgr.config.enabled:
            return current_user
        
        if not auth_mgr.has_permission(current_user.get('role', ''), permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {permission}"
            )
        
        return current_user
    
    return permission_dependency


def require_admin(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Require admin role"""
    if current_user.get('role') != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


# Convenience functions
def get_current_user_optional():
    """Get current user if authenticated, None otherwise"""
    try:
        return get_current_user()
    except HTTPException:
        return None


# Login/logout models
from pydantic import BaseModel

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"

class PasswordChange(BaseModel):
    current_password: str
    new_password: str
