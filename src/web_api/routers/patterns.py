"""
Patterns Router
Mowing pattern management and scheduling endpoints.
"""

from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Request
from datetime import datetime

from ..models import MowingSchedule, PatternConfig, MowingPattern, SuccessResponse
from ..auth import get_current_user, require_permission
from ..exceptions import ServiceUnavailableError, NotFoundError
from ..mqtt_bridge import MQTTBridge

router = APIRouter()

@router.get("/", response_model=List[PatternConfig])
async def get_available_patterns(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get available mowing patterns"""
    patterns = []
    for pattern in MowingPattern:
        patterns.append(PatternConfig(
            pattern=pattern,
            parameters={},
            coverage_overlap=0.1,
            edge_cutting=True
        ))
    return patterns

@router.get("/{pattern_name}", response_model=PatternConfig)
async def get_pattern_config(
    pattern_name: MowingPattern,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get configuration for specific pattern"""
    return PatternConfig(
        pattern=pattern_name,
        parameters={},
        coverage_overlap=0.1,
        edge_cutting=True
    )

@router.post("/{pattern_name}", response_model=SuccessResponse)
async def update_pattern_config(
    pattern_name: MowingPattern,
    config: PatternConfig,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Update pattern configuration"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    success = await mqtt_bridge.publish_message(
        "patterns/config/update",
        {
            "pattern": pattern_name.value,
            "config": config.dict(),
            "updated_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("patterns", "Failed to update pattern configuration")
    
    return SuccessResponse(message=f"Pattern configuration updated: {pattern_name.value}")

@router.get("/schedule/", response_model=List[MowingSchedule])
async def get_schedules(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get all mowing schedules"""
    # This would typically come from database
    return []

@router.post("/schedule/", response_model=SuccessResponse)
async def create_schedule(
    schedule: MowingSchedule,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Create new mowing schedule"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    success = await mqtt_bridge.publish_message(
        "patterns/schedule/create",
        {
            "schedule": schedule.dict(),
            "created_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("schedule", "Failed to create schedule")
    
    return SuccessResponse(message="Mowing schedule created successfully")
