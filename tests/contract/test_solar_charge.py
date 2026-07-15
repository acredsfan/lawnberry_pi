from types import SimpleNamespace


class _Energy:
    def __init__(self, action: str, reason: str):
        self.action = action
        self.reason = reason

    def runtime_policy(self, _mission):
        return SimpleNamespace(action=self.action, reason_code=self.reason)


def test_solar_charge_triggers_canonical_return_policy():
    """Contract (FR-038): Battery <20% should trigger return to solar waypoint.

    This test exercises a light-weight charge monitor that evaluates
    battery state and recommends a return-to-charge action when below
    a configurable minimum percentage. It doesn't require the full
    waypoint controller; instead, it validates the decision contract.
    """
    from backend.src.scheduler.charge_monitor import ChargeMonitor

    energy = _Energy("return_home", "ENERGY_RETURN_RESERVE_REACHED")
    monitor = ChargeMonitor(energy)

    # Below threshold → should return to charging station
    decision = monitor.decide()
    assert decision.should_return is True
    assert decision.target_waypoint_type == "charging_station"
    assert decision.reason == "ENERGY_RETURN_RESERVE_REACHED"

    energy.action = "continue"
    energy.reason = "ENERGY_RESERVE_AVAILABLE"
    ok_decision = monitor.decide()
    assert ok_decision.should_return is False


def test_solar_charge_predicate_reflects_threshold():
    from backend.src.scheduler.charge_monitor import ChargeMonitor

    energy = _Energy("return_home", "ENERGY_RETURN_RESERVE_REACHED")
    monitor = ChargeMonitor(energy)
    charge_ok = monitor.make_charge_ok_predicate()
    assert charge_ok() is False

    energy.action = "continue"
    assert charge_ok() is True


def test_critical_energy_policy_never_requests_return():
    from backend.src.scheduler.charge_monitor import ChargeMonitor

    decision = ChargeMonitor(_Energy("critical_stop", "ENERGY_CRITICAL_STOP")).decide()

    assert decision.should_return is False
    assert decision.hard_stop is True
