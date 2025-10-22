from __future__ import annotations

import asyncio
import time

from backend.src.safety.motor_authorization import MotorAuthorization
from backend.src.safety.estop_handler import EstopHandler
from backend.src.safety.watchdog import Watchdog
from backend.src.safety.interlock_validator import InterlockValidator, InterlockActiveError
from backend.src.safety.safety_triggers import SafetyTriggerManager
from backend.src.core.config_loader import ConfigLoader


def test_estop_latency_under_limit():
    # Load configured safety limits
    _, limits = ConfigLoader().get()
    auth = MotorAuthorization()
    estop = EstopHandler(auth)
    auth.authorize()
    assert auth.is_enabled()
    t0 = time.perf_counter()
    estop.trigger_estop("test")
    # Busy-wait micro sleep to detect flip
    while auth.is_enabled():
        time.sleep(0)
    dt_ms = (time.perf_counter() - t0) * 1000.0
    assert dt_ms <= limits.estop_latency_ms, f"E-stop latency {dt_ms:.3f}ms exceeds limit {limits.estop_latency_ms}ms"


def test_tilt_detection_response_under_limit():
    _, limits = ConfigLoader().get()
    mgr = SafetyTriggerManager()
    t0 = time.perf_counter()
    triggered = mgr.trigger_tilt(roll_deg=limits.tilt_threshold_degrees + 1, pitch_deg=0, threshold_deg=limits.tilt_threshold_degrees)
    assert triggered is True
    dt_ms = (time.perf_counter() - t0) * 1000.0
    assert dt_ms <= limits.tilt_cutoff_latency_ms, f"Tilt response {dt_ms:.3f}ms exceeds limit {limits.tilt_cutoff_latency_ms}ms"


def test_interlock_validator_blocks_and_raises():
    iv = InterlockValidator()
    iv.set_interlock("blade_guard_open", True)
    assert iv.is_any_active() is True
    try:
        iv.assert_safe_to_move()
        assert False, "Expected InterlockActiveError"
    except InterlockActiveError:
        pass
    iv.set_interlock("blade_guard_open", False)
    assert iv.is_any_active() is False


def test_watchdog_timeout_triggers_estop():
    auth = MotorAuthorization()
    estop = EstopHandler(auth)
    wd = Watchdog(estop, timeout_ms=50)

    async def run_test():
        await wd.start()
        auth.authorize()
        assert auth.is_enabled()
        # Heartbeat once then let it timeout
        wd.heartbeat()
        t0 = time.perf_counter()
        # Wait until auth revoked
        for _ in range(200):
            await asyncio.sleep(0.005)
            if not auth.is_enabled():
                break
        dt_ms = (time.perf_counter() - t0) * 1000.0
        await wd.stop()
        assert not auth.is_enabled()
        assert dt_ms <= 200.0, f"Watchdog response too slow: {dt_ms:.1f}ms"

    asyncio.run(run_test())
