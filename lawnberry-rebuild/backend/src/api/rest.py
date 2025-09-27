from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Set
from pathlib import Path
import os
import json
import asyncio
import time
import hashlib
from email.utils import format_datetime, parsedate_to_datetime
from ..core.persistence import persistence
from ..services.hw_selftest import run_selftest
from ..services.weather_service import weather_service

router = APIRouter()

# WebSocket Hub for real-time communication
class WebSocketHub:
    def __init__(self):
        self.clients: Dict[str, WebSocket] = {}
        self.subscriptions: Dict[str, Set[str]] = {}  # topic -> client_ids
        self.telemetry_cadence_hz = 5.0
        self._telemetry_task: Optional[asyncio.Task] = None
        # Hardware integration
        self._sensor_manager = None  # lazy init to avoid hardware deps on CI
        
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.clients[client_id] = websocket
        await websocket.send_text(json.dumps({
            "event": "connection.established",
            "client_id": client_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }))
        
    def disconnect(self, client_id: str):
        if client_id in self.clients:
            del self.clients[client_id]
        # Remove from all subscriptions
        for topic, subscribers in self.subscriptions.items():
            subscribers.discard(client_id)
            
    async def subscribe(self, client_id: str, topic: str):
        if topic not in self.subscriptions:
            self.subscriptions[topic] = set()
        self.subscriptions[topic].add(client_id)
        
        # Send confirmation
        if client_id in self.clients:
            await self.clients[client_id].send_text(json.dumps({
                "event": "subscription.confirmed",
                "topic": topic,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            
    async def set_cadence(self, client_id: str, cadence_hz: float):
        # Clamp cadence between 1-10 Hz
        cadence_hz = max(1.0, min(10.0, cadence_hz))
        self.telemetry_cadence_hz = cadence_hz
        
        # Send confirmation
        if client_id in self.clients:
            await self.clients[client_id].send_text(json.dumps({
                "event": "cadence.updated",
                "cadence_hz": cadence_hz,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            
    async def broadcast_to_topic(self, topic: str, data: dict):
        if topic not in self.subscriptions:
            return
            
        message = json.dumps({
            "event": "telemetry.data",
            "topic": topic,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        })
        
        disconnected_clients = []
        for client_id in self.subscriptions[topic]:
            if client_id in self.clients:
                try:
                    await self.clients[client_id].send_text(message)
                except:
                    disconnected_clients.append(client_id)
                    
        # Clean up disconnected clients
        for client_id in disconnected_clients:
            self.disconnect(client_id)
            
    async def start_telemetry_loop(self):
        if self._telemetry_task is not None:
            return
        self._telemetry_task = asyncio.create_task(self._telemetry_loop())
        
    async def stop_telemetry_loop(self):
        if self._telemetry_task:
            self._telemetry_task.cancel()
            try:
                await self._telemetry_task
            except asyncio.CancelledError:
                pass
            self._telemetry_task = None
            
    async def _telemetry_loop(self):
        while True:
            try:
                telemetry_data = await self._generate_telemetry()
                
                await self.broadcast_to_topic("telemetry/updates", telemetry_data)
                
                # Wait based on cadence
                await asyncio.sleep(1.0 / self.telemetry_cadence_hz)
                
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)

    async def _generate_telemetry(self) -> dict:
        """Generate telemetry from hardware when SIM_MODE=0, otherwise simulated.

        Safe on CI: imports and hardware init are lazy and wrapped in try/except.
        """
        # SIM_MODE: default to simulation unless explicitly set to '0'
        sim_mode = os.getenv("SIM_MODE", "1") != "0"

        if not sim_mode:
            # Try to read from SensorManager
            try:
                if self._sensor_manager is None:
                    # Lazy import to avoid unnecessary deps in CI
                    from ..services.sensor_manager import SensorManager  # type: ignore
                    self._sensor_manager = SensorManager()
                    # Initialize once (async)
                    await self._sensor_manager.initialize()

                if getattr(self._sensor_manager, "initialized", False):
                    data = await self._sensor_manager.read_all_sensors()
                    # Map to telemetry payload expected by clients
                    battery_pct = None
                    batt_v = None
                    if data.power and data.power.battery_voltage is not None:
                        batt_v = data.power.battery_voltage
                        # Rough estimate of percentage from voltage for 12V lead-acid/LiFePO4 profiles
                        # This is placeholder logic; real calibration to be added later
                        battery_pct = max(0.0, min(100.0, (batt_v - 11.0) / (13.0 - 11.0) * 100.0))

                    pos = data.gps
                    imu = data.imu
                    telemetry = {
                        "source": "hardware",
                        "battery": {"percentage": battery_pct, "voltage": batt_v},
                        "position": {
                            "latitude": getattr(pos, "latitude", None),
                            "longitude": getattr(pos, "longitude", None),
                            "altitude": getattr(pos, "altitude", None),
                            "accuracy": getattr(pos, "accuracy", None),
                            "gps_mode": getattr(pos, "mode", None),
                        },
                        "imu": {
                            "roll": getattr(imu, "roll", None),
                            "pitch": getattr(imu, "pitch", None),
                            "yaw": getattr(imu, "yaw", None),
                        },
                        "motor_status": "idle",
                        "safety_state": "safe",
                        "uptime_seconds": time.time(),
                    }
                    return telemetry
            except Exception:
                # Fall back to simulation if hardware path fails
                pass

        # Simulated data
        return {
            "source": "simulated",
            "battery": {"percentage": 85.2, "voltage": 12.6},
            "position": {"latitude": 40.7128, "longitude": -74.0060},
            "motor_status": "idle",
            "safety_state": "safe",
            "uptime_seconds": time.time(),
        }

# Global WebSocket hub instance
websocket_hub = WebSocketHub()
_app_start_time = time.time()


class AuthRequest(BaseModel):
    credential: str


class AuthResponse(BaseModel):
    token: str
    expires_at: datetime


# ------------------------ Auth Hardening ------------------------

# Rate limiting and lockout (simple in-memory, per client)
AUTH_WINDOW_SECONDS = 60
AUTH_MAX_ATTEMPTS_PER_WINDOW = 3
AUTH_LOCKOUT_FAILED_ATTEMPTS = 3
AUTH_LOCKOUT_SECONDS = 60

_auth_attempts: Dict[str, list[float]] = {}
_auth_failed_counts: Dict[str, int] = {}
_auth_lockout_until: Dict[str, float] = {}


@router.post("/auth/login", response_model=AuthResponse)
def auth_login(payload: AuthRequest, request: Request):
    now = time.time()
    client_id = request.headers.get("X-Client-Id") or "global"

    # Lockout check
    lock_until = _auth_lockout_until.get(client_id)
    if lock_until and now < lock_until:
        retry_after = int(max(1, lock_until - now))
        raise HTTPException(status_code=429, detail="Too Many Requests", headers={"Retry-After": str(retry_after)})

    # Rate limit: prune old attempts, then check
    attempts = _auth_attempts.get(client_id, [])
    cutoff = now - AUTH_WINDOW_SECONDS
    attempts = [t for t in attempts if t >= cutoff]
    if len(attempts) >= AUTH_MAX_ATTEMPTS_PER_WINDOW:
        # Compute retry-after based on oldest attempt in window
        oldest = min(attempts)
        retry_after = int(max(1, AUTH_WINDOW_SECONDS - (now - oldest)))
        _auth_attempts[client_id] = attempts  # persist pruned list
        raise HTTPException(status_code=429, detail="Too Many Requests", headers={"Retry-After": str(retry_after)})

    # Record this attempt before validating (rate limit applies to all attempts)
    attempts.append(now)
    _auth_attempts[client_id] = attempts

    # Validate credential
    if not payload.credential:
        # Increment failed count
        failed = _auth_failed_counts.get(client_id, 0) + 1
        _auth_failed_counts[client_id] = failed
        # Activate lockout after threshold, but this attempt still returns 401
        if failed >= AUTH_LOCKOUT_FAILED_ATTEMPTS:
            _auth_lockout_until[client_id] = now + AUTH_LOCKOUT_SECONDS
        raise HTTPException(status_code=401, detail="Authentication failed")

    # Successful login resets failed count
    _auth_failed_counts[client_id] = 0
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
_zones_last_modified: datetime = datetime.now(timezone.utc)


@router.get("/map/zones", response_model=List[Zone])
def get_map_zones(request: Request):
    data = [z.model_dump(mode="json") for z in _zones_store]
    body = json.dumps(data, sort_keys=True).encode()
    etag = hashlib.sha256(body).hexdigest()
    inm = request.headers.get("if-none-match")
    ims = request.headers.get("if-modified-since")
    if inm == etag:
        return JSONResponse(status_code=304, content=None)
    if ims:
        try:
            ims_dt = parsedate_to_datetime(ims)
            if ims_dt.tzinfo is None:
                ims_dt = ims_dt.replace(tzinfo=timezone.utc)
            if ims_dt >= _zones_last_modified.replace(microsecond=0):
                return JSONResponse(status_code=304, content=None)
        except Exception:
            pass
    headers = {
        "ETag": etag,
        "Last-Modified": format_datetime(_zones_last_modified),
        "Cache-Control": "public, max-age=30",
    }
    return JSONResponse(content=data, headers=headers)


@router.post("/map/zones", response_model=List[Zone])
def post_map_zones(zones: List[Zone]):
    global _zones_store
    _zones_store = zones
    global _zones_last_modified
    _zones_last_modified = datetime.now(timezone.utc)
    return _zones_store


# --------------------- Map Locations ---------------------


class MapLocations(BaseModel):
    home: Optional[Position] = None
    am_sun: Optional[Position] = None
    pm_sun: Optional[Position] = None


_locations_store = MapLocations()
_locations_last_modified: datetime = datetime.now(timezone.utc)


@router.get("/map/locations", response_model=MapLocations)
def get_map_locations(request: Request):
    data = _locations_store.model_dump(mode="json")
    body = json.dumps(data, sort_keys=True).encode()
    etag = hashlib.sha256(body).hexdigest()
    inm = request.headers.get("if-none-match")
    ims = request.headers.get("if-modified-since")
    if inm == etag:
        return JSONResponse(status_code=304, content=None)
    if ims:
        try:
            ims_dt = parsedate_to_datetime(ims)
            if ims_dt.tzinfo is None:
                ims_dt = ims_dt.replace(tzinfo=timezone.utc)
            if ims_dt >= _locations_last_modified.replace(microsecond=0):
                return JSONResponse(status_code=304, content=None)
        except Exception:
            pass
    headers = {
        "ETag": etag,
        "Last-Modified": format_datetime(_locations_last_modified),
        "Cache-Control": "public, max-age=30",
    }
    return JSONResponse(content=data, headers=headers)


@router.put("/map/locations", response_model=MapLocations)
def put_map_locations(locations: MapLocations):
    global _locations_store
    _locations_store = locations
    global _locations_last_modified
    _locations_last_modified = datetime.now(timezone.utc)
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
    # Audit
    persistence.add_audit_log("control.drive", details=cmd.model_dump())
    return {"accepted": True}


class BladeCommand(BaseModel):
    active: bool


@router.post("/control/blade")
def control_blade(cmd: BladeCommand):
    _blade_state["active"] = bool(cmd.active)
    persistence.add_audit_log("control.blade", details=cmd.model_dump())
    return {"blade_active": _blade_state["active"]}


@router.post("/control/emergency-stop")
def control_emergency_stop():
    _safety_state["emergency_stop_active"] = True
    # Also force blade off for safety
    _blade_state["active"] = False
    persistence.add_audit_log("control.emergency_stop")
    return {"emergency_stop_active": True}


# ----------------------- Planning Jobs -----------------------


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


# -------------------------- AI Datasets --------------------------


class Dataset(BaseModel):
    id: str
    name: str
    description: str
    image_count: int
    labeled_count: int
    categories: List[str]
    created_at: datetime
    last_updated: datetime


class ExportRequest(BaseModel):
    format: str  # "COCO" or "YOLO"
    include_unlabeled: bool = False
    min_confidence: float = 0.0


class ExportResponse(BaseModel):
    export_id: str
    status: str
    format: str
    created_at: datetime


# Mock datasets for now
_datasets = [
    Dataset(
        id="obstacle-detection",
        name="Obstacle Detection",
        description="Images for training obstacle detection models",
        image_count=150,
        labeled_count=120,
        categories=["tree", "rock", "fence", "person", "animal"],
        created_at=datetime.now(timezone.utc) - timedelta(days=7),
        last_updated=datetime.now(timezone.utc) - timedelta(hours=2)
    ),
    Dataset(
        id="grass-detection", 
        name="Grass Quality Detection",
        description="Images for grass health and cutting quality analysis",
        image_count=200,
        labeled_count=180,
        categories=["healthy_grass", "weeds", "bare_soil", "cut_grass"],
        created_at=datetime.now(timezone.utc) - timedelta(days=14),
        last_updated=datetime.now(timezone.utc) - timedelta(hours=6)
    )
]

_export_counter = 0


@router.get("/ai/datasets", response_model=List[Dataset])
def get_ai_datasets(request: Request):
    data = [ds.model_dump(mode="json") for ds in _datasets]
    # Last modified is the latest dataset update
    last_mod = max((ds.last_updated for ds in _datasets), default=datetime.now(timezone.utc))
    body = json.dumps(data, sort_keys=True).encode()
    etag = hashlib.sha256(body).hexdigest()
    inm = request.headers.get("if-none-match")
    ims = request.headers.get("if-modified-since")
    if inm == etag:
        return JSONResponse(status_code=304, content=None)
    if ims:
        try:
            ims_dt = parsedate_to_datetime(ims)
            if ims_dt.tzinfo is None:
                ims_dt = ims_dt.replace(tzinfo=timezone.utc)
            if ims_dt >= last_mod.replace(microsecond=0):
                return JSONResponse(status_code=304, content=None)
        except Exception:
            pass
    headers = {
        "ETag": etag,
        "Last-Modified": format_datetime(last_mod),
        "Cache-Control": "public, max-age=60",
    }
    return JSONResponse(content=data, headers=headers)


@router.post("/ai/datasets/{datasetId}/export", response_model=ExportResponse, status_code=202)
def post_ai_dataset_export(datasetId: str, export_req: ExportRequest):
    global _export_counter
    
    # Validate dataset exists
    dataset_exists = any(ds.id == datasetId for ds in _datasets)
    if not dataset_exists:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Validate format
    if export_req.format not in ["COCO", "YOLO"]:
        raise HTTPException(status_code=422, detail="Format must be COCO or YOLO")
    
    _export_counter += 1
    export_id = f"export-{_export_counter:04d}"
    
    resp = ExportResponse(
        export_id=export_id,
        status="started",
        format=export_req.format,
        created_at=datetime.now(timezone.utc)
    )
    persistence.add_audit_log("ai.export", resource=datasetId, details={"format": export_req.format})
    return resp


# ------------------------ System Settings ------------------------


class SystemSettings(BaseModel):
    hardware: dict = {
        "gps_module": "ZED-F9P",  # or "Neo-8M"
        "drive_controller": "RoboHAT-Cytron",  # or "L298N"
        "ai_acceleration": "Coral-USB",  # or "Hailo-HAT" or "CPU"
        "simulation_mode": False
    }
    operation: dict = {
        "max_speed": 0.8,
        "cutting_height": 3.0,  # cm
        "safety_timeout": 30,  # seconds
        "simulation_mode": False
    }
    telemetry: dict = {
        "cadence_hz": 5,  # 1-10 Hz
        "logging_level": "INFO",
        "retain_days": 30
    }
    ai: dict = {
        "confidence_threshold": 0.7,
        "inference_mode": "obstacle_detection",
        "training_enabled": True
    }
    ui: dict = {
        "theme": "retro-amber",
        "auto_refresh": True,
        "map_provider": "google"  # or "osm"
    }


_system_settings = SystemSettings()
_settings_last_modified: datetime = datetime.now(timezone.utc)


@router.get("/settings/system")
def get_settings_system(request: Request):
    data = _system_settings.model_dump(mode="json")
    body = json.dumps(data, sort_keys=True).encode()
    etag = hashlib.sha256(body).hexdigest()
    inm = request.headers.get("if-none-match")
    ims = request.headers.get("if-modified-since")
    if inm == etag:
        return JSONResponse(status_code=304, content=None)
    if ims:
        try:
            ims_dt = parsedate_to_datetime(ims)
            if ims_dt.tzinfo is None:
                ims_dt = ims_dt.replace(tzinfo=timezone.utc)
            if ims_dt >= _settings_last_modified.replace(microsecond=0):
                return JSONResponse(status_code=304, content=None)
        except Exception:
            pass
    headers = {
        "ETag": etag,
        "Last-Modified": format_datetime(_settings_last_modified),
        "Cache-Control": "public, max-age=30",
    }
    return JSONResponse(content=data, headers=headers)


@router.put("/settings/system")
def put_settings_system(settings_update: dict):
    global _system_settings
    
    # Get current settings as dict
    current = _system_settings.model_dump()
    
    # Apply partial or full updates
    for section_key, section_value in settings_update.items():
        if section_key in current:
            if isinstance(section_value, dict):
                # Update nested dict values
                current[section_key].update(section_value)
            else:
                current[section_key] = section_value
        else:
            # New section
            current[section_key] = section_value
    
    # Validate specific constraints
    if "telemetry" in current and "cadence_hz" in current["telemetry"]:
        cadence = current["telemetry"]["cadence_hz"]
        if not isinstance(cadence, int) or cadence < 1 or cadence > 10:
            raise HTTPException(status_code=422, detail="cadence_hz must be between 1 and 10")
    
    # Update the settings object
    try:
        _system_settings = SystemSettings(**current)
        global _settings_last_modified
        _settings_last_modified = datetime.now(timezone.utc)
        result = _system_settings.model_dump()
        persistence.add_audit_log("settings.update", details=settings_update)
        return result
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid settings: {str(e)}")


# ------------------------ Hardware Self-Test ------------------------


@router.get("/system/selftest")
def system_selftest():
    """Run on-device hardware self-test.

    Safe to run on systems without hardware; returns a structured report.
    """
    report = run_selftest()
    return report


# ------------------------ Health Endpoints ------------------------


@router.get("/health/liveness")
def health_liveness():
    """Basic liveness for systemd: process is up and serving requests."""
    uptime = max(0.0, time.time() - _app_start_time)
    return {
        "status": "ok",
        "service": "lawnberry-backend",
        "uptime_seconds": uptime,
    }


@router.get("/health/readiness")
def health_readiness():
    """Readiness: verify core dependencies are reachable (DB, app state)."""
    db_ok = False
    try:
        with persistence.get_connection() as conn:
            conn.execute("SELECT 1")
            db_ok = True
    except Exception:
        db_ok = False

    telemetry_state = "running" if getattr(websocket_hub, "_telemetry_task", None) else "idle"

    ready = db_ok  # minimal: DB reachable => ready
    return {
        "status": "ready" if ready else "not-ready",
        "components": {
            "database": {"ok": db_ok},
            "telemetry": {"state": telemetry_state},
        },
        "ready": ready,
    }


# ------------------------ Weather ------------------------


@router.get("/weather/current")
def weather_current(latitude: float | None = None, longitude: float | None = None):
    """Return minimal current weather snapshot.

    latitude/longitude are optional; when missing, service returns simulated values.
    """
    return weather_service.get_current(latitude=latitude, longitude=longitude)


@router.get("/weather/planning-advice")
def weather_planning_advice(latitude: float | None = None, longitude: float | None = None):
    current = weather_service.get_current(latitude=latitude, longitude=longitude)
    return weather_service.get_planning_advice(current)


# ------------------------ Docs Hub ------------------------


def _docs_root() -> Path:
    # backend/src/api/rest.py -> .../lawnberry-rebuild
    return Path(__file__).resolve().parents[3] / "docs"


@router.get("/docs/list")
def docs_list():
    root = _docs_root()
    if not root.exists():
        return []
    items = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root).as_posix()
        items.append({
            "name": p.stem.replace('_', ' ').title(),
            "path": rel,
            "size": p.stat().st_size,
        })
    return items


@router.get("/docs/{doc_path:path}")
def docs_get(doc_path: str):
    root = _docs_root()
    target = (root / doc_path).resolve()
    # Prevent path traversal
    try:
        target.relative_to(root)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Document not found")
    if target.suffix.lower() not in {".md", ".txt"}:
        raise HTTPException(status_code=415, detail="Unsupported document type")
    content = target.read_text(encoding="utf-8", errors="replace")
    # Add simple caching headers and appropriate content type
    body = content.encode("utf-8", errors="replace")
    etag = hashlib.sha256(body).hexdigest()
    last_mod = datetime.fromtimestamp(target.stat().st_mtime, tz=timezone.utc)
    headers = {
        "ETag": etag,
        "Last-Modified": format_datetime(last_mod),
        "Cache-Control": "public, max-age=60",
    }
    media_type = "text/markdown; charset=utf-8" if target.suffix.lower() == ".md" else "text/plain; charset=utf-8"
    return PlainTextResponse(content, headers=headers, media_type=media_type)
# ----------------------- WebSocket -----------------------


@router.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    client_id = f"client_{int(time.time())}"
    
    try:
        await websocket_hub.connect(websocket, client_id)
        
        # Start telemetry broadcasting
        await websocket_hub.start_telemetry_loop()
        
        while True:
            try:
                # Receive client messages
                data = await websocket.receive_text()
                message = json.loads(data)
                
                message_type = message.get("type")
                
                if message_type == "subscribe":
                    topic = message.get("topic")
                    if topic:
                        await websocket_hub.subscribe(client_id, topic)
                        
                elif message_type == "set_cadence":
                    cadence_hz = message.get("cadence_hz", 5.0)
                    await websocket_hub.set_cadence(client_id, cadence_hz)
                
                elif message_type == "ping":
                    # Heartbeat: reply with pong
                    await websocket.send_text(json.dumps({
                        "event": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }))
                    
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                # Invalid JSON, ignore
                continue
                
    finally:
        websocket_hub.disconnect(client_id)
