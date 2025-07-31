"""
Location Coordinator Service for LawnBerry Pi Autonomous Mower
Provides centralized GPS coordinate management with hardware prioritization and config fallback
"""

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import yaml
from pathlib import Path

from ..hardware.data_structures import GPSReading
from ..communication import MQTTClient, MessageProtocol, SensorData


logger = logging.getLogger(__name__)


class LocationSource(Enum):
    """Location data source types"""
    GPS_HARDWARE = "gps_hardware"
    CONFIG_FALLBACK = "config_fallback"
    UNKNOWN = "unknown"


@dataclass
class LocationData:
    """Standardized location data structure"""
    latitude: float
    longitude: float
    altitude: float = 0.0
    accuracy: float = 0.0
    source: LocationSource = LocationSource.UNKNOWN
    timestamp: Optional[datetime] = None
    satellites: int = 0
    fix_type: str = "none"
    health_status: str = "unknown"
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "accuracy": self.accuracy,
            "source": self.source.value,
            "timestamp": self.timestamp.isoformat() if self.timestamp else datetime.now().isoformat(),
            "satellites": self.satellites,
            "fix_type": self.fix_type,
            "health_status": self.health_status
        }


@dataclass
class GPSHealthStatus:
    """GPS hardware health monitoring"""
    is_available: bool = False
    last_update: Optional[datetime] = None
    satellite_count: int = 0
    fix_quality: str = "none"
    accuracy_meters: float = 999.0
    consecutive_failures: int = 0
    total_readings: int = 0
    
    @property
    def is_healthy(self) -> bool:
        """Check if GPS is considered healthy"""
        if not self.is_available:
            return False
        
        if self.last_update is None:
            return False
            
        # Check if data is recent (within 10 seconds)
        time_since_update = datetime.now() - self.last_update
        if time_since_update > timedelta(seconds=10):
            return False
            
        # Check fix quality
        if self.fix_quality in ['none', 'invalid']:
            return False
            
        # Check accuracy
        if self.accuracy_meters > 10.0:  # 10 meter threshold
            return False
            
        return True


class LocationCoordinator:
    """
    Centralized location coordinator that manages GPS coordinates from hardware
    and provides automatic fallback to configuration coordinates when GPS is unavailable
    """
    
    def __init__(self, mqtt_client: MQTTClient, config_path: Optional[str] = None):
        self.mqtt_client = mqtt_client
        self.config_path = Path(config_path) if config_path else Path("config/weather.yaml")
        
        # Current location state
        self._current_location: Optional[LocationData] = None
        self._fallback_location: Optional[LocationData] = None
        
        # GPS health monitoring
        self._gps_health = GPSHealthStatus()
        
        # Configuration
        self.config = self._load_config()
        
        # Subscriber callbacks
        self._location_callbacks: Dict[str, Callable[[LocationData], None]] = {}
        
        # Tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._publishing_task: Optional[asyncio.Task] = None
        self._running = False
        
        # GPS data timeout settings
        self.gps_timeout_seconds = 10
        self.health_check_interval = 5  # seconds
        self.publish_interval = 1  # seconds
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration with fallback coordinates"""
        default_config = {
            'location': {
                'latitude': 40.7128,   # Default NYC coordinates
                'longitude': -74.0060
            }
        }
        
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    return {**default_config, **config}
        except Exception as e:
            logger.warning(f"Failed to load config from {self.config_path}: {e}")
        
        return default_config
    
    def _load_fallback_location(self) -> LocationData:
        """Load fallback location from configuration"""
        location_config = self.config.get('location', {})
        
        return LocationData(
            latitude=location_config.get('latitude', 40.7128),
            longitude=location_config.get('longitude', -74.0060),
            altitude=0.0,
            accuracy=999.0,  # Low accuracy for config fallback
            source=LocationSource.CONFIG_FALLBACK,
            timestamp=datetime.now(),
            satellites=0,
            fix_type="config",
            health_status="config_fallback"
        )
    
    async def start(self):
        """Start the location coordinator service"""
        logger.info("Starting location coordinator service")
        self._running = True
        
        # Load fallback location from config
        self._fallback_location = self._load_fallback_location()
        self._current_location = self._fallback_location
        
        # Subscribe to GPS data
        await self._subscribe_to_gps()
        
        # Start monitoring and publishing tasks
        self._monitoring_task = asyncio.create_task(self._gps_health_monitor())
        self._publishing_task = asyncio.create_task(self._location_publisher())
        
        logger.info(f"Location coordinator started with fallback: {self._fallback_location.latitude:.6f}, {self._fallback_location.longitude:.6f}")
    
    async def stop(self):
        """Stop the location coordinator service"""
        logger.info("Stopping location coordinator service")
        self._running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        if self._publishing_task:
            self._publishing_task.cancel()
            try:
                await self._publishing_task
            except asyncio.CancelledError:
                pass
    
    async def _subscribe_to_gps(self):
        """Subscribe to GPS sensor data"""
        try:
            await self.mqtt_client.subscribe(
                "sensors/gps/data",
                self._handle_gps_data,
                qos=1
            )
            logger.info("Subscribed to GPS sensor data")
        except Exception as e:
            logger.error(f"Failed to subscribe to GPS data: {e}")
    
    async def _handle_gps_data(self, topic: str, message: Dict[str, Any]):
        """Handle incoming GPS data from hardware"""
        try:
            gps_data = message.get('value', {})
            
            # Update GPS health status
            self._gps_health.is_available = True
            self._gps_health.last_update = datetime.now()
            self._gps_health.satellite_count = gps_data.get('satellites', 0)
            self._gps_health.fix_quality = gps_data.get('fix_type', 'none')
            self._gps_health.accuracy_meters = gps_data.get('accuracy', 999.0)
            self._gps_health.total_readings += 1
            self._gps_health.consecutive_failures = 0
            
            # Create location data from GPS
            gps_location = LocationData(
                latitude=gps_data.get('latitude', 0.0),
                longitude=gps_data.get('longitude', 0.0),
                altitude=gps_data.get('altitude', 0.0),
                accuracy=gps_data.get('accuracy', 999.0),
                source=LocationSource.GPS_HARDWARE,
                timestamp=datetime.fromisoformat(message.get('timestamp', datetime.now().isoformat())),
                satellites=gps_data.get('satellites', 0),
                fix_type=gps_data.get('fix_type', 'none'),
                health_status="healthy" if self._gps_health.is_healthy else "degraded"
            )
            
            # Validate GPS coordinates
            if self._validate_coordinates(gps_location.latitude, gps_location.longitude):
                self._current_location = gps_location
                logger.debug(f"Updated location from GPS: {gps_location.latitude:.6f}, {gps_location.longitude:.6f}")
            else:
                logger.warning(f"Invalid GPS coordinates received: {gps_location.latitude}, {gps_location.longitude}")
                self._gps_health.consecutive_failures += 1
                
        except Exception as e:
            logger.error(f"Error processing GPS data: {e}")
            self._gps_health.consecutive_failures += 1
    
    def _validate_coordinates(self, latitude: float, longitude: float) -> bool:
        """Validate coordinate ranges and format"""
        # Check latitude range
        if not (-90.0 <= latitude <= 90.0):
            return False
        
        # Check longitude range
        if not (-180.0 <= longitude <= 180.0):
            return False
        
        # Check for invalid zero coordinates (common GPS error)
        if latitude == 0.0 and longitude == 0.0:
            return False
        
        return True
    
    async def _gps_health_monitor(self):
        """Monitor GPS health and switch to fallback when needed"""
        while self._running:
            try:
                # Check if GPS data is stale
                if (self._gps_health.last_update and 
                    datetime.now() - self._gps_health.last_update > timedelta(seconds=self.gps_timeout_seconds)):
                    self._gps_health.is_available = False
                
                # Switch to fallback if GPS is unhealthy
                if not self._gps_health.is_healthy and self._current_location.source == LocationSource.GPS_HARDWARE:
                    logger.warning("GPS unhealthy, switching to config fallback")
                    self._current_location = self._fallback_location
                
                # Update health status
                if self._current_location:
                    if self._gps_health.is_healthy:
                        self._current_location.health_status = "healthy"
                    elif self._gps_health.is_available:
                        self._current_location.health_status = "degraded"
                    else:
                        self._current_location.health_status = "unavailable"
                
                await asyncio.sleep(self.health_check_interval)
                
            except Exception as e:
                logger.error(f"Error in GPS health monitoring: {e}")
                await asyncio.sleep(self.health_check_interval)
    
    async def _location_publisher(self):
        """Publish current location data to MQTT"""
        while self._running:
            try:
                if self._current_location:
                    # Notify callbacks
                    for callback_id, callback in self._location_callbacks.items():
                        try:
                            callback(self._current_location)
                        except Exception as e:
                            logger.error(f"Error in location callback {callback_id}: {e}")
                    
                    # Publish to MQTT
                    await self.mqtt_client.publish_message(
                        "location/current",
                        self._current_location.to_dict(),
                        qos=1
                    )
                
                await asyncio.sleep(self.publish_interval)
                
            except Exception as e:
                logger.error(f"Error publishing location data: {e}")
                await asyncio.sleep(self.publish_interval)
    
    def get_current_location(self) -> Optional[LocationData]:
        """Get current location data"""
        return self._current_location
    
    def get_current_coordinates(self) -> Tuple[float, float]:
        """Get current coordinates as (latitude, longitude) tuple"""
        if self._current_location:
            return (self._current_location.latitude, self._current_location.longitude)
        return (0.0, 0.0)
    
    def get_gps_health(self) -> GPSHealthStatus:
        """Get GPS health status"""
        return self._gps_health
    
    def register_location_callback(self, callback_id: str, callback: Callable[[LocationData], None]):
        """Register callback for location updates"""
        self._location_callbacks[callback_id] = callback
        logger.info(f"Registered location callback: {callback_id}")
    
    def unregister_location_callback(self, callback_id: str):
        """Unregister location callback"""
        if callback_id in self._location_callbacks:
            del self._location_callbacks[callback_id]
            logger.info(f"Unregistered location callback: {callback_id}")
    
    async def update_fallback_coordinates(self, latitude: float, longitude: float):
        """Update fallback coordinates and save to config"""
        if not self._validate_coordinates(latitude, longitude):
            raise ValueError(f"Invalid coordinates: {latitude}, {longitude}")
        
        # Update in-memory fallback
        self._fallback_location = LocationData(
            latitude=latitude,
            longitude=longitude,
            altitude=0.0,
            accuracy=999.0,
            source=LocationSource.CONFIG_FALLBACK,
            timestamp=datetime.now(),
            satellites=0,
            fix_type="config",
            health_status="config_fallback"
        )
        
        # Update config file
        self.config['location']['latitude'] = latitude
        self.config['location']['longitude'] = longitude
        
        try:
            with open(self.config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False)
            logger.info(f"Updated fallback coordinates: {latitude:.6f}, {longitude:.6f}")
        except Exception as e:
            logger.error(f"Failed to save updated coordinates to config: {e}")
        
        # If currently using fallback, update current location
        if self._current_location and self._current_location.source == LocationSource.CONFIG_FALLBACK:
            self._current_location = self._fallback_location
