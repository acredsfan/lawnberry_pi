from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...core.globals import _security_last_modified, _security_settings
from ...models.auth_security_config import SecurityLevel
from ...services.settings_service import SettingsService

logger = logging.getLogger(__name__)
router = APIRouter()

DATA_DIR = Path(os.getcwd()) / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"
UI_SETTINGS_FILE = DATA_DIR / "ui_settings.json"


class SettingsResponse(BaseModel):
    theme: str = "dark"
    units: str = "metric"
    language: str = "en"
    notifications_enabled: bool = True
    map_provider: str = "osm"
    unit_system: str = "metric"


class SecuritySettingsResponse(BaseModel):
    auth_level: str = "password"
    session_timeout_minutes: int = 60
    require_https: bool = False
    auto_lock_manual_control: bool = True
    password_required: bool = False
    totp_enabled: bool = False
    cloudflare_access_enabled: bool = False
    security_level: str = "PASSWORD"


class SystemSectionResponse(BaseModel):
    device_name: str = "LawnBerry Pi"
    timezone: str = "UTC"
    timezone_source: str = "default"
    debug_mode: bool = False
    sim_mode: bool = Field(default_factory=lambda: os.getenv("SIM_MODE", "0") != "0")
    unit_system: str = "metric"
    ui: dict[str, Any] = Field(
        default_factory=lambda: {
            "unit_system": "metric",
            "theme": "retro-amber",
            "auto_refresh": True,
            "map_provider": "osm",
        }
    )


class RemoteAccessSectionResponse(BaseModel):
    method: str = "none"
    provider: str = "disabled"
    enabled: bool = False
    cloudflare_token: str = ""
    ngrok_token: str = ""
    custom_domain: str = ""
    auto_tls: bool = True
    cloudflare: dict[str, Any] = Field(default_factory=dict)
    ngrok: dict[str, Any] = Field(default_factory=dict)
    custom: dict[str, Any] = Field(default_factory=dict)


class MapsSectionResponse(BaseModel):
    provider: str = "osm"
    style: str = "standard"
    google_api_key: str = ""
    google_billing_warnings: bool = True
    zoom_level: int = 18
    bypass_external: bool = False


class GpsPolicySectionResponse(BaseModel):
    gps_loss_policy: str = "dead_reckoning"
    dead_reckoning_duration_minutes: int = 2
    reduced_speed_factor: float = 0.5
    accuracy_threshold_meters: int = 3


def _default_sections() -> dict[str, Any]:
    system = SystemSectionResponse().model_dump()
    return {
        "system": system,
        "security": {
            "auth_level": "password",
            "session_timeout_minutes": 60,
            "require_https": False,
            "auto_lock_manual_control": True,
        },
        "remote_access": RemoteAccessSectionResponse().model_dump(),
        "maps": MapsSectionResponse().model_dump(),
        "gps_policy": GpsPolicySectionResponse().model_dump(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _normalize_unit_system(value: Any, *, default: str = "metric") -> str:
    normalized = str(value or default).strip().lower()
    return normalized if normalized in {"metric", "imperial"} else default


def _default_legacy_settings() -> dict[str, Any]:
    return {
        "theme": "dark",
        "units": "metric",
        "language": "en",
        "notifications_enabled": True,
        "map_provider": "osm",
    }


def _load_legacy_settings() -> dict[str, Any]:
    defaults = _default_legacy_settings()
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text())
            if isinstance(data, dict):
                merged = {**defaults, **data}
                merged["units"] = _normalize_unit_system(
                    merged.get("unit_system") or merged.get("units"),
                    default=defaults["units"],
                )
                map_provider = str(merged.get("map_provider") or defaults["map_provider"]).strip().lower()
                if map_provider == "openstreetmap":
                    map_provider = "osm"
                merged["map_provider"] = map_provider
                return {
                    "theme": str(merged.get("theme") or defaults["theme"]),
                    "units": merged["units"],
                    "language": str(merged.get("language") or defaults["language"]),
                    "notifications_enabled": bool(merged.get("notifications_enabled", defaults["notifications_enabled"])),
                    "map_provider": map_provider,
                }
    except Exception as exc:
        logger.warning("Failed to load legacy settings: %s", exc)
    return defaults


def _save_legacy_settings(data: dict[str, Any]) -> dict[str, Any]:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        merged = {**_load_legacy_settings(), **data}
        merged["units"] = _normalize_unit_system(merged.get("unit_system") or merged.get("units"))
        map_provider = str(merged.get("map_provider") or "osm").strip().lower()
        if map_provider == "openstreetmap":
            map_provider = "osm"
        merged["map_provider"] = map_provider
        payload = {
            "theme": str(merged.get("theme") or "dark"),
            "units": merged["units"],
            "language": str(merged.get("language") or "en"),
            "notifications_enabled": bool(merged.get("notifications_enabled", True)),
            "map_provider": map_provider,
        }
        SETTINGS_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return payload
    except Exception as exc:
        logger.error("Failed to save legacy settings: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save settings") from exc


def _load_ui_settings() -> dict[str, Any]:
    defaults = _default_sections()
    try:
        if UI_SETTINGS_FILE.exists():
            data = json.loads(UI_SETTINGS_FILE.read_text())
            if isinstance(data, dict):
                merged = defaults | data
                for key in ("system", "security", "remote_access", "maps", "gps_policy"):
                    merged[key] = {**defaults.get(key, {}), **(data.get(key, {}) or {})}
                return merged
    except Exception as exc:
        logger.warning("Failed to load UI settings: %s", exc)
    return defaults


def _save_ui_settings(data: dict[str, Any]) -> dict[str, Any]:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {**data, "updated_at": datetime.now(timezone.utc).isoformat()}
        UI_SETTINGS_FILE.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return payload
    except Exception as exc:
        logger.error("Failed to save UI settings: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save settings") from exc


def _response_headers(payload: Any, last_modified: datetime | None = None) -> dict[str, str]:
    body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    headers = {
        "ETag": sha256(body).hexdigest(),
        "Cache-Control": "public, max-age=30",
    }
    if last_modified:
        headers["Last-Modified"] = format_datetime(last_modified)
    return headers


def _maybe_not_modified(request: Request, payload: Any, last_modified: datetime | None = None) -> JSONResponse | None:
    headers = _response_headers(payload, last_modified)
    inm = request.headers.get("if-none-match")
    ims = request.headers.get("if-modified-since")
    if inm == headers["ETag"]:
        return JSONResponse(status_code=304, content=None, headers=headers)
    if ims and last_modified is not None:
        try:
            ims_dt = parsedate_to_datetime(ims)
            if ims_dt.tzinfo is None:
                ims_dt = ims_dt.replace(tzinfo=timezone.utc)
            if ims_dt >= last_modified.replace(microsecond=0):
                return JSONResponse(status_code=304, content=None, headers=headers)
        except Exception:
            pass
    return None


def _coerce_auth_level(value: Any) -> str:
    normalized = str(value or "password").strip().lower()
    mapping = {
        "basic": "password",
        "password": "password",
        "password_only": "password",
        "totp": "totp",
        "password_totp": "totp",
        "google": "google",
        "google_auth": "google",
        "cloudflare": "cloudflare",
        "cloudflare_tunnel_auth": "cloudflare",
        "tunnel": "cloudflare",
        "tunnel_auth": "cloudflare",
    }
    return mapping.get(normalized, "password")


def _auth_level_to_security_level(value: str) -> SecurityLevel:
    normalized = _coerce_auth_level(value)
    if normalized == "totp":
        return SecurityLevel.TOTP
    if normalized == "google":
        return SecurityLevel.GOOGLE_OAUTH
    if normalized == "cloudflare":
        return SecurityLevel.TUNNEL_AUTH
    return SecurityLevel.PASSWORD


def _security_section_payload(stored: dict[str, Any] | None = None) -> dict[str, Any]:
    section = stored or {}
    auth_level = _coerce_auth_level(section.get("auth_level") or getattr(_security_settings, "security_level", SecurityLevel.PASSWORD).name)
    session_timeout = int(section.get("session_timeout_minutes") or getattr(_security_settings, "session_timeout_minutes", 60) or 60)
    require_https = bool(section.get("require_https", False))
    auto_lock_manual_control = bool(section.get("auto_lock_manual_control", True))
    security_level = _auth_level_to_security_level(auth_level)

    return SecuritySettingsResponse(
        auth_level=auth_level,
        session_timeout_minutes=session_timeout,
        require_https=require_https,
        auto_lock_manual_control=auto_lock_manual_control,
        password_required=security_level in {SecurityLevel.PASSWORD, SecurityLevel.TOTP},
        totp_enabled=security_level == SecurityLevel.TOTP,
        cloudflare_access_enabled=security_level == SecurityLevel.TUNNEL_AUTH,
        security_level=security_level.name,
    ).model_dump()


def _normalize_remote_section(payload: dict[str, Any]) -> dict[str, Any]:
    data = RemoteAccessSectionResponse.model_validate(payload).model_dump()
    provider = str(payload.get("provider") or payload.get("method") or data["provider"] or data["method"]).strip().lower()
    provider_map = {
        "disabled": "disabled",
        "none": "disabled",
        "cloudflare": "cloudflare",
        "ngrok": "ngrok",
        "custom": "custom",
    }
    normalized_provider = provider_map.get(provider, "disabled")
    data["provider"] = normalized_provider
    data["method"] = "none" if normalized_provider == "disabled" else normalized_provider
    if normalized_provider == "cloudflare":
        data["cloudflare"] = {
            **data.get("cloudflare", {}),
            **(payload.get("cloudflare") or {}),
        }
    if normalized_provider == "ngrok":
        data["ngrok"] = {
            **data.get("ngrok", {}),
            **(payload.get("ngrok") or {}),
        }
    if normalized_provider == "custom":
        custom = {**data.get("custom", {}), **(payload.get("custom") or {})}
        if data.get("custom_domain"):
            custom.setdefault("domain", data["custom_domain"])
        custom["auto_tls"] = data.get("auto_tls", True)
        data["custom"] = custom
    return data


def _normalize_maps_section(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    if "api_key" in data and not data.get("google_api_key"):
        data["google_api_key"] = data.get("api_key")
    provider = str(data.get("provider") or "osm").strip().lower()
    if provider not in {"google", "osm", "none"}:
        raise HTTPException(status_code=422, detail="provider must be one of google, osm, none")
    style = str(data.get("style") or "standard").strip().lower()
    if style not in {"standard", "satellite", "hybrid", "terrain"}:
        raise HTTPException(status_code=422, detail="style must be one of standard, satellite, hybrid, terrain")
    normalized = MapsSectionResponse.model_validate({**data, "provider": provider, "style": style}).model_dump()
    return normalized


def _maps_response_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_maps_section(payload)
    normalized["api_key"] = normalized.get("google_api_key", "")
    return normalized


def _settings_service() -> SettingsService:
    return SettingsService()


@router.get("/settings")
async def get_settings():
    """Get lightweight user settings compatibility payload."""
    return _load_legacy_settings()


@router.put("/settings")
async def update_settings(settings: dict[str, Any]):
    """Update lightweight user settings compatibility payload."""
    legacy_payload = _save_legacy_settings(settings)
    sections = _load_ui_settings()
    system = {**sections.get("system", {})}
    system_ui = {**system.get("ui", {})}
    maps = {**sections.get("maps", {})}
    unit_system = _normalize_unit_system(legacy_payload.get("units"))
    system_ui["unit_system"] = unit_system
    system_ui["theme"] = legacy_payload["theme"]
    system_ui["language"] = legacy_payload["language"]
    system_ui["notifications_enabled"] = legacy_payload["notifications_enabled"]
    system["ui"] = system_ui
    system["unit_system"] = unit_system
    maps["provider"] = legacy_payload["map_provider"]
    sections["system"] = SystemSectionResponse.model_validate(system).model_dump()
    sections["maps"] = _normalize_maps_section({**sections.get("maps", {}), **maps})
    _save_ui_settings(sections)
    return legacy_payload


@router.get("/settings/system")
async def get_system_settings(request: Request):
    sections = _load_ui_settings()
    payload = SystemSectionResponse.model_validate(sections.get("system", {})).model_dump()
    payload["ui"]["unit_system"] = payload.get("unit_system") or payload["ui"].get("unit_system", "metric")
    last_modified = datetime.fromisoformat(sections.get("updated_at", datetime.now(timezone.utc).isoformat()))
    not_modified = _maybe_not_modified(request, payload, last_modified)
    if not_modified is not None:
        return not_modified
    return JSONResponse(content=payload, headers=_response_headers(payload, last_modified))


@router.put("/settings/system")
async def update_system_settings(settings: dict[str, Any]):
    sections = _load_ui_settings()
    current = {**sections.get("system", {})}
    merged = {**current, **settings}
    merged_ui = {**current.get("ui", {}), **(settings.get("ui") or {})}
    unit_system = merged_ui.get("unit_system") or merged.get("unit_system") or current.get("unit_system") or "metric"
    unit_system = str(unit_system).strip().lower()
    if unit_system not in {"metric", "imperial"}:
        raise HTTPException(status_code=422, detail="unit_system must be metric or imperial")
    merged["unit_system"] = unit_system
    merged_ui["unit_system"] = unit_system
    merged["ui"] = merged_ui
    validated = SystemSectionResponse.model_validate(merged).model_dump()
    sections["system"] = validated
    _save_ui_settings(sections)
    return validated


@router.get("/settings/security")
async def get_security_settings():
    sections = _load_ui_settings()
    return _security_section_payload(sections.get("security", {}))


@router.put("/settings/security")
async def update_security_settings(settings: dict[str, Any]):
    global _security_last_modified

    sections = _load_ui_settings()
    current = {**sections.get("security", {})}
    merged = {**current, **settings}
    auth_level = _coerce_auth_level(merged.get("auth_level") or merged.get("security_level"))
    session_timeout = int(merged.get("session_timeout_minutes") or getattr(_security_settings, "session_timeout_minutes", 60) or 60)
    if session_timeout < 5 or session_timeout > 1440:
        raise HTTPException(status_code=422, detail="session_timeout_minutes must be between 5 and 1440")

    _security_settings.security_level = _auth_level_to_security_level(auth_level)
    _security_settings.session_timeout_minutes = session_timeout
    _security_settings.tunnel_auth_enabled = _security_settings.security_level == SecurityLevel.TUNNEL_AUTH
    _security_last_modified = datetime.now(timezone.utc)

    sections["security"] = {
        "auth_level": auth_level,
        "session_timeout_minutes": session_timeout,
        "require_https": bool(merged.get("require_https", False)),
        "auto_lock_manual_control": bool(merged.get("auto_lock_manual_control", True)),
    }
    _save_ui_settings(sections)
    return _security_section_payload(sections["security"])


@router.get("/settings/remote-access")
async def get_remote_access_settings(request: Request):
    sections = _load_ui_settings()
    payload = _normalize_remote_section(sections.get("remote_access", {}))
    last_modified = datetime.fromisoformat(sections.get("updated_at", datetime.now(timezone.utc).isoformat()))
    not_modified = _maybe_not_modified(request, payload, last_modified)
    if not_modified is not None:
        return not_modified
    return JSONResponse(content=payload, headers=_response_headers(payload, last_modified))


@router.put("/settings/remote-access")
async def update_remote_access_settings(settings: dict[str, Any]):
    sections = _load_ui_settings()
    current = {**sections.get("remote_access", {})}
    payload = _normalize_remote_section({**current, **settings})
    sections["remote_access"] = payload
    _save_ui_settings(sections)
    return payload


@router.get("/settings/maps")
async def get_maps_settings(request: Request):
    sections = _load_ui_settings()
    payload = _maps_response_payload(sections.get("maps", {}))
    last_modified = datetime.fromisoformat(sections.get("updated_at", datetime.now(timezone.utc).isoformat()))
    not_modified = _maybe_not_modified(request, payload, last_modified)
    if not_modified is not None:
        return not_modified
    return JSONResponse(content=payload, headers=_response_headers(payload, last_modified))


@router.put("/settings/maps")
async def update_maps_settings(settings: dict[str, Any]):
    sections = _load_ui_settings()
    current = {**sections.get("maps", {})}
    payload = _normalize_maps_section({**current, **settings})
    sections["maps"] = payload
    _save_ui_settings(sections)
    return _maps_response_payload(payload)


@router.get("/settings/gps-policy")
async def get_gps_policy_settings(request: Request):
    sections = _load_ui_settings()
    payload = GpsPolicySectionResponse.model_validate(sections.get("gps_policy", {})).model_dump()
    last_modified = datetime.fromisoformat(sections.get("updated_at", datetime.now(timezone.utc).isoformat()))
    not_modified = _maybe_not_modified(request, payload, last_modified)
    if not_modified is not None:
        return not_modified
    return JSONResponse(content=payload, headers=_response_headers(payload, last_modified))


@router.put("/settings/gps-policy")
async def update_gps_policy_settings(settings: dict[str, Any]):
    sections = _load_ui_settings()
    current = {**sections.get("gps_policy", {})}
    payload = GpsPolicySectionResponse.model_validate({**current, **settings}).model_dump()
    sections["gps_policy"] = payload
    _save_ui_settings(sections)
    return payload


@router.get("/settings/telemetry")
async def get_telemetry_settings():
    profile = _settings_service().load_profile()
    return {
        "cadence_hz": profile.telemetry.cadence_hz,
        "latency_targets": profile.telemetry.latency_targets,
    }


@router.put("/settings/telemetry")
async def update_telemetry_settings(settings: dict[str, Any]):
    profile = _settings_service().load_profile()
    if "cadence_hz" in settings:
        cadence_hz = int(settings["cadence_hz"])
        if cadence_hz < 1 or cadence_hz > 10:
            raise HTTPException(status_code=422, detail="cadence_hz must be between 1 and 10")
        profile.telemetry.cadence_hz = cadence_hz
    if "latency_targets" in settings and isinstance(settings["latency_targets"], dict):
        profile.telemetry.latency_targets = settings["latency_targets"]
    _settings_service().save_profile(profile)
    return {
        "cadence_hz": profile.telemetry.cadence_hz,
        "latency_targets": profile.telemetry.latency_targets,
    }
