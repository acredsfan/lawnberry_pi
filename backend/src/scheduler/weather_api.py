from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_CACHE_FILE = Path("./data/weather_cache.json")
SIX_HOURS_S = 6 * 60 * 60


@dataclass
class WeatherCache:
    path: Path = DEFAULT_CACHE_FILE
    ttl_s: int = SIX_HOURS_S

    def read(self) -> Optional[Dict[str, Any]]:
        try:
            if not self.path.exists():
                return None
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            ts = data.get("timestamp_s")
            if not isinstance(ts, (int, float)):
                return None
            if time.time() - float(ts) > self.ttl_s:
                return None
            return data.get("forecast")
        except Exception:
            return None

    def write(self, forecast: Dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"timestamp_s": time.time(), "forecast": forecast}
            tmp = self.path.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp, self.path)
        except Exception:
            # Cache write failures should never crash callers
            pass


class WeatherAPI:
    """Offline-first weather accessor with 6h file cache.

    Network calls are intentionally avoided by default; callers can inject a
    provider function returning a forecast dict or None. When provider returns
    None, this falls back to cached data if available and fresh.
    """

    def __init__(self, cache: Optional[WeatherCache] = None):
        self.cache = cache or WeatherCache()

    def get_forecast(
        self,
        latitude: float,
        longitude: float,
        provider: Optional[callable] = None,
    ) -> Optional[Dict[str, Any]]:
        # Try provider first (if any)
        forecast: Optional[Dict[str, Any]] = None
        if provider is not None:
            try:
                forecast = provider(latitude, longitude)
            except Exception:
                forecast = None

        # If provider unavailable, read from cache
        if forecast is None:
            forecast = self.cache.read()
            return forecast

        # If provider supplied data, refresh cache and return
        self.cache.write(forecast)
        return forecast
