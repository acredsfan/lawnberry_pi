"""
WebUIPageContracts model for LawnBerry Pi v2
WebUI page definitions and data flow contracts
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator


class WebUIPageSlug(str, Enum):
    """Mandated WebUI page identifiers"""
    DASHBOARD = "dashboard"
    MAP_SETUP = "map-setup"
    MANUAL_CONTROL = "manual-control"
    MOW_PLANNING = "mow-planning"
    AI_TRAINING = "ai-training"
    SETTINGS = "settings"
    DOCS_HUB = "docs-hub"


class AuthRequirement(str, Enum):
    """Authentication requirements for pages"""
    NONE = "none"  # Public access
    BASIC = "basic"  # Basic authentication
    OPERATOR = "operator"  # Operator-level access
    ADMIN = "admin"  # Administrative access


class DataDependencyType(str, Enum):
    """Types of data dependencies"""
    REST_ENDPOINT = "rest_endpoint"
    WEBSOCKET_TOPIC = "websocket_topic"
    LOCAL_STORAGE = "local_storage"
    COMPUTED = "computed"


class DataDependency(BaseModel):
    """Data dependency specification"""
    dependency_id: str
    dependency_type: DataDependencyType
    endpoint_or_topic: str  # e.g., "/api/dashboard/status" or "telemetry/updates"
    required: bool = True
    caching_policy: Optional[str] = None  # "cache", "no-cache", "refresh"
    refresh_interval_ms: Optional[int] = None
    fallback_value: Optional[Any] = None


class TelemetryRequirement(BaseModel):
    """Telemetry streaming requirements"""
    topic: str
    cadence_hz: float = 5.0  # Default 5Hz
    burst_max_hz: float = 10.0
    critical: bool = False  # Alert if stream stalls
    buffer_size: int = 10
    auto_subscribe: bool = True


class PerformanceMetrics(BaseModel):
    """Page performance requirements and metrics"""
    target_load_time_ms: int = 2000
    target_interaction_time_ms: int = 100
    max_memory_mb: int = 50
    target_fps: int = 30  # For animations/updates
    
    # Measured metrics
    actual_load_time_ms: Optional[int] = None
    actual_memory_mb: Optional[float] = None
    frame_drops: int = 0
    error_count: int = 0


class ResponsiveBreakpoint(BaseModel):
    """Responsive design breakpoints"""
    name: str  # "mobile", "tablet", "desktop"
    min_width_px: int
    max_width_px: Optional[int] = None
    layout_adjustments: Dict[str, Any] = Field(default_factory=dict)


class WebUIPageContract(BaseModel):
    """Contract definition for a WebUI page"""
    # Page identification
    slug: WebUIPageSlug
    display_name: str
    route_path: str  # e.g., "/dashboard", "/map-setup"
    
    # Page objectives and functionality
    primary_goal: str
    key_features: List[str] = Field(default_factory=list)
    user_workflows: List[str] = Field(default_factory=list)
    
    # Data requirements
    rest_dependencies: List[DataDependency] = Field(default_factory=list)
    websocket_topics: List[TelemetryRequirement] = Field(default_factory=list)
    
    # Security and access
    auth_requirement: AuthRequirement = AuthRequirement.OPERATOR
    permissions_required: List[str] = Field(default_factory=list)
    
    # UI specifications
    layout_type: str = "responsive"  # "responsive", "fixed", "fluid"
    responsive_breakpoints: List[ResponsiveBreakpoint] = Field(default_factory=list)
    theme_support: List[str] = Field(default_factory=lambda: ["retro-amber", "retro-green"])
    
    # Performance and constraints
    performance_metrics: PerformanceMetrics = Field(default_factory=PerformanceMetrics)
    offline_support: bool = False
    simulation_support: bool = True  # Must be true per constitution
    
    # Navigation and routing
    parent_route: Optional[str] = None
    child_routes: List[str] = Field(default_factory=list)
    navigation_menu_group: Optional[str] = None
    
    # Component specifications
    required_components: List[str] = Field(default_factory=list)
    optional_components: List[str] = Field(default_factory=list)
    
    # Testing requirements
    e2e_test_scenarios: List[str] = Field(default_factory=list)
    integration_test_requirements: List[str] = Field(default_factory=list)
    
    # Documentation
    help_content_path: Optional[str] = None
    tutorial_available: bool = False
    
    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = "1.0"
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}
    
    def add_rest_dependency(self, endpoint: str, required: bool = True, **kwargs):
        """Add a REST API dependency"""
        dependency = DataDependency(
            dependency_id=f"rest_{len(self.rest_dependencies)}",
            dependency_type=DataDependencyType.REST_ENDPOINT,
            endpoint_or_topic=endpoint,
            required=required,
            **kwargs
        )
        self.rest_dependencies.append(dependency)
        self.last_modified = datetime.now(timezone.utc)
    
    def add_websocket_topic(self, topic: str, cadence_hz: float = 5.0, **kwargs):
        """Add a WebSocket topic requirement"""
        requirement = TelemetryRequirement(
            topic=topic,
            cadence_hz=cadence_hz,
            **kwargs
        )
        self.websocket_topics.append(requirement)
        self.last_modified = datetime.now(timezone.utc)


class WebUIPageContracts(BaseModel):
    """Collection of all WebUI page contracts"""
    pages: Dict[WebUIPageSlug, WebUIPageContract] = Field(default_factory=dict)
    
    # Global UI settings
    global_theme: str = "retro-amber"
    brand_colors: Dict[str, str] = Field(default_factory=dict)
    logo_path: str = "/assets/LawnBerryPi_logo.png"
    icon_path: str = "/assets/LawnBerryPi_icon2.png"
    favicon_path: str = "/assets/favicon.ico"
    
    # Navigation structure
    main_navigation: List[Dict[str, Any]] = Field(default_factory=list)
    footer_links: List[Dict[str, str]] = Field(default_factory=list)
    
    # Global performance settings
    max_concurrent_connections: int = 10
    websocket_reconnect_delay_ms: int = 1000
    api_timeout_ms: int = 5000
    
    # Accessibility settings
    accessibility_enabled: bool = True
    keyboard_navigation: bool = True
    screen_reader_support: bool = True
    high_contrast_mode: bool = False
    
    # Metadata
    contract_version: str = "2.0"
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}
    
    def add_page(self, page_contract: WebUIPageContract):
        """Add a page contract"""
        self.pages[page_contract.slug] = page_contract
        self.last_updated = datetime.now(timezone.utc)
    
    def get_page(self, slug: WebUIPageSlug) -> Optional[WebUIPageContract]:
        """Get a page contract by slug"""
        return self.pages.get(slug)
    
    def get_pages_requiring_auth(self, auth_level: AuthRequirement) -> List[WebUIPageContract]:
        """Get pages requiring specific authentication level"""
        return [
            page for page in self.pages.values()
            if page.auth_requirement == auth_level
        ]
    
    def get_pages_with_websocket_topics(self) -> List[WebUIPageContract]:
        """Get pages that use WebSocket topics"""
        return [
            page for page in self.pages.values()
            if len(page.websocket_topics) > 0
        ]
    
    @classmethod
    def create_default_contracts(cls) -> 'WebUIPageContracts':
        """Create default page contracts for all mandated pages"""
        contracts = cls()
        
        # Dashboard page
        dashboard = WebUIPageContract(
            slug=WebUIPageSlug.DASHBOARD,
            display_name="Dashboard",
            route_path="/dashboard",
            primary_goal="Real-time system monitoring and status overview",
            key_features=[
                "Live telemetry display",
                "Battery and power status",
                "Current location and GPS status",
                "Camera stream",
                "System health indicators"
            ]
        )
        dashboard.add_rest_dependency("/api/dashboard/status")
        dashboard.add_rest_dependency("/api/dashboard/telemetry")
        dashboard.add_websocket_topic("telemetry/updates", cadence_hz=5.0, critical=True)
        
        # Map Setup page
        map_setup = WebUIPageContract(
            slug=WebUIPageSlug.MAP_SETUP,
            display_name="Map Setup",
            route_path="/map-setup",
            primary_goal="Define mowing boundaries and exclusion zones",
            key_features=[
                "Interactive map interface",
                "Boundary polygon drawing",
                "No-go zone definition",
                "Home location setting"
            ]
        )
        map_setup.add_rest_dependency("/api/map/zones")
        map_setup.add_rest_dependency("/api/map/locations")
        
        # Manual Control page
        manual_control = WebUIPageContract(
            slug=WebUIPageSlug.MANUAL_CONTROL,
            display_name="Manual Control",
            route_path="/manual-control",
            primary_goal="Direct robot control and emergency operations",
            key_features=[
                "Drive controls",
                "Blade control",
                "Emergency stop",
                "Camera view"
            ],
            auth_requirement=AuthRequirement.OPERATOR
        )
        manual_control.add_rest_dependency("/api/control/drive")
        manual_control.add_rest_dependency("/api/control/blade")
        manual_control.add_rest_dependency("/api/control/emergency-stop")
        
        # Add other pages...
        contracts.add_page(dashboard)
        contracts.add_page(map_setup)
        contracts.add_page(manual_control)
        
        return contracts