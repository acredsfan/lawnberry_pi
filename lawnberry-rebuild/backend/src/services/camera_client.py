"""
CameraClient for LawnBerry Pi v2
IPC client to camera-stream.service
"""

import logging
from typing import Dict, Any, Optional
from ..models import CameraStream

logger = logging.getLogger(__name__)


class CameraClient:
    """Camera service client"""
    
    def __init__(self):
        self.camera_stream = CameraStream()
        self.initialized = False
    
    async def initialize(self) -> bool:
        """Initialize camera client"""
        logger.info("Initializing camera client")
        self.initialized = True
        return True
    
    async def get_camera_status(self) -> Dict[str, Any]:
        """Get current camera status"""
        return {
            "mode": self.camera_stream.mode,
            "is_active": self.camera_stream.is_active,
            "client_count": self.camera_stream.client_count
        }