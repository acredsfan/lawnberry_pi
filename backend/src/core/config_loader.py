from __future__ import annotations

import threading

"""Configuration loader for hardware and safety limits (T003).

Loads YAML from config/hardware.yaml and config/limits.yaml, validates via
Pydantic models, and provides cached access with optional reload.

Acceptance (FR-003, FR-004):
- Loads at startup
- Validates against HardwareConfig and SafetyLimits schemas
"""

import logging
import os
from copy import deepcopy
from typing import Any

import yaml
from pydantic import ValidationError

from backend.src.core.simulation import is_simulation_mode
from backend.src.models.hardware_config import (
    BatteryConfig,
    HardwareConfig,
    Ina3221Config,
    VictronBleConfig,
)
from backend.src.models.safety_limits import SafetyLimits

logger = logging.getLogger(__name__)

_HARDWARE_SETUP_HINT = (
    "Run `uv run python scripts/manage_hardware_config.py ensure --profile auto` "
    "or pass `--profile pi5` / `--profile pi4` on non-detectable hosts."
)

_HARDWARE_MIGRATION_HINT = (
    "Run `uv run python scripts/manage_hardware_config.py migrate-legacy --profile auto` "
    "after backing up local configuration."
)


def _default_config_dir() -> str:
    return os.path.join(os.getcwd(), "config")


class ConfigLoader:
    """Load and validate LawnBerry configuration files.

    Files:
      - hardware.yaml
      - limits.yaml

    Usage:
      loader = ConfigLoader()
      hw, limits = loader.load()
    """

    def __init__(
        self,
        config_dir: str | None = None,
        hardware_path: str | None = None,
        limits_path: str | None = None,
        hardware_local_path: str | None = None,
        limits_local_path: str | None = None,
    ) -> None:
        self.config_dir = config_dir or _default_config_dir()
        self.hardware_path = hardware_path or os.path.join(self.config_dir, "hardware.yaml")
        self.limits_path = limits_path or os.path.join(self.config_dir, "limits.yaml")
        self.hardware_local_path = hardware_local_path or os.path.join(
            self.config_dir, "hardware.local.yaml"
        )
        env_limits_local = os.environ.get("LAWN_LIMITS_LOCAL_PATH")
        self.limits_local_path = (
            limits_local_path
            or env_limits_local
            or os.path.join(self.config_dir, "limits.local.yaml")
        )
        self._cache: tuple[HardwareConfig, SafetyLimits] | None = None
        self.hardware_loaded: bool = False
        self.hardware_missing_allowed: bool = False
        self.hardware_overlay: str | None = None
        self.hardware_legacy_present: bool = False

    def _read_yaml(self, path: str) -> dict[str, Any]:
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if not isinstance(data, dict):
                    raise ValueError(f"YAML at {path} must be a mapping/object")
                return data
        except FileNotFoundError:
            return {}

    def _load_hardware_raw(self) -> dict[str, Any]:
        self.hardware_loaded = False
        self.hardware_missing_allowed = False
        self.hardware_overlay = None
        self.hardware_legacy_present = bool(
            self.hardware_local_path and os.path.exists(self.hardware_local_path)
        )

        if self.hardware_legacy_present:
            message = (
                f"Legacy hardware overlay found at {self.hardware_local_path}. "
                f"Runtime no longer loads hardware.local.yaml. {_HARDWARE_MIGRATION_HINT}"
            )
            if is_simulation_mode():
                logger.warning(message)
            else:
                raise RuntimeError(message)

        if not os.path.exists(self.hardware_path):
            if is_simulation_mode():
                self.hardware_missing_allowed = True
                logger.warning(
                    "Hardware configuration %s is missing; using simulation-safe defaults",
                    self.hardware_path,
                )
                return {}
            raise FileNotFoundError(
                f"Hardware configuration not found at {self.hardware_path}. {_HARDWARE_SETUP_HINT}"
            )

        self.hardware_loaded = True
        return self._read_yaml(self.hardware_path)

    def load(self) -> tuple[HardwareConfig, SafetyLimits]:
        """Load and validate configuration; caches the result.

        Raises:
            ValidationError/ValueError on invalid configuration.
        """
        hw_raw = self._load_hardware_raw()
        limits_raw = self._read_yaml(self.limits_path)
        limits_local_raw = self._read_yaml(self.limits_local_path) if self.limits_local_path else {}
        if limits_local_raw:
            limits_raw = self._deep_merge(limits_raw, limits_local_raw)

        try:
            self._validate_hardware_yaml_keys(hw_raw)
            hardware = HardwareConfig(**self._normalize_hardware_yaml(hw_raw))
        except ValidationError as e:
            # Re-raise with file context
            raise ValidationError.from_exception_data(
                title=f"Invalid hardware.yaml at {self.hardware_path}",
                line_errors=e.errors(),
            ) from e
        except ValueError as e:
            raise ValueError(f"Invalid hardware.yaml at {self.hardware_path}: {e}") from e

        try:
            limits = SafetyLimits(**self._normalize_limits_yaml(limits_raw))
        except ValidationError as e:
            raise ValidationError.from_exception_data(
                title=f"Invalid limits.yaml at {self.limits_path}",
                line_errors=e.errors(),
            ) from e
        except ValueError as e:
            raise ValueError(f"Invalid limits.yaml at {self.limits_path}: {e}") from e

        self._cache = (hardware, limits)
        return self._cache

    def source_metadata(self) -> dict[str, Any]:
        """Return non-secret source metadata for startup/health diagnostics."""

        return {
            "hardware_source": self.hardware_path,
            "hardware_loaded": self.hardware_loaded,
            "hardware_missing_allowed": self.hardware_missing_allowed,
            "hardware_overlay": self.hardware_overlay,
            "hardware_legacy_path": self.hardware_local_path,
            "hardware_legacy_present": self.hardware_legacy_present,
            "limits_source": self.limits_path,
            "limits_local_source": self.limits_local_path,
            "limits_local_loaded": bool(self.limits_local_path and os.path.exists(self.limits_local_path)),
        }

    def get(self) -> tuple[HardwareConfig, SafetyLimits]:
        """Return cached configs, loading if necessary."""
        if self._cache is None:
            return self.load()
        return self._cache

    def reload(self) -> tuple[HardwareConfig, SafetyLimits]:
        """Force reloading configs from disk."""
        self._cache = None
        return self.load()

    def update_limits(self, patch: dict[str, Any]) -> SafetyLimits:
        """Merge *patch* into limits.local.yaml, validate the merged result, and reload.

        User customisations are written only to limits.local.yaml (gitignored)
        so that limits.yaml can remain an unmodified template in version control.
        Only keys present in SafetyLimits are accepted; unknown keys are silently dropped.
        Returns the validated merged SafetyLimits after write.
        """
        # Load current local overrides (may be empty on first write)
        local_raw = self._read_yaml(self.limits_local_path)
        allowed = set(SafetyLimits.model_fields.keys())
        for key, value in patch.items():
            if key in allowed:
                local_raw[key] = value

        # Validate the full merged result (template + new local) before writing
        template_raw = self._read_yaml(self.limits_path)
        merged_raw = self._deep_merge(template_raw, local_raw)
        updated = SafetyLimits(**self._normalize_limits_yaml(merged_raw))

        # Persist only the local overrides (not the full merged set)
        with open(self.limits_local_path, "w", encoding="utf-8") as f:
            yaml.dump(local_raw, f, default_flow_style=False, sort_keys=False)

        self._cache = None  # bust cache so next get() reads new values
        return updated

    @staticmethod
    def _normalize_hardware_yaml(cfg: dict[str, Any]) -> dict[str, Any]:
        """Map YAML structure to HardwareConfig fields.

        Supports both flat and nested forms used by tests and docs.
        """
        # Accept two shapes:
        # 1) Flat keys matching HardwareConfig fields
        # 2) Nested keys similar to driver_registry expectations
        if not cfg:
            return {}

        mapped: dict[str, Any] = {}

        # Flat mapping passthrough
        for key in (
            "gps_type",
            "gps_ntrip_enabled",
            "gps_antenna_offset_forward_m",
            "gps_antenna_offset_right_m",
            "gps_usb_device",
            "imu_type",
            "imu_port",
            "imu_mode",
            "imu_yaw_offset_degrees",
            "encoder_enabled",
            "tof_sensors",
            "env_sensor",
            "power_monitor",
            "motor_controller",
            "motor_controller_port",
            "blade_controller",
            "blade",
            "camera",
            "camera_enabled",
            "tof_config",
            "ina3221_config",
            "bme280_config",
            "victron_config",
            "battery_config",
        ):
            if key in cfg:
                if key == "power_monitor" and isinstance(cfg[key], dict):
                    # Defer dict handling so we can extract INA3221 config separately
                    continue
                mapped[key] = cfg[key]

        # Nested mapping compatibility (from tests/driver_registry style)
        gps = cfg.get("gps") or {}
        if isinstance(gps, dict) and "type" in gps and "gps_type" not in mapped:
            # Normalize common string values to enum values
            t = str(gps.get("type")).strip().lower()
            connection = str(gps.get("connection", "")).strip().lower()
            if t in {"zed-f9p", "zed_f9p", "zed-f9p-usb", "zed f9p usb", "zed-f9p-uart", "zed f9p"}:
                if connection == "uart" or t in {"zed-f9p-uart", "zed f9p uart"}:
                    mapped["gps_type"] = "zed-f9p-uart"
                else:
                    mapped["gps_type"] = "zed-f9p-usb"
            elif t in {"neo-8m", "neo8m", "neo-8m-uart", "neo 8m uart"}:
                mapped["gps_type"] = "neo-8m-uart"
            else:
                mapped["gps_type"] = gps.get("type")

        if isinstance(gps, dict) and "ntrip_enabled" in gps and "gps_ntrip_enabled" not in mapped:
            mapped["gps_ntrip_enabled"] = bool(gps.get("ntrip_enabled"))

        if isinstance(gps, dict) and "usb_device" in gps and "gps_usb_device" not in mapped:
            mapped["gps_usb_device"] = str(gps["usb_device"])

        gps_float_keys = {
            "antenna_offset_forward_m": "gps_antenna_offset_forward_m",
            "antenna_offset_right_m": "gps_antenna_offset_right_m",
        }
        if isinstance(gps, dict):
            for source_key, target_key in gps_float_keys.items():
                if source_key in gps and target_key not in mapped:
                    mapped[target_key] = float(gps[source_key])

        imu = cfg.get("imu") or {}
        if isinstance(imu, dict) and "type" in imu and "imu_type" not in mapped:
            t = str(imu.get("type")).strip().lower()
            if t in {"bno085", "bno080", "bno085-uart", "bno 085 uart"}:
                mapped["imu_type"] = "bno085-uart"
            else:
                mapped["imu_type"] = imu.get("type")
        if isinstance(imu, dict) and "port" in imu and "imu_port" not in mapped:
            mapped["imu_port"] = imu["port"]
        if isinstance(imu, dict) and "mode" in imu and "imu_mode" not in mapped:
            mapped["imu_mode"] = str(imu["mode"])
        if (
            isinstance(imu, dict)
            and "yaw_offset_degrees" in imu
            and "imu_yaw_offset_degrees" not in mapped
        ):
            mapped["imu_yaw_offset_degrees"] = float(imu["yaw_offset_degrees"])

        encoders = cfg.get("encoders") or {}
        if isinstance(encoders, dict) and "enabled" in encoders and "encoder_enabled" not in mapped:
            mapped["encoder_enabled"] = bool(encoders["enabled"])

        sensors = cfg.get("sensors") or {}
        tof = sensors.get("tof") if isinstance(sensors, dict) else None
        if isinstance(tof, list) and "tof_sensors" not in mapped:
            mapped["tof_sensors"] = tof
        # Optional typed ToF config block
        tof_cfg = sensors.get("tof_config") if isinstance(sensors, dict) else None
        if isinstance(tof_cfg, dict):
            # Preserve as-is; Pydantic model on HardwareConfig will validate
            mapped["tof_config"] = tof_cfg

        if isinstance(sensors, dict) and "env_sensor" in sensors and "env_sensor" not in mapped:
            mapped["env_sensor"] = bool(sensors["env_sensor"])

        bme280_cfg = cfg.get("bme280")
        if isinstance(bme280_cfg, dict):
            mapped["bme280_config"] = bme280_cfg
            if "env_sensor" not in mapped:
                mapped["env_sensor"] = bool(bme280_cfg.get("enabled", True))

        power_entry = cfg.get("power_monitor")
        if isinstance(power_entry, dict):
            if "power_monitor" not in mapped:
                if "enabled" in power_entry:
                    mapped["power_monitor"] = bool(power_entry.get("enabled"))
                elif "type" in power_entry:
                    mapped["power_monitor"] = True
            ina_cfg = power_entry.get("ina3221")
            if isinstance(ina_cfg, dict):
                mapped["ina3221_config"] = ina_cfg
            victron_cfg = power_entry.get("victron") or power_entry.get("victron_vedirect")
            if isinstance(victron_cfg, dict):
                mapped["victron_config"] = victron_cfg
        elif isinstance(power_entry, bool) and "power_monitor" not in mapped:
            mapped["power_monitor"] = power_entry

        if "ina3221" in cfg and isinstance(cfg["ina3221"], dict):
            mapped["ina3221_config"] = cfg["ina3221"]
        if "victron" in cfg and isinstance(cfg["victron"], dict):
            mapped["victron_config"] = cfg["victron"]

        # Battery pack specification block
        battery = cfg.get("battery")
        if isinstance(battery, dict):
            mapped["battery_config"] = battery

        motor = cfg.get("motor_controller") or {}
        if isinstance(motor, dict) and "type" in motor and "motor_controller" not in mapped:
            t = str(motor.get("type")).strip().lower()
            if "robohat" in t:
                mapped["motor_controller"] = "robohat-rp2040"
            elif "l298n" in t:
                mapped["motor_controller"] = "l298n"
            else:
                mapped["motor_controller"] = motor.get("type")

        if "motor_controller_port" in cfg and "motor_controller_port" not in mapped:
            port = cfg.get("motor_controller_port")
            mapped["motor_controller_port"] = str(port).strip() if port is not None else None

        blade_controller_entry = cfg.get("blade_controller")
        if isinstance(blade_controller_entry, dict) and "type" in blade_controller_entry:
            blade_type = str(blade_controller_entry.get("type")).strip().lower()
            if blade_type in {"ibt_4", "ibt-4", "ibt4"}:
                mapped["blade_controller"] = "ibt-4"
            elif "robohat" in blade_type:
                mapped["blade_controller"] = "robohat-rp2040"
            else:
                mapped["blade_controller"] = blade_controller_entry.get("type")

        blade_cfg = cfg.get("blade")
        if isinstance(blade_cfg, dict):
            mapped["blade"] = blade_cfg
            if "controller" in blade_cfg and "blade_controller" not in mapped:
                mapped["blade_controller"] = blade_cfg["controller"]
        elif "blade_controller" in mapped:
            mapped["blade"] = {"controller": mapped["blade_controller"]}

        camera = cfg.get("camera") or {}
        if isinstance(camera, dict) and "enabled" in camera and "camera_enabled" not in mapped:
            mapped["camera_enabled"] = bool(camera["enabled"])

        return mapped

    def _validate_hardware_yaml_keys(self, cfg: dict[str, Any]) -> None:
        """Reject unknown runtime hardware settings before normalization drops them."""

        if not cfg:
            return

        allowed_top = {
            "gps",
            "gps_type",
            "gps_ntrip_enabled",
            "gps_usb_device",
            "gps_antenna_offset_forward_m",
            "gps_antenna_offset_right_m",
            "imu",
            "imu_type",
            "imu_port",
            "imu_mode",
            "imu_yaw_offset_degrees",
            "encoders",
            "encoder_enabled",
            "sensors",
            "tof_config",
            "tof_sensors",
            "env_sensor",
            "bme280",
            "bme280_config",
            "power_monitor",
            "ina3221",
            "ina3221_config",
            "victron",
            "victron_config",
            "battery_config",
            "motor_controller",
            "motor_controller_port",
            "blade_controller",
            "blade",
            "camera_enabled",
            "battery",
        }
        nested_allowed = {
            "gps": {
                "type",
                "connection",
                "ntrip_enabled",
                "usb_device",
                "antenna_offset_forward_m",
                "antenna_offset_right_m",
            },
            "imu": {"type", "port", "mode", "yaw_offset_degrees"},
            "encoders": {"enabled"},
            "sensors": {"tof", "tof_config", "env_sensor", "power_monitor"},
            "sensors.tof_config": {
                "bus",
                "left_address",
                "right_address",
                "ranging_mode",
                "left_shutdown_gpio",
                "right_shutdown_gpio",
                "left_interrupt_gpio",
                "right_interrupt_gpio",
                "timing_budget_us",
            },
            "tof_config": {
                "bus",
                "left_address",
                "right_address",
                "ranging_mode",
                "left_shutdown_gpio",
                "right_shutdown_gpio",
                "left_interrupt_gpio",
                "right_interrupt_gpio",
                "timing_budget_us",
            },
            "bme280": {"enabled", "bus", "address", "sea_level_hpa"},
            "bme280_config": {"enabled", "bus", "address", "sea_level_hpa"},
            "power_monitor": {
                "enabled",
                "type",
                "channels",
                "ina3221",
                "victron",
                "victron_vedirect",
            },
            "power_monitor.ina3221": set(Ina3221Config.model_fields),
            "power_monitor.victron": set(VictronBleConfig.model_fields),
            "power_monitor.victron_vedirect": set(VictronBleConfig.model_fields),
            "ina3221": set(Ina3221Config.model_fields),
            "ina3221_config": set(Ina3221Config.model_fields),
            "victron": set(VictronBleConfig.model_fields),
            "victron_config": set(VictronBleConfig.model_fields),
            "battery": set(BatteryConfig.model_fields),
            "battery_config": set(BatteryConfig.model_fields),
            "blade": {
                "controller",
                "allow_autonomous",
                "spinup_seconds",
                "shutdown_timeout_seconds",
                "command_ack_timeout_seconds",
                "pins",
            },
            "blade.pins": {"in1", "in2"},
            "blade_controller": {"type"},
            "camera": {"enabled"},
            "motor_controller": {"type"},
        }

        for key, value in cfg.items():
            if key not in allowed_top:
                raise ValueError(f"unsupported top-level setting '{key}'")
            self._validate_nested_hardware_keys(value, key, nested_allowed)

    def _validate_nested_hardware_keys(
        self,
        value: Any,
        path: str,
        nested_allowed: dict[str, set[str]],
    ) -> None:
        if not isinstance(value, dict):
            return
        allowed = nested_allowed.get(path)
        if allowed is None:
            return
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key not in allowed:
                raise ValueError(f"unknown setting '{child_path}'")
            self._validate_nested_hardware_keys(child, child_path, nested_allowed)

    @staticmethod
    def _normalize_limits_yaml(cfg: dict[str, Any]) -> dict[str, Any]:
        return cfg or {}

    @staticmethod
    def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Merge override dict into base dict recursively without mutating inputs."""

        if not base and not override:
            return {}

        merged: dict[str, Any] = deepcopy(base) if base else {}
        for key, value in (override or {}).items():
            existing = merged.get(key)
            if isinstance(existing, dict) and isinstance(value, dict):
                merged[key] = ConfigLoader._deep_merge(existing, value)
            else:
                merged[key] = value
        return merged


__all__ = ["ConfigLoader", "get_config_loader"]

_config_loader_lock = threading.Lock()
_config_loader_instance: ConfigLoader | None = None


def get_config_loader() -> ConfigLoader:
    """Return the module-level ConfigLoader singleton.

    Uses double-checked locking so the instance is created at most once even
    when called concurrently from multiple threads at startup.
    """
    global _config_loader_instance
    if _config_loader_instance is None:
        with _config_loader_lock:
            if _config_loader_instance is None:
                _config_loader_instance = ConfigLoader()
    return _config_loader_instance
