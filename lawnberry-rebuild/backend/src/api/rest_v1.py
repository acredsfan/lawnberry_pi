"""FastAPI v1 API router for contract compliance with /api/v1 endpoints."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import List, Optional, Dict
import time
import hashlib
import json
from email.utils import format_datetime

router = APIRouter()


# --- Status Endpoint Models ---
class SafetyStatus(BaseModel):
    emergency_stop_active: bool = False
    tilt_detected: bool = False
    obstacle_detected: bool = False
    blade_safety_ok: bool = True
    safety_interlocks: List[str] = []


class SystemStatus(BaseModel):
    battery_percentage: Optional[float] = None
    navigation_state: str = "IDLE"
    safety_status: SafetyStatus = SafetyStatus()
    motor_status: str = "idle"
    last_updated: datetime = datetime.now(timezone.utc)


# --- Auth Models ---
class AuthLoginRequest(BaseModel):
    credential: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


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
    name: Optional[str] = None
    polygon: List[Point]
    priority: int = 0
    exclusion_zone: bool = False


# --- Job Models ---
class Job(BaseModel):
    id: str
    name: str
    schedule: str
    zones: List[str]
    priority: int = 1
    enabled: bool = True
    status: str = "pending"
    created_at: datetime = datetime.now(timezone.utc)
    last_run: Optional[datetime] = None


# --- Storage (in-memory for now) ---
_zones_store: List[Zone] = []
_jobs_store: List[Job] = []
_job_counter = 0


# --- API Endpoints ---

@router.get("/status", response_model=SystemStatus)
def get_status():
    """Get system status snapshot."""
    return SystemStatus(
        battery_percentage=85.2,  # Simulated value
        navigation_state="IDLE",
        safety_status=SafetyStatus(),
        motor_status="idle",
        last_updated=datetime.now(timezone.utc)
    )


@router.post("/auth/login", response_model=AuthResponse)
def auth_login(payload: AuthLoginRequest):
    """Start login flow (MFA compatible)."""
    # Determine provided credentials
    provided_credential = None
    if payload.credential:
        provided_credential = payload.credential
    elif payload.username and payload.password:
        # Simple compatibility: allow default admin/admin
        if payload.username == "admin" and payload.password == "admin":
            provided_credential = "operator123"
    
    # Validate credential
    if provided_credential != "operator123":
        raise HTTPException(status_code=401, detail="Authentication failed")
    
    # Issue token
    token = "lbp1-" + hashlib.sha256(f"v1-{time.time()}".encode()).hexdigest()[:32]
    user = UserResponse(id="admin", username="admin")
    
    return AuthResponse(
        access_token=token,
        user=user
    )


@router.get("/maps/zones", response_model=List[Zone])
def get_zones(request: Request):
    """List all zones."""
    # Create response data
    data = [zone.model_dump(mode="json") for zone in _zones_store]
    
    # Generate ETag from content
    body = json.dumps(data, sort_keys=True).encode()
    etag = hashlib.sha256(body).hexdigest()
    
    # Create headers with caching information
    last_modified = datetime.now(timezone.utc)
    headers = {
        "ETag": etag,
        "Last-Modified": format_datetime(last_modified),
        "Cache-Control": "public, max-age=30"
    }
    
    return JSONResponse(content=data, headers=headers)


@router.post("/maps/zones", response_model=List[Zone])
def create_zones(zones: List[Zone]):
    """Create or update zones."""
    global _zones_store
    
    # Basic validation: ensure polygon has at least 3 points
    for zone in zones:
        if len(zone.polygon) < 3:
            raise HTTPException(
                status_code=422, 
                detail=f"Zone {zone.id} polygon must have at least 3 points"
            )
    
    _zones_store = zones
    return _zones_store


@router.get("/mow/jobs", response_model=List[Job])
def get_jobs():
    """List all mowing jobs."""
    return _jobs_store


@router.post("/mow/jobs", response_model=Job, status_code=201)
def create_job(job_data: Dict):
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
        raise HTTPException(status_code=422, detail="Invalid schedule format (use HH:MM)")
    
    # Create job
    _job_counter += 1
    job = Job(
        id=f"job-{_job_counter:03d}",
        name=job_data["name"],
        schedule=schedule,
        zones=job_data["zones"],
        priority=job_data.get("priority", 1),
        enabled=job_data.get("enabled", True)
    )
    
    _jobs_store.append(job)
    return job