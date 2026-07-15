"""Cryptographic Cloudflare Access assertion verification.

Cloudflare's forwarding headers are untrusted input until the Access JWT has
been checked against the configured team issuer, application audience, and the
team's rotating RS256 keys.  This service is the single verification boundary
used by HTTP, manual-control, and WebSocket authentication paths.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
import jwt

logger = logging.getLogger(__name__)

JwksFetcher = Callable[[str], Awaitable[dict[str, Any]]]


class CloudflareAccessError(RuntimeError):
    """Raised when an Access assertion cannot be trusted."""


@dataclass(frozen=True, slots=True)
class VerifiedCloudflareIdentity:
    """Identity and claims derived exclusively from a verified assertion."""

    principal: str
    expires_at: datetime
    claims: dict[str, Any]


class CloudflareAccessVerifier:
    """Verify Cloudflare Access JWTs with a bounded rotating-JWKS cache."""

    def __init__(
        self,
        *,
        team_domain: str | None = None,
        audience: str | None = None,
        jwks_fetcher: JwksFetcher | None = None,
        cache_ttl_seconds: float = 3600.0,
        unknown_key_refresh_interval_seconds: float = 30.0,
    ) -> None:
        self.team_domain = self._normalize_team_domain(team_domain or "")
        self.audience = (audience or "").strip()
        self.issuer = f"https://{self.team_domain}" if self.team_domain else ""
        self.jwks_url = (
            f"{self.issuer}/cdn-cgi/access/certs" if self.issuer else ""
        )
        self._fetch_jwks = jwks_fetcher or self._fetch_jwks_http
        self._cache_ttl_seconds = max(60.0, min(float(cache_ttl_seconds), 86400.0))
        self._unknown_key_refresh_interval_seconds = max(
            1.0,
            min(float(unknown_key_refresh_interval_seconds), 300.0),
        )
        self._keys: dict[str, Any] = {}
        self._cache_expires_monotonic = 0.0
        self._next_refresh_allowed_monotonic = 0.0
        self._refresh_lock = asyncio.Lock()

    @classmethod
    def from_environment(cls) -> CloudflareAccessVerifier:
        return cls(
            team_domain=os.getenv("CLOUDFLARE_ACCESS_TEAM_DOMAIN"),
            audience=os.getenv("CLOUDFLARE_ACCESS_AUD"),
        )

    @property
    def configured(self) -> bool:
        return bool(self.team_domain and self.audience)

    async def verify(self, token: str) -> VerifiedCloudflareIdentity:
        """Return signed identity claims or fail closed with a safe reason."""
        if not self.configured:
            raise CloudflareAccessError("Cloudflare Access verifier is not configured")
        assertion = (token or "").strip()
        if not assertion or len(assertion) > 16384:
            raise CloudflareAccessError("Cloudflare Access assertion is malformed")

        try:
            header = jwt.get_unverified_header(assertion)
        except jwt.InvalidTokenError as exc:
            raise CloudflareAccessError("Cloudflare Access assertion is malformed") from exc

        if header.get("alg") != "RS256":
            raise CloudflareAccessError("Cloudflare Access algorithm must be RS256")
        key_id = header.get("kid")
        if not isinstance(key_id, str) or not key_id.strip():
            raise CloudflareAccessError("Cloudflare Access assertion key id is missing")

        key = await self._key_for_id(key_id)
        try:
            claims = jwt.decode(
                assertion,
                key=key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                leeway=15,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise CloudflareAccessError("Cloudflare Access assertion expired") from exc
        except jwt.InvalidAudienceError as exc:
            raise CloudflareAccessError("Cloudflare Access audience invalid") from exc
        except jwt.InvalidIssuerError as exc:
            raise CloudflareAccessError("Cloudflare Access issuer invalid") from exc
        except jwt.InvalidSignatureError as exc:
            raise CloudflareAccessError("Cloudflare Access signature invalid") from exc
        except jwt.InvalidTokenError as exc:
            raise CloudflareAccessError("Cloudflare Access assertion invalid") from exc

        principal_value = claims.get("email") or claims.get("sub")
        principal = str(principal_value or "").strip()
        if not principal:
            raise CloudflareAccessError("Cloudflare Access signed identity is missing")
        try:
            expires_at = datetime.fromtimestamp(float(claims["exp"]), tz=UTC)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise CloudflareAccessError("Cloudflare Access assertion expiry is invalid") from exc
        if expires_at <= datetime.now(UTC):
            raise CloudflareAccessError("Cloudflare Access assertion expired")
        return VerifiedCloudflareIdentity(
            principal=principal,
            expires_at=expires_at,
            claims=dict(claims),
        )

    async def _key_for_id(self, key_id: str) -> Any:
        now = time.monotonic()
        key = self._keys.get(key_id)
        if key is not None and now < self._cache_expires_monotonic:
            return key

        async with self._refresh_lock:
            now = time.monotonic()
            key = self._keys.get(key_id)
            if key is not None and now < self._cache_expires_monotonic:
                return key
            if now < self._next_refresh_allowed_monotonic:
                reason = (
                    "Cloudflare Access assertion key id is unknown"
                    if self._keys
                    else "Cloudflare Access verification keys unavailable"
                )
                raise CloudflareAccessError(reason)
            await self._refresh_keys()
            key = self._keys.get(key_id)
            if key is None:
                raise CloudflareAccessError("Cloudflare Access assertion key id is unknown")
            return key

    async def _refresh_keys(self) -> None:
        self._next_refresh_allowed_monotonic = (
            time.monotonic() + self._unknown_key_refresh_interval_seconds
        )
        try:
            payload = await self._fetch_jwks(self.jwks_url)
            raw_keys = payload.get("keys") if isinstance(payload, dict) else None
            if not isinstance(raw_keys, list) or not raw_keys:
                raise ValueError("JWKS contains no keys")
            parsed: dict[str, Any] = {}
            for raw_key in raw_keys:
                if not isinstance(raw_key, dict):
                    continue
                key_id = raw_key.get("kid")
                if (
                    not isinstance(key_id, str)
                    or raw_key.get("kty") != "RSA"
                    or raw_key.get("alg") not in {None, "RS256"}
                ):
                    continue
                parsed[key_id] = jwt.PyJWK.from_dict(raw_key, algorithm="RS256").key
            if not parsed:
                raise ValueError("JWKS contains no usable RS256 keys")
        except CloudflareAccessError:
            raise
        except Exception as exc:
            logger.warning("Unable to refresh Cloudflare Access verification keys: %s", exc)
            raise CloudflareAccessError(
                "Cloudflare Access verification keys unavailable"
            ) from exc

        self._keys = parsed
        self._cache_expires_monotonic = time.monotonic() + self._cache_ttl_seconds

    async def _fetch_jwks_http(self, url: str) -> dict[str, Any]:
        timeout = httpx.Timeout(5.0, connect=3.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            response = await client.get(url, headers={"Accept": "application/json"})
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Cloudflare Access JWKS response is not an object")
        return payload

    @staticmethod
    def _normalize_team_domain(value: str) -> str:
        raw = value.strip().lower().rstrip("/")
        if not raw:
            return ""
        parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError(
                "Cloudflare Access team domain must be a bare HTTPS hostname"
            ) from exc
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or port is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Cloudflare Access team domain must be a bare HTTPS hostname")
        hostname = (parsed.hostname or "").rstrip(".")
        if not hostname.endswith(".cloudflareaccess.com"):
            raise ValueError("Cloudflare Access team domain must end in cloudflareaccess.com")
        return hostname


cloudflare_access_verifier = CloudflareAccessVerifier.from_environment()


__all__ = [
    "CloudflareAccessError",
    "CloudflareAccessVerifier",
    "VerifiedCloudflareIdentity",
    "cloudflare_access_verifier",
]
