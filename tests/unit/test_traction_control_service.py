"""
Unit tests for TractionControlService
Tests slip detection and dynamic motor boost compensation.
"""

import pytest
from backend.src.services.traction_control_service import (
    TractionControlService,
    get_traction_control_service,
)


class TestTractionControlService:
    """Test traction control slip detection and boost."""

    def test_init(self):
        """Test service initialization."""
        svc = TractionControlService()
        assert svc.enabled
        assert svc.state.left_rpm == 0.0
        assert svc.state.right_rpm == 0.0
        assert svc.state.left_boost == 0.0
        assert svc.state.right_boost == 0.0

    def test_update_motor_feedback(self):
        """Test recording motor feedback."""
        svc = TractionControlService()
        svc.update_motor_feedback(left_rpm=50.0, right_rpm=45.0)
        
        assert svc.state.left_rpm == 50.0
        assert svc.state.right_rpm == 45.0

    def test_record_motor_command(self):
        """Test recording commanded speeds."""
        svc = TractionControlService()
        svc.record_motor_command(left_speed=0.5, right_speed=0.5)
        
        assert svc.state.left_commanded == 0.5
        assert svc.state.right_commanded == 0.5

    def test_no_slip_when_disabled(self):
        """Test that slip detection returns False when disabled."""
        svc = TractionControlService()
        svc.enabled = False
        svc.record_motor_command(0.8, 0.8)
        
        left_slip, right_slip = svc.detect_slip()
        assert not left_slip
        assert not right_slip

    def test_no_slip_at_low_speed(self):
        """Test that slip detection ignores low-speed creeping."""
        svc = TractionControlService(min_speed_for_detection=0.2)
        svc.update_motor_feedback(left_rpm=0.0, right_rpm=0.0)
        svc.record_motor_command(left_speed=0.05, right_speed=0.05)  # Below threshold
        
        left_slip, right_slip = svc.detect_slip()
        assert not left_slip
        assert not right_slip

    def test_detect_left_wheel_slip(self):
        """Test detection of left wheel slipping."""
        svc = TractionControlService(slip_threshold=5.0)
        # Commanded 0.5 (scales to ~50 RPM), but only actual 10 RPM = 40 RPM slip
        svc.update_motor_feedback(left_rpm=10.0, right_rpm=45.0)
        svc.record_motor_command(left_speed=0.5, right_speed=0.5)
        
        left_slip, right_slip = svc.detect_slip()
        assert left_slip
        assert not right_slip

    def test_detect_right_wheel_slip(self):
        """Test detection of right wheel slipping."""
        svc = TractionControlService(slip_threshold=5.0)
        svc.update_motor_feedback(left_rpm=45.0, right_rpm=5.0)
        svc.record_motor_command(left_speed=0.5, right_speed=0.5)
        
        left_slip, right_slip = svc.detect_slip()
        assert not left_slip
        assert right_slip

    def test_both_wheels_slipping(self):
        """Test detection when both wheels slip."""
        svc = TractionControlService(slip_threshold=5.0)
        svc.update_motor_feedback(left_rpm=5.0, right_rpm=10.0)
        svc.record_motor_command(left_speed=0.8, right_speed=0.8)
        
        left_slip, right_slip = svc.detect_slip()
        assert left_slip
        assert right_slip

    def test_boost_ramp_up(self):
        """Test that boost ramps up gradually."""
        svc = TractionControlService(slip_threshold=5.0, slip_sample_required=1)
        svc.record_motor_command(left_speed=0.5, right_speed=0.5)
        svc.update_motor_feedback(left_rpm=5.0, right_rpm=50.0)
        
        # First call: slip detected but still building up
        boost_left, boost_right = svc.compute_boost()
        assert boost_left > 0.0
        assert boost_right == 0.0
        
        # Check that boost is less than max
        assert boost_left < svc.state.max_boost

    def test_boost_caps_at_max(self):
        """Test that boost doesn't exceed max_boost."""
        svc = TractionControlService(slip_threshold=5.0, slip_sample_required=1)
        svc.record_motor_command(left_speed=0.5, right_speed=0.5)
        
        # Simulate multiple calls to ramp up boost
        for _ in range(20):
            svc.update_motor_feedback(left_rpm=5.0, right_rpm=50.0)
            svc.compute_boost()
        
        assert svc.state.left_boost <= svc.state.max_boost

    def test_boost_cleared_when_slip_stops(self):
        """Test that boost is cleared when slip is no longer detected."""
        svc = TractionControlService(slip_threshold=5.0, slip_sample_required=3)
        
        # Create slip for 3 cycles to confirm
        for _ in range(3):
            svc.record_motor_command(0.5, 0.5)
            svc.update_motor_feedback(left_rpm=5.0, right_rpm=50.0)
            svc.compute_boost()
        
        assert svc.state.left_boost > 0.0
        
        # Now slip recovers
        svc.record_motor_command(0.5, 0.5)
        svc.update_motor_feedback(left_rpm=45.0, right_rpm=50.0)
        svc.compute_boost()
        
        # Boost should be cleared
        assert svc.state.left_boost == 0.0
        assert svc.state.right_boost == 0.0
        assert svc.state.total_slip_events == 1

    def test_apply_boost_to_command(self):
        """Test applying boost to motor commands."""
        svc = TractionControlService(slip_threshold=5.0, slip_sample_required=1)
        svc.update_motor_feedback(left_rpm=5.0, right_rpm=50.0)
        
        # Apply boost to command
        boosted_left, boosted_right = svc.apply_boost_to_command(0.5, 0.5)
        
        # Left should be boosted up, right unchanged
        assert boosted_left > 0.5
        assert boosted_right == 0.5

    def test_boost_preserves_direction(self):
        """Test that boost preserves motor direction."""
        svc = TractionControlService(slip_threshold=5.0, slip_sample_required=1)
        
        # Reverse with slip on left
        svc.update_motor_feedback(left_rpm=-5.0, right_rpm=-50.0)
        boosted_left, boosted_right = svc.apply_boost_to_command(-0.5, -0.5)
        
        # Left should be MORE negative (more boost in reverse)
        assert boosted_left < -0.5
        assert boosted_right == -0.5

    def test_boost_clamped_to_max_speed(self):
        """Test that boosted speed doesn't exceed max_speed."""
        svc = TractionControlService(slip_threshold=5.0, slip_sample_required=1)
        svc.update_motor_feedback(left_rpm=5.0, right_rpm=50.0)
        
        # Command high speed with slip
        boosted_left, boosted_right = svc.apply_boost_to_command(0.9, 0.9, max_speed=1.0)
        
        # Boosted should not exceed 1.0
        assert -1.0 <= boosted_left <= 1.0
        assert -1.0 <= boosted_right <= 1.0

    def test_timeout_raises_error(self):
        """Test that persistent slip raises RuntimeError after timeout."""
        svc = TractionControlService(
            slip_threshold=5.0, 
            slip_sample_required=1,
            slip_timeout_s=0.1  # Short timeout for testing
        )
        svc.record_motor_command(0.5, 0.5)
        
        import time
        start = time.monotonic()
        
        # Simulate persistent slip beyond timeout
        while time.monotonic() - start < 0.5:
            svc.update_motor_feedback(left_rpm=5.0, right_rpm=50.0)
            try:
                svc.compute_boost()
            except RuntimeError as e:
                assert "traction loss" in str(e).lower()
                return  # Success: error was raised
        
        pytest.fail("Expected RuntimeError for persistent slip timeout")

    def test_get_diagnostics(self):
        """Test diagnostic output."""
        svc = TractionControlService()
        svc.update_motor_feedback(left_rpm=50.0, right_rpm=45.0)
        svc.record_motor_command(0.5, 0.5)
        
        diags = svc.get_diagnostics()
        
        assert diags["enabled"] is True
        assert diags["left_rpm"] == 50.0
        assert diags["right_rpm"] == 45.0
        assert diags["left_commanded"] == 0.5
        assert diags["right_commanded"] == 0.5

    def test_singleton_pattern(self):
        """Test that get_traction_control_service returns same instance."""
        svc1 = get_traction_control_service()
        svc2 = get_traction_control_service()
        
        assert svc1 is svc2
