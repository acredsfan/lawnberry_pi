from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..control.commands import CommandStatus, EmergencyClear
from ..core.runtime import RuntimeContext, get_runtime

router = APIRouter()


class EmergencyClearRequest(BaseModel):
    confirmation: bool = Field(False, description="Operator confirmation required to clear E-stop")
    reason: str | None = Field(default=None, description="Optional reason or operator note")


@router.post("/control/emergency_clear")
async def clear_emergency_stop(
    payload: EmergencyClearRequest,
    runtime: RuntimeContext = Depends(get_runtime),
):
    """Clear emergency stop after explicit operator confirmation."""
    outcome = await runtime.command_gateway.clear_emergency(
        EmergencyClear(confirmed=payload.confirmation)
    )
    if outcome.status == CommandStatus.BLOCKED:
        raise HTTPException(
            status_code=422, detail="Confirmation required to clear emergency stop"
        )
    if outcome.idempotent:
        return {"status": "EMERGENCY_CLEARED", "idempotent": True}
    return {
        "status": "EMERGENCY_CLEARED",
        "timestamp": outcome.timestamp,
    }
