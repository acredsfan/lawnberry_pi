"""Compatibility settings models for unit tests and external integrations.

These models provide a stable API surface expected by tests while the
system_configuration models continue to serve the internal configuration.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class HardwareSettings(BaseModel):
    sim_mode: bool = False
    robohat_port: Optional[str] = None


class NetworkSettings(BaseModel):
    wifi_ssid: Optional[str] = None
    wifi_password: Optional[str] = None
    ap_enabled: bool = False
    ap_ssid: Optional[str] = None


class TelemetrySettings(BaseModel):
    stream_enabled: bool = True
    persist_enabled: bool = True
    retention_days: int = 30
    cadence_hz: int = 5
    latency_targets: dict = Field(default_factory=lambda: {"pi5_ms": 250, "pi4b_ms": 350})


class ControlSettings(BaseModel):
    lockout_enabled: bool = True
    lockout_timeout: int = 30
    blade_safety: bool = True


class MapsSettings(BaseModel):
    provider: str = "leaflet"
    api_key: Optional[str] = None
    fallback_enabled: bool = True
    cache_tiles: bool = True


class CameraSettings(BaseModel):
    enabled: bool = True
    resolution: str = "1280x720"  # WIDTHxHEIGHT
    framerate: int = 30
    quality: int = 80


class AISettings(BaseModel):
    obstacle_detection: bool = True
    path_optimization: bool = True
    learning_enabled: bool = False


class SystemSettings(BaseModel):
    log_level: str = "INFO"
    auto_updates: bool = False
    remote_access: bool = False
    branding_checksum: Optional[str] = None


class SettingsProfile(BaseModel):
    version: int = 1
    last_modified: datetime = Field(default_factory=datetime.now)
    hardware: HardwareSettings = Field(default_factory=HardwareSettings)
    network: NetworkSettings = Field(default_factory=NetworkSettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    control: ControlSettings = Field(default_factory=ControlSettings)
    maps: MapsSettings = Field(default_factory=MapsSettings)
    camera: CameraSettings = Field(default_factory=CameraSettings)
    ai: AISettings = Field(default_factory=AISettings)
    system: SystemSettings = Field(default_factory=SystemSettings)

    def bump_version(self):
        self.version += 1
        self.last_modified = datetime.now()

    def update_setting(self, path: str, value) -> bool:
        """Update nested setting using dotted path e.g. 'hardware.sim_mode'."""
        parts = path.split(".")
        if not parts:
            return False
        obj = self
        for p in parts[:-1]:
            if not hasattr(obj, p):
                return False
            obj = getattr(obj, p)
        leaf = parts[-1]
        if not hasattr(obj, leaf):
            return False
        setattr(obj, leaf, value)
        self.bump_version()
        return True

    def validate_settings(self) -> List[str]:
        """Basic validation aligned with unit tests expectations."""
        issues: List[str] = []
        # Camera resolution validation: expect WIDTHxHEIGHT format
        res = self.camera.resolution
        if isinstance(res, str):
            try:
                w_str, h_str = res.lower().split("x")
                w, h = int(w_str), int(h_str)
                if w <= 0 or h <= 0:
                    issues.append("Invalid camera resolution")
            except Exception:
                issues.append("Invalid camera resolution")
        else:
            issues.append("Invalid camera resolution")

        # System log level validation
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        try:
            level = str(self.system.log_level).upper()
            if level not in valid_levels:
                issues.append("Invalid log_level")
        except Exception:
            issues.append("Invalid log_level")
        return issues

    def compute_branding_checksum(self, required_assets: List[str]) -> str:
        import hashlib, os
        hasher = hashlib.sha256()
        for p in sorted(required_assets):
            if os.path.exists(p):
                with open(p, "rb") as f:
                    hasher.update(f.read())
        checksum = hasher.hexdigest()
        self.system.branding_checksum = checksum
        return checksum

    def validate_branding_assets(self, required_assets: List[str]) -> bool:
        import os
        return all(os.path.exists(p) for p in required_assets)
