#!/usr/bin/env python3
"""
Simple validation script for environment variable security implementation
"""

import os
import sys
import yaml
from pathlib import Path

def test_config_files_cleaned():
    """Test that config files don't contain sensitive data"""
    print("Testing config files for sensitive data removal...")
    
    issues = []
    
    # Test weather.yaml
    try:
        with open('config/weather.yaml', 'r') as f:
            weather_config = yaml.safe_load(f)
        
        if 'api_key' in weather_config:
            issues.append("weather.yaml still contains api_key field")
    except Exception as e:
        issues.append(f"Failed to read weather.yaml: {e}")
    
    # Test fleet.yaml
    try:
        with open('config/fleet.yaml', 'r') as f:
            fleet_config = yaml.safe_load(f)
        
        fleet_section = fleet_config.get('fleet', {})
        if 'api_key' in fleet_section:
            issues.append("fleet.yaml still contains api_key field")
    except Exception as e:
        issues.append(f"Failed to read fleet.yaml: {e}")
    
    # Test data_management.yaml
    try:
        with open('config/data_management.yaml', 'r') as f:
            data_config = yaml.safe_load(f)
        
        redis_section = data_config.get('redis', {})
        if 'password' in redis_section:
            issues.append("data_management.yaml still contains password field")
    except Exception as e:
        issues.append(f"Failed to read data_management.yaml: {e}")
    
    # Test communication.yaml
    try:
        with open('config/communication.yaml', 'r') as f:
            comm_config = yaml.safe_load(f)
        
        mqtt_config = comm_config.get('mqtt', {})
        auth_config = mqtt_config.get('auth', {})
        if 'password' in auth_config:
            issues.append("communication.yaml still contains password in auth section")
        
        cloud_logging = comm_config.get('logging', {}).get('cloud_logging', {})
        if 'api_key' in cloud_logging:
            issues.append("communication.yaml still contains api_key in cloud_logging section")
    except Exception as e:
        issues.append(f"Failed to read communication.yaml: {e}")
    
    return issues

def test_gitignore():
    """Test that .gitignore properly excludes .env files"""
    print("Testing .gitignore for .env file exclusion...")
    
    issues = []
    
    try:
        with open('.gitignore', 'r') as f:
            gitignore_content = f.read()
        
        required_patterns = ['.env', '.env.*', '!.env.example']
        for pattern in required_patterns:
            if pattern not in gitignore_content:
                issues.append(f".gitignore missing pattern: {pattern}")
    except Exception as e:
        issues.append(f"Failed to read .gitignore: {e}")
    
    return issues

def test_env_example():
    """Test that .env.example contains required variables"""
    print("Testing .env.example for required environment variables...")
    
    issues = []
    
    try:
        with open('.env.example', 'r') as f:
            env_content = f.read()
        
        required_vars = [
            'OPENWEATHER_API_KEY',
            'REACT_APP_GOOGLE_MAPS_API_KEY', 
            'LAWNBERRY_FLEET_API_KEY',
            'JWT_SECRET_KEY',
            'REDIS_PASSWORD',
            'MQTT_USERNAME',
            'MQTT_PASSWORD'
        ]
        
        for var in required_vars:
            if var not in env_content:
                issues.append(f".env.example missing variable: {var}")
    except Exception as e:
        issues.append(f"Failed to read .env.example: {e}")
    
    return issues

def test_weather_service_env_handling():
    """Test that weather service properly handles environment variables"""
    print("Testing weather service environment variable handling...")
    
    issues = []
    
    try:
        # Test without environment variable
        if 'OPENWEATHER_API_KEY' in os.environ:
            del os.environ['OPENWEATHER_API_KEY']
        
        # Import here to avoid issues if modules aren't available
        sys.path.insert(0, 'src')
        from unittest.mock import MagicMock
        
        try:
            from weather.weather_service import WeatherService
            mock_mqtt = MagicMock()
            
            # Should raise ValueError
            try:
                WeatherService(mock_mqtt)
                issues.append("WeatherService should raise ValueError when OPENWEATHER_API_KEY is missing")
            except ValueError as e:
                if "OPENWEATHER_API_KEY" not in str(e):
                    issues.append(f"WeatherService ValueError should mention OPENWEATHER_API_KEY: {e}")
            except Exception as e:
                issues.append(f"WeatherService raised unexpected exception: {e}")
        except ImportError as e:
            issues.append(f"Could not import WeatherService: {e}")
        
        # Test with environment variable
        os.environ['OPENWEATHER_API_KEY'] = 'test_key'
        try:
            from weather.weather_service import WeatherService
            mock_mqtt = MagicMock()
            service = WeatherService(mock_mqtt)
            if service.api_key != 'test_key':
                issues.append(f"WeatherService api_key should be 'test_key', got: {service.api_key}")
        except Exception as e:
            issues.append(f"WeatherService failed with valid API key: {e}")
        
    except Exception as e:
        issues.append(f"Error testing weather service: {e}")
    
    return issues

def main():
    """Run all validation tests"""
    print("=" * 60)
    print("Environment Variable Security Validation")
    print("=" * 60)
    
    all_issues = []
    
    # Run tests
    all_issues.extend(test_config_files_cleaned())
    all_issues.extend(test_gitignore())
    all_issues.extend(test_env_example())
    all_issues.extend(test_weather_service_env_handling())
    
    # Report results
    print("\n" + "=" * 60)
    print("VALIDATION RESULTS")
    print("=" * 60)
    
    if not all_issues:
        print("✅ ALL TESTS PASSED - Environment variable security is properly implemented!")
        return 0
    else:
        print("❌ ISSUES FOUND:")
        for i, issue in enumerate(all_issues, 1):
            print(f"  {i}. {issue}")
        return len(all_issues)

if __name__ == "__main__":
    sys.exit(main())
