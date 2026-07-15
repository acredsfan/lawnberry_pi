import pytest

from backend.src.nav.gps_degradation import (
    GPSDegradationConfig,
    GPSDegradationState,
    GPSDegradationStateMachine,
)


def _policy() -> GPSDegradationStateMachine:
    return GPSDegradationStateMachine(
        GPSDegradationConfig(
            max_accuracy_m=0.25,
            max_fix_age_s=2.0,
            hold_grace_s=2.0,
            max_degraded_s=10.0,
            recovery_samples=3,
            degraded_speed_cap_mps=0.2,
        )
    )


def _update(policy: GPSDegradationStateMachine, now: float, **overrides):
    values = {
        "position_available": True,
        "fix_age_s": 0.1,
        "accuracy_m": 0.05,
        "dead_reckoning_active": False,
        "now_monotonic": now,
    }
    values.update(overrides)
    return policy.update(**values)


def test_gps_degradation_holds_then_enters_bounded_dead_reckoning():
    policy = _policy()
    policy.start_mission()

    first = _update(policy, 100.0, fix_age_s=3.0)
    degraded = _update(policy, 102.1, fix_age_s=3.0, dead_reckoning_active=True)

    assert first.state is GPSDegradationState.HOLD
    assert first.motion_held
    assert degraded.state is GPSDegradationState.DEAD_RECKONING
    assert degraded.speed_cap_mps == pytest.approx(0.2)


def test_gps_degradation_becomes_terminal_after_budget():
    policy = _policy()
    _update(policy, 100.0, position_available=False)

    terminal = _update(policy, 110.1, position_available=False)

    assert terminal.state is GPSDegradationState.TERMINAL
    assert terminal.terminal
    assert terminal.reason == "GPS_POSITION_UNAVAILABLE"


def test_gps_recovery_requires_consecutive_good_samples():
    policy = _policy()
    _update(policy, 100.0, accuracy_m=1.0)
    _update(policy, 102.1, accuracy_m=1.0)

    recovering = _update(policy, 103.0)
    second = _update(policy, 103.1)
    nominal = _update(policy, 103.2)

    assert recovering.state is GPSDegradationState.RECOVERING
    assert second.state is GPSDegradationState.RECOVERING
    assert nominal.state is GPSDegradationState.NOMINAL
    assert nominal.speed_cap_mps is None


def test_terminal_state_is_sticky_until_next_mission():
    policy = _policy()
    _update(policy, 10.0, position_available=False)
    _update(policy, 20.1, position_available=False)

    assert _update(policy, 21.0).state is GPSDegradationState.TERMINAL
    assert policy.start_mission().state is GPSDegradationState.NOMINAL


def test_invalid_policy_is_rejected():
    with pytest.raises(ValueError):
        GPSDegradationConfig(hold_grace_s=10.0, max_degraded_s=5.0)
