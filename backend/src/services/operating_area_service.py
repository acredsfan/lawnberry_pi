"""Authoritative operating-area geometry for autonomous mower motion.

This module keeps geofence checks in a local projected metre frame. Production
motion must never buffer latitude/longitude degrees directly.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import nearest_points, unary_union

from ..models import Position
from ..nav.geoutils import latlon_to_enu
from .boundary_paths import (
    MOWING_BOUNDARY_CONFIRMED,
    MOWING_BOUNDARY_SAFE,
    boundary_file,
)
from .geofence_buffer import boundary_revision_hash

LatLng = tuple[float, float]


class OperatingAreaError(RuntimeError):
    """Raised when the operating area cannot authorize autonomy."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(detail)
        self.reason_code = reason_code
        self.detail = detail


@dataclass(frozen=True)
class OperatingAreaSnapshot:
    outer_boundary: list[Position]
    safe_boundary: list[Position]
    exclusions: list[list[Position]]
    source: str
    created_at: datetime
    buffer_meters: float
    revision_hash: str | None
    validity_state: str
    selected_mow_zone_id: str | None
    _origin_lat: float
    _origin_lon: float
    _forward: Any
    _reverse: Any
    _safe_outer_xy: Polygon
    _exclusions_xy: tuple[Polygon, ...]
    _free_space_xy: Any

    @property
    def valid(self) -> bool:
        return self.validity_state == "valid"

    def contains_center(self, position: Position) -> bool:
        return bool(self._free_space_xy.covers(self._point_xy(position)))

    def contains_footprint(self, position: Position, uncertainty_m: float = 0.0) -> bool:
        radius = max(0.0, float(uncertainty_m))
        return bool(self._free_space_xy.covers(self._point_xy(position).buffer(radius)))

    def distance_to_boundary(self, position: Position) -> float:
        point = self._point_xy(position)
        distance = float(point.distance(self._free_space_xy.boundary))
        return distance if self._free_space_xy.covers(point) else -distance

    def safe_approach_position(
        self,
        reference: Position,
        clearance_m: float,
    ) -> Position:
        """Project a reference point to the nearest center-safe stand-off target."""
        if not self.valid:
            raise OperatingAreaError("SAFE_BOUNDARY_REQUIRED", self.validity_state)
        clearance = max(0.0, float(clearance_m))
        center_space = self._free_space_xy.buffer(-clearance)
        if center_space.is_empty:
            raise OperatingAreaError(
                "SAFE_BOUNDARY_COLLAPSED",
                "Operating area is too narrow for the requested verification stand-off",
            )
        target_xy, _ = nearest_points(center_space, self._point_xy(reference))
        lon, lat = self._reverse.transform(float(target_xy.x), float(target_xy.y))
        return Position(
            latitude=float(lat),
            longitude=float(lon),
            altitude=reference.altitude,
        )

    def segment_is_safe(
        self,
        start: Position,
        end: Position,
        margin_m: float = 0.0,
    ) -> bool:
        line = LineString([self._xy(start), self._xy(end)])
        envelope = line.buffer(max(0.0, float(margin_m)), cap_style=2, join_style=2)
        return bool(self._free_space_xy.covers(envelope))

    def path_is_safe(self, points: list[Position], margin_m: float = 0.0) -> bool:
        if not points:
            return False
        if any(not self.contains_footprint(point, margin_m) for point in points):
            return False
        return all(
            self.segment_is_safe(points[index], points[index + 1], margin_m)
            for index in range(len(points) - 1)
        )

    def swept_motion_is_safe(
        self,
        pose: Position,
        heading_deg: float | None,
        left_speed: float,
        right_speed: float,
        *,
        footprint_radius_m: float,
        uncertainty_m: float,
        fixed_allowance_m: float,
        horizon_s: float,
        command_latency_s: float,
        wheelbase_m: float,
        braking_decel_mps2: float,
    ) -> bool:
        radius = max(0.0, footprint_radius_m + uncertainty_m + fixed_allowance_m)
        point = self._point_xy(pose)
        if not self._free_space_xy.covers(point.buffer(radius)):
            return False

        linear = (float(left_speed) + float(right_speed)) / 2.0
        if abs(linear) < 1e-6:
            return bool(self._free_space_xy.covers(point.buffer(radius)))

        if heading_deg is None:
            return False
        stopping_m = (abs(linear) ** 2) / (2.0 * max(braking_decel_mps2, 1e-6))
        distance_m = abs(linear) * max(0.0, horizon_s + command_latency_s) + stopping_m
        heading_rad = math.radians(float(heading_deg))
        north_m = math.cos(heading_rad) * distance_m * (1 if linear >= 0 else -1)
        east_m = math.sin(heading_rad) * distance_m * (1 if linear >= 0 else -1)
        x, y = self._xy(pose)
        end_xy = (x + east_m, y + north_m)
        envelope = LineString([(x, y), end_xy]).buffer(radius, cap_style=1, join_style=1)
        return bool(self._free_space_xy.covers(envelope))

    def validate_ready_for_autonomy(
        self,
        *,
        position: Position | None,
        last_gps_fix: datetime | None,
        dead_reckoning_active: bool,
        max_fix_age_s: float,
        max_accuracy_m: float,
        footprint_radius_m: float,
        fixed_allowance_m: float,
        bootstrap_clearance_m: float | None = None,
    ) -> None:
        if not self.valid:
            raise OperatingAreaError("SAFE_BOUNDARY_REQUIRED", self.validity_state)
        if position is None:
            raise OperatingAreaError("LOCALIZATION_UNAVAILABLE", "Current position is unavailable")
        if dead_reckoning_active:
            raise OperatingAreaError(
                "LOCALIZATION_DEAD_RECKONING",
                "Dead reckoning cannot authorize boundary containment",
            )
        if last_gps_fix is None:
            raise OperatingAreaError("LOCALIZATION_STALE", "GPS fix timestamp is unavailable")
        fix = last_gps_fix if last_gps_fix.tzinfo else last_gps_fix.replace(tzinfo=UTC)
        if (datetime.now(UTC) - fix).total_seconds() > float(max_fix_age_s):
            raise OperatingAreaError("LOCALIZATION_STALE", "GPS fix is too old")
        accuracy = position.accuracy
        if accuracy is None or float(accuracy) > float(max_accuracy_m):
            raise OperatingAreaError(
                "LOCALIZATION_NOT_RTK_GRADE",
                "GPS accuracy is insufficient for autonomous motion",
            )
        uncertainty = float(accuracy) + float(footprint_radius_m) + float(fixed_allowance_m)
        if not self.contains_footprint(position, uncertainty):
            raise OperatingAreaError("CURRENT_FOOTPRINT_OUTSIDE_FREE_SPACE", "Mower footprint is outside free space")
        if bootstrap_clearance_m is not None and self.distance_to_boundary(position) < bootstrap_clearance_m:
            raise OperatingAreaError(
                "INSUFFICIENT_BOOTSTRAP_CLEARANCE",
                "Reposition mower farther inside the safe operating area",
            )

    def _xy(self, position: Position) -> tuple[float, float]:
        return self._forward.transform(float(position.longitude), float(position.latitude))

    def _point_xy(self, position: Position) -> Point:
        return Point(self._xy(position))


def load_operating_area_snapshot(
    *,
    map_repository: Any | None = None,
    selected_mow_zone_id: str | None = None,
    allow_zone_fallback: bool = False,
) -> OperatingAreaSnapshot:
    confirmed_payload = _read_json(MOWING_BOUNDARY_CONFIRMED)
    safe_payload = _read_json(MOWING_BOUNDARY_SAFE)
    zones = _safe_list_zones(map_repository)
    exclusions = [_positions_from_polygon(zone.get("polygon", [])) for zone in zones if _zone_kind(zone) == "exclusion"]
    exclusions = [poly for poly in exclusions if len(poly) >= 3]

    if safe_payload is not None:
        safe_points = _positions_from_polygon(safe_payload.get("coordinates", []))
        validity = _validate_safe_payload(safe_payload, safe_points, confirmed_payload)
        return _build_snapshot(
            outer_boundary=safe_points,
            safe_boundary=safe_points,
            exclusions=exclusions,
            source=str(safe_payload.get("source") or "generated_safe_boundary"),
            created_at=_parse_dt(safe_payload.get("created_at")),
            buffer_meters=float(safe_payload.get("buffer_meters", 0.0) or 0.0),
            revision_hash=safe_payload.get("confirmed_boundary_hash"),
            validity_state=validity,
            selected_mow_zone_id=selected_mow_zone_id,
        )

    if allow_zone_fallback:
        boundary_zones = [zone for zone in zones if _zone_kind(zone) in {"boundary", "mow"}]
        if selected_mow_zone_id is not None:
            selected = [zone for zone in boundary_zones if str(zone.get("id")) == selected_mow_zone_id]
            boundary_zones = selected or boundary_zones
        if boundary_zones:
            boundary_zone = sorted(
                boundary_zones,
                key=lambda zone: (-int(zone.get("priority", 0) or 0), str(zone.get("id", ""))),
            )[0]
            points = _positions_from_polygon(boundary_zone.get("polygon", []))
            return _build_snapshot(
                outer_boundary=points,
                safe_boundary=points,
                exclusions=exclusions,
                source="simulation_zone_fallback",
                created_at=datetime.now(UTC),
                buffer_meters=0.0,
                revision_hash=None,
                validity_state="valid" if len(points) >= 3 else "SAFE_BOUNDARY_REQUIRED",
                selected_mow_zone_id=str(boundary_zone.get("id")) if boundary_zone.get("id") else None,
            )

    return _invalid_snapshot("SAFE_BOUNDARY_REQUIRED", exclusions=exclusions)


def _build_snapshot(
    *,
    outer_boundary: list[Position],
    safe_boundary: list[Position],
    exclusions: list[list[Position]],
    source: str,
    created_at: datetime,
    buffer_meters: float,
    revision_hash: str | None,
    validity_state: str,
    selected_mow_zone_id: str | None,
) -> OperatingAreaSnapshot:
    if len(safe_boundary) < 3:
        return _invalid_snapshot("SAFE_BOUNDARY_REQUIRED", exclusions=exclusions)
    origin_lat = sum(point.latitude for point in safe_boundary) / len(safe_boundary)
    origin_lon = sum(point.longitude for point in safe_boundary) / len(safe_boundary)
    forward, reverse = _projection_for(origin_lat, origin_lon)
    outer_xy = _polygon_xy(safe_boundary, forward)
    exclusion_xy = tuple(
        poly for poly in (_polygon_xy(points, forward) for points in exclusions) if not poly.is_empty
    )
    if outer_xy.is_empty or not outer_xy.is_valid:
        validity_state = "SAFE_BOUNDARY_INVALID"
    free_space = outer_xy.difference(unary_union(exclusion_xy)) if exclusion_xy else outer_xy
    if free_space.is_empty:
        validity_state = "SAFE_BOUNDARY_COLLAPSED"
    return OperatingAreaSnapshot(
        outer_boundary=outer_boundary,
        safe_boundary=safe_boundary,
        exclusions=exclusions,
        source=source,
        created_at=created_at,
        buffer_meters=buffer_meters,
        revision_hash=revision_hash,
        validity_state=validity_state,
        selected_mow_zone_id=selected_mow_zone_id,
        _origin_lat=origin_lat,
        _origin_lon=origin_lon,
        _forward=forward,
        _reverse=reverse,
        _safe_outer_xy=outer_xy,
        _exclusions_xy=exclusion_xy,
        _free_space_xy=free_space,
    )


def _invalid_snapshot(reason: str, *, exclusions: list[list[Position]] | None = None) -> OperatingAreaSnapshot:
    points = [
        Position(latitude=0.0, longitude=0.0),
        Position(latitude=0.0, longitude=0.00001),
        Position(latitude=0.00001, longitude=0.0),
    ]
    forward, reverse = _projection_for(0.0, 0.0)
    poly = _polygon_xy(points, forward)
    return OperatingAreaSnapshot(
        outer_boundary=[],
        safe_boundary=[],
        exclusions=exclusions or [],
        source="unavailable",
        created_at=datetime.now(UTC),
        buffer_meters=0.0,
        revision_hash=None,
        validity_state=reason,
        selected_mow_zone_id=None,
        _origin_lat=0.0,
        _origin_lon=0.0,
        _forward=forward,
        _reverse=reverse,
        _safe_outer_xy=poly,
        _exclusions_xy=(),
        _free_space_xy=poly.difference(poly),
    )


def _validate_safe_payload(
    safe_payload: dict[str, Any],
    safe_points: list[Position],
    confirmed_payload: dict[str, Any] | None,
) -> str:
    if len(safe_points) < 3:
        return "SAFE_BOUNDARY_REQUIRED"
    if confirmed_payload is None:
        return "valid"
    confirmed_hash = boundary_revision_hash(confirmed_payload.get("coordinates", []))
    safe_hash = safe_payload.get("confirmed_boundary_hash")
    if not safe_hash:
        return "SAFE_BOUNDARY_STALE"
    if safe_hash != confirmed_hash:
        return "SAFE_BOUNDARY_STALE"
    return "valid"


class _LocalForward:
    def __init__(self, origin_lat: float, origin_lon: float) -> None:
        self.origin_lat = origin_lat
        self.origin_lon = origin_lon

    def transform(self, lon: float, lat: float) -> tuple[float, float]:
        return latlon_to_enu(lat, lon, self.origin_lat, self.origin_lon)


class _LocalReverse:
    def __init__(self, origin_lat: float, origin_lon: float) -> None:
        self.origin_lat = origin_lat
        self.origin_lon = origin_lon

    def transform(self, x: float, y: float) -> tuple[float, float]:
        from ..nav.geoutils import enu_to_latlon

        lat, lon = enu_to_latlon(x, y, self.origin_lat, self.origin_lon)
        return lon, lat


def _projection_for(lat: float, lon: float) -> tuple[Any, Any]:
    return _LocalForward(lat, lon), _LocalReverse(lat, lon)


def _polygon_xy(points: list[Position], forward: Any) -> Polygon:
    xy = [forward.transform(point.longitude, point.latitude) for point in points]
    poly = Polygon(xy)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly


def _read_json(filename: str) -> dict[str, Any] | None:
    path = boundary_file(filename)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_list_zones(map_repository: Any | None) -> list[dict[str, Any]]:
    if map_repository is None:
        return []
    try:
        return list(map_repository.list_zones())
    except Exception:
        return []


def _zone_kind(zone: dict[str, Any]) -> str:
    kind = str(zone.get("zone_kind") or "").strip().lower()
    if kind:
        return "exclusion" if kind == "exclusion_zone" else kind
    return "exclusion" if bool(zone.get("exclusion_zone", False)) else "boundary"


def _positions_from_polygon(points: Iterable[Any]) -> list[Position]:
    result: list[Position] = []
    for point in points or []:
        if isinstance(point, Position):
            result.append(point)
        elif isinstance(point, dict):
            lat = point.get("latitude", point.get("lat"))
            lon = point.get("longitude", point.get("lon", point.get("lng")))
            if lat is not None and lon is not None:
                result.append(Position(latitude=float(lat), longitude=float(lon)))
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            result.append(Position(latitude=float(point[0]), longitude=float(point[1])))
    return result


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return datetime.now(UTC)


__all__ = [
    "OperatingAreaError",
    "OperatingAreaSnapshot",
    "load_operating_area_snapshot",
]
