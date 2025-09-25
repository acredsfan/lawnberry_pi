from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from typing import List, Optional

router = APIRouter()


class AuthRequest(BaseModel):
    credential: str


class AuthResponse(BaseModel):
    token: str
    expires_at: datetime


@router.post("/auth/login", response_model=AuthResponse)
def auth_login(payload: AuthRequest):
    # Placeholder auth: accept any non-empty credential, else 401
    if not payload.credential:
        raise HTTPException(status_code=401, detail="Authentication failed")
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    return AuthResponse(token="dummy-token", expires_at=exp)


class Position(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    accuracy: float | None = None
    gps_mode: str | None = None


class SafetyStatus(BaseModel):
    emergency_stop_active: bool = False
    tilt_detected: bool = False
    obstacle_detected: bool = False
    blade_safety_ok: bool = True
    safety_interlocks: list[str] = []


class MowerStatus(BaseModel):
    position: Position | None = None
    battery_percentage: float = 0
    power_mode: str = "NORMAL"
    navigation_state: str = "IDLE"
    safety_status: SafetyStatus = SafetyStatus()
    blade_active: bool = False
    last_updated: datetime = datetime.now(timezone.utc)


@router.get("/dashboard/status", response_model=MowerStatus)
def dashboard_status():
    # Placeholder data; will be wired to services later
    return MowerStatus()


# ----------------------- Map Zones -----------------------


class Point(BaseModel):
    latitude: float
    longitude: float


class Zone(BaseModel):
    id: str
    name: Optional[str] = None
    polygon: List[Point]
    priority: int = 0
    exclusion_zone: bool = False


_zones_store: List[Zone] = []


@router.get("/map/zones", response_model=List[Zone])
def get_map_zones():
    return _zones_store


@router.post("/map/zones", response_model=List[Zone])
def post_map_zones(zones: List[Zone]):
    global _zones_store
    _zones_store = zones
    return _zones_store


# --------------------- Map Locations ---------------------


class MapLocations(BaseModel):
    home: Optional[Position] = None
    am_sun: Optional[Position] = None
    pm_sun: Optional[Position] = None


_locations_store = MapLocations()


@router.get("/map/locations", response_model=MapLocations)
def get_map_locations():
    return _locations_store


@router.put("/map/locations", response_model=MapLocations)
def put_map_locations(locations: MapLocations):
    global _locations_store
    _locations_store = locations
    return _locations_store


# ----------------------- Telemetry -----------------------


@router.get("/dashboard/telemetry")
def dashboard_telemetry():
    # Minimal shape to satisfy contract tests; values are placeholders
    now = datetime.now(timezone.utc).isoformat()
    return {
        "timestamp": now,
        "battery": {
            "percentage": 0.0,
            "voltage": None,
        },
        "temperatures": {
            "cpu": None,
            "ambient": None,
        },
        "position": {
            "latitude": None,
            "longitude": None,
            "altitude": None,
            "accuracy": None,
            "gps_mode": None,
        },
        "imu": {
            "roll": None,
            "pitch": None,
            "yaw": None,
        },
    }


# ------------------------ Control ------------------------


class DriveCommand(BaseModel):
    mode: str  # e.g., "arcade", "tank"
    throttle: float | None = None
    turn: float | None = None


_blade_state = {"active": False}
_safety_state = {"emergency_stop_active": False}


@router.post("/control/drive")
def control_drive(cmd: DriveCommand):
    # Placeholder: accept the command if within basic numeric bounds
    if cmd.throttle is not None and not (-1.0 <= cmd.throttle <= 1.0):
        raise HTTPException(status_code=422, detail="throttle out of range")
    if cmd.turn is not None and not (-1.0 <= cmd.turn <= 1.0):
        raise HTTPException(status_code=422, detail="turn out of range")
    return {"accepted": True}


class BladeCommand(BaseModel):
    active: bool


@router.post("/control/blade")
def control_blade(cmd: BladeCommand):
    _blade_state["active"] = bool(cmd.active)
    return {"blade_active": _blade_state["active"]}


@router.post("/control/emergency-stop")
def control_emergency_stop():
    _safety_state["emergency_stop_active"] = True
    # Also force blade off for safety
    _blade_state["active"] = False
    return {"emergency_stop_active": True}
