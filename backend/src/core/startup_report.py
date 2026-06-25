# backend/src/core/startup_report.py
"""Startup configuration report builder.

Produces a structured dict that lists each loaded config file, the selected
hardware source, and effective config values. Secrets identified by key name
are redacted recursively.

The report is logged at INFO level during startup and attached to the
/health response under the key "startup_config_report".
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SECRET_KEYWORDS = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "key",
        "credential",
        "credentials",
        "ntrip_password",
        "encryption_key",
        "device_key",
    }
)
REDACTED = "[REDACTED]"


def _is_secret_key(key: str, secrets_keys: list[str]) -> bool:
    key_lower = key.lower()
    if key in secrets_keys:
        return True
    return any(kw in key_lower for kw in _SECRET_KEYWORDS)


def _redact_secrets(value: Any, secrets_keys: list[str]) -> Any:
    """Recursively redact secret keys in dictionaries and lists."""
    if isinstance(value, list):
        return [_redact_secrets(item, secrets_keys) for item in value]
    if not isinstance(value, dict):
        return value
    result: dict[str, Any] = {}
    for k, v in value.items():
        if _is_secret_key(k, secrets_keys):
            result[k] = REDACTED
        else:
            result[k] = _redact_secrets(v, secrets_keys)
    return result


def build_startup_report(
    hardware_path: str,
    limits_path: str,
    calibration_path: Path,
    secrets_keys: list[str],
    *,
    hardware_config: Any | None = None,
    safety_limits: Any | None = None,
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build and return the startup config report dict.

    Args:
        hardware_path: Absolute path to hardware.yaml.
        limits_path: Absolute path to limits.yaml.
        calibration_path: Path to calibration.json (may not exist).
        secrets_keys: Additional key names to treat as secrets.

    Returns:
        dict with keys: files_loaded, overlays_applied, hardware_source,
        hardware_loaded, hardware_overlay, and effective_values.
    """
    files_loaded: list[str] = []
    effective: dict[str, Any] = {}
    metadata = dict(source_metadata or {})

    hardware_loaded = bool(metadata.get("hardware_loaded", Path(hardware_path).exists()))
    if hardware_loaded and Path(hardware_path).exists():
        files_loaded.append(hardware_path)

    if hardware_config is not None:
        hw_effective = hardware_config.model_dump(mode="json", exclude_none=True)
    else:
        hw_effective = {}
    effective["hardware"] = _redact_secrets(hw_effective, secrets_keys)

    if Path(limits_path).exists():
        files_loaded.append(limits_path)
    if safety_limits is not None:
        limits_effective = safety_limits.model_dump(mode="json", exclude_none=True)
    else:
        limits_effective = {}
    effective["limits"] = _redact_secrets(limits_effective, secrets_keys)

    # Calibration JSON
    cal_data: dict[str, Any] = {}
    if calibration_path.exists():
        files_loaded.append(str(calibration_path))
        try:
            cal_data = json.loads(calibration_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("startup_report: could not read calibration: %s", exc)
    effective["calibration"] = _redact_secrets(cal_data, secrets_keys)

    report = {
        "files_loaded": files_loaded,
        "overlays_applied": [],
        "hardware_source": metadata.get("hardware_source", hardware_path),
        "hardware_loaded": hardware_loaded,
        "hardware_overlay": None,
        "hardware_missing_allowed": bool(metadata.get("hardware_missing_allowed", False)),
        "hardware_legacy_present": bool(metadata.get("hardware_legacy_present", False)),
        "effective_values": effective,
    }
    logger.info(
        "Startup config report: files=%s hardware_source=%s hardware_loaded=%s",
        files_loaded,
        report["hardware_source"],
        hardware_loaded,
    )
    return report


__all__ = ["REDACTED", "build_startup_report"]
