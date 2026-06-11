"""ArcGIS REST parcel source adapter."""

from __future__ import annotations

import os
from typing import Any

import httpx

from .base import ParcelSource


class ArcGISParcelSource(ParcelSource):
    def __init__(
        self,
        query_url: str | None = None,
        *,
        out_fields: str | None = None,
        geometry_type: str | None = None,
        spatial_rel: str | None = None,
    ) -> None:
        self.query_url = query_url or os.getenv("PARCEL_ARCGIS_QUERY_URL", "").strip()
        self.out_fields = out_fields or os.getenv("PARCEL_ARCGIS_OUT_FIELDS", "*")
        self.geometry_type = geometry_type or os.getenv("PARCEL_ARCGIS_GEOMETRY_TYPE", "esriGeometryPoint")
        self.spatial_rel = spatial_rel or os.getenv("PARCEL_ARCGIS_SPATIAL_REL", "esriSpatialRelIntersects")

    async def find_parcel_by_point(self, lat: float, lng: float) -> dict[str, Any]:
        if not self.query_url:
            raise RuntimeError("Parcel ArcGIS source is not configured")
        params = {
            "f": "json",
            "geometry": f"{lng},{lat}",
            "geometryType": self.geometry_type,
            "inSR": "4326",
            "outSR": "4326",
            "spatialRel": self.spatial_rel,
            "outFields": self.out_fields,
            "returnGeometry": "true",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(self.query_url, params=params)
            response.raise_for_status()
            payload = response.json()
        features = payload.get("features")
        if not isinstance(features, list) or not features:
            raise RuntimeError("No parcel found for that point")
        feature = features[0]
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(geometry, dict):
            raise RuntimeError("Parcel response did not include polygon geometry")
        rings = geometry.get("rings")
        if not isinstance(rings, list) or not rings:
            raise RuntimeError("Parcel response did not include polygon rings")
        return {
            "source": "county_arcgis",
            "source_detail": self.query_url,
            "coordinates": rings[0],
            "attributes": feature.get("attributes", {}),
        }
