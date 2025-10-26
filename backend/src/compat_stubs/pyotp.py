"""Lightweight pyotp-compatible stub used in environments without the real dependency.

Implements the subset exercised by the backend unit tests: RFC 6238-compliant TOTP
generation with configurable digit length and step interval, ``now``/``at`` helpers,
and ``verify`` with ``valid_window`` support.  A deterministic ``random_base32`` helper
is provided to match the production API surface.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import datetime
from typing import Callable

__all__ = ["TOTP", "random_base32", "utils"]


def _normalize_base32(secret: str) -> bytes:
    try:
        padded = secret.strip().upper()
        # Pad length to a multiple of 8 for base32 decoding compliance
        missing = (-len(padded)) % 8
        if missing:
            padded += "=" * missing
        return base64.b32decode(padded, casefold=True)
    except Exception as exc:  # pragma: no cover - malformed secrets
        raise ValueError("Invalid base32 secret") from exc


def random_base32(length: int = 32, *, characters: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") -> str:
    """Return a random RFC 3548 base32 string using the requested alphabet."""
    if length <= 0:
        raise ValueError("length must be positive")
    alphabet = characters or "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    if len(set(alphabet)) < 2:
        raise ValueError("characters must contain at least two unique symbols")
    # Sample from the alphabet to produce deterministic-length output without padding.
    return "".join(secrets.choice(alphabet) for _ in range(length))


class _UtilsModule:
    @staticmethod
    def random_base32(length: int = 32) -> str:
        return random_base32(length=length)


utils = _UtilsModule()


class TOTP:  # pragma: no cover - exercised via higher-level unit tests
    def __init__(
        self,
        secret: str,
        digits: int = 6,
        interval: int = 30,
        digest: Callable[[bytes], "hashlib._Hash"] = hashlib.sha1,
    ) -> None:
        if digits <= 0:
            raise ValueError("digits must be positive")
        if interval <= 0:
            raise ValueError("interval must be positive")
        self.secret = secret
        self.digits = int(digits)
        self.interval = int(interval)
        self.digest = digest
        self._secret_bytes = _normalize_base32(secret)

    def __repr__(self) -> str:
        return f"TOTP(digits={self.digits}, interval={self.interval})"

    def _timecode(self, for_time: float | int | datetime | None = None) -> int:
        if for_time is None:
            timestamp = time.time()
        elif isinstance(for_time, datetime):
            timestamp = for_time.timestamp()
        else:
            timestamp = float(for_time)
        return int(timestamp // self.interval)

    def _generate_otp(self, counter: int) -> str:
        if counter < 0:
            raise ValueError("counter must be non-negative")
        packed = struct.pack(">Q", counter)
        digest = hmac.new(self._secret_bytes, packed, self.digest).digest()
        offset = digest[-1] & 0x0F
        truncated = (
            ((digest[offset] & 0x7F) << 24)
            | ((digest[offset + 1] & 0xFF) << 16)
            | ((digest[offset + 2] & 0xFF) << 8)
            | (digest[offset + 3] & 0xFF)
        )
        code = truncated % (10 ** self.digits)
        return str(code).zfill(self.digits)

    def at(self, for_time: float | int | datetime, counter_offset: int = 0) -> str:
        counter = self._timecode(for_time) + int(counter_offset)
        if counter < 0:
            raise ValueError("counter must be non-negative")
        return self._generate_otp(counter)

    def now(self) -> str:
        return self.at(time.time())

    def verify(
        self,
        code: str | int | None,
        for_time: float | int | datetime | None = None,
        valid_window: int = 0,
    ) -> bool:
        if code is None:
            return False
        candidate = str(code).strip()
        if not candidate:
            return False

        timestamp = self._timecode(for_time)
        window = max(0, int(valid_window))
        for offset in range(-window, window + 1):
            counter = timestamp + offset
            if counter < 0:
                continue
            if self._generate_otp(counter) == candidate:
                return True
        return False
