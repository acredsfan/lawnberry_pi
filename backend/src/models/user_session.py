"""
UserSession model for LawnBerry Pi v2
Web interface connections and user management
"""

from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict
import uuid
from ..models.auth_security_config import SecurityLevel


class SessionStatus(str, Enum):
    """User session status"""
    ACTIVE = "active"
    IDLE = "idle"
    EXPIRED = "expired"
    TERMINATED = "terminated"
    LOCKED = "locked"


class UserRole(str, Enum):
    """User role levels"""
    VIEWER = "viewer"  # Read-only access
    OPERATOR = "operator"  # Standard operation
    ADMIN = "admin"  # Administrative access
    SYSTEM = "system"  # System-level access


class AuthenticationMethod(str, Enum):
    """Authentication methods"""
    SHARED_CREDENTIAL = "shared_credential"  # Single operator credential
    TOKEN = "token"  # JWT token
    API_KEY = "api_key"  # API key authentication


class ConnectionType(str, Enum):
    """Connection types"""
    WEB_BROWSER = "web_browser"
    WEBSOCKET = "websocket"
    REST_API = "rest_api"
    MOBILE_APP = "mobile_app"
    SYSTEM_SERVICE = "system_service"


class Permission(str, Enum):
    """System permissions"""
    VIEW_STATUS = "view_status"
    VIEW_TELEMETRY = "view_telemetry"
    VIEW_CAMERA = "view_camera"
    CONTROL_MOTORS = "control_motors"
    CONTROL_BLADE = "control_blade"
    EMERGENCY_STOP = "emergency_stop"
    EDIT_MAP = "edit_map"
    MANAGE_JOBS = "manage_jobs"
    MANAGE_AI = "manage_ai"
    MANAGE_SETTINGS = "manage_settings"
    VIEW_LOGS = "view_logs"
    EXPORT_DATA = "export_data"


class SessionActivity(BaseModel):
    """Individual session activity record"""
    activity_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Activity details
    action: str  # "login", "page_view", "api_call", "control_command", etc.
    resource: Optional[str] = None  # Resource accessed
    method: Optional[str] = None  # HTTP method or action type
    
    # Request details
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    referrer: Optional[str] = None
    
    # Response details
    status_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    
    # Additional context
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UserPreferences(BaseModel):
    """User interface preferences"""
    # Theme and appearance
    theme: str = "retro-amber"  # "retro-amber", "retro-green", "modern"
    color_scheme: str = "auto"  # "light", "dark", "auto"
    font_size: str = "medium"  # "small", "medium", "large"
    
    # Dashboard customization
    dashboard_layout: str = "default"
    visible_widgets: List[str] = Field(default_factory=list)
    widget_positions: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    
    # Telemetry preferences
    telemetry_cadence_hz: float = 5.0
    auto_refresh_enabled: bool = True
    sound_alerts_enabled: bool = True
    
    # Map preferences
    map_provider: str = "google"  # "google", "osm"
    map_zoom_level: int = 18
    show_coverage_overlay: bool = True
    show_path_history: bool = True
    
    # Notification preferences
    desktop_notifications: bool = True
    email_notifications: bool = False
    emergency_alerts: bool = True
    
    # Language and localization
    language: str = "en"
    timezone: str = "UTC"
    date_format: str = "ISO"  # "ISO", "US", "EU"
    units: str = "metric"  # "metric", "imperial"


class SecurityContext(BaseModel):
    """Security context for session"""
    # Authentication details
    authentication_method: AuthenticationMethod = AuthenticationMethod.SHARED_CREDENTIAL
    credential_hash: Optional[str] = None  # Hashed credential
    token_expires_at: Optional[datetime] = None
    
    # Access control
    role: UserRole = UserRole.OPERATOR
    permissions: List[Permission] = Field(default_factory=list)
    
    # Security flags
    mfa_required: bool = False
    mfa_verified: bool = False
    password_expired: bool = False
    account_locked: bool = False
    
    # Rate limiting
    api_calls_per_minute: int = 0
    max_api_calls_per_minute: int = 100
    login_attempts: int = 0
    max_login_attempts: int = 5
    
    # Audit trail
    last_password_change: Optional[datetime] = None
    failed_login_attempts: List[datetime] = Field(default_factory=list)
    
    def has_permission(self, permission: Permission) -> bool:
        """Check if user has specific permission"""
        return permission in self.permissions
    
    def is_rate_limited(self) -> bool:
        """Check if user is rate limited"""
        return self.api_calls_per_minute >= self.max_api_calls_per_minute
    
    def is_locked_out(self) -> bool:
        """Check if user is locked out due to failed attempts"""
        return (
            self.account_locked or
            self.login_attempts >= self.max_login_attempts
        )


class WebSocketConnection(BaseModel):
    """WebSocket connection details"""
    connection_id: str
    connected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Connection details
    protocol: str = "websocket"
    endpoint: str = "/ws/telemetry"
    
    # Subscription information
    subscribed_topics: List[str] = Field(default_factory=list)
    message_count_sent: int = 0
    message_count_received: int = 0
    
    # Health monitoring
    last_ping: Optional[datetime] = None
    last_pong: Optional[datetime] = None
    ping_interval_seconds: int = 30
    
    # Error tracking
    connection_errors: int = 0
    last_error: Optional[str] = None


class UserSession(BaseModel):
    """Complete user session information"""
    # Session identification
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "operator"  # Single operator model
    # Compatibility username field for tests
    username: str = "operator"
    
    # Session timing
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=8)
    )
    
    # Session status
    status: SessionStatus = SessionStatus.ACTIVE
    
    # Connection information
    connection_type: ConnectionType = ConnectionType.WEB_BROWSER
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    
    # WebSocket connections
    websocket_connections: List[WebSocketConnection] = Field(default_factory=list)
    
    # Security and permissions
    security_context: SecurityContext = Field(default_factory=SecurityContext)
    # Compatibility flags/metadata used by auth tests
    security_level: Optional[SecurityLevel] = None
    mfa_verified: bool = False
    backup_code_used: bool = False
    oauth_provider: Optional[str] = None
    tunnel_authenticated: bool = False
    
    # User preferences
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    
    # Activity tracking
    activity_log: List[SessionActivity] = Field(default_factory=list)
    max_activity_log_size: int = 1000
    
    # Session statistics
    page_views: int = 0
    api_calls: int = 0
    control_commands: int = 0
    data_exports: int = 0
    
    # Idle timeout settings
    idle_timeout_minutes: int = 30
    warning_before_timeout_minutes: int = 5
    
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    model_config = ConfigDict(use_enum_values=True)
    
    def is_expired(self) -> bool:
        """Check if session is expired"""
        now = datetime.now(timezone.utc)
        return now >= self.expires_at
    
    def is_idle(self) -> bool:
        """Check if session is idle"""
        now = datetime.now(timezone.utc)
        idle_threshold = self.last_activity + timedelta(minutes=self.idle_timeout_minutes)
        return now >= idle_threshold
    
    def update_activity(self, action: str, **kwargs):
        """Record user activity"""
        activity = SessionActivity(
            action=action,
            **kwargs
        )
        
        self.activity_log.append(activity)
        
        # Maintain log size limit
        if len(self.activity_log) > self.max_activity_log_size:
            self.activity_log.pop(0)
        
        # Update session timing
        self.last_activity = datetime.now(timezone.utc)
        
        # Update statistics
        if action == "page_view":
            self.page_views += 1
        elif action == "api_call":
            self.api_calls += 1
        elif action in ["control_drive", "control_blade", "emergency_stop"]:
            self.control_commands += 1
    
    def extend_session(self, hours: int = 8):
        """Extend session expiration"""
        self.expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)
        self.last_activity = datetime.now(timezone.utc)
    
    def add_websocket_connection(self, connection_id: str, endpoint: str = "/ws/telemetry"):
        """Add WebSocket connection"""
        connection = WebSocketConnection(
            connection_id=connection_id,
            endpoint=endpoint
        )
        self.websocket_connections.append(connection)
    
    def remove_websocket_connection(self, connection_id: str):
        """Remove WebSocket connection"""
        self.websocket_connections = [
            conn for conn in self.websocket_connections
            if conn.connection_id != connection_id
        ]
    
    def get_websocket_connection(self, connection_id: str) -> Optional[WebSocketConnection]:
        """Get WebSocket connection by ID"""
        return next(
            (conn for conn in self.websocket_connections if conn.connection_id == connection_id),
            None
        )
    
    def terminate(self, reason: str = "user_logout"):
        """Terminate session"""
        self.status = SessionStatus.TERMINATED
        self.update_activity("session_terminated", metadata={"reason": reason})
        
        # Clear sensitive data
        self.security_context.credential_hash = None
        self.websocket_connections.clear()
    
    @classmethod
    def create_operator_session(cls, client_ip: str = None, user_agent: str = None) -> 'UserSession':
        """Create a new operator session with default permissions"""
        session = cls(
            client_ip=client_ip,
            user_agent=user_agent
        )
        
        # Set operator permissions
        session.security_context.role = UserRole.OPERATOR
        session.security_context.permissions = [
            Permission.VIEW_STATUS,
            Permission.VIEW_TELEMETRY,
            Permission.VIEW_CAMERA,
            Permission.CONTROL_MOTORS,
            Permission.CONTROL_BLADE,
            Permission.EMERGENCY_STOP,
            Permission.EDIT_MAP,
            Permission.MANAGE_JOBS,
            Permission.MANAGE_AI,
            Permission.VIEW_LOGS,
            Permission.EXPORT_DATA
        ]
        
        session.update_activity("login")
        return session