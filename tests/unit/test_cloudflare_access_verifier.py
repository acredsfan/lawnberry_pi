from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from backend.src.services.cloudflare_access_service import (
    CloudflareAccessError,
    CloudflareAccessVerifier,
)

TEAM_DOMAIN = "lawnberry-test.cloudflareaccess.com"
AUDIENCE = "lawnberry-access-audience"
KEY_ID = "test-key"


def _public_jwk(private_key: rsa.RSAPrivateKey, *, key_id: str = KEY_ID) -> dict[str, str]:
    numbers = private_key.public_key().public_numbers()

    def encoded(value: int) -> str:
        length = (value.bit_length() + 7) // 8
        return base64.urlsafe_b64encode(value.to_bytes(length, "big")).rstrip(b"=").decode()

    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": key_id,
        "n": encoded(numbers.n),
        "e": encoded(numbers.e),
    }


def _assertion(
    private_key: rsa.RSAPrivateKey,
    *,
    audience: str = AUDIENCE,
    issuer: str = f"https://{TEAM_DOMAIN}",
    email: str | None = "operator@example.com",
    expires_at: datetime | None = None,
    algorithm: str = "RS256",
    key_id: str = KEY_ID,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": "cloudflare-user-id",
        "aud": audience,
        "iss": issuer,
        "iat": now,
        "exp": expires_at or now + timedelta(minutes=5),
    }
    if email is not None:
        payload["email"] = email
    return jwt.encode(payload, private_key, algorithm=algorithm, headers={"kid": key_id})


@pytest.fixture
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.asyncio
async def test_verified_assertion_uses_signed_identity_and_cached_jwks(private_key):
    fetches: list[str] = []

    async def fetch_jwks(url: str) -> dict:
        fetches.append(url)
        return {"keys": [_public_jwk(private_key)]}

    verifier = CloudflareAccessVerifier(
        team_domain=TEAM_DOMAIN,
        audience=AUDIENCE,
        jwks_fetcher=fetch_jwks,
    )
    token = _assertion(private_key)

    first = await verifier.verify(token)
    second = await verifier.verify(token)

    assert first.principal == "operator@example.com"
    assert first.claims["sub"] == "cloudflare-user-id"
    assert first.expires_at == datetime.fromtimestamp(first.claims["exp"], tz=UTC)
    assert second == first
    assert fetches == [f"https://{TEAM_DOMAIN}/cdn-cgi/access/certs"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("token_factory", "reason"),
    [
        (lambda key: _assertion(key, audience="wrong-audience"), "audience"),
        (
            lambda key: _assertion(key, issuer="https://attacker.cloudflareaccess.com"),
            "issuer",
        ),
        (
            lambda key: _assertion(key, expires_at=datetime.now(UTC) - timedelta(seconds=30)),
            "expired",
        ),
    ],
)
async def test_assertion_claim_mismatch_fails_closed(private_key, token_factory, reason):
    async def fetch_jwks(_url: str) -> dict:
        return {"keys": [_public_jwk(private_key)]}

    verifier = CloudflareAccessVerifier(
        team_domain=TEAM_DOMAIN,
        audience=AUDIENCE,
        jwks_fetcher=fetch_jwks,
    )

    with pytest.raises(CloudflareAccessError, match=reason):
        await verifier.verify(token_factory(private_key))


@pytest.mark.asyncio
async def test_forged_signature_and_missing_identity_fail_closed(private_key):
    attacker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    async def fetch_jwks(_url: str) -> dict:
        return {"keys": [_public_jwk(private_key)]}

    verifier = CloudflareAccessVerifier(
        team_domain=TEAM_DOMAIN,
        audience=AUDIENCE,
        jwks_fetcher=fetch_jwks,
    )

    with pytest.raises(CloudflareAccessError, match="signature"):
        await verifier.verify(_assertion(attacker_key))

    token = _assertion(private_key, email=None)
    identity = await verifier.verify(token)
    assert identity.principal == "cloudflare-user-id"


@pytest.mark.asyncio
async def test_missing_or_unsafe_configuration_fails_closed(private_key):
    token = _assertion(private_key)

    with pytest.raises(CloudflareAccessError, match="not configured"):
        await CloudflareAccessVerifier(team_domain="", audience="").verify(token)

    with pytest.raises(ValueError, match="cloudflareaccess.com"):
        CloudflareAccessVerifier(
            team_domain="attacker.example.com",
            audience=AUDIENCE,
        )


@pytest.mark.asyncio
async def test_unknown_key_ids_cannot_amplify_jwks_fetches(private_key):
    fetches = 0

    async def fetch_jwks(_url: str) -> dict:
        nonlocal fetches
        fetches += 1
        return {"keys": [_public_jwk(private_key)]}

    verifier = CloudflareAccessVerifier(
        team_domain=TEAM_DOMAIN,
        audience=AUDIENCE,
        jwks_fetcher=fetch_jwks,
        unknown_key_refresh_interval_seconds=30.0,
    )
    await verifier.verify(_assertion(private_key))

    for key_id in ("unknown-1", "unknown-2", "unknown-3"):
        with pytest.raises(CloudflareAccessError, match="unknown"):
            await verifier.verify(_assertion(private_key, key_id=key_id))

    assert fetches == 1
