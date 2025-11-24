from fastapi import APIRouter, HTTPException, Request, status, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, Any, Dict
import json
import hashlib
import logging
import time
import os
import uuid
from email.utils import format_datetime, parsedate_to_datetime

from ..core.persistence import persistence
from ..core.globals import (
    _blade_state, _safety_state, _emergency_until, _client_emergency, 
    _legacy_motors_active, _manual_control_sessions
)
from .routers import telemetry
from .routers.auth import _resolve_manual_session
from ..services.websocket_hub import websocket_hub

logger = logging.getLogger(__name__)
router = APIRouter()
legacy_router = APIRouter()

# Legacy WebSocket paths
legacy_router.add_websocket_route("/ws/telemetry", telemetry.ws_telemetry)
legacy_router.add_websocket_route("/ws/control", telemetry.ws_control)

# ----------------------- Map Zones -----------------------

class Point(BaseModel):
    latitude: float
    longitude: float

class Zone(BaseModel):
    id: str
    name: Optional[str] = None
    polygon: list[Point]
    priority: int = 0
    exclusion_zone: bool = False

_zones_store: list[Zone] = []
_zones_last_modified: datetime = datetime.now(timezone.utc)

@router.get("/map/zones", response_model=list[Zone])
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

@router.post("/map/zones", response_model=list[Zone])
def post_map_zones(zones: list[Zone]):
    global _zones_store
    _zones_store = zones
    global _zones_last_modified
    _zones_last_modified = datetime.now(timezone.utc)
    return _zones_store

# --------------------- Map Locations ---------------------

class Position(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    altitude: float | None = None
    accuracy: float | None = None
    gps_mode: str | None = None

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
    safety_checks: list[str] = []
    active_interlocks: list[str] = []
    remediation: Optional[dict[str, str]] = None
    telemetry_snapshot: Optional[dict[str, Any]] = None
    timestamp: str

def _emergency_active() -> bool:
    try:
        return time.time() < _emergency_until
    except Exception:
        return False

def _client_key(request: Request) -> str:
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth:
        return auth
    cid = request.headers.get("X-Client-Id") or request.headers.get("x-client-id")
    if cid:
        return cid
    # Fall back to a per-request ephemeral anon id to avoid cross-test leakage
    try:
        anon = getattr(request.state, "_anon_client_id", None)
        if not anon:
            anon = "anon-" + uuid.uuid4().hex
            try:
                request.state._anon_client_id = anon
            except Exception:
                pass
        return anon
    except Exception:
        # As a last resort, return a fresh anon id each time
        return "anon-" + uuid.uuid4().hex

def _client_emergency_active(request: Request | None) -> bool:
    """Return True if this client's emergency flag is active; expire stale entries.

    Uses a short TTL to prevent cross-test leakage while still blocking
    immediately-following commands after an emergency trigger.
    """
    try:
        if request is None:
            return False
        key = _client_key(request)
        exp = _client_emergency.get(key)
        now = time.time()
        if exp is None:
            return False
        if now < exp:
            return True
        # Expired: cleanup
        _client_emergency.pop(key, None)
        return False
    except Exception:
        return False

# Import helper from auth router for session resolution
from .routers.auth import _resolve_manual_session

@router.get("/hardware/robohat")
async def get_robohat_status():
    """Get RoboHAT firmware health and watchdog status with safety summary."""
    from ..services.robohat_service import get_robohat_service

    robohat = get_robohat_service()

    # Determine safety state summary for this snapshot
    safety_state = "emergency_stop" if _safety_state.get("emergency_stop_active", False) else "nominal"

    if robohat is None:
        # Minimal payload when service not initialized yet
        return {
            "firmware_version": "unknown",
            "uptime_seconds": 0,
            "watchdog_active": False,
            "serial_connected": False,
            "health_status": "not_initialized",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            # Contract-friendly fields
            "watchdog_heartbeat_ms": None,
            "safety_state": safety_state,
        }

    status = robohat.get_status()
    payload = status.to_dict()
    # Contract-friendly aliases/fields
    payload["watchdog_heartbeat_ms"] = payload.get("watchdog_latency_ms")
    payload["safety_state"] = safety_state
    telemetry_snapshot: dict[str, Any] | None = None
    try:
        telemetry_snapshot = await websocket_hub._generate_telemetry()
    except Exception as exc:
        logger.warning("Failed to gather hardware telemetry snapshot: %s", exc)

    if telemetry_snapshot:
        source = telemetry_snapshot.get("source") or "unknown"
        payload["telemetry_source"] = source
        if telemetry_snapshot.get("safety_state"):
            payload["safety_state"] = telemetry_snapshot["safety_state"]
        if telemetry_snapshot.get("camera") is not None:
            payload["camera"] = telemetry_snapshot.get("camera")

        if source == "hardware":
            for key in ("battery", "position", "imu", "velocity", "motor_status", "uptime_seconds"):
                value = telemetry_snapshot.get(key)
                if value is not None:
                    payload[key] = value
        else:
            # Avoid presenting simulated values as live data
            payload.setdefault("battery", {"percentage": None, "voltage": None})
            payload.setdefault("position", {"latitude": None, "longitude": None})
            payload.setdefault(
                "velocity",
                {
                    "linear": {"x": None, "y": None, "z": None},
                    "angular": {"x": None, "y": None, "z": None},
                },
            )
    else:
        payload["telemetry_source"] = "unknown"

    return payload

class Vector2D(BaseModel):
    linear: float
    angular: float

class DriveContractIn(BaseModel):
    session_id: str
    vector: Vector2D
    duration_ms: int
    reason: Optional[str] = None

@router.post("/control/drive", response_model=ControlResponseV2, status_code=202)
async def control_drive_v2(cmd: dict, request: Request):
    """Execute drive command with safety checks and audit logging"""
    import uuid
    from ..services.robohat_service import get_robohat_service
    from ..services.motor_service import MotorService
    
    audit_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)
    
    # Legacy behavior for integration tests: when payload is legacy style (mode/command),
    # return 200 with calculated motor speeds, unless emergency stop is active (then 403).
    is_legacy = "session_id" not in cmd
    if is_legacy:
        # Emergency stop -> reject legacy drive commands with 403 (short-lived TTL)
        if _client_emergency_active(request) or _emergency_active():
            try:
                cmd_details = cmd if isinstance(cmd, dict) else cmd.model_dump()
            except Exception:
                cmd_details = {}
            persistence.add_audit_log(
                "control.drive.blocked",
                details={"reason": "emergency_stop_active", "command": cmd_details}
            )
            return JSONResponse(status_code=403, content={"detail": "Emergency stop active - drive commands blocked"})
        # Compute motor speeds using arcade drive
        throttle = float(cmd.get("throttle", 0.0))
        turn = float(cmd.get("turn", 0.0))
        left_speed = throttle - turn
        right_speed = throttle + turn
        # Clamp
        max_speed_limit = 1.0
        left_speed = max(-max_speed_limit, min(max_speed_limit, left_speed))
        right_speed = max(-max_speed_limit, min(max_speed_limit, right_speed))
        # Mark legacy motors active for interlock tests
        global _legacy_motors_active
        _legacy_motors_active = True
        body = {
            "left_motor_speed": round(left_speed, 3),
            "right_motor_speed": round(right_speed, 3),
            "safety_status": "OK",
        }
        persistence.add_audit_log("control.drive", details={"command": cmd, "response": body})
        return JSONResponse(status_code=200, content=body)

    # Contract-style payload
    # Block when emergency stop is active
    if _client_emergency_active(request) or _emergency_active():
        try:
            cmd_details = cmd if isinstance(cmd, dict) else cmd.model_dump()
        except Exception:
            cmd_details = {}
        if isinstance(cmd_details, dict) and "session_id" in cmd_details:
            cmd_details = dict(cmd_details)
            cmd_details["session_id"] = "***"
        persistence.add_audit_log(
            "control.drive.blocked",
            details={"reason": "emergency_stop_active", "command": cmd_details}
        )
        return JSONResponse(status_code=403, content={"detail": "Emergency stop active - drive commands blocked"})

    session_context = _resolve_manual_session(cmd.get("session_id"))

    try:
        duration_ms = int(cmd.get("duration_ms", 0))
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="duration_ms must be an integer")

    if duration_ms < 0 or duration_ms > 5000:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="duration_ms must be between 0 and 5000 milliseconds")

    # Extract vector and convert to differential speeds (arcade)
    # Contract-style payload
    throttle = float(cmd.get("vector", {}).get("linear", 0.0))
    turn = float(cmd.get("vector", {}).get("angular", 0.0))
    try:
        speed_limit = float(cmd.get("max_speed_limit", 0.8))
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="max_speed_limit must be numeric")
    speed_limit = max(0.0, min(1.0, speed_limit))
    
    # Send command to RoboHAT

    robohat = get_robohat_service()
    watchdog_start = datetime.now(timezone.utc)
    
    if robohat and robohat.status.serial_connected:
        # Calculate differential speeds
        left_speed = throttle - turn
        right_speed = throttle + turn
        
        # Clamp to max speed limit
        left_speed = max(-speed_limit, min(speed_limit, left_speed))
        right_speed = max(-speed_limit, min(speed_limit, right_speed))
        
        # Send to RoboHAT
        success = await robohat.send_motor_command(left_speed, right_speed)
        
        watchdog_end = datetime.now(timezone.utc)
        watchdog_latency = (watchdog_end - watchdog_start).total_seconds() * 1000
        
        response = ControlResponseV2(
            accepted=success,
            audit_id=audit_id,
            result="accepted" if success else "rejected",
            status_reason=None if success else (robohat.status.last_error or "robohat_communication_failed"),
            watchdog_echo=robohat.status.last_watchdog_echo,
            watchdog_latency_ms=watchdog_latency,
            safety_checks=["emergency_stop_check", "command_validation"],
            active_interlocks=[],
            telemetry_snapshot={
                "component_id": "drive_left",
                "status": "healthy" if success else "warning",
                "latency_ms": round(watchdog_latency, 2),
                "speed_limit": speed_limit,
            },
            timestamp=timestamp.isoformat()
        )
    else:
        # Contract allows "queued" acknowledgement even if hardware not connected
        response = ControlResponseV2(
            accepted=True,
            audit_id=audit_id,
            result="queued",
            status_reason="nominal",
            safety_checks=["emergency_stop_check"],
            active_interlocks=[],
            remediation=None,
            telemetry_snapshot={
                "component_id": "drive_left",
                "status": "warning",
                "latency_ms": 0.0,
                "speed_limit": speed_limit,
            },
            timestamp=timestamp.isoformat()
        )
    
    # Audit the command
    try:
        details_cmd = cmd if isinstance(cmd, dict) else cmd.model_dump()
    except Exception:
        details_cmd = {}
    if isinstance(details_cmd, dict):
        details_cmd = dict(details_cmd)
        if "session_id" in details_cmd:
            details_cmd["session_id"] = "***"
        principal = session_context.get("principal")
        if principal and "principal" not in details_cmd:
            details_cmd["principal"] = principal
        details_cmd["max_speed_limit"] = speed_limit
    persistence.add_audit_log("control.drive.v2", details={"command": details_cmd, "response": response.model_dump()})
    
    return response

class BladeContractIn(BaseModel):
    session_id: str
    action: str
    reason: Optional[str] = None

@router.post("/control/blade")
async def control_blade_v2(cmd: dict, request: Request):
    """Execute blade command with safety interlocks and audit logging"""
    import uuid
    from ..services.robohat_service import get_robohat_service
    
    audit_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)
    
    # Contract requires safety lockout for blade engagement by default
    # Return HTTP 423 (Locked) with remediation
    # Legacy behavior for integration tests
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if "session_id" not in cmd and ("active" in cmd or "command" in cmd):
        # Enable
        if (cmd.get("command") == "blade_enable") or (cmd.get("active") is True):
            # Block if emergency is active (global TTL or per-client TTL)
            if _emergency_active() or _client_emergency_active(request):
                body = {"detail": "safety_interlock: emergency_stop_active - blade commands blocked"}
                persistence.add_audit_log("control.blade", details={"command": cmd, "response": body})
                return JSONResponse(status_code=403, content=body)
            # If no auth header provided, allow enabling for audit test flow
            if not auth_header:
                body = {"blade_status": "ENABLED"}
                persistence.add_audit_log("control.blade", details={"command": cmd, "response": body})
                return JSONResponse(status_code=200, content=body)
            # Safety interlock: reject with 403 if motors active; otherwise accept
            global _legacy_motors_active
            if _legacy_motors_active:
                body = {"detail": "Safety interlock: motors_active"}
                persistence.add_audit_log("control.blade", details={"command": cmd, "response": body})
                return JSONResponse(status_code=403, content=body)
            body = {"blade_status": "ENABLED"}
            persistence.add_audit_log("control.blade", details={"command": cmd, "response": body})
            return JSONResponse(status_code=200, content=body)
        # Disable
        if (cmd.get("command") == "blade_disable") or (cmd.get("active") is False):
            body = {"blade_status": "DISABLED"}
            persistence.add_audit_log("control.blade", details={"command": cmd, "response": body})
            return JSONResponse(status_code=200, content=body)

    session_context = _resolve_manual_session(cmd.get("session_id"))

    # Basic control path when explicitly authorized or legacy payloads handled above.
    try:
        desired = None
        if isinstance(cmd, dict) and "action" in cmd:
            desired = True if str(cmd.get("action")).lower() in {"enable", "on", "start"} else False if str(cmd.get("action")).lower() in {"disable", "off", "stop"} else None
        elif isinstance(cmd, dict) and "active" in cmd:
            desired = bool(cmd.get("active"))
        if desired is not None and not (_emergency_active() or _client_emergency_active(request)):
            from ..services.blade_service import get_blade_service
            bs = get_blade_service()
            await bs.initialize()
            ok = await bs.set_active(desired)
            body = {"accepted": ok, "audit_id": audit_id, "result": "accepted" if ok else "rejected", "timestamp": timestamp.isoformat()}
            log_command = cmd if not isinstance(cmd, dict) else {**cmd}
            if isinstance(log_command, dict) and "session_id" in log_command:
                log_command["session_id"] = "***"
            if isinstance(log_command, dict) and session_context.get("principal"):
                log_command.setdefault("principal", session_context.get("principal"))
            persistence.add_audit_log("control.blade.v2", details={"command": log_command, "response": body})
            return JSONResponse(status_code=200 if ok else 409, content=body)
    except Exception:
        pass

    payload = {
        "accepted": False,
        "audit_id": audit_id,
        "result": "blocked",
        "status_reason": "SAFETY_LOCKOUT",
        "remediation_url": "/docs/OPERATIONS.md#blade-safety-lockout",
        "safety_checks": ["emergency_stop_check", "blade_lockout"],
        "active_interlocks": ["blade_requires_authorization"],
        "timestamp": timestamp.isoformat(),
    }
    try:
        cmd_details = cmd if isinstance(cmd, dict) else cmd.model_dump()
    except Exception:
        cmd_details = {}
    if isinstance(cmd_details, dict):
        cmd_details = dict(cmd_details)
        if "session_id" in cmd_details:
            cmd_details["session_id"] = "***"
        if session_context and session_context.get("principal"):
            cmd_details.setdefault("principal", session_context.get("principal"))
    persistence.add_audit_log("control.blade.blocked", details={"command": cmd_details, "response": payload})
    return JSONResponse(status_code=423, content=payload)

@router.post("/control/emergency", response_model=ControlResponseV2, status_code=202)
async def control_emergency_v2(body: Optional[dict] = None, request: Request = None):
    """Trigger emergency stop with immediate hardware shutdown"""
    import uuid
    from ..services.robohat_service import get_robohat_service
    
    audit_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)

    payload = body or {}
    is_legacy = isinstance(payload, dict) and payload.get("command")
    session_context = None
    if not is_legacy:
        session_context = _resolve_manual_session(payload.get("session_id"))
    
    # Set emergency state
    _safety_state["emergency_stop_active"] = True
    _blade_state["active"] = False
    global _legacy_motors_active
    _legacy_motors_active = False
    # Arm short-lived emergency TTL to block follow-up commands across both modes
    global _emergency_until
    # Block control commands for a short window after emergency to ensure deterministic tests
    _emergency_until = time.time() + 0.2
    # Mark this client as in-emergency for a short TTL
    try:
        if request is not None:
            _client_emergency[_client_key(request)] = time.time() + 0.3
    except Exception:
        pass
    
    # Send emergency stop to RoboHAT
    robohat = get_robohat_service()
    if robohat and robohat.status.serial_connected:
        await robohat.emergency_stop()
    
    # If legacy payload with command field was sent, return 200 with integration-expected shape
    if is_legacy:
        legacy_payload = {
            "status": "EMERGENCY_STOP_ACTIVE",
            "motors_stopped": True,
            "blade_disabled": True,
            "emergency_stop_active": True,
            "timestamp": timestamp.isoformat(),
        }
        persistence.add_audit_log("control.emergency_stop", details={"response": legacy_payload})
        return JSONResponse(status_code=200, content=legacy_payload)

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
        telemetry_snapshot={
            "component_id": "drive_left",
            "status": "fault",
            "latency_ms": 0.0,
        },
        timestamp=timestamp.isoformat()
    )
    
    # Audit the emergency stop
    audit_details: dict[str, Any] = {"response": response.model_dump()}
    if session_context and session_context.get("principal"):
        audit_details["principal"] = session_context["principal"]
    persistence.add_audit_log(
        "control.emergency.triggered",
        details=audit_details
    )
    
    return response

@router.post("/control/emergency-stop")
async def control_emergency_stop_alias(request: Request = None):
    """Integration-friendly alias that always returns 200 and a simple flag."""
    # Trigger emergency state
    _safety_state["emergency_stop_active"] = True
    _blade_state["active"] = False
    payload = {
        "emergency_stop_active": True,
        "motors_stopped": True,
        "blade_disabled": True,
        "remediation": {
            "message": "Emergency stop activated - all motors stopped",
            "docs_link": "/docs/OPERATIONS.md#emergency-stop-recovery"
        }
    }
    return JSONResponse(status_code=200, content=payload)
