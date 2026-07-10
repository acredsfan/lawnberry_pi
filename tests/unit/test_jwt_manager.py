from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from backend.src.core.secrets_manager import SecretsManager
from backend.src.models.user_session import UserRole
from backend.src.services.auth_service import JWTConfigurationError, JWTManager

SECRET = "test-only-jwt-secret-" + ("x" * 64)


def test_v25_pyjwt_213_round_trip_uses_required_claims_and_hs256():
    manager = JWTManager(SECRET)

    token, expires_at = manager.create_token(
        session_id="session-1",
        user_id="operator-1",
        role=UserRole.OPERATOR,
    )

    payload = manager.verify_token(token)
    assert payload is not None
    assert payload["sid"] == "session-1"
    assert payload["sub"] == "operator-1"
    assert payload["role"] == UserRole.OPERATOR.value
    assert expires_at > datetime.now(UTC)
    assert jwt.get_unverified_header(token)["alg"] == "HS256"


def test_v25_manager_uses_canonical_secrets_manager_jwt_secret(monkeypatch):
    monkeypatch.delenv("LAWN_BERRY_AUTH_SECRET", raising=False)
    monkeypatch.setenv("JWT_SECRET", SECRET)
    manager = JWTManager()

    token, _ = manager.create_token(
        session_id="session-canonical",
        user_id="operator-canonical",
        role=UserRole.OPERATOR,
    )

    assert manager.verify_token(token) is not None


def test_v25_expired_token_is_rejected():
    manager = JWTManager(SECRET)
    token = jwt.encode(
        {
            "sub": "operator-1",
            "sid": "session-1",
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        SECRET,
        algorithm="HS256",
    )

    assert manager.verify_token(token) is None


def test_v25_invalid_signature_is_rejected():
    manager = JWTManager(SECRET)
    token = jwt.encode(
        {
            "sub": "operator-1",
            "sid": "session-1",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        "different-test-signing-secret-at-least-32-bytes",
        algorithm="HS256",
    )

    assert manager.verify_token(token) is None


def test_v25_algorithm_allow_list_rejects_hs384():
    manager = JWTManager(SECRET)
    token = jwt.encode(
        {
            "sub": "operator-1",
            "sid": "session-1",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        SECRET,
        algorithm="HS384",
    )

    assert manager.verify_token(token) is None


@pytest.mark.parametrize("provided_secret", [None, "", "   "])
def test_v25_missing_or_empty_canonical_secret_fails_closed_at_token_use(
    monkeypatch,
    provided_secret,
):
    monkeypatch.delenv("LAWN_BERRY_AUTH_SECRET", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    manager = JWTManager(secret_provider=lambda: provided_secret)

    with pytest.raises(JWTConfigurationError, match="JWT_SECRET is required"):
        manager.create_token(
            session_id="session-1",
            user_id="operator-1",
            role=UserRole.OPERATOR,
        )

    with pytest.raises(JWTConfigurationError, match="JWT_SECRET is required"):
        manager.verify_token("not-a-token")


def test_v25_secrets_manager_does_not_auto_generate_missing_jwt_secret(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    store_path = tmp_path / "secrets.json"
    manager = SecretsManager(str(store_path))

    assert manager.get("JWT_SECRET", default=None, purpose="test") is None
    assert not store_path.exists()
