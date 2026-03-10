import json
import os
import logging
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...core.globals import _security_settings

logger = logging.getLogger(__name__)
router = APIRouter()

SETTINGS_FILE = os.path.join(os.getcwd(), "data", "settings.json")

class SettingsResponse(BaseModel):
    theme: str = "dark"
    units: str = "metric"
    language: str = "en"
    notifications_enabled: bool = True
    map_provider: str = "openstreetmap"

class SecuritySettingsResponse(BaseModel):
    password_required: bool = False
    totp_enabled: bool = False
    cloudflare_access_enabled: bool = False
    security_level: str = "BASIC"

def _load_settings() -> SettingsResponse:
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
                return SettingsResponse(**data)
    except Exception as e:
        logger.warning(f"Failed to load settings: {e}")
    return SettingsResponse()

def _save_settings(settings: SettingsResponse):
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, "w") as f:
            f.write(settings.model_dump_json(indent=2))
    except Exception as e:
        logger.error(f"Failed to save settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to save settings")

@router.get("/settings")
async def get_settings():
    """Get user settings."""
    return _load_settings()

@router.put("/settings")
async def update_settings(settings: SettingsResponse):
    """Update user settings."""
    _save_settings(settings)
    return settings

@router.get("/settings/security")
async def get_security_settings():
    """Get security settings."""
    try:
        return SecuritySettingsResponse(
            password_required=_security_settings.password_required(),
            totp_enabled=_security_settings.totp_config is not None and getattr(_security_settings.totp_config, "enabled", False),
            cloudflare_access_enabled=_security_settings.cloudflare_access_enabled,
            security_level=_security_settings.level.value if hasattr(_security_settings.level, "value") else str(_security_settings.level),
        )
    except Exception as e:
        logger.error(f"Failed to get security settings: {e}")
        return SecuritySettingsResponse()

@router.put("/settings/security")
async def update_security_settings(settings: SecuritySettingsResponse):
    """Update security settings."""
    # Note: Security settings persistence is complex and often tied to env vars or separate config.
    # For now, we acknowledge the request but don't persist to the simple JSON store 
    # to avoid overwriting critical security config with a simple file.
    # TODO: Implement proper security config management.
    return settings
