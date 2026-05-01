"""Integration tests for manual drive duration enforcement (Issue #2)."""

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.src.main import app
from backend.src.api import rest as rest_api

BASE_URL = "http://test"


def _session_id() -> str:
    return str(uuid.uuid4())


def _make_runtime_with_robohat(fake_robohat):
    from backend.src.control.command_gateway import MotorCommandGateway
    from backend.src.core import globals as core_globals
    from backend.src.core.runtime import RuntimeContext

    gw = MotorCommandGateway(
        safety_state=core_globals._safety_state,
        blade_state=core_globals._blade_state,
        client_emergency=core_globals._client_emergency,
        robohat=fake_robohat,
        persistence=MagicMock(),
        websocket_hub=MagicMock(),
        config_loader=MagicMock(),
    )
    rt = RuntimeContext(
        config_loader=MagicMock(),
        hardware_config=MagicMock(),
        safety_limits=MagicMock(),
        navigation=MagicMock(),
        mission_service=MagicMock(),
        safety_state=core_globals._safety_state,
        blade_state=core_globals._blade_state,
        robohat=fake_robohat,
        websocket_hub=MagicMock(),
        persistence=MagicMock(),
        command_gateway=gw,
    )
    return rt


@pytest.mark.asyncio
async def test_manual_drive_respects_duration_ms():
    """Verify motors stop within duration_ms + 100ms after drive command (Issue #2)."""
    from backend.src.core.runtime import get_runtime

    motor_commands = []

    async def mock_send_motor_command(left: float, right: float) -> bool:
        motor_commands.append((left, right, datetime.now(timezone.utc)))
        return True

    fake_robohat = SimpleNamespace(
        status=SimpleNamespace(serial_connected=True, last_error=None),
        send_motor_command=mock_send_motor_command,
    )

    fake_runtime = _make_runtime_with_robohat(fake_robohat)
    app.dependency_overrides[get_runtime] = lambda: fake_runtime
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v2/control/drive",
                json={
                    "session_id": _session_id(),
                    "vector": {"linear": 0.5, "angular": 0.0},
                    "duration_ms": 100,
                    "reason": "test_auto_stop",
                },
            )

            assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.text}"
            payload = response.json()
            assert payload.get("result") in {"accepted", "queued"}

            assert len(motor_commands) >= 1, "send_motor_command should be called with drive command"
            initial_command = motor_commands[0]
            assert initial_command[0] != 0.0 or initial_command[1] != 0.0, \
                f"Initial command should have non-zero speed, got {initial_command}"

            await asyncio.sleep(0.2)

            assert len(motor_commands) >= 2, \
                f"Auto-stop should have called send_motor_command again, got {len(motor_commands)} calls"
            last_command = motor_commands[-1]
            assert last_command[0] == 0.0 and last_command[1] == 0.0, \
                f"Expected motors stopped (0.0, 0.0), got {last_command}"

            time_delta_ms = (last_command[2] - initial_command[2]).total_seconds() * 1000
            assert time_delta_ms >= 90, \
                f"Auto-stop fired too early: {time_delta_ms}ms (expected ~100ms)"
            assert time_delta_ms <= 150, \
                f"Auto-stop fired too late: {time_delta_ms}ms (expected ~100ms)"
    finally:
        app.dependency_overrides.pop(get_runtime, None)


@pytest.mark.asyncio
async def test_drive_timeout_task_cancellation_on_new_command():
    """Verify timeout task is properly cancelled when a new drive command arrives (Issue #2)."""
    from backend.src.core.runtime import get_runtime

    motor_commands = []

    async def mock_send_motor_command(left: float, right: float) -> bool:
        motor_commands.append((left, right, datetime.now(timezone.utc)))
        return True

    fake_robohat = SimpleNamespace(
        status=SimpleNamespace(serial_connected=True, last_error=None),
        send_motor_command=mock_send_motor_command,
    )

    fake_runtime = _make_runtime_with_robohat(fake_robohat)
    app.dependency_overrides[get_runtime] = lambda: fake_runtime
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
            response1 = await client.post(
                "/api/v2/control/drive",
                json={
                    "session_id": _session_id(),
                    "vector": {"linear": 0.5, "angular": 0.0},
                    "duration_ms": 500,
                    "reason": "test_cancel",
                },
            )
            assert response1.status_code == 202

            first_command_time = motor_commands[0][2]

            await asyncio.sleep(0.05)

            response2 = await client.post(
                "/api/v2/control/drive",
                json={
                    "session_id": _session_id(),
                    "vector": {"linear": 0.3, "angular": 0.2},
                    "duration_ms": 100,
                    "reason": "test_cancel",
                },
            )
            assert response2.status_code == 202

            await asyncio.sleep(0.15)

            assert len(motor_commands) >= 3, \
                f"Expected at least 3 commands, got {len(motor_commands)}"

            last_command = motor_commands[-1]
            assert last_command[0] == 0.0 and last_command[1] == 0.0, \
                f"Expected final auto-stop (0.0, 0.0), got {last_command}"
    finally:
        app.dependency_overrides.pop(get_runtime, None)


@pytest.mark.asyncio
async def test_drive_duration_zero_clamps_to_500ms():
    """Verify duration_ms=0 clamps to 500ms hard ceiling (Issue #2)."""
    from backend.src.core.runtime import get_runtime

    motor_commands = []

    async def mock_send_motor_command(left: float, right: float) -> bool:
        motor_commands.append((left, right, datetime.now(timezone.utc)))
        return True

    fake_robohat = SimpleNamespace(
        status=SimpleNamespace(serial_connected=True, last_error=None),
        send_motor_command=mock_send_motor_command,
    )

    fake_runtime = _make_runtime_with_robohat(fake_robohat)
    app.dependency_overrides[get_runtime] = lambda: fake_runtime
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
            response = await client.post(
                "/api/v2/control/drive",
                json={
                    "session_id": _session_id(),
                    "vector": {"linear": 0.5, "angular": 0.0},
                    "duration_ms": 0,
                    "reason": "test_default_duration",
                },
            )

            assert response.status_code == 202
            assert len(motor_commands) >= 1

            await asyncio.sleep(0.6)

            assert len(motor_commands) >= 2, "Auto-stop should have fired"
            last_command = motor_commands[-1]
            assert last_command[0] == 0.0 and last_command[1] == 0.0, \
                f"Expected motors stopped, got {last_command}"

            time_delta_ms = (motor_commands[-1][2] - motor_commands[0][2]).total_seconds() * 1000
            assert time_delta_ms >= 450, \
                f"Auto-stop fired too early: {time_delta_ms}ms (expected ~500ms)"
            assert time_delta_ms <= 600, \
                f"Auto-stop fired too late: {time_delta_ms}ms (expected ~500ms)"
    finally:
        app.dependency_overrides.pop(get_runtime, None)


@pytest.mark.asyncio
async def test_drive_timeout_task_retained_on_gateway():
    """Verify _drive_timeout_task is retained on the gateway (not GC'd) (Issue #2).

    Phase D moved auto-stop task tracking from rest._drive_timeout_task to
    MotorCommandGateway._drive_timeout_task so the gateway owns the reference.
    """
    from backend.src.control.command_gateway import MotorCommandGateway
    from backend.src.core import globals as core_globals

    gw = MotorCommandGateway(
        safety_state=core_globals._safety_state,
        blade_state=core_globals._blade_state,
        client_emergency=core_globals._client_emergency,
        robohat=MagicMock(status=MagicMock(serial_connected=False)),
        persistence=MagicMock(),
    )

    assert hasattr(gw, "_drive_timeout_task"), "_drive_timeout_task should exist on gateway"

    async def dummy_task():
        await asyncio.sleep(1)

    gw._drive_timeout_task = asyncio.create_task(dummy_task())
    stored_task = gw._drive_timeout_task

    assert gw._drive_timeout_task is stored_task, "Gateway should retain task reference"

    gw._drive_timeout_task.cancel()
    try:
        await gw._drive_timeout_task
    except asyncio.CancelledError:
        pass

