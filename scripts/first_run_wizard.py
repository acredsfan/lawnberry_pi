#!/usr/bin/env python3
"""
First Run Wizard for LawnBerry Pi
Interactive setup wizard for first-time users
"""

import os
import sys
import json
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import time

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from hardware_detection import HardwareDetector
except ImportError:
    HardwareDetector = None

try:
    from setup_environment import EnvironmentSetup
except ImportError:
    EnvironmentSetup = None


class FirstRunWizard:
    """Interactive first-run setup wizard"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.wizard_data = {}
        self.hardware_results = {}
        
    def print_header(self):
        """Print wizard header"""
        print("\n" + "="*70)
        print("             🌱 WELCOME TO LAWNBERRY PI! 🌱")
        print("="*70)
        print("\nThank you for choosing LawnBerry Pi for your autonomous mowing needs!")
        print("This wizard will guide you through the initial setup process.")
        print("\nWhat we'll do together:")
        print("  1. 🔍 Detect your hardware configuration")
        print("  2. 🔑 Set up API keys and environment variables") 
        print("  3. 🗺️  Configure your location and yard boundaries")
        print("  4. ⏰ Set up mowing schedules")
        print("  5. 🛡️  Configure safety settings")
        print("  6. 🧪 Test your system")
        print("\nLet's get started!\n")
        
        input("Press Enter to continue...")
    
    def get_user_info(self) -> Dict[str, str]:
        """Collect basic user information"""
        print("\n" + "-"*50)
        print("Step 1: Basic Information")
        print("-"*50)
        
        user_info = {}
        
        print("\nLet's start with some basic information about your setup.")
        
        # System name
        default_name = "LawnBerry Pi"
        system_name = input(f"\nWhat would you like to call your system? [{default_name}]: ").strip()
        user_info['system_name'] = system_name if system_name else default_name
        
        # Location info
        print(f"\n🌍 Location Information")
        print("This helps with weather data and timezone settings.")
        
        location = input("Enter your city/location (e.g., 'Seattle, WA'): ").strip()
        user_info['location'] = location
        
        # Timezone
        try:
            # Try to detect timezone
            result = subprocess.run(['timedatectl', 'show', '--property=Timezone', '--value'], 
                                  capture_output=True, text=True)
            detected_tz = result.stdout.strip() if result.returncode == 0 else "UTC"
        except:
            detected_tz = "UTC"
        
        timezone = input(f"Timezone [{detected_tz}]: ").strip()
        user_info['timezone'] = timezone if timezone else detected_tz
        
        # Yard size estimate
        print(f"\n🏡 Yard Information")
        print("This helps optimize mowing patterns and battery usage.")
        
        yard_size = input("Approximate yard size in square meters (optional): ").strip()
        user_info['yard_size'] = yard_size if yard_size else "unknown"
        
        # Experience level
        print(f"\n🎯 Experience Level")
        print("This helps us customize the setup process for you.")
        print("1. Beginner - New to robotics/automation")
        print("2. Intermediate - Some experience with technical projects")  
        print("3. Advanced - Experienced with Raspberry Pi and hardware")
        
        while True:
            level = input("Select your experience level (1-3) [2]: ").strip()
            if not level:
                level = "2"
            if level in ["1", "2", "3"]:
                experience_levels = {"1": "beginner", "2": "intermediate", "3": "advanced"}
                user_info['experience_level'] = experience_levels[level]
                break
            print("Please enter 1, 2, or 3")
        
        print(f"\n✓ Great! Hello {user_info['system_name']} operator!")
        return user_info
    
    async def detect_hardware(self) -> Dict[str, Any]:
        """Run hardware detection with user-friendly output"""
        print("\n" + "-"*50)
        print("Step 2: Hardware Detection")
        print("-"*50)
        
        print("\n🔍 Let's see what hardware is connected to your Raspberry Pi...")
        print("This may take a minute while we scan for devices.\n")
        
        if not HardwareDetector:
            print("❌ Hardware detection module not available")
            print("Continuing with manual configuration...")
            return {}
        
        try:
            detector = HardwareDetector()
            
            # Show progress
            print("Scanning I2C bus for sensors...")
            time.sleep(1)
            print("Checking serial ports for GPS and controllers...")
            time.sleep(1)
            print("Testing camera connections...")
            time.sleep(1)
            print("Checking GPIO capabilities...")
            time.sleep(1)
            
            # Run detection
            results = await detector.detect_all_hardware()
            
            # Show results in user-friendly format
            self._display_hardware_results(results)
            
            # Run connectivity tests
            print("\n🧪 Testing hardware connectivity...")
            test_results = await detector.test_hardware_connectivity()
            self._display_test_results(test_results)
            
            self.hardware_results = {'detection': results, 'tests': test_results}
            
            # Ask if user wants to use detected configuration
            if results:
                print("\n" + "="*50)
                use_detected = input("Use detected hardware configuration? (Y/n): ").strip().lower()
                if use_detected != 'n':
                    config_yaml = detector.generate_hardware_config()
                    with open(self.project_root / 'config' / 'hardware.yaml', 'w') as f:
                        f.write(config_yaml)
                    print("✅ Hardware configuration saved!")
            
            return results
            
        except Exception as e:
            print(f"❌ Hardware detection failed: {e}")
            print("Don't worry! You can configure hardware manually later.")
            return {}
    
    def _display_hardware_results(self, results: Dict[str, Any]):
        """Display hardware detection results in user-friendly format"""
        print("\n🔍 Hardware Detection Results:")
        print("="*40)
        
        # System info
        system = results.get('system', {})
        if system:
            print(f"\n🖥️  System Information:")
            print(f"   Model: {system.get('pi_model', 'Unknown')}")
            print(f"   Memory: {system.get('memory_mb', 'Unknown')} MB")
            print(f"   OS: {system.get('os', 'Unknown')}")
        
        # I2C devices
        i2c = results.get('i2c_devices', {})
        found_count = i2c.get('found_count', 0)
        print(f"\n📡 I2C Sensors: {found_count} found")
        
        sensor_names = {
            'tof_left': 'Left Distance Sensor',
            'tof_right': 'Right Distance Sensor', 
            'power_monitor': 'Power Monitor',
            'environmental': 'Weather Sensor',
            'display': 'Display'
        }
        
        for device, info in i2c.items():
            if isinstance(info, dict) and 'present' in info:
                status = "✅" if info['present'] else "❌"
                name = sensor_names.get(device, device)
                print(f"   {status} {name}")
        
        # Serial devices  
        serial = results.get('serial_devices', {})
        found_count = serial.get('found_count', 0)
        print(f"\n🔌 Serial Devices: {found_count} found")
        
        device_names = {
            'gps': 'GPS Module',
            'robohat': 'Motor Controller',
            'imu': 'IMU Sensor'
        }
        
        for device, info in serial.items():
            if isinstance(info, dict) and 'present' in info:
                status = "✅" if info['present'] else "❌"
                name = device_names.get(device, device)
                print(f"   {status} {name}")
        
        # Camera
        camera = results.get('camera', {})
        if camera.get('present'):
            cam_type = camera.get('type', 'Unknown')
            print(f"\n📷 Camera: ✅ {cam_type.title()} detected")
        else:
            print(f"\n📷 Camera: ❌ Not detected")
        
        # GPIO
        gpio = results.get('gpio', {})
        if gpio.get('available'):
            print(f"\n🔧 GPIO: ✅ Available")
        else:
            print(f"\n🔧 GPIO: ❌ Not available")
    
    def _display_test_results(self, results: Dict[str, Any]):
        """Display connectivity test results"""
        print("\n🧪 Connectivity Test Results:")
        print("="*40)
        
        # I2C tests
        i2c_tests = results.get('i2c_tests', {})
        if not i2c_tests.get('error'):
            passed = sum(1 for t in i2c_tests.values() 
                        if isinstance(t, dict) and t.get('communication') == 'success')
            total = len([t for t in i2c_tests.values() if isinstance(t, dict)])
            print(f"📡 I2C Communication: {passed}/{total} devices responding")
        
        # Serial tests
        serial_tests = results.get('serial_tests', {})
        if not serial_tests.get('error'):
            passed = sum(1 for t in serial_tests.values()
                        if isinstance(t, dict) and t.get('communication') == 'success')
            total = len([t for t in serial_tests.values() if isinstance(t, dict)])
            print(f"🔌 Serial Communication: {passed}/{total} devices responding")
        
        # Camera test
        camera_tests = results.get('camera_tests', {})
        if camera_tests.get('capture') == 'success':
            print(f"📷 Camera: ✅ Capture test passed")
        else:
            print(f"📷 Camera: ❌ Capture test failed")
    
    def setup_environment_variables(self) -> bool:
        """Set up environment variables with wizard"""
        print("\n" + "-"*50)
        print("Step 3: API Keys & Environment Setup")
        print("-"*50)
        
        print("\n🔑 Now let's set up your API keys and environment variables.")
        print("These are needed for weather data, maps, and other cloud services.")
        
        if not EnvironmentSetup:
            print("❌ Environment setup module not available")
            return False
        
        # Check if .env already exists
        env_file = self.project_root / '.env'
        if env_file.exists():
            print(f"\n✅ Environment file already exists: {env_file}")
            response = input("Would you like to review/update it? (y/N): ").strip().lower()
            if response != 'y':
                return True
        
        # Provide Maps API guidance
        print("\n🗺️  Google Maps API Configuration")
        print("━" * 50)
        print("Google Maps API is OPTIONAL for enhanced mapping features.")
        print("If not configured, LawnBerryPi will use OpenStreetMap automatically.")
        print("\nBenefits of Google Maps:")
        print("  • High-quality satellite imagery")
        print("  • Advanced geocoding and address search")
        print("  • Enhanced location services")
        print("\nGoogle Maps requires:")
        print("  • Google Cloud account (free)")
        print("  • Billing account setup (free tier available)")
        print("  • API key configuration")
        print("\n📖 See docs/installation-guide.md for detailed setup instructions")
        
        maps_choice = input("\nDo you want to configure Google Maps API now? (y/N): ").strip().lower()
        
        try:
            setup = EnvironmentSetup()
            
            if maps_choice == 'y':
                print("\n🔧 Running full environment setup with Google Maps...")
                success = setup.run_setup(interactive=True)
            else:
                print("\n🔧 Running environment setup (Google Maps skipped)...")
                print("You can configure Google Maps later using: python3 scripts/setup_environment.py")
                success = setup.run_setup(interactive=True)
            
            if success:
                print("\n✅ Environment variables configured successfully!")
                if maps_choice != 'y':
                    print("🗺️  Using OpenStreetMap for mapping (Google Maps can be added later)")
            else:
                print("\n❌ Environment setup failed")
                print("You can run setup later with: python3 scripts/setup_environment.py")
            
            return success
            
        except Exception as e:
            print(f"\n❌ Environment setup error: {e}")
            return False
    
    def configure_location(self) -> Dict[str, Any]:
        """Configure GPS and location settings"""
        print("\n" + "-"*50)
        print("Step 4: Location Configuration")
        print("-"*50)
        
        location_config = {}
        
        print("\n🗺️  Let's configure your location settings.")
        print("This is important for GPS navigation and weather data.")
        
        # Check if GPS was detected
        gps_detected = False
        if self.hardware_results:
            serial_devices = self.hardware_results.get('detection', {}).get('serial_devices', {})
            gps_detected = serial_devices.get('gps', {}).get('present', False)
        
        if gps_detected:
            print("\n✅ GPS module detected!")
            print("Your system will use real-time GPS coordinates.")
            location_config['gps_available'] = True
        else:
            print("\n⚠️  No GPS module detected.")
            print("You'll need to configure fallback coordinates.")
            location_config['gps_available'] = False
        
        # Get fallback coordinates
        print(f"\n📍 Fallback Coordinates")
        print("These coordinates are used when GPS is unavailable.")
        print("You can find your coordinates using Google Maps or a GPS app.")
        
        while True:
            try:
                lat_input = input("Enter your latitude (e.g., 47.6062): ").strip()
                if lat_input:
                    latitude = float(lat_input)
                    if -90 <= latitude <= 90:
                        location_config['fallback_latitude'] = latitude
                        break
                    else:
                        print("Latitude must be between -90 and 90")
                else:
                    print("Latitude is required")
            except ValueError:
                print("Please enter a valid number")
        
        while True:
            try:
                lon_input = input("Enter your longitude (e.g., -122.3321): ").strip()
                if lon_input:
                    longitude = float(lon_input)
                    if -180 <= longitude <= 180:
                        location_config['fallback_longitude'] = longitude
                        break
                    else:
                        print("Longitude must be between -180 and 180")
                else:
                    print("Longitude is required")
            except ValueError:
                print("Please enter a valid number")
        
        print(f"\n✅ Location configured:")
        print(f"   Latitude: {location_config['fallback_latitude']}")
        print(f"   Longitude: {location_config['fallback_longitude']}")
        
        # Save location to config
        self._update_location_config(location_config)
        
        return location_config
    
    def _update_location_config(self, location_config: Dict[str, Any]):
        """Update location configuration file"""
        try:
            # Update location config file
            location_file = self.project_root / 'config' / 'location.yaml'
            
            config_content = f"""# Location Configuration
# Generated by first-run wizard

# GPS Configuration
gps:
  enabled: {str(location_config['gps_available']).lower()}
  fallback_coordinates:
    latitude: {location_config['fallback_latitude']}
    longitude: {location_config['fallback_longitude']}

# Coordinate System
coordinate_system:
  format: "decimal_degrees"
  datum: "WGS84"

# Update Intervals (seconds)
update_intervals:
  gps_reading: 1
  fallback_check: 60
  
logging_level: "INFO"
"""
            
            with open(location_file, 'w') as f:
                f.write(config_content)
            
            print(f"✅ Location configuration saved to: {location_file}")
            
        except Exception as e:
            print(f"⚠️  Failed to save location configuration: {e}")
    
    def configure_safety_settings(self) -> Dict[str, Any]:
        """Configure safety settings"""
        print("\n" + "-"*50)
        print("Step 5: Safety Configuration")
        print("-"*50)
        
        safety_config = {}
        
        print("\n🛡️  Safety is our top priority!")
        print("Let's configure important safety settings for your LawnBerry Pi.")
        
        # Emergency stop timeout
        print(f"\n⏱️  Emergency Stop Timeout")
        print("How long should the system wait for a response before emergency stop?")
        
        while True:
            try:
                timeout = input("Emergency stop timeout in seconds [30]: ").strip()
                if not timeout:
                    timeout = "30"
                timeout_val = int(timeout)
                if 10 <= timeout_val <= 120:
                    safety_config['emergency_timeout'] = timeout_val
                    break
                else:
                    print("Timeout must be between 10 and 120 seconds")
            except ValueError:
                print("Please enter a valid number")
        
        # Battery safety thresholds
        print(f"\n🔋 Battery Safety Thresholds")
        
        while True:
            try:
                low_battery = input("Low battery warning threshold % [20]: ").strip()
                if not low_battery:
                    low_battery = "20"
                low_val = int(low_battery)
                if 10 <= low_val <= 50:
                    safety_config['battery_low_threshold'] = low_val
                    break
                else:
                    print("Low battery threshold must be between 10% and 50%")
            except ValueError:
                print("Please enter a valid number")
        
        while True:
            try:
                critical_battery = input("Critical battery emergency stop % [10]: ").strip()
                if not critical_battery:
                    critical_battery = "10"
                crit_val = int(critical_battery)
                if 5 <= crit_val <= safety_config['battery_low_threshold']:
                    safety_config['battery_critical_threshold'] = crit_val
                    break
                else:
                    print(f"Critical threshold must be between 5% and {safety_config['battery_low_threshold']}%")
            except ValueError:
                print("Please enter a valid number")
        
        # Weather safety
        print(f"\n☔ Weather Safety")
        print("Should mowing stop in bad weather?")
        
        weather_stop = input("Stop mowing in rain/storms? (Y/n): ").strip().lower()
        safety_config['weather_safety'] = weather_stop != 'n'
        
        if safety_config['weather_safety']:
            while True:
                try:
                    wind_limit = input("Maximum wind speed for safe operation (m/s) [10]: ").strip()
                    if not wind_limit:
                        wind_limit = "10"
                    wind_val = float(wind_limit)
                    if 1 <= wind_val <= 25:
                        safety_config['max_wind_speed'] = wind_val
                        break
                    else:
                        print("Wind speed limit must be between 1 and 25 m/s")
                except ValueError:
                    print("Please enter a valid number")
        
        print(f"\n✅ Safety settings configured:")
        print(f"   Emergency timeout: {safety_config['emergency_timeout']} seconds")
        print(f"   Low battery warning: {safety_config['battery_low_threshold']}%")
        print(f"   Critical battery stop: {safety_config['battery_critical_threshold']}%")
        print(f"   Weather safety: {'Enabled' if safety_config['weather_safety'] else 'Disabled'}")
        
        # Save safety config
        self._update_safety_config(safety_config)
        
        return safety_config
    
    def _update_safety_config(self, safety_config: Dict[str, Any]):
        """Update safety configuration file"""
        try:
            safety_file = self.project_root / 'config' / 'safety.yaml'
            
            config_content = f"""# Safety Configuration
# Generated by first-run wizard

# Emergency Stop Configuration
emergency_stop:
  timeout_seconds: {safety_config['emergency_timeout']}
  require_acknowledgment: true

# Battery Safety
battery:
  low_threshold_percent: {safety_config['battery_low_threshold']}
  critical_threshold_percent: {safety_config['battery_critical_threshold']}
  auto_return_on_low: true
  emergency_stop_on_critical: true

# Weather Safety
weather:
  enabled: {str(safety_config['weather_safety']).lower()}
  max_wind_speed_ms: {safety_config.get('max_wind_speed', 10)}
  stop_on_rain: true
  stop_on_storm: true

# Sensor Safety
sensors:
  obstacle_detection: true
  tilt_protection: true
  lift_protection: true

# Operation Limits
limits:
  max_slope_degrees: 25
  max_operating_temperature: 40
  min_operating_temperature: 0

logging_level: "INFO"
"""
            
            with open(safety_file, 'w') as f:
                f.write(config_content)
            
            print(f"✅ Safety configuration saved to: {safety_file}")
            
        except Exception as e:
            print(f"⚠️  Failed to save safety configuration: {e}")
    
    def run_system_test(self) -> bool:
        """Run basic system tests"""
        print("\n" + "-"*50)
        print("Step 6: System Test")
        print("-"*50)
        
        print("\n🧪 Let's test your LawnBerry Pi system!")
        print("This will verify that everything is configured correctly.")
        
        test_results = {
            'environment': False,
            'database': False,
            'hardware': False,
            'services': False
        }
        
        # Test environment variables
        print(f"\n🔑 Testing environment variables...")
        env_file = self.project_root / '.env'
        if env_file.exists():
            print("   ✅ Environment file exists")
            test_results['environment'] = True
        else:
            print("   ❌ Environment file missing")
        
        # Test database
        print(f"\n💾 Testing database connection...")
        try:
            result = subprocess.run(
                [sys.executable, 'scripts/init_database.py', '--check-health'],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                print("   ✅ Database connection successful")
                test_results['database'] = True
            else:
                print("   ❌ Database connection failed")
                print(f"   Error: {result.stderr}")
        except Exception as e:
            print(f"   ❌ Database test error: {e}")
        
        # Test hardware (if detection was run)
        print(f"\n🔧 Testing hardware...")
        if self.hardware_results:
            detection_results = self.hardware_results.get('detection', {})
            if detection_results:
                print("   ✅ Hardware detection completed")
                test_results['hardware'] = True
            else:
                print("   ⚠️  Hardware detection incomplete")
        else:
            print("   ⚠️  Hardware detection not run")
        
        # Test services (check if they exist)
        print(f"\n⚙️  Testing service files...")
        service_files = [
            'src/system_integration/lawnberry-system.service',
            'src/hardware/lawnberry-hardware.service',
            'src/safety/lawnberry-safety.service'
        ]
        
        services_found = 0
        for service_file in service_files:
            if (self.project_root / service_file).exists():
                services_found += 1
        
        if services_found >= 2:
            print(f"   ✅ Service files available ({services_found}/{len(service_files)})")
            test_results['services'] = True
        else:
            print(f"   ⚠️  Limited service files ({services_found}/{len(service_files)})")
        
        # Overall result
        passed_tests = sum(test_results.values())
        total_tests = len(test_results)
        
        print(f"\n📊 Test Results: {passed_tests}/{total_tests} passed")
        
        if passed_tests >= 3:
            print("✅ System test PASSED! Your LawnBerry Pi is ready!")
            return True
        else:
            print("⚠️  System test completed with issues.")
            print("Your LawnBerry Pi may work, but some features might be limited.")
            return False
    
    def show_completion_summary(self):
        """Show setup completion summary"""
        print("\n" + "="*70)
        print("🎉 SETUP COMPLETE! WELCOME TO LAWNBERRY PI! 🎉")
        print("="*70)
        
        print(f"\nCongratulations! Your LawnBerry Pi setup is complete.")
        print(f"Here's what we accomplished together:")
        
        print(f"\n✅ System Configuration:")
        if 'system_name' in self.wizard_data:
            print(f"   • System Name: {self.wizard_data['system_name']}")
        if 'location' in self.wizard_data:
            print(f"   • Location: {self.wizard_data['location']}")
        
        print(f"\n✅ Hardware:")
        if self.hardware_results:
            detection = self.hardware_results.get('detection', {})
            i2c_count = detection.get('i2c_devices', {}).get('found_count', 0)
            serial_count = detection.get('serial_devices', {}).get('found_count', 0)
            camera = detection.get('camera', {}).get('present', False)
            print(f"   • I2C Sensors: {i2c_count} detected")
            print(f"   • Serial Devices: {serial_count} detected")
            print(f"   • Camera: {'Available' if camera else 'Not detected'}")
        
        print(f"\n✅ Configuration Files:")
        config_files = [
            'config/hardware.yaml',
            'config/location.yaml', 
            'config/safety.yaml',
            '.env'
        ]
        
        for config_file in config_files:
            if (self.project_root / config_file).exists():
                print(f"   • {config_file}: Configured")
        
        print(f"\n🚀 Next Steps:")
        print(f"   1. Review the user manual: docs/user-manual.md")
        print(f"   2. Set up yard boundaries using the web interface")
        print(f"   3. Create your first mowing schedule")
        print(f"   4. Run your first test mow!")
        
        print(f"\n🌐 Web Interface:")
        try:
            # Try to get IP address
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
            ip_address = result.stdout.strip().split()[0] if result.returncode == 0 else 'your-pi-ip'
            print(f"   • URL: http://{ip_address}:8000")
        except:
            print(f"   • URL: http://your-raspberry-pi-ip:8000")
        
        print(f"\n📚 Documentation:")
        print(f"   • Installation Guide: docs/installation-guide.md")
        print(f"   • User Manual: docs/user-manual.md")
        print(f"   • Troubleshooting: docs/troubleshooting-guide.md")
        
        print(f"\n💡 Helpful Commands:")
        print(f"   • Start system: lawnberry-system start")
        print(f"   • Check status: lawnberry-system status")
        print(f"   • View logs: lawnberry-system logs")
        print(f"   • Hardware info: lawnberry-system hardware")
        
        print(f"\n🆘 Need Help?")
        print(f"   • Check the troubleshooting guide")
        print(f"   • Review system logs")
        print(f"   • Visit the LawnBerry Pi community")
        
        print(f"\n" + "="*70)
        print("Thank you for choosing LawnBerry Pi!")
        print("Happy mowing! 🌱✂️🤖")
        print("="*70)
    
    async def run_wizard(self) -> bool:
        """Run the complete first-run wizard"""
        try:
            # Welcome and basic info
            self.print_header()
            self.wizard_data.update(self.get_user_info())
            
            # Hardware detection
            hardware_results = await self.detect_hardware()
            
            # Environment setup
            env_success = self.setup_environment_variables()
            
            # Location configuration
            location_config = self.configure_location()
            self.wizard_data.update(location_config)
            
            # Safety configuration
            safety_config = self.configure_safety_settings()
            self.wizard_data.update(safety_config)
            
            # System test
            test_success = self.run_system_test()
            
            # Completion summary
            self.show_completion_summary()
            
            # Save wizard data
            wizard_file = self.project_root / 'first_run_wizard.json'
            with open(wizard_file, 'w') as f:
                json.dump({
                    'wizard_data': self.wizard_data,
                    'hardware_results': self.hardware_results,
                    'completed_at': time.time(),
                    'test_success': test_success
                }, f, indent=2, default=str)
            
            return test_success
            
        except KeyboardInterrupt:
            print(f"\n\n⚠️  Setup interrupted by user.")
            print(f"You can run the wizard again anytime with:")
            print(f"  python3 scripts/first_run_wizard.py")
            return False
        except Exception as e:
            print(f"\n❌ Wizard error: {e}")
            print(f"Please check the logs and try again.")
            return False


async def main():
    """Main wizard function"""
    wizard = FirstRunWizard()
    success = await wizard.run_wizard()
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
