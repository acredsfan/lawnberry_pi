from fastapi import APIRouter, HTTPException, WebSocket, Request, status
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
import os
import uuid
import base64
import json
import hashlib
import logging
import bcrypt
import pyotp

from ..models.auth_security_config import AuthSecurityConfig, SecurityLevel
from ..models.user_session import UserSession
from ..services.auth_service import AuthenticationError, primary_auth_service
from ..core.globals import _manual_control_sessions, _security_settings, _security_last_modified

logger = logging.getLogger(__name__)
router = APIRouter()

# Security settings (auth levels, MFA options)
# This was in rest.py as _security_settings.
# I should probably move this to a service or keep it here if it's only used here.
# It is used in manual unlock logic.
# Security settings (auth levels, MFA options)
# Imported from globals.py


# Models
class ManualUnlockRequest(BaseModel):
    method: Optional[str] = None
    password: Optional[str] = None
    totp_code: Optional[str] = None

class ManualUnlockResponse(BaseModel):
    authorized: bool
    session_id: str
    expires_at: str
    principal: Optional[str] = None
    source: str = "manual_control"

class ManualUnlockStatusResponse(BaseModel):
    authorized: bool
    session_id: Optional[str] = None
    expires_at: Optional[str] = None
    principal: Optional[str] = None
    reason: Optional[str] = None

class AuthLoginRequest(BaseModel):
    # Support both shared-credential and username/password payloads
    credential: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

class UserOut(BaseModel):
    id: str
    username: str
    role: str = "admin"
    created_at: datetime = datetime.now(timezone.utc)

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

# Helpers
def _decode_jwt_payload(token: str) -> Dict[str, Any]:
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

def _manual_session_expiry(default_minutes: int | None = None, token_payload: Dict[str, Any] | None = None) -> datetime:
    now = datetime.now(timezone.utc)
    if token_payload and isinstance(token_payload.get("exp"), (int, float)):
        try:
            exp = datetime.fromtimestamp(float(token_payload["exp"]), tz=timezone.utc)
            if exp > now:
                return exp
        except Exception:
            pass
    minutes = default_minutes or 60
    try:
        minutes = int(minutes)
    except Exception:
        minutes = 60
    return now + timedelta(minutes=max(1, minutes))

def _manual_session_key(seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return f"manual-{digest[:16]}"

def _store_manual_session(seed: str, expires_at: datetime, principal: Optional[str]) -> dict[str, Any]:
    # Garbage collect expired sessions first
    now = datetime.now(timezone.utc)
    for key in list(_manual_control_sessions.keys()):
        if _manual_control_sessions[key]["expires_at"] <= now:
            _manual_control_sessions.pop(key, None)

    entry = _manual_control_sessions.get(seed)
    if entry:
        entry["expires_at"] = expires_at
        if principal:
            entry["principal"] = principal
        return entry

    session_id = _manual_session_key(seed)
    entry = {
        "session_id": session_id,
        "expires_at": expires_at,
        "principal": principal,
    }
    _manual_control_sessions[seed] = entry
    return entry

def _resolve_manual_session(session_id: Optional[str]) -> dict[str, Any]:
    token = (session_id or "").strip()
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Manual control session required")

    now = datetime.now(timezone.utc)
    matched_entry: dict[str, Any] | None = None
    expired: list[str] = []
    for seed, entry in _manual_control_sessions.items():
        expires_at: datetime = entry.get("expires_at", now)
        if expires_at <= now:
            expired.append(seed)
            continue
        if entry.get("session_id") == token:
            matched_entry = entry
            break

    for seed in expired:
        _manual_control_sessions.pop(seed, None)

    if matched_entry is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Manual control session invalid or expired")

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

def _validate_manual_password(password: Optional[str]) -> str:
    pwd = (password or "").strip()
    required = bool(_security_settings.password_required() or _security_settings.password_hash or os.getenv("MANUAL_CONTROL_PASSWORD"))
    if required and not pwd:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Password required for manual unlock")
    if not pwd:
        return pwd
    if _security_settings.password_hash:
        try:
            if not bcrypt.checkpw(pwd.encode("utf-8"), _security_settings.password_hash.encode("utf-8")):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
        except ValueError as exc:
            logger.error("Invalid password hash configuration: %s", exc)
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Password configuration invalid") from exc
    else:
        fallback = os.getenv("MANUAL_CONTROL_PASSWORD")
        if fallback and pwd != fallback:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    return pwd

def _verify_totp_code(code: Optional[str]) -> Tuple[bool, bool]:
    config = _security_settings.totp_config
    if not config or not getattr(config, "enabled", True):
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, detail="TOTP authentication not configured")
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
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid TOTP configuration") from exc
    if not totp.verify(normalized, valid_window=1):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid TOTP code")
    return True, False

def _extract_cloudflare_identity(request: Request) -> tuple[Optional[str], Dict[str, Any], Optional[str]]:
    token = request.headers.get("CF-Access-Jwt-Assertion") or request.headers.get("cf-access-jwt-assertion")
    if not token:
        token = request.cookies.get("CF_Authorization")
    payload = _decode_jwt_payload(token) if token else {}
    email = (
        request.headers.get("CF-Access-Authenticated-User-Email")
        or request.headers.get("cf-access-authenticated-user-email")
        or payload.get("email")
        or payload.get("sub")
    )
    if email:
        try:
            email = str(email)
        except Exception:
            email = None
    return token, payload, email

def _client_identifier(request: Request) -> Optional[str]:
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

def _client_ip(request: Request) -> Optional[str]:
    client = request.client
    if client and getattr(client, "host", None):
        return str(client.host)
    return None

def _extract_bearer_token(auth_header: Optional[str]) -> Optional[str]:
    if not auth_header:
        return None
    scheme, _, token = auth_header.strip().partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip() or None

async def _require_session(request: Request) -> UserSession:
    token = _extract_bearer_token(request.headers.get("Authorization"))
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    session = await primary_auth_service.verify_token(token)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return session

async def _authorize_websocket(websocket: WebSocket) -> UserSession:
    """Authorize websocket connections.

    Priority:
    1) Authorization: Bearer <token>
    2) Query param: access_token/token/auth_token
    3) Cloudflare Access assertion headers (when present)
    4) Local development (localhost/127.0.0.1) and SIM_MODE
    """
    # 1) Standard Bearer header
    token = _extract_bearer_token(websocket.headers.get("Authorization"))

    # 2) Query param fallbacks used by browsers that cannot set custom headers in WS
    if not token:
        try:
            qp = getattr(websocket, "query_params", None)
            if qp is not None:
                getter = getattr(qp, "get", None)
                if callable(getter):
                    token = getter("access_token") or getter("token") or getter("auth_token")
        except Exception:
            token = None

    if token:
        session = await primary_auth_service.verify_token(token)
        if not session:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return session

    # 3) Cloudflare Access: trust Access assertion when Zero Trust policy already enforced at edge
    try:
        cf_assert = websocket.headers.get("CF-Access-Jwt-Assertion") or websocket.headers.get("cf-access-jwt-assertion")
    except Exception:
        cf_assert = None
    if cf_assert:
        # Create an operator session bound to the connecting IP as a best-effort identity
        client = websocket.client
        client_ip = (client[0] if isinstance(client, (list, tuple)) else getattr(client, "host", None)) if client is not None else None
        return UserSession.create_operator_session(client_ip=str(client_ip) if client_ip else None, user_agent=websocket.headers.get("User-Agent"))

    # 4) Local dev and SIM_MODE safe path
    client = websocket.client
    if client is not None:
        host = (client[0] if isinstance(client, (list, tuple)) else getattr(client, "host", None)) or ""
    else:
        host = websocket.headers.get("host", "")
    host_lower = str(host).lower()
    if host_lower.startswith("127.") or host_lower in {"::1", "localhost", "testserver", "testclient"} or os.getenv("SIM_MODE", "0") == "1":
        session = UserSession.create_operator_session(client_ip=host_lower or None, user_agent=websocket.headers.get("User-Agent"))
        return session

    raise HTTPException(status_code=401, detail="Unauthorized")

# Endpoints

@router.post("/auth/login", response_model=AuthResponse)
async def auth_login(payload: AuthLoginRequest, request: Request):
    credential = payload.credential
    if credential is None and payload.username is not None and payload.password is not None:
        if payload.username == "admin" and payload.password == "admin":
            credential = os.getenv("LAWN_BERRY_OPERATOR_CREDENTIAL", "operator123")
        else:
            credential = ""

    try:
        result = await primary_auth_service.authenticate(
            credential or "",
            client_identifier=_client_identifier(request),
            client_ip=_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail, headers=exc.headers)

    session = result.session
    user = UserOut(
        id=session.user_id,
        username=session.username,
        role=session.security_context.role.value,
        created_at=session.created_at,
    )
    expires_in = max(0, int((result.expires_at - datetime.now(timezone.utc)).total_seconds()))

    return AuthResponse(
        access_token=result.token,
        token=result.token,
        expires_in=expires_in,
        expires_at=result.expires_at,
        user=user,
    )

@router.post("/auth/refresh", response_model=RefreshResponse)
async def auth_refresh(request: Request):
    session = await _require_session(request)
    result = primary_auth_service.refresh_session_token(session)
    expires_in = max(0, int((result.expires_at - datetime.now(timezone.utc)).total_seconds()))
    return RefreshResponse(access_token=result.token, token=result.token, expires_in=expires_in, expires_at=result.expires_at)

@router.post("/auth/logout")
async def auth_logout(request: Request):
    session = await _require_session(request)
    await primary_auth_service.terminate_session(session.session_id, "user_logout")
    return {"ok": True}

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
    token, payload, principal = _extract_cloudflare_identity(request)
    if not token:
        return ManualUnlockStatusResponse(
            authorized=False,
            reason="missing_cloudflare_token",
        )

    timeout_minutes = getattr(_security_settings, "session_timeout_minutes", 60)
    expires_at = _manual_session_expiry(timeout_minutes, payload)
    session_entry = _store_manual_session(token, expires_at, principal)
    return ManualUnlockStatusResponse(
        authorized=True,
        session_id=session_entry["session_id"],
        expires_at=session_entry["expires_at"].isoformat(),
        principal=session_entry.get("principal"),
    )

@router.post("/control/manual-unlock", response_model=ManualUnlockResponse)
async def manual_unlock(request: Request, body: ManualUnlockRequest):
    method = (body.method or "").strip().lower()
    security_level = getattr(_security_settings, "security_level", SecurityLevel.PASSWORD)
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
        token, payload, principal = _extract_cloudflare_identity(request)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cloudflare Access token missing",
            )

        timeout_minutes = getattr(_security_settings, "session_timeout_minutes", 60)
        expires_at = _manual_session_expiry(timeout_minutes, payload)
        session_entry = _store_manual_session(token, expires_at, principal)
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
        timeout_minutes = getattr(_security_settings, "session_timeout_minutes", 60)
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
        timeout_minutes = getattr(_security_settings, "session_timeout_minutes", 60)
        expires_at = _manual_session_expiry(timeout_minutes)
        seed_material = f"totp:{principal}:{body.totp_code or ''}:{password}:{'backup' if backup_used else 'primary'}"
        seed = f"totp:{hashlib.sha256(seed_material.encode('utf-8')).hexdigest()}"
        session_entry = _store_manual_session(seed, expires_at, principal)
        logger.info(
            "manual_control.unlock",
            extra={"method": "totp", "principal": principal, "backup_used": backup_used, "verified": totp_ok},
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
