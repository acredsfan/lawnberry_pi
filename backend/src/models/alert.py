from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertCategory(str, Enum):
    SAFETY = "safety"
    NAVIGATION = "navigation"
    POWER = "power"
    MECHANICAL = "mechanical"
    CONNECTIVITY = "connectivity"
    WEATHER = "weather"
    SECURITY = "security"
    MAINTENANCE = "maintenance"
    SYSTEM = "system"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class AlertAction(BaseModel):
    """Suggested or taken action for an alert."""
    action_type: str  # "stop_motors", "return_home", "notify_user", etc.
    description: str
    automated: bool = True
    executed_at: Optional[datetime] = None
    result: Optional[str] = None


class Alert(BaseModel):
    """System alert and notification model."""
    
    # Alert identification
    id: str
    title: str
    message: str
    
    # Classification
    severity: AlertSeverity
    category: AlertCategory
    
    # Alert lifecycle
    status: AlertStatus = AlertStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    
    # Source information
    source_component: Optional[str] = None  # "gps", "motors", "battery", etc.
    source_location: Optional[str] = None   # Geographic location if relevant
    
    # Alert details
    error_code: Optional[str] = None
    sensor_readings: Dict[str, Any] = Field(default_factory=dict)
    
    # User interaction
    acknowledged_by: Optional[str] = None
    acknowledgment_note: Optional[str] = None
    
    # Actions and responses
    suggested_actions: List[AlertAction] = Field(default_factory=list)
    automated_actions: List[AlertAction] = Field(default_factory=list)
    
    # Notification settings
    notify_immediately: bool = True
    notification_sent: bool = False
    notification_channels: List[str] = Field(default_factory=list)  # ["websocket", "email"]
    
    # Alert frequency control
    first_occurrence: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    occurrence_count: int = 1
    last_occurrence: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    suppressed: bool = False
    suppress_until: Optional[datetime] = None
    
    # Related alerts
    parent_alert_id: Optional[str] = None
    related_alert_ids: List[str] = Field(default_factory=list)
    
    # Custom metadata
    tags: List[str] = Field(default_factory=list)
    custom_data: Dict[str, Any] = Field(default_factory=dict)
    
    def acknowledge(self, user: str, note: Optional[str] = None):
        """Acknowledge the alert."""
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_at = datetime.now(timezone.utc)
        self.acknowledged_by = user
        self.acknowledgment_note = note
        self.updated_at = datetime.now(timezone.utc)
    
    def resolve(self, note: Optional[str] = None):
        """Mark alert as resolved."""
        self.status = AlertStatus.RESOLVED
        self.resolved_at = datetime.now(timezone.utc)
        if note:
            self.acknowledgment_note = note
        self.updated_at = datetime.now(timezone.utc)
    
    def dismiss(self):
        """Dismiss the alert."""
        self.status = AlertStatus.DISMISSED
        self.updated_at = datetime.now(timezone.utc)
    
    def suppress(self, minutes: int = 60):
        """Suppress similar alerts for a period."""
        self.suppressed = True
        self.suppress_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        self.updated_at = datetime.now(timezone.utc)
    
    def add_occurrence(self):
        """Record another occurrence of this alert."""
        self.occurrence_count += 1
        self.last_occurrence = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
    
    def is_suppressed(self) -> bool:
        """Check if alert is currently suppressed."""
        if not self.suppressed:
            return False
        if self.suppress_until and datetime.now(timezone.utc) >= self.suppress_until:
            self.suppressed = False
            self.suppress_until = None
            return False
        return True
    
    model_config = ConfigDict(use_enum_values=True)