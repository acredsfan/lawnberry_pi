"""
Dependencies for FastAPI dependency injection
Provides shared services and managers across routers.
"""

from typing import Optional
from fastapi import Request, HTTPException
import logging

logger = logging.getLogger(__name__)


async def get_system_manager(request: Request):
    """Get the system manager from application state"""
    try:
        # For now, return a mock system manager or None
        # In a full implementation, this would be initialized in main.py
        system_manager = getattr(request.app.state, 'system_manager', None)
        
        if system_manager is None:
            # Return a mock object for testing
            class MockSystemManager:
                def __init__(self):
                    self.vision_manager = None
                    self.camera_manager = None
                    self.hardware_interface = None
                
                def get_camera_manager(self):
                    return self.camera_manager
                
                def get_vision_manager(self):
                    return self.vision_manager
            
            system_manager = MockSystemManager()
            logger.warning("Using mock system manager - hardware integration not available")
        
        return system_manager
        
    except Exception as e:
        logger.error(f"Failed to get system manager: {e}")
        raise HTTPException(status_code=503, detail="System manager unavailable")


async def get_mqtt_bridge(request: Request):
    """Get the MQTT bridge from application state"""
    mqtt_bridge = getattr(request.app.state, 'mqtt_bridge', None)
    if not mqtt_bridge:
        raise HTTPException(status_code=503, detail="MQTT bridge unavailable")
    return mqtt_bridge


async def get_redis_client(request: Request):
    """Get the Redis client from application state"""
    return getattr(request.app.state, 'redis_client', None)


async def get_auth_manager(request: Request):
    """Get the auth manager from application state"""
    auth_manager = getattr(request.app.state, 'auth_manager', None)
    if not auth_manager:
        raise HTTPException(status_code=503, detail="Auth manager unavailable")
    return auth_manager
