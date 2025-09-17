"""
Public, non-sensitive runtime configuration for the Web UI.
This allows the UI to obtain settings like Google Maps API keys at runtime
so keys can live in server-side .env and do not need to be baked at build time.

Endpoint is intentionally unauthenticated and should only expose safe values.
"""

from fastapi import APIRouter
import os
from ..config import get_settings

router = APIRouter()


@router.get("/config")
async def get_public_config():
    """Return public runtime configuration for the Web UI.

    Includes only non-sensitive values: map provider preferences and API key needed by
    the client libraries (Google Maps JavaScript requires the key in the client).
    """
    settings = get_settings()
    gmaps = settings.google_maps
    # Resolve API key with robust fallbacks: BaseSettings first, then environment variables.
    # Accepted environment variable fallbacks (order matters). This allows operators to
    # drop a key into /opt/lawnberry/.env using common names without rebuilding UI:
    # GOOGLE_MAPS_API_KEY, REACT_APP_GOOGLE_MAPS_API_KEY, VITE_GOOGLE_MAPS_API_KEY,
    # VITE_REACT_APP_GOOGLE_MAPS_API_KEY, MAPS_API_KEY (generic fallback).
    candidates = [
        (gmaps.api_key or "").strip(),
        os.getenv("GOOGLE_MAPS_API_KEY", "").strip(),
        os.getenv("REACT_APP_GOOGLE_MAPS_API_KEY", "").strip(),
        os.getenv("VITE_GOOGLE_MAPS_API_KEY", "").strip(),
        os.getenv("VITE_REACT_APP_GOOGLE_MAPS_API_KEY", "").strip(),
        os.getenv("MAPS_API_KEY", "").strip(),
    ]
    api_key = ""
    for k in candidates:
        if k and k != "your_google_maps_api_key_here":
            api_key = k
            break
    # Note: Google Maps JS API requires key in browser. This is considered public.
    return {
        "google_maps": {
            "available": bool(api_key and api_key != "your_google_maps_api_key_here"),
            "api_key": api_key,
            "usage_level": gmaps.usage_level,
        }
    }
