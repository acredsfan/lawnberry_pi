"""
Test suite for environment variable security implementation
Verifies that sensitive data is only loaded from environment variables
"""

import os
import pytest
from unittest.mock import patch, MagicMock
import tempfile
import yaml

from src.weather.weather_service import WeatherService
from src.system_integration.fleet_manager import FleetManager
from src.data_management.cache_manager import CacheManager


class TestEnvironmentSecurity:
    """Test environment variable security requirements"""
    
    def test_weather_service_requires_api_key_env(self):
        """Test that weather service fails without OPENWEATHER_API_KEY"""
        # Ensure env var is not set
        with patch.dict(os.environ, {}, clear=True):
            mock_mqtt = MagicMock()
            
            # Should raise ValueError when API key is missing
            with pytest.raises(ValueError, match="Missing required environment variable: OPENWEATHER_API_KEY"):
                WeatherService(mock_mqtt)
    
    def test_weather_service_succeeds_with_api_key_env(self):
        """Test that weather service works with OPENWEATHER_API_KEY set"""
        with patch.dict(os.environ, {'OPENWEATHER_API_KEY': 'test_key'}):
            mock_mqtt = MagicMock()
            
            # Should not raise exception
            service = WeatherService(mock_mqtt)
            assert service.api_key == 'test_key'
    
    def test_fleet_manager_requires_api_key_when_enabled(self):
        """Test that fleet manager fails when enabled without API key"""
        # Create a config with fleet enabled
        config_data = {
            'fleet': {
                'enabled': True,
                'server_url': 'https://test.com'
            }
        }
        
        mock_config_manager = MagicMock()
        mock_config_manager.get_config.return_value = config_data['fleet']
        
        # Ensure env var is not set
        with patch.dict(os.environ, {}, clear=True):
            # Should raise ValueError when fleet is enabled but API key is missing
            with pytest.raises(ValueError, match="Missing required environment variable: LAWNBERRY_FLEET_API_KEY"):
                FleetManager(mock_config_manager)
    
    def test_fleet_manager_succeeds_when_disabled(self):
        """Test that fleet manager works when disabled without API key"""
        config_data = {
            'fleet': {
                'enabled': False,
                'server_url': 'https://test.com'
            }
        }
        
        mock_config_manager = MagicMock()
        mock_config_manager.get_config.return_value = config_data['fleet']
        
        # Ensure env var is not set
        with patch.dict(os.environ, {}, clear=True):
            # Should not raise exception when fleet is disabled
            manager = FleetManager(mock_config_manager)
            assert manager.fleet_api_key is None
    
    def test_fleet_manager_succeeds_with_api_key_when_enabled(self):
        """Test that fleet manager works when enabled with API key"""
        config_data = {
            'fleet': {
                'enabled': True,
                'server_url': 'https://test.com'
            }
        }
        
        mock_config_manager = MagicMock()
        mock_config_manager.get_config.return_value = config_data['fleet']
        
        with patch.dict(os.environ, {'LAWNBERRY_FLEET_API_KEY': 'test_fleet_key'}):
            # Should not raise exception
            manager = FleetManager(mock_config_manager)
            assert manager.fleet_api_key == 'test_fleet_key'
    
    def test_cache_manager_uses_env_password(self):
        """Test that cache manager uses environment variable for Redis password"""
        with patch.dict(os.environ, {'REDIS_PASSWORD': 'test_redis_pass'}):
            cache_manager = CacheManager()
            assert cache_manager.redis_password == 'test_redis_pass'
    
    def test_cache_manager_no_password_when_env_not_set(self):
        """Test that cache manager has no password when env var not set"""
        with patch.dict(os.environ, {}, clear=True):
            cache_manager = CacheManager()
            assert cache_manager.redis_password is None
    
    def test_config_files_no_sensitive_data(self):
        """Test that config files don't contain sensitive data"""
        # Test weather.yaml
        with open('config/weather.yaml', 'r') as f:
            weather_config = yaml.safe_load(f)
        
        # Should not have api_key field
        assert 'api_key' not in weather_config
        
        # Test fleet.yaml
        with open('config/fleet.yaml', 'r') as f:
            fleet_config = yaml.safe_load(f)
        
        # Should not have api_key field in fleet section
        assert 'api_key' not in fleet_config.get('fleet', {})
        
        # Test data_management.yaml
        with open('config/data_management.yaml', 'r') as f:
            data_config = yaml.safe_load(f)
        
        # Should not have password field in redis section
        assert 'password' not in data_config.get('redis', {})
        
        # Test communication.yaml
        with open('config/communication.yaml', 'r') as f:
            comm_config = yaml.safe_load(f)
        
        # Should not have password in auth section
        mqtt_config = comm_config.get('mqtt', {})
        auth_config = mqtt_config.get('auth', {})
        assert 'password' not in auth_config
        
        # Should not have api_key in cloud_logging section
        cloud_logging = comm_config.get('logging', {}).get('cloud_logging', {})
        assert 'api_key' not in cloud_logging
    
    def test_gitignore_excludes_env_files(self):
        """Test that .gitignore properly excludes .env files"""
        with open('.gitignore', 'r') as f:
            gitignore_content = f.read()
        
        # Should exclude .env files
        assert '.env' in gitignore_content
        assert '.env.*' in gitignore_content
        assert '!.env.example' in gitignore_content
