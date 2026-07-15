from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.src.api import rest
from backend.src.control.commands import CommandStatus, DriveOutcome
from backend.src.services.navigation_service import NavigationService


@pytest.mark.asyncio
async def test_preset_turn_dispatches_only_through_command_gateway(monkeypatch) -> None:
    monkeypatch.setenv("SIM_MODE", "0")
    monkeypatch.setattr(rest, "_resolve_manual_session", lambda _session_id: {"operator": True})

    navigation_state = SimpleNamespace(heading=0.0)
    monkeypatch.setattr(
        NavigationService,
        "get_instance",
        classmethod(lambda cls: SimpleNamespace(navigation_state=navigation_state)),
    )

    commands = []

    class _Gateway:
        def is_emergency_active(self, request=None) -> bool:
            return False

        async def dispatch_drive(self, command, request=None) -> DriveOutcome:
            commands.append(command)
            if command.left or command.right:
                navigation_state.heading = 90.0
            return DriveOutcome(
                status=CommandStatus.ACCEPTED,
                audit_id=f"audit-{len(commands)}",
                status_reason=None,
                active_interlocks=[],
                watchdog_latency_ms=1.0,
            )

    runtime = SimpleNamespace(command_gateway=_Gateway())
    response = await rest.control_preset_turn(
        {"session_id": "session", "target_degrees": 90, "speed": 0.4},
        SimpleNamespace(),
        runtime,
    )

    assert response["ok"] is True
    assert response["source"] == "hardware"
    assert response["method"] == "imu"
    assert len(commands) == 2
    assert commands[0].source == "manual"
    assert (commands[0].left, commands[0].right) == pytest.approx((-0.4, 0.4))
    assert (commands[-1].left, commands[-1].right) == (0.0, 0.0)


@pytest.mark.asyncio
async def test_preset_turn_fails_closed_without_heading(monkeypatch) -> None:
    monkeypatch.setenv("SIM_MODE", "0")
    monkeypatch.setattr(rest, "_resolve_manual_session", lambda _session_id: {"operator": True})
    monkeypatch.setattr(
        NavigationService,
        "get_instance",
        classmethod(
            lambda cls: SimpleNamespace(navigation_state=SimpleNamespace(heading=None))
        ),
    )
    gateway = SimpleNamespace(is_emergency_active=lambda request=None: False)

    response = await rest.control_preset_turn(
        {"session_id": "session", "target_degrees": 90},
        SimpleNamespace(),
        SimpleNamespace(command_gateway=gateway),
    )

    assert response.status_code == 409


def test_unsafe_diagnostic_motion_routes_are_not_exposed() -> None:
    from backend.src.main import app

    paths = app.openapi()["paths"]
    assert "/api/v2/control/diagnose/stiffness" not in paths
    assert "/api/v2/control/diagnose/heading-validation" not in paths
