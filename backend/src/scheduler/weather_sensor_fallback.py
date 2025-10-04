from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class EnvSnapshot:
    temperature_c: Optional[float]
    humidity_percent: Optional[float]
    pressure_hpa: Optional[float]


@dataclass
class SensorFallbackRules:
    max_humidity_percent: float = 85.0
    min_pressure_hpa: float = 1000.0

    def is_suitable(self, env: EnvSnapshot) -> bool:
        # If we lack data, fail-open to avoid blocking jobs unnecessarily
        if env.humidity_percent is not None and env.humidity_percent > self.max_humidity_percent:
            return False
        if env.pressure_hpa is not None and env.pressure_hpa < self.min_pressure_hpa:
            return False
        return True
