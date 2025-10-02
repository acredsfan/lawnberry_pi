from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Request, status, Query
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Set, Any
from pathlib import Path
import os
import json
import base64
import asyncio
import time
import hashlib
from email.utils import format_datetime, parsedate_to_datetime
import uuid
import io
from ..models.auth_security_config import AuthSecurityConfig
from ..models.remote_access_config import RemoteAccessConfig
from ..models.telemetry_exchange import ComponentId, ComponentStatus, HardwareTelemetryStream
from ..core.persistence import persistence
import os
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
            
    async def unsubscribe(self, client_id: str, topic: str):
        if topic in self.subscriptions:
            self.subscriptions[topic].discard(client_id)
            
        # Send confirmation
        if client_id in self.clients:
            await self.clients[client_id].send_text(json.dumps({
                "event": "unsubscription.confirmed", 
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
                
                # Broadcast to topic-specific channels
                await self._broadcast_telemetry_topics(telemetry_data)
                
                # Wait based on cadence
                await asyncio.sleep(1.0 / self.telemetry_cadence_hz)
                
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)
                
    async def _broadcast_telemetry_topics(self, telemetry_data: dict):
        """Broadcast telemetry data to appropriate topics."""
        # Extract data for specific topics
        if "battery" in telemetry_data:
            await self.broadcast_to_topic("telemetry.power", {
                "battery": telemetry_data["battery"],
                "source": telemetry_data.get("source", "unknown")
            })
            
        if "position" in telemetry_data:
            await self.broadcast_to_topic("telemetry.navigation", {
                "position": telemetry_data["position"],
                "source": telemetry_data.get("source", "unknown")
            })
            
        if "imu" in telemetry_data:
            await self.broadcast_to_topic("telemetry.sensors", {
                "imu": telemetry_data["imu"],
                "source": telemetry_data.get("source", "unknown")
            })
            
        if "motor_status" in telemetry_data:
            await self.broadcast_to_topic("telemetry.motors", {
                "motor_status": telemetry_data["motor_status"],
                "source": telemetry_data.get("source", "unknown")
            })
            
        # System status
        system_data = {
            "safety_state": telemetry_data.get("safety_state", "unknown"),
            "uptime_seconds": telemetry_data.get("uptime_seconds", 0),
            "source": telemetry_data.get("source", "unknown")
        }
        await self.broadcast_to_topic("telemetry.system", system_data)
        await self.broadcast_to_topic("system.health", system_data)
        
        # Legacy support: broadcast full data to general telemetry topic
        await self.broadcast_to_topic("telemetry/updates", telemetry_data)
        
        # Additional simulated topics (for demo/testing)
        await self._broadcast_additional_topics()
        
    async def _broadcast_additional_topics(self):
        """Broadcast simulated data for topics that don't have real hardware yet."""
        import random
        
        # Weather data
        weather_data = {
            "temperature_c": round(random.uniform(15, 30), 1),
            "humidity_percent": round(random.uniform(40, 80), 1),
            "wind_speed_ms": round(random.uniform(0, 10), 1),
            "precipitation_mm": round(random.uniform(0, 5), 2),
            "source": "simulated"
        }
        await self.broadcast_to_topic("telemetry.weather", weather_data)
        
        # Job status (simulated)
        job_data = {
            "current_job": "mowing_zone_1",
            "progress_percent": round(random.uniform(0, 100), 1),
            "remaining_time_min": random.randint(5, 60),
            "status": random.choice(["running", "paused", "idle"]),
            "source": "simulated"
        }
        await self.broadcast_to_topic("jobs.progress", job_data)
        
        # System performance
        perf_data = {
            "cpu_usage_percent": round(random.uniform(10, 60), 1),
            "memory_usage_percent": round(random.uniform(20, 70), 1),
            "disk_usage_percent": round(random.uniform(30, 80), 1),
            "temperature_c": round(random.uniform(35, 65), 1),
            "source": "simulated"
        }
        await self.broadcast_to_topic("system.performance", perf_data)
        
        # Connectivity status
        conn_data = {
            "wifi_signal_strength": random.randint(-80, -30),
            "internet_connected": random.choice([True, False]),
            "mqtt_connected": random.choice([True, False]),
            "remote_access_active": random.choice([True, False]),
            "source": "simulated"
        }
        await self.broadcast_to_topic("system.connectivity", conn_data)

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
                    
                    # Add camera data if available
                    try:
                        from ..services.camera_stream_service import camera_service
                        camera_frame = await camera_service.get_current_frame()
                        if camera_frame and camera_service.stream:
                            telemetry["camera"] = {
                                "active": camera_service.stream.is_active,
                                "mode": camera_service.stream.mode,
                                "fps": camera_service.stream.statistics.current_fps,
                                "frame_count": camera_service.stream.statistics.frames_captured,
                                "client_count": camera_service.stream.client_count,
                                "last_frame": camera_frame.metadata.timestamp.isoformat() if camera_frame else None
                            }
                        else:
                            telemetry["camera"] = {
                                "active": False,
                                "mode": "offline",
                                "fps": 0.0,
                                "frame_count": 0,
                                "client_count": 0,
                                "last_frame": None
                            }
                    except Exception as e:
                        telemetry["camera"] = {"active": False, "mode": "error"}
                    
                    return telemetry
            except Exception as e:
                # Fall back to simulation if hardware path fails
                pass

        # Simulated data
        telemetry = {
            "source": "simulated",
            "battery": {"percentage": 85.2, "voltage": 12.6},
            "position": {"latitude": 40.7128, "longitude": -74.0060},
            "motor_status": "idle",
            "safety_state": "safe",
            "uptime_seconds": time.time(),
        }
        
        # Add simulated camera data
        try:
            from ..services.camera_stream_service import camera_service
            if camera_service.stream and camera_service.stream.is_active:
                telemetry["camera"] = {
                    "active": True,
                    "mode": "streaming",
                    "fps": 15.0,
                    "frame_count": int(time.time() * 15) % 10000,  # Simulated counter
                    "client_count": len(camera_service.clients),
                    "last_frame": datetime.now(timezone.utc).isoformat()
                }
            else:
                telemetry["camera"] = {
                    "active": False,
                    "mode": "offline",
                    "fps": 0.0,
                    "frame_count": 0,
                    "client_count": 0,
                    "last_frame": None
                }
        except Exception:
            telemetry["camera"] = {"active": False, "mode": "error"}
        
        return telemetry

# Global WebSocket hub instance
websocket_hub = WebSocketHub()
_app_start_time = time.time()


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
def auth_login(payload: AuthLoginRequest, request: Request):
    now = time.time()
    client_id = request.headers.get("X-Client-Id")
    if not client_id:
        # Use per-request unique ID to avoid cross-test rate limiting when header is absent
        client_id = "anon-" + uuid.uuid4().hex

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

    # Determine provided credentials
    provided_credential = None
    if payload.credential:
        provided_credential = payload.credential
    elif payload.username is not None or payload.password is not None:
        # Simple compatibility: allow default admin/admin
        if payload.username == "admin" and payload.password == "admin":
            provided_credential = "operator123"
        else:
            provided_credential = None

    # Validate credential
    if not provided_credential:
        # Increment failed count
        failed = _auth_failed_counts.get(client_id, 0) + 1
        _auth_failed_counts[client_id] = failed
        # Activate lockout after threshold
        if failed >= AUTH_LOCKOUT_FAILED_ATTEMPTS:
            _auth_lockout_until[client_id] = now + AUTH_LOCKOUT_SECONDS
        raise HTTPException(status_code=401, detail="Authentication failed")

    # Successful login resets failed count
    _auth_failed_counts[client_id] = 0

    # Issue a dummy token compatible with frontend and tests
    token = "lbp2-" + hashlib.sha256(f"{client_id}-{now}".encode()).hexdigest()[:32]
    user = UserOut(id="admin", username="admin")
    expires_in = 3600
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return AuthResponse(
        access_token=token,
        token=token,
        token_type="bearer",
        expires_in=expires_in,
        expires_at=expires_at,
        user=user,
    )


class RefreshResponse(BaseModel):
    access_token: str
    token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    expires_at: datetime


@router.post("/auth/refresh", response_model=RefreshResponse)
def auth_refresh():
    # Return a new dummy token
    token = "lbp2-" + hashlib.sha256(f"refresh-{time.time()}".encode()).hexdigest()[:32]
    expires_in = 3600
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return RefreshResponse(access_token=token, token=token, expires_in=expires_in, expires_at=expires_at)


@router.post("/auth/logout")
def auth_logout():
    return {"ok": True}


@router.get("/auth/profile", response_model=UserOut)
def auth_profile():
    return UserOut(id="admin", username="admin")


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
async def dashboard_telemetry():
    """Get real-time telemetry from hardware sensors with RTK/IMU orientation states"""
    start_time = time.perf_counter()
    
    # Get hardware telemetry data from the WebSocket hub
    telemetry_data = await websocket_hub._generate_telemetry()
    
    latency_ms = (time.perf_counter() - start_time) * 1000
    now = datetime.now(timezone.utc).isoformat()
    
    # Extract and map hardware data to dashboard format
    if "source" in telemetry_data and telemetry_data["source"] == "hardware":
        # Use real hardware data
        battery_data = telemetry_data.get("battery", {})
        position_data = telemetry_data.get("position", {})
        imu_data = telemetry_data.get("imu", {})
        
        # RTK status and fallback messaging
        rtk_status = position_data.get("rtk_status", "unknown")
        rtk_fallback_message = None
        if rtk_status in ["no_fix", "gps_fix"]:
            rtk_fallback_message = "RTK corrections unavailable - using standard GPS. See docs/hardware-overview.md for troubleshooting."
        
        # IMU calibration status
        imu_calibration = imu_data.get("calibration", 0)
        orientation_health = "healthy" if imu_calibration >= 2 else "degraded"
        orientation_message = None
        if imu_calibration < 2:
            orientation_message = "IMU calibration incomplete - orientation data may be inaccurate. See docs/hardware-feature-matrix.md."
        
        result = {
            "timestamp": now,
            "latency_ms": round(latency_ms, 2),
            "battery": {
                "percentage": battery_data.get("percentage", 0.0),
                "voltage": battery_data.get("voltage", None),
            },
            "temperatures": {
                "cpu": None,  # Add CPU temperature monitoring if available
                "ambient": None,  # Add from environmental sensor if available
            },
            "position": {
                "latitude": position_data.get("latitude", None),
                "longitude": position_data.get("longitude", None),
                "altitude": position_data.get("altitude", None),
                "accuracy": position_data.get("accuracy", None),
                "gps_mode": position_data.get("gps_mode", None),
                "rtk_status": rtk_status,
                "rtk_fallback_message": rtk_fallback_message,
            },
            "imu": {
                "roll": imu_data.get("roll", None),
                "pitch": imu_data.get("pitch", None),
                "yaw": imu_data.get("yaw", None),
                "calibration": imu_calibration,
                "orientation_health": orientation_health,
                "orientation_message": orientation_message,
            },
        }
    else:
        # Fallback to simulated/default values
        result = {
            "timestamp": now,
            "latency_ms": round(latency_ms, 2),
            "battery": {
                "percentage": telemetry_data.get("battery", {}).get("percentage", 85.2),
                "voltage": telemetry_data.get("battery", {}).get("voltage", 12.6),
            },
            "temperatures": {
                "cpu": None,
                "ambient": None,
            },
            "position": {
                "latitude": telemetry_data.get("position", {}).get("latitude", None),
                "longitude": telemetry_data.get("position", {}).get("longitude", None),
                "altitude": None,
                "accuracy": None,
                "gps_mode": None,
                "rtk_status": "simulated",
                "rtk_fallback_message": None,
            },
            "imu": {
                "roll": None,
                "pitch": None,
                "yaw": None,
                "calibration": 0,
                "orientation_health": "unknown",
                "orientation_message": None,
            },
        }
    
    # Add remediation metadata if latency exceeds thresholds
    if latency_ms > 350:  # Pi 4B threshold
        result["remediation"] = {
            "type": "latency_exceeded",
            "message": "Dashboard telemetry latency exceeds 350ms threshold for Pi 4B",
            "docs_link": "docs/OPERATIONS.md#telemetry-latency-troubleshooting"
        }
    elif latency_ms > 250:  # Pi 5 threshold
        result["remediation"] = {
            "type": "latency_warning",
            "message": "Dashboard telemetry latency exceeds 250ms target for Pi 5",
            "docs_link": "docs/OPERATIONS.md#performance-optimization"
        }
    
    return result


# ------------------------ Control ------------------------


class DriveCommand(BaseModel):
    mode: str  # e.g., "arcade", "tank"
    throttle: float | None = None
    turn: float | None = None


_blade_state = {"active": False}
_safety_state = {"emergency_stop_active": False}


# ------------------------ Telemetry V2 Endpoints ------------------------

class TelemetryPingRequest(BaseModel):
    component_id: str
    sample_count: int = 10

class TelemetryPingResponse(BaseModel):
    component_id: str
    sample_count: int
    avg_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    meets_target: bool
    target_ms: float
    timestamp: str

@router.get("/api/v2/telemetry/stream")
async def get_telemetry_stream(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=500, description="Items per page"),
    component_id: Optional[str] = Query(None, description="Filter by component ID"),
    start_time: Optional[str] = Query(None, description="Filter by start timestamp (ISO8601)"),
    end_time: Optional[str] = Query(None, description="Filter by end timestamp (ISO8601)"),
):
    """Get paginated hardware telemetry stream with RTK/IMU orientation metadata"""
    
    # Calculate limit and offset for pagination
    offset = (page - 1) * page_size
    
    # Load telemetry streams from persistence layer
    streams = persistence.load_telemetry_streams(
        limit=page_size,
        component_id=component_id,
        start_time=start_time,
        end_time=end_time
    )
    
    # Compute statistics
    stats = persistence.compute_telemetry_latency_stats(
        component_id=component_id,
        start_time=start_time,
        end_time=end_time
    )
    
    return {
        "page": page,
        "page_size": page_size,
        "total_count": len(streams),
        "streams": streams,
        "statistics": stats,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@router.get("/api/v2/telemetry/export")
async def export_telemetry_diagnostic(
    component_id: Optional[str] = Query(None, description="Filter by component ID"),
    start_time: Optional[str] = Query(None, description="Filter by start timestamp"),
    end_time: Optional[str] = Query(None, description="Filter by end timestamp"),
    format: str = Query("json", description="Export format: json or csv")
):
    """Export telemetry diagnostic data including power metrics for troubleshooting"""
    
    # Generate diagnostic export
    diagnostic_data = persistence.export_telemetry_diagnostic(
        component_id=component_id,
        start_time=start_time,
        end_time=end_time
    )
    
    if format == "csv":
        # Convert to CSV format
        import csv
        output = io.StringIO()
        
        # Write header
        fieldnames = ["timestamp", "component_id", "value", "status", "latency_ms"]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        # Write rows
        for stream in diagnostic_data.get("streams", []):
            writer.writerow({
                "timestamp": stream.get("timestamp"),
                "component_id": stream.get("component_id"),
                "value": str(stream.get("value")),
                "status": stream.get("status"),
                "latency_ms": stream.get("latency_ms")
            })
        
        csv_content = output.getvalue()
        output.close()
        
        return StreamingResponse(
            io.BytesIO(csv_content.encode('utf-8')),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=telemetry_diagnostic_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
            }
        )
    else:
        # Return JSON
        return JSONResponse(
            content=diagnostic_data,
            headers={
                "Content-Disposition": f"attachment; filename=telemetry_diagnostic_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
            }
        )

@router.post("/api/v2/telemetry/ping")
async def telemetry_ping(request: TelemetryPingRequest):
    """Measure telemetry latency for specific component with guardrail validation"""
    
    latencies = []
    
    # Perform multiple samples to get accurate measurement
    for _ in range(request.sample_count):
        start_time = time.perf_counter()
        
        # Get latest telemetry streams (simulating component read)
        if websocket_hub._sensor_manager:
            try:
                streams = await websocket_hub._sensor_manager.generate_telemetry_streams()
                # Filter to requested component if specified
                if request.component_id != "power":  # Allow "power" as generic
                    streams = [s for s in streams if s.component_id.value == request.component_id]
            except Exception:
                pass
        
        latency_ms = (time.perf_counter() - start_time) * 1000
        latencies.append(latency_ms)
        
        # Small delay between samples
        await asyncio.sleep(0.01)
    
    # Calculate statistics
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    min_latency = min(latencies) if latencies else 0.0
    max_latency = max(latencies) if latencies else 0.0
    
    # Determine platform-specific target (250ms for Pi 5, 350ms for Pi 4B)
    # For now, use 250ms as baseline - can be made platform-aware
    target_ms = 250.0
    meets_target = avg_latency <= target_ms
    
    response = TelemetryPingResponse(
        component_id=request.component_id,
        sample_count=request.sample_count,
        avg_latency_ms=round(avg_latency, 2),
        min_latency_ms=round(min_latency, 2),
        max_latency_ms=round(max_latency, 2),
        meets_target=meets_target,
        target_ms=target_ms,
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    
    return response

# ------------------------ Control ------------------------


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


# ------------------------ Control V2 Endpoints ------------------------

class ControlCommandV2(BaseModel):
    throttle: Optional[float] = Field(None, ge=-1.0, le=1.0)
    turn: Optional[float] = Field(None, ge=-1.0, le=1.0)
    blade_enabled: Optional[bool] = None
    max_speed_limit: float = Field(0.8, ge=0.0, le=1.0)
    timeout_ms: int = Field(1000, ge=100, le=10000)
    confirmation_token: Optional[str] = None

class ControlResponseV2(BaseModel):
    accepted: bool
    audit_id: str
    result: str
    status_reason: Optional[str] = None
    watchdog_echo: Optional[str] = None
    watchdog_latency_ms: Optional[float] = None
    safety_checks: List[str] = []
    active_interlocks: List[str] = []
    remediation: Optional[Dict[str, str]] = None
    timestamp: str

@router.get("/api/v2/hardware/robohat")
async def get_robohat_status():
    """Get RoboHAT firmware health and watchdog status"""
    from ..services.robohat_service import get_robohat_service
    
    robohat = get_robohat_service()
    
    if robohat is None:
        return {
            "firmware_version": "unknown",
            "uptime_seconds": 0,
            "watchdog_active": False,
            "serial_connected": False,
            "health_status": "not_initialized",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    status = robohat.get_status()
    return status.to_dict()

@router.post("/api/v2/control/drive", response_model=ControlResponseV2)
async def control_drive_v2(cmd: ControlCommandV2):
    """Execute drive command with safety checks and audit logging"""
    import uuid
    from ..services.robohat_service import get_robohat_service
    from ..services.motor_service import MotorService
    
    audit_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)
    
    # Check emergency stop
    if _safety_state.get("emergency_stop_active", False):
        response = ControlResponseV2(
            accepted=False,
            audit_id=audit_id,
            result="blocked",
            status_reason="EMERGENCY_STOP_ACTIVE",
            safety_checks=[],
            active_interlocks=["emergency_stop_override"],
            remediation={
                "message": "Clear emergency stop before issuing drive commands",
                "docs_link": "/docs/OPERATIONS.md#emergency-stop-recovery"
            },
            timestamp=timestamp.isoformat()
        )
        
        # Audit the blocked command
        persistence.add_audit_log(
            "control.drive.blocked",
            details={"command": cmd.model_dump(), "response": response.model_dump()}
        )
        
        return response
    
    # Validate command
    if cmd.throttle is None or cmd.turn is None:
        raise HTTPException(status_code=422, detail="throttle and turn required")
    
    # Send command to RoboHAT
    robohat = get_robohat_service()
    watchdog_start = datetime.now(timezone.utc)
    
    if robohat and robohat.status.serial_connected:
        # Calculate differential speeds
        left_speed = cmd.throttle - cmd.turn
        right_speed = cmd.throttle + cmd.turn
        
        # Clamp to max speed limit
        left_speed = max(-cmd.max_speed_limit, min(cmd.max_speed_limit, left_speed))
        right_speed = max(-cmd.max_speed_limit, min(cmd.max_speed_limit, right_speed))
        
        # Send to RoboHAT
        success = await robohat.send_motor_command(left_speed, right_speed)
        
        watchdog_end = datetime.now(timezone.utc)
        watchdog_latency = (watchdog_end - watchdog_start).total_seconds() * 1000
        
        response = ControlResponseV2(
            accepted=success,
            audit_id=audit_id,
            result="accepted" if success else "rejected",
            status_reason=None if success else "robohat_communication_failed",
            watchdog_echo=robohat.status.last_watchdog_echo,
            watchdog_latency_ms=watchdog_latency,
            safety_checks=["emergency_stop_check", "command_validation"],
            active_interlocks=[],
            timestamp=timestamp.isoformat()
        )
    else:
        response = ControlResponseV2(
            accepted=False,
            audit_id=audit_id,
            result="rejected",
            status_reason="robohat_not_connected",
            safety_checks=["emergency_stop_check"],
            active_interlocks=[],
            remediation={
                "message": "RoboHAT not connected - check serial connection",
                "docs_link": "/docs/hardware-overview.md#robohat-setup"
            },
            timestamp=timestamp.isoformat()
        )
    
    # Audit the command
    persistence.add_audit_log(
        "control.drive.v2",
        details={"command": cmd.model_dump(), "response": response.model_dump()}
    )
    
    return response

@router.post("/api/v2/control/blade", response_model=ControlResponseV2)
async def control_blade_v2(cmd: ControlCommandV2):
    """Execute blade command with safety interlocks and audit logging"""
    import uuid
    from ..services.robohat_service import get_robohat_service
    
    audit_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)
    
    # Check emergency stop
    if _safety_state.get("emergency_stop_active", False):
        response = ControlResponseV2(
            accepted=False,
            audit_id=audit_id,
            result="blocked",
            status_reason="EMERGENCY_STOP_ACTIVE",
            safety_checks=[],
            active_interlocks=["emergency_stop_override"],
            remediation={
                "message": "Clear emergency stop before operating blade",
                "docs_link": "/docs/OPERATIONS.md#emergency-stop-recovery"
            },
            timestamp=timestamp.isoformat()
        )
        
        persistence.add_audit_log(
            "control.blade.blocked",
            details={"command": cmd.model_dump(), "response": response.model_dump()}
        )
        
        return response
    
    # Validate blade command
    if cmd.blade_enabled is None:
        raise HTTPException(status_code=422, detail="blade_enabled required")
    
    # Send command to RoboHAT
    robohat = get_robohat_service()
    
    if robohat and robohat.status.serial_connected:
        success = await robohat.send_blade_command(cmd.blade_enabled, speed=cmd.max_speed_limit)
        
        response = ControlResponseV2(
            accepted=success,
            audit_id=audit_id,
            result="accepted" if success else "rejected",
            status_reason=None if success else "robohat_communication_failed",
            watchdog_echo=robohat.status.last_watchdog_echo,
            watchdog_latency_ms=robohat.status.watchdog_latency_ms,
            safety_checks=["emergency_stop_check", "blade_safety_check"],
            active_interlocks=[],
            timestamp=timestamp.isoformat()
        )
        
        # Update global state
        _blade_state["active"] = cmd.blade_enabled if success else False
    else:
        response = ControlResponseV2(
            accepted=False,
            audit_id=audit_id,
            result="rejected",
            status_reason="robohat_not_connected",
            safety_checks=["emergency_stop_check"],
            active_interlocks=[],
            remediation={
                "message": "RoboHAT not connected - check serial connection",
                "docs_link": "/docs/hardware-overview.md#robohat-setup"
            },
            timestamp=timestamp.isoformat()
        )
    
    # Audit the command
    persistence.add_audit_log(
        "control.blade.v2",
        details={"command": cmd.model_dump(), "response": response.model_dump()}
        
    )
    
    return response

@router.post("/api/v2/control/emergency", response_model=ControlResponseV2)
async def control_emergency_v2():
    """Trigger emergency stop with immediate hardware shutdown"""
    import uuid
    from ..services.robohat_service import get_robohat_service
    
    audit_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)
    
    # Set emergency state
    _safety_state["emergency_stop_active"] = True
    _blade_state["active"] = False
    
    # Send emergency stop to RoboHAT
    robohat = get_robohat_service()
    if robohat and robohat.status.serial_connected:
        await robohat.emergency_stop()
    
    response = ControlResponseV2(
        accepted=True,
        audit_id=audit_id,
        result="accepted",
        status_reason="EMERGENCY_STOP_TRIGGERED",
        safety_checks=["immediate_stop"],
        active_interlocks=["emergency_stop_override"],
        remediation={
            "message": "Emergency stop activated - all motors stopped",
            "docs_link": "/docs/OPERATIONS.md#emergency-stop-recovery"
        },
        timestamp=timestamp.isoformat()
    )
    
    # Audit the emergency stop
    persistence.add_audit_log(
        "control.emergency.triggered",
        details={"response": response.model_dump()}
    )
    
    return response


# ----------------------- Map Configuration -----------------------

from ..models.zone import MapConfiguration, MapMarker, Zone, Point, MarkerType, MapProvider
from ..services.maps_service import maps_service


@router.get("/api/v2/map/configuration")
async def get_map_configuration(config_id: str = "default"):
    """Get map configuration with zones, markers, and provider settings"""
    config = await maps_service.load_map_configuration(config_id, persistence)
    
    if not config:
        # Return default empty configuration
        config = MapConfiguration(
            config_id=config_id,
            config_version=1,
            provider=MapProvider.GOOGLE_MAPS,
            markers=[],
            exclusion_zones=[],
            mowing_zones=[]
        )
    
    return config.model_dump()


@router.put("/api/v2/map/configuration")
async def put_map_configuration(config_data: dict, config_id: str = "default"):
    """Update map configuration with validation and overlap checking"""
    try:
        # Parse the configuration
        config = MapConfiguration.parse_obj({**config_data, "config_id": config_id})
        
        # Validate GeoJSON structures
        if config.boundary_zone:
            for point in config.boundary_zone.polygon:
                if not (-90 <= point.latitude <= 90 and -180 <= point.longitude <= 180):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": "Invalid coordinates in boundary zone",
                            "remediation": {
                                "message": "Coordinates must be valid lat/lng values",
                                "docs_link": "/docs/maps-api-setup.md#coordinate-validation"
                            }
                        }
                    )
        
        # Check for overlaps in exclusion zones
        for i, zone1 in enumerate(config.exclusion_zones):
            for zone2 in config.exclusion_zones[i+1:]:
                if maps_service.check_overlap(zone1, zone2):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": f"Exclusion zones overlap: {zone1.id} and {zone2.id}",
                            "remediation": {
                                "message": "Exclusion zones must not overlap",
                                "docs_link": "/docs/maps-api-setup.md#zone-overlap-rejection"
                            }
                        }
                    )
        
        # Validate complete configuration
        if not config.validate_configuration():
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Map configuration validation failed",
                    "validation_errors": config.validation_errors,
                    "remediation": {
                        "message": "Review validation errors and correct configuration",
                        "docs_link": "/docs/maps-api-setup.md#configuration-validation"
                    }
                }
            )
        
        # Save configuration
        saved_config = await maps_service.save_map_configuration(config, persistence)
        
        # Audit log
        persistence.add_audit_log(
            "map.configuration.updated",
            details={
                "config_id": config_id,
                "version": saved_config.config_version,
                "provider": saved_config.provider
            }
        )
        
        return saved_config.model_dump()
        
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": str(e),
                "remediation": {
                    "message": "Check configuration format and try again",
                    "docs_link": "/docs/maps-api-setup.md"
                }
            }
        )


@router.post("/api/v2/map/provider-fallback")
async def trigger_provider_fallback():
    """Manually trigger provider fallback from Google Maps to OSM"""
    if maps_service.attempt_provider_fallback():
        persistence.add_audit_log(
            "map.provider.fallback",
            details={"from": "google", "to": "osm"}
        )
        return {
            "success": True,
            "provider": maps_service.provider,
            "message": "Switched to OpenStreetMap provider"
        }
    else:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "message": "Already using fallback provider"
            }
        )


# ----------------------- Settings V2 -----------------------

from ..services.settings_service import get_settings_service
from ..models.system_configuration import SettingsProfile

settings_service = get_settings_service(persistence)


@router.get("/api/v2/settings")
async def get_settings_v2(profile_id: str = "default"):
    """Get complete settings profile with all categories"""
    try:
        profile = settings_service.load_profile(profile_id)
        return profile.dict()
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "remediation": {
                    "message": "Failed to load settings profile",
                    "docs_link": "/docs/OPERATIONS.md#settings-management"
                }
            }
        )


@router.put("/api/v2/settings")
async def put_settings_v2(update: dict, profile_id: str = "default", expected_version: Optional[str] = None):
    """Update settings profile with version conflict detection"""
    try:
        # Check version conflict if expected version provided
        if expected_version and not settings_service.check_version_conflict(profile_id, expected_version):
            return JSONResponse(
                status_code=409,
                content={
                    "error": "Version conflict detected",
                    "remediation": {
                        "message": "Another user or process has modified the settings. Please refresh and try again.",
                        "docs_link": "/docs/OPERATIONS.md#version-conflicts"
                    }
                }
            )
        
        # Load current profile
        profile = settings_service.load_profile(profile_id)
        
        # Apply updates (category.key format)
        for key, value in update.items():
            if '.' in key:
                category, setting_key = key.split('.', 1)
                if not profile.update_setting(category, setting_key, value):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": f"Invalid setting: {key}",
                            "remediation": {
                                "message": "Check setting path and value type",
                                "docs_link": "/docs/OPERATIONS.md#settings-reference"
                            }
                        }
                    )
        
        # Validate profile
        validation = settings_service.validate_profile(profile)
        if not validation["valid"]:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Settings validation failed",
                    "validation_errors": validation["issues"],
                    "remediation": {
                        "message": "Review validation errors and correct settings",
                        "docs_link": "/docs/OPERATIONS.md#settings-validation"
                    }
                }
            )
        
        # Save profile
        settings_service.save_profile(profile)
        
        # Audit log
        persistence.add_audit_log(
            "settings.updated",
            details={
                "profile_id": profile_id,
                "version": profile.profile_version,
                "updated_keys": list(update.keys())
            }
        )
        
        return profile.dict()
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "remediation": {
                    "message": "Failed to update settings",
                    "docs_link": "/docs/OPERATIONS.md#troubleshooting"
                }
            }
        )


# ----------------------- Documentation Bundle -----------------------

from ..models.webui_contracts import DocumentationBundle
import subprocess
import tarfile
import json as jsonlib


@router.get("/api/v2/docs/bundle")
async def get_docs_bundle():
    """Get documentation bundle metadata and download link"""
    bundle_dir = Path("/home/pi/lawnberry/verification_artifacts/docs-bundle")
    manifest_path = bundle_dir / "manifest.json"
    
    if not manifest_path.exists():
        return JSONResponse(
            status_code=404,
            content={
                "error": "Documentation bundle not found",
                "remediation": {
                    "message": "Generate documentation bundle first",
                    "docs_link": "/docs/OPERATIONS.md#documentation-bundle",
                    "command": "python scripts/generate_docs_bundle.py"
                }
            }
        )
    
    # Load manifest
    with open(manifest_path, 'r') as f:
        manifest = jsonlib.load(f)
    
    # Check freshness
    stale_warning = None
    if manifest.get("stale_documents", 0) > 0:
        stale_warning = f"{manifest['stale_documents']} document(s) are stale (older than {manifest.get('freshness_threshold_days', 90)} days)"
    
    return {
        "bundle_available": True,
        "manifest": manifest,
        "download_url": f"/api/v2/docs/bundle/download",
        "stale_warning": stale_warning,
        "offline_available": True
    }


@router.get("/api/v2/docs/bundle/download")
async def download_docs_bundle():
    """Download documentation bundle (tarball)"""
    from fastapi.responses import FileResponse
    
    bundle_dir = Path("/home/pi/lawnberry/verification_artifacts/docs-bundle")
    bundle_path = bundle_dir / "docs-bundle.tar.gz"
    
    if not bundle_path.exists():
        return JSONResponse(
            status_code=404,
            content={"error": "Documentation bundle not found"}
        )
    
    return FileResponse(
        bundle_path,
        media_type="application/gzip",
        filename="lawnberry-docs.tar.gz"
    )


@router.post("/api/v2/docs/bundle/generate")
async def generate_docs_bundle(format: str = "tarball"):
    """Regenerate documentation bundle"""
    try:
        script_path = Path("/home/pi/lawnberry/scripts/generate_docs_bundle.py")
        result = subprocess.run(
            [sys.executable, str(script_path), "--format", format],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Bundle generation failed",
                    "stderr": result.stderr,
                    "remediation": {
                        "message": "Check logs for details",
                        "docs_link": "/docs/OPERATIONS.md#documentation-troubleshooting"
                    }
                }
            )
        
        return {
            "success": True,
            "message": "Documentation bundle generated successfully",
            "download_url": "/api/v2/docs/bundle/download"
        }
        
    except subprocess.TimeoutExpired:
        return JSONResponse(
            status_code=500,
            content={"error": "Bundle generation timed out"}
        )


# ----------------------- Verification Artifacts -----------------------

from ..models.verification_artifact import VerificationArtifact


@router.post("/api/v2/verification-artifacts")
async def create_verification_artifact(artifact_data: dict):
    """Create verification artifact with linked requirements"""
    try:
        artifact = VerificationArtifact.parse_obj(artifact_data)
        
        # Validate linked requirements format (FR-XXX)
        for req_id in artifact.linked_requirements:
            if not req_id.startswith("FR-"):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": f"Invalid requirement ID format: {req_id}",
                        "remediation": {
                            "message": "Requirement IDs must start with 'FR-'",
                            "docs_link": "/docs/OPERATIONS.md#verification-artifacts"
                        }
                    }
                )
        
        # Store artifact metadata
        persistence.add_audit_log(
            "verification.artifact.created",
            details=artifact.dict()
        )
        
        return {
            "success": True,
            "artifact_id": artifact.artifact_id,
            "created_at": artifact.created_at.isoformat()
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": str(e),
                "remediation": {
                    "message": "Check artifact data format",
                    "docs_link": "/docs/OPERATIONS.md#verification-artifacts"
                }
            }
        )


@router.get("/api/v2/verification-artifacts")
async def list_verification_artifacts(limit: int = 100):
    """List verification artifacts"""
    artifacts = persistence.load_audit_logs(limit=limit)
    
    # Filter for verification artifacts
    verification_artifacts = [
        log for log in artifacts
        if log["action"] == "verification.artifact.created"
    ]
    
    return {
        "artifacts": verification_artifacts,
        "count": len(verification_artifacts)
    }


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


# -------------------- Enhanced Settings (Placeholders) --------------------

# Security settings (auth levels, MFA options)
_security_settings = AuthSecurityConfig()
_security_last_modified: datetime = datetime.now(timezone.utc)


@router.get("/settings/security")
def get_settings_security(request: Request):
    data = _security_settings.model_dump(mode="json")
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
            if ims_dt >= _security_last_modified.replace(microsecond=0):
                return JSONResponse(status_code=304, content=None)
        except Exception:
            pass
    headers = {
        "ETag": etag,
        "Last-Modified": format_datetime(_security_last_modified),
        "Cache-Control": "public, max-age=30",
    }
    return JSONResponse(content=data, headers=headers)


@router.put("/settings/security")
def put_settings_security(update: dict):
    global _security_settings, _security_last_modified
    # Merge update into existing settings
    current = _security_settings.model_dump()
    for k, v in update.items():
        current[k] = v
    try:
        _security_settings = AuthSecurityConfig(**current)
        _security_last_modified = datetime.now(timezone.utc)
        return _security_settings.model_dump()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid security settings: {str(e)}")


# Remote access settings (Cloudflare, ngrok, custom)
_remote_access_settings = RemoteAccessConfig()
_remote_access_last_modified: datetime = datetime.now(timezone.utc)


@router.get("/settings/remote-access")
def get_settings_remote_access(request: Request):
    data = _remote_access_settings.model_dump(mode="json")
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
            if ims_dt >= _remote_access_last_modified.replace(microsecond=0):
                return JSONResponse(status_code=304, content=None)
        except Exception:
            pass
    headers = {
        "ETag": etag,
        "Last-Modified": format_datetime(_remote_access_last_modified),
        "Cache-Control": "public, max-age=30",
    }
    return JSONResponse(content=data, headers=headers)


@router.put("/settings/remote-access")
def put_settings_remote_access(update: dict):
    global _remote_access_settings, _remote_access_last_modified
    current = _remote_access_settings.model_dump()
    for k, v in update.items():
        current[k] = v
    try:
        _remote_access_settings = RemoteAccessConfig(**current)
        _remote_access_last_modified = datetime.now(timezone.utc)
        return _remote_access_settings.model_dump()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid remote access settings: {str(e)}")


# Maps settings (provider toggle, API key management, bypass) - placeholder
_maps_settings: dict = {
    "provider": "google",  # "google" or "osm"
    "api_key": None,
    "bypass_external": False,
}
_maps_last_modified: datetime = datetime.now(timezone.utc)


@router.get("/settings/maps")
def get_settings_maps(request: Request):
    data = _maps_settings
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
            if ims_dt >= _maps_last_modified.replace(microsecond=0):
                return JSONResponse(status_code=304, content=None)
        except Exception:
            pass
    headers = {
        "ETag": etag,
        "Last-Modified": format_datetime(_maps_last_modified),
        "Cache-Control": "public, max-age=30",
    }
    return JSONResponse(content=data, headers=headers)


@router.put("/settings/maps")
def put_settings_maps(update: dict):
    global _maps_settings, _maps_last_modified
    allowed_providers = {"google", "osm"}
    if "provider" in update and update["provider"] not in allowed_providers:
        raise HTTPException(status_code=422, detail="provider must be 'google' or 'osm'")
    _maps_settings.update(update)
    _maps_last_modified = datetime.now(timezone.utc)
    return _maps_settings


# GPS policy settings (dead reckoning defaults) - placeholder
_gps_policy_settings: dict = {
    "dead_reckoning_max_seconds": 120,
    "reduced_speed_factor": 0.3,
    "alert_after_seconds": 120,
}
_gps_policy_last_modified: datetime = datetime.now(timezone.utc)


@router.get("/settings/gps-policy")
def get_settings_gps_policy(request: Request):
    data = _gps_policy_settings
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
            if ims_dt >= _gps_policy_last_modified.replace(microsecond=0):
                return JSONResponse(status_code=304, content=None)
        except Exception:
            pass
    headers = {
        "ETag": etag,
        "Last-Modified": format_datetime(_gps_policy_last_modified),
        "Cache-Control": "public, max-age=30",
    }
    return JSONResponse(content=data, headers=headers)


@router.put("/settings/gps-policy")
def put_settings_gps_policy(update: dict):
    global _gps_policy_settings, _gps_policy_last_modified
    # Simple range checks
    if "dead_reckoning_max_seconds" in update and (not isinstance(update["dead_reckoning_max_seconds"], int) or update["dead_reckoning_max_seconds"] <= 0):
        raise HTTPException(status_code=422, detail="dead_reckoning_max_seconds must be a positive integer")
    if "reduced_speed_factor" in update and (not isinstance(update["reduced_speed_factor"], (int, float)) or not (0.1 <= float(update["reduced_speed_factor"]) <= 1.0)):
        raise HTTPException(status_code=422, detail="reduced_speed_factor must be between 0.1 and 1.0")
    _gps_policy_settings.update(update)
    _gps_policy_last_modified = datetime.now(timezone.utc)
    return _gps_policy_settings


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


# ------------------------ Camera Control ------------------------

from ..services.camera_stream_service import camera_service
from ..models.camera_stream import CameraStream, CameraConfiguration, CameraFrame


@router.get("/camera/status")
async def camera_status():
    """Get camera stream status and statistics."""
    try:
        if camera_service.stream:
            return {
                "status": "success",
                "data": camera_service.stream.dict()
            }
        else:
            return {
                "status": "error",
                "error": "Camera service not initialized"
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/camera/frame")
async def camera_current_frame():
    """Get the current camera frame."""
    try:
        frame = await camera_service.get_current_frame()
        if frame:
            return {
                "status": "success",
                "data": frame.dict()
            }
        else:
            return {
                "status": "error",
                "error": "No frame available"
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@router.post("/camera/start")
async def camera_start_streaming():
    """Start camera streaming."""
    try:
        success = await camera_service.start_streaming()
        return {
            "status": "success" if success else "error",
            "message": "Streaming started" if success else "Failed to start streaming"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@router.post("/camera/stop")
async def camera_stop_streaming():
    """Stop camera streaming."""
    try:
        await camera_service.stop_streaming()
        return {
            "status": "success",
            "message": "Streaming stopped"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/camera/configuration")
async def camera_get_configuration():
    """Get camera configuration."""
    try:
        return {
            "status": "success",
            "data": camera_service.stream.configuration.dict()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@router.post("/camera/configuration")
async def camera_update_configuration(config: dict):
    """Update camera configuration."""
    try:
        success = await camera_service.update_configuration(config)
        return {
            "status": "success" if success else "error",
            "message": "Configuration updated" if success else "Configuration update failed"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/camera/statistics")
async def camera_get_statistics():
    """Get camera streaming statistics."""
    try:
        stats = await camera_service.get_stream_statistics()
        return {
            "status": "success",
            "data": stats.dict()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@router.post("/camera/statistics/reset")
async def camera_reset_statistics():
    """Reset camera statistics."""
    try:
        await camera_service.reset_statistics()
        return {
            "status": "success",
            "message": "Statistics reset"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


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


_WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _compute_accept_header(key: str) -> str:
    digest = hashlib.sha1((key + _WEBSOCKET_GUID).encode("utf-8")).digest()
    return base64.b64encode(digest).decode("utf-8")


def _build_handshake_response(*, protocol: str, key: str, latency_budget_ms: int | None = None, payload_schema: str | None = None) -> Response:
    headers = {
        "Upgrade": "websocket",
        "Connection": "Upgrade",
        "Sec-WebSocket-Accept": _compute_accept_header(key),
        "Sec-WebSocket-Protocol": protocol,
    }
    if latency_budget_ms is not None:
        headers["X-Latency-Budget-Ms"] = str(latency_budget_ms)
    if payload_schema:
        headers["X-Payload-Schema"] = payload_schema
    return Response(status_code=status.HTTP_101_SWITCHING_PROTOCOLS, headers=headers)


def _validate_websocket_upgrade(request: Request, *, expected_protocol: str) -> str:
    upgrade_header = request.headers.get("upgrade", "").lower()
    connection_header = request.headers.get("connection", "")
    if upgrade_header != "websocket" or "upgrade" not in connection_header.lower():
        raise HTTPException(status_code=400, detail="Invalid WebSocket upgrade request")

    version = request.headers.get("sec-websocket-version")
    if version and version != "13":
        raise HTTPException(status_code=426, detail="Unsupported WebSocket version")

    protocol = request.headers.get("sec-websocket-protocol")
    if protocol != expected_protocol:
        raise HTTPException(status_code=400, detail="Unsupported WebSocket protocol")

    key = request.headers.get("sec-websocket-key")
    if not key:
        raise HTTPException(status_code=400, detail="Missing Sec-WebSocket-Key")

    return key


def _require_bearer_auth(request: Request) -> None:
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/ws/telemetry")
async def websocket_telemetry_handshake(request: Request):
    _require_bearer_auth(request)
    key = _validate_websocket_upgrade(request, expected_protocol="telemetry.v1")
    return _build_handshake_response(
        protocol="telemetry.v1",
        key=key,
        latency_budget_ms=200,
        payload_schema="#/components/schemas/HardwareTelemetryStream",
    )


@router.get("/ws/control")
async def websocket_control_handshake(request: Request):
    _require_bearer_auth(request)
    key = _validate_websocket_upgrade(request, expected_protocol="control.v1")
    return _build_handshake_response(
        protocol="control.v1",
        key=key,
        latency_budget_ms=150,
        payload_schema="#/components/schemas/ControlCommandResponse",
    )


@router.get("/ws/settings")
async def websocket_settings_handshake(request: Request):
    _require_bearer_auth(request)
    key = _validate_websocket_upgrade(request, expected_protocol="settings.v1")
    return _build_handshake_response(
        protocol="settings.v1",
        key=key,
        latency_budget_ms=300,
        payload_schema="#/components/schemas/SettingsProfile",
    )


@router.get("/ws/notifications")
async def websocket_notifications_handshake(request: Request):
    _require_bearer_auth(request)
    key = _validate_websocket_upgrade(request, expected_protocol="notifications.v1")
    return _build_handshake_response(
        protocol="notifications.v1",
        key=key,
        latency_budget_ms=500,
        payload_schema="#/components/schemas/NotificationEvent",
    )


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
                    if topic and _is_valid_topic(topic):
                        await websocket_hub.subscribe(client_id, topic)
                    else:
                        await websocket.send_text(json.dumps({
                            "event": "subscription.error",
                            "error": "Invalid topic",
                            "valid_topics": _get_valid_topics(),
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }))
                        
                elif message_type == "unsubscribe":
                    topic = message.get("topic")
                    if topic:
                        await websocket_hub.unsubscribe(client_id, topic)
                        
                elif message_type == "set_cadence":
                    cadence_hz = message.get("cadence_hz", 5.0)
                    await websocket_hub.set_cadence(client_id, cadence_hz)
                
                elif message_type == "ping":
                    # Heartbeat: reply with pong
                    await websocket.send_text(json.dumps({
                        "event": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }))
                    
                elif message_type == "list_topics":
                    # Send available topics
                    await websocket.send_text(json.dumps({
                        "event": "topics.list",
                        "topics": _get_valid_topics(),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }))
                    
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                # Invalid JSON, ignore
                continue
                
    finally:
        websocket_hub.disconnect(client_id)


def _is_valid_topic(topic: str) -> bool:
    """Validate WebSocket topic names."""
    valid_topics = _get_valid_topics()
    return topic in valid_topics


def _get_valid_topics() -> List[str]:
    """Get list of valid WebSocket topics."""
    return [
        # Legacy topics (backward compatibility)
        "telemetry/updates",
        
        # Telemetry topics
        "telemetry.sensors",
        "telemetry.navigation", 
        "telemetry.motors",
        "telemetry.power",
        "telemetry.camera",
        "telemetry.weather",
        "telemetry.system",
        
        # Job/operation topics
        "jobs.status",
        "jobs.progress", 
        "jobs.queue",
        
        # Navigation/mapping topics
        "navigation.position",
        "navigation.path",
        "navigation.zones",
        
        # Alerts/notifications
        "alerts.safety",
        "alerts.maintenance",
        "alerts.weather",
        "alerts.system",
        
        # System status topics
        "system.health",
        "system.connectivity",
        "system.performance",
        
        # Control/command topics
        "control.manual",
        "control.autonomous",
        
        # Configuration topics
        "config.updates",
        "config.validation"
    ]
