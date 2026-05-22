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


def test_gateway_watchdog_heartbeat_integration():
    """Verify that MotorCommandGateway and Watchdog integration handles heartbeats and triggers estop on disconnect."""
    from backend.src.control.command_gateway import MotorCommandGateway
    from backend.src.control.commands import DriveCommand
    from unittest.mock import MagicMock
    from typing import Any

    safety = {"emergency_stop_active": False, "estop_reason": None}
    blade = {"active": False}
    client_em = {}
    rest_mock = MagicMock()
    rest_mock._emergency_until = 0.0

    gw = MotorCommandGateway(
        safety_state=safety,
        blade_state=blade,
        client_emergency=client_em,
        robohat=MagicMock(status=MagicMock(serial_connected=False)),
        persistence=MagicMock(),
        _rest_module=rest_mock,
    )
    # Ensure it returns an empty list of interlocks synchronously
    async def mock_interlocks():
        return []
    gw._check_manual_drive_interlocks = mock_interlocks

    auth = MotorAuthorization()
    auth.authorize()
    assert auth.is_enabled()

    class GatewayEstopHandler(EstopHandler):
        def __init__(self, auth: MotorAuthorization, gateway: Any) -> None:
            super().__init__(auth)
            self._gateway = gateway
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None

        def trigger_estop(self, reason: str = "unknown") -> None:
            super().trigger_estop(reason)
            loop = self._loop
            if loop is not None and loop.is_running():
                from backend.src.control.commands import EmergencyTrigger
                asyncio.run_coroutine_threadsafe(
                    self._gateway.trigger_emergency(
                        EmergencyTrigger(reason=reason, source="safety_trigger")
                    ),
                    loop
                )
            else:
                try:
                    self._gateway._safety_state["emergency_stop_active"] = True
                    self._gateway._safety_state["estop_reason"] = reason
                    self._gateway._blade_state["active"] = False
                except Exception:
                    pass

    async def run_test():
        estop = GatewayEstopHandler(auth, gw)
        wd = Watchdog(estop, timeout_ms=100)
        gw.set_watchdog(wd)
        await wd.start()
        try:
            # First, send a drive command which should feed the heartbeat
            cmd = DriveCommand(left=0.5, right=0.5, source="manual", duration_ms=500)
            await gw.dispatch_drive(cmd)
            
            # Watchdog timeout is 100ms. Sleep 50ms (less than timeout) and send another drive command
            await asyncio.sleep(0.05)
            assert auth.is_enabled()
            assert not gw.is_emergency_active()

            await gw.dispatch_drive(cmd)

            # Sleep another 50ms to ensure it's still alive
            await asyncio.sleep(0.05)
            assert auth.is_enabled()
            assert not gw.is_emergency_active()

            # Now wait >100ms without sending drive commands to let it timeout
            t0 = time.perf_counter()
            for _ in range(100):
                await asyncio.sleep(0.005)
                if not auth.is_enabled() or gw.is_emergency_active():
                    break
            dt_ms = (time.perf_counter() - t0) * 1000.0

            assert not auth.is_enabled()
            assert gw.is_emergency_active()
            assert safety["emergency_stop_active"] is True
            assert safety["estop_reason"] == "watchdog_timeout"
            assert dt_ms <= 250.0, f"Watchdog took too long to trigger: {dt_ms:.1f}ms"
        finally:
            await wd.stop()

    asyncio.run(run_test())

