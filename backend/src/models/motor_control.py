"""
MotorControl model for LawnBerry Pi v2
Motor commands and status for drive and blade systems
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict


class DriveController(str, Enum):
    """Available drive controller types"""
    ROBOHAT_MDDRC10 = "robohat_mddrc10"  # RoboHAT + Cytron MDDRC10
    L298N_ALT = "l298n_alt"  # L298N H-Bridge fallback


class ControlMode(str, Enum):
    """Motor control modes"""
    MANUAL = "manual"  # Direct user control
    AUTONOMOUS = "autonomous"  # Navigation system control
    EMERGENCY_STOP = "emergency_stop"  # Safety override
    CALIBRATION = "calibration"  # System calibration mode
    IDLE = "idle"  # No active control


class MotorStatus(str, Enum):
    """Motor operational status"""
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"
    STALLED = "stalled"
    CALIBRATING = "calibrating"


class DriveCommand(BaseModel):
    """Drive motor command structure"""
    # Drive system commands
    left_motor_speed: float = 0.0  # -1.0 to 1.0 (reverse to forward)
    right_motor_speed: float = 0.0  # -1.0 to 1.0 (reverse to forward)
    
    # Alternative control modes
    throttle: Optional[float] = None  # -1.0 to 1.0 for arcade-style control
    turn: Optional[float] = None  # -1.0 to 1.0 for arcade-style control
    
    # Command metadata
    control_mode: ControlMode = ControlMode.IDLE
    max_speed_limit: float = 1.0  # 0.0 to 1.0 speed governor
    ramp_rate: Optional[float] = None  # acceleration/deceleration rate
    timeout_ms: int = 1000  # command timeout in milliseconds
    
    @field_validator('left_motor_speed', 'right_motor_speed', 'throttle', 'turn')
    def validate_motor_range(cls, v):
        if v is not None and not (-1.0 <= v <= 1.0):
            raise ValueError('Motor values must be between -1.0 and 1.0')
        return v
    
    @field_validator('max_speed_limit')
    def validate_speed_limit(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError('Speed limit must be between 0.0 and 1.0')
        return v


class BladeCommand(BaseModel):
    """Blade motor command structure"""
    active: bool = False
    speed: float = 0.0  # 0.0 to 1.0 (blade speed)
    direction: int = 1  # 1 for forward, -1 for reverse (if supported)
    safety_enabled: bool = True
    timeout_ms: int = 1000  # command timeout in milliseconds
    
    @field_validator('speed')
    def validate_speed_range(cls, v):
        if not (0.0 <= v <= 1.0):
            raise ValueError('Blade speed must be between 0.0 and 1.0')
        return v


class EncoderFeedback(BaseModel):
    """Motor encoder feedback data"""
    left_encoder_ticks: int = 0
    right_encoder_ticks: int = 0
    left_rpm: Optional[float] = None
    right_rpm: Optional[float] = None
    left_distance: Optional[float] = None  # meters traveled
    right_distance: Optional[float] = None  # meters traveled
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MotorDiagnostics(BaseModel):
    """Motor system diagnostic information"""
    left_motor_current: Optional[float] = None  # Amperes
    right_motor_current: Optional[float] = None  # Amperes
    blade_motor_current: Optional[float] = None  # Amperes
    controller_temperature: Optional[float] = None  # °C
    voltage_supply: Optional[float] = None  # Volts
    error_flags: Dict[str, bool] = Field(default_factory=dict)
    last_error: Optional[str] = None
    error_count: int = 0


class MotorControl(BaseModel):
    """Complete motor control state and commands"""
    # Current commands
    drive_command: DriveCommand = Field(default_factory=DriveCommand)
    blade_command: BladeCommand = Field(default_factory=BladeCommand)
    
    # Motor status
    left_motor_status: MotorStatus = MotorStatus.STOPPED
    right_motor_status: MotorStatus = MotorStatus.STOPPED
    blade_motor_status: MotorStatus = MotorStatus.STOPPED
    
    # Feedback and monitoring
    encoder_feedback: Optional[EncoderFeedback] = None
    diagnostics: Optional[MotorDiagnostics] = None
    
    # Safety interlocks
    emergency_stop_active: bool = False
    tilt_cutoff_active: bool = False
    blade_safety_ok: bool = True
    manual_override_active: bool = False
    
    # Hardware configuration
    controller_type: DriveController = DriveController.L298N_ALT
    encoder_enabled: bool = False
    max_motor_current: float = 2.0  # Amperes per motor
    
    # Control loop parameters
    pid_kp: float = 1.0
    pid_ki: float = 0.1
    pid_kd: float = 0.05
    
    # Command timing
    last_command_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    command_sequence: int = 0
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(use_enum_values=True)
    
    def is_safe_to_operate(self) -> bool:
        """Check if it's safe to operate motors"""
        return (
            not self.emergency_stop_active and
            not self.tilt_cutoff_active and
            self.blade_safety_ok and
            self.left_motor_status != MotorStatus.ERROR and
            self.right_motor_status != MotorStatus.ERROR
        )
    
    def emergency_stop(self):
        """Activate emergency stop - stop all motors immediately"""
        self.emergency_stop_active = True
        self.drive_command.left_motor_speed = 0.0
        self.drive_command.right_motor_speed = 0.0
        self.drive_command.control_mode = ControlMode.EMERGENCY_STOP
        self.blade_command.active = False
        self.blade_command.speed = 0.0
        self.timestamp = datetime.now(timezone.utc)
    
    def calculate_differential_drive(self, throttle: float, turn: float) -> tuple[float, float]:
        """Convert arcade-style controls to differential drive speeds"""
        # Clamp inputs
        throttle = max(-1.0, min(1.0, throttle))
        turn = max(-1.0, min(1.0, turn))
        
        # Calculate left and right motor speeds
        left_speed = throttle + turn
        right_speed = throttle - turn
        
        # Normalize if either exceeds [-1, 1] range
        max_speed = max(abs(left_speed), abs(right_speed))
        if max_speed > 1.0:
            left_speed /= max_speed
            right_speed /= max_speed
        
        return left_speed, right_speed