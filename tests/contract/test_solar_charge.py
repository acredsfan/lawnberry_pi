def test_solar_charge_triggers_return_when_below_threshold():
    """Contract (FR-038): Battery <20% should trigger return to solar waypoint.

    This test exercises a light-weight charge monitor that evaluates
    battery state and recommends a return-to-charge action when below
    a configurable minimum percentage. It doesn't require the full
    waypoint controller; instead, it validates the decision contract.
    """
    from backend.src.scheduler.charge_monitor import ChargeMonitor

    monitor = ChargeMonitor(min_percent=20.0)

    # Below threshold → should return to charging station
    decision = monitor.decide(battery_percent=15.0, battery_voltage=11.9)
    assert decision.should_return is True
    assert decision.target_waypoint_type == "charging_station"
    assert "below minimum" in decision.reason

    # Above threshold → continue
    ok_decision = monitor.decide(battery_percent=35.0, battery_voltage=12.2)
    assert ok_decision.should_return is False


def test_solar_charge_predicate_reflects_threshold():
    from backend.src.scheduler.charge_monitor import ChargeMonitor

    monitor = ChargeMonitor(min_percent=20.0)

    # Predicate returning latest battery percent
    percent = 18.0

    def get_percent():
        return percent

    charge_ok = monitor.make_charge_ok_predicate(get_battery_percent=get_percent)
    assert charge_ok() is False  # 18% < 20%

    # Increase charge to resume
    percent = 25.0
    assert charge_ok() is True
