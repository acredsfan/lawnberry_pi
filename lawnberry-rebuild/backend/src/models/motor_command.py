from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, validator


class MotorMode(str, Enum):
    STOP = "stop"
    ARCADE = "arcade"  # throttle + turn
    TANK = "tank"     # left + right independent
    DIRECT = "direct" # raw motor speeds


class MotorCommand(BaseModel):
    """Motor control command for drive system."""
    
    mode: MotorMode = MotorMode.STOP
    
    # Arcade mode (most common)
    throttle: Optional[float] = None  # -1.0 to 1.0 (reverse to forward)
    turn: Optional[float] = None      # -1.0 to 1.0 (left to right)
    
    # Tank mode
    left_track: Optional[float] = None   # -1.0 to 1.0
    right_track: Optional[float] = None  # -1.0 to 1.0
    
    # Direct motor control (advanced)
    left_motor_speed: Optional[float] = None   # -1.0 to 1.0
    right_motor_speed: Optional[float] = None  # -1.0 to 1.0
    
    # Safety limits
    max_speed_limit: float = 1.0  # 0.0 to 1.0
    
    # Blade control
    blade_active: bool = False
    blade_height_mm: Optional[int] = None
    
    # Command metadata
    command_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    @validator('throttle', 'turn', 'left_track', 'right_track', 'left_motor_speed', 'right_motor_speed')
    def validate_motor_values(cls, v):
        if v is not None and not (-1.0 <= v <= 1.0):
            raise ValueError('Motor values must be between -1.0 and 1.0')
        return v
    
    @validator('max_speed_limit')
    def validate_speed_limit(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError('Speed limit must be between 0.0 and 1.0')
        return v
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}