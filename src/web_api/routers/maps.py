"""
Maps Router
Map data management endpoints for boundaries, no-go zones, and coverage tracking.
"""

from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Request
from datetime import datetime

from ..models import MapData, Boundary, NoGoZone, Position, SuccessResponse
from ..auth import get_current_user, require_permission
from ..exceptions import ServiceUnavailableError, NotFoundError
from ..mqtt_bridge import MQTTBridge

router = APIRouter()

@router.get("/", response_model=MapData)
async def get_map_data(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get complete map data"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get map data from cache
    boundaries_data = mqtt_bridge.get_cached_data("maps/boundaries")
    coverage_data = mqtt_bridge.get_cached_data("maps/coverage")
    
    return MapData(
        boundaries=[],  # Would parse from boundaries_data
        no_go_zones=[],
        home_position=None,
        charging_spots=[],
        coverage_map=coverage_data
    )

@router.get("/boundaries", response_model=List[Boundary])
async def get_boundaries(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get yard boundaries"""
    return []

@router.post("/boundaries", response_model=SuccessResponse)
async def create_boundary(
    boundary: Boundary,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Create new boundary"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    success = await mqtt_bridge.publish_message(
        "maps/boundaries/create",
        {
            "boundary": boundary.dict(),
            "created_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("maps", "Failed to create boundary")
    
    return SuccessResponse(message="Boundary created successfully")

@router.get("/no-go-zones", response_model=List[NoGoZone])
async def get_no_go_zones(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get no-go zones"""
    return []

@router.post("/no-go-zones", response_model=SuccessResponse)
async def create_no_go_zone(
    zone: NoGoZone,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Create new no-go zone"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    success = await mqtt_bridge.publish_message(
        "maps/no_go_zones/create",
        {
            "zone": zone.dict(),
            "created_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("maps", "Failed to create no-go zone")
    
    return SuccessResponse(message="No-go zone created successfully")

@router.get("/home-position", response_model=Position)
async def get_home_position(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get home/charging position"""
    return Position(latitude=0.0, longitude=0.0)

@router.post("/home-position", response_model=SuccessResponse)
async def set_home_position(
    position: Position,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Set home/charging position"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    success = await mqtt_bridge.publish_message(
        "maps/home_position/set",
        {
            "position": position.dict(),
            "set_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("maps", "Failed to set home position")
    
    return SuccessResponse(message="Home position set successfully")
