from __future__ import annotations

"""Configuration loader for hardware and safety limits (T003).

Loads YAML from config/hardware.yaml and config/limits.yaml, validates via
Pydantic models, and provides cached access with optional reload.

Acceptance (FR-003, FR-004):
- Loads at startup
- Validates against HardwareConfig and SafetyLimits schemas
"""

import os
from typing import Optional, Tuple, Dict, Any

import yaml
from pydantic import ValidationError

from backend.src.models.hardware_config import HardwareConfig
from backend.src.models.safety_limits import SafetyLimits


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
        config_dir: Optional[str] = None,
        hardware_path: Optional[str] = None,
        limits_path: Optional[str] = None,
    ) -> None:
        self.config_dir = config_dir or _default_config_dir()
        self.hardware_path = hardware_path or os.path.join(self.config_dir, "hardware.yaml")
        self.limits_path = limits_path or os.path.join(self.config_dir, "limits.yaml")
        self._cache: Optional[Tuple[HardwareConfig, SafetyLimits]] = None

    def _read_yaml(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                if not isinstance(data, dict):
                    raise ValueError(f"YAML at {path} must be a mapping/object")
                return data
        except FileNotFoundError:
            return {}

    def load(self) -> Tuple[HardwareConfig, SafetyLimits]:
        """Load and validate configuration; caches the result.

        Raises:
            ValidationError/ValueError on invalid configuration.
        """
        hw_raw = self._read_yaml(self.hardware_path)
        limits_raw = self._read_yaml(self.limits_path)

        try:
            hardware = HardwareConfig(**self._normalize_hardware_yaml(hw_raw))
        except ValidationError as e:
            # Re-raise with file context
            raise ValidationError.from_exception_data(
                title=f"Invalid hardware.yaml at {self.hardware_path}",
                line_errors=e.errors(),
            )
        except ValueError as e:
            raise ValueError(f"Invalid hardware.yaml at {self.hardware_path}: {e}")

        try:
            limits = SafetyLimits(**self._normalize_limits_yaml(limits_raw))
        except ValidationError as e:
            raise ValidationError.from_exception_data(
                title=f"Invalid limits.yaml at {self.limits_path}",
                line_errors=e.errors(),
            )
        except ValueError as e:
            raise ValueError(f"Invalid limits.yaml at {self.limits_path}: {e}")

        self._cache = (hardware, limits)
        return self._cache

    def get(self) -> Tuple[HardwareConfig, SafetyLimits]:
        """Return cached configs, loading if necessary."""
        if self._cache is None:
            return self.load()
        return self._cache

    def reload(self) -> Tuple[HardwareConfig, SafetyLimits]:
        """Force reloading configs from disk."""
        self._cache = None
        return self.load()

    @staticmethod
    def _normalize_hardware_yaml(cfg: Dict[str, Any]) -> Dict[str, Any]:
        """Map YAML structure to HardwareConfig fields.

        Supports both flat and nested forms used by tests and docs.
        """
        # Accept two shapes:
        # 1) Flat keys matching HardwareConfig fields
        # 2) Nested keys similar to driver_registry expectations
        if not cfg:
            return {}

        mapped: Dict[str, Any] = {}

        # Flat mapping passthrough
        for key in (
            "gps_type",
            "gps_ntrip_enabled",
            "imu_type",
            "tof_sensors",
            "env_sensor",
            "power_monitor",
            "motor_controller",
            "blade_controller",
            "camera_enabled",
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

        imu = cfg.get("imu") or {}
        if isinstance(imu, dict) and "type" in imu and "imu_type" not in mapped:
            t = str(imu.get("type")).strip().lower()
            if t in {"bno085", "bno080", "bno085-uart", "bno 085 uart"}:
                mapped["imu_type"] = "bno085-uart"
            else:
                mapped["imu_type"] = imu.get("type")

        sensors = cfg.get("sensors") or {}
        tof = sensors.get("tof") if isinstance(sensors, dict) else None
        if isinstance(tof, list) and "tof_sensors" not in mapped:
            mapped["tof_sensors"] = tof
        # Optional typed ToF config block
        tof_cfg = sensors.get("tof_config") if isinstance(sensors, dict) else None
        if isinstance(tof_cfg, dict):
            # Preserve as-is; Pydantic model on HardwareConfig will validate
            mapped["tof_config"] = tof_cfg

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
        elif isinstance(power_entry, bool) and "power_monitor" not in mapped:
            mapped["power_monitor"] = power_entry

        if "ina3221" in cfg and isinstance(cfg["ina3221"], dict):
            mapped["ina3221_config"] = cfg["ina3221"]

        motor = cfg.get("motor_controller") or {}
        if isinstance(motor, dict) and "type" in motor and "motor_controller" not in mapped:
            t = str(motor.get("type")).strip().lower()
            if "robohat" in t:
                mapped["motor_controller"] = "robohat-rp2040"
            elif "l298n" in t:
                mapped["motor_controller"] = "l298n"
            else:
                mapped["motor_controller"] = motor.get("type")

        return mapped

    @staticmethod
    def _normalize_limits_yaml(cfg: Dict[str, Any]) -> Dict[str, Any]:
        return cfg or {}


__all__ = ["ConfigLoader"]
