"""Parcel helper, boundary capture, safe buffer, and verification APIs."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from ..core.runtime import RuntimeContext, get_runtime
from ..services import boundary_capture
from ..services.boundary_verification import boundary_verification_service
from ..services.geofence_buffer import default_buffer_meters, get_safe_boundary, save_safe_boundary
from ..services.maps_service import MapsService
from ..services.parcel_boundary import (
    BoundaryValidationError,
    clear_imported_property_boundary,
    get_imported_property_boundary,
    parse_boundary_payload,
    save_imported_property_boundary,
)
from ..services.parcel_sources.arcgis_parcel_source import ArcGISParcelSource

router = APIRouter(prefix="/boundary", tags=["boundary"])
parcel_router = APIRouter(prefix="/parcel", tags=["parcel-boundary"])
capture_router = APIRouter(prefix="/boundary-capture", tags=["boundary-capture"])
verification_router = APIRouter(prefix="/boundary-verification", tags=["boundary-verification"])


class CoordinatesPayload(BaseModel):
    coordinates: list[dict[str, float]]


class FetchByPointRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class FetchByAddressRequest(BaseModel):
    address: str = Field(min_length=1)


class BoundaryPointRequest(BaseModel):
    source: str
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class GenerateSafeRequest(BaseModel):
    coordinates: list[dict[str, float]] | None = None
    buffer_meters: float | None = Field(default=None, ge=0, le=10)


class FinishCaptureRequest(BaseModel):
    buffer_meters: float | None = Field(default=None, ge=0, le=10)


class VerificationStartRequest(BaseModel):
    coordinates: list[dict[str, float]]
    operator_confirmed: bool = False
    blade_physically_disabled: bool = False
    route_clear_confirmed: bool = False
    physical_intervention: str = Field(default="", max_length=240)


def _raise_bad_request(exc: Exception) -> None:
    raise HTTPException(status_code=422, detail=str(exc)) from exc


def _current_confirmed_boundary_zone(repository: Any) -> dict[str, Any] | None:
    """Resolve the same highest-priority boundary zone used by the Maps UI."""
    legacy = repository.get_zone("confirmed_mowing_boundary")
    if legacy and legacy.get("polygon"):
        return legacy
    candidates = [
        zone
        for zone in repository.list_zones()
        if str(zone.get("zone_kind") or zone.get("zone_type") or "").lower() == "boundary"
        and not bool(zone.get("exclusion_zone"))
        and zone.get("polygon")
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda zone: (-int(zone.get("priority", 0) or 0), str(zone.get("id", ""))),
    )[0]


async def _request_payload(request: Request) -> str | dict[str, Any] | list[Any]:
    content_type = request.headers.get("content-type", "")
    raw = await request.body()
    if not raw:
        return {}
    if "application/json" in content_type:
        return json.loads(raw)
    return raw.decode("utf-8")


@parcel_router.post("/import")
async def import_property_boundary(
    request: Request,
    file: UploadFile | None = File(default=None),
):
    try:
        if file is not None:
            raw: str | bytes | dict[str, Any] | list[Any] = await file.read()
            filename = file.filename or ""
            source_detail = f"{filename or 'uploaded file'}"
        else:
            raw = await _request_payload(request)
            filename = ""
            source_detail = "Pasted boundary"
        coordinates = parse_boundary_payload(raw, filename=filename)
        return save_imported_property_boundary(
            coordinates,
            source="manual_upload",
            source_detail=source_detail,
        )
    except (BoundaryValidationError, json.JSONDecodeError) as exc:
        _raise_bad_request(exc)


@parcel_router.get("/imported")
async def get_imported_boundary():
    payload = get_imported_property_boundary()
    return payload or {"coordinates": [], "helper_only": True, "status": "empty"}


@parcel_router.post("/clear")
async def clear_imported_boundary():
    clear_imported_property_boundary()
    return {"success": True}


@parcel_router.post("/fetch-by-point")
async def fetch_parcel_by_point(payload: FetchByPointRequest):
    source_type = os.getenv("PARCEL_SOURCE_TYPE", "").strip().lower()
    if source_type not in {"arcgis", "county_arcgis"}:
        raise HTTPException(status_code=400, detail="Parcel point lookup is not configured")
    try:
        result = await ArcGISParcelSource().find_parcel_by_point(payload.lat, payload.lng)
        coordinates = parse_boundary_payload(result["coordinates"])
        saved = save_imported_property_boundary(
            coordinates,
            source="county_arcgis",
            source_detail=result.get("source_detail") or "ArcGIS parcel source",
            metadata={"attributes": result.get("attributes", {})},
        )
        return {"success": True, **saved}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@parcel_router.post("/fetch-by-address")
async def fetch_parcel_by_address(payload: FetchByAddressRequest):
    source_type = os.getenv("PARCEL_SOURCE_TYPE", "").strip().lower()
    if source_type not in {"arcgis", "county_arcgis"}:
        raise HTTPException(
            status_code=400,
            detail="Parcel address lookup is unavailable because parcel lookup is not configured",
        )
    maps = MapsService(provider="leaflet", bypass_external=False)
    geocoded = await maps.geocode(payload.address)
    if not geocoded or geocoded.get("lat") is None or geocoded.get("lng") is None:
        raise HTTPException(status_code=400, detail="Address geocoding is unavailable or returned no result")
    return await fetch_parcel_by_point(
        FetchByPointRequest(lat=float(geocoded["lat"]), lng=float(geocoded["lng"]))
    )


@capture_router.post("/start")
async def start_capture():
    return boundary_capture.start_boundary_capture()


@capture_router.post("/add-point")
async def add_capture_point(
    payload: BoundaryPointRequest,
    runtime: RuntimeContext = Depends(get_runtime),
):
    try:
        return boundary_capture.add_boundary_point(
            source=payload.source,
            runtime=runtime,
            latitude=payload.lat,
            longitude=payload.lng,
        )
    except BoundaryValidationError as exc:
        _raise_bad_request(exc)


@capture_router.post("/undo")
async def undo_capture_point():
    try:
        return boundary_capture.undo_last_boundary_point()
    except BoundaryValidationError as exc:
        _raise_bad_request(exc)


@capture_router.post("/finish")
async def finish_capture(
    payload: FinishCaptureRequest | None = None,
    runtime: RuntimeContext = Depends(get_runtime),
):
    try:
        buffer_meters = payload.buffer_meters if payload else None
        if buffer_meters is None:
            buffer_meters = float(
                getattr(
                    getattr(runtime, "safety_limits", None),
                    "geofence_buffer_meters",
                    default_buffer_meters(),
                )
            )
        return boundary_capture.finish_boundary_capture(
            map_repository=getattr(runtime, "map_repository", None),
            buffer_meters=buffer_meters,
        )
    except BoundaryValidationError as exc:
        _raise_bad_request(exc)


@capture_router.post("/cancel")
async def cancel_capture():
    return boundary_capture.cancel_boundary_capture()


@capture_router.get("/status")
async def capture_status():
    return boundary_capture.get_boundary_capture_status()


@router.post("/generate-safe")
async def generate_safe_boundary(
    payload: GenerateSafeRequest,
    runtime: RuntimeContext = Depends(get_runtime),
):
    try:
        coordinates = payload.coordinates
        if coordinates is None:
            repo = getattr(runtime, "map_repository", None)
            zone = _current_confirmed_boundary_zone(repo) if repo is not None else None
            if not zone:
                raise BoundaryValidationError("No confirmed boundary coordinates provided")
            coordinates = zone["polygon"]
        buffer_meters = payload.buffer_meters
        if buffer_meters is None:
            buffer_meters = float(
                getattr(
                    getattr(runtime, "safety_limits", None),
                    "geofence_buffer_meters",
                    default_buffer_meters(),
                )
            )
        return save_safe_boundary(coordinates, buffer_meters=buffer_meters)
    except BoundaryValidationError as exc:
        _raise_bad_request(exc)


@router.get("/safe")
async def read_safe_boundary():
    payload = get_safe_boundary()
    return payload or {
        "coordinates": [],
        "buffer_meters": default_buffer_meters(),
        "status": "empty",
    }


@verification_router.post("/start")
async def start_verification(
    payload: VerificationStartRequest,
    runtime: RuntimeContext = Depends(get_runtime),
):
    try:
        return await boundary_verification_service.start(
            payload.coordinates,
            runtime,
            operator_confirmed=payload.operator_confirmed,
            blade_physically_disabled=payload.blade_physically_disabled,
            route_clear_confirmed=payload.route_clear_confirmed,
            physical_intervention=payload.physical_intervention,
        )
    except BoundaryValidationError as exc:
        _raise_bad_request(exc)


@verification_router.post("/next")
async def verification_next(runtime: RuntimeContext = Depends(get_runtime)):
    try:
        return await boundary_verification_service.next_point(runtime)
    except BoundaryValidationError as exc:
        _raise_bad_request(exc)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@verification_router.post("/confirm-point")
async def verification_confirm(runtime: RuntimeContext = Depends(get_runtime)):
    try:
        return await boundary_verification_service.confirm_point(runtime)
    except BoundaryValidationError as exc:
        _raise_bad_request(exc)


@verification_router.post("/reject-point")
async def verification_reject(runtime: RuntimeContext = Depends(get_runtime)):
    try:
        return await boundary_verification_service.reject_point(runtime)
    except BoundaryValidationError as exc:
        _raise_bad_request(exc)


@verification_router.post("/cancel")
async def verification_cancel(runtime: RuntimeContext = Depends(get_runtime)):
    return await boundary_verification_service.cancel(runtime)


@verification_router.get("/status")
async def verification_status(runtime: RuntimeContext = Depends(get_runtime)):
    return await boundary_verification_service.status(runtime)
