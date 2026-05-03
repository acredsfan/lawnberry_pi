# backend/src/core/startup_report.py
"""Startup configuration report builder.

Produces a structured dict that lists every config file loaded, any local
overlays applied, and effective config values. Secrets (identified by key
name) are excluded from the effective_values section.

The report is logged at INFO level during startup and attached to the
/health response under the key "startup_config_report".
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_SECRET_KEYWORDS = frozenset(
    {"password", "secret", "token", "api_key", "key", "credential", "ntrip_password"}
)


def _is_secret_key(key: str, secrets_keys: list[str]) -> bool:
    key_lower = key.lower()
    if key in secrets_keys:
        return True
    return any(kw in key_lower for kw in _SECRET_KEYWORDS)


def _filter_secrets(d: dict[str, Any], secrets_keys: list[str]) -> dict[str, Any]:
    """Recursively remove secret keys from a dict."""
    result: dict[str, Any] = {}
    for k, v in d.items():
        if _is_secret_key(k, secrets_keys):
            continue
        if isinstance(v, dict):
            result[k] = _filter_secrets(v, secrets_keys)
        else:
            result[k] = v
    return result


def _read_yaml_safe(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.warning("startup_report: could not read %s: %s", path, exc)
        return {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    from copy import deepcopy
    merged = deepcopy(base)
    for k, v in override.items():
        if isinstance(merged.get(k), dict) and isinstance(v, dict):
            merged[k] = _deep_merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def build_startup_report(
    hardware_path: str,
    limits_path: str,
    hardware_local_path: str,
    calibration_path: Path,
    secrets_keys: list[str],
) -> dict[str, Any]:
    """Build and return the startup config report dict.

    Args:
        hardware_path: Absolute path to hardware.yaml.
        limits_path: Absolute path to limits.yaml.
        hardware_local_path: Absolute path to hardware.local.yaml (may not exist).
        calibration_path: Path to calibration.json (may not exist).
        secrets_keys: Additional key names to treat as secrets.

    Returns:
        dict with keys: files_loaded, overlays_applied, effective_values.
    """
    files_loaded: list[str] = []
    overlays_applied: list[str] = []
    effective: dict[str, Any] = {}

    # Hardware YAML
    hw_raw = _read_yaml_safe(hardware_path)
    if Path(hardware_path).exists():
        files_loaded.append(hardware_path)

    # Local overlay
    local_raw = _read_yaml_safe(hardware_local_path)
    if Path(hardware_local_path).exists():
        files_loaded.append(hardware_local_path)
        overlays_applied.append(hardware_local_path)
        hw_raw = _deep_merge(hw_raw, local_raw)

    effective["hardware"] = _filter_secrets(hw_raw, secrets_keys)

    # Limits YAML
    limits_raw = _read_yaml_safe(limits_path)
    if Path(limits_path).exists():
        files_loaded.append(limits_path)
    effective["limits"] = _filter_secrets(limits_raw, secrets_keys)

    # Calibration JSON
    cal_data: dict[str, Any] = {}
    if calibration_path.exists():
        files_loaded.append(str(calibration_path))
        try:
            cal_data = json.loads(calibration_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("startup_report: could not read calibration: %s", exc)
    effective["calibration"] = _filter_secrets(cal_data, secrets_keys)

    report = {
        "files_loaded": files_loaded,
        "overlays_applied": overlays_applied,
        "effective_values": effective,
    }
    logger.info(
        "Startup config report: files=%s overlays=%s",
        files_loaded,
        overlays_applied,
    )
    return report
