"""
Pytest configuration and shared fixtures for the testing framework.
Provides common test utilities, mock hardware interfaces, and test data.
"""

import asyncio
import json
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import yaml

# Import all the main modules for testing
from src.communication import MQTTClient
from src.data_management.data_manager import DataManager
from src.hardware.hardware_interface import HardwareInterface
from src.power_management.power_manager import PowerManager
from src.safety.safety_service import SafetyConfig, SafetyService
from src.sensor_fusion.fusion_engine import SensorFusionEngine
from src.vision.vision_manager import VisionManager
from src.weather.weather_service import WeatherService


# Test configurations
@pytest.fixture(scope="session")
def test_config():
    """Provide comprehensive test configuration"""
    return {
        "hardware": {"i2c_bus": 1, "mock_mode": True, "retry_attempts": 3, "timeout_ms": 1000},
        "safety": {
            "emergency_response_time_ms": 100,
            "person_safety_radius_m": 3.0,
            "pet_safety_radius_m": 1.5,
            "max_safe_tilt_deg": 15.0,
            "critical_tilt_deg": 25.0,
        },
        "sensor_fusion": {
            "update_rate_hz": 20,
            "gps_timeout_s": 5.0,
            "imu_timeout_s": 1.0,
            "localization_accuracy_m": 0.2,
        },
        "power": {
            "critical_battery_level": 0.15,
            "low_battery_level": 0.20,
            "charging_current_limit_a": 5.0,
        },
        "vision": {
            "detection_confidence_threshold": 0.7,
            "max_detection_distance_m": 10.0,
            "frame_rate_fps": 30,
        },
    }


# Mock Hardware Fixtures
@pytest.fixture
def mock_i2c_device():
    """Mock I2C device for sensor testing"""
    device = Mock()
    device.read_register = Mock(return_value=0x42)
    device.write_register = Mock()
    device.read_block = Mock(return_value=[0x01, 0x02, 0x03, 0x04])
    device.write_block = Mock()
    return device


@pytest.fixture
def mock_gpio():
    """Mock lgpio interface"""
    gpio = Mock()
    gpio.gpiochip_open = Mock(return_value=1)
    gpio.gpio_claim_output = Mock()
    gpio.gpio_claim_input = Mock()
    gpio.gpio_write = Mock()
    gpio.gpio_read = Mock(return_value=0)
    gpio.gpiochip_close = Mock()
    return gpio


@pytest.fixture
def mock_serial():
    """Mock serial interface for UART communication"""
    serial = Mock()
    serial.write = Mock()
    serial.read = Mock(return_value=b"OK\r\n")
    serial.readline = Mock(return_value=b"status=ready\r\n")
    serial.in_waiting = 10
    serial.is_open = True
    return serial


@pytest.fixture
def mock_camera():
    """Mock camera interface"""
    import numpy as np

    camera = Mock()
    # Create a fake 640x480 RGB image
    fake_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    camera.read = Mock(return_value=(True, fake_frame))
    camera.isOpened = Mock(return_value=True)
    camera.release = Mock()
    camera.set = Mock()
    camera.get = Mock(return_value=30.0)  # FPS
    return camera


# Service Fixtures
@pytest.fixture
async def mqtt_client():
    """Mock MQTT client for communication testing"""
    client = Mock(spec=MQTTClient)
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.subscribe = AsyncMock()
    client.publish = AsyncMock(return_value=True)
    client.is_connected = True
    return client


@pytest.fixture
async def hardware_interface(test_config, mock_i2c_device, mock_gpio, mock_serial):
    """Mock hardware interface with all sensors"""
    with (
        patch("src.hardware.managers.smbus.SMBus") as mock_smbus,
        patch("src.hardware.managers.lgpio", mock_gpio),
        patch("src.hardware.managers.serial.Serial", return_value=mock_serial),
    ):

        mock_smbus.return_value = mock_i2c_device

        interface = HardwareInterface(test_config["hardware"])
        await interface.initialize()
        yield interface
        await interface.shutdown()


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
    if hasattr(engine, "_running") and engine._running:
        await engine.stop()


@pytest.fixture
async def vision_manager(mqtt_client, test_config, mock_camera):
    """Vision manager with mock camera"""
    with patch("cv2.VideoCapture", return_value=mock_camera):
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
            "timestamp": datetime.now().isoformat(),
        },
        "imu": {
            "acceleration": {"x": 0.1, "y": 0.2, "z": 9.8},
            "gyroscope": {"x": 0.01, "y": -0.02, "z": 0.005},
            "magnetometer": {"x": 25.0, "y": -15.0, "z": 45.0},
            "orientation": {"roll": 2.0, "pitch": 1.5, "yaw": 180.0},
            "timestamp": datetime.now().isoformat(),
        },
        "tof_sensors": {
            "front_left": {"distance_mm": 500, "status": "valid"},
            "front_right": {"distance_mm": 480, "status": "valid"},
        },
        "environmental": {
            "temperature_c": 22.5,
            "humidity_percent": 65.0,
            "pressure_hpa": 1013.25,
            "timestamp": datetime.now().isoformat(),
        },
        "power": {
            "voltage_v": 12.6,
            "current_a": 2.3,
            "power_w": 28.98,
            "battery_level": 0.85,
            "timestamp": datetime.now().isoformat(),
        },
    }


@pytest.fixture
def sample_map_data():
    """Generate sample map and boundary data"""
    return {
        "boundaries": [
            {"lat": 40.7128, "lng": -74.0060},
            {"lat": 40.7130, "lng": -74.0060},
            {"lat": 40.7130, "lng": -74.0058},
            {"lat": 40.7128, "lng": -74.0058},
        ],
        "no_go_zones": [
            {
                "name": "flower_bed",
                "polygon": [
                    {"lat": 40.7129, "lng": -74.0059},
                    {"lat": 40.7129, "lng": -74.0058},
                    {"lat": 40.7128, "lng": -74.0058},
                    {"lat": 40.7128, "lng": -74.0059},
                ],
            }
        ],
        "home_position": {"lat": 40.7128, "lng": -74.0060},
        "coverage_grid": {
            "resolution_m": 0.1,
            "grid_size": {"width": 100, "height": 80},
            "covered_cells": [],
        },
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
    import time

    import psutil

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
                "cpu_usage_percent": (end_cpu + self.start_cpu) / 2,
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
            "max_response_time_ms": 100,
        },
        "pet_detection": {
            "hazard_type": "pet",
            "distance_m": 1.0,
            "expected_response": "emergency_stop",
            "max_response_time_ms": 100,
        },
        "cliff_detection": {
            "hazard_type": "cliff",
            "sensor_reading": 2000,  # > 2m drop
            "expected_response": "emergency_stop",
            "max_response_time_ms": 100,
        },
        "tilt_detection": {
            "hazard_type": "tilt",
            "tilt_angle_deg": 20.0,
            "expected_response": "emergency_stop",
            "max_response_time_ms": 100,
        },
        "boundary_violation": {
            "hazard_type": "boundary",
            "position": {"lat": 40.7131, "lng": -74.0061},  # Outside boundary
            "expected_response": "boundary_stop",
            "max_response_time_ms": 200,
        },
    }


# Async Test Utilities
@pytest.fixture
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Cleanup fixture
@pytest.fixture(autouse=True)
async def cleanup_background_tasks():
    """Ensure all background tasks are cleaned up after tests"""
    yield

    # Cancel any remaining tasks
    tasks = [task for task in asyncio.all_tasks() if not task.done()]
    for task in tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
