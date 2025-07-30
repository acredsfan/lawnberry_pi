#!/usr/bin/env python3
"""
Hardware Detection and Testing Module
Automatically detects and tests LawnBerry Pi hardware components
"""

import asyncio
import logging
import subprocess
import json
import os
import sys
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import time

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

try:
    import smbus2 as smbus
except ImportError:
    try:
        import smbus
    except ImportError:
        smbus = None

try:
    import picamera2
except ImportError:
    picamera2 = None

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import gpiozero
    from gpiozero import Device
    from gpiozero.pins.pigpio import PiGPIOFactory
except ImportError:
    gpiozero = None


class HardwareDetector:
    """Detects and tests LawnBerry Pi hardware components"""
    
    def __init__(self, config_path: str = "config/hardware.yaml"):
        self.config_path = config_path
        self.logger = self._setup_logging()
        self.detection_results = {}
        self.test_results = {}
        
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for hardware detection"""
        logger = logging.getLogger('hardware_detector')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    async def detect_all_hardware(self) -> Dict[str, Any]:
        """Detect all hardware components"""
        self.logger.info("Starting comprehensive hardware detection...")
        
        detection_tasks = [
            self._detect_i2c_devices(),
            self._detect_serial_devices(),
            self._detect_camera(),
            self._detect_gpio_capability(),
            self._detect_system_info(),
        ]
        
        results = await asyncio.gather(*detection_tasks, return_exceptions=True)
        
        # Compile results
        self.detection_results = {
            'i2c_devices': results[0] if not isinstance(results[0], Exception) else {},
            'serial_devices': results[1] if not isinstance(results[1], Exception) else {},
            'camera': results[2] if not isinstance(results[2], Exception) else {},
            'gpio': results[3] if not isinstance(results[3], Exception) else {},
            'system': results[4] if not isinstance(results[4], Exception) else {},
            'timestamp': time.time()
        }
        
        return self.detection_results
    
    async def _detect_i2c_devices(self) -> Dict[str, Any]:
        """Detect I2C devices on the bus"""
        self.logger.info("Scanning I2C bus for devices...")
        devices = {}
        
        if not smbus:
            self.logger.warning("smbus not available - I2C detection disabled")
            return {'error': 'smbus not available'}
        
        try:
            # Try I2C bus 1 (standard on Pi)
            bus = smbus.SMBus(1)
            found_addresses = []
            
            for address in range(0x03, 0x78):  # Valid I2C address range
                try:
                    bus.read_byte(address)
                    found_addresses.append(address)
                    self.logger.info(f"Found I2C device at address 0x{address:02x}")
                except OSError:
                    pass  # Device not present
            
            bus.close()
            
            # Map to expected devices
            expected_devices = {
                0x29: 'tof_left',
                0x30: 'tof_right', 
                0x40: 'power_monitor',
                0x76: 'environmental',
                0x3c: 'display'
            }
            
            for addr in found_addresses:
                device_name = expected_devices.get(addr, f'unknown_0x{addr:02x}')
                devices[device_name] = {
                    'address': f'0x{addr:02x}',
                    'present': True,
                    'bus': 1
                }
            
            # Add missing expected devices
            for addr, name in expected_devices.items():
                if addr not in found_addresses:
                    devices[name] = {
                        'address': f'0x{addr:02x}',
                        'present': False,
                        'bus': 1
                    }
            
            devices['scan_successful'] = True
            devices['found_count'] = len(found_addresses)
            
        except Exception as e:
            self.logger.error(f"I2C detection failed: {e}")
            devices['error'] = str(e)
            devices['scan_successful'] = False
        
        return devices
    
    async def _detect_serial_devices(self) -> Dict[str, Any]:
        """Detect serial devices (GPS, RoboHAT, IMU)"""
        self.logger.info("Scanning for serial devices...")
        devices = {}
        
        if not serial:
            self.logger.warning("pyserial not available - serial detection disabled")
            return {'error': 'pyserial not available'}
        
        try:
            # List all serial ports
            ports = serial.tools.list_ports.comports()
            
            for port in ports:
                port_info = {
                    'device': port.device,
                    'description': port.description,
                    'hwid': port.hwid,
                    'manufacturer': port.manufacturer or 'Unknown',
                    'product': port.product or 'Unknown',
                    'present': True
                }
                
                # Try to identify device type
                device_type = self._identify_serial_device(port_info)
                devices[device_type] = port_info
                
                self.logger.info(f"Found serial device: {port.device} ({device_type})")
            
            # Add expected devices if not found
            expected_devices = {
                '/dev/ttyACM0': 'gps',
                '/dev/ttyACM1': 'robohat',
                '/dev/ttyAMA4': 'imu'
            }
            
            for device_path, device_name in expected_devices.items():
                if device_name not in devices:
                    devices[device_name] = {
                        'device': device_path,
                        'present': False,
                        'expected': True
                    }
            
            devices['scan_successful'] = True
            devices['found_count'] = len([d for d in devices.values() 
                                        if isinstance(d, dict) and d.get('present')])
            
        except Exception as e:
            self.logger.error(f"Serial detection failed: {e}")
            devices['error'] = str(e)
            devices['scan_successful'] = False
        
        return devices
    
    def _identify_serial_device(self, port_info: Dict[str, Any]) -> str:
        """Identify serial device type based on port info"""
        device = port_info['device'].lower()
        description = port_info['description'].lower()
        manufacturer = port_info.get('manufacturer', '').lower()
        
        # GPS device identification
        if 'gps' in description or 'u-blox' in manufacturer:
            return 'gps'
        
        # RoboHAT identification
        if 'robohat' in description or 'arduino' in description:
            return 'robohat'
        
        # IMU identification
        if '/dev/ttyama' in device or 'uart' in description:
            return 'imu'
        
        # Default to device path-based identification
        if '/dev/ttyacm0' in device:
            return 'gps'
        elif '/dev/ttyacm1' in device:
            return 'robohat'
        elif '/dev/ttyama' in device:
            return 'imu'
        
        return f'unknown_{device.replace("/dev/", "")}'
    
    async def _detect_camera(self) -> Dict[str, Any]:
        """Detect camera availability"""
        self.logger.info("Detecting camera...")
        camera_info = {}
        
        try:
            # Check for PiCamera first
            if picamera2:
                try:
                    picam2 = picamera2.Picamera2()
                    camera_properties = picam2.camera_properties
                    picam2.close()
                    
                    camera_info = {
                        'type': 'picamera',
                        'present': True,
                        'properties': dict(camera_properties),
                        'device_path': '/dev/video0'
                    }
                    self.logger.info("PiCamera detected")
                except Exception as e:
                    self.logger.warning(f"PiCamera detection failed: {e}")
            
            # Check for USB camera with OpenCV
            if not camera_info.get('present') and cv2:
                try:
                    cap = cv2.VideoCapture(0)
                    if cap.isOpened():
                        width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                        height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                        fps = cap.get(cv2.CAP_PROP_FPS)
                        
                        camera_info = {
                            'type': 'usb_camera',
                            'present': True,
                            'device_path': '/dev/video0',
                            'properties': {
                                'width': int(width),
                                'height': int(height),
                                'fps': fps
                            }
                        }
                        self.logger.info("USB camera detected")
                    cap.release()
                except Exception as e:
                    self.logger.warning(f"USB camera detection failed: {e}")
            
            # Check for video device files
            if not camera_info.get('present'):
                video_devices = list(Path('/dev').glob('video*'))
                if video_devices:
                    camera_info = {
                        'type': 'video_device',
                        'present': True,
                        'device_path': str(video_devices[0]),
                        'available_devices': [str(d) for d in video_devices]
                    }
                    self.logger.info(f"Video devices found: {video_devices}")
            
            if not camera_info.get('present'):
                camera_info = {
                    'present': False,
                    'error': 'No camera detected'
                }
                self.logger.warning("No camera detected")
            
        except Exception as e:
            self.logger.error(f"Camera detection failed: {e}")
            camera_info = {
                'present': False,
                'error': str(e)
            }
        
        return camera_info
    
    async def _detect_gpio_capability(self) -> Dict[str, Any]:
        """Detect GPIO capability and pin availability"""
        self.logger.info("Testing GPIO capability...")
        gpio_info = {}
        
        try:
            if gpiozero:
                # Test basic GPIO functionality
                gpio_info = {
                    'library': 'gpiozero',
                    'available': True,
                    'pin_factory': str(Device.pin_factory.__class__.__name__)
                }
                
                # Test specific pins used by LawnBerry
                test_pins = [22, 23, 6, 12, 24, 25]  # From hardware.yaml
                pin_status = {}
                
                for pin_num in test_pins:
                    try:
                        # Just test pin creation, don't actually use
                        from gpiozero import OutputDevice
                        test_pin = OutputDevice(pin_num)
                        test_pin.close()
                        pin_status[pin_num] = 'available'
                    except Exception as e:
                        pin_status[pin_num] = f'error: {str(e)}'
                
                gpio_info['pin_status'] = pin_status
                self.logger.info("GPIO capability confirmed")
            else:
                gpio_info = {
                    'available': False,
                    'error': 'gpiozero not available'
                }
                self.logger.warning("GPIO capability not available")
                
        except Exception as e:
            self.logger.error(f"GPIO detection failed: {e}")
            gpio_info = {
                'available': False,
                'error': str(e)
            }
        
        return gpio_info
    
    async def _detect_system_info(self) -> Dict[str, Any]:
        """Detect system information"""
        self.logger.info("Gathering system information...")
        system_info = {}
        
        try:
            # Raspberry Pi info
            try:
                with open('/proc/cpuinfo', 'r') as f:
                    cpuinfo = f.read()
                
                # Extract Pi model
                for line in cpuinfo.split('\n'):
                    if 'Model' in line:
                        system_info['pi_model'] = line.split(':')[1].strip()
                        break
                
                # Extract serial
                for line in cpuinfo.split('\n'):
                    if 'Serial' in line:
                        system_info['pi_serial'] = line.split(':')[1].strip()
                        break
            except:
                system_info['pi_model'] = 'Unknown'
            
            # Memory info
            try:
                with open('/proc/meminfo', 'r') as f:
                    meminfo = f.read()
                
                for line in meminfo.split('\n'):
                    if 'MemTotal' in line:
                        total_kb = int(line.split()[1])
                        system_info['memory_mb'] = total_kb // 1024
                        break
            except:
                system_info['memory_mb'] = 'Unknown'
            
            # OS info
            try:
                result = subprocess.run(['lsb_release', '-d'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    system_info['os'] = result.stdout.split('\t')[1].strip()
            except:
                system_info['os'] = 'Unknown'
            
            # Python version
            system_info['python_version'] = sys.version.split()[0]
            
            # I2C enabled check
            try:
                result = subprocess.run(['ls', '/dev/i2c-*'], 
                                      capture_output=True, text=True)
                system_info['i2c_enabled'] = result.returncode == 0
            except:
                system_info['i2c_enabled'] = False
            
            # SPI enabled check
            try:
                result = subprocess.run(['ls', '/dev/spidev*'], 
                                      capture_output=True, text=True)
                system_info['spi_enabled'] = result.returncode == 0
            except:
                system_info['spi_enabled'] = False
            
            self.logger.info("System information gathered")
            
        except Exception as e:
            self.logger.error(f"System info detection failed: {e}")
            system_info['error'] = str(e)
        
        return system_info
    
    async def test_hardware_connectivity(self) -> Dict[str, Any]:
        """Test actual connectivity to detected hardware"""
        self.logger.info("Testing hardware connectivity...")
        
        if not self.detection_results:
            await self.detect_all_hardware()
        
        test_tasks = [
            self._test_i2c_communication(),
            self._test_serial_communication(),
            self._test_camera_capture(),
        ]
        
        results = await asyncio.gather(*test_tasks, return_exceptions=True)
        
        self.test_results = {
            'i2c_tests': results[0] if not isinstance(results[0], Exception) else {'error': str(results[0])},
            'serial_tests': results[1] if not isinstance(results[1], Exception) else {'error': str(results[1])},
            'camera_tests': results[2] if not isinstance(results[2], Exception) else {'error': str(results[2])},
            'timestamp': time.time()
        }
        
        return self.test_results
    
    async def _test_i2c_communication(self) -> Dict[str, Any]:
        """Test I2C device communication"""
        i2c_devices = self.detection_results.get('i2c_devices', {})
        test_results = {}
        
        if not smbus or not i2c_devices.get('scan_successful'):
            return {'error': 'I2C not available or scan failed'}
        
        try:
            bus = smbus.SMBus(1)
            
            for device_name, device_info in i2c_devices.items():
                if not isinstance(device_info, dict) or not device_info.get('present'):
                    continue
                
                try:
                    address = int(device_info['address'], 16)
                    # Simple read test
                    bus.read_byte(address)
                    test_results[device_name] = {
                        'communication': 'success',
                        'address': device_info['address']
                    }
                    self.logger.info(f"I2C communication test passed for {device_name}")
                except Exception as e:
                    test_results[device_name] = {
                        'communication': 'failed',
                        'error': str(e),
                        'address': device_info['address']
                    }
                    self.logger.warning(f"I2C communication test failed for {device_name}: {e}")
            
            bus.close()
            
        except Exception as e:
            self.logger.error(f"I2C communication testing failed: {e}")
            test_results['error'] = str(e)
        
        return test_results
    
    async def _test_serial_communication(self) -> Dict[str, Any]:
        """Test serial device communication"""
        serial_devices = self.detection_results.get('serial_devices', {})
        test_results = {}
        
        if not serial or not serial_devices.get('scan_successful'):
            return {'error': 'Serial not available or scan failed'}
        
        for device_name, device_info in serial_devices.items():
            if not isinstance(device_info, dict) or not device_info.get('present'):
                continue
            
            try:
                device_path = device_info['device']
                
                # Test basic serial connection
                with serial.Serial(device_path, baudrate=9600, timeout=1) as ser:
                    # Try to read any available data
                    data = ser.read(100)
                    
                    test_results[device_name] = {
                        'communication': 'success',
                        'device': device_path,
                        'data_available': len(data) > 0,
                        'bytes_read': len(data)
                    }
                    self.logger.info(f"Serial communication test passed for {device_name}")
                    
            except Exception as e:
                test_results[device_name] = {
                    'communication': 'failed',
                    'error': str(e),
                    'device': device_info.get('device', 'unknown')
                }
                self.logger.warning(f"Serial communication test failed for {device_name}: {e}")
        
        return test_results
    
    async def _test_camera_capture(self) -> Dict[str, Any]:
        """Test camera capture capability"""
        camera_info = self.detection_results.get('camera', {})
        
        if not camera_info.get('present'):
            return {'error': 'No camera detected'}
        
        try:
            if camera_info.get('type') == 'picamera' and picamera2:
                picam2 = picamera2.Picamera2()
                picam2.configure(picam2.create_preview_configuration())
                picam2.start()
                time.sleep(1)  # Let camera warm up
                
                # Capture test image
                array = picam2.capture_array()
                picam2.stop()
                picam2.close()
                
                return {
                    'capture': 'success',
                    'type': 'picamera',
                    'image_shape': array.shape
                }
                
            elif cv2:
                cap = cv2.VideoCapture(0)
                if cap.isOpened():
                    ret, frame = cap.read()
                    cap.release()
                    
                    if ret:
                        return {
                            'capture': 'success',
                            'type': 'opencv',
                            'image_shape': frame.shape
                        }
                    else:
                        return {
                            'capture': 'failed',
                            'error': 'Could not capture frame'
                        }
                else:
                    return {
                        'capture': 'failed',
                        'error': 'Could not open camera'
                    }
            else:
                return {
                    'capture': 'failed',
                    'error': 'No camera libraries available'
                }
                
        except Exception as e:
            self.logger.error(f"Camera test failed: {e}")
            return {
                'capture': 'failed',
                'error': str(e)
            }
    
    def generate_hardware_config(self, output_path: Optional[str] = None) -> str:
        """Generate hardware configuration based on detected devices"""
        if not self.detection_results:
            raise RuntimeError("No detection results available. Run detect_all_hardware() first.")
        
        config = self._create_hardware_config_dict()
        
        if output_path:
            with open(output_path, 'w') as f:
                f.write(self._dict_to_yaml(config))
            return output_path
        else:
            return self._dict_to_yaml(config)
    
    def _create_hardware_config_dict(self) -> Dict[str, Any]:
        """Create hardware config dictionary from detection results"""
        config = {
            'i2c': {
                'bus_number': 1,
                'devices': {}
            },
            'serial': {
                'devices': {}
            },
            'gpio': {
                'pins': {
                    'tof_left_shutdown': 22,
                    'tof_right_shutdown': 23,
                    'tof_left_interrupt': 6,
                    'tof_right_interrupt': 12,
                    'blade_enable': 24,
                    'blade_direction': 25
                }
            },
            'camera': {},
            'plugins': [],
            'logging_level': 'INFO',
            'retry_attempts': 3,
            'retry_base_delay': 0.1,
            'retry_max_delay': 5.0
        }
        
        # Add detected I2C devices
        i2c_devices = self.detection_results.get('i2c_devices', {})
        for device_name, device_info in i2c_devices.items():
            if isinstance(device_info, dict) and device_info.get('present'):
                address = int(device_info['address'], 16)
                config['i2c']['devices'][device_name] = address
        
        # Add detected serial devices
        serial_devices = self.detection_results.get('serial_devices', {})
        for device_name, device_info in serial_devices.items():
            if isinstance(device_info, dict) and device_info.get('present'):
                device_config = {
                    'port': device_info['device'],
                    'baud': self._get_default_baud_rate(device_name),
                    'timeout': 1.0
                }
                config['serial']['devices'][device_name] = device_config
        
        # Add camera configuration
        camera_info = self.detection_results.get('camera', {})
        if camera_info.get('present'):
            config['camera'] = {
                'device_path': camera_info.get('device_path', '/dev/video0'),
                'width': 1920,
                'height': 1080,
                'fps': 30,
                'buffer_size': 5
            }
        
        # Add plugins for detected devices
        for device_name, device_info in i2c_devices.items():
            if isinstance(device_info, dict) and device_info.get('present'):
                plugin_config = self._create_plugin_config(device_name, device_info)
                if plugin_config:
                    config['plugins'].append(plugin_config)
        
        return config
    
    def _get_default_baud_rate(self, device_name: str) -> int:
        """Get default baud rate for device type"""
        baud_rates = {
            'robohat': 115200,
            'gps': 38400,
            'imu': 3000000
        }
        return baud_rates.get(device_name, 9600)
    
    def _create_plugin_config(self, device_name: str, device_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create plugin configuration for device"""
        plugin_configs = {
            'tof_left': {
                'name': 'tof_left',
                'enabled': True,
                'parameters': {
                    'i2c_address': device_info['address'],
                    'shutdown_pin': 22,
                    'interrupt_pin': 6
                }
            },
            'tof_right': {
                'name': 'tof_right', 
                'enabled': True,
                'parameters': {
                    'i2c_address': device_info['address'],
                    'shutdown_pin': 23,
                    'interrupt_pin': 12
                }
            },
            'power_monitor': {
                'name': 'power_monitor',
                'enabled': True,
                'parameters': {
                    'i2c_address': device_info['address'],
                    'channel': 1
                }
            }
        }
        
        return plugin_configs.get(device_name)
    
    def _dict_to_yaml(self, data: Dict[str, Any], indent: int = 0) -> str:
        """Convert dictionary to YAML format (simple implementation)"""
        lines = []
        spaces = '  ' * indent
        
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{spaces}{key}:")
                lines.append(self._dict_to_yaml(value, indent + 1))
            elif isinstance(value, list):
                lines.append(f"{spaces}{key}:")
                for item in value:
                    if isinstance(item, dict):
                        lines.append(f"{spaces}  -")
                        for sub_key, sub_value in item.items():
                            if isinstance(sub_value, dict):
                                lines.append(f"{spaces}    {sub_key}:")
                                lines.append(self._dict_to_yaml(sub_value, indent + 3))
                            else:
                                lines.append(f"{spaces}    {sub_key}: {sub_value}")
                    else:
                        lines.append(f"{spaces}  - {item}")
            else:
                lines.append(f"{spaces}{key}: {value}")
        
        return '\n'.join(lines)
    
    def print_summary(self):
        """Print a summary of detection and test results"""
        print("\n" + "="*60)
        print("         LAWNBERRY PI HARDWARE DETECTION SUMMARY")
        print("="*60)
        
        if not self.detection_results:
            print("No detection results available")
            return
        
        # System Information
        system = self.detection_results.get('system', {})
        print(f"\nSystem Information:")
        print(f"  Pi Model: {system.get('pi_model', 'Unknown')}")
        print(f"  Memory: {system.get('memory_mb', 'Unknown')} MB")
        print(f"  OS: {system.get('os', 'Unknown')}")
        print(f"  Python: {system.get('python_version', 'Unknown')}")
        print(f"  I2C Enabled: {'Yes' if system.get('i2c_enabled') else 'No'}")
        print(f"  SPI Enabled: {'Yes' if system.get('spi_enabled') else 'No'}")
        
        # I2C Devices
        i2c = self.detection_results.get('i2c_devices', {})
        print(f"\nI2C Devices ({i2c.get('found_count', 0)} found):")
        for name, info in i2c.items():
            if isinstance(info, dict) and 'address' in info:
                status = "✓ Present" if info.get('present') else "✗ Missing"
                print(f"  {name:15} @ {info['address']} - {status}")
        
        # Serial Devices
        serial_devs = self.detection_results.get('serial_devices', {})
        print(f"\nSerial Devices ({serial_devs.get('found_count', 0)} found):")
        for name, info in serial_devs.items():
            if isinstance(info, dict) and 'device' in info:
                status = "✓ Present" if info.get('present') else "✗ Missing"
                device = info.get('device', 'Unknown')
                print(f"  {name:15} @ {device} - {status}")
        
        # Camera
        camera = self.detection_results.get('camera', {})
        print(f"\nCamera:")
        if camera.get('present'):
            cam_type = camera.get('type', 'Unknown')
            device = camera.get('device_path', 'Unknown')
            print(f"  Type: {cam_type}")
            print(f"  Device: {device}")
            print(f"  Status: ✓ Present")
        else:
            print(f"  Status: ✗ Not detected")
        
        # GPIO
        gpio = self.detection_results.get('gpio', {})
        print(f"\nGPIO:")
        if gpio.get('available'):
            print(f"  Library: {gpio.get('library', 'Unknown')}")
            print(f"  Status: ✓ Available")
        else:
            print(f"  Status: ✗ Not available")
        
        # Test Results Summary
        if self.test_results:
            print(f"\nConnectivity Tests:")
            
            i2c_tests = self.test_results.get('i2c_tests', {})
            if not i2c_tests.get('error'):
                passed = sum(1 for t in i2c_tests.values() 
                           if isinstance(t, dict) and t.get('communication') == 'success')
                total = len([t for t in i2c_tests.values() if isinstance(t, dict)])
                print(f"  I2C Communication: {passed}/{total} devices responding")
            
            serial_tests = self.test_results.get('serial_tests', {})
            if not serial_tests.get('error'):
                passed = sum(1 for t in serial_tests.values()
                           if isinstance(t, dict) and t.get('communication') == 'success')
                total = len([t for t in serial_tests.values() if isinstance(t, dict)])
                print(f"  Serial Communication: {passed}/{total} devices responding")
            
            camera_tests = self.test_results.get('camera_tests', {})
            if camera_tests.get('capture') == 'success':
                print(f"  Camera Capture: ✓ Working")
            else:
                print(f"  Camera Capture: ✗ Failed")
        
        print("\n" + "="*60)


async def main():
    """Main detection function"""
    detector = HardwareDetector()
    
    print("Starting LawnBerry Pi hardware detection...")
    
    # Detect all hardware
    detection_results = await detector.detect_all_hardware()
    
    # Test connectivity
    print("\nTesting hardware connectivity...")
    test_results = await detector.test_hardware_connectivity()
    
    # Print summary
    detector.print_summary()
    
    # Save results
    results_file = 'hardware_detection_results.json'
    with open(results_file, 'w') as f:
        json.dump({
            'detection': detection_results,
            'tests': test_results
        }, f, indent=2, default=str)
    
    print(f"\nDetailed results saved to: {results_file}")
    
    # Generate hardware config
    try:
        config_yaml = detector.generate_hardware_config()
        with open('hardware_detected.yaml', 'w') as f:
            f.write(config_yaml)
        print("Generated hardware configuration: hardware_detected.yaml")
    except Exception as e:
        print(f"Failed to generate hardware config: {e}")
    
    return detection_results, test_results


if __name__ == "__main__":
    asyncio.run(main())
