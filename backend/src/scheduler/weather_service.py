from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .weather_api import WeatherAPI
from .weather_sensor_fallback import EnvSnapshot, SensorFallbackRules


@dataclass
class WeatherSuitability:
    suitable: bool
    source: str
    details: dict[str, Any]


class WeatherService:
    """Combines API (with 6h cache) and local sensors for a suitability verdict.

    Offline-first: when API data is unavailable or stale, uses local sensors.
    """

    def __init__(
        self,
        api: WeatherAPI | None = None,
        rules: SensorFallbackRules | None = None,
    ):
        self.api = api or WeatherAPI()
        self.rules = rules or SensorFallbackRules()

    def evaluate(
        self,
        latitude: float,
        longitude: float,
        sensor_env: EnvSnapshot,
        provider: Callable[[float, float], dict[str, Any] | None] | None = None,
    ) -> WeatherSuitability:
        forecast = self.api.get_forecast(latitude, longitude, provider)

        if forecast is not None:
            # Minimal schema expectation: allow caller-defined thresholds later.
            # For now, treat any forecast as "ok" unless an explicit flag exists.
            unsuitable = False
            if isinstance(forecast, dict):
                # If the forecast explicitly signals unsuitable weather
                unsuitable = bool(forecast.get("unsuitable", False))
            return WeatherSuitability(
                suitable=not unsuitable, source="api_or_cache", details={"forecast": forecast}
            )

        # No forecast available — use sensor fallback
        suitable = self.rules.is_suitable(sensor_env)
        return WeatherSuitability(
            suitable=suitable,
            source="sensors",
            details={
                "humidity_percent": sensor_env.humidity_percent,
                "pressure_hpa": sensor_env.pressure_hpa,
            },
        )

    def make_predicate(
        self,
        latitude: float,
        longitude: float,
        sensor_env_supplier: Callable[[], EnvSnapshot],
        provider: Callable[[float, float], dict[str, Any] | None] | None = None,
    ) -> Callable[[], bool]:
        """Return a zero-arg predicate suitable for JobScheduler.start()."""

        def _pred() -> bool:
            env = sensor_env_supplier()
            verdict = self.evaluate(latitude, longitude, env, provider)
            return verdict.suitable

        return _pred
