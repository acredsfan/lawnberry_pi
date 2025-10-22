import asyncio
import os

import pytest

from backend.src.core.robot_state_manager import get_robot_state_manager
from backend.src.models.robot_state import NavigationMode
from backend.src.nav.gps_degradation import (
    GPSDegradationConfig,
    GPSDegradationMonitor,
)


@pytest.mark.asyncio
async def test_gps_degradation_switches_to_manual_on_poor_accuracy():
    os.environ["SIM_MODE"] = "1"

    # Ensure AUTONOMOUS mode with poor accuracy
    mgr = get_robot_state_manager()
    st = mgr.get_state()
    st.navigation_mode = NavigationMode.AUTONOMOUS
    st.position.latitude = 37.0
    st.position.longitude = -122.0
    st.position.accuracy_m = 6.5  # > 5m threshold
    st.touch()

    monitor = GPSDegradationMonitor(
        GPSDegradationConfig(max_accuracy_m=5.0, max_fix_age_s=10.0, check_interval_s=0.05)
    )
    await monitor.start()
    await asyncio.sleep(0.2)
    await monitor.stop()

    assert st.navigation_mode == NavigationMode.MANUAL


@pytest.mark.asyncio
async def test_gps_degradation_switches_to_manual_on_fix_timeout():
    os.environ["SIM_MODE"] = "1"

    mgr = get_robot_state_manager()
    st = mgr.get_state()
    st.navigation_mode = NavigationMode.AUTONOMOUS
    st.position.latitude = 37.0
    st.position.longitude = -122.0
    st.position.accuracy_m = 1.0  # good accuracy, but we'll age it out
    # Manually set last_updated sufficiently in the past
    import datetime as dt
    st.last_updated = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1.0)

    monitor = GPSDegradationMonitor(
        GPSDegradationConfig(max_accuracy_m=5.0, max_fix_age_s=0.2, check_interval_s=0.05)
    )
    await monitor.start()
    await asyncio.sleep(0.3)
    await monitor.stop()

    assert st.navigation_mode == NavigationMode.MANUAL
