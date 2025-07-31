"""
Configuration module for ML acceleration settings
"""

import os
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class AccelerationConfig:
    """Configuration for ML acceleration modes"""
    
    enable_coral_tpu: bool = True
    enable_cpu_fallback: bool = True
    force_cpu_mode: bool = False
    prefer_coral_when_available: bool = True
    cpu_threads: int = 4
    log_inference_times: bool = True
    
    @classmethod
    def from_environment(cls):
        """Create configuration from environment variables"""
        return cls(
            enable_coral_tpu=os.getenv('LAWNBERRY_ENABLE_CORAL', 'true').lower() == 'true',
            enable_cpu_fallback=os.getenv('LAWNBERRY_ENABLE_CPU_FALLBACK', 'true').lower() == 'true',
            force_cpu_mode=os.getenv('LAWNBERRY_FORCE_CPU_MODE', 'false').lower() == 'true',
            prefer_coral_when_available=os.getenv('LAWNBERRY_PREFER_CORAL', 'true').lower() == 'true',
            cpu_threads=int(os.getenv('LAWNBERRY_CPU_THREADS', '4')),
            log_inference_times=os.getenv('LAWNBERRY_LOG_INFERENCE_TIMES', 'true').lower() == 'true'
        )
    
    def get_runtime_status(self) -> Dict[str, Any]:
        """Get current configuration status"""
        return {
            "coral_enabled": self.enable_coral_tpu and not self.force_cpu_mode,
            "cpu_fallback_enabled": self.enable_cpu_fallback,
            "forced_cpu_mode": self.force_cpu_mode,
            "cpu_threads": self.cpu_threads
        }

# Global configuration instance
_config: Optional[AccelerationConfig] = None

def get_acceleration_config() -> AccelerationConfig:
    """Get global acceleration configuration"""
    global _config
    if _config is None:
        _config = AccelerationConfig.from_environment()
        logger.info(f"Acceleration config initialized: {_config.get_runtime_status()}")
    return _config
