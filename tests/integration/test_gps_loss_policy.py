"""Integration coverage for GPS degradation and final mission dispatch."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.src.control.commands import CommandStatus, DriveOutcome
from backend.src.nav.gps_degradation import (
    GPSDegradationConfig,
    GPSDegradationState,
    GPSDegradationStateMachine,
)
from backend.src.services.navigation_service import _NavGatewayAdapter


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


def _lost_update(policy: GPSDegradationStateMachine, now: float):
    return policy.update(
        position_available=False,
        fix_age_s=None,
        accuracy_m=None,
        dead_reckoning_active=True,
        now_monotonic=now,
    )


class _Gateway:
    def __init__(self) -> None:
        self.commands = []

    async def dispatch_drive(self, command) -> DriveOutcome:
        self.commands.append(command)
        return DriveOutcome(
            status=CommandStatus.ACCEPTED,
            audit_id=f"gps-policy-{len(self.commands)}",
            status_reason=None,
            active_interlocks=[],
            watchdog_latency_ms=1.0,
        )


def _navigation(policy: GPSDegradationStateMachine, gateway: _Gateway):
    return SimpleNamespace(
        gps_degradation=policy,
        navigation_state=SimpleNamespace(target_velocity=0.0),
        max_speed=1.0,
        autonomous_command_ttl_ms=350,
        _command_gateway=gateway,
        _global_emergency_active=lambda: False,
    )


@pytest.mark.asyncio
async def test_gps_loss_holds_then_caps_dead_reckoning_motion() -> None:
    policy = _policy()
    gateway = _Gateway()
    adapter = _NavGatewayAdapter(_navigation(policy, gateway))

    held = _lost_update(policy, 100.0)
    assert held.state is GPSDegradationState.HOLD
    assert await adapter.dispatch_drive_speeds(0.8, 0.4) is False
    assert gateway.commands == []

    degraded = _lost_update(policy, 102.1)
    assert degraded.state is GPSDegradationState.DEAD_RECKONING
    assert await adapter.dispatch_drive_speeds(0.8, 0.4) is True
    assert max(abs(gateway.commands[-1].left), abs(gateway.commands[-1].right)) == pytest.approx(
        0.2
    )


@pytest.mark.asyncio
async def test_gps_loss_budget_becomes_terminal_and_blocks_dispatch() -> None:
    policy = _policy()
    gateway = _Gateway()
    adapter = _NavGatewayAdapter(_navigation(policy, gateway))
    _lost_update(policy, 10.0)

    terminal = _lost_update(policy, 20.1)

    assert terminal.state is GPSDegradationState.TERMINAL
    assert terminal.reason == "GPS_POSITION_UNAVAILABLE"
    assert await adapter.dispatch_drive_speeds(0.2, 0.2) is False
    assert gateway.commands == []


def test_gps_recovery_requires_hysteresis_before_nominal_motion() -> None:
    policy = _policy()
    _lost_update(policy, 100.0)
    _lost_update(policy, 102.1)

    states = [
        policy.update(
            position_available=True,
            fix_age_s=0.1,
            accuracy_m=0.03,
            dead_reckoning_active=False,
            now_monotonic=now,
        ).state
        for now in (103.0, 103.1, 103.2)
    ]

    assert states == [
        GPSDegradationState.RECOVERING,
        GPSDegradationState.RECOVERING,
        GPSDegradationState.NOMINAL,
    ]
