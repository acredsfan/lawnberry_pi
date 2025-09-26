"""
SystemConfiguration model for LawnBerry Pi v2
Operational parameters and user-defined settings
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator
import json


class OperationalMode(str, Enum):
    """System operational modes"""
    DEVELOPMENT = "development"  # Development/testing mode
    PRODUCTION = "production"    # Normal operation
    MAINTENANCE = "maintenance"  # Maintenance mode
    SIMULATION = "simulation"    # Simulation mode (SIM_MODE=1)


class GpsModeConfig(str, Enum):
    """GPS module configuration"""
    F9P_USB = "f9p_usb"      # u-blox ZED-F9P via USB with RTK
    NEO8M_UART = "neo8m_uart" # u-blox Neo-8M via UART


class DriveControllerConfig(str, Enum):
    """Drive controller configuration"""
    ROBOHAT_MDDRC10 = "robohat_mddrc10"  # RoboHAT + Cytron MDDRC10
    L298N_ALT = "l298n_alt"              # L298N H-Bridge fallback


class AIRunnerPreference(str, Enum):
    """AI acceleration preference order"""
    CORAL_FIRST = "coral_first"    # Try Coral, fallback to Hailo, then CPU
    HAILO_FIRST = "hailo_first"    # Try Hailo, fallback to Coral, then CPU
    CPU_ONLY = "cpu_only"          # CPU-only inference


class LogLevel(str, Enum):
    """Logging levels"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class SensorCalibration(BaseModel):
    """Sensor calibration parameters"""
    sensor_type: str
    calibration_data: Dict[str, float] = Field(default_factory=dict)
    calibration_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    calibration_valid: bool = True
    
    # Calibration offsets and scaling factors
    offset_x: float = 0.0
    offset_y: float = 0.0
    offset_z: float = 0.0
    scale_factor: float = 1.0
    
    # Temperature compensation (if applicable)
    temp_coefficient: Optional[float] = None
    reference_temperature: float = 25.0  # °C
    
    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class NavigationSettings(BaseModel):
    """Navigation and path planning settings"""
    # Speed and movement
    max_speed_ms: float = 0.8        # Maximum speed in m/s
    cruise_speed_ms: float = 0.5     # Normal cruising speed
    turn_speed_ms: float = 0.3       # Speed when turning
    acceleration_ms2: float = 0.5    # Acceleration limit
    
    # Path planning
    waypoint_tolerance_m: float = 0.5     # Distance tolerance for waypoints
    path_lookahead_m: float = 2.0         # Path planning lookahead distance
    obstacle_avoidance_distance_m: float = 1.0  # Obstacle avoidance trigger distance
    
    # Coverage patterns
    cutting_pattern: str = "parallel"     # "parallel", "spiral", "random"
    cutting_width_m: float = 0.3          # Effective cutting width
    overlap_factor: float = 0.1           # Overlap between passes (0.0-0.5)
    
    # Turn behavior
    turn_radius_m: float = 0.5            # Minimum turn radius
    reversing_enabled: bool = True        # Allow reverse movements
    
    # Dead reckoning fallback
    dead_reckoning_max_distance_m: float = 10.0  # Max distance without GPS
    dead_reckoning_drift_tolerance_m: float = 2.0  # Acceptable drift


class SafetyThresholds(BaseModel):
    """Safety system thresholds and limits"""
    # Emergency stop conditions
    emergency_stop_timeout_s: int = 30           # Timeout for emergency stop
    tilt_angle_threshold_deg: float = 30.0       # Maximum tilt angle
    obstacle_emergency_distance_m: float = 0.2   # Emergency stop distance
    
    # Power safety
    battery_critical_voltage: float = 10.0       # Critical battery voltage
    battery_low_voltage: float = 11.0           # Low battery warning
    max_motor_current_a: float = 5.0            # Maximum motor current
    motor_temperature_limit_c: float = 80.0     # Motor temperature limit
    
    # Timeout settings
    communication_timeout_s: int = 10           # Communication timeout
    sensor_timeout_s: int = 5                  # Sensor data timeout
    user_input_timeout_s: int = 300            # User input timeout
    
    # Blade safety
    blade_safety_enabled: bool = True
    blade_auto_stop_on_tilt: bool = True
    blade_max_runtime_s: int = 7200            # 2 hours continuous
    
    # Environmental limits
    max_operating_temperature_c: float = 50.0
    min_operating_temperature_c: float = -10.0
    max_wind_speed_ms: float = 10.0            # Maximum wind speed
    rain_detection_enabled: bool = True


class UIPreferences(BaseModel):
    """User interface customization preferences"""
    # Theme settings
    theme_variant: str = "retro-amber"     # "retro-amber", "retro-green", "modern"
    color_scheme: str = "auto"             # "light", "dark", "auto"
    animation_speed: str = "normal"        # "slow", "normal", "fast", "disabled"
    
    # Layout preferences
    dashboard_layout: str = "default"
    sidebar_collapsed: bool = False
    show_advanced_controls: bool = False
    
    # Map preferences
    map_provider: str = "google"           # "google", "osm"
    map_satellite_view: bool = False
    show_grid_overlay: bool = True
    show_coverage_history: bool = True
    
    # Telemetry display
    telemetry_refresh_rate_hz: float = 5.0
    show_raw_sensor_data: bool = False
    units_metric: bool = True              # True for metric, False for imperial
    
    # Notifications
    desktop_notifications: bool = True
    sound_alerts: bool = True
    email_notifications: bool = False
    notification_volume: float = 0.7       # 0.0-1.0


class BrandingReference(BaseModel):
    """Branding and visual identity reference"""
    logo_primary_path: str = "/assets/LawnBerryPi_logo.png"
    logo_icon_path: str = "/assets/LawnBerryPi_icon2.png"
    map_pin_path: str = "/assets/LawnBerryPi_Pin.png"
    favicon_path: str = "/assets/favicon.ico"
    
    # Color palette
    primary_color: str = "#FFA500"         # Amber/Orange
    secondary_color: str = "#228B22"       # Green
    accent_color: str = "#4A90E2"          # Blue
    
    # Typography
    font_family: str = "Courier New, monospace"  # Retro monospace font
    font_size_base: str = "14px"
    
    # Retro styling
    scanline_effect: bool = True
    crt_curve_effect: bool = False
    terminal_style_borders: bool = True


class NetworkConfiguration(BaseModel):
    """Network configuration settings"""
    # Wi-Fi settings (primary runtime)
    wifi_enabled: bool = True
    wifi_ssid_hints: List[str] = Field(default_factory=list)
    wifi_auto_reconnect: bool = True
    wifi_power_save: bool = False
    
    # Ethernet settings (bench-only)
    ethernet_enabled: bool = False
    ethernet_bench_only: bool = True       # Per constitutional requirement
    
    # Network timeouts
    connection_timeout_s: int = 30
    request_timeout_s: int = 10
    
    # API settings
    api_rate_limit_per_minute: int = 100
    websocket_ping_interval_s: int = 30
    
    # External services
    ntp_servers: List[str] = Field(default_factory=lambda: [
        "pool.ntp.org", "time.google.com"
    ])
    weather_api_enabled: bool = True
    weather_api_key: Optional[str] = None


class SystemConfiguration(BaseModel):
    """Complete system configuration"""
    # Configuration metadata
    config_version: str = "2.0"
    config_id: str = "default"
    
    # Operational settings
    operational_mode: OperationalMode = OperationalMode.PRODUCTION
    sim_mode_enabled: bool = False         # Reflects SIM_MODE environment
    debug_mode_enabled: bool = False
    
    # Hardware configuration
    gps_mode: GpsModeConfig = GpsModeConfig.NEO8M_UART
    drive_controller: DriveControllerConfig = DriveControllerConfig.L298N_ALT
    ai_runner_preference: AIRunnerPreference = AIRunnerPreference.CPU_ONLY
    
    # Calibration data
    sensor_calibration: Dict[str, SensorCalibration] = Field(default_factory=dict)
    
    # System settings
    navigation_settings: NavigationSettings = Field(default_factory=NavigationSettings)
    safety_thresholds: SafetyThresholds = Field(default_factory=SafetyThresholds)
    ui_preferences: UIPreferences = Field(default_factory=UIPreferences)
    branding_ref: BrandingReference = Field(default_factory=BrandingReference)
    network_config: NetworkConfiguration = Field(default_factory=NetworkConfiguration)
    
    # Logging and observability
    log_level: LogLevel = LogLevel.INFO
    log_retention_days: int = 30
    metrics_enabled: bool = True
    telemetry_enabled: bool = True
    
    # Data management
    data_retention_days: int = 90
    auto_backup_enabled: bool = True
    backup_interval_hours: int = 24
    
    # Feature flags
    feature_flags: Dict[str, bool] = Field(default_factory=dict)
    experimental_features: Dict[str, bool] = Field(default_factory=dict)
    
    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_modified: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_backup: Optional[datetime] = None
    
    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}
    
    def add_sensor_calibration(self, sensor_type: str, calibration: SensorCalibration):
        """Add or update sensor calibration"""
        self.sensor_calibration[sensor_type] = calibration
        self.last_modified = datetime.now(timezone.utc)
    
    def get_sensor_calibration(self, sensor_type: str) -> Optional[SensorCalibration]:
        """Get sensor calibration by type"""
        return self.sensor_calibration.get(sensor_type)
    
    def set_feature_flag(self, flag_name: str, enabled: bool):
        """Set a feature flag"""
        self.feature_flags[flag_name] = enabled
        self.last_modified = datetime.now(timezone.utc)
    
    def is_feature_enabled(self, flag_name: str) -> bool:
        """Check if a feature flag is enabled"""
        return self.feature_flags.get(flag_name, False)
    
    def update_setting(self, section: str, key: str, value: Any):
        """Update a configuration setting"""
        if hasattr(self, section):
            section_obj = getattr(self, section)
            if hasattr(section_obj, key):
                setattr(section_obj, key, value)
                self.last_modified = datetime.now(timezone.utc)
                return True
        return False
    
    def to_json(self) -> str:
        """Export configuration as JSON"""
        return json.dumps(self.dict(), indent=2, default=str)
    
    def validate_configuration(self) -> List[str]:
        """Validate configuration and return any issues"""
        issues = []
        
        # Validate speed settings
        nav = self.navigation_settings
        if nav.max_speed_ms < nav.cruise_speed_ms:
            issues.append("Maximum speed must be >= cruise speed")
        
        if nav.cruise_speed_ms < nav.turn_speed_ms:
            issues.append("Cruise speed must be >= turn speed")
        
        # Validate safety thresholds
        safety = self.safety_thresholds
        if safety.battery_critical_voltage >= safety.battery_low_voltage:
            issues.append("Critical battery voltage must be < low battery voltage")
        
        # Validate telemetry rate
        if self.ui_preferences.telemetry_refresh_rate_hz > 10.0:
            issues.append("Telemetry refresh rate cannot exceed 10 Hz")
        
        return issues
    
    @classmethod
    def create_default_config(cls) -> 'SystemConfiguration':
        """Create default system configuration"""
        config = cls()
        
        # Set default feature flags
        config.feature_flags = {
            "weather_integration": True,
            "ai_obstacle_detection": True,
            "autonomous_charging": True,
            "coverage_optimization": True,
            "mobile_app_support": False,
            "cloud_sync": False
        }
        
        return config