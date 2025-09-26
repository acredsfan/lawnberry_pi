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


# ----------------------- Planning ------------------------


class PlanningJob(BaseModel):
    id: str
    name: str
    schedule: str  # e.g., "08:00" for time-based scheduling
    zones: List[str]  # zone IDs to mow
    priority: int = 1
    enabled: bool = True
    created_at: datetime = datetime.now(timezone.utc)
    last_run: Optional[datetime] = None
    status: str = "pending"  # pending, running, completed, failed


_jobs_store: List[PlanningJob] = []
_job_counter = 0


@router.get("/planning/jobs", response_model=List[PlanningJob])
def get_planning_jobs():
    return _jobs_store


@router.post("/planning/jobs", response_model=PlanningJob, status_code=201)
def post_planning_job(job_data: dict):
    global _job_counter
    _job_counter += 1
    
    # Create new job with generated ID
    job = PlanningJob(
        id=f"job-{_job_counter:03d}",
        name=job_data["name"],
        schedule=job_data["schedule"],
        zones=job_data["zones"],
        priority=job_data.get("priority", 1),
        enabled=job_data.get("enabled", True)
    )
    
    _jobs_store.append(job)
    return job


@router.delete("/planning/jobs/{jobId}", status_code=204)
def delete_planning_job(jobId: str):
    global _jobs_store
    # Find and remove the job
    for i, job in enumerate(_jobs_store):
        if job.id == jobId:
            _jobs_store.pop(i)
            return
    
    # Job not found
    raise HTTPException(status_code=404, detail="Job not found")


# ------------------------ AI/ML ---------------------------


class Dataset(BaseModel):
    id: str
    name: str
    type: str  # "object_detection", "path_learning", "grass_classification"
    size_mb: float
    last_updated: datetime
    status: str = "ready"  # ready, training, error


_datasets_store = [
    Dataset(
        id="grass-v1",
        name="Grass Classification v1",
        type="grass_classification",
        size_mb=45.2,
        last_updated=datetime.now(timezone.utc)
    ),
    Dataset(
        id="obstacles-v2",
        name="Obstacle Detection v2",
        type="object_detection", 
        size_mb=128.7,
        last_updated=datetime.now(timezone.utc)
    )
]


@router.get("/ai/model/datasets", response_model=List[Dataset])
def get_ai_datasets():
    return _datasets_store


@router.get("/ai/export/path-data")
def export_path_data(format: str = "csv"):
    # Placeholder export functionality
    if format not in ["csv", "json"]:
        raise HTTPException(status_code=422, detail="Unsupported format")
    
    return {
        "export_url": f"/data/exports/paths-{datetime.now().strftime('%Y%m%d')}.{format}",
        "format": format,
        "size_estimate_mb": 12.3,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    }


# ----------------------- Settings ------------------------


class SystemConfig(BaseModel):
    mowing_height_mm: int = 30
    cutting_speed: float = 0.8  # m/s
    edge_cutting_enabled: bool = True
    weather_pause_enabled: bool = True
    rain_threshold_mm: float = 2.0
    wind_threshold_kmh: float = 25.0
    charging_return_threshold: float = 20.0  # battery percentage
    safety_tilt_threshold_degrees: float = 30.0
    gps_required_accuracy_m: float = 2.0
    obstacle_detection_sensitivity: str = "medium"  # low, medium, high
    blade_engagement_delay_ms: int = 500
    emergency_stop_timeout_s: int = 30


_config_store = SystemConfig()


@router.get("/settings/config", response_model=SystemConfig)
def get_system_config():
    return _config_store


@router.put("/settings/config", response_model=SystemConfig)
def put_system_config(config: SystemConfig):
    global _config_store
    _config_store = config
    return _config_store
