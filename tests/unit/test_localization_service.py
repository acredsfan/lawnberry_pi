"""Unit tests for LocalizationService.

All tests are runnable with no hardware. Use:
    SIM_MODE=1 uv run pytest tests/unit/test_localization_service.py -v
"""


# --- Task 2: model imports ---------------------------------------------------

def test_pose_quality_enum_members():
    from backend.src.services.localization_service import PoseQuality
    members = {q.value for q in PoseQuality}
    assert members == {"rtk_fixed", "gps_float", "gps_degraded", "dead_reckoning", "stale"}


def test_localization_state_defaults():
    from backend.src.services.localization_service import LocalizationState
    state = LocalizationState()
    assert state.current_position is None
    assert state.heading is None
    assert state.gps_cog is None
    assert state.velocity is None
    assert state.quality.value == "stale"
    assert state.dead_reckoning_active is False
    assert state.dead_reckoning_drift is None
    assert state.last_gps_fix is None
