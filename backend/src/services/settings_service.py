"""Settings service for managing system configuration profiles

This module aligns APIs with unit tests under tests/unit/test_settings_service.py,
using lightweight compatibility models in backend.src.models.settings and exposing
module-level `persistence` for easy patching in tests.
"""

import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from pathlib import Path

from ..models.settings import SettingsProfile
from ..core.persistence import persistence as persistence  # module-level symbol for tests to patch

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for managing settings profiles and configuration persistence"""
    
    def __init__(self, persistence=None, config_dir: Path = Path("/home/pi/lawnberry/config")):
        # Default to module-level persistence if not provided (tests patch this symbol)
        self.persistence = persistence if persistence is not None else globals().get("persistence")
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._current_profile: Optional[SettingsProfile] = None
    
    def load_profile(self, profile_id: str = "default") -> SettingsProfile:
        """Load settings profile from persistence"""
        # Try a dedicated settings profile loader if available
        config_data: Optional[Dict[str, Any]] = None
        loader = getattr(self.persistence, "load_settings_profile", None)
        if callable(loader):
            try:
                data = loader()
                if isinstance(data, dict):
                    config_data = data
            except Exception:
                config_data = None
        # Fallback to system config structure
        if config_data is None:
            sys_loader = getattr(self.persistence, "load_system_config", None)
            if callable(sys_loader):
                try:
                    data = sys_loader()
                    if isinstance(data, dict):
                        config_data = data
                except Exception:
                    config_data = None

        if config_data:
            profile = SettingsProfile.model_validate(config_data)
            logger.info(f"Loaded settings profile {profile_id} from database")
            self._current_profile = profile
            return profile
        
        # Fall back to config files
        config_file = self.config_dir / f"{profile_id}.json"
        if config_file.exists():
            data = json.loads(config_file.read_text())
            profile = SettingsProfile.model_validate(data)
            logger.info(f"Loaded settings profile {profile_id} from config file")
            self._current_profile = profile
            return profile
        
        # Create default profile
        logger.info(f"Creating default settings profile {profile_id}")
        profile = SettingsProfile()
        self._current_profile = profile
        return profile
    
    def save_profile(self, profile: SettingsProfile, persist_to_db: bool = True, persist_to_file: bool = True) -> None:
        """Save settings profile to persistence layer"""
        # Increment version and update timestamp per unit test expectations
        try:
            profile.version = int(getattr(profile, "version", 1)) + 1
        except Exception:
            profile.version = 2
        profile.last_modified = datetime.now(timezone.utc)
        
        # Save to SQLite
        if persist_to_db and hasattr(self.persistence, "save_settings_profile"):
            try:
                self.persistence.save_settings_profile(profile.model_dump())
                logger.info(f"Saved profile to database")
            except Exception as e:
                logger.error(f"Failed to save profile to database: {e}")
        
        # Save to config file
        if persist_to_file:
            try:
                config_file = self.config_dir / f"{profile_id if (profile_id := 'default') else 'default'}.json"
                config_file.write_text(json.dumps(profile.model_dump(), indent=2, default=str))
                logger.info("Saved profile to config file")
            except Exception as e:
                logger.error(f"Failed to save profile to config file: {e}")
        
        self._current_profile = profile
    
    def update_setting(self, setting_path: str, value: Any) -> SettingsProfile:
        """Update a single setting in the profile"""
        profile = self.load_profile()
        if not profile.update_setting(setting_path, value):
            raise ValueError("Invalid setting path")
        self.save_profile(profile)
        return profile
    
    def validate_profile(self, profile: SettingsProfile) -> list[str]:
        """Validate settings profile and return list of error strings."""
        issues = profile.validate_settings()
        # Optional branding checksum validation using branding.json if present
        branding_file = self.config_dir.parent / "branding" / "branding.json"
        try:
            if branding_file.exists():
                try:
                    content = branding_file.read_text()
                except Exception:
                    content = "{}"
                data = json.loads(content) if content is not None else {}
                expected = data.get("logo_checksum")
                if expected and profile.system.branding_checksum and expected != profile.system.branding_checksum:
                    issues.append("Branding checksum mismatch")
        except Exception:
            # Non-fatal
            pass
        return issues
    
    def get_current_profile(self) -> Optional[SettingsProfile]:
        """Get currently loaded profile"""
        return self._current_profile
    
    def check_version_conflict(self, expected_version: int) -> bool:
        """Check if stored profile version conflicts with expected_version.
        Returns True when there is a conflict (versions differ)."""
        # Try quick check via persistence without full load
        db_profile = None
        if hasattr(self.persistence, "load_settings_profile"):
            try:
                db_profile = self.persistence.load_settings_profile()
            except Exception:
                db_profile = None
        if db_profile is not None:
            if isinstance(db_profile, dict) and "version" in db_profile:
                return int(db_profile.get("version", 0)) != int(expected_version)
            # If db_profile exists but has no version, treat as no conflict
            return False
        # No profile in DB -> no conflict
        return False
    
    def export_profile(self, profile_id: str, export_path: Path) -> None:
        """Export profile to a file for backup or migration"""
        profile = self.load_profile(profile_id)
        
        with open(export_path, 'w') as f:
            json.dump(profile.model_dump(), f, indent=2, default=str)
        
        logger.info(f"Exported profile {profile_id} to {export_path}")
    
    def import_profile(self, import_path: Path, profile_id: Optional[str] = None) -> SettingsProfile:
        """Import profile from a file"""
        with open(import_path, 'r') as f:
            data = json.load(f)
        
        profile = SettingsProfile.model_validate(data)
        
        if profile_id:
            profile.profile_id = profile_id
        
        self.save_profile(profile)
        logger.info(f"Imported profile {profile.profile_id} from {import_path}")
        
        return profile


# Back-compat helpers removed for tests; tests use SettingsService directly

# REST adapter and factory for compatibility with existing API layer
class _AdapterProfile:
    """Lightweight adapter to provide REST-layer expectations over SettingsProfile.

    - update_setting(category, key, value)
    - dict() alias to model_dump()
    - profile_version alias to version
    """

    def __init__(self, profile: SettingsProfile):
        self._p = profile

    # Attribute passthrough
    def __getattr__(self, name):
        if name == "profile_version":
            return getattr(self._p, "version", None)
        return getattr(self._p, name)

    def update_setting(self, category: str, key: str, value: Any) -> bool:
        path = f"{category}.{key}" if category else key
        return self._p.update_setting(path, value)

    def dict(self) -> Dict[str, Any]:  # FastAPI/rest layer compatibility
        return self._p.model_dump()

    def model_dump(self) -> Dict[str, Any]:
        return self._p.model_dump()


class _RestSettingsServiceAdapter:
    """Adapter exposing the interface expected by backend.src.api.rest.

    This wraps SettingsService while preserving unit-test semantics in this module.
    """

    def __init__(self, base: SettingsService):
        self._base = base

    def load_profile(self, profile_id: str = "default") -> _AdapterProfile:
        p = self._base.load_profile(profile_id)
        return _AdapterProfile(p)

    def save_profile(self, profile: Any) -> None:
        # Accept adapter or raw
        underlying = getattr(profile, "_p", profile)
        self._base.save_profile(underlying)

    def validate_profile(self, profile: Any) -> Dict[str, Any]:
        underlying = getattr(profile, "_p", profile)
        issues = self._base.validate_profile(underlying)
        return {"valid": len(issues) == 0, "issues": issues}

    def check_version_conflict(self, profile_id: str, expected_version: Any) -> bool:
        """Return True when versions match (no conflict), False when conflict.

        The REST layer uses `not check_version_conflict(...)` to signal 409.
        """
        try:
            exp = int(expected_version)
        except Exception:
            # If not parseable, consider it a conflict-safe path (let update proceed)
            return True
        # Base returns True when conflict exists; invert to match REST expectation
        has_conflict = self._base.check_version_conflict(exp)
        return not has_conflict


def get_settings_service(persist) -> _RestSettingsServiceAdapter:
    """Factory used by REST layer to obtain a settings service with expected API."""
    base = SettingsService(persistence=persist)
    return _RestSettingsServiceAdapter(base)
