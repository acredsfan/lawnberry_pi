from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core.runtime import RuntimeContext, get_runtime
from . import rest as rest_api
from .rest import (
    _client_emergency,  # noqa: E402  # cross-module map; unified under §4 motor gateway
)

router = APIRouter()


class EmergencyClearRequest(BaseModel):
    confirmation: bool = Field(False, description="Operator confirmation required to clear E-stop")
    reason: str | None = Field(default=None, description="Optional reason or operator note")


@router.post("/control/emergency_clear")
async def clear_emergency_stop(
    payload: EmergencyClearRequest,
    runtime: RuntimeContext = Depends(get_runtime),
):
    """Clear emergency stop after explicit operator confirmation.

    Behavior:
    - Requires payload.confirmation == True, otherwise 422
    - If E-stop not active, returns 200 idempotently
    - Clears E-stop latch and keeps blade off
    - Attempts to clear emergency on RoboHAT if connected
    """
    # Enforce explicit confirmation
    if not payload.confirmation:
        raise HTTPException(status_code=422, detail="Confirmation required to clear emergency stop")

    # If already clear, respond idempotently
    if not runtime.safety_state.get("emergency_stop_active", False):
        return {"status": "EMERGENCY_CLEARED", "idempotent": True}

    # Clear local safety state and ensure blade remains off
    runtime.safety_state["emergency_stop_active"] = False
    runtime.safety_state["estop_reason"] = None
    runtime.blade_state["active"] = False
    rest_api._emergency_until = 0.0
    _client_emergency.clear()

    # Inform RoboHAT firmware if available
    try:
        from ..services.robohat_service import get_robohat_service

        robohat = get_robohat_service()
        if robohat and robohat.status.serial_connected:
            await robohat.clear_emergency()
    except Exception:
        # Don't fail the clear operation if hardware isn't present in SIM/CI
        pass

    # Minimal response aligned with integration tests
    return {
        "status": "EMERGENCY_CLEARED",
        "timestamp": datetime.now(UTC).isoformat(),
    }
