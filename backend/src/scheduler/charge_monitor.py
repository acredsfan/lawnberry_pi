from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any


@dataclass
class ChargeDecision:
    should_return: bool
    reason: str
    target_waypoint_type: str | None = None  # e.g., "charging_station" or "home"
    hard_stop: bool = False


class ChargeMonitor:
    """Compatibility adapter over the canonical :class:`EnergyService` policy."""

    def __init__(self, energy_service: Any):
        if not callable(getattr(energy_service, "runtime_policy", None)):
            raise TypeError("ChargeMonitor requires the canonical EnergyService")
        self._energy = energy_service

    def decide(
        self,
        mission: Any | None = None,
    ) -> ChargeDecision:
        """Translate the canonical runtime policy into the legacy decision shape."""
        policy = self._energy.runtime_policy(
            mission or SimpleNamespace(name="", waypoints=[])
        )
        if policy.action == "critical_stop":
            return ChargeDecision(
                should_return=False,
                reason=policy.reason_code,
                hard_stop=True,
            )
        if policy.action in {"return_home", "stop"}:
            return ChargeDecision(
                should_return=True,
                reason=policy.reason_code,
                target_waypoint_type="charging_station",
            )
        return ChargeDecision(
            should_return=False,
            reason=policy.reason_code,
            target_waypoint_type=None,
        )

    def make_charge_ok_predicate(self, mission: Any | None = None):
        """Build a legacy scheduler predicate backed by canonical live policy."""

        def predicate() -> bool:
            return self._energy.runtime_policy(
                mission or SimpleNamespace(name="", waypoints=[])
            ).action in {"continue", "continue_return"}

        return predicate


__all__ = ["ChargeMonitor", "ChargeDecision"]
