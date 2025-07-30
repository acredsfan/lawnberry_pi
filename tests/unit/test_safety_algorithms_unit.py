"""
Unit tests for safety-critical algorithms with 100% coverage requirement.
Tests all emergency response, hazard detection, and boundary enforcement algorithms.
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import numpy as np
from typing import Dict, List, Any

from src.safety.hazard_detector import HazardDetector, HazardLevel
from src.safety.emergency_controller import EmergencyController
from src.safety.boundary_monitor import BoundaryMonitor
from src.sensor_fusion.data_structures import SensorReading, IMUReading, GPSReading
from src.hardware.data_structures import ToFReading


@pytest.mark.safety
class TestHazardDetector:
    """Test hazard detection algorithms - SAFETY CRITICAL (100% coverage required)"""
    
    @pytest.fixture
    def hazard_detector(self):
        """Create HazardDetector instance"""
        config = {
            "person_safety_radius_m": 3.0,
            "pet_safety_radius_m": 1.5,
            "emergency_stop_distance_m": 0.15,
            "max_safe_tilt_deg": 15.0,
            "critical_tilt_deg": 25.0
        }
        return HazardDetector(config)
    
    def test_person_detection_hazard_level(self, hazard_detector):
        """Test person detection returns correct hazard level"""
        # Test critical distance - immediate stop required
        detection = {
            "type": "person",
            "distance_m": 2.5,
            "confidence": 0.95,
            "position": {"x": 2.0, "y": 1.5}
        }
        
        hazard_level = hazard_detector.evaluate_vision_hazard(detection)
        assert hazard_level == HazardLevel.CRITICAL
        assert hazard_detector.get_last_hazard_reason() == "Person detected within safety zone"
    
    def test_person_detection_safe_distance(self, hazard_detector):
        """Test person at safe distance returns no hazard"""
        detection = {
            "type": "person", 
            "distance_m": 5.0,
            "confidence": 0.95,
            "position": {"x": 4.0, "y": 3.0}
        }
        
        hazard_level = hazard_detector.evaluate_vision_hazard(detection)
        assert hazard_level == HazardLevel.NONE
    
    def test_pet_detection_hazard_level(self, hazard_detector):
        """Test pet detection returns correct hazard level"""
        detection = {
            "type": "dog",
            "distance_m": 1.0,
            "confidence": 0.88,
            "position": {"x": 0.8, "y": 0.6}
        }
        
        hazard_level = hazard_detector.evaluate_vision_hazard(detection)
        assert hazard_level == HazardLevel.CRITICAL
        assert hazard_detector.get_last_hazard_reason() == "Pet detected within safety zone"
    
    def test_low_confidence_detection_filtered(self, hazard_detector):
        """Test low confidence detections are filtered out"""
        detection = {
            "type": "person",
            "distance_m": 1.0,
            "confidence": 0.5,  # Below threshold
            "position": {"x": 1.0, "y": 0.0}
        }
        
        hazard_level = hazard_detector.evaluate_vision_hazard(detection)
        assert hazard_level == HazardLevel.NONE
    
    def test_tilt_detection_safe_angle(self, hazard_detector):
        """Test safe tilt angles return no hazard"""
        imu_reading = IMUReading(
            acceleration={"x": 0.1, "y": 0.2, "z": 9.8},
            gyroscope={"x": 0.01, "y": -0.02, "z": 0.005},
            orientation={"roll": 10.0, "pitch": 8.0, "yaw": 180.0},  # Safe angles
            timestamp=datetime.now()
        )
        
        hazard_level = hazard_detector.evaluate_tilt_hazard(imu_reading)
        assert hazard_level == HazardLevel.NONE
    
    def test_tilt_detection_warning_angle(self, hazard_detector):
        """Test warning tilt angles return medium hazard"""
        imu_reading = IMUReading(
            acceleration={"x": 0.1, "y": 0.2, "z": 9.8},
            gyroscope={"x": 0.01, "y": -0.02, "z": 0.005},
            orientation={"roll": 18.0, "pitch": 8.0, "yaw": 180.0},  # Warning angle
            timestamp=datetime.now()
        )
        
        hazard_level = hazard_detector.evaluate_tilt_hazard(imu_reading)
        assert hazard_level == HazardLevel.MEDIUM
        assert "Tilt angle" in hazard_detector.get_last_hazard_reason()
    
    def test_tilt_detection_critical_angle(self, hazard_detector):
        """Test critical tilt angles return critical hazard"""
        imu_reading = IMUReading(
            acceleration={"x": 0.1, "y": 0.2, "z": 9.8},
            gyroscope={"x": 0.01, "y": -0.02, "z": 0.005},
            orientation={"roll": 30.0, "pitch": 8.0, "yaw": 180.0},  # Critical angle
            timestamp=datetime.now()
        )
        
        hazard_level = hazard_detector.evaluate_tilt_hazard(imu_reading)
        assert hazard_level == HazardLevel.CRITICAL
        assert "Critical tilt" in hazard_detector.get_last_hazard_reason()
    
    def test_cliff_detection_safe_distance(self, hazard_detector):
        """Test safe ToF distances return no hazard"""
        tof_reading = ToFReading(
            sensor_id="front_left",
            distance_mm=300,  # 30cm - safe
            status="valid",
            timestamp=datetime.now()
        )
        
        hazard_level = hazard_detector.evaluate_cliff_hazard(tof_reading)
        assert hazard_level == HazardLevel.NONE
    
    def test_cliff_detection_critical_distance(self, hazard_detector):
        """Test cliff detection returns critical hazard"""
        tof_reading = ToFReading(
            sensor_id="front_left", 
            distance_mm=100,  # 10cm - critical
            status="valid",
            timestamp=datetime.now()
        )
        
        hazard_level = hazard_detector.evaluate_cliff_hazard(tof_reading)
        assert hazard_level == HazardLevel.CRITICAL
        assert "Cliff detected" in hazard_detector.get_last_hazard_reason()
    
    def test_impact_detection_normal_acceleration(self, hazard_detector):
        """Test normal acceleration doesn't trigger impact detection"""
        imu_reading = IMUReading(
            acceleration={"x": 0.1, "y": 0.2, "z": 9.8},  # Normal
            gyroscope={"x": 0.01, "y": -0.02, "z": 0.005},
            orientation={"roll": 2.0, "pitch": 1.5, "yaw": 180.0},
            timestamp=datetime.now()
        )
        
        hazard_level = hazard_detector.evaluate_impact_hazard(imu_reading)
        assert hazard_level == HazardLevel.NONE
    
    def test_impact_detection_high_acceleration(self, hazard_detector):
        """Test high acceleration triggers impact detection"""
        imu_reading = IMUReading(
            acceleration={"x": 5.0, "y": 0.2, "z": 15.0},  # High impact
            gyroscope={"x": 0.01, "y": -0.02, "z": 0.005},
            orientation={"roll": 2.0, "pitch": 1.5, "yaw": 180.0},
            timestamp=datetime.now()
        )
        
        hazard_level = hazard_detector.evaluate_impact_hazard(imu_reading)
        assert hazard_level == HazardLevel.CRITICAL
        assert "Impact detected" in hazard_detector.get_last_hazard_reason()
    
    def test_invalid_sensor_data_handling(self, hazard_detector):
        """Test handling of invalid sensor data"""
        # Test invalid ToF reading
        invalid_tof = ToFReading(
            sensor_id="front_left",
            distance_mm=-1,  # Invalid
            status="error",
            timestamp=datetime.now()
        )
        
        hazard_level = hazard_detector.evaluate_cliff_hazard(invalid_tof)
        assert hazard_level == HazardLevel.NONE  # Should not trigger on invalid data
    
    def test_hazard_history_tracking(self, hazard_detector):
        """Test hazard history is properly tracked"""
        # Generate sequence of hazards
        for i in range(5):
            detection = {
                "type": "person",
                "distance_m": 2.0,
                "confidence": 0.95,
                "position": {"x": 2.0, "y": 0.0}
            }
            hazard_detector.evaluate_vision_hazard(detection)
        
        history = hazard_detector.get_hazard_history()
        assert len(history) == 5
        assert all(h["level"] == HazardLevel.CRITICAL for h in history)


@pytest.mark.safety
class TestEmergencyController:
    """Test emergency response controller - SAFETY CRITICAL (100% coverage required)"""
    
    @pytest.fixture
    def emergency_controller(self):
        """Create EmergencyController instance"""
        config = {
            "response_time_ms": 100,
            "recovery_delay_s": 5.0,
            "max_recovery_attempts": 3
        }
        controller = EmergencyController(config)
        controller._hardware_interface = Mock()
        controller._hardware_interface.emergency_stop = AsyncMock()
        controller._hardware_interface.resume_operation = AsyncMock()
        return controller
    
    @pytest.mark.asyncio
    async def test_emergency_stop_response_time(self, emergency_controller, performance_monitor):
        """Test emergency stop meets response time requirement"""
        performance_monitor.start()
        
        # Trigger emergency stop
        success = await emergency_controller.trigger_emergency_stop(
            "Test emergency", "unit_test"
        )
        
        metrics = performance_monitor.stop()
        
        assert success
        assert metrics["duration_s"] * 1000 <= 100  # 100ms requirement
        assert emergency_controller.is_emergency_active()
        
        # Verify hardware was called
        emergency_controller._hardware_interface.emergency_stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_emergency_stop_idempotent(self, emergency_controller):
        """Test multiple emergency stops don't cause issues"""
        # First emergency stop
        success1 = await emergency_controller.trigger_emergency_stop(
            "First emergency", "test"
        )
        
        # Second emergency stop
        success2 = await emergency_controller.trigger_emergency_stop(
            "Second emergency", "test"
        )
        
        assert success1
        assert success2
        assert emergency_controller.is_emergency_active()
        
        # Hardware should only be called once (idempotent)
        assert emergency_controller._hardware_interface.emergency_stop.call_count == 1
    
    @pytest.mark.asyncio
    async def test_emergency_recovery_sequence(self, emergency_controller):
        """Test emergency recovery sequence"""
        # Trigger emergency
        await emergency_controller.trigger_emergency_stop("Test", "test")
        assert emergency_controller.is_emergency_active()
        
        # Attempt recovery
        success = await emergency_controller.attempt_recovery()
        
        assert success
        assert not emergency_controller.is_emergency_active()
        emergency_controller._hardware_interface.resume_operation.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_recovery_failure_handling(self, emergency_controller):
        """Test handling of recovery failures"""
        # Mock hardware recovery failure
        emergency_controller._hardware_interface.resume_operation.side_effect = Exception("Hardware fault")
        
        # Trigger emergency
        await emergency_controller.trigger_emergency_stop("Test", "test")
        
        # Attempt recovery - should fail
        success = await emergency_controller.attempt_recovery()
        
        assert not success
        assert emergency_controller.is_emergency_active()
        assert emergency_controller.get_recovery_attempts() == 1
    
    @pytest.mark.asyncio
    async def test_max_recovery_attempts(self, emergency_controller):
        """Test maximum recovery attempts limit"""
        # Mock hardware recovery failure
        emergency_controller._hardware_interface.resume_operation.side_effect = Exception("Hardware fault")
        
        # Trigger emergency
        await emergency_controller.trigger_emergency_stop("Test", "test")
        
        # Exhaust recovery attempts
        for i in range(4):  # Max is 3, so 4th should fail
            success = await emergency_controller.attempt_recovery()
            if i < 3:
                assert not success
                assert emergency_controller.is_emergency_active()
            else:
                assert not success
                assert emergency_controller.get_recovery_attempts() == 3
    
    def test_emergency_state_persistence(self, emergency_controller):
        """Test emergency state is properly maintained"""
        assert not emergency_controller.is_emergency_active()
        
        # Set emergency state
        emergency_controller._emergency_active = True
        emergency_controller._emergency_reason = "Test emergency"
        emergency_controller._emergency_timestamp = datetime.now()
        
        assert emergency_controller.is_emergency_active()
        assert emergency_controller.get_emergency_reason() == "Test emergency"
        assert emergency_controller.get_emergency_duration() > timedelta(0)
    
    def test_emergency_logging(self, emergency_controller):
        """Test emergency events are properly logged"""
        with patch('src.safety.emergency_controller.logging') as mock_logging:
            emergency_controller._log_emergency_event("test_event", {"test": "data"})
            
            mock_logging.getLogger().critical.assert_called_once()


@pytest.mark.safety  
class TestBoundaryMonitor:
    """Test boundary enforcement - SAFETY CRITICAL (100% coverage required)"""
    
    @pytest.fixture
    def boundary_monitor(self, sample_map_data):
        """Create BoundaryMonitor instance"""
        config = {
            "safety_margin_m": 1.0,
            "boundary_check_rate_hz": 10
        }
        monitor = BoundaryMonitor(config)
        monitor.set_boundaries(sample_map_data["boundaries"])
        monitor.set_no_go_zones(sample_map_data["no_go_zones"])
        return monitor
    
    def test_position_inside_boundary(self, boundary_monitor):
        """Test position inside boundary returns safe"""
        # Position well inside boundary
        position = GPSReading(
            latitude=40.7129,
            longitude=-74.0059,
            altitude=10.0,
            accuracy=2.0,
            timestamp=datetime.now()
        )
        
        is_safe, distance_to_boundary = boundary_monitor.check_position_safety(position)
        assert is_safe
        assert distance_to_boundary > 1.0  # Outside safety margin
    
    def test_position_outside_boundary(self, boundary_monitor):
        """Test position outside boundary returns unsafe"""
        # Position outside boundary
        position = GPSReading(
            latitude=40.7132,  # Outside boundary
            longitude=-74.0061,
            altitude=10.0,
            accuracy=2.0,
            timestamp=datetime.now()
        )
        
        is_safe, distance_to_boundary = boundary_monitor.check_position_safety(position)
        assert not is_safe
        assert distance_to_boundary < 0  # Negative indicates outside
    
    def test_position_near_boundary_margin(self, boundary_monitor):
        """Test position near boundary but within safety margin"""
        # Position close to boundary but still within margin
        position = GPSReading(
            latitude=40.7130,  # At boundary
            longitude=-74.0060,
            altitude=10.0,
            accuracy=2.0,
            timestamp=datetime.now()
        )
        
        is_safe, distance_to_boundary = boundary_monitor.check_position_safety(position)
        # Should be unsafe due to safety margin
        assert not is_safe
    
    def test_no_go_zone_detection(self, boundary_monitor):
        """Test no-go zone detection"""
        # Position inside flower bed no-go zone
        position = GPSReading(
            latitude=40.7128,  # Inside flower bed
            longitude=-74.0058,
            altitude=10.0,
            accuracy=2.0,
            timestamp=datetime.now()
        )
        
        in_no_go, zone_name = boundary_monitor.check_no_go_zones(position)
        assert in_no_go
        assert zone_name == "flower_bed"
    
    def test_position_outside_no_go_zones(self, boundary_monitor):
        """Test position outside all no-go zones"""
        # Position outside all no-go zones
        position = GPSReading(
            latitude=40.7129,
            longitude=-74.0060,  # Outside flower bed
            altitude=10.0,
            accuracy=2.0,
            timestamp=datetime.now()
        )
        
        in_no_go, zone_name = boundary_monitor.check_no_go_zones(position)
        assert not in_no_go
        assert zone_name is None
    
    def test_boundary_crossing_detection(self, boundary_monitor):
        """Test boundary crossing detection"""
        # Start inside boundary
        pos1 = GPSReading(
            latitude=40.7129,
            longitude=-74.0059,
            altitude=10.0,
            accuracy=2.0,
            timestamp=datetime.now()
        )
        
        # Move outside boundary
        pos2 = GPSReading(
            latitude=40.7132,
            longitude=-74.0061,
            altitude=10.0,
            accuracy=2.0,
            timestamp=datetime.now() + timedelta(seconds=1)
        )
        
        crossing_detected = boundary_monitor.detect_boundary_crossing(pos1, pos2)
        assert crossing_detected
    
    def test_no_boundary_crossing_inside(self, boundary_monitor):
        """Test no crossing detected when staying inside"""
        # Both positions inside boundary
        pos1 = GPSReading(
            latitude=40.7129,
            longitude=-74.0059,
            altitude=10.0,
            accuracy=2.0,
            timestamp=datetime.now()
        )
        
        pos2 = GPSReading(
            latitude=40.7129,
            longitude=-74.0058,
            altitude=10.0,
            accuracy=2.0,
            timestamp=datetime.now() + timedelta(seconds=1)
        )
        
        crossing_detected = boundary_monitor.detect_boundary_crossing(pos1, pos2)
        assert not crossing_detected
    
    def test_distance_calculation_accuracy(self, boundary_monitor):
        """Test distance calculation accuracy"""
        # Test known distance
        pos1 = GPSReading(
            latitude=40.7128,
            longitude=-74.0060,
            altitude=10.0,
            accuracy=2.0,
            timestamp=datetime.now()
        )
        
        pos2 = GPSReading(
            latitude=40.7129,  # ~111m north
            longitude=-74.0060,
            altitude=10.0,
            accuracy=2.0,
            timestamp=datetime.now()
        )
        
        distance = boundary_monitor.calculate_distance(pos1, pos2)
        # Should be approximately 111 meters (1 degree latitude ≈ 111km)
        assert 100 < distance < 120
    
    def test_invalid_gps_handling(self, boundary_monitor):
        """Test handling of invalid GPS data"""
        # Invalid GPS reading
        invalid_position = GPSReading(
            latitude=0.0,  # Invalid
            longitude=0.0,  # Invalid
            altitude=10.0,
            accuracy=100.0,  # Poor accuracy
            timestamp=datetime.now()
        )
        
        is_safe, distance = boundary_monitor.check_position_safety(invalid_position)
        # Should err on side of safety - return unsafe for invalid GPS
        assert not is_safe
    
    def test_boundary_update_while_monitoring(self, boundary_monitor):
        """Test updating boundaries while monitoring is active"""
        # New boundary
        new_boundaries = [
            {"lat": 40.7125, "lng": -74.0065},
            {"lat": 40.7135, "lng": -74.0065},
            {"lat": 40.7135, "lng": -74.0055},
            {"lat": 40.7125, "lng": -74.0055}
        ]
        
        boundary_monitor.set_boundaries(new_boundaries)
        
        # Test position that was safe before but unsafe now
        position = GPSReading(
            latitude=40.7128,
            longitude=-74.0060,
            altitude=10.0,
            accuracy=2.0,
            timestamp=datetime.now()
        )
        
        is_safe, distance = boundary_monitor.check_position_safety(position)
        assert is_safe  # Should be safe with new boundary
