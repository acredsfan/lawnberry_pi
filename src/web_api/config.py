"""
Configuration Management
Settings and configuration for the web API backend using Pydantic.
"""

from functools import lru_cache
from typing import List, Optional
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings
import os
import logging
from pathlib import Path
try:
    # Auto-load .env early so AuthSettings os.getenv lookups work even when
    # importing settings outside run_server (e.g. systemd ExecStartPost probe).
    # This is safe and idempotent; if variables already in environment they are preserved.
    from dotenv import load_dotenv  # type: ignore
    _root = Path(__file__).resolve().parent.parent.parent  # project root
    env_path = _root / '.env'
    if env_path.exists():
        load_dotenv(env_path, override=False)
except Exception:
    # Don't fail if python-dotenv not available; run_server will still load it.
    pass


class MQTTSettings(BaseSettings):
    """MQTT connection settings"""
    broker_host: str = Field(default="localhost", validation_alias="MQTT_BROKER_HOST")
    broker_port: int = Field(default=1883, validation_alias="MQTT_BROKER_PORT")
    client_id: str = Field(default="web_api_backend", validation_alias="MQTT_CLIENT_ID")
    keepalive: int = Field(default=60, validation_alias="MQTT_KEEPALIVE")
    reconnect_delay: int = Field(default=5, validation_alias="MQTT_RECONNECT_DELAY")
    max_reconnect_delay: int = Field(default=300, validation_alias="MQTT_MAX_RECONNECT_DELAY")
    message_timeout: int = Field(default=30, validation_alias="MQTT_MESSAGE_TIMEOUT")

    # Authentication
    username: Optional[str] = Field(default=None, validation_alias="MQTT_USERNAME")
    password: Optional[str] = Field(default=None, validation_alias="MQTT_PASSWORD")

    # TLS
    use_tls: bool = Field(default=False, validation_alias="MQTT_USE_TLS")
    ca_certs: Optional[str] = Field(default=None, validation_alias="MQTT_CA_CERTS")
    cert_file: Optional[str] = Field(default=None, validation_alias="MQTT_CERT_FILE")
    key_file: Optional[str] = Field(default=None, validation_alias="MQTT_KEY_FILE")
    
    class Config:
        env_prefix = "MQTT_"


class AuthSettings(BaseSettings):
    """Authentication and authorization settings"""
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    
    # Default admin user  
    admin_username: str = "admin"
    admin_password: str = ""
    
    # Enable/disable authentication
    enabled: bool = True
    
    def __init__(self, **kwargs):
        # Load from environment variables
        kwargs.setdefault('jwt_secret_key', os.getenv('JWT_SECRET_KEY', ''))
        kwargs.setdefault('jwt_algorithm', os.getenv('JWT_ALGORITHM', 'HS256'))
        kwargs.setdefault('jwt_expiration_hours', int(os.getenv('JWT_EXPIRATION_HOURS', '24')))
        kwargs.setdefault('admin_username', os.getenv('ADMIN_USERNAME', 'admin'))
        kwargs.setdefault('admin_password', os.getenv('ADMIN_PASSWORD', ''))
        kwargs.setdefault('enabled', os.getenv('AUTH_ENABLED', 'true').lower() == 'true')
        
        super().__init__(**kwargs)
        
        # Validate critical environment variables after initialization
        if not self.jwt_secret_key or not self.admin_password:
            # Instead of aborting startup, disable auth (graceful degraded mode)
            missing = []
            if not self.jwt_secret_key:
                missing.append("JWT_SECRET_KEY")
            if not self.admin_password:
                missing.append("ADMIN_PASSWORD")
            logging.getLogger(__name__).warning(
                "Authentication disabled due to missing secrets: %s. Set them in .env to enable auth.",
                ", ".join(missing)
            )
            object.__setattr__(self, 'enabled', False)  # pydantic BaseSettings immutability workaround (if any)
    
    class Config:
        env_prefix = "AUTH_"


class RedisSettings(BaseSettings):
    """Redis cache settings"""
    host: str = Field(default="localhost", validation_alias="REDIS_HOST")
    port: int = Field(default=6379, validation_alias="REDIS_PORT")
    db: int = Field(default=0, validation_alias="REDIS_DB")
    password: Optional[str] = Field(default=None, validation_alias="REDIS_PASSWORD")

    # Connection pool settings
    max_connections: int = Field(default=20, validation_alias="REDIS_MAX_CONNECTIONS")
    retry_on_timeout: bool = Field(default=True, validation_alias="REDIS_RETRY_ON_TIMEOUT")

    # Cache TTL settings (seconds)
    default_ttl: int = Field(default=300, validation_alias="REDIS_DEFAULT_TTL")
    sensor_data_ttl: int = Field(default=60, validation_alias="REDIS_SENSOR_DATA_TTL")
    config_ttl: int = Field(default=3600, validation_alias="REDIS_CONFIG_TTL")
    
    class Config:
        env_prefix = "REDIS_"


class DatabaseSettings(BaseSettings):
    """Database settings"""
    url: str = Field(default="sqlite:///lawnberry.db", validation_alias="DATABASE_URL")
    echo: bool = Field(default=False, validation_alias="DATABASE_ECHO")
    pool_size: int = Field(default=5, validation_alias="DATABASE_POOL_SIZE")
    max_overflow: int = Field(default=10, validation_alias="DATABASE_MAX_OVERFLOW")
    
    class Config:
        env_prefix = "DATABASE_"

class GoogleMapsSettings(BaseSettings):
    """Google Maps API settings"""
    api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_MAPS_API_KEY", "REACT_APP_GOOGLE_MAPS_API_KEY"),
    )
    usage_level: str = Field(default="medium", validation_alias="REACT_APP_GOOGLE_MAPS_USAGE_LEVEL")
    cost_alert_threshold: float = Field(default=50.0, validation_alias="GOOGLE_MAPS_COST_ALERT_THRESHOLD")

    # Cache settings
    geocoding_cache_ttl: int = Field(default=604800, validation_alias="GOOGLE_MAPS_GEOCODING_CACHE_TTL")  # 7 days
    reverse_geocoding_cache_ttl: int = Field(default=86400, validation_alias="GOOGLE_MAPS_REVERSE_CACHE_TTL")  # 1 day
    places_cache_ttl: int = Field(default=21600, validation_alias="GOOGLE_MAPS_PLACES_CACHE_TTL")  # 6 hours
    tiles_cache_ttl: int = Field(default=2592000, validation_alias="GOOGLE_MAPS_TILES_CACHE_TTL")  # 30 days

    def is_available(self) -> bool:
        """Check if Google Maps API is properly configured"""
        return bool(self.api_key and self.api_key != "your_google_maps_api_key_here")

    class Config:
        env_prefix = "GOOGLE_MAPS_"




class RateLimitSettings(BaseSettings):
    """Rate limiting settings"""
    enabled: bool = Field(default=True, validation_alias="RATE_LIMIT_ENABLED")
    default_requests_per_minute: int = Field(default=100, validation_alias="RATE_LIMIT_DEFAULT_RPM")
    burst_multiplier: float = Field(default=1.5, validation_alias="RATE_LIMIT_BURST_MULTIPLIER")

    # Per-endpoint limits
    sensor_data_rpm: int = Field(default=200, validation_alias="RATE_LIMIT_SENSOR_DATA_RPM")
    navigation_rpm: int = Field(default=60, validation_alias="RATE_LIMIT_NAVIGATION_RPM")
    configuration_rpm: int = Field(default=30, validation_alias="RATE_LIMIT_CONFIG_RPM")
    
    class Config:
        env_prefix = "RATE_LIMIT_"


class Settings(BaseSettings):
    """Main application settings"""
    # Application settings
    app_name: str = Field(default="Lawnberry Web API", validation_alias="APP_NAME")
    debug: bool = Field(default=False, validation_alias="DEBUG")
    host: str = Field(default="0.0.0.0", validation_alias="HOST")
    port: int = Field(default=8000, validation_alias="PORT")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    # CORS settings
    cors_origins: List[str] = Field(default_factory=lambda: ["*"], validation_alias="CORS_ORIGINS")

    # API settings
    api_prefix: str = Field(default="/api/v1", validation_alias="API_PREFIX")
    docs_url: Optional[str] = Field(default="/docs", validation_alias="DOCS_URL")
    redoc_url: Optional[str] = Field(default="/redoc", validation_alias="REDOC_URL")

    # Performance settings
    max_request_size: int = Field(default=16 * 1024 * 1024, validation_alias="MAX_REQUEST_SIZE")  # 16MB
    request_timeout: int = Field(default=30, validation_alias="REQUEST_TIMEOUT")

    # WebSocket settings
    websocket_heartbeat_interval: int = Field(default=30, validation_alias="WS_HEARTBEAT_INTERVAL")
    websocket_max_connections: int = Field(default=100, validation_alias="WS_MAX_CONNECTIONS")
    
    # Component settings
    mqtt: MQTTSettings = Field(default_factory=MQTTSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    google_maps: GoogleMapsSettings = Field(default_factory=GoogleMapsSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    
    class Config:
        # Use absolute path to project root .env so systemd WorkingDirectory doesn't affect loading
        env_file = str(Path(__file__).resolve().parent.parent.parent / ".env")
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


def get_mqtt_settings() -> MQTTSettings:
    """Get MQTT settings"""
    return get_settings().mqtt


def get_auth_settings() -> AuthSettings:
    """Get authentication settings"""
    return get_settings().auth


def get_redis_settings() -> RedisSettings:
    """Get Redis settings"""
    return get_settings().redis


def get_database_settings() -> DatabaseSettings:
    """Get database settings"""
    return get_settings().database


def get_rate_limit_settings() -> RateLimitSettings:
    """Get rate limiting settings"""
    return get_settings().rate_limit
