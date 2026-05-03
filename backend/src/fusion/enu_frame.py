"""Local ENU (East-North-Up) frame anchored at a WGS84 origin.

The flat-earth tangent-plane approximation is used. Error vs true
haversine at 500 m is < 1 mm — well within RTK accuracy.

Coordinate convention
---------------------
  x_m  = east  (+east, -west)
  y_m  = north (+north, -south)
  heading_deg: compass, 0 = north, 90 = east, clockwise-positive
"""
from __future__ import annotations

import math


_METERS_PER_DEG_LAT: float = 111_320.0  # matches geoutils.py constant


class ENUFrame:
    """Convert between WGS84 lat/lon and local ENU metres.

    Usage
    -----
    frame = ENUFrame()
    frame.set_origin(lat, lon)
    x_m, y_m = frame.to_local(lat2, lon2)
    lat2, lon2 = frame.to_wgs84(x_m, y_m)
    """

    def __init__(self) -> None:
        self._origin_lat: float | None = None
        self._origin_lon: float | None = None
        self._meters_per_deg_lon: float = 0.0

    @property
    def is_anchored(self) -> bool:
        return self._origin_lat is not None

    def set_origin(self, lat: float, lon: float) -> None:
        """Anchor the frame at (lat, lon). Must be called before to_local."""
        self._origin_lat = lat
        self._origin_lon = lon
        self._meters_per_deg_lon = _METERS_PER_DEG_LAT * math.cos(math.radians(lat))

    def to_local(self, lat: float, lon: float) -> tuple[float, float]:
        """Convert WGS84 (lat, lon) to local ENU (x_m east, y_m north).

        Raises RuntimeError if the frame is not anchored.
        """
        if self._origin_lat is None:
            raise RuntimeError("ENUFrame has no origin; call set_origin first")
        y_m = (lat - self._origin_lat) * _METERS_PER_DEG_LAT
        x_m = (lon - self._origin_lon) * self._meters_per_deg_lon
        return x_m, y_m

    def to_wgs84(self, x_m: float, y_m: float) -> tuple[float, float]:
        """Convert local ENU (x_m east, y_m north) back to WGS84 (lat, lon).

        Raises RuntimeError if the frame is not anchored.
        """
        if self._origin_lat is None:
            raise RuntimeError("ENUFrame has no origin; call set_origin first")
        lat = self._origin_lat + y_m / _METERS_PER_DEG_LAT
        if abs(self._meters_per_deg_lon) > 1.0:
            lon = self._origin_lon + x_m / self._meters_per_deg_lon
        else:
            lon = self._origin_lon
        return lat, lon

    @property
    def origin_lat(self) -> float | None:
        return self._origin_lat

    @property
    def origin_lon(self) -> float | None:
        return self._origin_lon


__all__ = ["ENUFrame"]
