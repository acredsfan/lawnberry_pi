from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MotorMode(str, Enum):
    STOP = "stop"
    ARCADE = "arcade"  # throttle + turn
    TANK = "tank"  # left + right independent
    DIRECT = "direct"  # raw motor speeds


class MotorCommand(BaseModel):
    """Motor control command for drive system."""

    mode: MotorMode = MotorMode.STOP

    # Arcade mode (most common)
    throttle: float | None = None  # -1.0 to 1.0 (reverse to forward)
    turn: float | None = None  # -1.0 to 1.0 (left to right)

    # Tank mode
    left_track: float | None = None  # -1.0 to 1.0
    right_track: float | None = None  # -1.0 to 1.0

    # Direct motor control (advanced)
    left_motor_speed: float | None = None  # -1.0 to 1.0
    right_motor_speed: float | None = None  # -1.0 to 1.0

    # Safety limits
    max_speed_limit: float = 1.0  # 0.0 to 1.0

    # Blade control
    blade_active: bool = False
    blade_height_mm: int | None = None

    # Command metadata
    command_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator(
        "throttle", "turn", "left_track", "right_track", "left_motor_speed", "right_motor_speed"
    )
    def validate_motor_values(cls, v):
        if v is not None and not (-1.0 <= v <= 1.0):
            raise ValueError("Motor values must be between -1.0 and 1.0")
        return v

    @field_validator("max_speed_limit")
    def validate_speed_limit(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError("Speed limit must be between 0.0 and 1.0")
        return v

    model_config = ConfigDict(use_enum_values=True)
