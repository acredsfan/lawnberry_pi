from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, model_validator
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Literal
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
from .routers.planning import PlanningJobResponse
from ..services.websocket_hub import websocket_hub
from ..services.timezone_service import detect_system_timezone
from ..services.boundary_verification import boundary_verification_service
from ..services.geofence_buffer import clear_safe_boundary
from ..services.parcel_boundary import BoundaryValidationError

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

# Rate-limit for high-frequency drive audit logs (accepted commands only).
# Blocked / fault logs are always written synchronously regardless of this gate.
_last_drive_audit_at: float = 0.0
_DRIVE_AUDIT_SAMPLE_INTERVAL_S: float = 1.0


class SystemSettings(BaseModel):
    timezone: str = "UTC"
    timezone_source: str = "default"


_system_settings = SystemSettings()
_settings_last_modified: datetime = datetime.now(timezone.utc)


def _docs_root():
    from pathlib import Path

    return Path(os.getcwd()) / "docs"


def _require_bearer_auth(request: Request) -> None:
    telemetry._require_bearer_auth(request)


def _invalidate_operating_area(runtime: RuntimeContext) -> None:
    """Make autonomy reload geometry after a Maps boundary mutation."""
    invalidate = getattr(getattr(runtime, "navigation", None), "invalidate_operating_area_snapshot", None)
    if callable(invalidate):
        invalidate()


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
    zone_kind: Literal["boundary", "exclusion", "mow"] = "boundary"

    @model_validator(mode="after")
    def _sync_exclusion(self) -> "Zone":
        if self.zone_kind == "exclusion":
            self.exclusion_zone = True
        elif self.exclusion_zone and self.zone_kind == "boundary":
            self.zone_kind = "exclusion"
        return self


def _is_boundary_zone(zone: dict[str, Any] | None) -> bool:
    if not zone:
        return False
    return (
        str(zone.get("zone_kind") or "").lower() == "boundary"
        and not bool(zone.get("exclusion_zone"))
    )


def _update_boundary_zone(repo: Any, zone: dict[str, Any], runtime: RuntimeContext) -> bool:
    updated = repo.update_zone(zone)
    if updated:
        clear_safe_boundary()
        _invalidate_operating_area(runtime)
    return updated


def _delete_boundary_zone(repo: Any, zone_id: str, runtime: RuntimeContext) -> bool:
    deleted = repo.delete_zone(zone_id)
    if deleted:
        clear_safe_boundary()
        _invalidate_operating_area(runtime)
    return deleted


_zones_last_modified: datetime = datetime.now(timezone.utc)


async def _emit_zone_changed(hub, zone_id: str, action: str) -> None:
    """Best-effort WS broadcast for zone mutations — never raises to caller."""
    if hub is None:
        return
    try:
        await hub.broadcast_to_topic(
            "planning.zone.changed",
            {"zone_id": zone_id, "action": action},
        )
    except Exception:
        # Hub unavailable or closed — skip silently
        pass


@router.get("/map/zones", response_model=list[Zone])
def get_map_zones(request: Request, runtime: RuntimeContext = Depends(get_runtime)):
    global _zones_last_modified
    repo = getattr(runtime, "map_repository", None)
    if repo is not None:
        data = repo.list_zones()
    else:
        data = []
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
async def post_map_zones(
    zones: list[Zone],
    bulk: bool = Query(False),
    allow_empty: bool = Query(False),
    runtime: RuntimeContext = Depends(get_runtime),
):
    global _zones_last_modified
    if not bulk:
        raise HTTPException(
            status_code=400,
            detail="Bulk zone replace requires ?bulk=true. For single-zone creation use POST /map/zones/{id}.",
        )
    repo = getattr(runtime, "map_repository", None)
    zone_dicts = [z.model_dump(mode="json") for z in zones]
    if not zone_dicts and not allow_empty:
        raise HTTPException(
            status_code=422,
            detail=(
                "Refusing to clear all zones via empty bulk replace. "
                "Pass allow_empty=true only for intentional full deletion."
            ),
        )
    if repo is not None:
        repo.save_zones(zone_dicts)
    _zones_last_modified = datetime.now(timezone.utc)
    hub = getattr(runtime, "websocket_hub", None)
    for z in zones:
        await _emit_zone_changed(hub, z.id, "bulk_replace")
    persistence.add_audit_log(
        "map.zones.bulk_replace",
        details={
            "count": len(zones),
            "ids": [z.id for z in zones],
        },
    )
    return zone_dicts


@router.post("/map/zones/{zone_id}", response_model=Zone, status_code=201)
async def post_map_zone_single(
    zone_id: str,
    zone: Zone,
    runtime: RuntimeContext = Depends(get_runtime),
):
    """Atomically create a single zone. 409 if zone_id already exists."""
    global _zones_last_modified
    if zone.id != zone_id:
        raise HTTPException(
            status_code=422,
            detail=f"Zone id in body '{zone.id}' does not match path id '{zone_id}'",
        )
    repo = getattr(runtime, "map_repository", None)
    if repo is not None:
        if repo.get_zone(zone_id) is not None:
            raise HTTPException(status_code=409, detail=f"Zone '{zone_id}' already exists.")
        existing = repo.list_zones()
        conflicts = _validate_zone_against_existing(zone, existing)
        if conflicts:
            raise HTTPException(
                status_code=422,
                detail=f"Zone overlaps with existing zones: {conflicts}",
            )
        import sqlite3 as _sqlite3

        try:
            repo.save_zone(zone.model_dump(mode="json"))
        except _sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail=f"Zone '{zone_id}' already exists.")
    _zones_last_modified = datetime.now(timezone.utc)
    hub = getattr(runtime, "websocket_hub", None)
    await _emit_zone_changed(hub, zone_id, "created")
    persistence.add_audit_log(
        "map.zone.created",
        resource=zone_id,
        details={
            "name": zone.name,
            "zone_kind": zone.zone_kind,
            "priority": zone.priority,
            "exclusion_zone": zone.exclusion_zone,
            "polygon": [{"latitude": p.latitude, "longitude": p.longitude} for p in zone.polygon],
        },
    )
    return zone.model_dump(mode="json")


@router.get("/map/zones/{zone_id}", response_model=Zone)
def get_map_zone(zone_id: str, runtime: RuntimeContext = Depends(get_runtime)):
    repo = getattr(runtime, "map_repository", None)
    if repo is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    zone = repo.get_zone(zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    return zone


@router.put("/map/zones/{zone_id}", response_model=Zone)
async def put_map_zone(zone_id: str, zone: Zone, runtime: RuntimeContext = Depends(get_runtime)):
    global _zones_last_modified
    if zone.id != zone_id:
        raise HTTPException(
            status_code=422,
            detail=f"Zone id in body '{zone.id}' does not match path id '{zone_id}'",
        )
    repo = getattr(runtime, "map_repository", None)
    if repo is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    existing = repo.get_zone(zone_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    zone_dict = zone.model_dump(mode="json")
    is_boundary_change = (
        _is_boundary_zone(existing)
        or _is_boundary_zone(zone_dict)
    )
    if is_boundary_change:
        try:
            updated = await boundary_verification_service.apply_boundary_change(
                runtime,
                lambda: _update_boundary_zone(repo, zone_dict, runtime),
            )
        except BoundaryValidationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    else:
        updated = repo.update_zone(zone_dict)
    if not updated:
        raise HTTPException(status_code=404, detail="Zone not found")
    _zones_last_modified = datetime.now(timezone.utc)
    hub = getattr(runtime, "websocket_hub", None)
    await _emit_zone_changed(hub, zone_id, "updated")
    persistence.add_audit_log(
        "map.zone.updated",
        resource=zone_id,
        details={
            "name": zone.name,
            "zone_kind": zone.zone_kind,
            "priority": zone.priority,
            "exclusion_zone": zone.exclusion_zone,
            "polygon": [{"latitude": p.latitude, "longitude": p.longitude} for p in zone.polygon],
        },
    )
    return zone_dict


@router.delete("/map/zones/{zone_id}", status_code=204)
async def delete_map_zone(zone_id: str, runtime: RuntimeContext = Depends(get_runtime)):
    global _zones_last_modified
    repo = getattr(runtime, "map_repository", None)
    if repo is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    # Load zone details before deletion so they can be recorded in the audit log
    zone_for_audit = repo.get_zone(zone_id)
    is_boundary = _is_boundary_zone(zone_for_audit)
    if is_boundary:
        try:
            deleted = await boundary_verification_service.apply_boundary_change(
                runtime,
                lambda: _delete_boundary_zone(repo, zone_id, runtime),
            )
        except BoundaryValidationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    else:
        deleted = repo.delete_zone(zone_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Zone not found")
    _zones_last_modified = datetime.now(timezone.utc)
    hub = getattr(runtime, "websocket_hub", None)
    await _emit_zone_changed(hub, zone_id, "deleted")
    persistence.add_audit_log(
        "map.zone.deleted",
        resource=zone_id,
        details=zone_for_audit or {"id": zone_id},
    )
    return Response(status_code=204)


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


_MAP_LOCATIONS_FILE = os.path.join(os.getcwd(), "data", "map_locations.json")


def _load_map_locations() -> MapLocations:
    try:
        with open(_MAP_LOCATIONS_FILE) as f:
            return MapLocations.model_validate(json.load(f))
    except Exception:
        return MapLocations()


def _save_map_locations(locations: MapLocations) -> None:
    try:
        os.makedirs(os.path.dirname(_MAP_LOCATIONS_FILE), exist_ok=True)
        tmp = _MAP_LOCATIONS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(locations.model_dump(mode="json"), f, indent=2)
        os.replace(tmp, _MAP_LOCATIONS_FILE)
    except Exception as exc:
        logger.warning("Failed to persist map locations: %s", exc)


_locations_store = _load_map_locations()
_locations_last_modified: datetime = datetime.now(timezone.utc)


@router.get("/map/locations", response_model=MapLocations)
def get_map_locations(request: Request):
    data = _locations_store.model_dump(mode="json")
    body = json.dumps(
        {
            "data": data,
            "last_modified": _locations_last_modified.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
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
        "Cache-Control": "no-cache",
    }
    return JSONResponse(content=data, headers=headers)


@router.put("/map/locations", response_model=MapLocations)
def put_map_locations(locations: MapLocations):
    global _locations_store
    _locations_store = locations
    global _locations_last_modified
    _locations_last_modified = datetime.now(timezone.utc)
    _save_map_locations(locations)
    return _locations_store


# TODO(v3): extract PlanningRepository(BaseRepository) once subsystem is end-to-end green - Issue #60


def _planning_jobs_service(runtime: RuntimeContext):
    """Return the canonical singleton when a lightweight test app skips lifespan."""
    if runtime.jobs_service is not None:
        return runtime.jobs_service
    from ..services.jobs_service import jobs_service

    return jobs_service


@router.get("/planning/jobs", response_model=list[PlanningJobResponse])
async def list_planning_jobs(runtime: RuntimeContext = Depends(get_runtime)):
    return _planning_jobs_service(runtime).list_persisted_planning_jobs()


@router.post("/planning/jobs", response_model=PlanningJobResponse, status_code=201)
async def create_planning_job(
    payload: dict[str, Any],
    runtime: RuntimeContext = Depends(get_runtime),
):
    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "name": str(payload.get("name") or f"Planning Job {job_id[:8]}"),
        "schedule": payload.get("schedule"),
        "zones": list(payload.get("zones") or []),
        "priority": int(payload.get("priority") or 1),
        "enabled": bool(payload.get("enabled", True)),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_run": None,
        "status": "pending",
        "pattern": str(payload.get("pattern") or "parallel"),
        "pattern_params": dict(payload.get("pattern_params") or {}),
    }
    persistence.save_planning_job(job)
    if payload.get("start_immediately"):
        state = await _planning_jobs_service(runtime).start_persisted_planning_job(job_id)
        if state.get("status") != "running":
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Planning job start was not accepted",
                    "job_id": job_id,
                    "status": state.get("status"),
                    "reason": state.get("error_message"),
                },
            )
        return state
    state = _planning_jobs_service(runtime).get_persisted_planning_job(job_id)
    return state or job


async def _control_planning_job(
    runtime: RuntimeContext,
    job_id: str,
    action: str,
) -> dict[str, Any]:
    try:
        if action == "start":
            state = await _planning_jobs_service(runtime).start_persisted_planning_job(job_id)
            if state.get("status") != "running":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Planning job start was not accepted",
                        "status": state.get("status"),
                        "reason": state.get("error_message"),
                    },
                )
            return state
        return await _planning_jobs_service(runtime).control_persisted_planning_job(job_id, action)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Planning job not found") from exc
    except HTTPException:
        raise
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/planning/jobs/{job_id}/start", response_model=PlanningJobResponse)
async def start_planning_job(
    job_id: str,
    runtime: RuntimeContext = Depends(get_runtime),
):
    return await _control_planning_job(runtime, job_id, "start")


@router.post("/planning/jobs/{job_id}/pause", response_model=PlanningJobResponse)
async def pause_planning_job(
    job_id: str,
    runtime: RuntimeContext = Depends(get_runtime),
):
    return await _control_planning_job(runtime, job_id, "pause")


@router.post("/planning/jobs/{job_id}/resume", response_model=PlanningJobResponse)
async def resume_planning_job(
    job_id: str,
    runtime: RuntimeContext = Depends(get_runtime),
):
    return await _control_planning_job(runtime, job_id, "resume")


@router.post("/planning/jobs/{job_id}/cancel", response_model=PlanningJobResponse)
async def cancel_planning_job(
    job_id: str,
    runtime: RuntimeContext = Depends(get_runtime),
):
    return await _control_planning_job(runtime, job_id, "cancel")


@router.delete("/planning/jobs/{job_id}")
async def delete_planning_job(
    job_id: str,
    runtime: RuntimeContext = Depends(get_runtime),
):
    job = _planning_jobs_service(runtime).get_persisted_planning_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Planning job not found")
    if job.get("status") in {"running", "paused"}:
        raise HTTPException(status_code=409, detail="Cancel the active planning job first")
    deleted = persistence.delete_planning_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Planning job not found")
    return Response(status_code=204)


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
        "markers": [],
        "provider": _map_provider_from_settings(),
        "updated_at": timestamp,
        "updated_by": "system",
    }


async def _load_map_configuration_envelope(
    config_id: str,
    map_repository=None,
) -> dict[str, Any]:
    default_envelope = _default_map_configuration_envelope(config_id)
    payload: dict[str, Any] = {}
    raw = await persistence.load_map_configuration(config_id)
    if not raw:
        envelope = default_envelope
    else:
        try:
            payload = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            logger.warning(
                "Stored map configuration %s is not valid JSON; using defaults", config_id
            )
            payload = {}

        if not isinstance(payload, dict):
            payload = {}

        envelope = {**default_envelope, **payload}
        envelope["config_id"] = config_id
        markers = envelope.get("markers")
        envelope["markers"] = markers if isinstance(markers, (list, dict)) else []
        envelope["provider"] = _normalize_map_provider(envelope.get("provider"))
        envelope["updated_at"] = str(envelope.get("updated_at") or default_envelope["updated_at"])
        envelope["updated_by"] = str(envelope.get("updated_by") or "system")

    # Compose zones from map_zones table (the authoritative source)
    if map_repository is not None:
        try:
            zones_from_db = map_repository.list_zones()
            if not zones_from_db:
                recovered_zones = _extract_legacy_envelope_zones(payload)
                if recovered_zones:
                    map_repository.save_zones(recovered_zones)
                    zones_from_db = map_repository.list_zones()
                    logger.warning(
                        "Recovered %d legacy zone(s) from map configuration envelope into map_zones",
                        len(zones_from_db),
                    )
            envelope["zones"] = zones_from_db
            envelope["_zones_source"] = "map_zones"
        except Exception as exc:
            logger.warning("Failed to load zones from map_repository: %s", exc)
            envelope["zones"] = []
            envelope["_zones_source"] = "error"
    else:
        envelope["zones"] = []
        envelope["_zones_source"] = "no_repository"

    return envelope


_SPATIAL_KEYS = frozenset({"zones", "boundaries", "exclusion_zones"})


async def _save_map_configuration_envelope(
    config_id: str,
    envelope: dict[str, Any],
    *,
    updated_by: str | None = None,
) -> dict[str, Any]:
    # Strip spatial keys — zones are owned by map_zones table, not this envelope
    spatial_keys_present = [k for k in _SPATIAL_KEYS if k in envelope]
    if spatial_keys_present:
        logger.warning(
            "Spatial keys %s stripped from map configuration envelope for config_id=%s. "
            "Use POST/PUT /api/v2/map/zones/{id} to manage zones.",
            spatial_keys_present,
            config_id,
        )

    # Load existing to preserve markers if not explicitly provided
    existing_raw = await persistence.load_map_configuration(config_id)
    existing: dict[str, Any] = {}
    if existing_raw:
        try:
            existing = json.loads(existing_raw)
        except (TypeError, json.JSONDecodeError):
            pass

    saved = {
        **_default_map_configuration_envelope(config_id),
        **{k: v for k, v in existing.items() if k not in _SPATIAL_KEYS},
        **{k: v for k, v in envelope.items() if k not in _SPATIAL_KEYS},
    }
    saved["config_id"] = config_id
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


def _validate_zone_against_existing(
    new_zone: "Zone",
    existing_zones: list[dict],
    *,
    skip_id: str | None = None,
) -> list[str]:
    """Return a list of zone ids that overlap with new_zone.

    existing_zones is a list of dicts from MapRepository.list_zones().
    skip_id allows excluding an existing zone (e.g. during update of self).
    """
    new_ring = [(p.latitude, p.longitude) for p in new_zone.polygon]
    if len(new_ring) < 3:
        return []

    candidate_rings: list[tuple[str, list]] = [(new_zone.id, new_ring)]
    for z in existing_zones:
        if z.get("id") == skip_id:
            continue
        polygon = z.get("polygon", [])
        ring = []
        for p in polygon:
            if isinstance(p, dict):
                ring.append((p.get("latitude", 0), p.get("longitude", 0)))
        if len(ring) >= 3:
            candidate_rings.append((z["id"], ring))

    if len(candidate_rings) < 2:
        return []

    try:
        from shapely.geometry import Polygon as ShapelyPolygon

        polys = []
        for zid, ring in candidate_rings:
            poly = ShapelyPolygon(ring)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if not poly.is_empty:
                polys.append((zid, poly))

        new_id, new_poly = polys[0]
        conflict_set: set[str] = set()
        for other_id, other_poly in polys[1:]:
            if new_poly.intersects(other_poly) and not new_poly.touches(other_poly):
                conflict_set.add(other_id)
        return sorted(conflict_set)
    except Exception:
        return []


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


def _repo_polygon_from_geojson_zone(entry: dict[str, Any]) -> list[dict[str, float]]:
    geometry = entry.get("geometry")
    if not isinstance(geometry, dict):
        return []
    if geometry.get("type") != "Polygon":
        return []
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        return []
    ring = coordinates[0]
    if not isinstance(ring, list):
        return []

    points: list[dict[str, float]] = []
    for point in ring:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            lng = float(point[0])
            lat = float(point[1])
        except (TypeError, ValueError):
            continue
        points.append({"latitude": lat, "longitude": lng})

    if len(points) < 3:
        return []
    if points[0] == points[-1]:
        points = points[:-1]
    return points if len(points) >= 3 else []


def _repo_zone_from_modern_zone(
    entry: dict[str, Any],
    *,
    zone_kind: str,
    fallback_id: str,
) -> dict[str, Any] | None:
    polygon = entry.get("polygon")
    if not isinstance(polygon, list):
        return None

    points: list[dict[str, float]] = []
    for point in polygon:
        if not isinstance(point, dict):
            continue
        try:
            lat = float(point.get("latitude"))
            lng = float(point.get("longitude"))
        except (TypeError, ValueError):
            continue
        points.append({"latitude": lat, "longitude": lng})

    if len(points) < 3:
        return None

    zone_id = str(entry.get("id") or entry.get("zone_id") or entry.get("name") or fallback_id)
    return {
        "id": zone_id,
        "name": str(entry.get("name") or zone_id),
        "polygon": points,
        "priority": int(entry.get("priority", 0) or 0),
        "exclusion_zone": zone_kind == "exclusion",
        "zone_kind": zone_kind,
    }


def _extract_legacy_envelope_zones(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Recover zones from legacy envelope formats used before map_zones became authoritative."""

    recovered: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    def _append(zone: dict[str, Any] | None) -> None:
        if not zone:
            return
        zone_id = str(zone.get("id") or "").strip()
        if not zone_id:
            return
        if zone_id in seen_ids:
            return
        seen_ids.add(zone_id)
        recovered.append(zone)

    # Legacy GeoJSON-style entries under "zones"
    raw_zones = payload.get("zones")
    if isinstance(raw_zones, list):
        for index, entry in enumerate(raw_zones):
            if not isinstance(entry, dict):
                continue
            zone_type = str(entry.get("zone_type") or "boundary").lower()
            zone_kind = (
                "boundary" if zone_type not in {"boundary", "exclusion", "mow"} else zone_type
            )
            polygon = _repo_polygon_from_geojson_zone(entry)
            if not polygon:
                continue
            zone_id = str(
                entry.get("zone_id")
                or entry.get("id")
                or entry.get("name")
                or f"{zone_kind}-{index + 1}"
            )
            _append(
                {
                    "id": zone_id,
                    "name": str(entry.get("name") or zone_id),
                    "polygon": polygon,
                    "priority": int(entry.get("priority", 0) or 0),
                    "exclusion_zone": zone_kind == "exclusion",
                    "zone_kind": zone_kind,
                }
            )

    # Legacy list formats with "coordinates" arrays
    for entry in _legacy_polygon_zones(payload.get("boundaries"), zone_type="boundary"):
        polygon = _repo_polygon_from_geojson_zone(entry)
        _append(
            {
                "id": str(entry.get("zone_id") or entry.get("name") or "boundary"),
                "name": str(entry.get("name") or entry.get("zone_id") or "boundary"),
                "polygon": polygon,
                "priority": 0,
                "exclusion_zone": False,
                "zone_kind": "boundary",
            }
        )
    for entry in _legacy_polygon_zones(payload.get("exclusion_zones"), zone_type="exclusion"):
        polygon = _repo_polygon_from_geojson_zone(entry)
        _append(
            {
                "id": str(entry.get("zone_id") or entry.get("name") or "exclusion"),
                "name": str(entry.get("name") or entry.get("zone_id") or "exclusion"),
                "polygon": polygon,
                "priority": 0,
                "exclusion_zone": True,
                "zone_kind": "exclusion",
            }
        )

    # Transitional MapConfiguration-style envelope fields
    boundary = payload.get("boundary_zone")
    if isinstance(boundary, dict):
        _append(_repo_zone_from_modern_zone(boundary, zone_kind="boundary", fallback_id="boundary"))
    exclusions = payload.get("exclusion_zones")
    if isinstance(exclusions, list):
        for index, entry in enumerate(exclusions):
            if isinstance(entry, dict):
                _append(
                    _repo_zone_from_modern_zone(
                        entry,
                        zone_kind="exclusion",
                        fallback_id=f"exclusion-{index + 1}",
                    )
                )
    mows = payload.get("mowing_zones")
    if isinstance(mows, list):
        for index, entry in enumerate(mows):
            if isinstance(entry, dict):
                _append(
                    _repo_zone_from_modern_zone(
                        entry, zone_kind="mow", fallback_id=f"mow-{index + 1}"
                    )
                )

    return [z for z in recovered if isinstance(z.get("polygon"), list) and len(z["polygon"]) >= 3]


def _persist_map_provider_setting(provider: str, request: Request | None = None) -> None:
    try:
        from .routers.settings import _load_ui_settings, _save_ui_settings

        sections = _load_ui_settings(request)
        maps_settings = dict(sections.get("maps", {}))
        maps_settings["provider"] = "google" if provider == "google-maps" else "osm"
        sections["maps"] = maps_settings
        _save_ui_settings(sections, request)
    except Exception as exc:
        logger.warning("Failed to persist maps provider setting: %s", exc)


@router.get("/map/configuration")
async def get_map_configuration(
    config_id: str = Query("default"),
    simulate_fallback: str | None = Query(default=None),
    runtime: RuntimeContext = Depends(get_runtime),
):
    map_repo = getattr(runtime, "map_repository", None)
    envelope = await _load_map_configuration_envelope(config_id, map_repository=map_repo)
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
    request: Request,
    config_id: str = Query("default"),
    runtime: RuntimeContext = Depends(get_runtime),
):
    # 410 Gone: zones are no longer stored in the configuration envelope
    spatial_keys = [k for k in ("zones", "boundaries", "exclusion_zones") if k in envelope]
    if spatial_keys:
        raise HTTPException(
            status_code=410,
            detail=(
                "Zones are no longer stored on /map/configuration. "
                "Use POST/PUT/DELETE /api/v2/map/zones/{id}."
            ),
        )

    markers = envelope.get("markers")
    if markers is not None and not isinstance(markers, (list, dict)):
        raise HTTPException(status_code=422, detail="markers must be a list or object")

    saved = await _save_map_configuration_envelope(
        config_id,
        {
            **envelope,
            "markers": markers if markers is not None else envelope.get("markers", []),
        },
        updated_by=str(envelope.get("updated_by") or "api"),
    )
    _persist_map_provider_setting(saved["provider"], request)
    return {
        "status": "accepted",
        "config_id": config_id,
        "updated_at": saved["updated_at"],
        "updated_by": saved["updated_by"],
    }


@router.post("/map/provider-fallback")
async def trigger_map_provider_fallback(request: Request, config_id: str = Query("default")):
    from ..services.maps_service import maps_service

    await persistence.update_map_configuration_provider(config_id, "osm")
    _persist_map_provider_setting("osm", request)
    now = datetime.now(timezone.utc).isoformat()
    try:
        maps_service.configure("osm")
    except Exception:
        logger.debug("Maps service provider fallback sync skipped", exc_info=True)
    return {
        "success": True,
        "provider": "osm",
        "updated_at": now,
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
    motor_connected: bool = True
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
        # Use cached telemetry to avoid blocking the event loop with a live sensor read.
        # _generate_telemetry() reads all sensors synchronously and takes 600-800 ms,
        # which is long enough to trigger the watchdog when called every 60 s.
        cached = await websocket_hub.get_cached_telemetry()
        if cached.get("source") != "unavailable":
            telemetry_snapshot = cached
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


@router.post("/hardware/robohat/soft-reset")
async def robohat_soft_reset():
    """Send a CircuitPython soft-reload (Ctrl+D) to restart the RoboHAT firmware.

    Use when the motor controller is stuck in REPL mode, the RC handshake is
    stalled, or PWM commands are not being acknowledged.  Safe to call at any
    time — neutral PWM is sent before the reset signal.
    """
    from ..services.robohat_service import get_robohat_service

    robohat = get_robohat_service()
    if robohat is None:
        return {"success": False, "message": "RoboHAT service not initialised"}

    result = await robohat.soft_reset()
    status_code = 200 if result["success"] else 503
    from fastapi.responses import JSONResponse

    return JSONResponse(content=result, status_code=status_code)


class Vector2D(BaseModel):
    linear: float
    angular: float


class DriveContractIn(BaseModel):
    session_id: str
    vector: Vector2D
    duration_ms: int
    reason: Optional[str] = None


@router.post("/control/drive", response_model=ControlResponseV2, status_code=202)
async def control_drive_v2(
    cmd: dict, request: Request, runtime: RuntimeContext = Depends(get_runtime)
):
    """Execute drive command with safety checks and audit logging"""
    from ..control.commands import CommandStatus, DriveCommand

    timestamp = datetime.now(timezone.utc)

    if "session_id" not in cmd:
        raise HTTPException(
            status_code=400,
            detail=(
                "Legacy drive payloads are not supported. "
                "Use session_id + vector + duration_ms contract payload."
            ),
        )

    # Contract-style payload
    if runtime.command_gateway.is_emergency_active(request):
        try:
            cmd_details = dict(cmd)
            if "session_id" in cmd_details:
                cmd_details["session_id"] = "***"
        except Exception:
            cmd_details = {}
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

    throttle = float(cmd.get("vector", {}).get("linear", 0.0))
    turn = float(cmd.get("vector", {}).get("angular", 0.0))
    try:
        speed_limit = float(cmd.get("max_speed_limit", 0.8))
    except (TypeError, ValueError):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="max_speed_limit must be numeric"
        )
    speed_limit = max(0.0, min(1.0, speed_limit))
    left_speed = throttle - turn
    right_speed = throttle + turn
    left_speed = max(-speed_limit, min(speed_limit, left_speed))
    right_speed = max(-speed_limit, min(speed_limit, right_speed))

    drive_cmd = DriveCommand(
        left=left_speed,
        right=right_speed,
        source="manual",
        duration_ms=duration_ms,
        session_id=cmd.get("session_id"),
        max_speed_limit=speed_limit,
        legacy=False,
    )
    outcome = await runtime.command_gateway.dispatch_drive(drive_cmd, request=request)

    if outcome.status == CommandStatus.BLOCKED and outcome.active_interlocks:
        _transient = {
            "telemetry_unavailable",
            "telemetry_stale",
            "location_awareness_unavailable",
            "obstacle_detected",
        }
        has_only_transient = all(i in _transient for i in outcome.active_interlocks)
        lockout_until_str: str | None = None
        if has_only_transient:
            lockout_until_str = (datetime.now(timezone.utc) + timedelta(seconds=3)).isoformat()

        try:
            details_cmd = dict(cmd)
            if "session_id" in details_cmd:
                details_cmd["session_id"] = "***"
        except Exception:
            details_cmd = {}
        persistence.add_audit_log(
            "control.drive.blocked",
            details={
                "reason": outcome.status_reason,
                "active_interlocks": outcome.active_interlocks,
                "command": details_cmd,
            },
        )
        blocked_response = ControlResponseV2(
            accepted=False,
            audit_id=outcome.audit_id,
            result="blocked",
            status_reason=outcome.status_reason,
            safety_checks=[
                "emergency_stop_check",
                "command_validation",
                "telemetry_source_check",
                "location_awareness_check",
                "obstacle_clearance_check",
            ],
            active_interlocks=outcome.active_interlocks,
            remediation={
                "docs_link": "/docs/OPERATIONS.md#manual-drive-safety-gating",
                "message": "Clear nearby obstacles and restore fresh hardware telemetry before retrying manual movement.",
            },
            telemetry_snapshot=None,
            until=lockout_until_str,
            timestamp=timestamp.isoformat(),
        )
        return JSONResponse(status_code=423, content=blocked_response.model_dump(mode="json"))

    accepted = outcome.status in (CommandStatus.ACCEPTED, CommandStatus.QUEUED)
    motor_connected = outcome.status == CommandStatus.ACCEPTED
    result = outcome.status.value if accepted else "rejected"
    response = ControlResponseV2(
        accepted=accepted,
        motor_connected=motor_connected,
        audit_id=outcome.audit_id,
        result=result,
        status_reason=outcome.status_reason,
        watchdog_latency_ms=outcome.watchdog_latency_ms,
        safety_checks=["emergency_stop_check", "command_validation"],
        active_interlocks=[],
        telemetry_snapshot={
            "component_id": "drive_left",
            "status": "healthy" if accepted else "warning",
            "latency_ms": outcome.watchdog_latency_ms or 0.0,
            "speed_limit": speed_limit,
        },
        timestamp=timestamp.isoformat(),
    )

    global _last_drive_audit_at
    try:
        details_cmd = dict(cmd)
        if "session_id" in details_cmd:
            details_cmd["session_id"] = "***"
        principal = session_context.get("principal") if session_context else None
        if principal:
            details_cmd["principal"] = principal
        details_cmd["max_speed_limit"] = speed_limit
    except Exception:
        details_cmd = {}
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


@router.get("/sensors/encoders")
async def get_encoder_status(runtime: RuntimeContext = Depends(get_runtime)):
    """Return current encoder telemetry from RoboHAT."""
    from ..services.robohat_service import get_robohat_service

    robohat = runtime.robohat or get_robohat_service()
    if robohat is None:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "encoder_feedback_ok": False,
            "encoder_position": 0,
            "encoder_1_position": 0,
            "encoder_2_position": 0,
            "encoder_rpm": 0.0,
            "encoder_1_rpm": 0.0,
            "encoder_2_rpm": 0.0,
            "serial_connected": False,
            "timestamp": now,
        }

    status = robohat.get_status().to_dict()
    return {
        "encoder_feedback_ok": bool(status.get("encoder_feedback_ok", False)),
        "encoder_position": int(status.get("encoder_position", 0) or 0),
        "encoder_1_position": int(status.get("encoder_1_position", 0) or 0),
        "encoder_2_position": int(status.get("encoder_2_position", 0) or 0),
        "encoder_rpm": float(status.get("encoder_rpm", 0.0) or 0.0),
        "encoder_1_rpm": float(status.get("encoder_1_rpm", 0.0) or 0.0),
        "encoder_2_rpm": float(status.get("encoder_2_rpm", 0.0) or 0.0),
        "serial_connected": bool(status.get("serial_connected", False)),
        "timestamp": status.get("timestamp"),
    }


_PRESET_TURN_SPEED = 0.5
_PRESET_TURN_TIMEOUT_S = 8.0  # must be < axios 10 s client timeout
_PRESET_TURN_DPS = 60.0  # fallback timed rate (degrees per second)


@router.post("/control/preset-turn")
async def control_preset_turn(
    cmd: dict, request: Request, runtime: RuntimeContext = Depends(get_runtime)
):
    """Execute a closed-loop preset turn using IMU heading feedback.

    POST /api/v2/control/preset-turn
    Body: {
        "session_id": "<session>",
        "target_degrees": 90.0,    # positive = CW (right), negative = CCW (left)
        "speed": 0.5               # optional, default 0.5
    }

    Returns:
    {
        "ok": bool,
        "target_degrees": float,
        "actual_degrees": float,
        "duration_ms": int,
        "method": "imu" | "timed"
    }
    """
    import os

    from ..control.commands import CommandStatus, DriveCommand
    from ..services.navigation_service import NavigationService

    if runtime.command_gateway.is_emergency_active(request):
        return JSONResponse(status_code=403, content={"detail": "Emergency stop active"})

    session_context = _resolve_manual_session(cmd.get("session_id"))
    if session_context is None:
        return JSONResponse(status_code=403, content={"detail": "Invalid or expired session"})

    try:
        target_degrees = float(cmd.get("target_degrees", 0.0))
    except (TypeError, ValueError):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="target_degrees must be numeric"
        )
    if abs(target_degrees) > 360.0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="target_degrees must be between -360 and 360"
        )
    if target_degrees == 0.0:
        return {
            "ok": True,
            "target_degrees": 0.0,
            "actual_degrees": 0.0,
            "duration_ms": 0,
            "method": "none",
            "source": "simulated" if os.getenv("SIM_MODE", "0") == "1" else "hardware",
        }

    try:
        speed = float(cmd.get("speed", _PRESET_TURN_SPEED))
    except (TypeError, ValueError):
        speed = _PRESET_TURN_SPEED
    speed = max(0.1, min(1.0, speed))

    # CW (positive): right forward, left backward.
    # _mix_arcade_to_pwm uses angular=(right-left)/2 (inverted vs standard) to
    # compensate for MDDRC10 physical wiring swap, so we swap our signs here so
    # the net result is the correct physical turn direction.
    turn_sign = 1.0 if target_degrees > 0 else -1.0
    left_cmd = -turn_sign * speed
    right_cmd = turn_sign * speed

    start_time = time.monotonic()
    sim_mode = os.getenv("SIM_MODE", "0") == "1"

    if sim_mode:
        duration_s = abs(target_degrees) / _PRESET_TURN_DPS
        await asyncio.sleep(duration_s)
        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        return {
            "ok": True,
            "target_degrees": target_degrees,
            "actual_degrees": target_degrees,
            "duration_ms": elapsed_ms,
            "method": "simulation",
            "source": "simulated",
        }

    nav_service = NavigationService.get_instance()
    initial_heading = nav_service.navigation_state.heading if nav_service else None

    if initial_heading is None:
        return JSONResponse(
            status_code=409,
            content={
                "ok": False,
                "status_reason": "heading_unavailable",
                "detail": "Fresh IMU heading is required for a preset turn",
            },
        )

    async def dispatch_turn(left: float, right: float) -> None:
        outcome = await runtime.command_gateway.dispatch_drive(
            DriveCommand(
                left=left,
                right=right,
                source="manual",
                duration_ms=350,
                session_id=cmd.get("session_id"),
                max_speed_limit=speed,
                legacy=False,
            ),
            request=request,
        )
        if outcome.status not in (CommandStatus.ACCEPTED, CommandStatus.QUEUED):
            raise HTTPException(
                status_code=423,
                detail={
                    "status_reason": outcome.status_reason or outcome.status.value,
                    "active_interlocks": outcome.active_interlocks,
                    "audit_id": outcome.audit_id,
                },
            )

    cumulative = 0.0
    prev_heading = float(initial_heading)
    timed_out = False

    try:
        while abs(cumulative) < abs(target_degrees):
            if time.monotonic() - start_time > _PRESET_TURN_TIMEOUT_S:
                timed_out = True
                break
            await dispatch_turn(left_cmd, right_cmd)
            await asyncio.sleep(0.1)
            curr_heading = nav_service.navigation_state.heading
            if curr_heading is None:
                raise HTTPException(status_code=409, detail="IMU heading was lost during preset turn")
            curr = float(curr_heading)
            step = (curr - prev_heading + 180.0) % 360.0 - 180.0
            cumulative += step
            prev_heading = curr
    finally:
        await dispatch_turn(0.0, 0.0)

    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    return {
        "ok": not timed_out,
        "target_degrees": target_degrees,
        "actual_degrees": round(cumulative, 1),
        "duration_ms": elapsed_ms,
        "method": "imu",
        "source": "hardware",
    }


class BladeContractIn(BaseModel):
    session_id: str
    action: str
    reason: Optional[str] = None


@router.post("/control/blade")
async def control_blade_v2(
    cmd: dict, request: Request, runtime: RuntimeContext = Depends(get_runtime)
):
    """Execute blade command with safety interlocks and audit logging."""
    from ..control.commands import BladeCommand, CommandStatus

    audit_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)

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
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Invalid blade command — provide 'active' (bool) or 'action' (enable/disable)"
            },
        )

    session_id = cmd.get("session_id")
    if desired:
        _resolve_manual_session(session_id)

    blade_cmd = BladeCommand(
        active=desired,
        source="manual",
        session_id=session_id,
        motors_active=_legacy_motors_active,
    )
    outcome = await runtime.command_gateway.dispatch_blade(blade_cmd, request=request)

    if outcome.status == CommandStatus.BLOCKED:
        if "motors_active" in (outcome.status_reason or ""):
            body = {
                "detail": "safety_interlock: motors_active — blade enable blocked while motors running"
            }
            persistence.add_audit_log(
                "control.blade.blocked", details={"command": cmd, "response": body}
            )
            return JSONResponse(status_code=403, content=body)
        if "QUALIFICATION_" in (outcome.status_reason or ""):
            reason_codes = [code for code in str(outcome.status_reason).split(";") if code]
            body = {
                "detail": "qualification_required: blade enable blocked until current qualification evidence passes",
                "status_reason": outcome.status_reason,
                "reason_codes": reason_codes,
            }
            persistence.add_audit_log(
                "control.blade.blocked", details={"command": cmd, "response": body}
            )
            return JSONResponse(status_code=409, content=body)
        body = {"detail": "safety_interlock: emergency_stop_active — blade commands blocked"}
        persistence.add_audit_log(
            "control.blade.blocked", details={"command": cmd, "response": body}
        )
        return JSONResponse(status_code=409, content=body)

    ok = outcome.status in (CommandStatus.ACCEPTED, CommandStatus.QUEUED)
    body = {
        "accepted": ok,
        "audit_id": audit_id,
        "result": "accepted" if ok else "rejected",
        "blade_active": desired if ok else _blade_state.get("active", False),
        "blade_status": "ENABLED"
        if (ok and desired)
        else ("LOCKED_OUT" if desired else "DISABLED"),
        "status_reason": outcome.status_reason,
        "timestamp": timestamp.isoformat(),
    }
    persistence.add_audit_log("control.blade", details={"command": cmd, "response": body})
    return JSONResponse(status_code=200, content=body)


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
async def control_start_navigation(runtime: RuntimeContext = Depends(get_runtime)):
    """Reject legacy autonomous start; callers must start a real mission."""
    from ..services.navigation_service import NavigationService

    nav_service = NavigationService.get_instance()
    if runtime.command_gateway.is_emergency_active():
        return _navigation_error_response(
            nav_service,
            status_label="emergency_stop_active",
            detail="Navigation start is blocked while emergency stop is active.",
        )
    return JSONResponse(
        status_code=409,
        content={
            "ok": False,
            "status": "not_supported",
            "reason": "MISSION_EXECUTOR_REQUIRED",
            "detail": (
                "Legacy /control/start does not start an autonomous executor. "
                "Create and start a mission with /api/v2/missions/{id}/start."
            ),
            **_control_navigation_snapshot(nav_service),
        },
    )


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
async def control_resume_navigation(runtime: RuntimeContext = Depends(get_runtime)):
    """Resume navigation after a pause."""
    from ..services.navigation_service import NavigationService

    nav_service = NavigationService.get_instance()
    if runtime.command_gateway.is_emergency_active():
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
async def control_return_home(runtime: RuntimeContext = Depends(get_runtime)):
    """Create the canonical blade-off return mission and return its authoritative identity."""
    from ..services.navigation_service import NavigationService
    from ..services.mission_service import MissionError

    nav_service = NavigationService.get_instance()
    if runtime.command_gateway.is_emergency_active():
        return _navigation_error_response(
            nav_service,
            status_label="emergency_stop_active",
            detail="Return-home is blocked while emergency stop is active.",
        )
    try:
        mission = await runtime.mission_service.start_return_home()
    except MissionError as exc:
        return _navigation_error_response(
            nav_service,
            status_label="return_home_unavailable",
            detail=str(exc),
        )

    return {
        "ok": True,
        "status": "returning_home",
        "mission_id": mission.id,
        "mission_status": "running",
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
