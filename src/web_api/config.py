"""
Configuration Management
Settings and configuration for the web API backend using Pydantic.
"""

from functools import lru_cache
from typing import List, Optional, Dict, Any
from pydantic import BaseSettings, Field
import os


class MQTTSettings(BaseSettings):
    """MQTT connection settings"""
    broker_host: str = Field(default="localhost", env="MQTT_BROKER_HOST")
    broker_port: int = Field(default=1883, env="MQTT_BROKER_PORT")
    client_id: str = Field(default="web_api_backend", env="MQTT_CLIENT_ID")
    keepalive: int = Field(default=60, env="MQTT_KEEPALIVE")
    reconnect_delay: int = Field(default=5, env="MQTT_RECONNECT_DELAY")
    max_reconnect_delay: int = Field(default=300, env="MQTT_MAX_RECONNECT_DELAY")
    message_timeout: int = Field(default=30, env="MQTT_MESSAGE_TIMEOUT")
    
    # Authentication
    username: Optional[str] = Field(default=None, env="MQTT_USERNAME")
    password: Optional[str] = Field(default=None, env="MQTT_PASSWORD")
    
    # TLS
    use_tls: bool = Field(default=False, env="MQTT_USE_TLS")
    ca_certs: Optional[str] = Field(default=None, env="MQTT_CA_CERTS")
    cert_file: Optional[str] = Field(default=None, env="MQTT_CERT_FILE")
    key_file: Optional[str] = Field(default=None, env="MQTT_KEY_FILE")
    
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
        if not self.jwt_secret_key:
            raise ValueError("Missing required environment variable: JWT_SECRET_KEY. Please set this in your .env file.")
        if not self.admin_password:
            raise ValueError("Missing required environment variable: ADMIN_PASSWORD. Please set this in your .env file.")
    
    class Config:
        env_prefix = "AUTH_"


class RedisSettings(BaseSettings):
    """Redis cache settings"""
    host: str = Field(default="localhost", env="REDIS_HOST")
    port: int = Field(default=6379, env="REDIS_PORT")
    db: int = Field(default=0, env="REDIS_DB")
    password: Optional[str] = Field(default=None, env="REDIS_PASSWORD")
    
    # Connection pool settings
    max_connections: int = Field(default=20, env="REDIS_MAX_CONNECTIONS")
    retry_on_timeout: bool = Field(default=True, env="REDIS_RETRY_ON_TIMEOUT")
    
    # Cache TTL settings (seconds)
    default_ttl: int = Field(default=300, env="REDIS_DEFAULT_TTL")
    sensor_data_ttl: int = Field(default=60, env="REDIS_SENSOR_DATA_TTL")
    config_ttl: int = Field(default=3600, env="REDIS_CONFIG_TTL")
    
    class Config:
        env_prefix = "REDIS_"


class DatabaseSettings(BaseSettings):
    """Database settings"""
    url: str = Field(default="sqlite:///lawnberry.db", env="DATABASE_URL")
    echo: bool = Field(default=False, env="DATABASE_ECHO")
    pool_size: int = Field(default=5, env="DATABASE_POOL_SIZE")
    max_overflow: int = Field(default=10, env="DATABASE_MAX_OVERFLOW")
    
    class Config:
        env_prefix = "DATABASE_"


class RateLimitSettings(BaseSettings):
    """Rate limiting settings"""
    enabled: bool = Field(default=True, env="RATE_LIMIT_ENABLED")
    default_requests_per_minute: int = Field(default=100, env="RATE_LIMIT_DEFAULT_RPM")
    burst_multiplier: float = Field(default=1.5, env="RATE_LIMIT_BURST_MULTIPLIER")
    
    # Per-endpoint limits
    sensor_data_rpm: int = Field(default=200, env="RATE_LIMIT_SENSOR_DATA_RPM")
    navigation_rpm: int = Field(default=60, env="RATE_LIMIT_NAVIGATION_RPM")
    configuration_rpm: int = Field(default=30, env="RATE_LIMIT_CONFIG_RPM")
    
    class Config:
        env_prefix = "RATE_LIMIT_"


class Settings(BaseSettings):
    """Main application settings"""
    # Application settings
    app_name: str = Field(default="Lawnberry Web API", env="APP_NAME")
    debug: bool = Field(default=False, env="DEBUG")
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    # CORS settings
    cors_origins: List[str] = Field(default=["*"], env="CORS_ORIGINS")
    
    # API settings
    api_prefix: str = Field(default="/api/v1", env="API_PREFIX")
    docs_url: Optional[str] = Field(default="/docs", env="DOCS_URL")
    redoc_url: Optional[str] = Field(default="/redoc", env="REDOC_URL")
    
    # Performance settings
    max_request_size: int = Field(default=16 * 1024 * 1024, env="MAX_REQUEST_SIZE")  # 16MB
    request_timeout: int = Field(default=30, env="REQUEST_TIMEOUT")
    
    # WebSocket settings
    websocket_heartbeat_interval: int = Field(default=30, env="WS_HEARTBEAT_INTERVAL")
    websocket_max_connections: int = Field(default=100, env="WS_MAX_CONNECTIONS")
    
    # Component settings
    mqtt: MQTTSettings = Field(default_factory=MQTTSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


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
