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


class DocumentationType(str, Enum):
    """Documentation types"""
    HARDWARE_OVERVIEW = "hardware_overview"
    INSTALLATION_GUIDE = "installation_guide"
    OPERATIONS_MANUAL = "operations_manual"
    API_REFERENCE = "api_reference"
    TROUBLESHOOTING = "troubleshooting"
    CONSTITUTION = "constitution"
    RELEASE_NOTES = "release_notes"
    TESTING_GUIDE = "testing_guide"
    OTHER = "other"


class DocumentationFile(BaseModel):
    """Individual documentation file"""
    file_id: str
    file_path: str  # Relative path within docs/
    filename: str
    doc_type: DocumentationType
    
    # File metadata
    size_bytes: int = 0
    checksum: Optional[str] = None  # SHA256
    last_modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Content metadata
    title: Optional[str] = None
    version: Optional[str] = None
    author: Optional[str] = None
    
    # Accessibility
    offline_available: bool = True
    requires_auth: bool = False
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class DocumentationBundle(BaseModel):
    """Collection of synchronized documentation artifacts"""
    bundle_id: str
    bundle_version: str = "2.0.0"
    bundle_name: str = "LawnBerry Pi v2 Documentation"
    
    # Documentation files
    files: List[DocumentationFile] = Field(default_factory=list)
    
    # Bundle metadata
    total_size_bytes: int = 0
    total_files: int = 0
    
    # Checksums and validation
    bundle_checksum: Optional[str] = None  # SHA256 of all file checksums
    checksum_validated: bool = False
    checksum_validation_time: Optional[datetime] = None
    
    # Freshness tracking
    oldest_file_date: Optional[datetime] = None
    newest_file_date: Optional[datetime] = None
    days_since_last_update: int = 0
    freshness_status: str = "current"  # "current", "stale", "outdated"
    
    # Generation metadata
    generated_at: Optional[datetime] = None
    generation_method: str = "manual"  # "manual", "automated", "ci"
    
    # Offline support
    offline_bundle_available: bool = False
    offline_bundle_path: Optional[str] = None  # Path to tarball/ZIP
    offline_bundle_size_bytes: int = 0
    
    # Path traversal protection
    allowed_base_paths: List[str] = Field(default_factory=lambda: ["docs/", "assets/"])
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}
    
    def add_file(self, file: DocumentationFile):
        """Add a documentation file to the bundle"""
        self.files.append(file)
        self.total_files = len(self.files)
        self.total_size_bytes += file.size_bytes
        self.updated_at = datetime.now(timezone.utc)
        
        # Update file date tracking
        if not self.oldest_file_date or file.last_modified < self.oldest_file_date:
            self.oldest_file_date = file.last_modified
        if not self.newest_file_date or file.last_modified > self.newest_file_date:
            self.newest_file_date = file.last_modified
    
    def get_file_by_id(self, file_id: str) -> Optional[DocumentationFile]:
        """Get documentation file by ID"""
        return next((f for f in self.files if f.file_id == file_id), None)
    
    def get_files_by_type(self, doc_type: DocumentationType) -> List[DocumentationFile]:
        """Get files by documentation type"""
        return [f for f in self.files if f.doc_type == doc_type]
    
    def validate_path(self, file_path: str) -> bool:
        """Validate file path against path traversal attacks"""
        import os
        
        # Normalize path
        normalized = os.path.normpath(file_path)
        
        # Check for null bytes
        if '\x00' in file_path:
            return False
        
        # Check for absolute paths
        if os.path.isabs(normalized):
            return False
        
        # Check for path traversal attempts
        if '..' in normalized.split(os.sep):
            return False
        
        # Check if path starts with allowed base
        allowed = any(normalized.startswith(base) for base in self.allowed_base_paths)
        return allowed
    
    def compute_bundle_checksum(self) -> str:
        """Compute bundle checksum from all file checksums"""
        import hashlib
        
        hasher = hashlib.sha256()
        
        # Sort files by path for consistent checksum
        sorted_files = sorted(self.files, key=lambda f: f.file_path)
        
        for file in sorted_files:
            if file.checksum:
                hasher.update(file.checksum.encode('utf-8'))
        
        checksum = hasher.hexdigest()
        self.bundle_checksum = checksum
        self.checksum_validated = True
        self.checksum_validation_time = datetime.now(timezone.utc)
        
        return checksum
    
    def check_freshness(self, stale_threshold_days: int = 90, outdated_threshold_days: int = 180):
        """Check documentation freshness and update status"""
        from datetime import timedelta
        
        now = datetime.now(timezone.utc)
        
        if self.oldest_file_date:
            age_delta = now - self.oldest_file_date
            self.days_since_last_update = age_delta.days
            
            if age_delta.days > outdated_threshold_days:
                self.freshness_status = "outdated"
            elif age_delta.days > stale_threshold_days:
                self.freshness_status = "stale"
            else:
                self.freshness_status = "current"
    
    def generate_offline_bundle(self, output_path: str, format: str = "tar.gz") -> bool:
        """Generate offline documentation bundle"""
        import tarfile
        import zipfile
        import os
        
        try:
            if format == "tar.gz":
                with tarfile.open(output_path, "w:gz") as tar:
                    for file in self.files:
                        if os.path.exists(file.file_path):
                            tar.add(file.file_path, arcname=file.filename)
            
            elif format == "zip":
                with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for file in self.files:
                        if os.path.exists(file.file_path):
                            zipf.write(file.file_path, file.filename)
            
            self.offline_bundle_available = True
            self.offline_bundle_path = output_path
            self.offline_bundle_size_bytes = os.path.getsize(output_path)
            self.generated_at = datetime.now(timezone.utc)
            
            return True
            
        except Exception as e:
            return False
    
    def get_freshness_alerts(self) -> List[str]:
        """Get freshness alert messages"""
        alerts = []
        
        if self.freshness_status == "outdated":
            alerts.append(f"Documentation is outdated ({self.days_since_last_update} days old)")
        elif self.freshness_status == "stale":
            alerts.append(f"Documentation may be stale ({self.days_since_last_update} days old)")
        
        # Check for missing critical documentation
        critical_types = [
            DocumentationType.HARDWARE_OVERVIEW,
            DocumentationType.OPERATIONS_MANUAL,
            DocumentationType.TROUBLESHOOTING
        ]
        
        for critical_type in critical_types:
            if not self.get_files_by_type(critical_type):
                alerts.append(f"Missing critical documentation: {critical_type.value}")
        
        return alerts
    
    @classmethod
    def create_from_directory(cls, docs_dir: str, bundle_name: str = "LawnBerry Pi v2 Documentation") -> 'DocumentationBundle':
        """Create documentation bundle by scanning directory"""
        import os
        import uuid
        import hashlib
        
        bundle = cls(
            bundle_id=str(uuid.uuid4()),
            bundle_name=bundle_name
        )
        
        for root, dirs, files in os.walk(docs_dir):
            for filename in files:
                if filename.endswith(('.md', '.html', '.pdf')):
                    file_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(file_path, docs_dir)
                    
                    # Compute checksum
                    with open(file_path, 'rb') as f:
                        file_checksum = hashlib.sha256(f.read()).hexdigest()
                    
                    # Determine doc type from filename/path
                    doc_type = DocumentationType.OTHER
                    if 'hardware' in filename.lower():
                        doc_type = DocumentationType.HARDWARE_OVERVIEW
                    elif 'installation' in filename.lower():
                        doc_type = DocumentationType.INSTALLATION_GUIDE
                    elif 'operations' in filename.lower():
                        doc_type = DocumentationType.OPERATIONS_MANUAL
                    elif 'troubleshooting' in filename.lower():
                        doc_type = DocumentationType.TROUBLESHOOTING
                    elif 'constitution' in filename.lower():
                        doc_type = DocumentationType.CONSTITUTION
                    
                    doc_file = DocumentationFile(
                        file_id=str(uuid.uuid4()),
                        file_path=relative_path,
                        filename=filename,
                        doc_type=doc_type,
                        size_bytes=os.path.getsize(file_path),
                        checksum=file_checksum,
                        last_modified=datetime.fromtimestamp(os.path.getmtime(file_path), tz=timezone.utc)
                    )
                    
                    bundle.add_file(doc_file)
        
        bundle.compute_bundle_checksum()
        bundle.check_freshness()
        
        return bundle