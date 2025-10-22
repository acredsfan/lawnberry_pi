"""Unit tests for SettingsService."""

import json
from datetime import datetime
from unittest.mock import patch

import pytest

from backend.src.models.settings import (
    AISettings,
    CameraSettings,
    ControlSettings,
    HardwareSettings,
    MapsSettings,
    NetworkSettings,
    SettingsProfile,
    SystemSettings,
    TelemetrySettings,
)
from backend.src.services.settings_service import SettingsService


@pytest.fixture
def mock_persistence():
    """Mock persistence layer."""
    with patch("backend.src.services.settings_service.persistence") as mock:
        yield mock


@pytest.fixture
def mock_branding_config():
    """Mock branding config."""
    return {
        "project_name": "lawnberry",
        "tagline": "Autonomous Lawn Care",
        "colors": {"primary": "#4CAF50", "secondary": "#8BC34A"},
        "logo_checksum": "abc123",
    }


@pytest.fixture
def sample_profile():
    """Create a sample settings profile."""
    return SettingsProfile(
        version=1,
        last_modified=datetime.now(),
        hardware=HardwareSettings(sim_mode=False, robohat_port="/dev/ttyACM0"),
        network=NetworkSettings(
            wifi_ssid="TestNetwork",
            wifi_password="password",
            ap_enabled=False,
            ap_ssid="LawnBerry-AP",
        ),
        telemetry=TelemetrySettings(
            stream_enabled=True, persist_enabled=True, retention_days=30
        ),
        control=ControlSettings(
            lockout_enabled=True, lockout_timeout=30, blade_safety=True
        ),
        maps=MapsSettings(
            provider="leaflet",
            api_key=None,
            fallback_enabled=True,
            cache_tiles=True,
        ),
        camera=CameraSettings(
            enabled=True, resolution="1280x720", framerate=30, quality=80
        ),
        ai=AISettings(
            obstacle_detection=True,
            path_optimization=True,
            learning_enabled=False,
        ),
        system=SystemSettings(
            log_level="INFO",
            auto_updates=False,
            remote_access=False,
            branding_checksum="abc123",
        ),
    )


class TestSettingsService:
    """Test suite for SettingsService."""

    def test_load_profile_from_db(self, mock_persistence, sample_profile):
        """Test loading profile from database."""
        mock_persistence.load_settings_profile.return_value = sample_profile.model_dump()
        service = SettingsService()
        
        profile = service.load_profile()
        
        assert profile.version == 1
        assert profile.hardware.sim_mode is False
        assert profile.network.wifi_ssid == "TestNetwork"
        mock_persistence.load_settings_profile.assert_called_once()

    def test_load_profile_from_json_fallback(self, mock_persistence):
        """Test loading profile from JSON when DB fails."""
        mock_persistence.load_settings_profile.return_value = None
        
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text") as mock_read,
        ):
            fallback_payload = {
                "version": 1,
                "last_modified": datetime.now().isoformat(),
                "hardware": {
                    "sim_mode": True,
                    "robohat_port": "/dev/ttyACM0",
                },
                "network": {
                    "wifi_ssid": "Fallback",
                    "wifi_password": "pass",
                },
                "telemetry": {
                    "stream_enabled": True,
                    "persist_enabled": True,
                    "retention_days": 30,
                },
                "control": {
                    "lockout_enabled": True,
                    "lockout_timeout": 30,
                    "blade_safety": True,
                },
                "maps": {
                    "provider": "leaflet",
                    "fallback_enabled": True,
                    "cache_tiles": True,
                },
                "camera": {
                    "enabled": True,
                    "resolution": "1280x720",
                    "framerate": 30,
                    "quality": 80,
                },
                "ai": {
                    "obstacle_detection": True,
                    "path_optimization": True,
                    "learning_enabled": False,
                },
                "system": {
                    "log_level": "INFO",
                    "auto_updates": False,
                    "remote_access": False,
                    "branding_checksum": "abc123",
                },
            }
            mock_read.return_value = json.dumps(fallback_payload)
            
            service = SettingsService()
            profile = service.load_profile()
            
            assert profile.hardware.sim_mode is True
            assert profile.network.wifi_ssid == "Fallback"

    def test_load_profile_creates_default(self, mock_persistence):
        """Test creating default profile when none exists."""
        mock_persistence.load_settings_profile.return_value = None
        
        with patch("pathlib.Path.exists", return_value=False):
            service = SettingsService()
            profile = service.load_profile()
            
            assert profile.version == 1
            assert profile.hardware.sim_mode is False
            assert profile.system.log_level == "INFO"

    def test_save_profile_dual_persistence(self, mock_persistence, sample_profile):
        """Test profile is saved to both DB and JSON."""
        service = SettingsService()
        
        with patch("pathlib.Path.write_text") as mock_write:
            service.save_profile(sample_profile)
            
            mock_persistence.save_settings_profile.assert_called_once()
            mock_write.assert_called_once()

    def test_update_setting_success(self, mock_persistence, sample_profile):
        """Test updating a specific setting."""
        mock_persistence.load_settings_profile.return_value = sample_profile.model_dump()
        service = SettingsService()
        
        with patch.object(service, "save_profile") as mock_save:
            service.update_setting("hardware.sim_mode", True)
            
            mock_save.assert_called_once()
            saved_profile = mock_save.call_args[0][0]
            assert saved_profile.hardware.sim_mode is True

    def test_update_setting_invalid_path(self, mock_persistence, sample_profile):
        """Test updating with invalid setting path."""
        mock_persistence.load_settings_profile.return_value = sample_profile.model_dump()
        service = SettingsService()
        
        with pytest.raises(ValueError, match="Invalid setting path"):
            service.update_setting("invalid.path.to.setting", True)

    def test_validate_profile_success(self, sample_profile, mock_branding_config):
        """Test successful profile validation."""
        service = SettingsService()
        
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("json.loads", return_value=mock_branding_config),
        ):
            errors = service.validate_profile(sample_profile)
            
            assert len(errors) == 0

    def test_validate_profile_branding_mismatch(self, sample_profile):
        """Test validation fails with branding checksum mismatch."""
        sample_profile.system.branding_checksum = "wrong_checksum"
        service = SettingsService()
        
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("json.loads", return_value={"logo_checksum": "correct_checksum"}),
        ):
            errors = service.validate_profile(sample_profile)
            
            assert len(errors) > 0
            assert any("branding" in err.lower() for err in errors)

    def test_validate_profile_invalid_resolution(self, sample_profile):
        """Test validation fails with invalid camera resolution."""
        sample_profile.camera.resolution = "invalid"
        service = SettingsService()
        
        errors = service.validate_profile(sample_profile)
        
        assert len(errors) > 0
        assert any("resolution" in err.lower() for err in errors)

    def test_validate_profile_invalid_log_level(self, sample_profile):
        """Test validation fails with invalid log level."""
        sample_profile.system.log_level = "INVALID"
        service = SettingsService()
        
        errors = service.validate_profile(sample_profile)
        
        assert len(errors) > 0
        assert any("log_level" in err.lower() for err in errors)

    def test_check_version_conflict_no_conflict(self, mock_persistence):
        """Test no conflict when client version matches."""
        mock_persistence.load_settings_profile.return_value = {"version": 5}
        service = SettingsService()
        
        has_conflict = service.check_version_conflict(5)
        
        assert has_conflict is False

    def test_check_version_conflict_exists(self, mock_persistence):
        """Test conflict detected when versions differ."""
        mock_persistence.load_settings_profile.return_value = {"version": 10}
        service = SettingsService()
        
        has_conflict = service.check_version_conflict(5)
        
        assert has_conflict is True

    def test_check_version_conflict_no_db_profile(self, mock_persistence):
        """Test no conflict when no DB profile exists."""
        mock_persistence.load_settings_profile.return_value = None
        service = SettingsService()
        
        has_conflict = service.check_version_conflict(1)
        
        assert has_conflict is False

    def test_profile_version_increments_on_save(self, mock_persistence, sample_profile):
        """Test profile version increments on each save."""
        service = SettingsService()
        initial_version = sample_profile.version
        
        with patch("pathlib.Path.write_text"):
            service.save_profile(sample_profile)
            
            saved_data = mock_persistence.save_settings_profile.call_args[0][0]
            # Version should increment
            assert saved_data["version"] > initial_version

    def test_concurrent_save_detection(self, mock_persistence, sample_profile):
        """Test detecting concurrent modifications."""
        mock_persistence.load_settings_profile.return_value = sample_profile.model_dump()
        service = SettingsService()
        
        # Simulate another process updating the profile
        sample_profile.version = 1
        mock_persistence.load_settings_profile.return_value = {"version": 5}
        
        has_conflict = service.check_version_conflict(sample_profile.version)
        assert has_conflict is True
