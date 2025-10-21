"""Minimal passlib CryptContext stub used for tests when passlib is unavailable."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Iterable, Optional

__all__ = ["CryptContext"]


class CryptContext:
    def __init__(self, schemes: Optional[Iterable[str]] = None, deprecated: str | None = None) -> None:
        self.schemes = list(schemes or ["bcrypt"])
        self.deprecated = deprecated
        self._rounds = 390000

    def hash(self, password: str) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), self._rounds)
        return f"pbkdf2_sha256${salt}${digest.hex()}"

    def verify(self, password: str, hashed: str) -> bool:
        try:
            _scheme, salt, digest_hex = hashed.split("$", 2)
        except ValueError:
            return False
        new_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), self._rounds)
        return hmac.compare_digest(new_digest.hex(), digest_hex)
