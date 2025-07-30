#!/usr/bin/env python3
"""
Environment Setup Script
Generates .env files and validates API keys for LawnBerry Pi
"""

import os
import sys
import secrets
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional, Tuple
import requests
from urllib.parse import urlparse


class EnvironmentSetup:
    """Handles environment variable setup and validation"""
    
    def __init__(self):
        self.env_file = Path('.env')
        self.env_example = Path('.env.example')
        self.required_vars = {
            'OPENWEATHER_API_KEY': {
                'description': 'OpenWeather API key for weather data',
                'url': 'https://openweathermap.org/api',
                'validation': self._validate_openweather_key,
                'required': True
            },
            'REACT_APP_GOOGLE_MAPS_API_KEY': {
                'description': 'Google Maps API key for web UI',
                'url': 'https://console.cloud.google.com/apis/credentials',
                'validation': self._validate_google_maps_key,
                'required': True
            },
            'JWT_SECRET_KEY': {
                'description': 'JWT secret for web authentication',
                'url': None,
                'validation': self._validate_jwt_secret,
                'required': True,
                'auto_generate': True
            },
            'LAWNBERRY_FLEET_API_KEY': {
                'description': 'Fleet management API key (optional)',
                'url': 'Contact LawnBerry support',
                'validation': None,
                'required': False
            },
            'REDIS_PASSWORD': {
                'description': 'Redis database password (optional)',
                'url': None,
                'validation': None,
                'required': False,
                'auto_generate': True
            },
            'MQTT_USERNAME': {
                'description': 'MQTT username (optional)',
                'url': None,
                'validation': None,
                'required': False
            },
            'MQTT_PASSWORD': {
                'description': 'MQTT password (optional)',
                'url': None,
                'validation': None,
                'required': False,
                'auto_generate': True
            }
        }
    
    def run_setup(self, interactive: bool = True) -> bool:
        """Run the complete environment setup process"""
        print("="*60)
        print("       LAWNBERRY PI ENVIRONMENT SETUP")
        print("="*60)
        
        # Check if .env already exists
        if self.env_file.exists():
            if interactive:
                response = input(f"\n{self.env_file} already exists. Overwrite? (y/N): ")
                if response.lower() != 'y':
                    print("Setup cancelled.")
                    return False
            else:
                print(f"Backing up existing {self.env_file}")
                self.env_file.rename(f"{self.env_file}.backup")
        
        # Load example file if it exists
        example_vars = self._load_example_file()
        
        # Collect environment variables
        env_vars = {}
        
        if interactive:
            env_vars = self._interactive_setup()
        else:
            env_vars = self._non_interactive_setup()
        
        # Write .env file
        success = self._write_env_file(env_vars)
        
        if success:
            # Set file permissions (readable only by owner)
            os.chmod(self.env_file, 0o600)
            
            print(f"\n✓ Environment file created: {self.env_file}")
            print(f"✓ File permissions set to 600 (owner read/write only)")
            
            # Validate all keys
            self._validate_all_keys(env_vars)
            
            print("\n" + "="*60)
            print("Environment setup complete!")
            print("="*60)
            return True
        else:
            print("\n✗ Failed to create environment file")
            return False
    
    def _load_example_file(self) -> Dict[str, str]:
        """Load variables from .env.example file"""
        example_vars = {}
        
        if not self.env_example.exists():
            print(f"Warning: {self.env_example} not found")
            return example_vars
        
        try:
            with open(self.env_example, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        example_vars[key] = value
        except Exception as e:
            print(f"Error reading {self.env_example}: {e}")
        
        return example_vars
    
    def _interactive_setup(self) -> Dict[str, str]:
        """Interactive setup process"""
        env_vars = {}
        
        print("\nThis setup will guide you through configuring environment variables.")
        print("Required variables must be provided. Optional variables can be skipped.\n")
        
        for var_name, var_info in self.required_vars.items():
            print(f"\n{'-'*50}")
            print(f"Setting up: {var_name}")
            print(f"Description: {var_info['description']}")
            
            if var_info.get('url'):
                print(f"Get your key from: {var_info['url']}")
            
            required = var_info['required']
            can_generate = var_info.get('auto_generate', False)
            
            if can_generate and var_name == 'JWT_SECRET_KEY':
                response = input(f"\nAuto-generate secure {var_name}? (Y/n): ")
                if response.lower() != 'n':
                    env_vars[var_name] = secrets.token_hex(32)
                    print(f"✓ Generated secure {var_name}")
                    continue
            
            if can_generate and var_name in ['REDIS_PASSWORD', 'MQTT_PASSWORD']:
                response = input(f"\nAuto-generate {var_name}? (y/N): ")
                if response.lower() == 'y':
                    env_vars[var_name] = secrets.token_urlsafe(16)
                    print(f"✓ Generated {var_name}")
                    continue
            
            # Get user input
            while True:
                prompt = f"\nEnter {var_name}"
                if not required:
                    prompt += " (optional, press Enter to skip)"
                prompt += ": "
                
                value = input(prompt).strip()
                
                if not value and not required:
                    print(f"Skipping optional {var_name}")
                    break
                
                if not value and required:
                    print(f"✗ {var_name} is required")
                    continue
                
                # Validate if validation function exists
                if var_info.get('validation'):
                    valid, message = var_info['validation'](value)
                    if not valid:
                        print(f"✗ Invalid {var_name}: {message}")
                        continue
                    else:
                        print(f"✓ {var_name} validated successfully")
                
                env_vars[var_name] = value
                break
        
        return env_vars
    
    def _non_interactive_setup(self) -> Dict[str, str]:
        """Non-interactive setup using environment or defaults"""
        env_vars = {}
        
        print("\nRunning non-interactive setup...")
        
        for var_name, var_info in self.required_vars.items():
            # Check if already set in environment
            value = os.environ.get(var_name)
            
            if value:
                env_vars[var_name] = value
                print(f"✓ Using existing {var_name} from environment")
                continue
            
            # Auto-generate if possible
            if var_info.get('auto_generate'):
                if var_name == 'JWT_SECRET_KEY':
                    env_vars[var_name] = secrets.token_hex(32)
                    print(f"✓ Generated {var_name}")
                elif var_name in ['REDIS_PASSWORD', 'MQTT_PASSWORD']:
                    env_vars[var_name] = secrets.token_urlsafe(16)
                    print(f"✓ Generated {var_name}")
                continue
            
            # Required but not available
            if var_info['required']:
                print(f"✗ Required {var_name} not found in environment")
                print(f"  Set with: export {var_name}=your_value")
                if var_info.get('url'):
                    print(f"  Get your key from: {var_info['url']}")
        
        return env_vars
    
    def _write_env_file(self, env_vars: Dict[str, str]) -> bool:
        """Write environment variables to .env file"""
        try:
            with open(self.env_file, 'w') as f:
                f.write("# LawnBerry Pi Environment Variables\n")
                f.write("# Generated by setup_environment.py\n")
                f.write(f"# Created: {os.popen('date').read().strip()}\n\n")
                
                f.write("# =============================================================================\n")
                f.write("# SENSITIVE DATA (Required - No config file fallback)\n")
                f.write("# =============================================================================\n\n")
                
                # Write required sensitive variables
                sensitive_vars = ['OPENWEATHER_API_KEY', 'REACT_APP_GOOGLE_MAPS_API_KEY', 
                                'JWT_SECRET_KEY', 'LAWNBERRY_FLEET_API_KEY']
                
                for var_name in sensitive_vars:
                    if var_name in env_vars:
                        f.write(f"{var_name}={env_vars[var_name]}\n")
                
                f.write("\n# =============================================================================\n")
                f.write("# OPTIONAL CONFIGURATION\n")
                f.write("# =============================================================================\n\n")
                
                # Write optional variables
                optional_vars = ['REDIS_PASSWORD', 'MQTT_USERNAME', 'MQTT_PASSWORD']
                
                for var_name in optional_vars:
                    if var_name in env_vars:
                        f.write(f"{var_name}={env_vars[var_name]}\n")
                
                f.write("\n# Add any additional environment variables below this line\n")
            
            return True
            
        except Exception as e:
            print(f"Error writing {self.env_file}: {e}")
            return False
    
    def _validate_openweather_key(self, api_key: str) -> Tuple[bool, str]:
        """Validate OpenWeather API key"""
        if not api_key or len(api_key) < 10:
            return False, "API key too short"
        
        # Test API key with a simple request
        try:
            url = f"https://api.openweathermap.org/data/2.5/weather"
            params = {
                'q': 'London',
                'appid': api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                return True, "API key validated successfully"
            elif response.status_code == 401:
                return False, "Invalid API key"
            else:
                return False, f"API validation failed: HTTP {response.status_code}"
                
        except requests.RequestException as e:
            return False, f"Network error during validation: {str(e)}"
    
    def _validate_google_maps_key(self, api_key: str) -> Tuple[bool, str]:
        """Validate Google Maps API key"""
        if not api_key or len(api_key) < 10:
            return False, "API key too short"
        
        # Basic format check - Google API keys start with AIza
        if not api_key.startswith('AIza'):
            return False, "Google API keys typically start with 'AIza'"
        
        # Test with a simple geocoding request
        try:
            url = "https://maps.googleapis.com/maps/api/geocode/json"
            params = {
                'address': 'New York',
                'key': api_key
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'OK':
                    return True, "API key validated successfully"
                elif data.get('status') == 'REQUEST_DENIED':
                    return False, "API key denied - check restrictions"
                else:
                    return False, f"API error: {data.get('status')}"
            else:
                return False, f"HTTP error: {response.status_code}"
                
        except requests.RequestException as e:
            return False, f"Network error during validation: {str(e)}"
    
    def _validate_jwt_secret(self, secret: str) -> Tuple[bool, str]:
        """Validate JWT secret key"""
        if not secret:
            return False, "JWT secret cannot be empty"
        
        if len(secret) < 32:
            return False, "JWT secret should be at least 32 characters"
        
        # Check for basic randomness (no repeated patterns)
        if len(set(secret)) < 10:
            return False, "JWT secret appears to lack randomness"
        
        return True, "JWT secret validated"
    
    def _validate_all_keys(self, env_vars: Dict[str, str]):
        """Validate all API keys after setup"""
        print(f"\n{'-'*50}")
        print("Validating API keys...")
        print(f"{'-'*50}")
        
        for var_name, value in env_vars.items():
            var_info = self.required_vars.get(var_name, {})
            validation_func = var_info.get('validation')
            
            if validation_func:
                print(f"\nValidating {var_name}...")
                try:
                    valid, message = validation_func(value)
                    if valid:
                        print(f"✓ {var_name}: {message}")
                    else:
                        print(f"✗ {var_name}: {message}")
                except Exception as e:
                    print(f"✗ {var_name}: Validation error - {e}")
    
    def check_existing_env(self) -> bool:
        """Check if .env file exists and validate it"""
        if not self.env_file.exists():
            print(f"{self.env_file} not found")
            return False
        
        print(f"Checking existing {self.env_file}...")
        
        # Load existing variables
        env_vars = {}
        try:
            with open(self.env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key] = value
        except Exception as e:
            print(f"Error reading {self.env_file}: {e}")
            return False
        
        # Check required variables
        missing_vars = []
        for var_name, var_info in self.required_vars.items():
            if var_info['required'] and var_name not in env_vars:
                missing_vars.append(var_name)
        
        if missing_vars:
            print(f"✗ Missing required variables: {', '.join(missing_vars)}")
            return False
        
        print(f"✓ All required environment variables present")
        
        # Validate keys
        self._validate_all_keys(env_vars)
        
        return True


def main():
    """Main setup function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='LawnBerry Pi Environment Setup')
    parser.add_argument('--non-interactive', action='store_true',
                       help='Run in non-interactive mode')
    parser.add_argument('--check', action='store_true',
                       help='Check existing .env file')
    
    args = parser.parse_args()
    
    setup = EnvironmentSetup()
    
    if args.check:
        return setup.check_existing_env()
    else:
        return setup.run_setup(interactive=not args.non_interactive)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
