import asyncio
import os

import pytest


@pytest.mark.asyncio
async def test_watchdog_triggers_estop_on_timeout():
    os.environ.setdefault("SIM_MODE", "1")
    try:
        from backend.src.safety.estop_handler import EstopHandler
        from backend.src.safety.motor_authorization import MotorAuthorization
        from backend.src.safety.watchdog import Watchdog
    except Exception:
        import pytest
        pytest.skip("Watchdog not implemented yet")

    auth = MotorAuthorization()
    auth.authorize()
    estop = EstopHandler(auth)
    wd = Watchdog(estop, timeout_ms=50)

    await wd.start()
    # No heartbeat, let it timeout
    await asyncio.sleep(0.1)
    await wd.stop()

    assert not auth.is_enabled(), "Watchdog timeout must disable motors (E-stop)"
