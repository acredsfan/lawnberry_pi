"""Boundary capture sessions for manual, GPS, and RTK-assisted workflows."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from .boundary_paths import BOUNDARY_CAPTURE_SESSION, MOWING_BOUNDARY_CONFIRMED, boundary_file
from .geofence_buffer import save_safe_boundary
from .parcel_boundary import BoundaryValidationError, normalize_boundary_to_lat_lng


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(filename: str, payload: dict[str, Any]) -> None:
    path = boundary_file(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read_session() -> dict[str, Any] | None:
    path = boundary_file(BOUNDARY_CAPTURE_SESSION)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_session(session: dict[str, Any]) -> dict[str, Any]:
    _write_json(BOUNDARY_CAPTURE_SESSION, session)
    return session


def _current_position(runtime: Any) -> dict[str, float]:
    nav = getattr(runtime, "navigation", None)
    pos = getattr(getattr(nav, "navigation_state", None), "current_position", None)
    lat = getattr(pos, "latitude", None)
    lng = getattr(pos, "longitude", None)
    if lat is None or lng is None:
        raise BoundaryValidationError("Current GPS/RTK position is unavailable")
    return {"latitude": float(lat), "longitude": float(lng)}


def start_boundary_capture() -> dict[str, Any]:
    session = {
        "session_id": str(uuid.uuid4()),
        "status": "active",
        "created_at": _now(),
        "updated_at": _now(),
        "points": [],
    }
    return _write_session(session)


def get_boundary_capture_status() -> dict[str, Any]:
    return _read_session() or {"status": "idle", "points": []}


def add_boundary_point(
    *,
    source: str,
    runtime: Any = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> dict[str, Any]:
    session = _read_session()
    if not session or session.get("status") != "active":
        raise BoundaryValidationError("No active boundary capture session")
    if source == "current_gps":
        point = _current_position(runtime)
    elif source == "manual" and latitude is not None and longitude is not None:
        point = {"latitude": float(latitude), "longitude": float(longitude)}
    else:
        raise BoundaryValidationError("Use source=current_gps or source=manual with latitude/longitude")
    normalize_boundary_to_lat_lng(session["points"] + [point], order="latlng") if len(session["points"]) >= 2 else None
    session["points"].append(point)
    session["updated_at"] = _now()
    return _write_session(session)


def undo_last_boundary_point() -> dict[str, Any]:
    session = _read_session()
    if not session or session.get("status") != "active":
        raise BoundaryValidationError("No active boundary capture session")
    if session["points"]:
        session["points"].pop()
    session["updated_at"] = _now()
    return _write_session(session)


def cancel_boundary_capture() -> dict[str, Any]:
    session = _read_session() or {"points": []}
    session["status"] = "cancelled"
    session["updated_at"] = _now()
    return _write_session(session)


def save_confirmed_mowing_boundary(
    coordinates: list[dict[str, float]],
    *,
    map_repository: Any | None = None,
    buffer_meters: float | None = None,
    zone_id: str = "confirmed_mowing_boundary",
) -> dict[str, Any]:
    normalized = normalize_boundary_to_lat_lng(coordinates, order="latlng")
    confirmed = {
        "source": "user_confirmed",
        "created_at": _now(),
        "coordinates": normalized,
    }
    _write_json(MOWING_BOUNDARY_CONFIRMED, confirmed)
    if map_repository is not None:
        zone = {
            "id": zone_id,
            "name": "Confirmed Mowing Boundary",
            "polygon": normalized,
            "priority": 100,
            "exclusion_zone": False,
            "zone_kind": "boundary",
        }
        if map_repository.get_zone(zone_id):
            map_repository.update_zone(zone)
        else:
            map_repository.save_zone(zone)
    safe = save_safe_boundary(normalized, buffer_meters=buffer_meters)
    return {"confirmed": confirmed, "safe": safe}


def finish_boundary_capture(
    *,
    map_repository: Any | None = None,
    buffer_meters: float | None = None,
) -> dict[str, Any]:
    session = _read_session()
    if not session or session.get("status") != "active":
        raise BoundaryValidationError("No active boundary capture session")
    result = save_confirmed_mowing_boundary(
        session.get("points") or [],
        map_repository=map_repository,
        buffer_meters=buffer_meters,
    )
    session["status"] = "finished"
    session["updated_at"] = _now()
    session["result"] = result
    _write_session(session)
    return session
