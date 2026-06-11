"""Parcel boundary import and persistence helpers.

Imported parcel data is helper-only. It must never be used directly as an
autonomous mower geofence.
"""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .boundary_paths import PROPERTY_BOUNDARY_IMPORTED, boundary_file

LARGE_PARCEL_WARNING_M2 = 20_000.0


class BoundaryValidationError(ValueError):
    """Raised when boundary geometry cannot be normalized or validated."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _as_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise BoundaryValidationError("Coordinate values must be numeric") from exc
    if not math.isfinite(result):
        raise BoundaryValidationError("Coordinate values must be finite")
    return result


def _point_from_dict(point: dict[str, Any]) -> dict[str, float]:
    lat = point.get("lat", point.get("latitude"))
    lng = point.get("lng", point.get("lon", point.get("longitude")))
    return {"latitude": _as_float(lat), "longitude": _as_float(lng)}


def _point_from_pair(point: list[Any] | tuple[Any, ...], *, order: str = "lnglat") -> dict[str, float]:
    if len(point) < 2:
        raise BoundaryValidationError("Coordinate pairs must have at least two values")
    first = _as_float(point[0])
    second = _as_float(point[1])
    if order == "latlng":
        return {"latitude": first, "longitude": second}
    return {"latitude": second, "longitude": first}


def _strip_closing_point(points: list[dict[str, float]]) -> list[dict[str, float]]:
    if len(points) > 1 and points[0] == points[-1]:
        return points[:-1]
    return points


def normalize_boundary_to_lat_lng(raw_points: Any, *, order: str = "lnglat") -> list[dict[str, float]]:
    if not isinstance(raw_points, list):
        raise BoundaryValidationError("Boundary coordinates must be a list")
    points: list[dict[str, float]] = []
    for raw in raw_points:
        if isinstance(raw, dict):
            point = _point_from_dict(raw)
        elif isinstance(raw, (list, tuple)):
            point = _point_from_pair(raw, order=order)
        else:
            raise BoundaryValidationError("Unsupported coordinate point format")
        if not (-90.0 <= point["latitude"] <= 90.0):
            raise BoundaryValidationError("Latitude must be between -90 and 90")
        if not (-180.0 <= point["longitude"] <= 180.0):
            raise BoundaryValidationError("Longitude must be between -180 and 180")
        points.append(point)
    points = _strip_closing_point(points)
    unique = {(round(p["latitude"], 9), round(p["longitude"], 9)) for p in points}
    if len(unique) < 3:
        raise BoundaryValidationError("Boundary must contain at least 3 unique points")
    _validate_polygon(points)
    return points


def _validate_polygon(points: list[dict[str, float]]) -> None:
    try:
        from shapely.geometry import Polygon

        poly = Polygon([(p["longitude"], p["latitude"]) for p in points])
        if not poly.is_valid:
            fixed = poly.buffer(0)
            if fixed.is_empty or not fixed.is_valid:
                raise BoundaryValidationError("Boundary polygon is invalid")
        if poly.area <= 0:
            raise BoundaryValidationError("Boundary polygon area must be greater than zero")
    except BoundaryValidationError:
        raise
    except ImportError:
        return


def _first_polygon_from_geojson(payload: dict[str, Any]) -> list[Any]:
    geo_type = payload.get("type")
    if geo_type == "FeatureCollection":
        features = payload.get("features")
        if not isinstance(features, list):
            raise BoundaryValidationError("FeatureCollection must contain features")
        for feature in features:
            if isinstance(feature, dict):
                try:
                    return _first_polygon_from_geojson(feature)
                except BoundaryValidationError:
                    continue
    if geo_type == "Feature":
        geometry = payload.get("geometry")
        if isinstance(geometry, dict):
            return _first_polygon_from_geojson(geometry)
    if geo_type == "Polygon":
        coords = payload.get("coordinates")
        if isinstance(coords, list) and coords and isinstance(coords[0], list):
            return coords[0]
    if geo_type == "MultiPolygon":
        coords = payload.get("coordinates")
        if isinstance(coords, list) and coords and isinstance(coords[0], list) and coords[0]:
            return coords[0][0]
    raise BoundaryValidationError("No polygon geometry found")


def load_geojson_boundary(data: str | bytes | dict[str, Any]) -> list[dict[str, float]]:
    payload = json.loads(data.decode() if isinstance(data, bytes) else data) if isinstance(data, str | bytes) else data
    if not isinstance(payload, dict):
        raise BoundaryValidationError("GeoJSON payload must be an object")
    return normalize_boundary_to_lat_lng(_first_polygon_from_geojson(payload), order="lnglat")


def load_raw_coordinate_boundary(data: str | bytes | list[Any] | dict[str, Any]) -> list[dict[str, float]]:
    payload = json.loads(data.decode() if isinstance(data, bytes) else data) if isinstance(data, str | bytes) else data
    if isinstance(payload, dict):
        if "coordinates" in payload:
            raw = payload["coordinates"]
        elif "points" in payload:
            raw = payload["points"]
        else:
            return load_geojson_boundary(payload)
    else:
        raw = payload
    if isinstance(raw, list) and raw and isinstance(raw[0], list) and raw and raw[0] and isinstance(raw[0][0], (list, tuple)):
        raw = raw[0]
    order = "latlng" if raw and isinstance(raw[0], dict) else "lnglat"
    return normalize_boundary_to_lat_lng(raw, order=order)


def load_kml_boundary(data: str | bytes) -> list[dict[str, float]]:
    text = data.decode() if isinstance(data, bytes) else data
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise BoundaryValidationError("Invalid KML XML") from exc
    coord_el = None
    for element in root.iter():
        if element.tag.endswith("coordinates") and element.text:
            coord_el = element
            break
    if coord_el is None or not coord_el.text:
        raise BoundaryValidationError("No KML coordinates found")
    pairs: list[list[float]] = []
    for token in re.split(r"\s+", coord_el.text.strip()):
        if not token:
            continue
        parts = token.split(",")
        if len(parts) < 2:
            continue
        pairs.append([_as_float(parts[0]), _as_float(parts[1])])
    return normalize_boundary_to_lat_lng(pairs, order="lnglat")


def parse_boundary_payload(data: str | bytes | dict[str, Any] | list[Any], *, filename: str = "") -> list[dict[str, float]]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".kml":
        return load_kml_boundary(data if isinstance(data, str | bytes) else json.dumps(data))
    if suffix in {".geojson", ".json"}:
        try:
            return load_geojson_boundary(data)  # type: ignore[arg-type]
        except BoundaryValidationError:
            return load_raw_coordinate_boundary(data)  # type: ignore[arg-type]
    if isinstance(data, str | bytes):
        text = data.decode() if isinstance(data, bytes) else data
        stripped = text.lstrip()
        if stripped.startswith("<"):
            return load_kml_boundary(text)
        try:
            return load_geojson_boundary(text)
        except BoundaryValidationError:
            return load_raw_coordinate_boundary(text)
    return load_raw_coordinate_boundary(data)


def _area_m2(points: list[dict[str, float]]) -> float:
    try:
        from pyproj import Transformer
        from shapely.geometry import Polygon

        lat = sum(p["latitude"] for p in points) / len(points)
        lon = sum(p["longitude"] for p in points) / len(points)
        zone = int((lon + 180) // 6) + 1
        epsg = 32600 + zone if lat >= 0 else 32700 + zone
        transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
        xy = [transformer.transform(p["longitude"], p["latitude"]) for p in points]
        return float(Polygon(xy).area)
    except Exception:
        return 0.0


def save_imported_property_boundary(
    coordinates: list[dict[str, float]],
    *,
    source: str = "manual_upload",
    source_detail: str = "Manual import",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_boundary_to_lat_lng(coordinates, order="latlng")
    area_m2 = _area_m2(normalized)
    warnings: list[str] = []
    if area_m2 > LARGE_PARCEL_WARNING_M2:
        warnings.append("This imported boundary may represent the full legal parcel, not the actual mowable area.")
    payload = {
        "source": source,
        "source_detail": source_detail,
        "created_at": _now(),
        "confidence": "helper_only",
        "helper_only": True,
        "coordinates": normalized,
        "area_m2": area_m2,
        "warnings": warnings,
        "metadata": metadata or {},
    }
    path = boundary_file(PROPERTY_BOUNDARY_IMPORTED)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    return payload


def get_imported_property_boundary() -> dict[str, Any] | None:
    path = boundary_file(PROPERTY_BOUNDARY_IMPORTED)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def clear_imported_property_boundary() -> None:
    path = boundary_file(PROPERTY_BOUNDARY_IMPORTED)
    if path.exists():
        path.unlink()
