"""
RC Control Router
Remote control system management and monitoring endpoints.
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from datetime import datetime

from ..auth import get_current_user, require_permission
from ..exceptions import ServiceUnavailableError, ValidationError
from ..mqtt_bridge import MQTTBridge

router = APIRouter()

class RCModeRequest(BaseModel):
    mode: str

class RCChannelConfig(BaseModel):
    channel: int
    function: str
    min_value: int = 1000
    max_value: int = 2000
    center_value: int = 1500

class RCStatus(BaseModel):
    rc_enabled: bool
    rc_mode: str
    signal_lost: bool
    blade_enabled: bool
    channels: Dict[int, int]
    encoder_position: int
    timestamp: datetime

class BladeControlRequest(BaseModel):
    enabled: bool

class RCDriveRequest(BaseModel):
    steer: int  # 1000-2000 µs
    throttle: int  # 1000-2000 µs

@router.get("/status", response_model=RCStatus)
async def get_rc_status(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get comprehensive RC control status"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get RC status from hardware interface
    try:
        # Request status from hardware
        await mqtt_bridge.publish_message(
            "hardware/rc/get_status",
            {"requested_by": current_user.get("username", "unknown")},
            qos=1
        )
        
        # Get cached RC data
        rc_data = mqtt_bridge.get_cached_data("hardware/rc/status")
        
        if not rc_data:
            # Return default status
            return RCStatus(
                rc_enabled=True,
                rc_mode="emergency",
                signal_lost=False,
                blade_enabled=False,
                channels={},
                encoder_position=0,
                timestamp=datetime.utcnow()
            )
        
        return RCStatus(
            rc_enabled=rc_data.get("rc_enabled", True),
            rc_mode=rc_data.get("rc_mode", "emergency"),
            signal_lost=rc_data.get("signal_lost", False),
            blade_enabled=rc_data.get("blade_enabled", False),
            channels=rc_data.get("channels", {}),
            encoder_position=rc_data.get("encoder", 0),
            timestamp=datetime.fromisoformat(rc_data.get("timestamp", datetime.utcnow().isoformat()))
        )
        
    except Exception as e:
        raise ServiceUnavailableError("rc_control", f"Failed to get RC status: {str(e)}")

@router.post("/mode")
async def set_rc_mode(
    mode_request: RCModeRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Set RC control mode"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    valid_modes = ["emergency", "manual", "assisted", "training"]
    if mode_request.mode not in valid_modes:
        raise ValidationError(f"Invalid RC mode. Must be one of: {', '.join(valid_modes)}")
    
    try:
        success = await mqtt_bridge.publish_message(
            "hardware/rc/set_mode",
            {
                "mode": mode_request.mode,
                "requested_by": current_user.get("username", "unknown"),
                "timestamp": datetime.utcnow().isoformat()
            },
            qos=2
        )
        
        if not success:
            raise ServiceUnavailableError("rc_control", "Failed to send RC mode command")
        
        return {"message": f"RC mode set to {mode_request.mode}", "success": True}
        
    except Exception as e:
        raise ServiceUnavailableError("rc_control", f"Failed to set RC mode: {str(e)}")

@router.post("/enable")
async def enable_rc_control(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Enable RC control"""
    return await _set_rc_control_state(request, current_user, True)

@router.post("/disable")
async def disable_rc_control(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Disable RC control (switch to autonomous mode)"""
    return await _set_rc_control_state(request, current_user, False)

async def _set_rc_control_state(
    request: Request,
    current_user: Dict[str, Any],
    enabled: bool
):
    """Helper function to enable/disable RC control"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    try:
        success = await mqtt_bridge.publish_message(
            "hardware/rc/control",
            {
                "enabled": enabled,
                "requested_by": current_user.get("username", "unknown"),
                "timestamp": datetime.utcnow().isoformat()
            },
            qos=2
        )
        
        if not success:
            raise ServiceUnavailableError("rc_control", "Failed to send RC control command")
        
        state = "enabled" if enabled else "disabled"
        return {"message": f"RC control {state}", "success": True}
        
    except Exception as e:
        raise ServiceUnavailableError("rc_control", f"Failed to set RC control state: {str(e)}")

@router.post("/blade")
async def control_blade(
    blade_request: BladeControlRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Control blade motor"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    try:
        success = await mqtt_bridge.publish_message(
            "hardware/rc/blade",
            {
                "enabled": blade_request.enabled,
                "requested_by": current_user.get("username", "unknown"),
                "timestamp": datetime.utcnow().isoformat()
            },
            qos=2
        )
        
        if not success:
            raise ServiceUnavailableError("rc_control", "Failed to send blade control command")
        
        state = "enabled" if blade_request.enabled else "disabled"
        return {"message": f"Blade {state}", "success": True}
        
    except Exception as e:
        raise ServiceUnavailableError("rc_control", f"Failed to control blade: {str(e)}")

@router.post("/pwm")
async def send_pwm(
    drive: RCDriveRequest,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Send direct PWM command (steer/throttle) to RoboHAT via MQTT."""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")

    steer = max(1000, min(2000, int(drive.steer)))
    throttle = max(1000, min(2000, int(drive.throttle)))
    try:
        success = await mqtt_bridge.publish_message(
            "hardware/rc/pwm",
            {
                "steer": steer,
                "throttle": throttle,
                "requested_by": current_user.get("username", "unknown"),
                "timestamp": datetime.utcnow().isoformat()
            },
            qos=1
        )
        if not success:
            raise ServiceUnavailableError("rc_control", "Failed to send PWM command")
        return {"success": True, "message": "PWM command sent", "steer": steer, "throttle": throttle}
    except Exception as e:
        raise ServiceUnavailableError("rc_control", f"Failed to send PWM: {str(e)}")

@router.post("/channel/configure")
async def configure_rc_channel(
    channel_config: RCChannelConfig,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("admin"))
):
    """Configure RC channel function mapping"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    if not (1 <= channel_config.channel <= 6):
        raise ValidationError("Channel must be between 1 and 6")
    
    valid_functions = ["steer", "throttle", "blade", "speed_adj", "emergency", "mode_switch"]
    if channel_config.function not in valid_functions:
        raise ValidationError(f"Invalid function. Must be one of: {', '.join(valid_functions)}")
    
    try:
        success = await mqtt_bridge.publish_message(
            "hardware/rc/configure_channel",
            {
                "channel": channel_config.channel,
                "function": channel_config.function,
                "min_value": channel_config.min_value,
                "max_value": channel_config.max_value,
                "center_value": channel_config.center_value,
                "requested_by": current_user.get("username", "unknown"),
                "timestamp": datetime.utcnow().isoformat()
            },
            qos=2
        )
        
        if not success:
            raise ServiceUnavailableError("rc_control", "Failed to send channel configuration")
        
        return {
            "message": f"Channel {channel_config.channel} configured for {channel_config.function}",
            "success": True
        }
        
    except Exception as e:
        raise ServiceUnavailableError("rc_control", f"Failed to configure channel: {str(e)}")

@router.get("/channels")
async def get_channel_config(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get current RC channel configuration"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get channel configuration from cache
    channel_data = mqtt_bridge.get_cached_data("hardware/rc/channels")
    
    if not channel_data:
        # Return default configuration
        return {
            1: {"function": "steer", "min": 1000, "max": 2000, "center": 1500},
            2: {"function": "throttle", "min": 1000, "max": 2000, "center": 1500},
            3: {"function": "blade", "min": 1000, "max": 2000, "center": 1500},
            4: {"function": "speed_adj", "min": 1000, "max": 2000, "center": 1500},
            5: {"function": "emergency", "min": 1000, "max": 2000, "center": 1500},
            6: {"function": "mode_switch", "min": 1000, "max": 2000, "center": 1500},
        }
    
    return channel_data

@router.post("/emergency_stop")
async def emergency_stop(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Trigger emergency stop via RC system"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    try:
        success = await mqtt_bridge.publish_message(
            "safety/emergency_stop",
            {
                "source": "rc_control",
                "requested_by": current_user.get("username", "unknown"),
                "timestamp": datetime.utcnow().isoformat()
            },
            qos=2
        )
        
        if not success:
            raise ServiceUnavailableError("safety", "Failed to send emergency stop command")
        
        return {"message": "Emergency stop triggered", "success": True}
        
    except Exception as e:
        raise ServiceUnavailableError("safety", f"Failed to trigger emergency stop: {str(e)}")

# Compatibility route: some UIs may PUT /channels/{id}
@router.put("/channels/{channel}")
async def update_channel_compat(
    channel: int,
    channel_config: Dict[str, Any],
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("admin"))
):
    """Compatibility endpoint mapping to /channel/configure."""
    cfg = RCChannelConfig(
        channel=channel,
        function=str(channel_config.get("function", "steer")),
        min_value=int(channel_config.get("min_value", channel_config.get("min", 1000))),
        max_value=int(channel_config.get("max_value", channel_config.get("max", 2000))),
        center_value=int(channel_config.get("center_value", channel_config.get("center", 1500)))
    )
    # Delegate to main handler
    return await configure_rc_channel(cfg, request, current_user)
