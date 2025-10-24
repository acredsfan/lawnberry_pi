"""Lightweight timezonefinder stub for unit tests in environments without the dependency."""

from __future__ import annotations

from typing import Optional


class TimezoneFinder:
    def __init__(self, in_memory: bool = True):  # pragma: no cover - trivial
        self.in_memory = in_memory

    def timezone_at(self, lat: float | int | str | None = None, lng: float | int | str | None = None) -> Optional[str]:
        return self._lookup(lat, lng)

    def closest_timezone_at(self, lat: float | int | str | None = None, lng: float | int | str | None = None) -> Optional[str]:
        return self._lookup(lat, lng)

    @staticmethod
    def _lookup(lat: float | int | str | None, lng: float | int | str | None) -> Optional[str]:
        try:
            lat_f = float(lat) if lat is not None else None
            lng_f = float(lng) if lng is not None else None
        except (TypeError, ValueError):
            return None
        if lat_f is None or lng_f is None:
            return None
        # Rough bounding box for US Pacific time used in tests
        if 32.0 <= lat_f <= 42.5 and -125.0 <= lng_f <= -114.0:
            return "America/Los_Angeles"
        return None
