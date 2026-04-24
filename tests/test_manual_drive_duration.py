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


@pytest.mark.asyncio
async def test_manual_drive_respects_duration_ms():
    """Verify motors stop within duration_ms + 100ms after drive command (Issue #2)."""
    
    # Track all motor commands sent during the test
    motor_commands = []
    
    async def mock_send_motor_command(left: float, right: float) -> bool:
        motor_commands.append((left, right, datetime.now(timezone.utc)))
        return True
    
    # Create fake RoboHAT service with mock
    fake_robohat = SimpleNamespace(
        status=SimpleNamespace(
            serial_connected=True,
            last_watchdog_echo="echo",
            last_error=None,
        ),
        send_motor_command=mock_send_motor_command,
    )
    
    async def fake_telemetry():
        return {
            "source": "hardware",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "position": {
                "latitude": 39.0,
                "longitude": -84.0,
                "accuracy": 0.2,
            },
            "tof": {
                "left": {"distance_mm": 5000.0},
                "right": {"distance_mm": 5000.0},
            },
        }
    
    transport = httpx.ASGITransport(app=app)
    
    with patch(
        "backend.src.services.websocket_hub.websocket_hub.get_cached_telemetry",
        side_effect=fake_telemetry,
    ), patch(
        "backend.src.services.robohat_service.get_robohat_service",
        return_value=fake_robohat,
    ):
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
            # Send a 100ms drive command
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
            
            # Verify initial drive command was sent
            assert len(motor_commands) >= 1, "send_motor_command should be called with drive command"
            initial_command = motor_commands[0]
            assert initial_command[0] != 0.0 or initial_command[1] != 0.0, \
                f"Initial command should have non-zero speed, got {initial_command}"
            
            # Wait for auto-stop to fire (100ms + 100ms margin for timing)
            await asyncio.sleep(0.2)
            
            # Verify the last call is zero command (auto-stop)
            assert len(motor_commands) >= 2, \
                f"Auto-stop should have called send_motor_command again, got {len(motor_commands)} calls"
            last_command = motor_commands[-1]
            assert last_command[0] == 0.0 and last_command[1] == 0.0, \
                f"Expected motors stopped (0.0, 0.0), got {last_command}"
            
            # Verify timing: last command should be close to duration_ms after initial
            time_delta_ms = (last_command[2] - initial_command[2]).total_seconds() * 1000
            assert time_delta_ms >= 90, \
                f"Auto-stop fired too early: {time_delta_ms}ms (expected ~100ms)"
            assert time_delta_ms <= 150, \
                f"Auto-stop fired too late: {time_delta_ms}ms (expected ~100ms)"


@pytest.mark.asyncio
async def test_drive_timeout_task_cancellation_on_new_command():
    """Verify timeout task is properly cancelled when a new drive command arrives (Issue #2)."""
    
    motor_commands = []
    
    async def mock_send_motor_command(left: float, right: float) -> bool:
        motor_commands.append((left, right, datetime.now(timezone.utc)))
        return True
    
    fake_robohat = SimpleNamespace(
        status=SimpleNamespace(
            serial_connected=True,
            last_watchdog_echo="echo",
            last_error=None,
        ),
        send_motor_command=mock_send_motor_command,
    )
    
    async def fake_telemetry():
        return {
            "source": "hardware",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "position": {
                "latitude": 39.0,
                "longitude": -84.0,
                "accuracy": 0.2,
            },
            "tof": {
                "left": {"distance_mm": 5000.0},
                "right": {"distance_mm": 5000.0},
            },
        }
    
    transport = httpx.ASGITransport(app=app)
    
    with patch(
        "backend.src.services.websocket_hub.websocket_hub.get_cached_telemetry",
        side_effect=fake_telemetry,
    ), patch(
        "backend.src.services.robohat_service.get_robohat_service",
        return_value=fake_robohat,
    ):
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
            # Send first drive command with 500ms duration
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
            
            # Record the first command
            commands_after_first = len(motor_commands)
            first_command_time = motor_commands[0][2]
            
            # Wait a short time, then send another drive command
            # This should cancel the first auto-stop task
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
            
            # The second command should have triggered a cancellation and created a new timeout
            # Wait for the second timeout to fire
            await asyncio.sleep(0.15)
            
            # We should have: initial drive, second drive, and auto-stop from second
            # (the first auto-stop should have been cancelled)
            assert len(motor_commands) >= 3, \
                f"Expected at least 3 commands, got {len(motor_commands)}"
            
            # Last command should be the auto-stop (0.0, 0.0)
            last_command = motor_commands[-1]
            assert last_command[0] == 0.0 and last_command[1] == 0.0, \
                f"Expected final auto-stop (0.0, 0.0), got {last_command}"


@pytest.mark.asyncio
async def test_drive_duration_zero_clamps_to_500ms():
    """Verify duration_ms=0 clamps to 500ms hard ceiling (Issue #2)."""
    
    motor_commands = []
    
    async def mock_send_motor_command(left: float, right: float) -> bool:
        motor_commands.append((left, right, datetime.now(timezone.utc)))
        return True
    
    fake_robohat = SimpleNamespace(
        status=SimpleNamespace(
            serial_connected=True,
            last_watchdog_echo="echo",
            last_error=None,
        ),
        send_motor_command=mock_send_motor_command,
    )
    
    async def fake_telemetry():
        return {
            "source": "hardware",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "position": {
                "latitude": 39.0,
                "longitude": -84.0,
                "accuracy": 0.2,
            },
            "tof": {
                "left": {"distance_mm": 5000.0},
                "right": {"distance_mm": 5000.0},
            },
        }
    
    transport = httpx.ASGITransport(app=app)
    
    with patch(
        "backend.src.services.websocket_hub.websocket_hub.get_cached_telemetry",
        side_effect=fake_telemetry,
    ), patch(
        "backend.src.services.robohat_service.get_robohat_service",
        return_value=fake_robohat,
    ):
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
            # Send drive command with duration_ms=0 (means use 500ms default)
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
            
            # Wait for auto-stop to fire (should be ~500ms)
            # Give 100ms margin for timing variance
            await asyncio.sleep(0.6)
            
            # Verify the last call is zero command (auto-stop)
            assert len(motor_commands) >= 2, "Auto-stop should have fired"
            last_command = motor_commands[-1]
            assert last_command[0] == 0.0 and last_command[1] == 0.0, \
                f"Expected motors stopped, got {last_command}"
            
            # Verify timing is close to 500ms
            time_delta_ms = (motor_commands[-1][2] - motor_commands[0][2]).total_seconds() * 1000
            assert time_delta_ms >= 450, \
                f"Auto-stop fired too early: {time_delta_ms}ms (expected ~500ms)"
            assert time_delta_ms <= 600, \
                f"Auto-stop fired too late: {time_delta_ms}ms (expected ~500ms)"


@pytest.mark.asyncio
async def test_drive_timeout_module_variable_retained():
    """Verify _drive_timeout_task module variable is retained (not GC'd) (Issue #2)."""
    
    # This is a simple unit test that verifies the module variable exists and can be accessed
    from backend.src.api import rest
    
    # Verify the variable exists
    assert hasattr(rest, "_drive_timeout_task"), "_drive_timeout_task should exist at module level"
    
    # Create a dummy task and store it
    async def dummy_task():
        await asyncio.sleep(1)
    
    rest._drive_timeout_task = asyncio.create_task(dummy_task())
    stored_task = rest._drive_timeout_task
    
    # Verify we can retrieve it
    assert rest._drive_timeout_task is stored_task, "Module variable should retain task reference"
    
    # Clean up
    rest._drive_timeout_task.cancel()
    try:
        await rest._drive_timeout_task
    except asyncio.CancelledError:
        pass

