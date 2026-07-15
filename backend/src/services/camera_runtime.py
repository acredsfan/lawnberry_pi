"""Select the camera interface without creating competing live device owners."""

from __future__ import annotations

import inspect
import os
from typing import Any

if os.getenv("SIM_MODE", "0") == "1":
    # Offline development/CI may embed the simulated owner in-process.
    from .camera_stream_service import camera_service
else:
    # Raspberry Pi hardware mode always consumes the standalone owner over IPC.
    from .camera_client import camera_client as camera_service


async def sync_external_ai_owner_state(ai_service: Any) -> bool:
    """Refresh hardware camera-owner truth into the API-side AI service.

    SIM/CI embeds the owner and therefore has no IPC status getter. Hardware
    mode must refresh synchronously when an API caller asks for readiness so a
    stale background-poll snapshot cannot contradict the camera endpoint.
    """
    status_getter = getattr(camera_service, "get_camera_status", None)
    state_setter = getattr(ai_service, "set_external_owner_state", None)
    if not callable(status_getter) or not callable(state_setter):
        return False
    try:
        outcome = status_getter()
        if inspect.isawaitable(outcome):
            await outcome
    except Exception:
        state_setter(
            sim_mode=True,
            hardware_available=False,
            ai_runtime_ready=False,
            model_sha256=None,
            error="Camera owner IPC unavailable",
        )
        return False

    state_setter(
        sim_mode=bool(getattr(camera_service, "sim_mode", True)),
        hardware_available=bool(getattr(camera_service, "hardware_available", False)),
        ai_runtime_ready=bool(getattr(camera_service, "ai_runtime_ready", False)),
        model_sha256=getattr(camera_service, "ai_model_sha256", None),
        error=getattr(camera_service, "ai_runtime_error", None),
    )
    return True


__all__ = ["camera_service", "sync_external_ai_owner_state"]
