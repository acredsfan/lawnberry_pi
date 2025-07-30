"""
Power Router
Power management and battery status endpoints.
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, Request
from datetime import datetime

from ..models import PowerStatus, BatteryStatus, SolarStatus
from ..auth import get_current_user, require_permission
from ..exceptions import ServiceUnavailableError, NotFoundError
from ..mqtt_bridge import MQTTBridge

router = APIRouter()

@router.get("/status", response_model=PowerStatus)
async def get_power_status(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get complete power system status"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get battery data
    battery_data = mqtt_bridge.get_cached_data("power/battery")
    solar_data = mqtt_bridge.get_cached_data("power/solar")
    
    if not battery_data:
        raise NotFoundError("battery_data", "No battery data available")
    
    battery = BatteryStatus(
        voltage=battery_data.get("voltage", 12.0),
        current=battery_data.get("current", 0.0),
        power=battery_data.get("power", 0.0),
        state_of_charge=battery_data.get("state_of_charge", 0.5),
        temperature=battery_data.get("temperature"),
        health=battery_data.get("health", 1.0),
        cycles=battery_data.get("cycles", 0),
        time_remaining=battery_data.get("time_remaining"),
        timestamp=datetime.fromisoformat(battery_data.get("timestamp", datetime.utcnow().isoformat()))
    )
    
    solar = None
    if solar_data:
        solar = SolarStatus(
            voltage=solar_data.get("voltage", 0.0),
            current=solar_data.get("current", 0.0),
            power=solar_data.get("power", 0.0),
            daily_energy=solar_data.get("daily_energy", 0.0),
            efficiency=solar_data.get("efficiency", 0.0),
            timestamp=datetime.fromisoformat(solar_data.get("timestamp", datetime.utcnow().isoformat()))
        )
    
    return PowerStatus(
        battery=battery,
        solar=solar,
        charging_mode=battery_data.get("charging_mode", "auto"),
        power_saving_enabled=battery_data.get("power_saving_enabled", False)
    )

@router.get("/battery", response_model=BatteryStatus)
async def get_battery_status(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get battery status"""
    power_status = await get_power_status(request, current_user)
    return power_status.battery

@router.get("/solar", response_model=SolarStatus)
async def get_solar_status(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get solar charging status"""
    power_status = await get_power_status(request, current_user)
    if not power_status.solar:
        raise NotFoundError("solar_data", "No solar data available")
    return power_status.solar

@router.post("/charging-mode")
async def set_charging_mode(
    mode: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Set charging mode (auto/manual/eco)"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    if mode not in ["auto", "manual", "eco"]:
        raise ValueError("Invalid charging mode. Must be: auto, manual, or eco")
    
    success = await mqtt_bridge.publish_message(
        "power/charging_mode/set",
        {
            "mode": mode,
            "set_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("power", "Failed to set charging mode")
    
    return {
        "success": True,
        "message": f"Charging mode set to: {mode}",
        "mode": mode
    }

@router.post("/power-saving")
async def toggle_power_saving(
    enabled: bool,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Enable/disable power saving mode"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    success = await mqtt_bridge.publish_message(
        "power/power_saving/set",
        {
            "enabled": enabled,
            "set_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("power", "Failed to set power saving mode")
    
    return {
        "success": True,
        "message": f"Power saving {'enabled' if enabled else 'disabled'}",
        "enabled": enabled
    }

@router.get("/consumption")
async def get_power_consumption(
    request: Request,
    hours: int = 24,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get power consumption history"""
    # This would typically query historical data
    return {
        "period_hours": hours,
        "total_consumption": 0.0,
        "average_power": 0.0,
        "peak_power": 0.0,
        "data_points": [],
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/charging-locations")
async def get_charging_locations(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get learned optimal charging locations"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    locations_data = mqtt_bridge.get_cached_data("power/charging_locations")
    
    return locations_data or {
        "locations": [],
        "current_best": None,
        "learning_progress": 0.0
    }
