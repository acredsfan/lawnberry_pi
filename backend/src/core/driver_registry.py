from __future__ import annotations

import os

import yaml

from backend.src.core.simulation import is_simulation_mode


def _make_mock(name: str) -> object:
    """Create a lightweight mock driver instance with a stable repr.

    In SIM_MODE, drivers are simple objects but distinct per instantiation so
    restarts can be detected via object identity changes in tests.
    """
    cls_name = "Mock" + name.replace("_", " ").title().replace(" ", "") + "Driver"
    return type(cls_name, (), {})()


class DriverRegistry:
    """Simple driver registry with minimal restart semantics.

    Notes:
    - In SIM_MODE, returns mock driver objects keyed by logical names.
    - In non-sim mode, creates opaque object() placeholders based on config.
    - Maintains internal mapping to allow mark_failed() and restart().
    """

    def __init__(self, config_path: str | None = None):
        self.config_path = config_path or os.path.join(os.getcwd(), "config", "hardware.yaml")
        self._drivers: dict[str, object] = {}
        self._config_cache: dict[str, object] = {}

    def _load_config(self) -> dict[str, object]:
        try:
            with open(self.config_path, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except FileNotFoundError:
            cfg = {}
        self._config_cache = cfg
        return cfg

    def _instantiate(self, name: str, cfg: dict[str, object] | None = None) -> object | None:
        if is_simulation_mode():
            return _make_mock(name)

        # Minimal instantiation logic from config presence
        cfg = cfg or (self._config_cache or self._load_config())
        if name == "gps" and (cfg.get("gps", {}) or {}).get("type"):
            return object()
        if name == "imu" and (cfg.get("imu", {}) or {}).get("type"):
            return object()
        if name in ("tof_left", "tof_right"):
            tof = (cfg.get("sensors", {}) or {}).get("tof", [])
            if (name == "tof_left" and "left" in tof) or (name == "tof_right" and "right" in tof):
                return object()
        if name == "power" and (cfg.get("power_monitor", {}) or {}).get("type"):
            return object()
        if name == "motor" and (cfg.get("motor_controller", {}) or {}).get("type"):
            return object()
        return None

    def load(self) -> dict[str, object]:
        """Load driver instances and cache internally.

        Returns the internal mapping for convenience.
        """
        self._drivers.clear()
        if is_simulation_mode():
            self._drivers.update(
                {
                    "gps": _make_mock("gps"),
                    "imu": _make_mock("imu"),
                    "tof_left": _make_mock("tof_left"),
                    "tof_right": _make_mock("tof_right"),
                    "power": _make_mock("power"),
                    "motor": _make_mock("motor"),
                }
            )
            return dict(self._drivers)

        cfg = self._load_config()
        for name in ("gps", "imu", "tof_left", "tof_right", "power", "motor"):
            inst = self._instantiate(name, cfg)
            if inst is not None:
                self._drivers[name] = inst
        return dict(self._drivers)

    def get(self, name: str) -> object | None:
        return self._drivers.get(name)

    def mark_failed(self, name: str) -> None:
        """Mark a driver as failed (removed), to be recreated on restart."""
        if name in self._drivers:
            # Remove to simulate failure/crash
            del self._drivers[name]

    def restart(self, name: str) -> object | None:
        """Restart (recreate) a driver instance by name.

        Returns the new instance or None if not available per config.
        """
        inst = self._instantiate(name)
        if inst is not None:
            self._drivers[name] = inst
        return inst

    def list(self) -> dict[str, object]:
        return dict(self._drivers)
