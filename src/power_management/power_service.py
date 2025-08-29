"""
Power Management Service
MQTT-based service for power management coordination.
"""

import asyncio
import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime

from ..communication.client import MQTTClient
from ..data_management.cache_manager import CacheManager
from ..hardware.hardware_interface import HardwareInterface
from ..weather.weather_service import WeatherService
from .power_manager import PowerManager


class PowerService:
    """MQTT-based power management service"""
    
    def __init__(self, 
                 mqtt_client: MQTTClient,
                 cache_manager: CacheManager,
                 hardware_interface: HardwareInterface,
                 weather_service: Optional[WeatherService] = None):
        
        self.logger = logging.getLogger(__name__)
        self.mqtt = mqtt_client
        self.cache = cache_manager
        self.hardware = hardware_interface
        self.weather = weather_service
        
        # Initialize power manager
        self.power_manager = PowerManager(
            hardware_interface=hardware_interface,
            mqtt_client=mqtt_client,
            cache_manager=cache_manager,
            weather_service=weather_service
        )
        
        self._initialized = False
        self._shutdown_event = asyncio.Event()
        self._service_task: Optional[asyncio.Task] = None
    
    async def initialize(self) -> bool:
        """Initialize the power service"""
        if self._initialized:
            return True
        
        try:
            self.logger.info("Initializing power management service...")
            
            # Initialize power manager
            if not await self.power_manager.initialize():
                self.logger.error("Failed to initialize power manager")
                return False
            
            # Start service task
            self._service_task = asyncio.create_task(self._service_loop())
            
            # Setup additional MQTT subscriptions
            await self._setup_service_subscriptions()
            
            self._initialized = True
            self.logger.info("Power management service initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize power service: {e}")
            return False
    
    async def shutdown(self):
        """Gracefully shutdown the power service"""
        self.logger.info("Shutting down power management service...")
        self._shutdown_event.set()
        
        # Cancel service task
        if self._service_task and not self._service_task.done():
            self._service_task.cancel()
            try:
                await self._service_task
            except asyncio.CancelledError:
                pass
        
        # Shutdown power manager
        await self.power_manager.shutdown()
        
        self.logger.info("Power management service shutdown complete")
    
    async def _service_loop(self):
        """Main service loop for health monitoring and status reporting"""
        while not self._shutdown_event.is_set():
            try:
                # Publish service health status
                await self._publish_service_health()
                
                # Check for any critical power conditions
                await self._check_critical_conditions()
                
                # Update service metrics
                await self._update_service_metrics()
                
                await asyncio.sleep(10.0)  # Service health check every 10 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in power service loop: {e}")
                await asyncio.sleep(10.0)
    
    async def _setup_service_subscriptions(self):
        """Setup additional MQTT subscriptions for service coordination"""
        try:
            # Subscribe using standardized API, then attach handlers
            subs = [
                ("lawnberry/commands/system", self._wrap_protocol_handler(self._handle_system_command)),
                ("lawnberry/system/health_check", self._wrap_protocol_handler(self._handle_health_check)),
                ("lawnberry/config/power", self._wrap_protocol_handler(self._handle_config_update)),
            ]
            for topic, handler in subs:
                await self.mqtt.subscribe(topic)
                self.mqtt.add_message_handler(topic, handler)
            
        except Exception as e:
            self.logger.error(f"Error setting up service subscriptions: {e}")

    def _wrap_protocol_handler(self, func):
        """Wrap legacy (topic, payload) handlers to accept MessageProtocol."""
        async def _wrapped(topic: str, message):
            try:
                payload = message.payload if hasattr(message, 'payload') else message
                await func(topic, payload)
            except Exception as e:
                self.logger.error(f"Wrapped handler error for {func.__name__}: {e}")
        return _wrapped
    
    async def _handle_system_command(self, topic: str, payload: Dict[str, Any]):
        """Handle system-level commands"""
        try:
            command = payload.get('command')
            
            if command == "shutdown":
                self.logger.info("Received system shutdown command")
                await self.shutdown()
            
            elif command == "restart_power_service":
                self.logger.info("Received power service restart command")
                await self.shutdown()
                await asyncio.sleep(2.0)
                await self.initialize()
            
            elif command == "get_power_status":
                status = await self.power_manager.get_power_status()
                await self.mqtt.publish("lawnberry/responses/system", {
                    "command": command,
                    "status": "success",
                    "data": status,
                    "timestamp": datetime.now().isoformat()
                })
            
        except Exception as e:
            self.logger.error(f"Error handling system command: {e}")
    
    async def _handle_health_check(self, topic: str, payload: Dict[str, Any]):
        """Handle health check requests"""
        try:
            service_name = payload.get('service')
            
            if service_name == "power_service" or service_name == "all":
                health_status = await self._get_health_status()
                
                await self.mqtt.publish("lawnberry/system/health_response", {
                    "service": "power_service",
                    "status": health_status,
                    "timestamp": datetime.now().isoformat()
                })
            
        except Exception as e:
            self.logger.error(f"Error handling health check: {e}")
    
    async def _handle_config_update(self, topic: str, payload: Dict[str, Any]):
        """Handle power configuration updates"""
        try:
            config_type = payload.get('type')
            config_data = payload.get('data', {})
            
            if config_type == "thresholds":
                # Update battery thresholds
                if 'critical_level' in config_data:
                    self.power_manager.CRITICAL_BATTERY_LEVEL = config_data['critical_level']
                if 'low_level' in config_data:
                    self.power_manager.LOW_BATTERY_LEVEL = config_data['low_level']
                if 'optimal_level' in config_data:
                    self.power_manager.OPTIMAL_BATTERY_LEVEL = config_data['optimal_level']
                
                self.logger.info(f"Updated power thresholds: {config_data}")
            
            elif config_type == "charging":
                # Update charging parameters
                if 'mode' in config_data:
                    await self.power_manager.set_charging_mode(config_data['mode'])
                
                self.logger.info(f"Updated charging configuration: {config_data}")
            
        except Exception as e:
            self.logger.error(f"Error handling config update: {e}")
    
    async def _publish_service_health(self):
        """Publish service health status"""
        try:
            health_status = await self._get_health_status()
            
            await self.mqtt.publish("lawnberry/system/service_health", {
                "service": "power_service",
                "status": health_status,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            self.logger.error(f"Error publishing service health: {e}")
    
    async def _get_health_status(self) -> Dict[str, Any]:
        """Get current service health status"""
        try:
            # Check if power manager is running
            power_manager_healthy = (
                self.power_manager._initialized and
                not self.power_manager._shutdown_event.is_set()
            )
            
            # Check if we're getting fresh power data
            power_status = await self.power_manager.get_power_status()
            data_fresh = True  # Would check timestamp in real implementation
            
            # Check MQTT connectivity
            mqtt_connected = self.mqtt.is_connected() if hasattr(self.mqtt, 'is_connected') else True
            
            # Overall health assessment
            overall_healthy = power_manager_healthy and data_fresh and mqtt_connected
            
            return {
                "healthy": overall_healthy,
                "components": {
                    "power_manager": power_manager_healthy,
                    "data_freshness": data_fresh,
                    "mqtt_connection": mqtt_connected
                },
                "metrics": {
                    "battery_soc": power_status["battery"]["state_of_charge"],
                    "solar_power": power_status["solar"]["power"],
                    "power_mode": power_status["mode"],
                    "sunny_spots_count": power_status["sunny_spots_count"]
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error getting health status: {e}")
            return {
                "healthy": False,
                "error": str(e),
                "components": {},
                "metrics": {}
            }
    
    async def _check_critical_conditions(self):
        """Check for critical power conditions and alert other services"""
        try:
            power_status = await self.power_manager.get_power_status()
            battery = power_status["battery"]
            
            # Critical battery level
            if battery["state_of_charge"] <= 0.05:  # 5%
                await self.mqtt.publish("lawnberry/alerts/critical", {
                    "type": "battery_critical",
                    "level": "critical",
                    "message": f"Battery critically low: {battery['state_of_charge']:.1%}",
                    "data": {
                        "battery_soc": battery["state_of_charge"],
                        "voltage": battery["voltage"],
                        "time_remaining": battery["time_remaining"]
                    },
                    "timestamp": datetime.now().isoformat()
                })
            
            # High temperature warning
            if battery.get("temperature") and battery["temperature"] > 50.0:
                await self.mqtt.publish("lawnberry/alerts/warning", {
                    "type": "battery_temperature_high",
                    "level": "warning",
                    "message": f"Battery temperature high: {battery['temperature']:.1f}°C",
                    "data": {
                        "temperature": battery["temperature"],
                        "battery_soc": battery["state_of_charge"]
                    },
                    "timestamp": datetime.now().isoformat()
                })
            
            # Solar charging failure (during daylight hours)
            current_hour = datetime.now().hour
            if (6 <= current_hour <= 18 and 
                power_status["solar"]["power"] < 1.0 and 
                battery["state_of_charge"] < 0.5):
                
                await self.mqtt.publish("lawnberry/alerts/warning", {
                    "type": "solar_charging_low",
                    "level": "warning",
                    "message": "Solar charging is very low during daylight hours",
                    "data": {
                        "solar_power": power_status["solar"]["power"],
                        "battery_soc": battery["state_of_charge"],
                        "hour": current_hour
                    },
                    "timestamp": datetime.now().isoformat()
                })
            
        except Exception as e:
            self.logger.error(f"Error checking critical conditions: {e}")
    
    async def _update_service_metrics(self):
        """Update service-specific metrics"""
        try:
            power_status = await self.power_manager.get_power_status()
            
            # Store service metrics in cache
            service_metrics = {
                "service_name": "power_service",
                "uptime_seconds": 0,  # Would track actual uptime
                "power_status": power_status,
                "last_updated": datetime.now().isoformat()
            }
            
            await self.cache.set("service:power:metrics", service_metrics, ttl=60)
            
        except Exception as e:
            self.logger.error(f"Error updating service metrics: {e}")
    
    # Public service API methods
    
    async def get_service_info(self) -> Dict[str, Any]:
        """Get service information"""
        return {
            "service_name": "power_service",
            "version": "1.0.0",
            "description": "Comprehensive power management service",
            "initialized": self._initialized,
            "health": await self._get_health_status()
        }
    
    async def get_power_status(self) -> Dict[str, Any]:
        """Get current power status (proxy to power manager)"""
        return await self.power_manager.get_power_status()
    
    async def set_charging_mode(self, mode: str) -> bool:
        """Set charging mode (proxy to power manager)"""
        return await self.power_manager.set_charging_mode(mode)
    
    async def enable_power_saving(self, enabled: bool):
        """Enable power saving mode (proxy to power manager)"""
        await self.power_manager.enable_power_saving(enabled)
    
    async def get_sunny_spots(self) -> List[Dict[str, Any]]:
        """Get sunny spots data (proxy to power manager)"""
        return await self.power_manager.get_sunny_spots()
    
    async def navigate_to_best_sunny_spot(self) -> bool:
        """Navigate to best sunny spot (proxy to power manager)"""
        return await self.power_manager.force_navigate_to_best_sunny_spot()
