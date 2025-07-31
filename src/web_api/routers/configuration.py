"""
Configuration Router
System configuration management endpoints.
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, Request
from datetime import datetime

from ..models import SystemConfig, SafetyConfig, SuccessResponse
from ..auth import get_current_user, require_permission
from ..exceptions import ServiceUnavailableError
from ..mqtt_bridge import MQTTBridge

router = APIRouter()

@router.get("/system", response_model=SystemConfig)
async def get_system_config(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get system configuration"""
    return SystemConfig()

@router.put("/system", response_model=SuccessResponse)
async def update_system_config(
    config: SystemConfig,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Update system configuration"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    success = await mqtt_bridge.publish_message(
        "config/system/update",
        {
            "config": config.dict(),
            "updated_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("config", "Failed to update system configuration")
    
    return SuccessResponse(message="System configuration updated successfully")

@router.get("/safety", response_model=SafetyConfig)
async def get_safety_config(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get safety configuration"""
    return SafetyConfig()

@router.put("/safety", response_model=SuccessResponse)
async def update_safety_config(
    config: SafetyConfig,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Update safety configuration"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    success = await mqtt_bridge.publish_message(
        "config/safety/update",
        {
            "config": config.dict(),
            "updated_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("config", "Failed to update safety configuration")
    
    return SuccessResponse(message="Safety configuration updated successfully")
