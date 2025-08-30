#!/usr/bin/env python3
"""
Safety System Main Entry Point
Production entry point for the comprehensive safety monitoring system
"""

import asyncio
import logging
import signal
import sys
import yaml
from pathlib import Path
from datetime import datetime
from typing import Optional

from ..communication import MQTTClient
from ..communication.message_protocols import StatusMessage, SensorData
from .safety_service import SafetyService, SafetyConfig
from ..data_management import DataManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/var/log/lawnberry/safety.log')
    ]
)

logger = logging.getLogger(__name__)


class SafetySystemMain:
    """Main safety system service runner"""
    
    def __init__(self):
        self.safety_service: Optional[SafetyService] = None
        self.mqtt_client: Optional[MQTTClient] = None
        self.data_manager: Optional[DataManager] = None
        self.running = False
        self.shutdown_event = asyncio.Event()
        self._heartbeat_task: Optional[asyncio.Task] = None
        
    async def initialize(self):
        """Initialize the safety system"""
        try:
            logger.info("Initializing Lawnberry Safety Monitoring System")
            
            # Load configuration
            config = self._load_configuration()
            
            # Initialize data manager
            self.data_manager = DataManager()
            await self.data_manager.start()
            
            # Initialize MQTT client with explicit client_id and config
            import socket
            host = "unknown"
            try:
                host = socket.gethostname()
            except Exception:
                pass
            client_id = f"lawnberry-safety-{host}"
            self.mqtt_client = MQTTClient(
                client_id=client_id,
                config={
                    'broker_host': 'localhost',
                    'broker_port': 1883,
                    'keepalive': 60,
                    'clean_session': True,
                    'reconnect_delay': 5,
                    'max_reconnect_delay': 300,
                    'reconnect_backoff': 2.0,
                    'message_timeout': 30,
                    'auth': {
                        'enabled': False,
                        'username': None,
                        'password': None
                    },
                    'tls': {
                        'enabled': False,
                        'ca_certs': None,
                        'certfile': None,
                        'keyfile': None
                    }
                }
            )
            initialized = await self.mqtt_client.initialize()
            if not initialized:
                raise RuntimeError("MQTT client initialization failed")
            
            # Initialize safety service
            self.safety_service = SafetyService(self.mqtt_client, config)
            
            # Set up signal handlers
            self._setup_signal_handlers()
            
            logger.info("Safety system initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize safety system: {e}")
            raise
    
    def _load_configuration(self) -> SafetyConfig:
        """Load safety configuration from file"""
        try:
            config_path = Path(__file__).parent.parent.parent / 'config' / 'safety.yaml'
            
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            
            # Extract safety parameters
            safety_params = config_data['safety']
            
            # Create SafetyConfig object
            config = SafetyConfig(
                emergency_response_time_ms=safety_params['emergency_response_time_ms'],
                safety_update_rate_hz=safety_params['safety_update_rate_hz'],
                emergency_update_rate_hz=safety_params['emergency_update_rate_hz'],
                status_publish_rate_hz=safety_params.get('status_publish_rate_hz', 2),
                heartbeat_timeout_s=safety_params.get('heartbeat_timeout_s', 15.0),
                person_safety_radius_m=safety_params['person_safety_radius_m'],
                pet_safety_radius_m=safety_params['pet_safety_radius_m'],
                general_safety_distance_m=safety_params['general_safety_distance_m'],
                emergency_stop_distance_m=safety_params['emergency_stop_distance_m'],
                max_safe_tilt_deg=safety_params['max_safe_tilt_deg'],
                critical_tilt_deg=safety_params['critical_tilt_deg'],
                min_operating_temp_c=safety_params['min_operating_temp_c'],
                max_operating_temp_c=safety_params['max_operating_temp_c'],
                boundary_safety_margin_m=safety_params['boundary_safety_margin_m'],
                enable_weather_safety=safety_params['enable_weather_safety'],
                enable_vision_safety=safety_params['enable_vision_safety'],
                enable_boundary_enforcement=safety_params['enable_boundary_enforcement']
            )
            # Optional maintenance warmup config
            try:
                maint = config_data.get('maintenance', {}) or {}
                if 'startup_grace_seconds' in maint:
                    config.maintenance_startup_grace_seconds = float(maint['startup_grace_seconds'])
                if 'allow_missing_data_during_warmup' in maint:
                    config.maintenance_allow_missing_data_during_warmup = bool(maint['allow_missing_data_during_warmup'])
            except Exception:
                pass
            
            logger.info(f"Configuration loaded: {config}")
            return config
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            # Return default configuration as fallback
            return SafetyConfig()
    
    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown")
            asyncio.create_task(self._shutdown())
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGHUP, signal_handler)
    
    async def run(self):
        """Run the safety system"""
        try:
            logger.info("Starting Lawnberry Safety Monitoring System")
            self.running = True
            
            # Start safety service
            await self.safety_service.start()
            
            # Publish startup status
            await self._publish_startup_status()
            
            # Set up health monitoring
            health_task = asyncio.create_task(self._health_monitoring_loop())
            
            # Set up performance monitoring
            performance_task = asyncio.create_task(self._performance_monitoring_loop())

            # Start system heartbeat publisher to satisfy emergency controller watchdog
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            logger.info("Safety system is running")
            
            # Wait for shutdown signal
            await self.shutdown_event.wait()
            
            # Cancel monitoring tasks
            health_task.cancel()
            performance_task.cancel()
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
            
            try:
                await health_task
            except asyncio.CancelledError:
                pass
            
            try:
                await performance_task
            except asyncio.CancelledError:
                pass
            
        except Exception as e:
            logger.error(f"Error running safety system: {e}")
            raise
        finally:
            await self._cleanup()

    async def _heartbeat_loop(self):
        """Publish a periodic system heartbeat for watchdogs."""
        try:
            interval = 2.0  # seconds
            while self.running and self.mqtt_client:
                try:
                    msg = StatusMessage.create(
                        sender="safety_system",
                        status="healthy",
                        details={"component": "safety_system", "heartbeat": True}
                    )
                    # EmergencyController listens on this topic to reset its watchdog timer
                    await self.mqtt_client.publish("lawnberry/system/heartbeat", msg)
                except Exception as e:
                    logger.error(f"Heartbeat publish error: {e}")
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            pass
    
    async def _publish_startup_status(self):
        """Publish safety system startup status"""
        try:
            startup_status = {
                'timestamp': datetime.now().isoformat(),
                'service': 'safety_system',
                'status': 'started',
                'version': '1.0.0',
                'configuration': {
                    'emergency_response_time_ms': self.safety_service.config.emergency_response_time_ms,
                    'safety_update_rate_hz': self.safety_service.config.safety_update_rate_hz,
                    'features_enabled': {
                        'weather_safety': self.safety_service.config.enable_weather_safety,
                        'vision_safety': self.safety_service.config.enable_vision_safety,
                        'boundary_enforcement': self.safety_service.config.enable_boundary_enforcement
                    }
                }
            }
            
            from ..communication.message_protocols import SensorData
            message = SensorData.create(
                sender="safety_system",
                sensor_type="service_status",
                data=startup_status
            )
            
            await self.mqtt_client.publish("lawnberry/system/safety/status", message)
            logger.info("Startup status published")
            
        except Exception as e:
            logger.error(f"Failed to publish startup status: {e}")
    
    async def _health_monitoring_loop(self):
        """Monitor safety system health"""
        while self.running:
            try:
                # Collect health metrics
                health_status = await self._collect_health_metrics()
                
                # Publish health status
                await self._publish_health_status(health_status)
                
                # Check for critical health issues
                if not health_status['overall_healthy']:
                    logger.warning("Safety system health issues detected")
                    await self._handle_health_issues(health_status)
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Error in health monitoring: {e}")
                await asyncio.sleep(10)
    
    async def _performance_monitoring_loop(self):
        """Monitor safety system performance"""
        while self.running:
            try:
                # Collect performance metrics
                if self.safety_service:
                    metrics = await self.safety_service.get_safety_metrics()
                    
                    # Log performance summary
                    performance = metrics.get('performance', {})
                    avg_response_time = performance.get('average_response_time_ms', 0)
                    target_response_time = performance.get('target_response_time_ms', 100)
                    
                    if avg_response_time > target_response_time * 1.2:  # 20% over target
                        logger.warning(f"Safety response time degraded: {avg_response_time:.1f}ms (target: {target_response_time}ms)")
                    
                    # Check safety events
                    safety_events = metrics.get('safety_events', {})
                    if safety_events.get('emergency_stops', 0) > 0:
                        logger.info(f"Safety events summary: {safety_events}")
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in performance monitoring: {e}")
                await asyncio.sleep(60)
    
    async def _collect_health_metrics(self) -> dict:
        """Collect comprehensive health metrics"""
        try:
            health_status = {
                'timestamp': datetime.now().isoformat(),
                'overall_healthy': True,
                'components': {},
                'system_metrics': {}
            }
            
            if self.safety_service:
                # Check safety service health
                safety_status = self.safety_service._current_safety_status
                if safety_status:
                    health_status['components']['safety_service'] = {
                        'healthy': safety_status.get('overall_safe', True),
                        'active_alerts': len(safety_status.get('active_alerts', [])),
                        'running': self.safety_service._running
                    }
                
                # Check component health
                if hasattr(self.safety_service, 'emergency_controller'):
                    controller_status = self.safety_service.emergency_controller.get_current_status()
                    health_status['components']['emergency_controller'] = {
                        'healthy': not controller_status.get('emergency_active', False),
                        'failed_responses': controller_status.get('failed_responses', 0),
                        'last_response_time_ms': controller_status.get('last_response_time_ms', 0)
                    }
            
            # Check MQTT connection
            if self.mqtt_client:
                health_status['components']['mqtt_client'] = {
                    'healthy': self.mqtt_client.is_connected(),
                    'connected': self.mqtt_client.is_connected()
                }
            
            # Determine overall health
            component_health = [comp.get('healthy', False) for comp in health_status['components'].values()]
            health_status['overall_healthy'] = all(component_health) if component_health else False
            
            return health_status
            
        except Exception as e:
            logger.error(f"Error collecting health metrics: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'overall_healthy': False,
                'error': str(e)
            }
    
    async def _publish_health_status(self, health_status: dict):
        """Publish health status"""
        try:
            from ..communication.message_protocols import SensorData
            message = SensorData.create(
                sender="safety_system",
                sensor_type="health_status",
                data=health_status
            )
            
            await self.mqtt_client.publish("lawnberry/system/safety/health", message)
            
        except Exception as e:
            logger.error(f"Failed to publish health status: {e}")
    
    async def _handle_health_issues(self, health_status: dict):
        """Handle detected health issues"""
        try:
            # Log detailed health issues
            unhealthy_components = [
                name for name, status in health_status.get('components', {}).items()
                if not status.get('healthy', False)
            ]
            
            logger.warning(f"Unhealthy components: {unhealthy_components}")
            
            # Attempt recovery actions for specific issues
            for component_name, component_status in health_status.get('components', {}).items():
                if not component_status.get('healthy', False):
                    await self._attempt_component_recovery(component_name, component_status)
            
        except Exception as e:
            logger.error(f"Error handling health issues: {e}")
    
    async def _attempt_component_recovery(self, component_name: str, component_status: dict):
        """Attempt to recover a specific component"""
        try:
            logger.info(f"Attempting recovery for component: {component_name}")
            
            if component_name == 'mqtt_client' and not component_status.get('connected', False):
                # Attempt MQTT reconnection
                if self.mqtt_client:
                    await self.mqtt_client.disconnect()
                    await asyncio.sleep(1)
                    await self.mqtt_client.connect()
                    logger.info("MQTT client reconnection attempted")
            
            elif component_name == 'safety_service' and not component_status.get('running', False):
                # Restart safety service if it's not running
                if self.safety_service and not self.safety_service._running:
                    await self.safety_service.start()
                    logger.info("Safety service restart attempted")
            
        except Exception as e:
            logger.error(f"Failed to recover component {component_name}: {e}")
    
    async def _shutdown(self):
        """Initiate graceful shutdown"""
        logger.info("Initiating graceful shutdown")
        self.running = False
        self.shutdown_event.set()
    
    async def _cleanup(self):
        """Clean up resources"""
        try:
            logger.info("Cleaning up safety system resources")
            
            # Stop safety service
            if self.safety_service:
                await self.safety_service.stop()
            
            # Disconnect MQTT client
            if self.mqtt_client:
                await self.mqtt_client.disconnect()
            
            # Stop data manager
            if self.data_manager:
                await self.data_manager.stop()
            
            logger.info("Safety system cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


async def main():
    """Main entry point"""
    safety_main = SafetySystemMain()
    
    try:
        await safety_main.initialize()
        await safety_main.run()
    except KeyboardInterrupt:
        logger.info("Safety system interrupted by user")
    except Exception as e:
        logger.error(f"Safety system failed: {e}")
        sys.exit(1)
    
    logger.info("Safety system shutdown complete")


if __name__ == "__main__":
    # Enable uvloop if available for better performance
    try:
        import uvloop
        uvloop.install()
        logger.info("Using uvloop for improved async performance")
    except ImportError:
        logger.info("uvloop not available, using default asyncio")
    
    asyncio.run(main())
