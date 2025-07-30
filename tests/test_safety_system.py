"""
Comprehensive Safety System Tests
Tests 100ms emergency response, hazard detection, and boundary enforcement
"""

import pytest
import asyncio
import logging
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import yaml
from typing import Dict, Any, List

from src.communication import MQTTClient
from src.safety import SafetyService
from src.safety.safety_service import SafetyConfig
from src.safety.emergency_controller import EmergencyController
from src.safety.hazard_detector import HazardDetector
from src.safety.boundary_monitor import BoundaryMonitor
from src.sensor_fusion.data_structures import HazardLevel
from src.hardware.data_structures import GPSReading, IMUReading
from src.communication.message_protocols import SensorData

# Test configuration
TEST_CONFIG = SafetyConfig(
    emergency_response_time_ms=100,
    safety_update_rate_hz=20,
    emergency_update_rate_hz=50,
    person_safety_radius_m=3.0,
    pet_safety_radius_m=1.5,
    general_safety_distance_m=0.3,
    emergency_stop_distance_m=0.15,
    max_safe_tilt_deg=15.0,
    critical_tilt_deg=25.0,
    min_operating_temp_c=5.0,
    max_operating_temp_c=40.0,
    boundary_safety_margin_m=1.0,
    enable_weather_safety=True,
    enable_vision_safety=True,
    enable_boundary_enforcement=True
)


class TestSafetyService:
    """Test the main SafetyService coordination"""
    
    @pytest.fixture
    async def safety_service(self):
        """Create SafetyService instance for testing"""
        mqtt_client = Mock(spec=MQTTClient)
        mqtt_client.connect = AsyncMock()
        mqtt_client.disconnect = AsyncMock()
        mqtt_client.subscribe = AsyncMock()
        mqtt_client.publish = AsyncMock(return_value=True)
        
        service = SafetyService(mqtt_client, TEST_CONFIG)
        yield service
        
        if service._running:
            await service.stop()
    
    @pytest.mark.asyncio
    async def test_safety_service_initialization(self, safety_service):
        """Test safety service initializes correctly"""
        assert safety_service.config.emergency_response_time_ms == 100
        assert safety_service.config.person_safety_radius_m == 3.0
        assert not safety_service._running
        assert safety_service._system_state == "INITIALIZING"
    
    @pytest.mark.asyncio
    async def test_safety_service_start_stop(self, safety_service):
        """Test safety service starts and stops correctly"""
        # Test start
        await safety_service.start()
        assert safety_service._running
        
        # Test stop
        await safety_service.stop()
        assert not safety_service._running
    
    @pytest.mark.asyncio
    async def test_emergency_stop_response_time(self, safety_service):
        """Test emergency stop meets 100ms response time requirement"""
        await safety_service.start()
        
        # Measure emergency stop response time
        start_time = datetime.now()
        success = await safety_service.trigger_emergency_stop(
            reason="Test emergency stop",
            triggered_by="test_suite"
        )
        end_time = datetime.now()
        
        response_time_ms = (end_time - start_time).total_seconds() * 1000
        
        assert success
        assert response_time_ms <= TEST_CONFIG.emergency_response_time_ms
        print(f"Emergency stop response time: {response_time_ms:.1f}ms")
    
    @pytest.mark.asyncio
    async def test_comprehensive_safety_status_collection(self, safety_service):
        """Test comprehensive safety status collection"""
        await safety_service.start()
        
        # Collect safety status
        status = await safety_service._collect_comprehensive_safety_status()
        
        assert 'timestamp' in status
        assert 'overall_safe' in status
        assert 'safety_level' in status
        assert 'components' in status
        assert 'performance_metrics' in status
        
        # Check component status
        components = status['components']
        assert 'safety_monitor' in components
        assert 'hazard_detector' in components
        assert 'boundary_monitor' in components
        assert 'emergency_controller' in components
    
    @pytest.mark.asyncio
    async def test_emergency_callback_registration(self, safety_service):
        """Test emergency callback registration and execution"""
        callback_called = False
        callback_data = None
        
        async def test_callback(source, hazards):
            nonlocal callback_called, callback_data
            callback_called = True
            callback_data = (source, hazards)
        
        # Register callback
        safety_service.register_emergency_callback(test_callback)
        
        # Trigger emergency
        await safety_service.start()
        await safety_service.trigger_emergency_stop("Test callback")
        
        # Allow callback to execute
        await asyncio.sleep(0.1)
        
        assert callback_called
        assert callback_data is not None
    
    @pytest.mark.asyncio
    async def test_safety_metrics_collection(self, safety_service):
        """Test safety performance metrics collection"""
        await safety_service.start()
        
        # Get metrics
        metrics = await safety_service.get_safety_metrics()
        
        assert 'service_status' in metrics
        assert 'performance' in metrics
        assert 'safety_events' in metrics
        assert 'component_metrics' in metrics
        
        # Check service status
        service_status = metrics['service_status']
        assert 'running' in service_status
        assert 'system_state' in service_status
        
        # Check performance metrics
        performance = metrics['performance']
        assert 'average_response_time_ms' in performance
        assert 'target_response_time_ms' in performance


class TestEmergencyController:
    """Test the EmergencyController functionality"""
    
    @pytest.fixture
    async def emergency_controller(self):
        """Create EmergencyController instance for testing"""
        mqtt_client = Mock(spec=MQTTClient)
        mqtt_client.subscribe = AsyncMock()
        mqtt_client.publish = AsyncMock(return_value=True)
        
        controller = EmergencyController(mqtt_client, TEST_CONFIG)
        yield controller
        
        if controller._running:
            await controller.stop()
    
    @pytest.mark.asyncio
    async def test_emergency_controller_initialization(self, emergency_controller):
        """Test emergency controller initializes correctly"""
        assert len(emergency_controller._emergency_actions) > 0
        assert not emergency_controller._emergency_active
        assert not emergency_controller._running
    
    @pytest.mark.asyncio
    async def test_emergency_stop_execution(self, emergency_controller):
        """Test emergency stop execution with timing"""
        await emergency_controller.start()
        
        start_time = datetime.now()
        success = await emergency_controller.execute_emergency_stop("Test emergency")
        end_time = datetime.now()
        
        response_time_ms = (end_time - start_time).total_seconds() * 1000
        
        assert success
        assert response_time_ms <= TEST_CONFIG.emergency_response_time_ms
        assert emergency_controller._emergency_active
        assert emergency_controller._emergency_reason == "Test emergency"
    
    @pytest.mark.asyncio
    async def test_emergency_action_prioritization(self, emergency_controller):
        """Test emergency actions execute in correct priority order"""
        await emergency_controller.start()
        
        # Track action execution order
        execution_order = []
        
        async def mock_publish(topic, message, qos=0):
            execution_order.append(topic)
            return True
        
        emergency_controller.mqtt_client.publish = mock_publish
        
        # Execute emergency stop
        await emergency_controller.execute_emergency_stop("Priority test")
        
        # Verify high priority actions were executed
        assert "lawnberry/motors/emergency_stop" in execution_order
        assert "lawnberry/blade/emergency_disable" in execution_order
    
    @pytest.mark.asyncio
    async def test_emergency_acknowledge_and_reset(self, emergency_controller):
        """Test emergency acknowledgment and reset sequence"""
        await emergency_controller.start()
        
        # Trigger emergency
        await emergency_controller.execute_emergency_stop("Test acknowledge")
        assert emergency_controller._emergency_active
        
        # Acknowledge emergency
        success = await emergency_controller.acknowledge_emergency("test_user")
        assert success
        assert emergency_controller._emergency_acknowledged
        
        # Reset emergency
        success = await emergency_controller.reset_emergency("test_user")
        assert success
        assert not emergency_controller._emergency_active
    
    @pytest.mark.asyncio
    async def test_emergency_state_enforcement(self, emergency_controller):
        """Test continuous emergency state enforcement"""
        await emergency_controller.start()
        
        # Trigger emergency
        await emergency_controller.execute_emergency_stop("Test enforcement")
        
        # Test enforcement loop runs
        await asyncio.sleep(0.1)
        
        # Verify emergency state is maintained
        assert emergency_controller._emergency_active
        assert not emergency_controller._emergency_acknowledged


class TestHazardDetector:
    """Test the HazardDetector functionality"""
    
    @pytest.fixture
    async def hazard_detector(self):
        """Create HazardDetector instance for testing"""
        mqtt_client = Mock(spec=MQTTClient)
        mqtt_client.subscribe = AsyncMock()
        mqtt_client.publish = AsyncMock(return_value=True)
        
        detector = HazardDetector(mqtt_client, TEST_CONFIG)
        yield detector
        
        if detector._running:
            await detector.stop()
    
    @pytest.mark.asyncio
    async def test_hazard_detector_initialization(self, hazard_detector):
        """Test hazard detector initializes correctly"""
        assert hazard_detector._vision_enabled == TEST_CONFIG.enable_vision_safety
        assert len(hazard_detector._hazard_patterns) > 0
        assert not hazard_detector._running
    
    @pytest.mark.asyncio
    async def test_person_detection_critical_response(self, hazard_detector):
        """Test person detection triggers critical response"""
        await hazard_detector.start()
        
        # Simulate person detection at close range
        detection = {
            'object_id': 'person_test_1',
            'class': 'person',
            'confidence': 0.95,
            'bbox': [0.4, 0.3, 0.2, 0.4],  # Large bbox = close distance
        }
        
        await hazard_detector._process_object_detection(detection)
        
        # Check for critical hazards
        critical_hazards = await hazard_detector.check_critical_hazards()
        
        assert len(critical_hazards) > 0
        critical_hazard = critical_hazards[0]['alert']
        assert critical_hazard['hazard_level'] == 'CRITICAL'
        assert 'person' in critical_hazard['hazard_type']
    
    @pytest.mark.asyncio
    async def test_pet_detection_high_response(self, hazard_detector):
        """Test pet detection triggers high priority response"""
        await hazard_detector.start()
        
        # Simulate pet detection
        detection = {
            'object_id': 'pet_test_1',
            'class': 'dog',
            'confidence': 0.85,
            'bbox': [0.45, 0.4, 0.15, 0.25],
        }
        
        await hazard_detector._process_object_detection(detection)
        
        # Check detection was processed
        assert len(hazard_detector._detected_objects) > 0
        
        detected_obj = list(hazard_detector._detected_objects.values())[0]
        assert detected_obj.object_type == 'dog'
        assert detected_obj.threat_level in [HazardLevel.HIGH, HazardLevel.CRITICAL]
    
    @pytest.mark.asyncio
    async def test_distance_estimation_accuracy(self, hazard_detector):
        """Test distance estimation from bounding box"""
        # Test various bounding box sizes
        test_cases = [
            ([0.4, 0.2, 0.2, 0.6], 'person', 2.5),  # Large bbox = close
            ([0.45, 0.4, 0.1, 0.2], 'person', 8.0),  # Small bbox = far
        ]
        
        for bbox, object_type, expected_range in test_cases:
            distance = hazard_detector._estimate_distance_from_bbox(bbox, object_type)
            
            # Distance should be in reasonable range
            assert 0.1 <= distance <= 50.0
            print(f"Distance estimate for {object_type} with bbox {bbox}: {distance:.1f}m")
    
    @pytest.mark.asyncio
    async def test_object_velocity_calculation(self, hazard_detector):
        """Test object velocity calculation and approach detection"""
        await hazard_detector.start()
        
        object_id = "velocity_test_1"
        
        # Simulate object moving toward robot
        positions = [
            ((5.0, 10.0), datetime.now()),
            ((4.0, 8.0), datetime.now() + timedelta(seconds=1)),
            ((3.0, 6.0), datetime.now() + timedelta(seconds=2)),
        ]
        
        for position, timestamp in positions:
            # Add to velocity history
            if object_id not in hazard_detector._velocity_history:
                hazard_detector._velocity_history[object_id] = []
            hazard_detector._velocity_history[object_id].append((timestamp, position))
        
        # Calculate velocity
        velocity = hazard_detector._calculate_object_velocity(object_id)
        
        # Should show movement toward robot (negative y velocity)
        assert velocity[1] < 0  # Moving toward robot (y decreasing)
        
        # Test approach detection
        is_approaching = hazard_detector._is_object_approaching(velocity, positions[-1][0])
        assert is_approaching
    
    @pytest.mark.asyncio
    async def test_hazard_detection_performance(self, hazard_detector):
        """Test hazard detection performance and timing"""
        await hazard_detector.start()
        
        # Simulate rapid detection processing
        detections = [
            {'object_id': f'perf_test_{i}', 'class': 'person', 'confidence': 0.9,
             'bbox': [0.4, 0.3, 0.2, 0.4]} for i in range(10)
        ]
        
        start_time = datetime.now()
        
        for detection in detections:
            await hazard_detector._process_object_detection(detection)
        
        end_time = datetime.now()
        processing_time_ms = (end_time - start_time).total_seconds() * 1000
        avg_time_per_detection = processing_time_ms / len(detections)
        
        # Should process detections quickly
        assert avg_time_per_detection < 10.0  # Less than 10ms per detection
        print(f"Average detection processing time: {avg_time_per_detection:.1f}ms")


class TestBoundaryMonitor:
    """Test the BoundaryMonitor functionality"""
    
    @pytest.fixture
    async def boundary_monitor(self):
        """Create BoundaryMonitor instance for testing"""
        mqtt_client = Mock(spec=MQTTClient)
        mqtt_client.subscribe = AsyncMock()
        mqtt_client.publish = AsyncMock(return_value=True)
        
        monitor = BoundaryMonitor(mqtt_client, TEST_CONFIG)
        yield monitor
        
        if monitor._running:
            await monitor.stop()
    
    @pytest.mark.asyncio
    async def test_boundary_monitor_initialization(self, boundary_monitor):
        """Test boundary monitor initializes correctly"""
        assert boundary_monitor._safety_margin_m == TEST_CONFIG.boundary_safety_margin_m
        assert not boundary_monitor._boundary_loaded
        assert not boundary_monitor._monitoring_active
    
    @pytest.mark.asyncio
    async def test_boundary_violation_detection(self, boundary_monitor):
        """Test boundary violation detection"""
        await boundary_monitor.start()
        
        # Set up test boundary (rectangle)
        from src.safety.boundary_monitor import BoundaryPoint
        boundary_points = [
            BoundaryPoint(40.7125, -74.0065, 'p1', datetime.now()),
            BoundaryPoint(40.7125, -74.0055, 'p2', datetime.now()),
            BoundaryPoint(40.7135, -74.0055, 'p3', datetime.now()),
            BoundaryPoint(40.7135, -74.0065, 'p4', datetime.now())
        ]
        
        boundary_monitor._yard_boundary = boundary_points
        boundary_monitor._boundary_loaded = True
        boundary_monitor._monitoring_active = True
        
        # Test position outside boundary
        outside_position = (40.7140, -74.0060)  # North of boundary
        
        await boundary_monitor._check_boundary_violations(outside_position)
        
        # Should have violation
        assert len(boundary_monitor._active_violations) > 0
        
        violation = list(boundary_monitor._active_violations.values())[0]
        assert violation.violation_type == "boundary_exit"
        assert violation.severity in [HazardLevel.HIGH, HazardLevel.CRITICAL]
    
    @pytest.mark.asyncio
    async def test_point_in_polygon_algorithm(self, boundary_monitor):
        """Test point-in-polygon algorithm accuracy"""
        from src.safety.boundary_monitor import BoundaryPoint
        
        # Create square boundary
        boundary_points = [
            BoundaryPoint(40.7125, -74.0065, 'p1', datetime.now()),
            BoundaryPoint(40.7125, -74.0055, 'p2', datetime.now()),
            BoundaryPoint(40.7135, -74.0055, 'p3', datetime.now()),
            BoundaryPoint(40.7135, -74.0065, 'p4', datetime.now())
        ]
        
        # Test points
        test_cases = [
            ((40.7130, -74.0060), True),   # Inside
            ((40.7140, -74.0060), False),  # Outside (north)
            ((40.7130, -74.0050), False),  # Outside (east)
            ((40.7120, -74.0060), False),  # Outside (south)
            ((40.7130, -74.0070), False),  # Outside (west)
        ]
        
        for point, expected_inside in test_cases:
            result = boundary_monitor._is_point_inside_polygon(point, boundary_points)
            assert result == expected_inside, f"Point {point} should be {'inside' if expected_inside else 'outside'}"
    
    @pytest.mark.asyncio
    async def test_gps_accuracy_filtering(self, boundary_monitor):
        """Test GPS accuracy filtering"""
        await boundary_monitor.start()
        
        # Create GPS reading with poor accuracy
        poor_gps = GPSReading(
            timestamp=datetime.now(),
            sensor_id='gps_test',
            value={},
            unit='degrees',
            latitude=40.7130,
            longitude=-74.0060,
            altitude=100.0,
            accuracy=5.0,  # Exceeds threshold of 2.0m
            satellites=4
        )
        
        # Should be rejected due to poor accuracy
        await boundary_monitor.update_position(poor_gps)
        assert boundary_monitor._current_position is None
        
        # Create GPS reading with good accuracy
        good_gps = GPSReading(
            timestamp=datetime.now(),
            sensor_id='gps_test',
            value={},
            unit='degrees',
            latitude=40.7130,
            longitude=-74.0060,
            altitude=100.0,
            accuracy=1.5,  # Within threshold
            satellites=8
        )
        
        # Should be accepted
        await boundary_monitor.update_position(good_gps)
        assert boundary_monitor._current_position is not None
    
    @pytest.mark.asyncio
    async def test_no_go_zone_enforcement(self, boundary_monitor):
        """Test no-go zone enforcement"""
        await boundary_monitor.start()
        
        # Create no-go zone
        from src.safety.boundary_monitor import NoGoZone, BoundaryPoint
        zone_points = [
            BoundaryPoint(40.7126, -74.0059, 'z1', datetime.now()),
            BoundaryPoint(40.7126, -74.0057, 'z2', datetime.now()),
            BoundaryPoint(40.7128, -74.0057, 'z3', datetime.now()),
            BoundaryPoint(40.7128, -74.0059, 'z4', datetime.now())
        ]
        
        no_go_zone = NoGoZone(
            zone_id='test_zone',
            name='Test No-Go Zone',
            boundary_points=zone_points,
            zone_type='temporary',
            active=True,
            created_by='test'
        )
        
        boundary_monitor._no_go_zones['test_zone'] = no_go_zone
        
        # Test position inside no-go zone
        inside_zone_position = (40.7127, -74.0058)
        
        await boundary_monitor._check_boundary_violations(inside_zone_position)
        
        # Should have no-go zone violation
        violations = [v for v in boundary_monitor._active_violations.values() 
                     if v.violation_type == "no_go_entry"]
        assert len(violations) > 0
    
    @pytest.mark.asyncio
    async def test_critical_violation_detection(self, boundary_monitor):
        """Test critical boundary violation detection"""
        await boundary_monitor.start()
        
        # Set up boundary
        from src.safety.boundary_monitor import BoundaryPoint
        boundary_monitor._yard_boundary = [
            BoundaryPoint(40.7125, -74.0065, 'p1', datetime.now()),
            BoundaryPoint(40.7125, -74.0055, 'p2', datetime.now()),
            BoundaryPoint(40.7135, -74.0055, 'p3', datetime.now()),
            BoundaryPoint(40.7135, -74.0065, 'p4', datetime.now())
        ]
        boundary_monitor._boundary_loaded = True
        boundary_monitor._monitoring_active = True
        
        # Create critical violation (far outside boundary)
        far_outside_position = (40.7150, -74.0060)
        await boundary_monitor._check_boundary_violations(far_outside_position)
        
        # Check for critical violations
        critical_violations = await boundary_monitor.check_critical_violations()
        
        # Should detect critical violation
        assert len(critical_violations) > 0
        critical_violation = critical_violations[0]['alert']
        assert critical_violation['hazard_level'] == 'CRITICAL'


class TestIntegrationScenarios:
    """Test complete integration scenarios"""
    
    @pytest.fixture
    async def complete_safety_system(self):
        """Create complete safety system for integration testing"""
        mqtt_client = Mock(spec=MQTTClient)
        mqtt_client.connect = AsyncMock()
        mqtt_client.disconnect = AsyncMock()
        mqtt_client.subscribe = AsyncMock()
        mqtt_client.publish = AsyncMock(return_value=True)
        
        safety_service = SafetyService(mqtt_client, TEST_CONFIG)
        yield safety_service
        
        if safety_service._running:
            await safety_service.stop()
    
    @pytest.mark.asyncio
    async def test_multi_hazard_scenario(self, complete_safety_system):
        """Test response to multiple simultaneous hazards"""
        await complete_safety_system.start()
        
        # Create multiple simultaneous hazards
        hazards = []
        
        # Add person detection hazard
        hazards.append({
            'source': 'hazard_detector',
            'alert': {
                'hazard_type': 'person_detection',
                'hazard_level': 'CRITICAL',
                'description': 'Person detected at close range',
                'immediate_response_required': True
            }
        })
        
        # Add boundary violation hazard
        hazards.append({
            'source': 'boundary_monitor',
            'alert': {
                'hazard_type': 'boundary_exit',
                'hazard_level': 'HIGH',
                'description': 'Outside yard boundary',
                'immediate_response_required': True
            }
        })
        
        # Trigger coordinated emergency response
        start_time = datetime.now()
        await complete_safety_system._trigger_coordinated_emergency_response(hazards)
        end_time = datetime.now()
        
        response_time_ms = (end_time - start_time).total_seconds() * 1000
        
        # Should handle multiple hazards within response time
        assert response_time_ms <= TEST_CONFIG.emergency_response_time_ms
        print(f"Multi-hazard response time: {response_time_ms:.1f}ms")
    
    @pytest.mark.asyncio
    async def test_system_recovery_scenario(self, complete_safety_system):
        """Test system recovery after emergency"""
        await complete_safety_system.start()
        
        # Trigger emergency
        await complete_safety_system.trigger_emergency_stop("Recovery test")
        
        # Verify emergency state
        assert complete_safety_system.emergency_controller._emergency_active
        
        # Acknowledge and reset emergency
        await complete_safety_system.emergency_controller.acknowledge_emergency("test")
        await complete_safety_system.emergency_controller.reset_emergency("test")
        
        # Verify recovery
        assert not complete_safety_system.emergency_controller._emergency_active
        
        # Verify system can resume normal operation
        status = await complete_safety_system._collect_comprehensive_safety_status()
        assert status is not None
    
    @pytest.mark.asyncio
    async def test_performance_under_load(self, complete_safety_system):
        """Test system performance under high sensor data load"""
        await complete_safety_system.start()
        
        # Simulate high-frequency sensor updates
        update_tasks = []
        
        for i in range(100):
            # Simulate rapid sensor updates
            task = asyncio.create_task(
                complete_safety_system._collect_comprehensive_safety_status()
            )
            update_tasks.append(task)
        
        start_time = datetime.now()
        results = await asyncio.gather(*update_tasks, return_exceptions=True)
        end_time = datetime.now()
        
        processing_time_ms = (end_time - start_time).total_seconds() * 1000
        avg_time_per_update = processing_time_ms / len(update_tasks)
        
        # Verify no exceptions occurred
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0
        
        # Verify performance is acceptable
        assert avg_time_per_update < 10.0  # Less than 10ms per update
        print(f"Average status update time under load: {avg_time_per_update:.1f}ms")


@pytest.mark.asyncio
async def test_safety_system_compliance():
    """Test overall safety system compliance with requirements"""
    # Test emergency response time requirement
    mqtt_client = Mock(spec=MQTTClient)
    mqtt_client.connect = AsyncMock()
    mqtt_client.subscribe = AsyncMock()
    mqtt_client.publish = AsyncMock(return_value=True)
    
    safety_service = SafetyService(mqtt_client, TEST_CONFIG)
    
    try:
        await safety_service.start()
        
        # Measure multiple emergency stops to verify consistency
        response_times = []
        
        for i in range(5):
            start_time = datetime.now()
            success = await safety_service.trigger_emergency_stop(f"Compliance test {i}")
            end_time = datetime.now()
            
            response_time_ms = (end_time - start_time).total_seconds() * 1000
            response_times.append(response_time_ms)
            
            assert success
            assert response_time_ms <= TEST_CONFIG.emergency_response_time_ms
            
            # Reset for next test
            await safety_service.emergency_controller.acknowledge_emergency("test")
            await safety_service.emergency_controller.reset_emergency("test")
            await asyncio.sleep(0.1)
        
        # Verify consistent performance
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        
        assert avg_response_time <= TEST_CONFIG.emergency_response_time_ms
        assert max_response_time <= TEST_CONFIG.emergency_response_time_ms * 1.2  # Allow 20% variance
        
        print(f"Emergency stop compliance test:")
        print(f"  Average response time: {avg_response_time:.1f}ms")
        print(f"  Maximum response time: {max_response_time:.1f}ms")
        print(f"  Target response time: {TEST_CONFIG.emergency_response_time_ms}ms")
        print(f"  All tests passed: {all(t <= TEST_CONFIG.emergency_response_time_ms for t in response_times)}")
        
    finally:
        await safety_service.stop()


if __name__ == "__main__":
    # Run compliance test directly
    asyncio.run(test_safety_system_compliance())
