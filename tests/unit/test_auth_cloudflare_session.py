from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.src.models.auth_security_config import SecurityLevel
from backend.src.models.user_session import AuthenticationMethod
from backend.src.services.auth_service import (
    AuthenticationError,
    AuthService,
    AuthStatePersistenceError,
)


def _configure_auth_environment(monkeypatch) -> None:
    monkeypatch.setenv("SIM_MODE", "0")
    monkeypatch.setenv("LAWN_BERRY_OPERATOR_CREDENTIAL", "test-operator-credential")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-" + ("x" * 64))


@pytest.mark.asyncio
async def test_cloudflare_jwt_restores_signed_principal_and_method(monkeypatch):
    _configure_auth_environment(monkeypatch)
    issuer = AuthService()
    result = await issuer.authenticate_cloudflare(
        "operator@example.com",
        assertion_expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )

    restored_service = AuthService()
    restored = await restored_service.verify_token(result.token)

    assert restored is not None
    assert restored.username == "operator@example.com"
    assert restored.security_level == SecurityLevel.TUNNEL_AUTH
    assert (
        restored.security_context.authentication_method
        == AuthenticationMethod.CLOUDFLARE_ACCESS
    )


@pytest.mark.asyncio
async def test_repeated_cloudflare_bootstrap_reuses_bounded_session(monkeypatch):
    _configure_auth_environment(monkeypatch)
    service = AuthService()
    service.config.max_concurrent_sessions = 1

    assertion_expires_at = datetime.now(UTC) + timedelta(minutes=30)
    first = await service.authenticate_cloudflare(
        "operator@example.com",
        assertion_expires_at=assertion_expires_at,
    )
    second = await service.authenticate_cloudflare(
        "operator@example.com",
        assertion_expires_at=assertion_expires_at,
    )

    assert second.session.session_id == first.session.session_id
    assert len(service.active_sessions) == 1


@pytest.mark.asyncio
async def test_cloudflare_token_and_session_never_outlive_verified_assertion(monkeypatch):
    _configure_auth_environment(monkeypatch)
    service = AuthService()
    assertion_expires_at = datetime.now(UTC) + timedelta(minutes=2)

    result = await service.authenticate_cloudflare(
        "operator@example.com",
        assertion_expires_at=assertion_expires_at,
    )
    payload = service.jwt_manager.verify_token(result.token)

    assert payload is not None
    assert payload["exp"] == int(assertion_expires_at.timestamp())
    assert payload["upstream_exp"] == int(assertion_expires_at.timestamp())
    assert result.expires_at <= assertion_expires_at
    assert result.session.expires_at <= assertion_expires_at
    assert await service.extend_session(result.session.session_id, hours=24)
    assert result.session.expires_at <= assertion_expires_at


@pytest.mark.asyncio
async def test_cloudflare_refresh_requires_matching_verified_identity(monkeypatch):
    _configure_auth_environment(monkeypatch)
    service = AuthService()
    initial_expiry = datetime.now(UTC) + timedelta(minutes=2)
    result = await service.authenticate_cloudflare(
        "operator@example.com",
        assertion_expires_at=initial_expiry,
    )

    with pytest.raises(AuthenticationError):
        service.refresh_session_token(result.session)
    with pytest.raises(AuthenticationError):
        service.refresh_session_token(
            result.session,
            cloudflare_principal="different@example.com",
            cloudflare_expires_at=initial_expiry + timedelta(minutes=2),
        )

    refreshed_expiry = initial_expiry + timedelta(minutes=2)
    refreshed = service.refresh_session_token(
        result.session,
        cloudflare_principal="operator@example.com",
        cloudflare_expires_at=refreshed_expiry,
    )
    assert refreshed.expires_at <= refreshed_expiry


@pytest.mark.asyncio
async def test_logout_revocation_survives_service_restart(monkeypatch, tmp_path):
    _configure_auth_environment(monkeypatch)
    revocation_path = tmp_path / "revocations.json"
    service = AuthService(revocation_path=revocation_path)
    result = await service.authenticate(
        "test-operator-credential",
        client_ip="192.0.2.10",
    )

    assert await service.terminate_session(result.session.session_id, "user_logout")
    assert await service.verify_token(result.token) is None

    restarted = AuthService(revocation_path=revocation_path)
    assert await restarted.verify_token(result.token) is None


@pytest.mark.asyncio
async def test_old_token_first_logout_revokes_newer_same_sid_token(monkeypatch, tmp_path):
    import backend.src.services.auth_service as auth_service_module

    _configure_auth_environment(monkeypatch)
    revocation_path = tmp_path / "revocations.json"
    issuer = AuthService(revocation_path=revocation_path)
    issuer.jwt_manager.token_expiry_hours = 1
    initial = await issuer.authenticate(
        "test-operator-credential",
        client_ip="192.0.2.10",
    )
    initial_payload = issuer.jwt_manager.verify_token(initial.token)
    assert initial_payload is not None

    issuer.jwt_manager.token_expiry_hours = 4
    refreshed = issuer.refresh_session_token(initial.session)
    refreshed_payload = issuer.jwt_manager.verify_token(refreshed.token)
    assert refreshed_payload is not None
    assert refreshed_payload["sid"] == initial_payload["sid"]
    assert refreshed_payload["exp"] > initial_payload["exp"]

    restarted = AuthService(revocation_path=revocation_path)
    restored_from_old = await restarted.verify_token(initial.token)
    assert restored_from_old is not None
    assert await restarted.terminate_session(restored_from_old.session_id, "user_logout")

    simulated_now = datetime.fromtimestamp(initial_payload["exp"] + 1, tz=UTC)
    assert simulated_now < datetime.fromtimestamp(refreshed_payload["exp"], tz=UTC)

    class _FutureDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return simulated_now if tz is not None else simulated_now.replace(tzinfo=None)

    monkeypatch.setattr(auth_service_module, "datetime", _FutureDateTime)
    after_old_expiry = AuthService(revocation_path=revocation_path)

    assert await after_old_expiry.verify_token(refreshed.token) is None


@pytest.mark.asyncio
async def test_session_limit_eviction_revokes_displaced_jwt(monkeypatch, tmp_path):
    _configure_auth_environment(monkeypatch)
    service = AuthService(revocation_path=tmp_path / "revocations.json")
    service.config.max_concurrent_sessions = 1
    first = await service.authenticate(
        "test-operator-credential",
        client_ip="192.0.2.10",
    )
    second = await service.authenticate(
        "test-operator-credential",
        client_ip="192.0.2.10",
    )

    assert first.session.session_id != second.session.session_id
    assert await service.verify_token(first.token) is None
    assert await service.verify_token(second.token) is not None


@pytest.mark.asyncio
async def test_unwritable_revocation_store_fails_logout_and_restart_closed(
    monkeypatch,
    tmp_path,
):
    from backend.src.api.routers import auth as auth_router

    _configure_auth_environment(monkeypatch)
    service = AuthService(revocation_path=tmp_path / "healthy" / "revocations.json")
    result = await service.authenticate(
        "test-operator-credential",
        client_ip="192.0.2.10",
    )
    monkeypatch.setattr(auth_router, "primary_auth_service", service)

    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("blocks atomic revocation writes", encoding="utf-8")
    blocked_path = blocked_parent / "revocations.json"
    service._revocation_path = blocked_path
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v2/auth/logout",
            "headers": [(b"authorization", f"Bearer {result.token}".encode("ascii"))],
        }
    )

    with pytest.raises(HTTPException) as failed_logout:
        await auth_router.auth_logout(request)

    assert failed_logout.value.status_code == 503
    assert result.session.session_id in service.active_sessions
    assert service.revocation_store_healthy is False
    assert await service.verify_token(result.token) is None

    restarted = AuthService(revocation_path=blocked_path)
    assert restarted.revocation_store_healthy is False
    assert await restarted.verify_token(result.token) is None
    with pytest.raises(AuthenticationError) as failed_login:
        await restarted.authenticate(
            "test-operator-credential",
            client_ip="192.0.2.10",
        )
    assert failed_login.value.status_code == 503


@pytest.mark.asyncio
async def test_terminate_session_raises_when_revocation_commit_fails(monkeypatch, tmp_path):
    _configure_auth_environment(monkeypatch)
    service = AuthService(revocation_path=tmp_path / "revocations.json")
    result = await service.authenticate(
        "test-operator-credential",
        client_ip="192.0.2.10",
    )
    blocked_parent = tmp_path / "blocked"
    blocked_parent.write_text("not a directory", encoding="utf-8")
    service._revocation_path = blocked_parent / "revocations.json"

    with pytest.raises(AuthStatePersistenceError):
        await service.terminate_session(result.session.session_id, "user_logout")


@pytest.mark.asyncio
async def test_custom_password_lockout_expires_instead_of_becoming_permanent(monkeypatch):
    _configure_auth_environment(monkeypatch)
    service = AuthService()
    service.config.password_hash = service.password_manager.hash_password("correct-password")
    client_ip = "127.0.0.1"
    key = "password:ip:127.0.0.1"

    for _ in range(service.rate_limiter.failure_limit):
        with pytest.raises(AuthenticationError):
            await service.authenticate_password(
                "admin",
                "wrong-password",
                client_ip=client_ip,
            )

    with pytest.raises(AuthenticationError) as locked:
        await service.authenticate_password(
            "admin",
            "correct-password",
            client_ip=client_ip,
        )
    assert locked.value.status_code == 429

    service.rate_limiter._lockout_until[key] = datetime.now(UTC) - timedelta(seconds=1)
    session = await service.authenticate_password(
        "admin",
        "correct-password",
        client_ip=client_ip,
    )
    assert session.username == "admin"
