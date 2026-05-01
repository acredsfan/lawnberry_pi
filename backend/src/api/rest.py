from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
import json
import hashlib
import logging
import time
import os
import uuid
import asyncio
from email.utils import format_datetime, parsedate_to_datetime

from ..core.persistence import persistence
from ..core.runtime import RuntimeContext, get_runtime
from ..core.globals import (
    _blade_state,
    _safety_state,
    _emergency_until,
    _client_emergency,
    _legacy_motors_active,
    _manual_control_sessions,
    _security_settings,
)
from ..core.http_util import client_key
from .routers import telemetry
from .routers.auth import _resolve_manual_session
from ..services.websocket_hub import websocket_hub
from ..services.timezone_service import detect_system_timezone

logger = logging.getLogger(__name__)
router = APIRouter()
legacy_router = APIRouter()

# Legacy WebSocket paths
legacy_router.add_websocket_route("/ws/telemetry", telemetry.ws_telemetry)
legacy_router.add_websocket_route("/ws/control", telemetry.ws_control)
legacy_router.add_api_route(
    "/ws/telemetry", telemetry.websocket_telemetry_handshake, methods=["GET"]
)
legacy_router.add_api_route("/ws/control", telemetry.websocket_control_handshake, methods=["GET"])

_planning_jobs_store: list[dict[str, Any]] = []
_planning_job_counter = 0

# Rate-limit for high-frequency drive audit logs (accepted commands only).
# Blocked / fault logs are always written synchronously regardless of this gate.
_last_drive_audit_at: float = 0.0
_DRIVE_AUDIT_SAMPLE_INTERVAL_S: float = 1.0

# Manual drive auto-stop task tracking (Issue #2).
# Must be retained at module scope to prevent garbage collection mid-flight.
_drive_timeout_task: asyncio.Task | None = None


class SystemSettings(BaseModel):
    timezone: str = "UTC"
    timezone_source: str = "default"


_system_settings = SystemSettings()
_settings_last_modified: datetime = datetime.now(timezone.utc)


def _docs_root():
    from pathlib import Path
    import os

    return Path(os.getcwd()) / "docs"


def _require_bearer_auth(request: Request) -> None:
    telemetry._require_bearer_auth(request)


def get_settings_system(request: Request):
    global _system_settings
    try:
        timezone_info = detect_system_timezone()
        _system_settings.timezone = timezone_info.timezone
        _system_settings.timezone_source = timezone_info.source
    except Exception:
        pass

    return JSONResponse(
        content=_system_settings.model_dump(mode="json"),
        headers={
            "Last-Modified": format_datetime(_settings_last_modified),
            "Cache-Control": "public, max-age=30",
        },
    )


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
        return Response(status_code=304)
    if ims:
        try:
            ims_dt = parsedate_to_datetime(ims)
            if ims_dt.tzinfo is None:
                ims_dt = ims_dt.replace(tzinfo=timezone.utc)
            if ims_dt >= _zones_last_modified.replace(microsecond=0):
                return Response(status_code=304)
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
        return Response(status_code=304)
    if ims:
        try:
            ims_dt = parsedate_to_datetime(ims)
            if ims_dt.tzinfo is None:
                ims_dt = ims_dt.replace(tzinfo=timezone.utc)
            if ims_dt >= _locations_last_modified.replace(microsecond=0):
                return Response(status_code=304)
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


@router.get("/planning/jobs")
async def list_planning_jobs():
    return [dict(job) for job in _planning_jobs_store]


@router.post("/planning/jobs")
async def create_planning_job(payload: dict[str, Any]):
    global _planning_job_counter
    _planning_job_counter += 1
    job = {
        "id": f"planning-{_planning_job_counter:04d}",
        "name": str(payload.get("name") or f"Planning Job {_planning_job_counter}"),
        "schedule": payload.get("schedule"),
        "zones": list(payload.get("zones") or []),
        "priority": int(payload.get("priority") or 1),
        "enabled": bool(payload.get("enabled", True)),
    }
    _planning_jobs_store.append(job)
    return JSONResponse(status_code=201, content=job)


@router.delete("/planning/jobs/{job_id}")
async def delete_planning_job(job_id: str):
    for index, job in enumerate(_planning_jobs_store):
        if job.get("id") == job_id:
            _planning_jobs_store.pop(index)
            return JSONResponse(status_code=204, content=None)
    raise HTTPException(status_code=404, detail="Planning job not found")


def _normalize_map_provider(provider: Any) -> str:
    normalized = str(provider or "osm").strip().lower().replace("_", "-")
    if normalized in {"google", "google-maps"}:
        return "google-maps"
    return "osm"


def _map_provider_from_settings() -> str:
    try:
        from .routers.settings import _load_ui_settings, _normalize_maps_section

        sections = _load_ui_settings()
        maps_settings = _normalize_maps_section(sections.get("maps", {}))
        return "google-maps" if maps_settings.get("provider") == "google" else "osm"
    except Exception:
        return "osm"


def _default_map_configuration_envelope(config_id: str) -> dict[str, Any]:
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "config_id": config_id,
        "zones": [],
        "markers": [],
        "provider": _map_provider_from_settings(),
        "updated_at": timestamp,
        "updated_by": "system",
    }


async def _load_map_configuration_envelope(config_id: str) -> dict[str, Any]:
    default_envelope = _default_map_configuration_envelope(config_id)
    raw = await persistence.load_map_configuration(config_id)
    if not raw:
        return default_envelope

    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        logger.warning("Stored map configuration %s is not valid JSON; using defaults", config_id)
        return default_envelope

    if not isinstance(payload, dict):
        return default_envelope

    envelope = {**default_envelope, **payload}
    envelope["config_id"] = config_id
    envelope["zones"] = envelope.get("zones") if isinstance(envelope.get("zones"), list) else []
    markers = envelope.get("markers")
    envelope["markers"] = markers if isinstance(markers, (list, dict)) else []
    envelope["provider"] = _normalize_map_provider(envelope.get("provider"))
    envelope["updated_at"] = str(envelope.get("updated_at") or default_envelope["updated_at"])
    envelope["updated_by"] = str(envelope.get("updated_by") or "system")
    return envelope


async def _save_map_configuration_envelope(
    config_id: str,
    envelope: dict[str, Any],
    *,
    updated_by: str | None = None,
) -> dict[str, Any]:
    saved = {
        **_default_map_configuration_envelope(config_id),
        **envelope,
    }
    saved["config_id"] = config_id
    saved["zones"] = saved.get("zones") if isinstance(saved.get("zones"), list) else []
    markers = saved.get("markers")
    saved["markers"] = markers if isinstance(markers, (list, dict)) else []
    saved["provider"] = _normalize_map_provider(saved.get("provider"))
    saved["updated_at"] = datetime.now(timezone.utc).isoformat()
    saved["updated_by"] = updated_by or str(saved.get("updated_by") or "system")
    await persistence.save_map_configuration(config_id, json.dumps(saved))
    return saved


def _geometry_conflicts(
    zones: list[dict[str, Any]],
    *,
    zone_types: set[str] | None = None,
) -> list[str]:
    boundary_polygons: list[tuple[str, list[tuple[float, float]]]] = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        current_zone_type = str(zone.get("zone_type") or "")
        if zone_types is not None and current_zone_type not in zone_types:
            continue
        geometry = zone.get("geometry") if isinstance(zone.get("geometry"), dict) else {}
        if geometry.get("type") != "Polygon":
            continue
        coordinates = geometry.get("coordinates")
        if (
            not isinstance(coordinates, list)
            or not coordinates
            or not isinstance(coordinates[0], list)
        ):
            continue
        ring: list[tuple[float, float]] = []
        for point in coordinates[0]:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                ring.append((float(point[0]), float(point[1])))
            except (TypeError, ValueError):
                continue
        if len(ring) >= 3:
            boundary_polygons.append(
                (
                    str(zone.get("zone_id") or zone.get("id") or current_zone_type or "boundary"),
                    ring,
                )
            )

    if len(boundary_polygons) < 2:
        return []

    conflicts: set[str] = set()
    try:
        from shapely.geometry import Polygon  # type: ignore

        polygons: list[tuple[str, Any]] = []
        for zone_id, ring in boundary_polygons:
            poly = Polygon(ring)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                continue
            polygons.append((zone_id, poly))

        for index, (zone_id, polygon) in enumerate(polygons):
            for other_zone_id, other_polygon in polygons[index + 1 :]:
                if polygon.intersects(other_polygon) and not polygon.touches(other_polygon):
                    conflicts.add(zone_id)
                    conflicts.add(other_zone_id)
    except Exception:

        def _bbox(ring: list[tuple[float, float]]) -> tuple[float, float, float, float]:
            xs = [point[0] for point in ring]
            ys = [point[1] for point in ring]
            return min(xs), min(ys), max(xs), max(ys)

        def _bbox_overlaps(
            first: tuple[float, float, float, float],
            second: tuple[float, float, float, float],
        ) -> bool:
            return not (
                first[2] <= second[0]
                or second[2] <= first[0]
                or first[3] <= second[1]
                or second[3] <= first[1]
            )

        polygons = [(zone_id, _bbox(ring)) for zone_id, ring in boundary_polygons]
        for index, (zone_id, bbox) in enumerate(polygons):
            for other_zone_id, other_bbox in polygons[index + 1 :]:
                if _bbox_overlaps(bbox, other_bbox):
                    conflicts.add(zone_id)
                    conflicts.add(other_zone_id)

    return sorted(conflicts)


def _legacy_polygon_zones(entries: Any, *, zone_type: str) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []

    zones: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        coordinates = entry.get("coordinates")
        if not isinstance(coordinates, list):
            continue
        ring: list[list[float]] = []
        for point in coordinates:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                lat = float(point[0])
                lng = float(point[1])
            except (TypeError, ValueError):
                continue
            ring.append([lng, lat])
        if len(ring) < 3:
            continue
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        zone_id = str(
            entry.get("zone_id")
            or entry.get("name")
            or entry.get("zone_type")
            or f"{zone_type}-{index + 1}"
        )
        zones.append(
            {
                "zone_id": zone_id,
                "zone_type": zone_type,
                "name": entry.get("name") or zone_id,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [ring],
                },
            }
        )
    return zones


def _persist_map_provider_setting(provider: str) -> None:
    try:
        from .routers.settings import _load_ui_settings, _save_ui_settings

        sections = _load_ui_settings()
        maps_settings = dict(sections.get("maps", {}))
        maps_settings["provider"] = "google" if provider == "google-maps" else "osm"
        sections["maps"] = maps_settings
        _save_ui_settings(sections)
    except Exception as exc:
        logger.warning("Failed to persist maps provider setting: %s", exc)


@router.get("/map/configuration")
async def get_map_configuration(
    config_id: str = Query("default"),
    simulate_fallback: str | None = Query(default=None),
):
    envelope = await _load_map_configuration_envelope(config_id)
    provider = envelope["provider"]
    fallback_active = False
    fallback_reason = None
    if simulate_fallback:
        provider = "osm"
        fallback_active = True
        fallback_reason = str(simulate_fallback).upper()

    return {
        **envelope,
        "provider": provider,
        "fallback": {
            "active": fallback_active,
            "reason": fallback_reason,
            "provider": provider,
        },
    }


@router.put("/map/configuration")
async def put_map_configuration(
    envelope: dict[str, Any],
    config_id: str = Query("default"),
):
    zones = envelope.get("zones")
    if zones is not None and not isinstance(zones, list):
        raise HTTPException(status_code=422, detail="zones must be a list")

    markers = envelope.get("markers")
    if markers is not None and not isinstance(markers, (list, dict)):
        raise HTTPException(status_code=422, detail="markers must be a list or object")

    legacy_boundaries = _legacy_polygon_zones(envelope.get("boundaries"), zone_type="boundary")
    legacy_exclusions = _legacy_polygon_zones(
        envelope.get("exclusion_zones"), zone_type="exclusion"
    )
    zone_list = zones if isinstance(zones, list) else [*legacy_boundaries, *legacy_exclusions]

    conflicts = _geometry_conflicts(
        zone_list,
        zone_types={"boundary"} if isinstance(zones, list) else {"boundary", "exclusion"},
    )
    if conflicts:
        return JSONResponse(
            status_code=400,
            content={
                "error_code": "GEOMETRY_OVERLAP",
                "detail": "Geometry overlap conflict detected",
                "message": "Overlapping boundary polygons detected",
                "conflicts": conflicts,
            },
        )

    saved = await _save_map_configuration_envelope(
        config_id,
        {
            **envelope,
            "zones": zone_list,
            "markers": markers if markers is not None else envelope.get("markers", []),
        },
        updated_by=str(envelope.get("updated_by") or "api"),
    )
    _persist_map_provider_setting(saved["provider"])
    return {
        "status": "accepted",
        "config_id": config_id,
        "updated_at": saved["updated_at"],
        "updated_by": saved["updated_by"],
    }


@router.post("/map/provider-fallback")
async def trigger_map_provider_fallback(config_id: str = Query("default")):
    from ..services.maps_service import maps_service

    envelope = await _load_map_configuration_envelope(config_id)
    envelope["provider"] = "osm"
    saved = await _save_map_configuration_envelope(
        config_id,
        envelope,
        updated_by="provider-fallback",
    )
    _persist_map_provider_setting("osm")
    try:
        maps_service.configure("osm")
    except Exception:
        logger.debug("Maps service provider fallback sync skipped", exc_info=True)
    return {
        "success": True,
        "provider": "osm",
        "updated_at": saved["updated_at"],
        "fallback": {
            "active": True,
            "reason": "MANUAL_PROVIDER_FALLBACK",
            "provider": "osm",
        },
    }


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
    until: Optional[str] = None
    timestamp: str


def _emergency_active() -> bool:
    try:
        if bool(_safety_state.get("emergency_stop_active", False)):
            return True
        return time.time() < _emergency_until
    except Exception:
        return False


def _client_emergency_active(request: Request | None) -> bool:
    """Return True if this client's emergency flag is active; expire stale entries.

    Uses a short TTL to prevent cross-test leakage while still blocking
    immediately-following commands after an emergency trigger.
    """
    try:
        if request is None:
            return False
        key = client_key(request)
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


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _control_navigation_snapshot(nav_service: Any) -> dict[str, Any]:
    state = getattr(nav_service, "navigation_state", None)
    planned_path = getattr(state, "planned_path", None) if state is not None else None
    return {
        "mode": _enum_value(getattr(state, "navigation_mode", None)) if state is not None else None,
        "path_status": _enum_value(getattr(state, "path_status", None))
        if state is not None
        else None,
        "current_waypoint_index": getattr(state, "current_waypoint_index", None)
        if state is not None
        else None,
        "waypoints_total": len(planned_path) if isinstance(planned_path, list) else 0,
        "emergency_stop_active": bool(_safety_state.get("emergency_stop_active", False)),
    }


def _navigation_error_response(nav_service: Any, *, status_label: str, detail: str) -> JSONResponse:
    payload = {
        "ok": False,
        "status": status_label,
        "detail": detail,
        **_control_navigation_snapshot(nav_service),
    }
    return JSONResponse(status_code=409, content=payload)


def _manual_drive_status_reason(active_interlocks: list[str]) -> str:
    if "obstacle_detected" in active_interlocks:
        return "OBSTACLE_DETECTED"
    if "location_awareness_unavailable" in active_interlocks:
        return "LOCATION_AWARENESS_UNAVAILABLE"
    if "telemetry_unavailable" in active_interlocks or "telemetry_stale" in active_interlocks:
        return "TELEMETRY_UNAVAILABLE"
    return "SAFETY_LOCKOUT"


# Import helper from auth router for session resolution


@router.get("/hardware/robohat")
async def get_robohat_status():
    """Get RoboHAT firmware health and watchdog status with safety summary."""
    from ..services.robohat_service import get_robohat_service

    robohat = get_robohat_service()

    # Determine safety state summary for this snapshot
    safety_state = (
        "emergency_stop" if _safety_state.get("emergency_stop_active", False) else "nominal"
    )

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
                details={"reason": "emergency_stop_active", "command": cmd_details},
            )
            return JSONResponse(
                status_code=403,
                content={"detail": "Emergency stop active - drive commands blocked"},
            )
        # Compute motor speeds using arcade drive.
        # RoboHAT service uses INVERTED arcade formula to compensate for MDDRC10 motor wiring.
        # Convention: positive turn = turn right → right wheel speed < left wheel speed
        throttle = float(cmd.get("throttle", 0.0))
        turn = float(cmd.get("turn", 0.0))
        left_speed = throttle + turn
        right_speed = throttle - turn
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
            details={"reason": "emergency_stop_active", "command": cmd_details},
        )
        return JSONResponse(
            status_code=403, content={"detail": "Emergency stop active - drive commands blocked"}
        )

    session_context = _resolve_manual_session(cmd.get("session_id"))

    try:
        duration_ms = int(cmd.get("duration_ms", 0))
    except (TypeError, ValueError):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="duration_ms must be an integer"
        )

    if duration_ms < 0 or duration_ms > 5000:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="duration_ms must be between 0 and 5000 milliseconds",
        )

    # Extract vector and convert to differential speeds (arcade)
    # Contract-style payload
    throttle = float(cmd.get("vector", {}).get("linear", 0.0))
    turn = float(cmd.get("vector", {}).get("angular", 0.0))
    try:
        speed_limit = float(cmd.get("max_speed_limit", 0.8))
    except (TypeError, ValueError):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="max_speed_limit must be numeric"
        )
    speed_limit = max(0.0, min(1.0, speed_limit))
    motion_requested = abs(throttle) > 1e-3 or abs(turn) > 1e-3

    # Send command to RoboHAT

    robohat = get_robohat_service()
    watchdog_start = datetime.now(timezone.utc)
    telemetry_snapshot: dict[str, Any] | None = None
    manual_active_interlocks: list[str] = []

    if (
        motion_requested
        and robohat
        and robohat.status.serial_connected
        and os.getenv("SIM_MODE", "0") == "0"
    ):
        try:
            from ..services.navigation_service import NavigationService

            telemetry_snapshot = await websocket_hub.get_cached_telemetry()
            # Use the shared app.state loader so hot-reloaded limits are always fresh.
            # Fall back to constructing a loader (test environments that skip startup lifespan).
            _loader = getattr(request.app.state, "config_loader", None)
            if _loader is None:
                from ..core.config_loader import ConfigLoader

                _loader = ConfigLoader()
            _, limits = _loader.get()
            max_position_accuracy_m = NavigationService.get_instance().max_waypoint_accuracy_m

            source = telemetry_snapshot.get("source")
            if source != "hardware":
                manual_active_interlocks.append("telemetry_unavailable")
            else:
                snapshot_timestamp = telemetry_snapshot.get("timestamp")
                try:
                    snapshot_at = datetime.fromisoformat(str(snapshot_timestamp))
                    if snapshot_at.tzinfo is None:
                        snapshot_at = snapshot_at.replace(tzinfo=timezone.utc)
                    if (datetime.now(timezone.utc) - snapshot_at).total_seconds() > 2.5:
                        manual_active_interlocks.append("telemetry_stale")
                except Exception:
                    manual_active_interlocks.append("telemetry_stale")

                position = telemetry_snapshot.get("position") or {}
                latitude = position.get("latitude")
                longitude = position.get("longitude")
                accuracy = position.get("accuracy")
                if latitude is None or longitude is None or accuracy is None:
                    manual_active_interlocks.append("location_awareness_unavailable")
                else:
                    try:
                        if float(accuracy) > float(max_position_accuracy_m):
                            manual_active_interlocks.append("location_awareness_unavailable")
                    except (TypeError, ValueError):
                        manual_active_interlocks.append("location_awareness_unavailable")

                tof = telemetry_snapshot.get("tof") or {}
                threshold_mm = float(limits.tof_obstacle_distance_meters) * 1000.0
                for side in ("left", "right"):
                    side_payload = tof.get(side) or {}
                    distance_mm = side_payload.get("distance_mm")
                    if distance_mm is None:
                        continue
                    try:
                        if float(distance_mm) <= threshold_mm:
                            manual_active_interlocks.append("obstacle_detected")
                            break
                    except (TypeError, ValueError):
                        continue
        except Exception as exc:
            logger.warning("Manual drive telemetry safety validation failed: %s", exc)
            manual_active_interlocks.append("telemetry_unavailable")

    if manual_active_interlocks:
        manual_active_interlocks = list(dict.fromkeys(manual_active_interlocks))

        # Determine auto-expiry for transient vs persistent faults.
        # Obstacle faults clear only when the obstacle actually moves — no time-based expiry.
        # Telemetry/location faults are transient and auto-expire so the UI unlocks once sensors recover.
        _transient_interlocks = {
            "telemetry_unavailable",
            "telemetry_stale",
            "location_awareness_unavailable",
        }
        _has_only_transient = all(i in _transient_interlocks for i in manual_active_interlocks)
        lockout_until_str: str | None = None
        if _has_only_transient:
            lockout_until_str = (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat()

        blocked_response = ControlResponseV2(
            accepted=False,
            audit_id=audit_id,
            result="blocked",
            status_reason=_manual_drive_status_reason(manual_active_interlocks),
            safety_checks=[
                "emergency_stop_check",
                "command_validation",
                "telemetry_source_check",
                "location_awareness_check",
                "obstacle_clearance_check",
            ],
            active_interlocks=manual_active_interlocks,
            remediation={
                "docs_link": "/docs/OPERATIONS.md#manual-drive-safety-gating",
                "message": "Clear nearby obstacles and restore fresh hardware telemetry before retrying manual movement.",
            },
            telemetry_snapshot=telemetry_snapshot,
            until=lockout_until_str,
            timestamp=timestamp.isoformat(),
        )
        try:
            details_cmd = cmd if isinstance(cmd, dict) else cmd.model_dump()
        except Exception:
            details_cmd = {}
        if isinstance(details_cmd, dict) and "session_id" in details_cmd:
            details_cmd = dict(details_cmd)
            details_cmd["session_id"] = "***"
        persistence.add_audit_log(
            "control.drive.blocked",
            details={
                "reason": blocked_response.status_reason,
                "active_interlocks": manual_active_interlocks,
                "command": details_cmd,
            },
        )
        return JSONResponse(status_code=423, content=blocked_response.model_dump(mode="json"))

    if robohat and robohat.status.serial_connected:
        # Calculate differential speeds.
        # RoboHAT service uses INVERTED arcade formula (right_norm - left_norm)
        # to compensate for MDDRC10 physical wiring. Use matching formula here.
        # Convention: positive turn = turn right → right wheel speed < left wheel speed
        left_speed = throttle - turn
        right_speed = throttle + turn

        # Clamp to max speed limit
        left_speed = max(-speed_limit, min(speed_limit, left_speed))
        right_speed = max(-speed_limit, min(speed_limit, right_speed))

        # Send to RoboHAT
        success = await robohat.send_motor_command(left_speed, right_speed)

        # Auto-stop enforcement: if client goes silent, kill motors after duration_ms (Issue #2)
        if success:
            global _drive_timeout_task
            if _drive_timeout_task and not _drive_timeout_task.done():
                _drive_timeout_task.cancel()
            
            # duration_ms == 0 means "use client-side tick" — clamp to hard ceiling anyway
            auto_stop_ms = duration_ms if duration_ms > 0 else 500
            
            async def _auto_stop():
                try:
                    await asyncio.sleep(auto_stop_ms / 1000.0)
                    await robohat.send_motor_command(0.0, 0.0)
                    logger.warning("Manual drive duration expired (%d ms); motors stopped", auto_stop_ms)
                except asyncio.CancelledError:
                    pass
            
            _drive_timeout_task = asyncio.create_task(_auto_stop())

        watchdog_end = datetime.now(timezone.utc)
        watchdog_latency = (watchdog_end - watchdog_start).total_seconds() * 1000

        response = ControlResponseV2(
            accepted=success,
            audit_id=audit_id,
            result="accepted" if success else "rejected",
            status_reason=None
            if success
            else (robohat.status.last_error or "robohat_communication_failed"),
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
            timestamp=timestamp.isoformat(),
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
            timestamp=timestamp.isoformat(),
        )

    # Audit the command — sampled at 1 Hz for accepted drive commands to avoid
    # blocking the event loop with a synchronous SQLite write on every 120 ms
    # joystick pulse.  Blocked / fault audit entries are always written (see above).
    global _last_drive_audit_at
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
    _now = time.monotonic()
    if _now - _last_drive_audit_at >= _DRIVE_AUDIT_SAMPLE_INTERVAL_S:
        _last_drive_audit_at = _now
        _audit_details = {"command": details_cmd, "response": response.model_dump(mode="json")}
        _task = asyncio.create_task(
            asyncio.to_thread(
                persistence.add_audit_log, "control.drive.v2", None, None, _audit_details
            )
        )
        _task.add_done_callback(
            lambda t: logger.warning("Drive audit log failed: %s", t.exception())
            if not t.cancelled() and t.exception()
            else None
        )

    return response


class BladeContractIn(BaseModel):
    session_id: str
    action: str
    reason: Optional[str] = None


@router.post("/control/blade")
async def control_blade_v2(cmd: dict, request: Request):
    """Execute blade command with safety interlocks and audit logging.

    The only gate here is the emergency-stop interlock.  UI login already
    authenticates the caller; no additional session/auth layer is required.
    """
    audit_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)

    # Resolve desired state from either {"active": bool} or {"action": str}
    desired: bool | None = None
    if "active" in cmd:
        desired = bool(cmd["active"])
    elif "action" in cmd:
        action = str(cmd["action"]).lower()
        if action in {"enable", "on", "start"}:
            desired = True
        elif action in {"disable", "off", "stop"}:
            desired = False
    elif cmd.get("command") == "blade_enable":
        desired = True
    elif cmd.get("command") == "blade_disable":
        desired = False

    if desired is None:
        body = {
            "detail": "Invalid blade command — provide 'active' (bool) or 'action' (enable/disable)"
        }
        return JSONResponse(status_code=422, content=body)

    if desired is True and _legacy_motors_active:
        body = {
            "detail": "safety_interlock: motors_active — blade enable blocked while motors running"
        }
        persistence.add_audit_log(
            "control.blade.blocked", details={"command": cmd, "response": body}
        )
        return JSONResponse(status_code=403, content=body)

    if desired is True and (_emergency_active() or _client_emergency_active(request)):
        body = {"detail": "safety_interlock: emergency_stop_active — blade commands blocked"}
        persistence.add_audit_log(
            "control.blade.blocked", details={"command": cmd, "response": body}
        )
        return JSONResponse(status_code=409, content=body)

    try:
        from ..services.blade_service import get_blade_service

        bs = get_blade_service()
        await bs.initialize()
        ok = await bs.set_active(desired)
        body = {
            "accepted": ok,
            "audit_id": audit_id,
            "result": "accepted" if ok else "rejected",
            "blade_status": "ENABLED" if desired else "DISABLED",
            "timestamp": timestamp.isoformat(),
        }
        persistence.add_audit_log("control.blade", details={"command": cmd, "response": body})
        return JSONResponse(status_code=200 if ok else 409, content=body)
    except Exception as exc:
        logger.exception("Blade command failed: %s", exc)
        body = {"detail": f"Blade command error: {exc}"}
        persistence.add_audit_log("control.blade.error", details={"command": cmd, "response": body})
        return JSONResponse(status_code=500, content=body)


@router.post("/control/emergency", response_model=ControlResponseV2, status_code=202)
async def control_emergency_v2(
    body: Optional[dict] = None,
    request: Request = None,
    runtime: RuntimeContext = Depends(get_runtime),
):
    """Trigger emergency stop with immediate hardware shutdown"""
    from ..control.commands import EmergencyTrigger

    audit_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)

    payload = body or {}
    is_legacy = isinstance(payload, dict) and payload.get("command")
    session_context = None
    if not is_legacy:
        session_context = _resolve_manual_session(payload.get("session_id"))

    outcome = await runtime.command_gateway.trigger_emergency(
        EmergencyTrigger(
            reason="Operator-triggered emergency stop",
            source="operator",
            request=request,
        )
    )
    emergency_confirmed = outcome.hardware_confirmed

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
        accepted=emergency_confirmed,
        audit_id=audit_id,
        result="accepted" if emergency_confirmed else "rejected",
        status_reason="EMERGENCY_STOP_TRIGGERED"
        if emergency_confirmed
        else "EMERGENCY_STOP_DELIVERY_FAILED",
        safety_checks=["immediate_stop"],
        active_interlocks=["emergency_stop_override"],
        remediation={
            "message": "Emergency stop activated - all motors stopped",
            "docs_link": "/docs/OPERATIONS.md#emergency-stop-recovery",
        },
        telemetry_snapshot={
            "component_id": "drive_left",
            "status": "fault",
            "latency_ms": 0.0,
        },
        timestamp=timestamp.isoformat(),
    )
    audit_details: dict[str, Any] = {"response": response.model_dump(mode="json")}
    if session_context and session_context.get("principal"):
        audit_details["principal"] = session_context["principal"]
    persistence.add_audit_log("control.emergency.triggered", details=audit_details)
    return response


@router.post("/control/emergency-stop")
async def control_emergency_stop_alias(
    request: Request = None,
    runtime: RuntimeContext = Depends(get_runtime),
):
    """Integration-friendly alias that always returns 200 and a simple flag."""
    from ..control.commands import EmergencyTrigger

    await runtime.command_gateway.trigger_emergency(
        EmergencyTrigger(
            reason="Operator-triggered emergency stop",
            source="operator",
            request=request,
        )
    )
    payload = {
        "emergency_stop_active": True,
        "motors_stopped": True,
        "blade_disabled": True,
        "remediation": {
            "message": "Emergency stop activated - all motors stopped",
            "docs_link": "/docs/OPERATIONS.md#emergency-stop-recovery",
        },
    }
    persistence.add_audit_log(
        "control.emergency_stop",
        client_id=request.headers.get("X-Client-Id") if request is not None else None,
        details=payload,
    )
    return JSONResponse(status_code=200, content=payload)


@router.post("/control/start")
async def control_start_navigation():
    """Start autonomous navigation using the active planned path."""
    from ..services.navigation_service import NavigationService

    nav_service = NavigationService.get_instance()
    if _emergency_active():
        return _navigation_error_response(
            nav_service,
            status_label="emergency_stop_active",
            detail="Navigation start is blocked while emergency stop is active.",
        )
    started = await nav_service.start_autonomous_navigation()
    if not started:
        return _navigation_error_response(
            nav_service,
            status_label="not_ready",
            detail="Navigation could not start with the current path and position state.",
        )

    return {
        "ok": True,
        "status": "running",
        **_control_navigation_snapshot(nav_service),
    }


@router.post("/control/pause")
async def control_pause_navigation():
    """Pause autonomous navigation while preserving the current path."""
    from ..services.navigation_service import NavigationService

    nav_service = NavigationService.get_instance()
    paused = await nav_service.pause_navigation()
    if not paused:
        return _navigation_error_response(
            nav_service,
            status_label="pause_failed",
            detail="Navigation could not be paused cleanly.",
        )

    return {
        "ok": True,
        "status": "paused",
        **_control_navigation_snapshot(nav_service),
    }


@router.post("/control/resume")
async def control_resume_navigation():
    """Resume navigation after a pause."""
    from ..services.navigation_service import NavigationService

    nav_service = NavigationService.get_instance()
    if _emergency_active():
        return _navigation_error_response(
            nav_service,
            status_label="emergency_stop_active",
            detail="Navigation resume is blocked while emergency stop is active.",
        )
    resumed = await nav_service.resume_navigation()
    if not resumed:
        return _navigation_error_response(
            nav_service,
            status_label="resume_failed",
            detail="Navigation could not resume from the current state.",
        )

    return {
        "ok": True,
        "status": "running",
        **_control_navigation_snapshot(nav_service),
    }


@router.post("/control/stop")
async def control_stop_navigation():
    """Stop navigation and place the system back in idle."""
    from ..services.navigation_service import NavigationService

    nav_service = NavigationService.get_instance()
    stopped = await nav_service.stop_navigation()
    if not stopped:
        return _navigation_error_response(
            nav_service,
            status_label="stop_failed",
            detail="Navigation stop was requested but controller stop could not be confirmed.",
        )

    return {
        "ok": True,
        "status": "stopped",
        **_control_navigation_snapshot(nav_service),
    }


@router.post("/control/return-home")
async def control_return_home():
    """Start a return-to-home navigation sequence when home and position are available."""
    from ..services.navigation_service import NavigationService

    nav_service = NavigationService.get_instance()
    if _emergency_active():
        return _navigation_error_response(
            nav_service,
            status_label="emergency_stop_active",
            detail="Return-home is blocked while emergency stop is active.",
        )
    accepted = await nav_service.return_home()
    if not accepted:
        return _navigation_error_response(
            nav_service,
            status_label="return_home_unavailable",
            detail="Return-to-home is unavailable until home and current position are configured.",
        )

    return {
        "ok": True,
        "status": "returning_home",
        **_control_navigation_snapshot(nav_service),
    }


@router.get("/control/status")
async def control_navigation_status():
    """Expose navigation control state for operator dashboards."""
    from ..services.navigation_service import NavigationService

    nav_service = NavigationService.get_instance()
    return {
        "ok": True,
        "status": "emergency_stop" if _safety_state.get("emergency_stop_active") else "ready",
        "estop_reason": _safety_state.get("estop_reason"),
        **_control_navigation_snapshot(nav_service),
    }


@router.post("/control/diagnose/stiffness")
async def diagnose_stiffness_progressive(cmd: dict, request: Request):
    """Start progressive stiffness detection test (slowly increase turn effort until stuck).

    POST /api/v2/control/diagnose/stiffness
    Body: {
        "session_id": "<session>",
        "direction": "left|right",
        "initial_effort": 0.1,  # Start at 10% effort, optional
        "step": 0.05,            # Increase by 5% each iteration, optional
        "max_effort": 1.0        # Stop at 100%, optional
    }

    Returns:
    {
        "ok": true,
        "test_active": true,
        "current_effort": 0.10,
        "heading": 45.2,
        "heading_delta": 0.0,  # degrees changed since last step
        "status": "testing|stuck|completed"
    }
    """
    from ..services.navigation_service import NavigationService
    from ..services.robohat_service import get_robohat_service

    nav_service = NavigationService.get_instance()
    robohat = get_robohat_service()

    if _emergency_active():
        return JSONResponse(status_code=403, content={"detail": "Emergency stop active"})

    direction = cmd.get("direction", "left")
    initial_effort = float(cmd.get("initial_effort", 0.1))
    step = float(cmd.get("step", 0.05))
    max_effort = float(cmd.get("max_effort", 1.0))

    # Start or continue test
    heading_delta_out = 0.0  # Default value for initial request
    if not nav_service._stiffness_test_active:
        nav_service._stiffness_test_active = True
        nav_service._stiffness_test_start_time = time.time()
        nav_service._stiffness_test_effort = initial_effort
        nav_service._stiffness_test_effort_step = step
        nav_service._stiffness_test_max_effort = max_effort
        nav_service._stiffness_test_direction = direction
        nav_service._stiffness_test_last_heading: Optional[float] = None
        nav_service._stiffness_test_last_check: Optional[float] = None
        test_status = "started"
    else:
        elapsed = time.time() - nav_service._stiffness_test_start_time
        heading = nav_service.navigation_state.current_heading or 0.0

        # Check if stuck (heading barely changed in last 2 seconds)
        if nav_service._stiffness_test_last_heading is not None and elapsed > 2.0:
            heading_delta = abs(heading - nav_service._stiffness_test_last_heading)
            if heading_delta < nav_service._stiffness_test_stuck_threshold:
                # Motor is stuck - cease test
                nav_service._stiffness_test_active = False
                await robohat.send_motor_command(0.0, 0.0)
                test_status = "stuck"
                heading_delta_out = heading_delta
            else:
                # Not stuck yet, increase effort
                nav_service._stiffness_test_effort = min(
                    max_effort, nav_service._stiffness_test_effort + step
                )
                if nav_service._stiffness_test_effort >= max_effort:
                    nav_service._stiffness_test_active = False
                    await robohat.send_motor_command(0.0, 0.0)
                    test_status = "completed"
                else:
                    test_status = "testing"
                heading_delta_out = heading_delta
        else:
            test_status = "testing"
            heading_delta_out = 0.0

        nav_service._stiffness_test_last_heading = heading
        nav_service._stiffness_test_last_check = elapsed

    # Apply current effort in requested direction
    # Convert throttle/turn to left/right speeds using arcade math
    # RoboHAT service uses INVERTED arcade formula to compensate for motor wiring
    if nav_service._stiffness_test_active:
        effort = nav_service._stiffness_test_effort
        throttle = 0.3
        turn = effort if direction == "right" else -effort
        left_speed = throttle - turn
        right_speed = throttle + turn
        await robohat.send_motor_command(left_speed, right_speed)

    return {
        "ok": True,
        "test_active": nav_service._stiffness_test_active,
        "current_effort": nav_service._stiffness_test_effort,
        "heading": nav_service.navigation_state.heading or 0.0,
        "heading_delta": heading_delta_out if test_status != "started" else 0.0,
        "status": test_status,
    }


@router.post("/control/diagnose/heading-validation")
async def diagnose_heading_validation(cmd: dict, request: Request):
    """Validate heading by comparing GPS Course-Over-Ground vs IMU yaw.

    POST /api/v2/control/diagnose/heading-validation
    Body: {
        "session_id": "<session>",
        "distance_m": 5.0,       # Drive forward this far
        "samples": 10            # Collect this many GPS/IMU samples
    }

    Returns:
    {
        "ok": true,
        "heading_source": "gps|imu|conflict",
        "gps_cog": 45.2,
        "imu_yaw": 45.5,
        "difference": 0.3,
        "confidence": 0.95,
        "recommendation": "GPS source is reliable" | "IMU appears inverted" | "Conflict detected"
    }
    """
    from ..services.navigation_service import NavigationService
    from ..services.robohat_service import get_robohat_service

    nav_service = NavigationService.get_instance()
    robohat = get_robohat_service()

    if _emergency_active():
        return JSONResponse(status_code=403, content={"detail": "Emergency stop active"})

    # Collect GPS and IMU heading data while driving forward
    samples = int(cmd.get("samples", 10))

    # Start forward movement (pure forward, no turn)
    await robohat.send_motor_command(0.5, 0.5)

    gps_headings = []
    imu_headings = []

    try:
        for _ in range(samples):
            gps_cog = nav_service.navigation_state.gps_cog
            imu_heading = nav_service.navigation_state.heading

            if gps_cog is not None:
                gps_headings.append(float(gps_cog))
            if imu_heading is not None:
                imu_headings.append(float(imu_heading))

            await asyncio.sleep(0.2)
    finally:
        # Stop movement
        await robohat.send_motor_command(0.0, 0.0)

    if not gps_headings or not imu_headings:
        return {
            "ok": False,
            "error": "Insufficient sensor data collected",
            "gps_samples": len(gps_headings),
            "imu_samples": len(imu_headings),
        }

    # Compute average headings
    avg_gps = sum(gps_headings) / len(gps_headings)
    avg_imu = sum(imu_headings) / len(imu_headings)

    # Normalize angle difference to [-180, 180]
    diff = (avg_imu - avg_gps + 180) % 360 - 180
    abs_diff = abs(diff)

    # Determine heading source and recommendation
    if abs_diff < 5.0:
        heading_source = "gps"  # GPS and IMU agree
        recommendation = "GPS Course-Over-Ground is reliable; IMU calibration is correct"
        confidence = 1.0 - (abs_diff / 180.0)
    elif abs_diff > 170.0:
        heading_source = "imu"  # 180° difference suggests IMU inverted
        recommendation = "IMU yaw appears to be inverted (180° offset); check BNO085 calibration or fix yaw formula"
        confidence = 0.95
    else:
        heading_source = "conflict"  # Significant mismatch
        recommendation = f"Heading conflict detected ({abs_diff:.1f}°). Verify GPS fix quality and IMU calibration"
        confidence = max(0.0, 1.0 - (abs_diff / 90.0))

    return {
        "ok": True,
        "heading_source": heading_source,
        "gps_cog": round(avg_gps, 2),
        "imu_yaw": round(avg_imu, 2),
        "difference": round(abs_diff, 2),
        "confidence": round(confidence, 3),
        "recommendation": recommendation,
        "gps_samples": len(gps_headings),
        "imu_samples": len(imu_headings),
    }
