from __future__ import annotations

import os

from backend.src.safety.safety_triggers import get_safety_trigger_manager
from backend.src.core.robot_state_manager import get_robot_state_manager


def test_tilt_and_obstacle_interlocks_activate_and_reflect_in_state():
    os.environ["SIM_MODE"] = "1"
    mgr = get_safety_trigger_manager()
    # Clear any previous state by creating fresh manager reference
    st = get_robot_state_manager().get_state()
    st.active_interlocks = []

    # Trigger tilt
    assert mgr.trigger_tilt(roll_deg=35.0, pitch_deg=0.0, threshold_deg=30.0)
    st = get_robot_state_manager().get_state()
    kinds = {i.interlock_type.value for i in st.active_interlocks}
    assert "tilt_detected" in kinds

    # Trigger obstacle
    assert mgr.trigger_obstacle(distance_m=0.15, threshold_m=0.2)
    st = get_robot_state_manager().get_state()
    kinds = {i.interlock_type.value for i in st.active_interlocks}
    assert "obstacle_detected" in kinds
