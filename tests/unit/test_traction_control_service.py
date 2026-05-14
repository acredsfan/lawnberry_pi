"""Unit tests for TractionControlService — underpower-based adaptive boost."""

import pytest
import time
from unittest.mock import patch


class TestTractionControlService:

    def test_init_state(self):
        from backend.src.services.traction_control_service import TractionControlService
        svc = TractionControlService()
        assert svc.enabled is True
        assert svc.state.underpower_boost == 0.0
        assert svc.state.underpower_start_time is None

    def test_update_motor_feedback_stores_rpms(self):
        from backend.src.services.traction_control_service import TractionControlService
        svc = TractionControlService()
        svc.update_motor_feedback(25.0, 30.0)
        assert svc.state.left_rpm == 25.0
        assert svc.state.right_rpm == 30.0

    def test_below_min_speed_no_boost(self):
        """Commands below min_speed_for_detection never trigger boost."""
        from backend.src.services.traction_control_service import TractionControlService
        svc = TractionControlService(min_speed_for_detection=0.25)
        svc.update_velocity_feedback(0.1, 0.0)  # commanded below threshold
        with patch("time.monotonic", return_value=100.0):
            svc.update_velocity_feedback(0.1, 0.0)
        with patch("time.monotonic", return_value=110.0):  # 10s later
            boost = svc.detect_underpower()
        assert boost == 0.0

    def test_underpower_no_boost_when_fast_enough(self):
        """No boost when measured >= 0.8 * commanded."""
        from backend.src.services.traction_control_service import TractionControlService
        svc = TractionControlService()
        svc.update_velocity_feedback(0.5, 0.42)  # 0.42 >= 0.8 * 0.5
        assert svc.detect_underpower() == 0.0

    def test_underpower_stage1_after_2s(self):
        """Boost reaches 0.15 after 2s of measured < 0.5 * commanded."""
        from backend.src.services.traction_control_service import TractionControlService
        svc = TractionControlService(min_speed_for_detection=0.25)
        with patch("time.monotonic", return_value=0.0):
            svc.update_velocity_feedback(0.5, 0.2)  # start timer
        with patch("time.monotonic", return_value=2.1):
            boost = svc.detect_underpower()
        assert boost == pytest.approx(0.15)

    def test_underpower_stage2_after_4s(self):
        """Boost reaches 0.30 after 4s of measured < 0.5 * commanded."""
        from backend.src.services.traction_control_service import TractionControlService
        svc = TractionControlService(min_speed_for_detection=0.25)
        with patch("time.monotonic", return_value=0.0):
            svc.update_velocity_feedback(0.5, 0.2)
        with patch("time.monotonic", return_value=4.1):
            boost = svc.detect_underpower()
        assert boost == pytest.approx(0.30)

    def test_underpower_resets_on_recovery(self):
        """Boost returns to 0 when measured >= 0.8 * commanded."""
        from backend.src.services.traction_control_service import TractionControlService
        svc = TractionControlService(min_speed_for_detection=0.25)
        with patch("time.monotonic", return_value=0.0):
            svc.update_velocity_feedback(0.5, 0.2)
        with patch("time.monotonic", return_value=4.1):
            svc.detect_underpower()  # sets stage 2 (0.30)
        # Recovery: measured now sufficient
        svc.update_velocity_feedback(0.5, 0.45)  # 0.45 >= 0.8 * 0.5
        assert svc.detect_underpower() == 0.0
        assert svc.state.underpower_start_time is None
        assert svc.state.underpower_boost == 0.0

    def test_apply_boost_symmetric(self):
        """Boost is applied equally to both wheels (no heading drift)."""
        from backend.src.services.traction_control_service import TractionControlService
        svc = TractionControlService(min_speed_for_detection=0.25)
        with patch("time.monotonic", return_value=0.0):
            svc.update_velocity_feedback(0.5, 0.2)
        with patch("time.monotonic", return_value=2.1):
            left, right = svc.apply_boost_to_command(0.5, 0.5, max_speed=1.0)
        # Both should be 0.5 * 1.15 = 0.575
        assert left == pytest.approx(0.575, abs=0.001)
        assert right == pytest.approx(0.575, abs=0.001)

    def test_apply_boost_clamps_to_max_speed(self):
        """Boosted values are clamped to max_speed."""
        from backend.src.services.traction_control_service import TractionControlService
        svc = TractionControlService(min_speed_for_detection=0.25)
        with patch("time.monotonic", return_value=0.0):
            svc.update_velocity_feedback(0.8, 0.2)
        with patch("time.monotonic", return_value=4.1):
            left, right = svc.apply_boost_to_command(0.8, 0.8, max_speed=0.8)
        assert left <= 0.8
        assert right <= 0.8

    def test_apply_boost_no_op_when_zero_boost(self):
        """When no underpower, apply_boost_to_command returns commands unchanged."""
        from backend.src.services.traction_control_service import TractionControlService
        svc = TractionControlService()
        svc.update_velocity_feedback(0.5, 0.45)  # fast enough
        left, right = svc.apply_boost_to_command(0.4, 0.6, max_speed=0.8)
        assert left == pytest.approx(0.4)
        assert right == pytest.approx(0.6)

    def test_get_diagnostics_has_expected_keys(self):
        from backend.src.services.traction_control_service import TractionControlService
        svc = TractionControlService()
        svc.update_motor_feedback(20.0, 22.0)
        diags = svc.get_diagnostics()
        assert "left_rpm" in diags
        assert "right_rpm" in diags
        assert "commanded_velocity_mps" in diags
        assert "measured_velocity_mps" in diags
        assert "underpower_boost" in diags
        assert "underpower_duration_s" in diags

    def test_singleton_returns_same_instance(self):
        from backend.src.services.traction_control_service import get_traction_control_service
        svc1 = get_traction_control_service()
        svc2 = get_traction_control_service()
        assert svc1 is svc2
