import asyncio
import inspect
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
import pytest

# Basic pytest configuration
def pytest_configure(config):
    # Markers are already configured in pytest.ini; keep lightweight customization only
    config.addinivalue_line("markers", "asyncio: mark async tests")


# Mock hardware fixtures
@pytest.fixture
def mock_i2c_device():
    device = Mock()
    device.read_register = Mock(return_value=0x42)
    device.write_register = Mock()
    device.read_block = Mock(return_value=[0x01, 0x02, 0x03, 0x04])
    device.write_block = Mock()
    return device


@pytest.fixture
def mock_gpio():
    gpio = Mock()
    gpio.setup = Mock()
    gpio.output = Mock()
    gpio.input = Mock(return_value=0)
    gpio.add_event_detect = Mock()
    gpio.remove_event_detect = Mock()
    return gpio


@pytest.fixture
def mock_serial():
    serial = Mock()
    serial.write = Mock()
    serial.read = Mock(return_value=b"OK\r\n")
    serial.readline = Mock(return_value=b"status=ready\r\n")
    serial.in_waiting = 10
    serial.is_open = True
    return serial


@pytest.fixture
def mock_camera():
    import numpy as np
    camera = Mock()
    fake_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    camera.read = Mock(return_value=(True, fake_frame))
    camera.isOpened = Mock(return_value=True)
    camera.release = Mock()
    camera.set = Mock()
    camera.get = Mock(return_value=30.0)
    return camera


# Common service fixtures
@pytest.fixture
async def mqtt_client():
    client = Mock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.subscribe = AsyncMock()
    client.publish = AsyncMock(return_value=True)
    client.is_connected = True
    return client


@pytest.fixture
async def hardware_interface(mock_i2c_device, mock_gpio, mock_serial):
    # Patch lower-level hardware managers that may touch system resources
    with patch('src.hardware.managers.smbus.SMBus') as mock_smbus, \
         patch('src.hardware.managers.GPIO', mock_gpio), \
         patch('src.hardware.managers.serial.Serial', return_value=mock_serial):
        mock_smbus.return_value = mock_i2c_device
        from src.hardware.hardware_interface import HardwareInterface
        interface = HardwareInterface({'mock_mode': True})
        await interface.initialize()
        yield interface
        await interface.shutdown()


@pytest.fixture(autouse=True)
async def cleanup_background_tasks():
    """Ensure all background tasks are cleaned up after tests (single definition)."""
    yield
    # Cancel any remaining tasks created by tests to avoid bleed-over
    tasks = [t for t in asyncio.all_tasks() if not t.done()]
    for t in tasks:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
@pytest.fixture
async def safety_service(mqtt_client, test_config):
    """Safety service with mock dependencies"""
    config = SafetyConfig(**test_config["safety"])
    service = SafetyService(mqtt_client, config)
    yield service
    if service._running:
        await service.stop()


@pytest.fixture
async def sensor_fusion_engine(mqtt_client, test_config):
    """Sensor fusion engine with mock data"""
    engine = SensorFusionEngine(mqtt_client, test_config["sensor_fusion"])
    yield engine
    if hasattr(engine, '_running') and engine._running:
        await engine.stop()


@pytest.fixture
async def vision_manager(mqtt_client, test_config, mock_camera):
    """Vision manager with mock camera"""
    with patch('cv2.VideoCapture', return_value=mock_camera):
        manager = VisionManager(mqtt_client, test_config["vision"])
        await manager.initialize()
        yield manager
        await manager.shutdown()


# Test Data Fixtures
@pytest.fixture
def sample_sensor_data():
    """Generate sample sensor data for testing"""
    return {
        "gps": {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "altitude": 10.0,
            "accuracy": 2.5,
            "timestamp": datetime.now().isoformat()
        },
        "imu": {
            "acceleration": {"x": 0.1, "y": 0.2, "z": 9.8},
            "gyroscope": {"x": 0.01, "y": -0.02, "z": 0.005},
            "magnetometer": {"x": 25.0, "y": -15.0, "z": 45.0},
            "orientation": {"roll": 2.0, "pitch": 1.5, "yaw": 180.0},
            "timestamp": datetime.now().isoformat()
        },
        "tof_sensors": {
            "front_left": {"distance_mm": 500, "status": "valid"},
            "front_right": {"distance_mm": 480, "status": "valid"}
        },
        "environmental": {
            "temperature_c": 22.5,
            "humidity_percent": 65.0,
            "pressure_hpa": 1013.25,
            "timestamp": datetime.now().isoformat()
        },
        "power": {
            "voltage_v": 12.6,
            "current_a": 2.3,
            "power_w": 28.98,
            "battery_level": 0.85,
            "timestamp": datetime.now().isoformat()
        }
    }


@pytest.fixture
def sample_map_data():
    """Generate sample map and boundary data"""
    return {
        "boundaries": [
            {"lat": 40.7128, "lng": -74.0060},
            {"lat": 40.7130, "lng": -74.0060},
            {"lat": 40.7130, "lng": -74.0058},
            {"lat": 40.7128, "lng": -74.0058}
        ],
        "no_go_zones": [
            {
                "name": "flower_bed",
                "polygon": [
                    {"lat": 40.7129, "lng": -74.0059},
                    {"lat": 40.7129, "lng": -74.0058},
                    {"lat": 40.7128, "lng": -74.0058},
                    {"lat": 40.7128, "lng": -74.0059}
                ]
            }
        ],
        "home_position": {"lat": 40.7128, "lng": -74.0060},
        "coverage_grid": {
            "resolution_m": 0.1,
            "grid_size": {"width": 100, "height": 80},
            "covered_cells": []
        }
    }


# Test Environment Fixtures
@pytest.fixture
def temp_config_dir():
    """Create temporary configuration directory"""
    temp_dir = tempfile.mkdtemp(prefix="lawnberry_test_")
    config_dir = Path(temp_dir) / "config"
    config_dir.mkdir(parents=True)
    
    yield config_dir
    
    shutil.rmtree(temp_dir)


@pytest.fixture
def temp_data_dir():
    """Create temporary data directory"""
    temp_dir = tempfile.mkdtemp(prefix="lawnberry_data_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


# Performance Testing Utilities
@pytest.fixture
def performance_monitor():
    """Monitor performance metrics during tests"""
    import psutil
    import time
    
    class PerformanceMonitor:
        def __init__(self):
            self.start_time = None
            self.start_memory = None
            self.start_cpu = None
            
        def start(self):
            self.start_time = time.time()
            self.start_memory = psutil.virtual_memory().available
            self.start_cpu = psutil.cpu_percent()
            
        def stop(self):
            end_time = time.time()
            end_memory = psutil.virtual_memory().available
            end_cpu = psutil.cpu_percent()
            
            return {
                "duration_s": end_time - self.start_time,
                "memory_used_mb": (self.start_memory - end_memory) / 1024 / 1024,
                "cpu_usage_percent": (end_cpu + self.start_cpu) / 2
            }
    
    return PerformanceMonitor()


# Safety Test Utilities
@pytest.fixture
def safety_test_scenarios():
    """Predefined safety test scenarios"""
    return {
        "person_detection": {
            "hazard_type": "person",
            "distance_m": 2.5,
            "expected_response": "emergency_stop",
            "max_response_time_ms": 100
        },
        "pet_detection": {
            "hazard_type": "pet",
            "distance_m": 1.0,
            "expected_response": "emergency_stop",
            "max_response_time_ms": 100
        },
        "cliff_detection": {
            "hazard_type": "cliff",
            "sensor_reading": 2000,  # > 2m drop
            "expected_response": "emergency_stop",
            "max_response_time_ms": 100
        },
        "tilt_detection": {
            "hazard_type": "tilt",
            "tilt_angle_deg": 20.0,
            "expected_response": "emergency_stop",
            "max_response_time_ms": 100
        },
        "boundary_violation": {
            "hazard_type": "boundary",
            "position": {"lat": 40.7131, "lng": -74.0061},  # Outside boundary
            "expected_response": "boundary_stop",
            "max_response_time_ms": 200
        }
    }


# Async Test Utilities


# Note: Duplicate cleanup fixture removed above to prevent redefinition warnings
