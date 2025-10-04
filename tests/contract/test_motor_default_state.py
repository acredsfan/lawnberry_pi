def test_motors_default_off_on_startup():
    try:
        from backend.src.safety.motor_authorization import MotorAuthorization
    except Exception:
        import pytest
        pytest.skip("MotorAuthorization not implemented yet")

    auth = MotorAuthorization()
    assert not auth.is_enabled(), "Motors must be OFF by default until explicitly authorized"
