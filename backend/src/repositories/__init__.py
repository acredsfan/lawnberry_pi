"""Typed repository layer for LawnBerry persistent data.

Each repository is the single owner of its domain's persisted fields.
Repositories are constructed at startup and stored on RuntimeContext.
Tests construct repositories against tmp_path databases; no real data/
directory is touched.
"""
from .base import BaseRepository

# Import repositories as they are implemented
try:
    from .calibration_repository import CalibrationRepository
except ImportError:
    CalibrationRepository = None  # type: ignore

try:
    from .map_repository import MapRepository
except ImportError:
    MapRepository = None  # type: ignore

try:
    from .mission_repository import MissionRepository
except ImportError:
    MissionRepository = None  # type: ignore

try:
    from .settings_repository import SettingsRepository
except ImportError:
    SettingsRepository = None  # type: ignore

try:
    from .telemetry_repository import TelemetryRepository
except ImportError:
    TelemetryRepository = None  # type: ignore

__all__ = [
    "BaseRepository",
    "CalibrationRepository",
    "MapRepository",
    "MissionRepository",
    "SettingsRepository",
    "TelemetryRepository",
]
