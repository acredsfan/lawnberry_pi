"""Base interface for public parcel source adapters."""

from __future__ import annotations

from typing import Any


class ParcelSource:
    async def find_parcel_by_point(self, lat: float, lng: float) -> dict[str, Any]:
        raise NotImplementedError
