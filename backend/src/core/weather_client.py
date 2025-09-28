"""Weather client interfaces.

Provides optional integration points for external weather providers. In tests
and by default, we avoid network calls and return None so the service can fall
back to on-device sensors or simulated values.
"""
from __future__ import annotations
from typing import Optional, Dict, Any


class OpenWeatherClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def fetch_current(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
        """Placeholder for external API call. Returns None when not configured.

        This method intentionally avoids network usage in tests/CI. A real
        implementation can be added later guarded behind configuration and
        environment flags, ensuring ARM64 safety and offline behavior.
        """
        if not self.api_key:
            return None
        # Network-off default
        return None
