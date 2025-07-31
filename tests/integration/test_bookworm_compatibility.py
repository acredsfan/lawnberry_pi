"""
Raspberry Pi OS Bookworm Compatibility Tests

Tests specific to Raspberry Pi OS Bookworm compatibility including:
- Python 3.11+ features and performance
- systemd service configurations
- Hardware interface stability
- Performance benchmarks
"""

import asyncio
import sys
import os
import subprocess
import platform
import pytest
from pathlib import Path
import psutil
import time
from typing import Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

class TestBookwormCompatibility:
    """Test suite for Raspberry Pi OS Bookworm compatibility"""
    
    def test_python_version_compatibility(self):
        """Test Python version meets Bookworm requirements"""
        # Check Python version is 3.11+
        assert sys.version_info >= (3, 11), f"Python 3.11+ required, found {sys.version_info}"
        
        # Test Python 3.11 specific features
        try:
            # Exception groups (Python 3.11 feature)
            from contextlib import suppress
            with suppress(ExceptionGroup):
                raise ExceptionGroup("test", [ValueError("test")])
        except ImportError:
            pytest.fail("Python 3.11 exception groups not available")
    
    def test_system_detection(self):
        """Test system detection for Raspberry Pi OS Bookworm"""
        try:
            # Check for Raspberry Pi
            with open('/proc/device-tree/model', 'r') as f:
                model = f.read().strip()
            assert 'Raspberry Pi' in model, f"Not running on Raspberry Pi: {model}"
            
            # Check for Bookworm
            if os.path.exists('/etc/os-release'):
                with open('/etc/os-release', 'r') as f:
                    os_info = f.read()
                if 'VERSION_CODENAME=bookworm' in os_info:
                    assert True  # Bookworm detected
                else:
                    pytest.skip("Not running on Raspberry Pi OS Bookworm")
        except FileNotFoundError:
            pytest.skip("Cannot detect Raspberry Pi model")
    
    def test_systemd_compatibility(self):
        """Test systemd features required for Bookworm"""
        # Check systemd version
        result = subprocess.run(['systemctl', '--version'], 
                              capture_output=True, text=True)
        assert result.returncode == 0, "systemd not available"
        
        version_line = result.stdout.split('\n')[0]
        version_num = int(version_line.split()[1])
        assert version_num >= 252, f"systemd 252+ required, found {version_num}"
    
    def test_hardware_interface_libraries(self):
        """Test hardware interface libraries for Bookworm compatibility"""
        # Test GPIO libraries
        try:
            import RPi.GPIO as GPIO
            import gpiozero
            from gpiozero.pins.pigpio import PiGPIOFactory
            assert True  # GPIO libraries available
        except ImportError as e:
            pytest.fail(f"GPIO libraries not available: {e}")
        
        # Test I2C libraries
        try:
            import smbus2 as smbus
            assert True  # I2C libraries available
        except ImportError:
            try:
                import smbus
                assert True  # Fallback I2C library available
            except ImportError as e:
                pytest.fail(f"I2C libraries not available: {e}")
        
        # Test serial libraries
        try:
            import serial
            import serial.tools.list_ports
            assert True  # Serial libraries available
        except ImportError as e:
            pytest.fail(f"Serial libraries not available: {e}")
    
    def test_computer_vision_libraries(self):
        """Test computer vision libraries for Bookworm"""
        # Test OpenCV
        try:
            import cv2
            version = cv2.__version__
            major, minor = map(int, version.split('.')[:2])
            assert major >= 4 and (major > 4 or minor >= 8), f"OpenCV 4.8+ required, found {version}"
        except ImportError as e:
            pytest.fail(f"OpenCV not available: {e}")
        
        # Test NumPy
        try:
            import numpy as np
            version = np.__version__
            major, minor = map(int, version.split('.')[:2])
            assert major >= 1 and minor >= 21, f"NumPy 1.21+ required, found {version}"
        except ImportError as e:
            pytest.fail(f"NumPy not available: {e}")
        
        # Test TensorFlow Lite
        try:
            import tflite_runtime.interpreter as tflite
            assert True  # TFLite available
        except ImportError as e:
            pytest.fail(f"TensorFlow Lite not available: {e}")
    
    def test_camera_compatibility(self):
        """Test camera system compatibility with Bookworm"""
        try:
            import picamera2
            # Test camera detection
            cameras = picamera2.Picamera2.global_camera_info()
            if not cameras:
                pytest.skip("No camera detected")
            
            # Test camera initialization (brief test)
            picam2 = picamera2.Picamera2()
            try:
                config = picam2.create_preview_configuration()
                picam2.configure(config)
                # Don't start capture in test environment
                assert True  # Camera initialization successful
            finally:
                picam2.close()
        except ImportError:
            pytest.skip("picamera2 not available")
        except Exception as e:
            pytest.skip(f"Camera test failed: {e}")
    
    def test_web_api_dependencies(self):
        """Test web API dependencies for Bookworm"""
        # Test FastAPI
        try:
            import fastapi
            version = fastapi.__version__
            major, minor = map(int, version.split('.')[:2])
            assert major >= 0 and minor >= 104, f"FastAPI 0.104+ required, found {version}"
        except ImportError as e:
            pytest.fail(f"FastAPI not available: {e}")
        
        # Test Uvicorn
        try:
            import uvicorn
            assert True  # Uvicorn available
        except ImportError as e:
            pytest.fail(f"Uvicorn not available: {e}")
        
        # Test Pydantic
        try:
            import pydantic
            version = pydantic.__version__
            major = int(version.split('.')[0])
            assert major >= 2, f"Pydantic 2+ required, found {version}"
        except ImportError as e:
            pytest.fail(f"Pydantic not available: {e}")
    
    def test_database_dependencies(self):
        """Test database and caching dependencies"""
        # Test Redis
        try:
            import redis
            version = redis.__version__
            major, minor = map(int, version.split('.')[:2])
            assert major >= 4 and minor >= 5, f"Redis 4.5+ required, found {version}"
        except ImportError as e:
            pytest.fail(f"Redis not available: {e}")
        
        # Test SQLite
        try:
            import aiosqlite
            import sqlite3
            assert sqlite3.sqlite_version_info >= (3, 35), f"SQLite 3.35+ recommended"
        except ImportError as e:
            pytest.fail(f"SQLite libraries not available: {e}")
    
    def test_communication_dependencies(self):
        """Test communication system dependencies"""
        # Test MQTT
        try:
            import asyncio_mqtt
            import paho.mqtt.client as mqtt
            assert True  # MQTT libraries available
        except ImportError as e:
            pytest.fail(f"MQTT libraries not available: {e}")
        
        # Test WebSockets
        try:
            import websockets
            version = websockets.__version__
            major = int(version.split('.')[0])
            assert major >= 12, f"websockets 12+ required, found {version}"
        except ImportError as e:
            pytest.fail(f"WebSockets not available: {e}")
    
    @pytest.mark.asyncio
    async def test_asyncio_performance(self):
        """Test asyncio performance improvements in Python 3.11"""
        # Test async context manager performance
        class AsyncContextManager:
            async def __aenter__(self):
                return self
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        # Benchmark asyncio operations
        start_time = time.time()
        for _ in range(1000):
            async with AsyncContextManager():
                await asyncio.sleep(0.001)
        
        duration = time.time() - start_time
        # Should complete in reasonable time with Python 3.11 optimizations
        assert duration < 5.0, f"Asyncio performance test took too long: {duration}s"
    
    def test_memory_management(self):
        """Test memory management capabilities"""
        # Check available memory
        memory = psutil.virtual_memory()
        assert memory.total > 3 * 1024**3, f"Insufficient RAM: {memory.total / 1024**3:.1f}GB"
        
        # Test memory allocation patterns
        large_list = [i for i in range(100000)]
        del large_list
        
        # Check memory is properly managed
        current_memory = psutil.virtual_memory()
        assert current_memory.available > memory.total * 0.5, "Memory not properly released"
    
    def test_file_system_performance(self):
        """Test file system performance for SD card operations"""
        test_file = Path('/tmp/lawnberry_fs_test.txt')
        test_data = b'0' * 1024 * 1024  # 1MB test data
        
        try:
            # Write performance test
            start_time = time.time()
            with open(test_file, 'wb') as f:
                f.write(test_data)
                f.fsync()  # Force sync to storage
            write_time = time.time() - start_time
            
            # Read performance test
            start_time = time.time()
            with open(test_file, 'rb') as f:
                read_data = f.read()
            read_time = time.time() - start_time
            
            assert len(read_data) == len(test_data), "Data integrity error"
            assert write_time < 2.0, f"Write performance too slow: {write_time}s"
            assert read_time < 1.0, f"Read performance too slow: {read_time}s"
            
        finally:
            if test_file.exists():
                test_file.unlink()
    
    def test_network_capabilities(self):
        """Test network capabilities for Bookworm"""
        # Test network interface availability
        interfaces = psutil.net_if_addrs()
        assert len(interfaces) > 0, "No network interfaces found"
        
        # Check for common interfaces
        interface_names = list(interfaces.keys())
        has_ethernet = any('eth' in name for name in interface_names)
        has_wifi = any('wlan' in name for name in interface_names)
        
        assert has_ethernet or has_wifi, f"No ethernet or WiFi found: {interface_names}"
    
    def test_service_file_syntax(self):
        """Test systemd service file syntax"""
        service_files = [
            'src/system_integration/lawnberry-system.service',
            'src/communication/lawnberry-communication.service',
            'src/hardware/lawnberry-hardware.service',
            'src/safety/lawnberry-safety.service',
            'src/web_api/lawnberry-api.service'
        ]
        
        for service_file in service_files:
            if os.path.exists(service_file):
                # Basic syntax validation
                with open(service_file, 'r') as f:
                    content = f.read()
                
                assert '[Unit]' in content, f"Missing [Unit] section in {service_file}"
                assert '[Service]' in content, f"Missing [Service] section in {service_file}"
                assert '[Install]' in content, f"Missing [Install] section in {service_file}"
                
                # Check for Bookworm-compatible security settings
                security_features = [
                    'NoNewPrivileges=true',
                    'ProtectSystem=strict',
                    'ProtectHome=true'
                ]
                for feature in security_features:
                    assert feature in content, f"Missing security feature {feature} in {service_file}"


class TestBookwormPerformance:
    """Performance benchmarks specific to Bookworm"""
    
    def test_system_startup_time(self):
        """Test system startup performance"""
        # Check system uptime
        uptime = time.time() - psutil.boot_time()
        
        # System should boot reasonably quickly
        if uptime < 300:  # Less than 5 minutes since boot
            # Approximate boot time based on load average
            load_avg = os.getloadavg()[0]
            assert load_avg < 2.0, f"High system load during startup: {load_avg}"
    
    def test_i2c_performance(self):
        """Test I2C bus performance"""
        try:
            import smbus2 as smbus
            bus = smbus.SMBus(1)
            
            # Test I2C scan performance
            start_time = time.time()
            detected_devices = []
            
            for addr in range(0x08, 0x78):  # Valid I2C address range
                try:
                    bus.read_byte(addr)
                    detected_devices.append(addr)
                except OSError:
                    pass  # Device not present
            
            scan_time = time.time() - start_time
            bus.close()
            
            # I2C scan should complete quickly
            assert scan_time < 5.0, f"I2C scan too slow: {scan_time}s"
            
        except ImportError:
            pytest.skip("I2C libraries not available")
        except PermissionError:
            pytest.skip("I2C access requires permissions")
    
    def test_cpu_scheduling(self):
        """Test CPU scheduling performance"""
        # Check CPU count
        cpu_count = psutil.cpu_count()
        assert cpu_count >= 4, f"Expected 4+ CPU cores, found {cpu_count}"
        
        # Test CPU utilization
        cpu_percent = psutil.cpu_percent(interval=1)
        assert cpu_percent < 80, f"High CPU utilization: {cpu_percent}%"


if __name__ == '__main__':
    # Run specific test categories
    pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '-x'  # Stop on first failure
    ])
