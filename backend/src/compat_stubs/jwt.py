"""Lightweight JWT compatibility stub for test environments.

Provides a minimal subset of the PyJWT API required by the authentication
service. Tokens are signed using HMAC-SHA256 and validated against expiration
claims. This module is only used when the real PyJWT package is unavailable.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Iterable, Optional

__all__ = [
    "encode",
    "decode",
    "ExpiredSignatureError",
    "InvalidTokenError",
]


class ExpiredSignatureError(Exception):
    """Raised when the token's exp claim has passed."""


class InvalidTokenError(Exception):
    """Raised when a token cannot be decoded or validated."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _json_dumps(data: Dict[str, Any]) -> str:
    return json.dumps(data, separators=(",", ":"), sort_keys=True)


def encode(payload: Dict[str, Any], key: str, algorithm: str = "HS256") -> str:
    if algorithm != "HS256":
        raise InvalidTokenError(f"Unsupported algorithm: {algorithm}")

    header = {"alg": algorithm, "typ": "JWT"}
    segments = [
        _b64url_encode(_json_dumps(header).encode("utf-8")),
        _b64url_encode(_json_dumps(payload).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("utf-8")
    signature = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    segments.append(_b64url_encode(signature))
    return ".".join(segments)


def decode(
    token: str,
    key: str,
    algorithms: Optional[Iterable[str]] = None,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    algorithms = list(algorithms or ["HS256"])
    if "HS256" not in algorithms:
        raise InvalidTokenError("HS256 algorithm must be allowed")

    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidTokenError("Invalid token format")

    header_segment, payload_segment, signature_segment = parts
    signing_input = f"{header_segment}.{payload_segment}".encode("utf-8")

    try:
        header = json.loads(_b64url_decode(header_segment))
        payload = json.loads(_b64url_decode(payload_segment))
    except Exception as exc:
        raise InvalidTokenError("Malformed token") from exc

    algorithm = header.get("alg")
    if algorithm != "HS256":
        raise InvalidTokenError(f"Unsupported algorithm: {algorithm}")

    expected_signature = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    provided_signature = _b64url_decode(signature_segment)
    if not hmac.compare_digest(expected_signature, provided_signature):
        raise InvalidTokenError("Signature verification failed")

    required = set((options or {}).get("require", []))
    if required and not required.issubset(payload.keys()):
        missing = required.difference(payload.keys())
        raise InvalidTokenError(f"Missing required claims: {', '.join(sorted(missing))}")

    exp = payload.get("exp")
    if isinstance(exp, (int, float)) and time.time() > exp:
        raise ExpiredSignatureError("Token expired")

    return payload
