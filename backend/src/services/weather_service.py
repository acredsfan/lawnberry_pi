from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from ..core.weather_client import OpenWeatherClient


class WeatherService:
    def __init__(self, ow_client: Optional[OpenWeatherClient] = None):
        self.ow_client = ow_client or OpenWeatherClient()

    def get_current(self, latitude: Optional[float] = None, longitude: Optional[float] = None) -> Dict[str, Any]:
        # Try external client (disabled by default)
        ext = None
        if latitude is not None and longitude is not None:
            try:
                ext = self.ow_client.fetch_current(latitude, longitude)
            except Exception:
                ext = None

        # Fallback minimal data; in future can read BME280 when wired
        now = datetime.now(timezone.utc).isoformat()
        if ext:
            return {
                "timestamp": now,
                "source": "openweather",
                "temperature_c": ext.get("temperature_c"),
                "humidity_percent": ext.get("humidity_percent"),
                "pressure_hpa": ext.get("pressure_hpa"),
            }
        return {
            "timestamp": now,
            "source": "simulated",
            "temperature_c": None,
            "humidity_percent": None,
            "pressure_hpa": None,
        }

    def get_planning_advice(self, current: Dict[str, Any]) -> Dict[str, Any]:
        # Simple rule: if we lack data, return insufficient-data; else proceed
        reasons = []
        if current.get("temperature_c") is None or current.get("humidity_percent") is None:
            return {"advice": "insufficient-data", "reasons": ["no-sensor-data"]}
        # Placeholder: could add rain/wind thresholds here
        return {"advice": "proceed", "reasons": reasons}


weather_service = WeatherService()
