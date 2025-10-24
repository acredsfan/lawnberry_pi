"""Minimal bcrypt stub for test environments without the C extension.

The goal of this stub is not to be cryptographically accurate but to
behave similarly enough for unit tests that assert the output format of
`bcrypt.hashpw`. The real library returns hashes that start with
``$2b$`` followed by a two-digit cost and a 53-character payload. We
mirror that layout so tests can validate the prefix without requiring
the C extension to be installed.
"""

import base64
import hashlib
import os
from typing import Union


def _ensure_bytes(value: Union[str, bytes]) -> bytes:
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")


def _bcrypt64(data: bytes, length: int) -> str:
    """Return a bcrypt-style base64 string of the requested length."""

    encoded = base64.b64encode(data).decode("ascii")
    # bcrypt uses ./ as the two extra characters and strips padding
    sanitized = encoded.replace("+", ".").replace("/", "/").replace("=", "")
    if len(sanitized) < length:
        # Pad deterministically with dots if randomness is too short
        sanitized = sanitized.ljust(length, ".")
    return sanitized[:length]


def gensalt(rounds: int = 12) -> bytes:  # pragma: no cover - deterministic enough for tests
    rounds = max(4, min(31, int(rounds)))
    salt_body = _bcrypt64(os.urandom(16), 22)
    return f"$2b${rounds:02d}${salt_body}".encode("ascii")


def hashpw(password: Union[str, bytes], salt: Union[str, bytes]) -> bytes:  # pragma: no cover
    salt_str = _ensure_bytes(salt).decode("ascii")
    if not salt_str.startswith("$2b$"):
        raise ValueError("Invalid salt format")

    try:
        _, _, cost_str, salt_body = salt_str.split("$", 3)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError("Invalid salt structure") from exc

    if len(salt_body) < 22:
        raise ValueError("Salt too short")

    password_bytes = _ensure_bytes(password)
    digest = hashlib.sha256(f"{cost_str}:{salt_body}".encode("ascii") + b":" + password_bytes).digest()
    hash_body = _bcrypt64(digest, 31)
    return f"$2b${cost_str}${salt_body}{hash_body}".encode("ascii")


def checkpw(password: Union[str, bytes], hashed: Union[str, bytes]) -> bool:  # pragma: no cover
    hashed_bytes = _ensure_bytes(hashed)
    try:
        recalculated = hashpw(password, hashed_bytes[:29])  # salt is first 29 bytes
    except ValueError:
        return False
    return hashed_bytes == recalculated
