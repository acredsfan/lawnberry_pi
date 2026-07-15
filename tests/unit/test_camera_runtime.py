"""Camera runtime ownership synchronization contracts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.src.services import camera_runtime


@pytest.mark.asyncio
async def test_external_ai_owner_sync_copies_one_fresh_status(monkeypatch):
    owner = SimpleNamespace(
        get_camera_status=AsyncMock(return_value={"ai_runtime_ready": True}),
        sim_mode=False,
        hardware_available=True,
        ai_runtime_ready=True,
        ai_model_sha256="a" * 64,
        ai_runtime_error=None,
    )
    service = SimpleNamespace(set_external_owner_state=Mock())
    monkeypatch.setattr(camera_runtime, "camera_service", owner)

    assert await camera_runtime.sync_external_ai_owner_state(service) is True

    owner.get_camera_status.assert_awaited_once_with()
    service.set_external_owner_state.assert_called_once_with(
        sim_mode=False,
        hardware_available=True,
        ai_runtime_ready=True,
        model_sha256="a" * 64,
        error=None,
    )


@pytest.mark.asyncio
async def test_external_ai_owner_sync_fails_closed_when_ipc_is_unavailable(monkeypatch):
    owner = SimpleNamespace(
        get_camera_status=AsyncMock(side_effect=TimeoutError("owner unavailable")),
    )
    service = SimpleNamespace(set_external_owner_state=Mock())
    monkeypatch.setattr(camera_runtime, "camera_service", owner)

    assert await camera_runtime.sync_external_ai_owner_state(service) is False
    service.set_external_owner_state.assert_called_once_with(
        sim_mode=True,
        hardware_available=False,
        ai_runtime_ready=False,
        model_sha256=None,
        error="Camera owner IPC unavailable",
    )
