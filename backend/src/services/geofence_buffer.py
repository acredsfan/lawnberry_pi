"""Safe inward-buffer generation for confirmed mowing boundaries."""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime
from typing import Any

from pyproj import Transformer
from shapely.geometry import Polygon

from .boundary_paths import MOWING_BOUNDARY_SAFE, boundary_file
from .parcel_boundary import BoundaryValidationError, normalize_boundary_to_lat_lng

DEFAULT_SAFE_BOUNDARY_BUFFER_METERS = 0.75


def default_buffer_meters() -> float:
    raw = os.getenv("SAFE_BOUNDARY_BUFFER_METERS", "").strip()
    if not raw:
        return DEFAULT_SAFE_BOUNDARY_BUFFER_METERS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_SAFE_BOUNDARY_BUFFER_METERS
    return value if math.isfinite(value) and value >= 0 else DEFAULT_SAFE_BOUNDARY_BUFFER_METERS


def _projection_for(points: list[dict[str, float]]) -> tuple[Transformer, Transformer]:
    lat = sum(p["latitude"] for p in points) / len(points)
    lon = sum(p["longitude"] for p in points) / len(points)
    zone = int((lon + 180) // 6) + 1
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    return (
        Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True),
        Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True),
    )


def create_safe_boundary(
    coordinates: list[dict[str, float]],
    buffer_meters: float | None = None,
) -> list[dict[str, float]]:
    normalized = normalize_boundary_to_lat_lng(coordinates, order="latlng")
    buffer_value = default_buffer_meters() if buffer_meters is None else float(buffer_meters)
    if not math.isfinite(buffer_value) or buffer_value < 0:
        raise BoundaryValidationError("Buffer meters must be a non-negative finite value")
    forward, reverse = _projection_for(normalized)
    xy = [forward.transform(p["longitude"], p["latitude"]) for p in normalized]
    poly = Polygon(xy)
    if not poly.is_valid:
        poly = poly.buffer(0)
    if poly.is_empty or not poly.is_valid:
        raise BoundaryValidationError("Confirmed boundary polygon is invalid")
    safe = poly.buffer(-buffer_value) if buffer_value else poly
    if safe.is_empty or not safe.is_valid:
        raise BoundaryValidationError("Safe boundary buffer collapsed the polygon")
    if safe.geom_type == "MultiPolygon":
        safe = max(safe.geoms, key=lambda geom: geom.area)
    ring = list(safe.exterior.coords)[:-1]
    result = []
    for x, y in ring:
        lng, lat = reverse.transform(x, y)
        result.append({"latitude": float(lat), "longitude": float(lng)})
    return normalize_boundary_to_lat_lng(result, order="latlng")


def save_safe_boundary(
    coordinates: list[dict[str, float]],
    *,
    buffer_meters: float | None = None,
    source: str = "user_confirmed",
) -> dict[str, Any]:
    buffer_value = default_buffer_meters() if buffer_meters is None else float(buffer_meters)
    safe_coordinates = create_safe_boundary(coordinates, buffer_value)
    payload = {
        "source": source,
        "created_at": datetime.now(UTC).isoformat(),
        "buffer_meters": buffer_value,
        "coordinates": safe_coordinates,
    }
    path = boundary_file(MOWING_BOUNDARY_SAFE)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    return payload


def get_safe_boundary() -> dict[str, Any] | None:
    path = boundary_file(MOWING_BOUNDARY_SAFE)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
