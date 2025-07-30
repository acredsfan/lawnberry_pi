"""
Navigation Router
Navigation control and path planning endpoints.
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Request
from datetime import datetime

from ..models import NavigationStatus, NavigationCommand, Position, MowingPattern, SuccessResponse
from ..auth import get_current_user, require_permission
from ..exceptions import ServiceUnavailableError
from ..mqtt_bridge import MQTTBridge

router = APIRouter()

@router.get("/status", response_model=NavigationStatus)
async def get_navigation_status(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get current navigation status"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get navigation data from cache
    nav_data = mqtt_bridge.get_cached_data("navigation/position")
    
    if not nav_data:
        # Return default status
        return NavigationStatus(
            position=Position(latitude=0.0, longitude=0.0),
            heading=0.0,
            speed=0.0,
            timestamp=datetime.utcnow()
        )
    
    position_data = nav_data.get("position", {})
    return NavigationStatus(
        position=Position(
            latitude=position_data.get("latitude", 0.0),
            longitude=position_data.get("longitude", 0.0),
            altitude=position_data.get("altitude"),
            accuracy=position_data.get("accuracy")
        ),
        heading=nav_data.get("heading", 0.0),
        speed=nav_data.get("speed", 0.0),
        target_position=None,  # Would parse from nav_data
        distance_to_target=nav_data.get("distance_to_target"),
        path_progress=nav_data.get("path_progress", 0.0),
        timestamp=datetime.fromisoformat(nav_data.get("timestamp", datetime.utcnow().isoformat()))
    )

@router.post("/start", response_model=SuccessResponse)
async def start_navigation(
    command: NavigationCommand,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Start navigation/mowing operation"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Send navigation command
    success = await mqtt_bridge.publish_message(
        "navigation/command",
        {
            "action": command.action,
            "target_position": command.target_position.dict() if command.target_position else None,
            "pattern": command.pattern.value if command.pattern else None,
            "speed": command.speed,
            "requested_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("navigation", "Failed to send navigation command")
    
    return SuccessResponse(message=f"Navigation command sent: {command.action}")

@router.post("/stop", response_model=SuccessResponse)
async def stop_navigation(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Stop navigation/mowing operation"""
    return await start_navigation(
        NavigationCommand(action="stop"), 
        request, 
        current_user
    )

@router.get("/path")
async def get_current_path(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get current navigation path"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    path_data = mqtt_bridge.get_cached_data("navigation/path")
    return path_data or {"path_points": [], "total_distance": 0, "estimated_time": 0}

@router.post("/goto")
async def goto_position(
    position: Position,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Navigate to specific position"""
    return await start_navigation(
        NavigationCommand(action="start", target_position=position),
        request,
        current_user
    )
