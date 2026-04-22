from __future__ import annotations
# ruff: noqa: I001

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.persistence import persistence
from ..core.robot_state_manager import get_robot_state_manager
from ..models.geofence import Geofence, LatLng
from ..models.robot_state import NavigationMode
from ..nav.coverage_planner import plan_coverage
from ..nav.geoutils import haversine_m, point_in_polygon


router = APIRouter()


# In-memory debug state (simulation/testing only)
_debug_position: dict[str, float] | None = None  # {latitude, longitude, accuracy_m}
_active_geofence: Geofence | None = None
_waypoints: list[dict[str, Any]] = []
_waypoint_reached: bool | None = None
_current_waypoint_id: str | None = None


class GPSInject(BaseModel):
    latitude: float
    longitude: float
    accuracy_m: float | None = None


@router.post("/api/v2/debug/gps/inject")
async def debug_gps_inject(pos: GPSInject):
    global _debug_position
    _debug_position = {
        "latitude": pos.latitude,
        "longitude": pos.longitude,
        "accuracy_m": pos.accuracy_m or 5.0,
    }
    # Update RobotState immediately
    mgr = get_robot_state_manager()
    st = mgr.get_state()
    st.position.latitude = pos.latitude
    st.position.longitude = pos.longitude
    st.position.accuracy_m = pos.accuracy_m or 5.0
    st.touch()
    _update_geofence_and_waypoint()
    return {"ok": True}


class GeofenceIn(BaseModel):
    geofence_id: str = "default"
    boundary: list[LatLng]
    buffer_distance_m: float = 0.0


@router.post("/api/v2/debug/geofence")
async def debug_geofence_set(f: GeofenceIn):
    global _active_geofence
    _active_geofence = Geofence(
        geofence_id=f.geofence_id,
        boundary=f.boundary,
        buffer_distance_m=f.buffer_distance_m,
    )
    _update_geofence_and_waypoint()
    return {"ok": True}


class WaypointIn(BaseModel):
    waypoint_id: str
    latitude: float
    longitude: float
    arrival_threshold_m: float = Field(1.0, ge=0.1, le=10.0)


class WaypointList(BaseModel):
    waypoints: list[WaypointIn]


@router.post("/api/v2/nav/waypoints")
async def set_waypoints(wps: WaypointList):
    global _waypoints, _waypoint_reached, _current_waypoint_id
    _waypoints = [w.model_dump() for w in wps.waypoints]
    _waypoint_reached = False
    _current_waypoint_id = _waypoints[0]["waypoint_id"] if _waypoints else None
    _update_geofence_and_waypoint()
    return {"ok": True, "count": len(_waypoints)}


class ModeIn(BaseModel):
    mode: NavigationMode


@router.post("/api/v2/nav/mode")
async def set_mode(m: ModeIn):
    mgr = get_robot_state_manager()
    st = mgr.get_state()
    st.navigation_mode = m.mode
    st.touch()
    return {"ok": True, "mode": st.navigation_mode.value}


@router.get("/api/v2/nav/status")
async def get_nav_status():
    mgr = get_robot_state_manager()
    st = mgr.get_state()
    # Compute latest inside_geofence if applicable
    if _active_geofence and st.position.latitude is not None and st.position.longitude is not None:
        pts = [(p.latitude, p.longitude) for p in _active_geofence.boundary]
        st.inside_geofence = point_in_polygon(st.position.latitude, st.position.longitude, pts)
    # Response conforms to FR-034 expectations
    return {
        "mode": st.navigation_mode.value,
        "position": {
            "latitude": st.position.latitude,
            "longitude": st.position.longitude,
            "accuracy_m": st.position.accuracy_m,
        },
        "geofence": {
            "active": _active_geofence is not None,
            "inside": st.inside_geofence,
        },
        "waypoint": {
            "current_id": st.current_waypoint_id,
            "distance_m": st.distance_to_waypoint_m,
            "reached": _waypoint_reached,
            "queue_len": len(_waypoints),
        },
    }


def _zone_polygons_from_envelope(
    envelope: dict[str, Any],
    *,
    zone_type: str,
) -> list[list[tuple[float, float]]]:
    polygons: list[list[tuple[float, float]]] = []
    for zone in envelope.get("zones", []):
        if not isinstance(zone, dict) or str(zone.get("zone_type") or "") != zone_type:
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
        polygon: list[tuple[float, float]] = []
        for point in coordinates[0]:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            try:
                lng = float(point[0])
                lat = float(point[1])
            except (TypeError, ValueError):
                continue
            polygon.append((lat, lng))
        if len(polygon) >= 3:
            polygons.append(polygon)
    return polygons


@router.get("/api/v2/nav/coverage-plan")
async def get_coverage_plan(
    config_id: str = Query("default"),
    spacing_m: float = Query(0.6, gt=0.0, le=5.0),
):
    raw = await persistence.load_map_configuration(config_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Map configuration not found")

    try:
        envelope = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Stored map configuration is invalid") from exc

    if not isinstance(envelope, dict):
        raise HTTPException(status_code=500, detail="Stored map configuration is invalid")

    boundary_polygons = _zone_polygons_from_envelope(envelope, zone_type="boundary")
    if not boundary_polygons:
        raise HTTPException(status_code=404, detail="Boundary zone not configured")

    exclusion_polygons = _zone_polygons_from_envelope(envelope, zone_type="exclusion")
    path, row_count, length_m = plan_coverage(
        boundary_polygons[0],
        exclusion_polys=exclusion_polygons,
        spacing_m=spacing_m,
    )
    coordinates = [[lng, lat] for lat, lng in path]
    return {
        "plan": {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
            "properties": {
                "config_id": config_id,
                "spacing_m": spacing_m,
                "row_count": row_count,
                "length_m": round(length_m, 3),
            },
        },
    }


def _update_geofence_and_waypoint() -> None:
    """Recompute inside_geofence and waypoint arrival flag from current state."""
    global _waypoint_reached
    mgr = get_robot_state_manager()
    st = mgr.get_state()

    # Geofence effect: if outside, switch to EMERGENCY_STOP (placeholder behavior)
    if _active_geofence and st.position.latitude is not None and st.position.longitude is not None:
        pts = [(p.latitude, p.longitude) for p in _active_geofence.boundary]
        inside = point_in_polygon(st.position.latitude, st.position.longitude, pts)
        st.inside_geofence = inside
        if not inside:
            st.navigation_mode = NavigationMode.EMERGENCY_STOP

    # Waypoint arrival
    if _waypoints and st.position.latitude is not None and st.position.longitude is not None:
        wp = _waypoints[0]
        dist = haversine_m(
            st.position.latitude,
            st.position.longitude,
            wp["latitude"],
            wp["longitude"],
        )
        thr = float(wp.get("arrival_threshold_m") or 1.0)
        if dist <= thr:
            _waypoint_reached = True
        else:
            _waypoint_reached = False
        st.current_waypoint_id = wp.get("waypoint_id")
        st.distance_to_waypoint_m = dist
    else:
        st.current_waypoint_id = None
        st.distance_to_waypoint_m = None
