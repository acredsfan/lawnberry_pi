import time


def test_estop_triggers_motor_disable_quickly():
    try:
        from backend.src.safety.estop_handler import EstopHandler
        from backend.src.safety.motor_authorization import MotorAuthorization
    except Exception:
        # Will be implemented in Phase 2
        import pytest
        pytest.skip("Safety services not implemented yet")

    auth = MotorAuthorization()
    auth.authorize()
    handler = EstopHandler(auth)

    start = time.perf_counter()
    handler.trigger_estop(reason="test")
    end = time.perf_counter()

    # Verify motors disabled and latency within 100ms
    assert not auth.is_enabled(), "E-stop must disable motors immediately"
    latency_ms = (end - start) * 1000.0
    assert latency_ms <= 100.0, f"E-stop latency {latency_ms:.2f}ms exceeds 100ms"
