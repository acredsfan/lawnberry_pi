from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ..core.weather_client import OpenWeatherClient


class WeatherService:
    def __init__(self, ow_client: OpenWeatherClient | None = None):
        self.ow_client = ow_client or OpenWeatherClient()
        self._sensor_manager_getter: Callable[[], Any] | None = None

    def register_sensor_manager(self, getter: Callable[[], Any]) -> None:
        """Attach a callable that returns the active SensorManager.

        The callable is evaluated lazily so weather_service can be created
        before the WebSocket hub initializes hardware services.
        """
        self._sensor_manager_getter = getter

    async def _get_environmental_snapshot_async(self) -> dict[str, Any] | None:
        if self._sensor_manager_getter is None:
            return None
        try:
            manager = self._sensor_manager_getter()
        except Exception:
            return None
        if not manager:
            return None
        env_iface = getattr(manager, "environmental", None)
        if env_iface is None:
            return None

        reading = getattr(env_iface, "last_reading", None)
        if reading is None:
            try:
                reading = await env_iface.read_environmental()
            except Exception:
                reading = None

        if reading is None:
            return None
        temperature = getattr(reading, "temperature", None)
        humidity = getattr(reading, "humidity", None)
        pressure = getattr(reading, "pressure", None)
        altitude = getattr(reading, "altitude", None)
        if temperature is None and humidity is None and pressure is None:
            return None
        return {
            "source": "bme280",
            "temperature_c": temperature,
            "humidity_percent": humidity,
            "pressure_hpa": pressure,
            "altitude_m": altitude,
        }

    async def get_current_async(
        self, latitude: float | None = None, longitude: float | None = None
    ) -> dict[str, Any]:
        # Try external client (disabled by default)
        ext = None
        if latitude is not None and longitude is not None:
            try:
                ext = await asyncio.to_thread(self.ow_client.fetch_current, latitude, longitude)
            except Exception:
                ext = None

        now = datetime.now(UTC).isoformat()
        sensor_snapshot = await self._get_environmental_snapshot_async()
        if sensor_snapshot:
            sensor_snapshot["timestamp"] = now
            return sensor_snapshot
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
            "source": "unavailable",
            "temperature_c": None,
            "humidity_percent": None,
            "pressure_hpa": None,
        }

    def get_current(
        self, latitude: float | None = None, longitude: float | None = None
    ) -> dict[str, Any]:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            raise RuntimeError("Call get_current_async() when inside an event loop")
        return asyncio.run(self.get_current_async(latitude=latitude, longitude=longitude))

    def get_planning_advice(self, current: dict[str, Any]) -> dict[str, Any]:
        # Simple rule: if we lack data, return insufficient-data; else proceed
        reasons = []
        if current.get("temperature_c") is None or current.get("humidity_percent") is None:
            return {"advice": "insufficient-data", "reasons": ["no-sensor-data"]}
        # Placeholder: could add rain/wind thresholds here
        return {"advice": "proceed", "reasons": reasons}


weather_service = WeatherService()
