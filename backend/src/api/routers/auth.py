import base64
import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import pyotp
from fastapi import APIRouter, HTTPException, Request, WebSocket, status
from pydantic import BaseModel, Field

from ...core import globals as global_state
from ...core.client_identity import client_ip
from ...core.globals import _manual_control_sessions
from ...models.auth_security_config import AuthSecurityConfig, SecurityLevel
from ...models.user_session import AuthenticationMethod, UserSession
from ...services.auth_service import (
    AuthenticationError,
    AuthStatePersistenceError,
    primary_auth_service,
)
from ...services.cloudflare_access_service import (
    CloudflareAccessError,
    VerifiedCloudflareIdentity,
    cloudflare_access_verifier,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _current_security_settings() -> AuthSecurityConfig:
    rest_module = sys.modules.get("backend.src.api.rest")
    if rest_module is not None:
        rest_settings = getattr(rest_module, "_security_settings", None)
        if isinstance(rest_settings, AuthSecurityConfig):
            return rest_settings
    return global_state._security_settings


# Security settings (auth levels, MFA options)
# This was in rest.py as _security_settings.
# I should probably move this to a service or keep it here if it's only used here.
# It is used in manual unlock logic.
# Security settings (auth levels, MFA options)
# Imported from globals.py


# Models
class ManualUnlockRequest(BaseModel):
    method: str | None = None
    password: str | None = None
    totp_code: str | None = None


class ManualUnlockResponse(BaseModel):
    authorized: bool
    session_id: str
    expires_at: str
    principal: str | None = None
    source: str = "manual_control"


class ManualUnlockStatusResponse(BaseModel):
    authorized: bool
    session_id: str | None = None
    expires_at: str | None = None
    principal: str | None = None
    reason: str | None = None


class AuthLoginRequest(BaseModel):
    # Shared credential is the initial/local login. Username/password is only
    # available after an operator explicitly configures a custom password.
    credential: str | None = None
    username: str | None = None
    password: str | None = None


class UserOut(BaseModel):
    id: str
    username: str
    role: str = "admin"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuthResponse(BaseModel):
    # Back-compat fields
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: UserOut
    # Contract-required convenience fields
    token: str
    expires_at: datetime


class RefreshResponse(BaseModel):
    access_token: str
    token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    expires_at: datetime


class SetPasswordRequest(BaseModel):
    username: str
    password: str


class SetPasswordResponse(BaseModel):
    ok: bool
    message: str = "Password configured successfully"


# Helpers
def _decode_jwt_payload(token: str) -> dict[str, Any]:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload_segment = parts[1]
        padding = "=" * ((4 - len(payload_segment) % 4) % 4)
        decoded = base64.urlsafe_b64decode((payload_segment + padding).encode("utf-8"))
        data = json.loads(decoded.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _manual_session_expiry(
    default_minutes: int | None = None, token_payload: dict[str, Any] | None = None
) -> datetime:
    now = datetime.now(UTC)
    minutes = default_minutes or 60
    try:
        minutes = int(minutes)
    except Exception:
        minutes = 60
    local_expiry = now + timedelta(minutes=max(1, minutes))
    if token_payload and isinstance(token_payload.get("exp"), (int, float)):
        try:
            token_expiry = datetime.fromtimestamp(float(token_payload["exp"]), tz=UTC)
            return min(local_expiry, token_expiry)
        except (OverflowError, OSError, ValueError):
            pass
    return local_expiry


def _manual_session_key(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"manual-{digest[:16]}"


def _store_manual_session(
    seed: str,
    expires_at: datetime,
    principal: str | None,
    *,
    auth_session_id: str | None = None,
    auth_source: str | None = None,
) -> dict[str, Any]:
    # Garbage collect expired sessions first
    now = datetime.now(UTC)
    for key in list(_manual_control_sessions.keys()):
        if _manual_control_sessions[key]["expires_at"] <= now:
            _manual_control_sessions.pop(key, None)

    entry = _manual_control_sessions.get(seed)
    if entry:
        entry["expires_at"] = expires_at
        if principal:
            entry["principal"] = principal
        if auth_session_id:
            entry["auth_session_id"] = auth_session_id
        if auth_source:
            entry["auth_source"] = auth_source
        return entry

    session_id = _manual_session_key(seed)
    entry = {
        "session_id": session_id,
        "expires_at": expires_at,
        "principal": principal,
        "auth_session_id": auth_session_id,
        "auth_source": auth_source,
    }
    _manual_control_sessions[seed] = entry
    return entry


def _resolve_manual_session(session_id: str | None) -> dict[str, Any]:
    token = (session_id or "").strip()
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Manual control session required")

    now = datetime.now(UTC)
    matched_entry: dict[str, Any] | None = None
    matched_seed: str | None = None
    expired: list[str] = []
    for seed, entry in _manual_control_sessions.items():
        expires_at: datetime = entry.get("expires_at", now)
        if expires_at <= now:
            expired.append(seed)
            continue
        if entry.get("session_id") == token:
            matched_entry = entry
            matched_seed = seed
            break

    for seed in expired:
        _manual_control_sessions.pop(seed, None)

    if matched_entry is None:
        if os.getenv("SIM_MODE", "0") == "1":
            matched_entry = {
                "session_id": token,
                "expires_at": now + timedelta(minutes=60),
                "principal": "simulated-manual-control",
            }
            _manual_control_sessions[token] = matched_entry
            return matched_entry
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Manual control session invalid or expired"
        )

    auth_session_id = str(matched_entry.get("auth_session_id") or "").strip()
    if auth_session_id and not primary_auth_service.is_session_authorized(auth_session_id):
        if matched_seed is not None:
            _manual_control_sessions.pop(matched_seed, None)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Manual control authentication session ended",
        )

    return matched_entry


def _manual_unlock_principal(request: Request, method: str) -> str:
    host = None
    try:
        client = getattr(request, "client", None)
        if client is not None:
            host = getattr(client, "host", None)
    except Exception:
        host = None
    host_str = str(host).strip() if host else ""
    return f"{method}:{host_str}" if host_str else method


def _validate_manual_password(password: str | None) -> str:
    pwd = (password or "").strip()
    security_settings = _current_security_settings()
    required = bool(
        security_settings.password_required()
        or security_settings.password_hash
        or os.getenv("MANUAL_CONTROL_PASSWORD")
    )
    if required and not pwd:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Password required for manual unlock"
        )
    if not pwd:
        return pwd
    if security_settings.password_hash:
        try:
            if not bcrypt.checkpw(
                pwd.encode("utf-8"), security_settings.password_hash.encode("utf-8")
            ):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
        except ValueError as exc:
            logger.error("Invalid password hash configuration: %s", exc)
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Password configuration invalid"
            ) from exc
    else:
        fallback = os.getenv("MANUAL_CONTROL_PASSWORD")
        if fallback and pwd != fallback:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    return pwd


def _verify_totp_code(code: str | None) -> tuple[bool, bool]:
    config = _current_security_settings().totp_config
    if not config or not getattr(config, "enabled", True):
        raise HTTPException(
            status.HTTP_501_NOT_IMPLEMENTED, detail="TOTP authentication not configured"
        )
    normalized = (code or "").strip()
    if not normalized:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="TOTP code required")
    backup_codes = list(getattr(config, "backup_codes", []) or [])
    if normalized in backup_codes:
        try:
            backup_codes.remove(normalized)
            config.backup_codes = backup_codes  # type: ignore[attr-defined]
        except Exception:
            pass
        return True, True
    try:
        totp = pyotp.TOTP(config.secret, digits=config.digits, interval=config.period)
    except Exception as exc:  # pragma: no cover - misconfiguration
        logger.error("Invalid TOTP configuration: %s", exc)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid TOTP configuration"
        ) from exc
    if not totp.verify(normalized, valid_window=1):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid TOTP code")
    return True, False


def _extract_cloudflare_assertion(request: Request | WebSocket) -> str | None:
    token = request.headers.get("CF-Access-Jwt-Assertion") or request.headers.get(
        "cf-access-jwt-assertion"
    )
    if not token and isinstance(request, Request):
        token = request.cookies.get("CF_Authorization")
    normalized = str(token or "").strip()
    return normalized or None


def _client_identifier(request: Request) -> str | None:
    header = request.headers.get("X-Client-Id")
    if header:
        return header
    request_id = request.headers.get("X-Request-ID")
    if request_id:
        return f"request:{request_id}"
    correlation = request.headers.get("X-Correlation-ID")
    if correlation:
        return f"correlation:{correlation}"
    if os.getenv("SIM_MODE", "0") == "1":
        return f"sim:{uuid.uuid4().hex}"
    return None


def _client_ip(request: Request) -> str | None:
    return client_ip(request)


def _extract_bearer_token(auth_header: str | None) -> str | None:
    if not auth_header:
        return None
    scheme, _, token = auth_header.strip().partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip() or None


def _store_bearer_manual_session(
    bearer_token: str,
    session: UserSession,
    timeout_minutes: int,
) -> dict[str, Any]:
    auth_session_id = str(getattr(session, "session_id", "") or "").strip()
    if not auth_session_id:
        raise AuthenticationError("Bearer authentication session is missing")
    payload = _decode_jwt_payload(bearer_token)
    expires_at = min(
        _manual_session_expiry(timeout_minutes, payload),
        session.expires_at,
    )
    seed = f"bearer:{hashlib.sha256(bearer_token.encode('utf-8')).hexdigest()}"
    return _store_manual_session(
        seed,
        expires_at,
        session.username,
        auth_session_id=auth_session_id,
        auth_source="bearer_token",
    )


async def _store_cloudflare_manual_session(
    request: Request,
    assertion: str,
    identity: VerifiedCloudflareIdentity,
    timeout_minutes: int,
) -> dict[str, Any]:
    auth_result = await primary_auth_service.authenticate_cloudflare(
        identity.principal,
        assertion_expires_at=identity.expires_at,
        client_ip=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    expires_at = min(
        _manual_session_expiry(timeout_minutes, identity.claims),
        auth_result.session.expires_at,
    )
    seed = f"cloudflare:{hashlib.sha256(assertion.encode('utf-8')).hexdigest()}"
    return _store_manual_session(
        seed,
        expires_at,
        identity.principal,
        auth_session_id=auth_result.session.session_id,
        auth_source="cloudflare_access",
    )


_WEBSOCKET_AUTH_PROTOCOL_PREFIX = "lawnberry.jwt."


def _extract_websocket_subprotocol_token(websocket: WebSocket) -> str | None:
    """Extract a browser WebSocket JWT without placing it in the request URL."""
    raw_protocols = websocket.headers.get("Sec-WebSocket-Protocol", "")
    for candidate in raw_protocols.split(","):
        protocol = candidate.strip()
        if protocol.startswith(_WEBSOCKET_AUTH_PROTOCOL_PREFIX):
            token = protocol.removeprefix(_WEBSOCKET_AUTH_PROTOCOL_PREFIX).strip()
            if token and len(token) <= 16384:
                return token
    return None


async def _require_session(request: Request) -> UserSession:
    token = _extract_bearer_token(request.headers.get("Authorization"))
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not primary_auth_service.revocation_store_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication session state unavailable",
        )
    session = await primary_auth_service.verify_token(token)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return session


async def _authorize_websocket(websocket: WebSocket) -> UserSession:
    """Authorize websocket connections.

    Priority:
    1) Authorization: Bearer <token>
    2) Browser WebSocket subprotocol carrying the signed LawnBerry JWT
    3) Cloudflare Access assertion headers (when present)
    4) Explicit SIM_MODE test/development sessions
    """
    # 1) Standard Bearer header
    token = _extract_bearer_token(websocket.headers.get("Authorization"))

    # 2) Browser WebSocket API cannot set Authorization headers. A subprotocol
    # carries the signed token through the upgrade without leaking it into URL
    # access logs or browser history.
    if not token:
        token = _extract_websocket_subprotocol_token(websocket)

    if token:
        session = await primary_auth_service.verify_token(token)
        if not session:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return session

    # 3) Cloudflare Access assertion, verified against the pinned team and app.
    cf_assert = _extract_cloudflare_assertion(websocket)
    if cf_assert:
        remote_ip = client_ip(websocket)
        try:
            identity = await cloudflare_access_verifier.verify(cf_assert)
        except CloudflareAccessError as exc:
            logger.warning("Cloudflare Access WebSocket verification failed: %s", exc)
            raise HTTPException(status_code=401, detail="Unauthorized") from exc
        result = await primary_auth_service.authenticate_cloudflare(
            identity.principal,
            assertion_expires_at=identity.expires_at,
            client_ip=remote_ip,
            user_agent=websocket.headers.get("User-Agent"),
        )
        return result.session

    # 4) Only explicit simulation mode may create a proofless development
    # session. Production proxy traffic is loopback by design and must never be
    # treated as authenticated merely because of its source address.
    if os.getenv("SIM_MODE", "0") == "1":
        host = client_ip(websocket)
        session = UserSession.create_operator_session(
            client_ip=str(host) if host else None,
            user_agent=websocket.headers.get("User-Agent"),
        )
        return session

    raise HTTPException(status_code=401, detail="Unauthorized")


# Endpoints


@router.post("/auth/login", response_model=AuthResponse)
async def auth_login(payload: AuthLoginRequest, request: Request):
    # Local authentication only. Cloudflare Access has a separate fail-closed
    # exchange so an invalid upstream assertion can never downgrade to password.
    credential = payload.credential
    if credential is None and payload.username is not None and payload.password is not None:
        # username/password path
        security_settings = _current_security_settings()
        
        # Check if a custom password has been configured
        if security_settings.password_hash:
            # Custom password is set - authenticate against it
            try:
                session = await primary_auth_service.authenticate_password(
                    payload.username,
                    payload.password,
                    client_ip=_client_ip(request),
                )
                user = UserOut(
                    id=session.user_id,
                    username=session.username,
                    role=session.security_context.role.value,
                    created_at=session.created_at,
                )
                result = primary_auth_service._issue_token_for_session(session)
                
                expires_in = max(0, int((result.expires_at - datetime.now(UTC)).total_seconds()))
                return AuthResponse(
                    access_token=result.token,
                    token=result.token,
                    expires_in=expires_in,
                    expires_at=result.expires_at,
                    user=user,
                )
            except AuthenticationError as exc:
                raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        else:
            # No custom password exists. Never translate a known username and
            # password pair into the configured operator secret; callers must
            # submit that secret explicitly through the credential field.
            raise HTTPException(
                status_code=401,
                detail="Invalid credentials",
            )

    client_identifier = _client_identifier(request)

    try:
        result = await primary_auth_service.authenticate(
            credential or "",
            client_identifier=client_identifier,
            client_ip=_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail, headers=exc.headers) from exc

    session = result.session
    user = UserOut(
        id=session.user_id,
        username=session.username,
        role=session.security_context.role.value,
        created_at=session.created_at,
    )
    expires_in = max(0, int((result.expires_at - datetime.now(UTC)).total_seconds()))

    return AuthResponse(
        access_token=result.token,
        token=result.token,
        expires_in=expires_in,
        expires_at=result.expires_at,
        user=user,
    )


@router.post("/auth/cloudflare", response_model=AuthResponse)
async def auth_cloudflare(request: Request):
    """Exchange a verified Cloudflare Access identity for a LawnBerry JWT."""
    token = _extract_cloudflare_assertion(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Cloudflare Access assertion missing",
        )
    try:
        identity = await cloudflare_access_verifier.verify(token)
    except CloudflareAccessError as exc:
        logger.warning("Cloudflare Access exchange failed: %s", exc)
        unavailable = "not configured" in str(exc) or "keys unavailable" in str(exc)
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
                if unavailable
                else status.HTTP_401_UNAUTHORIZED
            ),
            detail=(
                "Cloudflare Access verification unavailable"
                if unavailable
                else "Cloudflare Access assertion invalid"
            ),
        ) from exc

    try:
        result = await primary_auth_service.authenticate_cloudflare(
            identity.principal,
            assertion_expires_at=identity.expires_at,
            client_ip=_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers=exc.headers,
        ) from exc
    session = result.session
    return AuthResponse(
        access_token=result.token,
        token=result.token,
        expires_in=max(0, int((result.expires_at - datetime.now(UTC)).total_seconds())),
        expires_at=result.expires_at,
        user=UserOut(
            id=session.user_id,
            username=session.username,
            role=session.security_context.role.value,
            created_at=session.created_at,
        ),
    )


@router.post("/auth/refresh", response_model=RefreshResponse)
async def auth_refresh(request: Request):
    session = await _require_session(request)
    method = getattr(
        session.security_context.authentication_method,
        "value",
        session.security_context.authentication_method,
    )
    if method == AuthenticationMethod.CLOUDFLARE_ACCESS.value:
        assertion = _extract_cloudflare_assertion(request)
        if not assertion:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cloudflare Access assertion required for refresh",
            )
        try:
            identity = await cloudflare_access_verifier.verify(assertion)
            result = primary_auth_service.refresh_session_token(
                session,
                cloudflare_principal=identity.principal,
                cloudflare_expires_at=identity.expires_at,
            )
        except CloudflareAccessError as exc:
            logger.warning("Cloudflare Access refresh failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cloudflare Access refresh authorization invalid",
            ) from exc
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=exc.detail,
                headers=exc.headers,
            ) from exc
    else:
        try:
            result = primary_auth_service.refresh_session_token(session)
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=exc.detail,
                headers=exc.headers,
            ) from exc
    expires_in = max(0, int((result.expires_at - datetime.now(UTC)).total_seconds()))
    return RefreshResponse(
        access_token=result.token,
        token=result.token,
        expires_in=expires_in,
        expires_at=result.expires_at,
    )


@router.post("/auth/logout")
async def auth_logout(request: Request):
    session = await _require_session(request)
    try:
        terminated = await primary_auth_service.terminate_session(
            session.session_id,
            "user_logout",
        )
    except AuthStatePersistenceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to durably revoke authentication session",
        ) from exc
    if not terminated:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication session termination was not committed",
        )
    return {"ok": True}


@router.post("/auth/configure/password", response_model=SetPasswordResponse)
async def configure_password(payload: SetPasswordRequest, request: Request):
    """Configure a custom username/password for local authentication.
    
    Requires an active authenticated session (admin).
    Generates a bcrypt hash and stores it in the security config.
    """
    session = await _require_session(request)
    
    # Validate inputs
    if not payload.username or len(payload.username) < 1:
        raise HTTPException(status_code=400, detail="Username cannot be empty")
    if not payload.password or len(payload.password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 6 characters"
        )
    
    # Hash the password with bcrypt
    hashed = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    hashed_str = hashed.decode("utf-8")
    
    # Update the auth service config with new password hash
    primary_auth_service.config.password_hash = hashed_str
    
    # Also update the global security settings so login checks will see it
    from ...core import globals as global_state
    global_state._security_settings.password_hash = hashed_str
    
    # Also update rest module's reference if it has one (for backward compatibility)
    import sys
    rest_module = sys.modules.get("backend.src.api.rest")
    if rest_module is not None and hasattr(rest_module, '_security_settings'):
        rest_module._security_settings.password_hash = hashed_str
    
    logger.info(
        "Password configured",
        extra={
            "correlation_id": request.headers.get("X-Correlation-ID", "unknown"),
            "username": payload.username,
            "operator": session.username,
        },
    )
    
    return SetPasswordResponse(
        ok=True,
        message=f"Password configured successfully for username '{payload.username}'"
    )


@router.get("/auth/profile", response_model=UserOut)
async def auth_profile(request: Request):
    session = await _require_session(request)
    return UserOut(
        id=session.user_id,
        username=session.username,
        role=session.security_context.role.value,
        created_at=session.created_at,
    )


@router.get("/control/manual-unlock/status", response_model=ManualUnlockStatusResponse)
async def manual_unlock_status(request: Request):
    auth_header = request.headers.get("Authorization")
    bearer_token = _extract_bearer_token(auth_header)
    if bearer_token:
        try:
            session = await primary_auth_service.verify_token(bearer_token)
            if session:
                security_settings = _current_security_settings()
                timeout_minutes = getattr(security_settings, "session_timeout_minutes", 60)
                session_entry = _store_bearer_manual_session(
                    bearer_token,
                    session,
                    timeout_minutes,
                )
                return ManualUnlockStatusResponse(
                    authorized=True,
                    session_id=session_entry["session_id"],
                    expires_at=session_entry["expires_at"].isoformat(),
                    principal=session_entry.get("principal"),
                )
        except Exception as exc:
            logger.warning(f"Unable to restore manual control session from bearer token: {exc}")

    token = _extract_cloudflare_assertion(request)
    if not token:
        return ManualUnlockStatusResponse(
            authorized=False,
            reason="manual_control_session_unavailable",
        )

    try:
        identity = await cloudflare_access_verifier.verify(token)
    except CloudflareAccessError:
        return ManualUnlockStatusResponse(
            authorized=False,
            reason="cloudflare_access_invalid",
        )
    timeout_minutes = getattr(_current_security_settings(), "session_timeout_minutes", 60)
    try:
        session_entry = await _store_cloudflare_manual_session(
            request,
            token,
            identity,
            timeout_minutes,
        )
    except AuthenticationError:
        return ManualUnlockStatusResponse(
            authorized=False,
            reason="authentication_session_unavailable",
        )
    return ManualUnlockStatusResponse(
        authorized=True,
        session_id=session_entry["session_id"],
        expires_at=session_entry["expires_at"].isoformat(),
        principal=session_entry.get("principal"),
    )


@router.post("/control/manual-unlock", response_model=ManualUnlockResponse)
async def manual_unlock(request: Request, body: ManualUnlockRequest):
    # First, check if user is already authenticated via Bearer token
    # If they are, we can skip password verification
    auth_header = request.headers.get("Authorization")
    bearer_token = _extract_bearer_token(auth_header)

    if bearer_token:
        # User is already logged in, verify their session and grant manual control
        try:
            session = await primary_auth_service.verify_token(bearer_token)
            if session:
                timeout_minutes = getattr(
                    _current_security_settings(), "session_timeout_minutes", 60
                )
                session_entry = _store_bearer_manual_session(
                    bearer_token,
                    session,
                    timeout_minutes,
                )
                principal = session_entry.get("principal")

                logger.info(
                    "manual_control.unlock",
                    extra={"method": "bearer_token", "principal": principal},
                )
                return ManualUnlockResponse(
                    authorized=True,
                    session_id=session_entry["session_id"],
                    expires_at=session_entry["expires_at"].isoformat(),
                    principal=principal,
                    source="bearer_token",
                )
        except Exception as e:
            logger.warning(f"Bearer token verification failed: {e}")
            # Fall through to traditional auth methods

    # If no valid bearer token, proceed with traditional manual unlock methods
    method = (body.method or "").strip().lower()
    security_level = getattr(_current_security_settings(), "security_level", SecurityLevel.PASSWORD)
    if not method:
        if security_level == SecurityLevel.TUNNEL_AUTH:
            method = "cloudflare"
        elif security_level == SecurityLevel.GOOGLE_OAUTH:
            method = "google"
        elif security_level == SecurityLevel.TOTP:
            method = "totp"
        else:
            method = "password"
    if method in {"cloudflare", "cloudflare_tunnel_auth", "tunnel"}:
        token = _extract_cloudflare_assertion(request)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cloudflare Access token missing",
            )

        try:
            identity = await cloudflare_access_verifier.verify(token)
        except CloudflareAccessError as exc:
            logger.warning("Cloudflare manual unlock verification failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cloudflare Access assertion invalid",
            ) from exc
        timeout_minutes = getattr(_current_security_settings(), "session_timeout_minutes", 60)
        try:
            session_entry = await _store_cloudflare_manual_session(
                request,
                token,
                identity,
                timeout_minutes,
            )
        except AuthenticationError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=exc.detail,
                headers=exc.headers,
            ) from exc
        return ManualUnlockResponse(
            authorized=True,
            session_id=session_entry["session_id"],
            expires_at=session_entry["expires_at"].isoformat(),
            principal=session_entry.get("principal"),
            source="cloudflare_access",
        )

    if method in {"password", "password_only"}:
        password = _validate_manual_password(body.password)
        principal = _manual_unlock_principal(request, "password")
        timeout_minutes = getattr(_current_security_settings(), "session_timeout_minutes", 60)
        expires_at = _manual_session_expiry(timeout_minutes)
        seed_material = f"password:{principal}:{password}"
        seed = f"password:{hashlib.sha256(seed_material.encode('utf-8')).hexdigest()}"
        session_entry = _store_manual_session(seed, expires_at, principal)
        logger.info("manual_control.unlock", extra={"method": "password", "principal": principal})
        return ManualUnlockResponse(
            authorized=True,
            session_id=session_entry["session_id"],
            expires_at=session_entry["expires_at"].isoformat(),
            principal=principal,
            source="password",
        )

    if method in {"totp", "password_totp"}:
        totp_ok, backup_used = _verify_totp_code(body.totp_code)
        password = _validate_manual_password(body.password)
        principal = _manual_unlock_principal(request, "totp")
        timeout_minutes = getattr(_current_security_settings(), "session_timeout_minutes", 60)
        expires_at = _manual_session_expiry(timeout_minutes)
        seed_material = f"totp:{principal}:{body.totp_code or ''}:{password}:{'backup' if backup_used else 'primary'}"
        seed = f"totp:{hashlib.sha256(seed_material.encode('utf-8')).hexdigest()}"
        session_entry = _store_manual_session(seed, expires_at, principal)
        logger.info(
            "manual_control.unlock",
            extra={
                "method": "totp",
                "principal": principal,
                "backup_used": backup_used,
                "verified": totp_ok,
            },
        )
        return ManualUnlockResponse(
            authorized=True,
            session_id=session_entry["session_id"],
            expires_at=session_entry["expires_at"].isoformat(),
            principal=principal,
            source="totp_backup" if backup_used else "totp",
        )

    if method in {"google", "google_auth"}:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google-based manual unlock is not implemented",
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unknown manual unlock method",
    )
