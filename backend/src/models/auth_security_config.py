from enum import Enum
from typing import Optional
from pydantic import BaseModel


class AuthSecurityLevel(str, Enum):
    PASSWORD_ONLY = "password_only"
    PASSWORD_TOTP = "password_totp"
    GOOGLE_AUTH = "google_auth"
    CLOUDFLARE_TUNNEL_AUTH = "cloudflare_tunnel_auth"


class AuthSecurityConfig(BaseModel):
    level: AuthSecurityLevel = AuthSecurityLevel.PASSWORD_ONLY
    # TOTP
    totp_issuer: str = "LawnBerry"
    totp_digits: int = 6
    totp_period: int = 30
    # Google OAuth
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_redirect_uri: Optional[str] = None
    # Cloudflare Tunnel Auth (trust headers from tunnel)
    cloudflare_email_header: str = "Cf-Access-Authenticated-User-Email"
    cloudflare_jwt_header: str = "Cf-Access-Jwt-Assertion"

    class Config:
        use_enum_values = True
