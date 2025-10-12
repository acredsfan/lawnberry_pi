"""
ControlSession model for LawnBerry Pi v2
Auditable record of manual control interactions and safety interlocks
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator, ConfigDict


class ControlCommandType(str, Enum):
    """Control command types"""
    DRIVE = "drive"
    BLADE = "blade"
    EMERGENCY_STOP = "emergency_stop"
    MODE_TOGGLE = "mode_toggle"
    EMERGENCY_CLEAR = "emergency_clear"


class ControlCommandResult(str, Enum):
    """Control command execution result"""
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    PENDING = "pending"


class EmergencyStatus(str, Enum):
    """Emergency stop status"""
    CLEAR = "clear"
    ACTIVE = "active"
    PENDING_CLEAR = "pending_clear"


class SafetyInterlock(str, Enum):
    """Safety interlock types"""
    BLADE_REQUIRES_STOPPED_MOTORS = "blade_requires_stopped_motors"
    EMERGENCY_STOP_OVERRIDE = "emergency_stop_override"
    LOW_BATTERY_LOCKOUT = "low_battery_lockout"
    TILT_SENSOR_LOCKOUT = "tilt_sensor_lockout"
    WATCHDOG_TIMEOUT = "watchdog_timeout"


class ControlCommand(BaseModel):
    """Individual control command"""
    command_id: str
    command_type: ControlCommandType
    
    # Command payload (varies by type)
    throttle: Optional[float] = Field(None, ge=-1.0, le=1.0)  # For drive commands
    turn: Optional[float] = Field(None, ge=-1.0, le=1.0)  # For drive commands
    blade_enabled: Optional[bool] = None  # For blade commands
    mode_target: Optional[str] = None  # For mode toggles
    reason: Optional[str] = None  # For emergency commands
    confirmation_token: Optional[str] = None  # For emergency clear
    
    # Execution details
    result: ControlCommandResult = ControlCommandResult.PENDING
    status_reason: Optional[str] = None
    latency_ms: Optional[float] = None
    
    # Safety checks
    safety_checks_passed: List[str] = Field(default_factory=list)
    safety_interlocks_active: List[SafetyInterlock] = Field(default_factory=list)
    
    # Watchdog acknowledgement
    watchdog_echo: Optional[str] = None  # RoboHAT watchdog response
    watchdog_latency_ms: Optional[float] = None
    
    # Timestamps
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    
    model_config = ConfigDict(use_enum_values=True)
    
    @field_validator('latency_ms', 'watchdog_latency_ms')
    def validate_latency(cls, v):
        if v is not None and (v < 0 or v > 10000):
            raise ValueError('Latency must be between 0 and 10000 ms')
        return v


class ControlAuditEntry(BaseModel):
    """Auditable record of control session interaction"""
    audit_id: str
    session_id: str
    operator_id: str  # Single shared credential with MFA
    
    # Command details
    command: ControlCommand
    
    # Result and state
    result: ControlCommandResult
    status_reason: Optional[str] = None
    
    # Telemetry snapshot reference
    telemetry_snapshot_id: Optional[str] = None
    
    # Settings changes (if command modified configuration)
    settings_changed: Dict[str, Any] = Field(default_factory=dict)
    
    # Remediation guidance
    documentation_link: Optional[str] = None  # Link to troubleshooting docs
    remediation_steps: List[str] = Field(default_factory=list)
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(use_enum_values=True)


class EmergencyState(BaseModel):
    """Current emergency stop state"""
    status: EmergencyStatus = EmergencyStatus.CLEAR
    
    # Emergency details
    triggered_at: Optional[datetime] = None
    trigger_reason: Optional[str] = None
    trigger_source: Optional[str] = None  # "manual", "watchdog", "safety_sensor"
    
    # Clear operation
    cleared_at: Optional[datetime] = None
    cleared_by: Optional[str] = None
    clear_confirmation_token: Optional[str] = None
    clear_requires_confirmation: bool = True
    
    # Active interlocks
    active_interlocks: List[SafetyInterlock] = Field(default_factory=list)
    
    # Audit trail
    audit_entries: List[str] = Field(default_factory=list)  # References to audit IDs
    
    model_config = ConfigDict(use_enum_values=True)
    
    def trigger_emergency(self, reason: str, source: str = "manual"):
        """Trigger emergency stop"""
        self.status = EmergencyStatus.ACTIVE
        self.triggered_at = datetime.now(timezone.utc)
        self.trigger_reason = reason
        self.trigger_source = source
        
        # Generate confirmation token for clear operation
        import secrets
        self.clear_confirmation_token = secrets.token_urlsafe(16)
    
    def request_clear(self, confirmation_token: str, operator_id: str) -> bool:
        """Request emergency clear with confirmation"""
        if self.status != EmergencyStatus.ACTIVE:
            return False
        
        if not self.clear_requires_confirmation:
            self.status = EmergencyStatus.CLEAR
            self.cleared_at = datetime.now(timezone.utc)
            self.cleared_by = operator_id
            return True
        
        if confirmation_token == self.clear_confirmation_token:
            self.status = EmergencyStatus.CLEAR
            self.cleared_at = datetime.now(timezone.utc)
            self.cleared_by = operator_id
            self.clear_confirmation_token = None
            return True
        
        return False
    
    def check_interlock(self, interlock: SafetyInterlock) -> bool:
        """Check if a specific interlock is active"""
        return interlock in self.active_interlocks
    
    def add_interlock(self, interlock: SafetyInterlock):
        """Add a safety interlock"""
        if interlock not in self.active_interlocks:
            self.active_interlocks.append(interlock)
    
    def remove_interlock(self, interlock: SafetyInterlock):
        """Remove a safety interlock"""
        if interlock in self.active_interlocks:
            self.active_interlocks.remove(interlock)


class ControlSession(BaseModel):
    """Complete control session with audit trail"""
    session_id: str
    operator_id: str
    
    # Session state
    active: bool = True
    emergency_state: EmergencyState = Field(default_factory=EmergencyState)
    
    # Audit trail
    audit_entries: List[ControlAuditEntry] = Field(default_factory=list)
    
    # Statistics
    commands_issued: int = 0
    commands_accepted: int = 0
    commands_rejected: int = 0
    average_latency_ms: float = 0.0
    
    # Timestamps
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None
    last_command_at: Optional[datetime] = None
    
    model_config = ConfigDict(use_enum_values=True)
    
    def issue_command(self, command: ControlCommand) -> ControlAuditEntry:
        """Issue a control command and create audit entry"""
        import uuid
        
        # Check emergency state
        if self.emergency_state.status == EmergencyStatus.ACTIVE:
            if command.command_type != ControlCommandType.EMERGENCY_CLEAR:
                command.result = ControlCommandResult.BLOCKED
                command.status_reason = "EMERGENCY_STOP_ACTIVE"
        
        # Create audit entry
        audit_entry = ControlAuditEntry(
            audit_id=str(uuid.uuid4()),
            session_id=self.session_id,
            operator_id=self.operator_id,
            command=command,
            result=command.result,
            status_reason=command.status_reason
        )
        
        self.audit_entries.append(audit_entry)
        self.commands_issued += 1
        self.last_command_at = datetime.now(timezone.utc)
        
        if command.result == ControlCommandResult.ACCEPTED:
            self.commands_accepted += 1
        elif command.result == ControlCommandResult.REJECTED:
            self.commands_rejected += 1
        
        # Update average latency
        if command.latency_ms is not None:
            total_latency = self.average_latency_ms * (self.commands_issued - 1)
            self.average_latency_ms = (total_latency + command.latency_ms) / self.commands_issued
        
        return audit_entry
    
    def end_session(self):
        """End the control session"""
        self.active = False
        self.ended_at = datetime.now(timezone.utc)
