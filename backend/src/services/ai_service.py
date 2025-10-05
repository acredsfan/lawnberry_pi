"""
AIService for LawnBerry Pi v2
AI inference management with hardware acceleration support
"""

import logging
from typing import Dict, Any, Optional
from ..models import AIProcessing, AIAccelerator, AcceleratorStatus

logger = logging.getLogger(__name__)


class AIService:
    """AI processing service"""
    
    def __init__(self):
        self.ai_processing = AIProcessing()
        self.initialized = False
    
    async def initialize(self) -> bool:
        """Initialize AI service"""
        logger.info("Initializing AI service")
        # Detect Coral USB presence (best-effort, non-fatal)
        try:
            coral_present = False
            # Quick heuristic: check common device nodes
            possible = [
                "/dev/apex_0",
                "/dev/usb-accelerator",
            ]
            import os
            for p in possible:
                if os.path.exists(p):
                    coral_present = True
                    break
            # Populate accelerator status map
            self.ai_processing.accelerator_status[AIAccelerator.CPU] = AcceleratorStatus(
                accelerator_type=AIAccelerator.CPU, is_available=True
            )
            self.ai_processing.accelerator_status[AIAccelerator.CORAL_USB] = AcceleratorStatus(
                accelerator_type=AIAccelerator.CORAL_USB,
                is_available=coral_present,
                device_path=possible[0] if coral_present else None,
            )
            # Select best accelerator
            self.ai_processing.primary_accelerator = self.ai_processing.get_best_accelerator()
        except Exception:
            # Default to CPU
            self.ai_processing.primary_accelerator = AIAccelerator.CPU
        self.initialized = True
        return True
    
    async def get_ai_status(self) -> Dict[str, Any]:
        """Get current AI processing status"""
        return {
            "system_enabled": self.ai_processing.system_enabled,
            "primary_accelerator": self.ai_processing.primary_accelerator,
            "processing_fps": self.ai_processing.processing_fps,
            "accelerators": {k: v.model_dump() for k, v in self.ai_processing.accelerator_status.items()},
        }