"""
Maps Router
Map data management endpoints for boundaries, no-go zones, and coverage tracking.
"""

from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Request
from datetime import datetime
from math import cos, radians

from ..models import MapData, Boundary, NoGoZone, Position, HomeLocation, HomeLocationType, SuccessResponse
from ..auth import get_current_user, require_permission
from ..exceptions import ServiceUnavailableError, NotFoundError
from ..mqtt_bridge import MQTTBridge

router = APIRouter()

@router.get("/", response_model=MapData)
async def get_map_data(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get complete map data with current location"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get map data from cache
    boundaries_data = mqtt_bridge.get_cached_data("maps/boundaries")
    coverage_data = mqtt_bridge.get_cached_data("maps/coverage")
    location_data = mqtt_bridge.get_cached_data("location/current")
    
    # Get current position for map centering
    current_position = None
    if location_data:
        current_position = Position(
            latitude=location_data.get("latitude", 0.0),
            longitude=location_data.get("longitude", 0.0)
        )
    
    return MapData(
        boundaries=[],  # Would parse from boundaries_data
        no_go_zones=[],
        home_position=current_position,
        charging_spots=[],
        coverage_map=coverage_data
    )

@router.get("/boundaries", response_model=List[Boundary])
async def get_boundaries(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get yard boundaries"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get boundaries from cache
    boundaries_data = mqtt_bridge.get_cached_data("maps/boundaries")
    
    if not boundaries_data:
        return []
    
    # Convert stored boundaries to API format
    boundaries = []
    if isinstance(boundaries_data, list):
        for boundary_data in boundaries_data:
            if isinstance(boundary_data, dict) and "points" in boundary_data:
                boundaries.append(Boundary(
                    points=[Position(latitude=p.get("latitude", 0), longitude=p.get("longitude", 0)) 
                           for p in boundary_data.get("points", [])],
                    name=boundary_data.get("name", "Boundary")
                ))
    
    return boundaries

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

@router.delete("/boundaries/{boundary_id}", response_model=SuccessResponse)
async def delete_boundary(
    boundary_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Delete a boundary"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    success = await mqtt_bridge.publish_message(
        "maps/boundaries/delete",
        {
            "boundary_id": boundary_id,
            "deleted_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("maps", "Failed to delete boundary")
    
    return SuccessResponse(message="Boundary deleted successfully")

@router.post("/boundaries/validate", response_model=Dict[str, Any])
async def validate_boundary(
    boundary: Boundary,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Validate boundary polygon"""
    points = boundary.points
    
    # Basic validation
    if len(points) < 3:
        return {
            "isValid": False,
            "error": "Boundary must have at least 3 points",
            "violations": ["insufficient_points"]
        }
    
    if len(points) > 100:
        return {
            "isValid": False,
            "error": "Boundary cannot have more than 100 vertices",
            "violations": ["too_many_vertices"]
        }
    
    # Calculate area using shoelace formula
    area = 0.0
    for i in range(len(points)):
        j = (i + 1) % len(points)
        area += points[i].latitude * points[j].longitude
        area -= points[j].latitude * points[i].longitude
    area = abs(area) / 2.0
    
    # Convert to square meters (rough approximation)
    area_m2 = area * 111320 * 111320 * cos(radians(points[0].latitude))
    
    if area_m2 < 10:
        return {
            "isValid": False,
            "error": "Boundary area must be at least 10 square meters",
            "area": area_m2,
            "violations": ["area_too_small"]
        }
    
    # Check for self-intersection (basic check)
    violations = []
    if _has_self_intersection(points):
        violations.append("self_intersection")
    
    return {
        "isValid": len(violations) == 0,
        "area": area_m2,
        "violations": violations,
        "error": "Boundary has geometric issues" if violations else None
    }

def _has_self_intersection(points: List[Position]) -> bool:
    """Simple self-intersection check using line segment intersection"""
    from math import isclose
    
    def orientation(p, q, r):
        val = (q.longitude - p.longitude) * (r.latitude - q.latitude) - (q.latitude - p.latitude) * (r.longitude - q.longitude)
        if isclose(val, 0, abs_tol=1e-10):
            return 0  # Collinear
        return 1 if val > 0 else 2  # Clockwise or counterclockwise
    
    def segments_intersect(p1, q1, p2, q2):
        o1 = orientation(p1, q1, p2)
        o2 = orientation(p1, q1, q2)
        o3 = orientation(p2, q2, p1)
        o4 = orientation(p2, q2, q1)
        return o1 != o2 and o3 != o4
    
    for i in range(len(points)):
        line1_start = points[i]
        line1_end = points[(i + 1) % len(points)]
        
        for j in range(i + 2, len(points)):
            if j == len(points) - 1 and i == 0:
                continue  # Skip adjacent segments
            
            line2_start = points[j]
            line2_end = points[(j + 1) % len(points)]
            
            if segments_intersect(line1_start, line1_end, line2_start, line2_end):
                return True
    
    return False


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

@router.put("/no-go-zones/{zone_id}", response_model=SuccessResponse)
async def update_no_go_zone(
    zone_id: str,
    zone_updates: Dict[str, Any],
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Update existing no-go zone"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    success = await mqtt_bridge.publish_message(
        "maps/no_go_zones/update",
        {
            "zone_id": zone_id,
            "updates": zone_updates,
            "updated_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("maps", "Failed to update no-go zone")
    
    return SuccessResponse(message="No-go zone updated successfully")

@router.delete("/no-go-zones/{zone_id}", response_model=SuccessResponse)
async def delete_no_go_zone(
    zone_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Delete no-go zone"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    success = await mqtt_bridge.publish_message(
        "maps/no_go_zones/delete",
        {
            "zone_id": zone_id,
            "deleted_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("maps", "Failed to delete no-go zone")
    
    return SuccessResponse(message="No-go zone deleted successfully")

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


# Home Locations Endpoints
@router.get("/home-locations", response_model=List[HomeLocation])
async def get_home_locations(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get all home locations"""
    # TODO: Implement actual data retrieval from backend
    return []


@router.post("/home-locations", response_model=HomeLocation)
async def create_home_location(
    location: HomeLocation,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Create a new home location"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Generate ID if not provided
    if not location.id:
        location.id = f"home_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    
    location.updated_at = datetime.utcnow()
    
    success = await mqtt_bridge.publish_message(
        "maps/home_locations/create",
        {
            "location": location.dict(),
            "created_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("maps", "Failed to create home location")
    
    return location


@router.put("/home-locations/{location_id}", response_model=HomeLocation)
async def update_home_location(
    location_id: str,
    location: HomeLocation,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Update an existing home location"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Ensure ID matches
    location.id = location_id
    location.updated_at = datetime.utcnow()
    
    success = await mqtt_bridge.publish_message(
        "maps/home_locations/update",
        {
            "location": location.dict(),
            "updated_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("maps", "Failed to update home location")
    
    return location


@router.delete("/home-locations/{location_id}", response_model=SuccessResponse)
async def delete_home_location(
    location_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Delete a home location"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    success = await mqtt_bridge.publish_message(
        "maps/home_locations/delete",
        {
            "location_id": location_id,
            "deleted_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("maps", "Failed to delete home location")
    
    return SuccessResponse(message="Home location deleted successfully")


@router.post("/home-locations/{location_id}/set-default", response_model=SuccessResponse)
async def set_default_home_location(
    location_id: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Set a home location as the default"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    success = await mqtt_bridge.publish_message(
        "maps/home_locations/set_default",
        {
            "location_id": location_id,
            "set_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("maps", "Failed to set default home location")
    
    return SuccessResponse(message="Default home location set successfully")


@router.post("/home-locations/validate-boundary", response_model=Dict[str, bool])
async def validate_home_location_boundary(
    position: Position,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Validate if a position is within yard boundaries"""
    # TODO: Implement actual boundary validation logic
    # For now, return a placeholder
    return {"is_within_boundary": True, "requires_clipping": False}
