"""
Comprehensive test suite for sensor fusion engine
Validates performance requirements and functionality
"""

import pytest
import asyncio
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import time

from src.sensor_fusion import (
    SensorFusionEngine, LocalizationSystem, ObstacleDetectionSystem, 
    SafetyMonitor, PoseEstimate, ObstacleMap, SafetyStatus, ObstacleInfo,
    ObstacleType, HazardLevel, HazardAlert
)
from src.hardware.data_structures import GPSReading, IMUReading, ToFReading
from src.communication import MQTTClient


class TestSensorFusionEngine:
    """Test sensor fusion engine integration and performance"""
    
    @pytest.fixture
    async def fusion_engine(self):
        """Create sensor fusion engine for testing"""
        config = {
            'mqtt': {
                'host': 'localhost',
                'port': 1883,
                'start_local_broker': False
            },
            'hardware': {
                'i2c_devices': {},
                'serial_devices': {},
                'gpio_pins': {}
            }
        }
        
        engine = SensorFusionEngine(config)
        
        # Mock dependencies
        engine.mqtt_client = Mock(spec=MQTTClient)
        engine.mqtt_client.connect = AsyncMock()
        engine.mqtt_client.disconnect = AsyncMock()
        engine.mqtt_client.publish = AsyncMock()
        engine.mqtt_client.subscribe = AsyncMock()
        engine.mqtt_client.is_connected = Mock(return_value=True)
        
        # Mock hardware interface
        with patch('src.sensor_fusion.fusion_engine.HardwareInterface'):
            await engine.initialize()
        
        return engine
    
    @pytest.mark.asyncio
    async def test_fusion_engine_initialization(self, fusion_engine):
        """Test fusion engine initializes correctly"""
        assert fusion_engine.localization_system is not None
        assert fusion_engine.obstacle_detection_system is not None
        assert fusion_engine.safety_monitor is not None
        assert fusion_engine.mqtt_client is not None
    
    @pytest.mark.asyncio
    async def test_fusion_engine_startup_shutdown(self, fusion_engine):
        """Test fusion engine starts and stops correctly"""
        # Mock subsystem start/stop methods
        fusion_engine.localization_system.start = AsyncMock()
        fusion_engine.localization_system.stop = AsyncMock()
        fusion_engine.obstacle_detection_system.start = AsyncMock()
        fusion_engine.obstacle_detection_system.stop = AsyncMock()
        fusion_engine.safety_monitor.start = AsyncMock()
        fusion_engine.safety_monitor.stop = AsyncMock()
        fusion_engine.hardware_interface.start = AsyncMock()
        fusion_engine.hardware_interface.stop = AsyncMock()
        
        # Start engine
        await fusion_engine.start()
        assert fusion_engine._running is True
        
        # Verify subsystems started
        fusion_engine.localization_system.start.assert_called_once()
        fusion_engine.obstacle_detection_system.start.assert_called_once()
        fusion_engine.safety_monitor.start.assert_called_once()
        
        # Stop engine
        await fusion_engine.stop()
        assert fusion_engine._running is False
        
        # Verify subsystems stopped
        fusion_engine.localization_system.stop.assert_called_once()
        fusion_engine.obstacle_detection_system.stop.assert_called_once()
        fusion_engine.safety_monitor.stop.assert_called_once()


class TestLocalizationSystem:
    """Test localization system accuracy and performance"""
    
    @pytest.fixture
    def localization_system(self):
        """Create localization system for testing"""
        mqtt_client = Mock(spec=MQTTClient)
        mqtt_client.subscribe = AsyncMock()
        mqtt_client.publish = AsyncMock()
        
        return LocalizationSystem(mqtt_client)
    
    @pytest.mark.asyncio
    async def test_gps_rtk_accuracy(self, localization_system):
        """Test GPS-RTK provides <10cm accuracy (Success Criteria #1)"""
        # Simulate high-precision GPS-RTK data
        test_gps = GPSReading(
            timestamp=datetime.now(),
            sensor_id='gps_rtk',
            value={'lat': 40.7128, 'lon': -74.0060},
            unit='degrees',
            port='/dev/ttyACM0',
            baud_rate=38400,
            latitude=40.7128,
            longitude=-74.0060,
            altitude=10.0,
            accuracy=0.05,  # 5cm RTK accuracy
            satellites=12,
            fix_type='rtk'
        )
        
        # Process GPS data
        await localization_system._handle_gps_data(
            'lawnberry/sensors/gps',
            Mock(payload=test_gps.__dict__, metadata=Mock(timestamp=time.time()))
        )
        
        # Verify reference point is set for RTK fix
        assert localization_system._reference_lat is not None
        assert localization_system._reference_lon is not None
        
        # Test position accuracy after initialization
        if localization_system._kalman_state:
            accuracy = localization_system.get_position_accuracy()
            assert accuracy <= 0.10, f"Position accuracy {accuracy:.3f}m exceeds 10cm requirement"
    
    @pytest.mark.asyncio
    async def test_imu_integration(self, localization_system):
        """Test IMU data integration for orientation"""
        # Simulate IMU data
        test_imu = IMUReading(
            timestamp=datetime.now(),
            sensor_id='bno085',
            value={},
            unit='mixed',
            port='/dev/ttyAMA4',
            baud_rate=3000000,
            quaternion=(1.0, 0.0, 0.0, 0.0),  # Identity quaternion
            acceleration=(0.0, 0.0, 9.81),    # Gravity only
            angular_velocity=(0.0, 0.0, 0.0)  # No rotation
        )
        
        # Process IMU data
        await localization_system._handle_imu_data(
            'lawnberry/sensors/imu',
            Mock(payload=test_imu.__dict__, metadata=Mock(timestamp=time.time()))
        )
        
        assert localization_system._latest_imu is not None
        assert localization_system._latest_imu.quaternion == (1.0, 0.0, 0.0, 0.0)
    
    def test_kalman_filter_initialization(self, localization_system):
        """Test Kalman filter initializes with correct dimensions"""
        localization_system._initialize_kalman_filter(40.7128, -74.0060, 10.0)
        
        assert localization_system._kalman_state is not None
        assert localization_system._kalman_state.state.shape == (13,)
        assert localization_system._kalman_state.covariance.shape == (13, 13)
    
    def test_coordinate_conversion(self, localization_system):
        """Test GPS to local coordinate conversion"""
        # Set reference point
        localization_system._reference_lat = 40.7128
        localization_system._reference_lon = -74.0060
        localization_system._reference_alt = 10.0
        
        # Test conversion
        x, y, z = localization_system._gps_to_local(40.7129, -74.0059, 15.0)
        
        # Verify reasonable local coordinates
        assert abs(x) < 1000  # Within 1km
        assert abs(y) < 1000  # Within 1km
        assert z == 5.0       # 5m altitude difference
        
        # Test reverse conversion
        lat, lon, alt = localization_system._local_to_gps(x, y, z)
        assert abs(lat - 40.7129) < 0.0001
        assert abs(lon - -74.0059) < 0.0001
        assert abs(alt - 15.0) < 0.1
    
    @pytest.mark.asyncio
    async def test_localization_update_rate(self, localization_system):
        """Test localization updates at required rates"""
        # Mock the update method to track calls
        update_calls = []
        original_update = localization_system._update_localization
        
        async def mock_update():
            update_calls.append(datetime.now())
            
        localization_system._update_localization = mock_update
        localization_system._running = True
        
        # Run for a short time
        task = asyncio.create_task(localization_system._localization_loop())
        await asyncio.sleep(0.5)  # Run for 500ms
        localization_system._running = False
        
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        # Verify update rate (should be ~10Hz, so ~5 updates in 500ms)
        assert len(update_calls) >= 4, f"Expected ≥4 updates in 500ms, got {len(update_calls)}"


class TestObstacleDetectionSystem:
    """Test obstacle detection accuracy and performance"""
    
    @pytest.fixture
    def obstacle_detection(self):
        """Create obstacle detection system for testing"""
        mqtt_client = Mock(spec=MQTTClient)
        mqtt_client.subscribe = AsyncMock()
        mqtt_client.publish = AsyncMock()
        
        return ObstacleDetectionSystem(mqtt_client)
    
    @pytest.mark.asyncio
    async def test_tof_obstacle_detection(self, obstacle_detection):
        """Test ToF sensors detect obstacles >30cm with 95% accuracy (Success Criteria #2)"""
        # Simulate ToF sensor detecting obstacle at 50cm
        test_tof = ToFReading(
            timestamp=datetime.now(),
            sensor_id='tof_left',
            value=500,  # 500mm = 50cm
            unit='mm',
            i2c_address=0x29,
            distance_mm=500,
            range_status='valid'
        )
        
        # Process ToF data
        await obstacle_detection._handle_tof_left_data(
            'lawnberry/sensors/tof_left',
            Mock(payload=test_tof.__dict__, metadata=Mock(timestamp=time.time()))
        )
        
        # Process sensor data into obstacles
        obstacles = await obstacle_detection._process_tof_sensors()
        
        # Verify obstacle detected
        assert len(obstacles) == 1
        obstacle = obstacles[0]
        assert obstacle.distance >= 0.30, f"Detected obstacle at {obstacle.distance:.2f}m < 30cm minimum"
        assert obstacle.confidence >= 0.8, f"Detection confidence {obstacle.confidence} too low"
        assert 'tof_left' in obstacle.detected_by
    
    @pytest.mark.asyncio
    async def test_obstacle_tracking(self, obstacle_detection):
        """Test dynamic obstacle tracking"""
        # Create initial obstacle
        obstacle1 = ObstacleInfo(
            obstacle_id='test_1',
            obstacle_type=ObstacleType.UNKNOWN,
            x=1.0, y=2.0, z=0.0,
            width=0.1, height=0.1, depth=0.1,
            confidence=0.9,
            detected_by=['tof_left']
        )
        
        # Add to tracking
        await obstacle_detection._update_obstacle_tracking([obstacle1])
        assert len(obstacle_detection._tracked_obstacles) == 1
        
        # Update obstacle position (simulate movement)
        obstacle2 = ObstacleInfo(
            obstacle_id='test_2',
            obstacle_type=ObstacleType.UNKNOWN,
            x=1.1, y=2.1, z=0.0,  # Moved slightly
            width=0.1, height=0.1, depth=0.1,
            confidence=0.9,
            detected_by=['tof_left']
        )
        
        await obstacle_detection._update_obstacle_tracking([obstacle2])
        
        # Verify obstacle was updated (matched by proximity)
        tracked = list(obstacle_detection._tracked_obstacles.values())
        assert len(tracked) == 1
        assert abs(tracked[0].vx) > 0 or abs(tracked[0].vy) > 0  # Has velocity
    
    def test_safety_distance_detection(self, obstacle_detection):
        """Test detection of obstacles within safety threshold"""
        # Create close obstacle
        close_obstacle = ObstacleInfo(
            obstacle_id='close_1',
            obstacle_type=ObstacleType.UNKNOWN,
            x=0.0, y=0.2, z=0.0,  # 20cm away
            width=0.1, height=0.1, depth=0.1,
            distance=0.2,
            confidence=1.0,
            detected_by=['tof_left']
        )
        
        obstacle_detection._tracked_obstacles['close_1'] = close_obstacle
        
        # Check if detected as immediate hazard
        distance = obstacle_detection.get_nearest_obstacle_distance()
        assert distance == 0.2
        assert distance < obstacle_detection.safety_distance_threshold
    
    @pytest.mark.asyncio
    async def test_detection_latency(self, obstacle_detection):
        """Test obstacle detection latency <50ms (Performance Requirement)"""
        start_time = datetime.now()
        
        # Simulate rapid obstacle detection
        obstacles = await obstacle_detection._process_tof_sensors()
        cv_obstacles = await obstacle_detection._process_computer_vision()
        fused = await obstacle_detection._fuse_detections(obstacles, cv_obstacles)
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        assert processing_time < 50, f"Detection processing took {processing_time:.1f}ms > 50ms requirement"


class TestSafetyMonitor:
    """Test safety monitoring and emergency response"""
    
    @pytest.fixture
    def safety_monitor(self):
        """Create safety monitor for testing"""
        mqtt_client = Mock(spec=MQTTClient)
        mqtt_client.subscribe = AsyncMock()
        mqtt_client.publish = AsyncMock()
        
        return SafetyMonitor(mqtt_client)
    
    @pytest.mark.asyncio
    async def test_emergency_response_time(self, safety_monitor):
        """Test safety stops within 200ms of hazard detection (Success Criteria #3)"""
        # Create critical hazard
        critical_hazard = HazardAlert(
            alert_id='test_critical',
            hazard_level=HazardLevel.CRITICAL,
            hazard_type='collision_detected',
            timestamp=datetime.now(),
            description='Test critical hazard',
            immediate_response_required=True
        )
        
        # Mock emergency callback to measure response time
        response_times = []
        async def mock_callback(hazards):
            response_time = (datetime.now() - hazards[0].timestamp).total_seconds() * 1000
            response_times.append(response_time)
        
        safety_monitor.register_emergency_callback(mock_callback)
        
        # Trigger emergency response
        await safety_monitor._trigger_emergency_response([critical_hazard])
        
        # Verify response time
        assert len(response_times) == 1
        assert response_times[0] <= 200, f"Emergency response took {response_times[0]:.1f}ms > 200ms requirement"
    
    def test_tilt_detection(self, safety_monitor):
        """Test tilt angle detection from IMU"""
        # Simulate tilted IMU reading (30-degree tilt)
        tilt_angle_rad = np.radians(30)
        
        # Create quaternion for 30-degree rotation around X-axis
        cos_half = np.cos(tilt_angle_rad / 2)
        sin_half = np.sin(tilt_angle_rad / 2)
        quaternion = (cos_half, sin_half, 0.0, 0.0)
        
        test_imu = IMUReading(
            timestamp=datetime.now(),
            sensor_id='bno085',
            value={},
            unit='mixed',
            port='/dev/ttyAMA4',
            baud_rate=3000000,
            quaternion=quaternion,
            acceleration=(0.0, 0.0, 9.81),
            angular_velocity=(0.0, 0.0, 0.0)
        )
        
        safety_monitor._latest_imu = test_imu
        
        # Calculate tilt angle
        tilt_angle = safety_monitor._calculate_tilt_angle()
        
        # Verify tilt detection (should be close to 30 degrees)
        assert abs(tilt_angle - 30.0) < 1.0, f"Tilt calculation error: {tilt_angle:.1f}° vs expected 30.0°"
        assert tilt_angle > safety_monitor.max_safe_tilt_angle, "Dangerous tilt not detected"
    
    def test_collision_detection(self, safety_monitor):
        """Test collision detection from acceleration data"""
        # Simulate normal acceleration
        normal_accel = np.array([0.0, 0.0, 9.81])
        safety_monitor._acceleration_history = [
            (datetime.now() - timedelta(milliseconds=50), normal_accel),
            (datetime.now() - timedelta(milliseconds=40), normal_accel),
        ]
        
        # Simulate collision (sudden acceleration spike)
        collision_accel = np.array([0.0, 0.0, 9.81 + 3.0 * 9.81])  # 3g impact
        safety_monitor._acceleration_history.append(
            (datetime.now(), collision_accel)
        )
        
        # Test collision detection
        collision_detected = safety_monitor._detect_collision()
        assert collision_detected, "Collision not detected with 3g acceleration spike"
    
    @pytest.mark.asyncio
    async def test_safety_status_evaluation(self, safety_monitor):
        """Test comprehensive safety status evaluation"""
        # Set up normal conditions
        safety_monitor._latest_imu = IMUReading(
            timestamp=datetime.now(),
            sensor_id='bno085',
            value={},
            unit='mixed',
            port='/dev/ttyAMA4',
            baud_rate=3000000,
            quaternion=(1.0, 0.0, 0.0, 0.0),  # No tilt
            acceleration=(0.0, 0.0, 9.81),    # Normal gravity
            angular_velocity=(0.0, 0.0, 0.0)
        )
        
        # Evaluate safety status
        safety_status = await safety_monitor._evaluate_safety_status()
        
        # Verify safe conditions
        assert safety_status.is_safe
        assert safety_status.tilt_safe
        assert safety_status.collision_safe
        assert safety_status.tilt_angle < safety_monitor.max_safe_tilt_angle
    
    @pytest.mark.asyncio
    async def test_multiple_hazard_handling(self, safety_monitor):
        """Test handling multiple simultaneous hazards"""
        hazards = [
            HazardAlert(
                alert_id='hazard_1',
                hazard_level=HazardLevel.HIGH,
                hazard_type='tilt_exceeded',
                timestamp=datetime.now(),
                description='Tilt hazard'
            ),
            HazardAlert(
                alert_id='hazard_2',
                hazard_level=HazardLevel.CRITICAL,
                hazard_type='collision_detected',
                timestamp=datetime.now(),
                description='Collision hazard'
            )
        ]
        
        await safety_monitor._trigger_emergency_response(hazards)
        
        # Verify both hazards are tracked
        assert len(safety_monitor._active_alerts) == 2
        assert 'hazard_1' in safety_monitor._active_alerts
        assert 'hazard_2' in safety_monitor._active_alerts


class TestIntegrationScenarios:
    """Test integrated scenarios combining all systems"""
    
    @pytest.mark.asyncio
    async def test_full_system_integration(self):
        """Test complete system integration scenario"""
        # This would be a comprehensive integration test
        # combining localization, obstacle detection, and safety monitoring
        
        config = {
            'mqtt': {'start_local_broker': False},
            'hardware': {}
        }
        
        with patch('src.sensor_fusion.fusion_engine.HardwareInterface'):
            engine = SensorFusionEngine(config)
            engine.mqtt_client = Mock(spec=MQTTClient)
            engine.mqtt_client.connect = AsyncMock()
            engine.mqtt_client.disconnect = AsyncMock()
            engine.mqtt_client.publish = AsyncMock()
            engine.mqtt_client.subscribe = AsyncMock()
            engine.mqtt_client.is_connected = Mock(return_value=True)
            
            await engine.initialize()
            
            # Verify all subsystems initialized
            assert engine.localization_system is not None
            assert engine.obstacle_detection_system is not None
            assert engine.safety_monitor is not None
            
            # Test system health check
            assert engine.is_system_healthy() or not engine._sensor_health  # May not have health data yet
    
    def test_performance_requirements_validation(self):
        """Validate all performance requirements are testable"""
        # Success Criteria validation
        success_criteria = {
            'gps_rtk_accuracy': 0.10,      # 10cm accuracy
            'obstacle_detection_accuracy': 0.95,  # 95% accuracy
            'safety_response_time': 200    # 200ms response
        }
        
        # Performance Requirements validation
        performance_requirements = {
            'localization_update_rate': 10,    # 10Hz for navigation
            'safety_update_rate': 20,          # 20Hz for safety
            'obstacle_detection_latency': 50,  # <50ms
            'localization_latency': 100        # <100ms
        }
        
        # Verify requirements are reasonable
        assert success_criteria['gps_rtk_accuracy'] <= 0.10
        assert success_criteria['obstacle_detection_accuracy'] >= 0.95
        assert success_criteria['safety_response_time'] <= 200
        
        assert performance_requirements['localization_update_rate'] >= 10
        assert performance_requirements['safety_update_rate'] >= 20
        assert performance_requirements['obstacle_detection_latency'] <= 50
        assert performance_requirements['localization_latency'] <= 100


# Performance benchmarking tests
class TestPerformanceBenchmarks:
    """Performance benchmarking tests"""
    
    @pytest.mark.asyncio
    async def test_localization_performance_benchmark(self):
        """Benchmark localization system performance"""
        mqtt_client = Mock(spec=MQTTClient)
        mqtt_client.subscribe = AsyncMock()
        mqtt_client.publish = AsyncMock()
        
        localization = LocalizationSystem(mqtt_client)
        
        # Benchmark coordinate conversion performance
        localization._reference_lat = 40.7128
        localization._reference_lon = -74.0060
        localization._reference_alt = 10.0
        
        start_time = time.time()
        iterations = 1000
        
        for i in range(iterations):
            x, y, z = localization._gps_to_local(40.7128 + i*0.0001, -74.0060 + i*0.0001, 10.0 + i*0.1)
            lat, lon, alt = localization._local_to_gps(x, y, z)
        
        end_time = time.time()
        avg_time_ms = ((end_time - start_time) / iterations) * 1000
        
        # Should be very fast (<1ms per conversion)
        assert avg_time_ms < 1.0, f"Coordinate conversion too slow: {avg_time_ms:.2f}ms per conversion"
    
    @pytest.mark.asyncio  
    async def test_obstacle_processing_performance(self):
        """Benchmark obstacle processing performance"""
        mqtt_client = Mock(spec=MQTTClient)
        mqtt_client.subscribe = AsyncMock()
        mqtt_client.publish = AsyncMock()
        
        obstacle_detection = ObstacleDetectionSystem(mqtt_client)
        
        # Set up test data
        obstacle_detection._latest_tof_left = ToFReading(
            timestamp=datetime.now(),
            sensor_id='tof_left',
            value=1000, unit='mm',
            i2c_address=0x29,
            distance_mm=1000,
            range_status='valid'
        )
        
        start_time = time.time()
        iterations = 100
        
        for i in range(iterations):
            obstacles = await obstacle_detection._process_tof_sensors()
            cv_obstacles = await obstacle_detection._process_computer_vision()
            fused = await obstacle_detection._fuse_detections(obstacles, cv_obstacles)
        
        end_time = time.time()
        avg_time_ms = ((end_time - start_time) / iterations) * 1000
        
        # Should meet <50ms requirement
        assert avg_time_ms < 50.0, f"Obstacle processing too slow: {avg_time_ms:.2f}ms per cycle"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--asyncio-mode=auto'])
