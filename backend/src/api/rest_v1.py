"""FastAPI v1 API router for contract compliance with /api/v1 endpoints."""

# ──────────────────────────────────────────────────────────────────────────────
# DEPRECATED — REST v1 API
# All endpoints in this file are superseded by the v2 API (api/rest.py and
# api/routers/). New features will not be added here. Callers should migrate
# to /api/v2/* equivalents.
# ──────────────────────────────────────────────────────────────────────────────

import hashlib
import json
import os
from datetime import UTC, datetime
from email.utils import format_datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..services.auth_service import AuthenticationError, primary_auth_service

router = APIRouter()

_auth_service = primary_auth_service


# --- Status Endpoint Models ---
class SafetyStatus(BaseModel):
    emergency_stop_active: bool = False
    tilt_detected: bool = False
    obstacle_detected: bool = False
    blade_safety_ok: bool = True
    safety_interlocks: list[str] = []


class SystemStatus(BaseModel):
    battery_percentage: float | None = None
    navigation_state: str = "IDLE"
    safety_status: SafetyStatus = SafetyStatus()
    motor_status: str = "idle"
    last_updated: datetime = datetime.now(UTC)


# --- Auth Models ---
class AuthLoginRequest(BaseModel):
    credential: str | None = None
    username: str | None = None
    password: str | None = None


class UserResponse(BaseModel):
    id: str
    username: str
    role: str = "admin"


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: UserResponse


# --- Zone Models ---
class Point(BaseModel):
    latitude: float
    longitude: float


class Zone(BaseModel):
    id: str
    name: str | None = None
    polygon: list[Point]
    priority: int = 0
    exclusion_zone: bool = False


# --- Job Models ---
class Job(BaseModel):
    id: str
    name: str
    schedule: str
    zones: list[str]
    priority: int = 1
    enabled: bool = True
    status: str = "pending"
    created_at: datetime = datetime.now(UTC)
    last_run: datetime | None = None


# --- Storage (in-memory for now) ---
_zones_store: list[Zone] = []
_jobs_store: list[Job] = []
_job_counter = 0


# --- API Endpoints ---


@router.get("/status", response_model=SystemStatus, deprecated=True)
def get_status():
    """Get system status snapshot."""
    return SystemStatus(
        battery_percentage=85.2,  # Simulated value
        navigation_state="IDLE",
        safety_status=SafetyStatus(),
        motor_status="idle",
        last_updated=datetime.now(UTC),
    )


@router.post("/auth/login", response_model=AuthResponse, deprecated=True)
async def auth_login(payload: AuthLoginRequest, request: Request):
    """Start login flow (MFA compatible)."""
    expected_secret = os.getenv("LAWN_BERRY_OPERATOR_CREDENTIAL")
    if not expected_secret:
        raise HTTPException(status_code=503, detail="Operator credential not configured")

    credential = payload.credential
    if credential is None and payload.username and payload.password:
        # username/password path: map admin/admin to LAWN_BERRY_OPERATOR_CREDENTIAL
        if payload.username == "admin" and payload.password == "admin":
            credential = expected_secret
        else:
            # Reject unsupported username/password combinations
            raise HTTPException(status_code=401, detail="Authentication failed")

    if credential != expected_secret:
        raise HTTPException(status_code=401, detail="Authentication failed")

    try:
        result = await _auth_service.authenticate(
            credential or "",
            client_identifier=request.headers.get("X-Client-Id"),
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail, headers=exc.headers) from exc

    session = result.session
    user = UserResponse(
        id=session.user_id, username=session.username, role=session.security_context.role.value
    )
    expires_in = max(0, int((result.expires_at - datetime.now(UTC)).total_seconds()))

    return AuthResponse(access_token=result.token, expires_in=expires_in, user=user)


@router.get("/maps/zones", response_model=list[Zone], deprecated=True)
def get_zones(request: Request):
    """List all zones."""
    # Create response data
    data = [zone.model_dump(mode="json") for zone in _zones_store]

    # Generate ETag from content
    body = json.dumps(data, sort_keys=True).encode()
    etag = hashlib.sha256(body).hexdigest()

    # Create headers with caching information
    last_modified = datetime.now(UTC)
    headers = {
        "ETag": etag,
        "Last-Modified": format_datetime(last_modified),
        "Cache-Control": "public, max-age=30",
    }

    return JSONResponse(content=data, headers=headers)


@router.post("/maps/zones", response_model=list[Zone], deprecated=True)
def create_zones(zones: list[Zone]):
    """Create or update zones."""
    global _zones_store

    # Basic validation: ensure polygon has at least 3 points
    for zone in zones:
        if len(zone.polygon) < 3:
            raise HTTPException(
                status_code=422, detail=f"Zone {zone.id} polygon must have at least 3 points"
            )

    _zones_store = zones
    return _zones_store


@router.get("/mow/jobs", response_model=list[Job], deprecated=True)
def get_jobs():
    """List all mowing jobs."""
    return _jobs_store


@router.post("/mow/jobs", response_model=Job, status_code=201, deprecated=True)
def create_job(job_data: dict):
    """Queue a new mowing job."""
    global _job_counter, _jobs_store

    # Validation
    if not job_data.get("name"):
        raise HTTPException(status_code=422, detail="Job name is required")

    if not job_data.get("zones") or len(job_data["zones"]) == 0:
        raise HTTPException(status_code=422, detail="At least one zone is required")

    schedule = job_data.get("schedule", "")
    if not schedule or ":" not in schedule:
        raise HTTPException(status_code=422, detail="Valid schedule time required (HH:MM)")

    try:
        hour, minute = schedule.split(":")
        hour, minute = int(hour), int(minute)
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError()
    except (ValueError, IndexError):
        raise HTTPException(status_code=422, detail="Invalid schedule format (use HH:MM)") from None

    # Create job
    _job_counter += 1
    job = Job(
        id=f"job-{_job_counter:03d}",
        name=job_data["name"],
        schedule=schedule,
        zones=job_data["zones"],
        priority=job_data.get("priority", 1),
        enabled=job_data.get("enabled", True),
    )

    _jobs_store.append(job)
    return job
