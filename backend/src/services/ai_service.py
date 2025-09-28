"""
AIService for LawnBerry Pi v2
AI inference management with hardware acceleration support
"""

import logging
from typing import Dict, Any, Optional
from ..models import AIProcessing

logger = logging.getLogger(__name__)


class AIService:
    """AI processing service"""
    
    def __init__(self):
        self.ai_processing = AIProcessing()
        self.initialized = False
    
    async def initialize(self) -> bool:
        """Initialize AI service"""
        logger.info("Initializing AI service")
        self.initialized = True
        return True
    
    async def get_ai_status(self) -> Dict[str, Any]:
        """Get current AI processing status"""
        return {
            "system_enabled": self.ai_processing.system_enabled,
            "primary_accelerator": self.ai_processing.primary_accelerator,
            "processing_fps": self.ai_processing.processing_fps
        }