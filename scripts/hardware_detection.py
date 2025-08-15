#!/usr/bin/env python3
"""
Enhanced Hardware Detection and Testing Module
Automatically detects and tests LawnBerry Pi hardware components with manual override support
"""

import asyncio
import logging
import subprocess
import json
import os
import sys
from typing import Dict, List, Optional, Tuple, Any, Union
from pathlib import Path
import time
from dataclasses import dataclass, asdict
from enum import Enum

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

# Coral TPU detection imports
try:
    import pycoral.utils.edgetpu as edgetpu
    PYCORAL_AVAILABLE = True
except ImportError:
    PYCORAL_AVAILABLE = False

try:
    import tflite_runtime.interpreter as tflite
    TFLITE_AVAILABLE = True
except ImportError:
    TFLITE_AVAILABLE = False


class DetectionConfidence(Enum):
    """Confidence levels for hardware detection"""
    HIGH = "high"       # 90-100% confident
    MEDIUM = "medium"   # 70-89% confident  
    LOW = "low"         # 50-69% confident
    UNKNOWN = "unknown" # <50% confident


@dataclass
class HardwareDetectionResult:
    """Result of hardware detection with confidence scoring"""
    component_name: str
    detected: bool
    confidence: DetectionConfidence
    details: Dict[str, Any]
    alternative_options: List[str]
    manual_override: Optional[Dict[str, Any]] = None
    requires_user_confirmation: bool = False


@dataclass
class HardwareCapability:
    """Defines hardware capability with alternatives"""
    name: str
    required: bool
    primary_hardware: List[str]
    alternative_hardware: List[str]
    software_fallback: Optional[str] = None


class EnhancedHardwareDetector:
    """Enhanced hardware detector with confidence scoring and manual override support"""
    
    def __init__(self, config_path: str = "config/hardware.yaml"):
        self.config_path = config_path
        self.logger = self._setup_logging()
        self.detection_results: Dict[str, HardwareDetectionResult] = {}
        self.test_results = {}
        self.manual_overrides: Dict[str, Dict[str, Any]] = {}
        self.hardware_capabilities = self._define_hardware_capabilities()
    
    def _define_hardware_capabilities(self) -> Dict[str, HardwareCapability]:
        """Define hardware capabilities with alternatives"""
        return {
            'navigation': HardwareCapability(
                name='navigation',
                required=True,
                primary_hardware=['SparkFun GPS-RTK-SMA', 'BNO085 IMU'],
                alternative_hardware=['Generic GPS', 'MPU6050', 'LSM9DS1'],
                software_fallback='Dead reckoning navigation'
            ),
            'obstacle_detection': HardwareCapability(
                name='obstacle_detection',
                required=True,
                primary_hardware=['VL53L0X ToF', 'Pi Camera'],
                alternative_hardware=['HC-SR04 Ultrasonic', 'VL53L1X ToF', 'Generic Camera'],
                software_fallback='Camera-only detection'
            ),
            'power_monitoring': HardwareCapability(
                name='power_monitoring',
                required=True,
                primary_hardware=['INA226 Power Monitor'],
                alternative_hardware=['INA219', 'Voltage Divider + ADC'],
                software_fallback='Software estimation'
            ),
            'environmental': HardwareCapability(
                name='environmental',
                required=False,
                primary_hardware=['BME280'],
                alternative_hardware=['DHT22', 'BMP280'],
                software_fallback='Weather API'
            ),
            'communication': HardwareCapability(
                name='communication',
                required=True,
                primary_hardware=['RoboHAT RP2040'],
                alternative_hardware=['Arduino', 'Pico'],
                software_fallback='Direct GPIO control'
            )
        }
        
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
    
    def set_manual_override(self, component: str, override_config: Dict[str, Any]) -> None:
        """Set manual override for a specific component"""
        self.manual_overrides[component] = override_config
        self.logger.info(f"Manual override set for {component}: {override_config}")
    
    def get_detection_confidence(self, component: str) -> DetectionConfidence:
        """Get confidence level for detected component"""
        if component in self.detection_results:
            return self.detection_results[component].confidence
        return DetectionConfidence.UNKNOWN
    
    async def detect_all_hardware(self) -> Dict[str, HardwareDetectionResult]:
        """Enhanced hardware detection with confidence scoring"""
        self.logger.info("Starting enhanced hardware detection with confidence scoring...")
        
        detection_tasks = [
            self._detect_i2c_devices_enhanced(),
            self._detect_serial_devices_enhanced(), 
            self._detect_camera_enhanced(),
            self._detect_gpio_capability_enhanced(),
            self._detect_system_info_enhanced(),
            self._detect_coral_tpu_enhanced(),
        ]
        
        results = await asyncio.gather(*detection_tasks, return_exceptions=True)
        
        # Process results with confidence scoring
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"Detection task {i} failed: {result}")
                continue
            
            if isinstance(result, dict):
                self.detection_results.update(result)
        
        # Apply manual overrides
        self._apply_manual_overrides()
        
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
            
            # I2C/SPI enabled check (use Python glob to avoid shell glob pitfalls)
            try:
                i2c_nodes = list(Path('/dev').glob('i2c-*'))
                system_info['i2c_enabled'] = len(i2c_nodes) > 0
            except Exception:
                system_info['i2c_enabled'] = False
            # Fallback: attempt to open I2C bus 1 with smbus to infer availability
            if not system_info.get('i2c_enabled') and smbus:
                try:
                    _bus_probe = smbus.SMBus(1)
                    _bus_probe.close()
                    system_info['i2c_enabled'] = True
                except Exception:
                    pass

            try:
                spi_nodes = list(Path('/dev').glob('spidev*'))
                system_info['spi_enabled'] = len(spi_nodes) > 0
            except Exception:
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
        i2c_devices = self.detection_results.get('i2c_devices')
        test_results: Dict[str, Any] = {}

        if not smbus or not i2c_devices or not i2c_devices.detected:
            return {'error': 'I2C not available or no devices detected'}

        try:
            bus = smbus.SMBus(1)

            for device_name, device_info in i2c_devices.details.get('devices', {}).items():
                if not isinstance(device_info, dict) or not device_info.get('present'):
                    continue

                address_hex = device_info['address']
                address = int(address_hex, 16)

                try:
                    if device_name in ("environmental",):
                        # BME280 check: CHIP_ID register 0xD0 should be 0x60; fallback to presence
                        try:
                            chip_id = bus.read_byte_data(address, 0xD0)
                            ok = (chip_id == 0x60)
                            ok = (chip_id in (0x60, 0x58))  # BME280=0x60, BMP280=0x58
                            test_results[device_name] = {
                                'communication': 'success' if ok else 'failed',
                                'check': 'BME/BMP280 CHIP_ID',
                                'chip_id': f"0x{chip_id:02x}",
                                'address': address_hex
                            }
                            self.logger.info(f"I2C test for BME/BMP280 at {address_hex}: chip_id=0x{chip_id:02x}")
                        except Exception as e:
                            try:
                                bus.read_byte(address)
                                test_results[device_name] = {
                                    'communication': 'success',
                                    'check': 'presence',
                                    'address': address_hex
                                }
                                self.logger.info(f"I2C presence for BME280 at {address_hex}")
                            except Exception:
                                raise e

                    elif device_name in ("power_monitor",):
                        # INA3221/INA226: Manufacturer ID at 0xFE should be 0x5449 ('TI'); fallback to presence
                        man_id = None
                        die_id = None
                        try:
                            raw_man = bus.read_word_data(address, 0xFE)
                            man_id = ((raw_man & 0xFF) << 8) | ((raw_man >> 8) & 0xFF)
                            try:
                                raw_die = bus.read_word_data(address, 0xFF)
                                die_id = ((raw_die & 0xFF) << 8) | ((raw_die >> 8) & 0xFF)
                            except Exception:
                                die_id = None
                        except Exception as e:
                            try:
                                bus.read_byte(address)
                            except Exception:
                                raise e
                        ok = (man_id == 0x5449)
                        test_results[device_name] = {
                            'communication': 'success' if ok or man_id is None else 'failed',
                            'check': 'INA32xx Manufacturer ID' if man_id is not None else 'presence',
                            'manufacturer_id': (f"0x{man_id:04x}" if man_id is not None else None),
                            'die_id': (f"0x{die_id:04x}" if die_id is not None else None),
                            'address': address_hex
                        }
                        self.logger.info(
                            f"I2C test for INA32xx at {address_hex}: "
                            f"mfg={(('0x%04x' % man_id) if man_id is not None else 'N/A')}, "
                            f"die={(('0x%04x' % die_id) if die_id is not None else 'N/A')}"
                        )

                    elif device_name.startswith("tof_"):
                        # Conservative presence check for VL53L0X; optionally read I2C address register (0x8A)
                        present = self._test_i2c_address(bus, address)
                        addr_reg = None
                        if present:
                            try:
                                addr_reg = bus.read_byte_data(address, 0x8A) & 0x7F
                            except Exception:
                                addr_reg = None
                        test_results[device_name] = {
                            'communication': 'success' if present else 'failed',
                            'check': 'VL53L0X presence',
                            'reported_addr': (f"0x{addr_reg:02x}" if addr_reg is not None else None),
                            'address': address_hex
                        }
                        self.logger.info(
                            f"I2C presence for VL53L0X at {address_hex}: present={present}, "
                            f"reg_8A={(('0x%02x' % addr_reg) if addr_reg is not None else 'N/A')}"
                        )

                    else:
                        # Fallback: presence probe
                        bus.read_byte(address)
                        test_results[device_name] = {
                            'communication': 'success',
                            'check': 'presence',
                            'address': address_hex
                        }
                        self.logger.info(f"I2C presence check passed for {device_name} at {address_hex}")

                except Exception as e:
                    test_results[device_name] = {
                        'communication': 'failed',
                        'error': str(e),
                        'address': address_hex
                    }
                    self.logger.warning(f"I2C test failed for {device_name} at {address_hex}: {e}")

                await asyncio.sleep(0.05)

            bus.close()
        except Exception as e:
            self.logger.error(f"I2C communication testing failed: {e}")
            test_results['error'] = str(e)

        return test_results
    
    async def _test_serial_communication(self) -> Dict[str, Any]:
        """Test serial device communication"""
        serial_devices = self.detection_results.get('serial_devices')
        test_results = {}
        
        if not serial or not serial_devices or not serial_devices.detected:
            return {'error': 'Serial not available or no devices detected'}
        
        for device_name, device_info in serial_devices.details.get('devices', {}).items():
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
        camera_result = self.detection_results.get('camera')
        # Support both dict and HardwareDetectionResult
        if isinstance(camera_result, dict):
            camera_present = camera_result.get('present')
            camera_type = camera_result.get('type')
            camera_device = camera_result.get('device_path')
        elif camera_result is not None:
            camera_present = getattr(camera_result, 'detected', False)
            details = getattr(camera_result, 'details', {}) or {}
            camera_type = details.get('type')
            camera_device = details.get('device_path')
        else:
            camera_present = False
            camera_type = None
            camera_device = None

        if not camera_present:
            return {'error': 'No camera detected'}
        
        try:
            if camera_type and 'Pi Camera' in camera_type and picamera2:
                # Use still configuration suitable for headless systems (no preview requirements)
                try:
                    from picamera2 import Picamera2
                except Exception:
                    Picamera2 = None
                if Picamera2 is not None:
                    picam2 = Picamera2()
                    cfg = picam2.create_still_configuration(buffer_count=1)
                    picam2.configure(cfg)
                    picam2.start()
                    time.sleep(0.8)
                    array = picam2.capture_array("main")
                    picam2.stop()
                    picam2.close()
                    return {
                        'capture': 'success',
                        'type': 'picamera2',
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
            # Fallback: try rpicam-still headless capture with timeout
            try:
                result = subprocess.run(
                    ['timeout', '6s', 'rpicam-still', '-n', '-t', '100', '-o', '/tmp/lawnberry_cam_test.jpg'],
                    capture_output=True, text=True
                )
                if result.returncode == 0 and os.path.exists('/tmp/lawnberry_cam_test.jpg'):
                    return {
                        'capture': 'success',
                        'type': 'rpicam-still',
                        'image_path': '/tmp/lawnberry_cam_test.jpg'
                    }
            except Exception as e2:
                self.logger.debug(f"rpicam-still fallback failed: {e2}")
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
        i2c_devices = self.detection_results.get('i2c_devices')
        if i2c_devices and i2c_devices.detected:
            for device_name, device_info in i2c_devices.details.get('devices', {}).items():
                if isinstance(device_info, dict) and device_info.get('present'):
                    address = int(device_info['address'], 16)
                    config['i2c']['devices'][device_name] = address
        
        # Add detected serial devices
        serial_devices = self.detection_results.get('serial_devices')
        if serial_devices and serial_devices.detected:
            for device_name, device_info in serial_devices.details.get('devices', {}).items():
                if isinstance(device_info, dict) and device_info.get('present'):
                    device_config = {
                        'port': device_info['device'],
                        'baud': self._get_default_baud_rate(device_name),
                        'timeout': 1.0
                    }
                    config['serial']['devices'][device_name] = device_config
        
        # Add camera configuration
        camera_info = self.detection_results.get('camera')
        if camera_info and camera_info.detected:
            config['camera'] = {
                'device_path': camera_info.details.get('device_path', '/dev/video0'),
                'width': 1920,
                'height': 1080,
                'fps': 30,
                'buffer_size': 5
            }
        
        # Add plugins for detected devices
        i2c_devices = self.detection_results.get('i2c_devices')
        if i2c_devices and i2c_devices.detected:
            for device_name, device_info in i2c_devices.details.get('devices', {}).items():
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
        if isinstance(system, HardwareDetectionResult):
            system_details = system.details
        else:
            system_details = system

        print(f"\nSystem Information:")
        print(f"  Pi Model: {system_details.get('pi_model', 'Unknown')}")
        print(f"  Memory: {system_details.get('memory_mb', 'Unknown')} MB")
        print(f"  OS: {system_details.get('os', 'Unknown')}")
        print(f"  Python: {system_details.get('python_version', 'Unknown')}")
        print(f"  I2C Enabled: {'Yes' if system_details.get('i2c_enabled') else 'No'}")
        print(f"  SPI Enabled: {'Yes' if system_details.get('spi_enabled') else 'No'}")
        
        # I2C Devices
        i2c_devices = self.detection_results.get('i2c_devices')
        if i2c_devices and i2c_devices.detected:
            device_count = len(i2c_devices.details.get('devices', {}))
            print(f"\nI2C Devices ({device_count} found):")
            for name, info in i2c_devices.details.get('devices', {}).items():
                if isinstance(info, dict) and 'address' in info:
                    status = "✓ Present" if info.get('present') else "✗ Missing"
                    print(f"  {name:15} @ {info['address']} - {status}")
        else:
            print(f"\nI2C Devices (0 found):")
        
        # Serial Devices
        serial_devices = self.detection_results.get('serial_devices')
        if serial_devices and serial_devices.detected:
            device_count = len(serial_devices.details.get('devices', {}))
            print(f"\nSerial Devices ({device_count} found):")
            for name, info in serial_devices.details.get('devices', {}).items():
                if isinstance(info, dict) and 'device' in info:
                    status = "✓ Present" if info.get('present') else "✗ Missing"
                    device = info.get('device', 'Unknown')
                    print(f"  {name:15} @ {device} - {status}")
        else:
            print(f"\nSerial Devices (0 found):")
        
        # Camera
        camera = self.detection_results.get('camera')
        print(f"\nCamera:")
        if camera and camera.detected:
            cam_type = camera.details.get('type', 'Unknown')
            device = camera.details.get('device_path', 'Unknown')
            print(f"  Type: {cam_type}")
            print(f"  Device: {device}")
            print(f"  Status: ✓ Present (confidence={camera.confidence.value})")
        else:
            print(f"  Status: ✗ Not detected")
        
        # GPIO
        gpio = self.detection_results.get('gpio')
        print(f"\nGPIO:")
        if gpio and gpio.detected:
            print(f"  Library: {gpio.details.get('library', 'Unknown')}")
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
                print(f"  Camera Capture: ✓ Working ({camera_tests.get('type')})")
            else:
                err = camera_tests.get('error', 'unknown error')
                print(f"  Camera Capture: ✗ Failed ({err})")
        
        print("\n" + "="*60)



    def _apply_manual_overrides(self) -> None:
        """Apply manual overrides to detection results"""
        for component, override_config in self.manual_overrides.items():
            if component in self.detection_results:
                result = self.detection_results[component]
                result.manual_override = override_config
                result.confidence = DetectionConfidence.HIGH  # User confirmed
                self.logger.info(f"Applied manual override for {component}")
    
    async def _detect_i2c_devices_enhanced(self) -> Dict[str, HardwareDetectionResult]:
        """Enhanced I2C device detection with confidence scoring"""
        individual_results = {}
        
        if not smbus:
            self.logger.warning("SMBus not available - I2C detection limited")
            # Return a grouped result indicating I2C is not available
            return {
                'i2c_devices': HardwareDetectionResult(
                    component_name='i2c_devices',
                    detected=False,
                    confidence=DetectionConfidence.HIGH,
                    details={'error': 'SMBus not available', 'devices': {}},
                    alternative_options=['Install python3-smbus package'],
                    requires_user_confirmation=False
                )
            }
        
        try:
            bus = smbus.SMBus(1)
            expected_devices = {
                'tof_left': {'address': 0x29, 'alternatives': [0x30]},
                'tof_right': {'address': 0x30, 'alternatives': [0x29]},
                'power_monitor': {'address': 0x40, 'alternatives': [0x41, 0x44, 0x45]},
                'environmental': {'address': 0x76, 'alternatives': [0x77]},
                'display': {'address': 0x3c, 'alternatives': [0x3d]}
            }
            
            detected_devices = {}
            any_detected = False

            claimed_addrs = set()
            for device_name, config in expected_devices.items():
                primary_addr = config['address']
                alternatives = config['alternatives']

                # Try primary address with device-specific probing
                if device_name.startswith('tof_'):
                    detected = (primary_addr not in claimed_addrs) and self._probe_tof_presence(bus, primary_addr)
                else:
                    detected = self._test_i2c_address(bus, primary_addr)
                confidence = DetectionConfidence.HIGH if detected else DetectionConfidence.UNKNOWN
                alternative_options = []
                actual_addr = primary_addr

                if not detected:
                    # Try alternatives
                    for alt_addr in alternatives:
                        if alt_addr in claimed_addrs:
                            continue
                        if device_name.startswith('tof_'):
                            alt_ok = self._probe_tof_presence(bus, alt_addr)
                        else:
                            alt_ok = self._test_i2c_address(bus, alt_addr)
                        if alt_ok:
                            detected = True
                            confidence = DetectionConfidence.MEDIUM
                            alternative_options.append(f"Found at 0x{alt_addr:02x}")
                            actual_addr = alt_addr
                            break

                # If still not detected and this is ToF, run a quick bus scan to confirm
                if not detected and device_name.startswith('tof_'):
                    scanned = self._i2c_scan_addresses()
                    if primary_addr in scanned or any(a in scanned for a in alternatives):
                        # Presence suggested by scan; mark as low confidence and pick seen address
                        detected = True
                        confidence = DetectionConfidence.LOW
                        seen = None
                        if primary_addr in scanned:
                            seen = primary_addr
                        else:
                            for a in alternatives:
                                if a in scanned:
                                    seen = a
                                    break
                        if seen is not None:
                            actual_addr = seen
                            alternative_options.append(f"Seen by i2cdetect at 0x{seen:02x}")

                if detected:
                    any_detected = True
                    claimed_addrs.add(actual_addr)
                    detected_devices[device_name] = {
                        'address': f"0x{actual_addr:02x}",
                        'present': True,
                        'confidence': confidence.value
                    }

                individual_results[device_name] = HardwareDetectionResult(
                    component_name=device_name,
                    detected=detected,
                    confidence=confidence,
                    details={'address': actual_addr},
                    alternative_options=alternative_options,
                    requires_user_confirmation=confidence == DetectionConfidence.MEDIUM
                )
            
            bus.close()
            
            # Create grouped result for I2C devices
            group_result = HardwareDetectionResult(
                component_name='i2c_devices',
                detected=any_detected,
                confidence=DetectionConfidence.HIGH if any_detected else DetectionConfidence.LOW,
                details={'devices': detected_devices},
                alternative_options=[],
                requires_user_confirmation=False
            )
            
            # Return both individual and grouped results
            result = individual_results.copy()
            result['i2c_devices'] = group_result
            return result
            
        except Exception as e:
            self.logger.error(f"I2C detection failed: {e}")
            return {
                'i2c_devices': HardwareDetectionResult(
                    component_name='i2c_devices',
                    detected=False,
                    confidence=DetectionConfidence.LOW,
                    details={'error': str(e), 'devices': {}},
                    alternative_options=['Check I2C is enabled in raspi-config'],
                    requires_user_confirmation=True
                )
            }
    
    async def _detect_serial_devices_enhanced(self) -> Dict[str, HardwareDetectionResult]:
        """Enhanced serial device detection with confidence scoring"""
        individual_results = {}
        
        if not serial:
            self.logger.warning("PySerial not available - serial detection limited")
            return {
                'serial_devices': HardwareDetectionResult(
                    component_name='serial_devices',
                    detected=False,
                    confidence=DetectionConfidence.HIGH,
                    details={'error': 'PySerial not available', 'devices': {}},
                    alternative_options=['Install python3-serial package'],
                    requires_user_confirmation=False
                )
            }
        
        expected_devices = {
            'robohat': {'ports': ['/dev/ttyACM1', '/dev/ttyACM0'], 'baud': 115200},
            'gps': {'ports': ['/dev/ttyACM0', '/dev/ttyUSB0'], 'baud': 38400},
            'imu': {'ports': ['/dev/ttyAMA4', '/dev/ttyAMA0'], 'baud': 3000000}
        }
        
        available_ports = [port.device for port in serial.tools.list_ports.comports()]
        detected_devices = {}
        any_detected = False
        
        for device_name, config in expected_devices.items():
            primary_port = config['ports'][0]
            alternative_ports = config['ports'][1:]
            detected = False
            confidence = DetectionConfidence.UNKNOWN
            alternative_options = []
            actual_port = primary_port
            
            # Check primary port
            if primary_port in available_ports:
                detected = True
                confidence = DetectionConfidence.HIGH
                actual_port = primary_port
            else:
                # Check alternatives
                for alt_port in alternative_ports:
                    if alt_port in available_ports:
                        detected = True
                        confidence = DetectionConfidence.MEDIUM
                        actual_port = alt_port
                        alternative_options.append(f"Found at {alt_port}")
                        break
            
            if detected:
                any_detected = True
                detected_devices[device_name] = {
                    'device': actual_port,
                    'present': True,
                    'baud': config['baud']
                }
            
            individual_results[device_name] = HardwareDetectionResult(
                component_name=device_name,
                detected=detected,
                confidence=confidence,
                details={'port': actual_port, 'baud': config['baud']},
                alternative_options=alternative_options,
                requires_user_confirmation=confidence == DetectionConfidence.MEDIUM
            )
        
        # Create grouped result for serial devices
        group_result = HardwareDetectionResult(
            component_name='serial_devices',
            detected=any_detected,
            confidence=DetectionConfidence.HIGH if any_detected else DetectionConfidence.LOW,
            details={'devices': detected_devices},
            alternative_options=[],
            requires_user_confirmation=False
        )
        
        # Return both individual and grouped results
        result = individual_results.copy()
        result['serial_devices'] = group_result
        return result
    
    async def _detect_camera_enhanced(self) -> Dict[str, HardwareDetectionResult]:
        """Enhanced camera detection with confidence scoring"""
        results = {}
        
        # Try different camera detection methods
        detected = False
        confidence = DetectionConfidence.UNKNOWN
        alternative_options = []
        camera_details = {}
        
        # Method 1: Try picamera2 (Bookworm preferred)
        if picamera2:
            try:
                from picamera2 import Picamera2
                cam = Picamera2()
                cam.close()
                detected = True
                confidence = DetectionConfidence.HIGH
                camera_details = {'type': 'Pi Camera (picamera2)', 'device_path': '/dev/video0'}
            except Exception as e:
                self.logger.debug(f"Picamera2 detection failed: {e}")
        
        # Method 2: Try OpenCV detection
        if not detected and cv2:
            try:
                cap = cv2.VideoCapture(0)
                if cap.isOpened():
                    detected = True
                    confidence = DetectionConfidence.MEDIUM
                    camera_details = {'type': 'Generic Camera (OpenCV)', 'device_path': '/dev/video0'}
                    alternative_options.append("Detected via OpenCV - may need configuration")
                cap.release()
            except Exception as e:
                self.logger.debug(f"OpenCV camera detection failed: {e}")
        
        # Method 3: Check for video devices
        if not detected:
            video_devices = [f"/dev/video{i}" for i in range(4) if Path(f"/dev/video{i}").exists()]
            if video_devices:
                detected = True
                confidence = DetectionConfidence.LOW
                camera_details = {'type': 'Unknown Camera', 'device_path': video_devices[0]}
                alternative_options.extend([f"Video device: {dev}" for dev in video_devices])
        
        results['camera'] = HardwareDetectionResult(
            component_name='camera',
            detected=detected,
            confidence=confidence,
            details=camera_details,
            alternative_options=alternative_options,
            requires_user_confirmation=confidence in [DetectionConfidence.MEDIUM, DetectionConfidence.LOW]
        )
        
        return results
    
    async def _detect_gpio_capability_enhanced(self) -> Dict[str, HardwareDetectionResult]:
        """Enhanced GPIO capability detection"""
        results = {}
        
        detected = False
        confidence = DetectionConfidence.UNKNOWN
        alternative_options = []
        gpio_details = {}
        
        if gpiozero:
            try:
                from gpiozero import LED
                # Test with a safe pin
                test_pin = LED(18)
                test_pin.close()
                detected = True
                confidence = DetectionConfidence.HIGH
                gpio_details = {'library': 'gpiozero', 'available': True}
            except Exception as e:
                self.logger.debug(f"GPIOZero test failed: {e}")
                alternative_options.append("GPIOZero available but may need permissions")
                confidence = DetectionConfidence.MEDIUM
        
        # Check for GPIO sysfs interface
        if not detected and Path('/sys/class/gpio').exists():
            detected = True
            confidence = DetectionConfidence.LOW
            gpio_details = {'library': 'sysfs', 'available': True}
            alternative_options.append("GPIO available via sysfs interface")
        
        results['gpio'] = HardwareDetectionResult(
            component_name='gpio',
            detected=detected,
            confidence=confidence,
            details=gpio_details,
            alternative_options=alternative_options,
            requires_user_confirmation=confidence != DetectionConfidence.HIGH
        )
        
        return results
    
    async def _detect_system_info_enhanced(self) -> Dict[str, HardwareDetectionResult]:
        """Enhanced system information detection"""
        results = {}
        
        try:
            # Pi model detection
            pi_model = "Unknown"
            try:
                with open('/proc/device-tree/model', 'r') as f:
                    pi_model = f.read().strip().replace('\x00', '')
            except:
                pass
            
            # Memory detection
            memory_mb = 0
            try:
                with open('/proc/meminfo', 'r') as f:
                    for line in f:
                        if line.startswith('MemTotal:'):
                            memory_mb = int(line.split()[1]) // 1024
                            break
            except:
                pass
            
            # OS detection
            os_info = "Unknown"
            try:
                result = subprocess.run(['lsb_release', '-d'], capture_output=True, text=True)
                if result.returncode == 0:
                    os_info = result.stdout.split('\t')[1].strip()
            except:
                pass
            
            # I2C/SPI enabled checks
            try:
                i2c_nodes = list(Path('/dev').glob('i2c-*'))
                i2c_enabled = len(i2c_nodes) > 0
            except Exception:
                i2c_enabled = False
            if not i2c_enabled and smbus:
                try:
                    _bus_probe = smbus.SMBus(1)
                    _bus_probe.close()
                    i2c_enabled = True
                except Exception:
                    pass

            try:
                spi_nodes = list(Path('/dev').glob('spidev*'))
                spi_enabled = len(spi_nodes) > 0
            except Exception:
                spi_enabled = False

            confidence = DetectionConfidence.HIGH
            system_details = {
                'pi_model': pi_model,
                'memory_mb': memory_mb,
                'os': os_info,
                'python_version': sys.version.split()[0],
                'i2c_enabled': i2c_enabled,
                'spi_enabled': spi_enabled
            }
            
            results['system'] = HardwareDetectionResult(
                component_name='system',
                detected=True,
                confidence=confidence,
                details=system_details,
                alternative_options=[],
                requires_user_confirmation=False
            )
            
        except Exception as e:
            self.logger.error(f"System info detection failed: {e}")
        
        return results
    
    async def _detect_coral_tpu_enhanced(self) -> Dict[str, HardwareDetectionResult]:
        """Enhanced Coral TPU detection with Pi OS Bookworm compatibility"""
        results = {}
        
        try:
            self.logger.info("Detecting Coral TPU hardware and software compatibility...")
            
            # 1. Check OS compatibility (Pi OS Bookworm + Python 3.11+)
            os_compatible, os_details = self._check_pi_os_bookworm_compatibility()
            
            # 2. Check hardware presence
            hardware_present, hardware_details = self._detect_coral_hardware()
            
            # 3. Check software installation
            software_status, software_details = self._check_coral_software_status()
            
            # 4. Determine installation strategy
            installation_strategy = self._determine_coral_installation_strategy(
                os_compatible, hardware_present, software_status
            )
            
            # Create detection result
            overall_detected = os_compatible and (hardware_present or software_status['system_packages'])
            confidence = self._calculate_coral_confidence(
                os_compatible, hardware_present, software_status
            )
            
            details = {
                'os_compatibility': os_details,
                'hardware_detection': hardware_details,
                'software_status': software_details,
                'installation_strategy': installation_strategy,
                'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                'recommended_packages': self._get_recommended_coral_packages(os_compatible)
            }
            
            alternative_options = []
            if not hardware_present:
                alternative_options.append("CPU fallback available with tflite-runtime")
            if not os_compatible:
                alternative_options.append("Legacy installation methods for older OS versions")
            if software_status['pip_packages']:
                alternative_options.append("System package installation recommended over pip")
            
            results['coral_tpu'] = HardwareDetectionResult(
                component_name='coral_tpu',
                detected=overall_detected,
                confidence=confidence,
                details=details,
                alternative_options=alternative_options,
                requires_user_confirmation=installation_strategy.get('requires_user_input', False)
            )
            
            self.logger.info(f"Coral TPU detection completed: {confidence.value} confidence")
            
        except Exception as e:
            self.logger.error(f"Coral TPU detection failed: {e}")
            results['coral_tpu'] = HardwareDetectionResult(
                component_name='coral_tpu',
                detected=False,
                confidence=DetectionConfidence.UNKNOWN,
                details={'error': str(e)},
                alternative_options=['CPU fallback with tflite-runtime'],
                requires_user_confirmation=False
            )
        
        return results
    
    def _check_pi_os_bookworm_compatibility(self) -> Tuple[bool, Dict[str, Any]]:
        """Check Pi OS Bookworm and Python 3.11+ compatibility"""
        details = {}
        compatible = True
        
        try:
            # Check OS release
            with open('/etc/os-release', 'r') as f:
                os_release = f.read()
            
            is_bookworm = 'VERSION_CODENAME=bookworm' in os_release
            details['os_codename'] = 'bookworm' if is_bookworm else 'other'
            details['is_bookworm'] = is_bookworm
            
            # Check Python version
            python_version = (sys.version_info.major, sys.version_info.minor)
            python_compatible = python_version >= (3, 11)
            details['python_version'] = f"{python_version[0]}.{python_version[1]}"
            details['python_compatible'] = python_compatible
            
            # Check architecture
            import platform
            arch = platform.machine()
            arch_compatible = arch in ['aarch64', 'armv7l', 'x86_64']
            details['architecture'] = arch
            details['arch_compatible'] = arch_compatible
            
            compatible = is_bookworm and python_compatible and arch_compatible
            details['overall_compatible'] = compatible
            
            if compatible:
                self.logger.info("Pi OS Bookworm + Python 3.11+ compatibility confirmed")
            else:
                # Only warn when any required flag is false; include concise hint
                self.logger.warning(
                    "Compatibility issues detected: "
                    f"Bookworm={is_bookworm}, Python3.11+={python_compatible}, Arch={arch_compatible}"
                )
                
        except Exception as e:
            self.logger.error(f"OS compatibility check failed: {e}")
            compatible = False
            details['error'] = str(e)
        
        return compatible, details
    
    def _detect_coral_hardware(self) -> Tuple[bool, Dict[str, Any]]:
        """Detect Coral TPU hardware presence"""
        details = {}
        hardware_found = False
        
        try:
            # Check USB devices for Coral USB Accelerator
            usb_devices = []
            try:
                result = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    usb_output = result.stdout
                    # Google Coral USB Accelerator: Vendor ID 18d1, Product ID 9302
                    if '18d1:9302' in usb_output:
                        usb_devices.append('Coral USB Accelerator')
                        hardware_found = True
                    # Check for other Google devices
                    for line in usb_output.split('\n'):
                        if '18d1:' in line:
                            usb_devices.append(line.strip())
            except Exception as e:
                self.logger.warning(f"USB device detection failed: {e}")
            
            details['usb_devices'] = usb_devices
            
            # Check PCIe devices for Coral PCIe cards
            pcie_devices = []
            try:
                result = subprocess.run(['lspci'], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    pcie_output = result.stdout
                    # Google Edge TPU PCIe: Vendor ID 1ac1
                    for line in pcie_output.split('\n'):
                        if '1ac1:' in line:
                            pcie_devices.append(line.strip())
                            hardware_found = True
            except Exception as e:
                self.logger.warning(f"PCIe device detection failed: {e}")
            
            details['pcie_devices'] = pcie_devices
            
            # Check for Edge TPU device nodes
            device_nodes = []
            try:
                import glob
                apex_devices = glob.glob('/dev/apex_*')
                device_nodes.extend(apex_devices)
                if apex_devices:
                    hardware_found = True
            except Exception as e:
                self.logger.warning(f"Device node detection failed: {e}")
            
            details['device_nodes'] = device_nodes
            
            # Try to detect using pycoral if available
            if PYCORAL_AVAILABLE:
                try:
                    edge_tpus = edgetpu.list_edge_tpus()
                    details['pycoral_devices'] = [str(tpu) for tpu in edge_tpus]
                    if edge_tpus:
                        hardware_found = True
                        self.logger.info(f"PyCoral detected {len(edge_tpus)} Edge TPU device(s)")
                except Exception as e:
                    details['pycoral_error'] = str(e)
            
            details['hardware_detected'] = hardware_found
            
        except Exception as e:
            self.logger.error(f"Hardware detection failed: {e}")
            details['error'] = str(e)
        
        return hardware_found, details
    
    def _check_coral_software_status(self) -> Tuple[Dict[str, bool], Dict[str, Any]]:
        """Check current Coral software installation status"""
        status = {
            'system_packages': False,
            'pip_packages': False,
            'tflite_runtime': False
        }
        details = {}
        
        try:
            # Check system packages
            try:
                result = subprocess.run(
                    ['dpkg', '-l', 'python3-pycoral'], 
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and 'ii' in result.stdout:
                    status['system_packages'] = True
                    details['system_pycoral'] = 'installed'
                else:
                    details['system_pycoral'] = 'not_installed'
            except Exception as e:
                details['system_check_error'] = str(e)
            
            # Check Edge TPU runtime
            try:
                result = subprocess.run(
                    ['dpkg', '-l'], 
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    if 'libedgetpu1-std' in result.stdout or 'libedgetpu1-max' in result.stdout:
                        details['edgetpu_runtime'] = 'installed'
                    else:
                        details['edgetpu_runtime'] = 'not_installed'
            except Exception as e:
                details['runtime_check_error'] = str(e)
            
            # Check pip packages
            details['pip_pycoral'] = 'not_available' if not PYCORAL_AVAILABLE else 'available'
            status['pip_packages'] = PYCORAL_AVAILABLE
            
            # Check tflite-runtime
            details['tflite_runtime'] = 'not_available' if not TFLITE_AVAILABLE else 'available'
            status['tflite_runtime'] = TFLITE_AVAILABLE
            
        except Exception as e:
            self.logger.error(f"Software status check failed: {e}")
            details['error'] = str(e)
        
        return status, details
    
    def _determine_coral_installation_strategy(self, os_compatible: bool, hardware_present: bool, software_status: Dict[str, bool]) -> Dict[str, Any]:
        """Determine the best installation strategy for Coral packages"""
        strategy = {
            'method': 'none',
            'requires_user_input': False,
            'install_runtime': False,
            'install_packages': False,
            'fallback_available': True
        }
        
        if not os_compatible:
            strategy['method'] = 'unsupported'
            strategy['reason'] = 'Pi OS Bookworm and Python 3.11+ required'
            return strategy
        
        # Default behavior: Install Coral packages on compatible systems
        if os_compatible:
            if not software_status['system_packages']:
                strategy['method'] = 'system_packages'
                strategy['install_packages'] = True
                strategy['requires_user_input'] = True  # Ask about runtime frequency
                strategy['install_runtime'] = True
                strategy['reason'] = 'Install system packages on compatible system'
            else:
                strategy['method'] = 'already_installed'
                strategy['reason'] = 'System packages already installed'
        
        # Alternative methods if primary fails
        if software_status['pip_packages'] and not software_status['system_packages']:
            strategy['alternative_method'] = 'pip_cleanup_recommended'
            strategy['alternative_reason'] = 'Migrate from pip to system packages'
        
        return strategy
    
    def _calculate_coral_confidence(self, os_compatible: bool, hardware_present: bool, software_status: Dict[str, bool]) -> DetectionConfidence:
        """Calculate confidence level for Coral detection"""
        if not os_compatible:
            return DetectionConfidence.LOW
        
        if software_status['system_packages'] and hardware_present:
            return DetectionConfidence.HIGH
        elif software_status['system_packages'] or hardware_present:
            return DetectionConfidence.MEDIUM
        elif os_compatible:
            return DetectionConfidence.MEDIUM
        else:
            return DetectionConfidence.LOW
    
    def _get_recommended_coral_packages(self, os_compatible: bool) -> List[str]:
        """Get recommended package installation commands"""
        if not os_compatible:
            return []
        
        return [
            'sudo apt-get update',
            'sudo apt-get install -y python3-pycoral',
            'sudo apt-get install -y libedgetpu1-std'  # or libedgetpu1-max
        ]

    def _test_i2c_address(self, bus, address: int) -> bool:
        """Test if device responds at I2C address"""
        try:
            bus.read_byte(address)
            return True
        except:
            return False

    def _probe_tof_presence(self, bus, address: int) -> bool:
        """Conservative probe for VL53L0X presence without full init.
        Tries model id registers; falls back to a simple read ping.
        """
        # Try reading known ID registers (won't harm if device present)
        for reg in (0xC0, 0xC1):
            try:
                _ = bus.read_byte_data(address, reg)
                return True
            except Exception:
                continue
        # Final fallback: generic presence probe
        return self._test_i2c_address(bus, address)

    def _attempt_tof_readdress(self, bus) -> Optional[Dict[str, int]]:
        """Attempt to ensure left/right ToF are on 0x29 and 0x30 respectively using XSHUT pins.
        Returns a mapping {name: address} if successful, else None. Non-fatal on errors.
        """
        if not gpiozero:
            return None
        try:
            from gpiozero import OutputDevice
            # Pin mapping from project conventions
            left_xshut_pin = 22
            right_xshut_pin = 23

            left = OutputDevice(left_xshut_pin, active_high=True, initial_value=False)
            right = OutputDevice(right_xshut_pin, active_high=True, initial_value=False)

            # Reset both
            left.off(); right.off(); time.sleep(0.05)

            # Bring up RIGHT first alone at default 0x29, then readdress to 0x30
            right.on(); time.sleep(0.05)
            right_at_default = self._probe_tof_presence(bus, 0x29)
            if right_at_default:
                try:
                    # I2C_SLAVE__DEVICE_ADDRESS (0x8A) expects 7-bit address value
                    bus.write_byte_data(0x29, 0x8A, 0x30 & 0x7F)
                    time.sleep(0.02)
                except Exception:
                    # If write fails, proceed — detection will fall back later
                    pass
            # Verify right now at 0x30
            right_ok = self._probe_tof_presence(bus, 0x30)

            # Bring up LEFT, it should be at default 0x29 and not collide now
            left.on(); time.sleep(0.05)
            left_ok = self._probe_tof_presence(bus, 0x29)

            # Cleanup devices
            left.close(); right.close()

            result = {}
            if left_ok:
                result['tof_left'] = 0x29
            if right_ok:
                result['tof_right'] = 0x30
            return result if result else None
        except Exception:
            return None

    def _i2c_scan_addresses(self) -> List[int]:
        """Best-effort scan using i2cdetect for robustness; returns list of addresses.
        Uses a short timeout to avoid hangs on misbehaving buses.
        """
        addrs: List[int] = []
        try:
            result = subprocess.run(
                ['timeout', '5s', 'i2cdetect', '-y', '1'], capture_output=True, text=True
            )
            if result.returncode == 0 and result.stdout:
                for tok in result.stdout.split():
                    if len(tok) == 2 and all(c in '0123456789abcdef' for c in tok.lower()):
                        try:
                            addrs.append(int(tok, 16))
                        except Exception:
                            pass
        except Exception:
            # Ignore failures; fallback is empty list
            pass
        return sorted(set(a for a in addrs if 0x03 <= a <= 0x77))


async def main():
    """Main detection function"""
    detector = EnhancedHardwareDetector()
    
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
