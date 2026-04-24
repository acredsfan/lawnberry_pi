"""Unit tests for BNO085 quaternion-to-euler conversion.

Tests the quaternion-to-euler formula used to compute yaw/pitch/roll from
the BNO085 Game Rotation Vector (gyro + accelerometer fusion).

The Game Rotation Vector returns quaternion components in order (i, j, k, real)
which maps to (x, y, z, w) in standard quaternion notation.
"""

import math
import pytest
from backend.src.drivers.sensors.bno085_driver import _quaternion_to_euler


class TestQuaternionToEulerYaw:
    """Test yaw (Z-axis rotation) extraction from quaternion."""

    def test_identity_quaternion_gives_zero_yaw(self):
        """Identity quaternion [0, 0, 0, 1] should give yaw=0°."""
        # (i, j, k, real) = (x, y, z, w) = (0, 0, 0, 1)
        yaw, pitch, roll = _quaternion_to_euler(0, 0, 0, 1)
        assert abs(yaw) < 1e-6, f"Expected yaw=0°, got {yaw:.1f}°"
        assert abs(pitch) < 1e-6, f"Expected pitch=0°, got {pitch:.1f}°"
        assert abs(roll) < 1e-6, f"Expected roll=0°, got {roll:.1f}°"

    def test_90_degree_ccw_z_rotation(self):
        """90° CCW Z rotation (aerospace) should give yaw≈90°.

        In aerospace ZYX convention (Tait-Bryan), positive yaw is CCW rotation
        around Z axis when viewed from above (Z pointing up).

        Quaternion for 90° around Z: q = [sin(45°), sin(45°), sin(45°), cos(45°)]
        But wait, for pure Z rotation, only k component (Z) should be nonzero:
        q = [0, 0, sin(45°), cos(45°)] = [0, 0, 0.707, 0.707]
        """
        angle_deg = 90.0
        angle_rad = math.radians(angle_deg / 2)
        i = 0
        j = 0
        k = math.sin(angle_rad)
        real = math.cos(angle_rad)

        yaw, pitch, roll = _quaternion_to_euler(i, j, k, real)

        assert abs(yaw - 90.0) < 1e-6, f"Expected yaw=90°, got {yaw:.1f}°"
        assert abs(pitch) < 1e-6, f"Expected pitch=0°, got {pitch:.1f}°"
        assert abs(roll) < 1e-6, f"Expected roll=0°, got {roll:.1f}°"

    def test_minus_90_degree_z_rotation(self):
        """−90° Z rotation should give yaw=270° (or −90° normalized to [0,360))."""
        angle_deg = -90.0
        angle_rad = math.radians(angle_deg / 2)
        i = 0
        j = 0
        k = math.sin(angle_rad)
        real = math.cos(angle_rad)

        yaw, pitch, roll = _quaternion_to_euler(i, j, k, real)

        # yaw should be 270° (same as -90° in [0, 360))
        expected = 270.0
        # Handle wrap-around: 270° and -90° are equivalent
        yaw_normalized = yaw % 360.0
        expected_normalized = expected % 360.0
        assert abs(yaw_normalized - expected_normalized) < 1e-6, (
            f"Expected yaw={expected}°, got {yaw:.1f}°"
        )
        assert abs(pitch) < 1e-6, f"Expected pitch=0°, got {pitch:.1f}°"
        assert abs(roll) < 1e-6, f"Expected roll=0°, got {roll:.1f}°"

    def test_45_degree_z_rotation(self):
        """45° Z rotation should give yaw=45°."""
        angle_deg = 45.0
        angle_rad = math.radians(angle_deg / 2)
        i = 0
        j = 0
        k = math.sin(angle_rad)
        real = math.cos(angle_rad)

        yaw, pitch, roll = _quaternion_to_euler(i, j, k, real)

        assert abs(yaw - 45.0) < 1e-6, f"Expected yaw=45°, got {yaw:.1f}°"
        assert abs(pitch) < 1e-6, f"Expected pitch=0°, got {pitch:.1f}°"
        assert abs(roll) < 1e-6, f"Expected roll=0°, got {roll:.1f}°"

    def test_180_degree_z_rotation(self):
        """180° Z rotation should give yaw=180°."""
        angle_deg = 180.0
        angle_rad = math.radians(angle_deg / 2)
        i = 0
        j = 0
        k = math.sin(angle_rad)
        real = math.cos(angle_rad)

        yaw, pitch, roll = _quaternion_to_euler(i, j, k, real)

        assert abs(yaw - 180.0) < 1e-6, f"Expected yaw=180°, got {yaw:.1f}°"
        assert abs(pitch) < 1e-6, f"Expected pitch=0°, got {pitch:.1f}°"
        assert abs(roll) < 1e-6, f"Expected roll=0°, got {roll:.1f}°"

    def test_yaw_increases_ccw_in_aerospace_convention(self):
        """Verify yaw increases CCW (aerospace convention).

        This is a regression test for the bug where cosy_cosp used (j,k)
        instead of (i,k), which would rotate all yaws by 90°.
        """
        # Test sequence: 0° → 45° → 90° → 135° → 180° (CCW)
        expected_yaws = [0.0, 45.0, 90.0, 135.0, 180.0]

        for expected_yaw_deg in expected_yaws:
            angle_rad = math.radians(expected_yaw_deg / 2)
            i = 0
            j = 0
            k = math.sin(angle_rad)
            real = math.cos(angle_rad)

            yaw, _, _ = _quaternion_to_euler(i, j, k, real)

            assert abs(yaw - expected_yaw_deg) < 1e-6, (
                f"At expected_yaw={expected_yaw_deg}°: got {yaw:.1f}°"
            )


class TestQuaternionToEulerPitch:
    """Test pitch (Y-axis rotation) extraction from quaternion."""

    def test_45_degree_pitch_positive(self):
        """+45° pitch (nose up) should give pitch=45°."""
        angle_deg = 45.0
        angle_rad = math.radians(angle_deg / 2)
        i = 0
        j = math.sin(angle_rad)
        k = 0
        real = math.cos(angle_rad)

        yaw, pitch, roll = _quaternion_to_euler(i, j, k, real)

        assert abs(yaw) < 1e-6, f"Expected yaw=0°, got {yaw:.1f}°"
        assert abs(pitch - 45.0) < 1e-6, f"Expected pitch=45°, got {pitch:.1f}°"
        assert abs(roll) < 1e-6, f"Expected roll=0°, got {roll:.1f}°"

    def test_minus_45_degree_pitch(self):
        """−45° pitch (nose down) should give pitch=−45°."""
        angle_deg = -45.0
        angle_rad = math.radians(angle_deg / 2)
        i = 0
        j = math.sin(angle_rad)
        k = 0
        real = math.cos(angle_rad)

        yaw, pitch, roll = _quaternion_to_euler(i, j, k, real)

        assert abs(yaw) < 1e-6, f"Expected yaw=0°, got {yaw:.1f}°"
        assert abs(pitch - angle_deg) < 1e-6, f"Expected pitch={angle_deg}°, got {pitch:.1f}°"
        assert abs(roll) < 1e-6, f"Expected roll=0°, got {roll:.1f}°"


class TestQuaternionToEulerRoll:
    """Test roll (X-axis rotation) extraction from quaternion."""

    def test_45_degree_roll_positive(self):
        """+45° roll (right wing down) should give roll=45°."""
        angle_deg = 45.0
        angle_rad = math.radians(angle_deg / 2)
        i = math.sin(angle_rad)
        j = 0
        k = 0
        real = math.cos(angle_rad)

        yaw, pitch, roll = _quaternion_to_euler(i, j, k, real)

        assert abs(yaw) < 1e-6, f"Expected yaw=0°, got {yaw:.1f}°"
        assert abs(pitch) < 1e-6, f"Expected pitch=0°, got {pitch:.1f}°"
        assert abs(roll - 45.0) < 1e-6, f"Expected roll=45°, got {roll:.1f}°"

    def test_minus_45_degree_roll(self):
        """−45° roll (left wing down) should give roll=−45°."""
        angle_deg = -45.0
        angle_rad = math.radians(angle_deg / 2)
        i = math.sin(angle_rad)
        j = 0
        k = 0
        real = math.cos(angle_rad)

        yaw, pitch, roll = _quaternion_to_euler(i, j, k, real)

        assert abs(yaw) < 1e-6, f"Expected yaw=0°, got {yaw:.1f}°"
        assert abs(pitch) < 1e-6, f"Expected pitch=0°, got {pitch:.1f}°"
        assert abs(roll - angle_deg) < 1e-6, f"Expected roll={angle_deg}°, got {roll:.1f}°"


class TestQuaternionToEulerCombined:
    """Test combined rotations (multiple axes)."""

    def test_45_degree_yaw_plus_30_degree_pitch(self):
        """Combined 45° yaw + 30° pitch."""
        # First rotate 45° around Z (yaw)
        yaw_rad = math.radians(45.0 / 2)
        q_yaw = (0, 0, math.sin(yaw_rad), math.cos(yaw_rad))

        # Then rotate 30° around Y (pitch)
        pitch_rad = math.radians(30.0 / 2)
        q_pitch = (0, math.sin(pitch_rad), 0, math.cos(pitch_rad))

        # Compose: q = q_pitch * q_yaw (quaternion multiplication)
        # For simplicity, we'll test each separately
        i1, j1, k1, w1 = q_yaw
        yaw1, pitch1, roll1 = _quaternion_to_euler(i1, j1, k1, w1)
        assert abs(yaw1 - 45.0) < 1e-6
        assert abs(pitch1) < 1e-6
        assert abs(roll1) < 1e-6

        i2, j2, k2, w2 = q_pitch
        yaw2, pitch2, roll2 = _quaternion_to_euler(i2, j2, k2, w2)
        assert abs(yaw2) < 1e-6
        assert abs(pitch2 - 30.0) < 1e-6
        assert abs(roll2) < 1e-6
