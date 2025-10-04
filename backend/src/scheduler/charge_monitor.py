from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ChargeDecision:
    should_return: bool
    reason: str
    target_waypoint_type: str | None = None  # e.g., "charging_station" or "home"


class ChargeMonitor:
    """Simple solar/battery charge monitor (FR-038).

    Decision contract only: determines whether the robot should
    return to a charging station based on state-of-charge. This is
    intentionally minimal for contract tests and SIM_MODE.
    """

    def __init__(self, min_percent: float = 20.0, critical_percent: float = 10.0):
        if min_percent <= 0 or min_percent > 100:
            raise ValueError("min_percent must be in (0, 100]")
        if not (0 < critical_percent <= min_percent):
            raise ValueError("critical_percent must be >0 and <= min_percent")
        self.min_percent = float(min_percent)
        self.critical_percent = float(critical_percent)

    def decide(
        self,
        *,
        battery_percent: float | None,
        battery_voltage: float | None = None,
    ) -> ChargeDecision:
        """Return a decision about whether to return to the charger.

        Inputs:
        - battery_percent: SOC percentage (0-100)
        - battery_voltage: optional diagnostic info (not used in threshold yet)
        """
        if battery_percent is None:
            # Fail-safe: without SOC info, recommend return conservatively
            return ChargeDecision(
                should_return=True,
                reason="unknown battery percent; conservative return",
                target_waypoint_type="charging_station",
            )

        if battery_percent < self.critical_percent:
            return ChargeDecision(
                should_return=True,
                reason=f"critical battery {battery_percent:.1f}% < {self.critical_percent:.0f}%",
                target_waypoint_type="charging_station",
            )

        if battery_percent < self.min_percent:
            return ChargeDecision(
                should_return=True,
                reason=f"battery {battery_percent:.1f}% below minimum {self.min_percent:.0f}%",
                target_waypoint_type="charging_station",
            )

        return ChargeDecision(
            should_return=False,
            reason="battery sufficient",
            target_waypoint_type=None,
        )

    def make_charge_ok_predicate(
        self, *, get_battery_percent: Callable[[], float | None]
    ) -> Callable[[], bool]:
        """Build a predicate compatible with JobScheduler's gating.

        Returns True when charge is sufficient to continue or start jobs.
        """

        def predicate() -> bool:
            soc = get_battery_percent()
            # JobScheduler expects True to proceed; proceed only if SOC >= min_percent
            if soc is None:
                return False
            return float(soc) >= self.min_percent

        return predicate


__all__ = ["ChargeMonitor", "ChargeDecision"]
