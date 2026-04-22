from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    executed_at: datetime | None = None
    result: str | None = None


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None

    # Source information
    source_component: str | None = None  # "gps", "motors", "battery", etc.
    source_location: str | None = None  # Geographic location if relevant

    # Alert details
    error_code: str | None = None
    sensor_readings: dict[str, Any] = Field(default_factory=dict)

    # User interaction
    acknowledged_by: str | None = None
    acknowledgment_note: str | None = None

    # Actions and responses
    suggested_actions: list[AlertAction] = Field(default_factory=list)
    automated_actions: list[AlertAction] = Field(default_factory=list)

    # Notification settings
    notify_immediately: bool = True
    notification_sent: bool = False
    notification_channels: list[str] = Field(default_factory=list)  # ["websocket", "email"]

    # Alert frequency control
    first_occurrence: datetime = Field(default_factory=lambda: datetime.now(UTC))
    occurrence_count: int = 1
    last_occurrence: datetime = Field(default_factory=lambda: datetime.now(UTC))
    suppressed: bool = False
    suppress_until: datetime | None = None

    # Related alerts
    parent_alert_id: str | None = None
    related_alert_ids: list[str] = Field(default_factory=list)

    # Custom metadata
    tags: list[str] = Field(default_factory=list)
    custom_data: dict[str, Any] = Field(default_factory=dict)

    def acknowledge(self, user: str, note: str | None = None):
        """Acknowledge the alert."""
        self.status = AlertStatus.ACKNOWLEDGED
        self.acknowledged_at = datetime.now(UTC)
        self.acknowledged_by = user
        self.acknowledgment_note = note
        self.updated_at = datetime.now(UTC)

    def resolve(self, note: str | None = None):
        """Mark alert as resolved."""
        self.status = AlertStatus.RESOLVED
        self.resolved_at = datetime.now(UTC)
        if note:
            self.acknowledgment_note = note
        self.updated_at = datetime.now(UTC)

    def dismiss(self):
        """Dismiss the alert."""
        self.status = AlertStatus.DISMISSED
        self.updated_at = datetime.now(UTC)

    def suppress(self, minutes: int = 60):
        """Suppress similar alerts for a period."""
        self.suppressed = True
        self.suppress_until = datetime.now(UTC) + timedelta(minutes=minutes)
        self.updated_at = datetime.now(UTC)

    def add_occurrence(self):
        """Record another occurrence of this alert."""
        self.occurrence_count += 1
        self.last_occurrence = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def is_suppressed(self) -> bool:
        """Check if alert is currently suppressed."""
        if not self.suppressed:
            return False
        if self.suppress_until and datetime.now(UTC) >= self.suppress_until:
            self.suppressed = False
            self.suppress_until = None
            return False
        return True

    model_config = ConfigDict(use_enum_values=True)
