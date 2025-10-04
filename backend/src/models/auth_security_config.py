from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class SecurityLevel(int, Enum):
    PASSWORD = 1
    TOTP = 2
    GOOGLE_OAUTH = 3
    TUNNEL_AUTH = 4


class TOTPConfig(BaseModel):
    secret: str
    enabled: bool = True
    digits: int = 6
    period: int = 30
    backup_codes: List[str] = Field(default_factory=list)


class GoogleAuthConfig(BaseModel):
    client_id: str
    enabled: bool = True
    allowed_domains: List[str] = Field(default_factory=list)


class AuthSecurityConfig(BaseModel):
    security_level: SecurityLevel = SecurityLevel.PASSWORD
    password_hash: Optional[str] = None
    session_timeout_minutes: int = 60
    require_password_change: bool = False
    max_concurrent_sessions: int = 1
    
    # Optional provider configs
    totp_config: Optional[TOTPConfig] = None
    google_auth_config: Optional[GoogleAuthConfig] = None
    tunnel_auth_enabled: bool = False
    required_headers: Dict[str, str] = Field(default_factory=dict)

    # Compatibility helpers expected by tests
    def password_required(self) -> bool:
        return self.security_level in (SecurityLevel.PASSWORD, SecurityLevel.TOTP)

    def totp_required(self) -> bool:
        return self.security_level == SecurityLevel.TOTP

    def google_auth_required(self) -> bool:
        return self.security_level == SecurityLevel.GOOGLE_OAUTH

    def tunnel_auth_required(self) -> bool:
        return self.security_level == SecurityLevel.TUNNEL_AUTH

    def meets_security_level(self, level: SecurityLevel) -> bool:
        return int(self.security_level) >= int(level)

    def generate_backup_codes(self, count: int = 10) -> List[str]:
        """Generate numeric backup codes for TOTP."""
        import secrets
        codes = []
        for _ in range(count):
            codes.append("".join(str(secrets.randbelow(10)) for _ in range(6)))
        # store if totp_config present
        if self.totp_config is not None:
            self.totp_config.backup_codes = codes.copy()
        return codes
