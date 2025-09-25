"""Manual control API endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

from lawnberry.core.websocket_hub import websocket_hub

router = APIRouter(prefix="/api/v1/manual", tags=["manual"])


class ManualCommand(BaseModel):
    """Manual control command request."""
    command_type: str  # drive_forward, drive_reverse, turn_left, turn_right, stop, emergency_stop, blade_on, blade_off
    duration_ms: Optional[int] = None  # For timed commands
    parameters: Optional[Dict[str, Any]] = None


class ManualCommandResponse(BaseModel):
    """Manual control command response."""
    command_id: str
    status: str  # accepted, rejected
    message: str
    timestamp: str


@router.post("/command", response_model=ManualCommandResponse)
async def execute_manual_command(command: ManualCommand) -> ManualCommandResponse:
    """Execute manual control command with authentication gate."""
    # TODO: Add authentication check here
    # if not authenticated:
    #     raise HTTPException(status_code=401, detail="Authentication required for manual control")
    
    # Validate command type
    valid_commands = {
        "drive_forward", "drive_reverse", "turn_left", "turn_right", 
        "stop", "emergency_stop", "blade_on", "blade_off"
    }
    
    if command.command_type not in valid_commands:
        raise HTTPException(status_code=400, detail=f"Invalid command type: {command.command_type}")
    
    # Generate command ID
    command_id = str(uuid.uuid4())
    
    # For now, accept all commands (simulation mode)
    response = ManualCommandResponse(
        command_id=command_id,
        status="accepted",
        message=f"Manual command {command.command_type} accepted",
        timestamp=datetime.utcnow().isoformat()
    )
    
    # Send feedback via WebSocket
    feedback_data = {
        "command_id": command_id,
        "command_type": command.command_type,
        "status": "executing",
        "executed_at": datetime.utcnow().isoformat(),
        "parameters": command.parameters
    }
    
    await websocket_hub.broadcast_to_topic("manual/feedback", feedback_data)
    
    return response


@router.get("/status")
async def get_manual_control_status() -> Dict[str, Any]:
    """Get current manual control status."""
    return {
        "manual_mode_active": False,
        "last_command": None,
        "motor_status": "idle",
        "blade_status": "off",
        "safety_override": False,
        "emergency_stop_active": False,
        "timestamp": datetime.utcnow().isoformat()
    }