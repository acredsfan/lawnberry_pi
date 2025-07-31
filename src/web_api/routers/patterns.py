"""
Patterns Router
Mowing pattern management and scheduling endpoints.
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Request, HTTPException
from datetime import datetime

from ..models import MowingSchedule, PatternConfig, MowingPattern, SuccessResponse
from ..auth import get_current_user, require_permission
from ..exceptions import ServiceUnavailableError, NotFoundError
from ..mqtt_bridge import MQTTBridge
from ...navigation.pattern_service import pattern_service

router = APIRouter()

@router.get("/", response_model=List[PatternConfig])
async def get_available_patterns(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get available mowing patterns with proper configurations"""
    try:
        return await pattern_service.get_available_patterns()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get patterns: {str(e)}")

@router.get("/{pattern_name}", response_model=PatternConfig)
async def get_pattern_config(
    pattern_name: MowingPattern,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get configuration for specific pattern"""
    try:
        return await pattern_service.get_pattern_config(pattern_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get pattern config: {str(e)}")

@router.post("/{pattern_name}", response_model=SuccessResponse)
async def update_pattern_config(
    pattern_name: MowingPattern,
    config: PatternConfig,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Update pattern configuration"""
    try:
        # Update configuration using pattern service
        success = await pattern_service.update_pattern_config(pattern_name, config)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to update pattern configuration")
        
        # Also publish to MQTT if available
        mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
        if mqtt_bridge and mqtt_bridge.is_connected():
            await mqtt_bridge.publish_message(
                "patterns/config/update",
                {
                    "pattern": pattern_name.value,
                    "config": config.dict(),
                    "updated_by": current_user.get("username", "unknown"),
                    "timestamp": datetime.utcnow().isoformat()
                },
                qos=2
            )
        
        return SuccessResponse(message=f"Pattern configuration updated: {pattern_name.value}")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update pattern: {str(e)}")

@router.post("/{pattern_name}/generate")
async def generate_pattern_path(
    pattern_name: MowingPattern,
    boundary_data: Dict[str, Any],
    parameters: Optional[Dict[str, Any]] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Generate mowing path for specified pattern and boundary"""
    try:
        boundary_coords = boundary_data.get('coordinates', [])
        if not boundary_coords:
            raise HTTPException(status_code=400, detail="Boundary coordinates required")
        
        paths = await pattern_service.generate_pattern_path(
            pattern_name, boundary_coords, parameters
        )
        
        return {
            "pattern": pattern_name.value,
            "paths": paths,
            "path_count": len(paths),
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate pattern: {str(e)}")

@router.post("/{pattern_name}/validate")
async def validate_pattern(
    pattern_name: MowingPattern,
    boundary_data: Dict[str, Any],
    parameters: Optional[Dict[str, Any]] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Validate pattern feasibility for given boundary and parameters"""
    try:
        boundary_coords = boundary_data.get('coordinates', [])
        if not boundary_coords:
            raise HTTPException(status_code=400, detail="Boundary coordinates required")
        
        validation_result = await pattern_service.validate_pattern_feasibility(
            pattern_name, boundary_coords, parameters
        )
        
        return validation_result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate pattern: {str(e)}")

@router.post("/{pattern_name}/efficiency")
async def estimate_pattern_efficiency(
    pattern_name: MowingPattern,
    boundary_data: Dict[str, Any],
    parameters: Optional[Dict[str, Any]] = None,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Estimate pattern efficiency metrics for battery optimization"""
    try:
        boundary_coords = boundary_data.get('coordinates', [])
        if not boundary_coords:
            raise HTTPException(status_code=400, detail="Boundary coordinates required")
        
        efficiency_metrics = await pattern_service.estimate_pattern_efficiency(
            pattern_name, boundary_coords, parameters
        )
        
        return efficiency_metrics
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to estimate efficiency: {str(e)}")

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
