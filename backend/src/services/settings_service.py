"""Settings service for managing system configuration profiles"""

import logging
import json
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from pathlib import Path

from ..models.system_configuration import SettingsProfile
from ..core.persistence import PersistenceLayer

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for managing settings profiles and configuration persistence"""
    
    def __init__(self, persistence: PersistenceLayer, config_dir: Path = Path("/home/pi/lawnberry/config")):
        self.persistence = persistence
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._current_profile: Optional[SettingsProfile] = None
    
    def load_profile(self, profile_id: str = "default") -> SettingsProfile:
        """Load settings profile from persistence"""
        # Try loading from SQLite first
        config_data = self.persistence.load_system_config()
        
        if config_data and config_data.get("profile_id") == profile_id:
            profile = SettingsProfile.parse_obj(config_data)
            logger.info(f"Loaded settings profile {profile_id} from database")
            self._current_profile = profile
            return profile
        
        # Fall back to config files
        config_file = self.config_dir / f"{profile_id}.json"
        if config_file.exists():
            with open(config_file, 'r') as f:
                data = json.load(f)
            profile = SettingsProfile.parse_obj(data)
            logger.info(f"Loaded settings profile {profile_id} from config file")
            self._current_profile = profile
            return profile
        
        # Create default profile
        logger.info(f"Creating default settings profile {profile_id}")
        profile = SettingsProfile.create_default_profile()
        profile.profile_id = profile_id
        self._current_profile = profile
        return profile
    
    def save_profile(self, profile: SettingsProfile, persist_to_db: bool = True, persist_to_file: bool = True) -> None:
        """Save settings profile to persistence layer"""
        profile.updated_at = datetime.now(timezone.utc)
        
        # Save to SQLite
        if persist_to_db:
            try:
                self.persistence.save_system_config(profile.dict())
                profile.persisted_to_sqlite = True
                profile.sqlite_last_sync = datetime.now(timezone.utc)
                logger.info(f"Saved profile {profile.profile_id} to database")
            except Exception as e:
                logger.error(f"Failed to save profile to database: {e}")
        
        # Save to config file
        if persist_to_file:
            try:
                config_file = self.config_dir / f"{profile.profile_id}.json"
                with open(config_file, 'w') as f:
                    json.dump(profile.dict(), f, indent=2, default=str)
                profile.persisted_to_config_files = True
                profile.config_files_last_sync = datetime.now(timezone.utc)
                logger.info(f"Saved profile {profile.profile_id} to config file")
            except Exception as e:
                logger.error(f"Failed to save profile to config file: {e}")
        
        self._current_profile = profile
    
    def update_setting(self, profile_id: str, category: str, key: str, value: Any, bump_type: str = "patch") -> SettingsProfile:
        """Update a single setting in the profile"""
        profile = self.load_profile(profile_id)
        
        if not profile.update_setting(category, key, value):
            raise ValueError(f"Failed to update setting: {category}.{key}")
        
        profile.bump_version(bump_type)
        self.save_profile(profile)
        
        return profile
    
    def validate_profile(self, profile: SettingsProfile) -> Dict[str, Any]:
        """Validate settings profile and return validation report"""
        issues = profile.validate_settings()
        
        # Check for required branding assets
        required_assets = [
            str(self.config_dir.parent / "branding" / "LawnBerryPi_logo.png"),
            str(self.config_dir.parent / "branding" / "LawnBerryPi_icon2.png"),
            str(self.config_dir.parent / "branding" / "LawnBerryPi_Pin.png"),
        ]
        
        branding_valid = profile.validate_branding_assets(required_assets)
        if not branding_valid:
            issues.append("Missing required branding assets")
        
        # Compute branding checksum
        if branding_valid:
            profile.compute_branding_checksum(required_assets)
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "branding_checksum": profile.branding_checksum,
            "branding_assets_present": profile.branding_assets_present,
            "profile_version": profile.profile_version
        }
    
    def get_current_profile(self) -> Optional[SettingsProfile]:
        """Get currently loaded profile"""
        return self._current_profile
    
    def check_version_conflict(self, profile_id: str, expected_version: str) -> bool:
        """Check if profile version matches expected version"""
        profile = self.load_profile(profile_id)
        return profile.profile_version == expected_version
    
    def export_profile(self, profile_id: str, export_path: Path) -> None:
        """Export profile to a file for backup or migration"""
        profile = self.load_profile(profile_id)
        
        with open(export_path, 'w') as f:
            json.dump(profile.dict(), f, indent=2, default=str)
        
        logger.info(f"Exported profile {profile_id} to {export_path}")
    
    def import_profile(self, import_path: Path, profile_id: Optional[str] = None) -> SettingsProfile:
        """Import profile from a file"""
        with open(import_path, 'r') as f:
            data = json.load(f)
        
        profile = SettingsProfile.parse_obj(data)
        
        if profile_id:
            profile.profile_id = profile_id
        
        self.save_profile(profile)
        logger.info(f"Imported profile {profile.profile_id} from {import_path}")
        
        return profile


# Global instance
_settings_service: Optional[SettingsService] = None


def get_settings_service(persistence: Optional[PersistenceLayer] = None) -> SettingsService:
    """Get or create global settings service instance"""
    global _settings_service
    
    if _settings_service is None:
        if persistence is None:
            from ..core.persistence import PersistenceLayer
            persistence = PersistenceLayer()
        _settings_service = SettingsService(persistence)
    
    return _settings_service
