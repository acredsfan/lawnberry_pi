from __future__ import annotations
import time
import hashlib
from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    id: str
    username: str
    role: str = "admin"


class AuthService:
    """Simple auth service with default admin account.

    NOTE: This is a placeholder to satisfy Phase 0 wiring; full integration
    will be performed in later phases aligning with contracts.
    """

    def __init__(self):
        self._default_user = User(id="admin", username="admin")

    def authenticate(self, username: str, password: str) -> Optional[User]:
        if username == "admin" and password == "admin":
            return self._default_user
        return None

    def issue_token(self, subject: str) -> str:
        return "lbp2-" + hashlib.sha256(f"{subject}-{time.time()}".encode()).hexdigest()[:32]


auth_service = AuthService()
