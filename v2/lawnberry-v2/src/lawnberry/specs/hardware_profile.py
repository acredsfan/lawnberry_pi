"""HardwareProfile dataclass describing platform hardware configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass 
class HardwareProfile:
    """Snapshot describing preferred and alternate hardware for the mower platform."""
    
    component: str  # e.g., gps, imu, ai_acceleration
    preferred: Dict[str, Any] = field(default_factory=dict)  # matches spec/hardware.yaml details
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)  # e.g., "Hailo HAT cannot stack with RoboHAT"
    required_buses: List[str] = field(default_factory=list)  # e.g., I2C, UART4, USB
    priority_order: List[str] = field(default_factory=list)  # e.g., AI acceleration ["coral_usb", "hailo_hat", "cpu_tflite"]
    exclusive_group: Optional[str] = None  # e.g., gps - indicates mutually exclusive options
    
    def __post_init__(self):
        """Validate HardwareProfile fields."""
        if not self.component:
            raise ValueError("component name is required")
        if not self.preferred:
            raise ValueError("preferred hardware configuration is required")