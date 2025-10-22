import pytest

def test_interlock_blocks_motor_operations():
    try:
        from backend.src.safety.interlock_validator import InterlockActiveError, InterlockValidator
        from backend.src.safety.motor_authorization import MotorAuthorization
    except Exception:
        pytest.skip("Interlock validator not implemented yet")

    auth = MotorAuthorization()
    validator = InterlockValidator()

    # Activate an interlock
    validator.set_interlock("tilt_detected", True)

    # Authorize should not enable motion if interlocks active
    auth.authorize()
    try:
        validator.assert_safe_to_move()
        pytest.fail("Interlock should block motion")
    except InterlockActiveError:
        pass
