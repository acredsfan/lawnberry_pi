#!/usr/bin/env python3
"""
Hardware Sensor Service
Bridges real hardware sensors to MQTT for real-time data streaming
"""

import asyncio
import logging
import signal
import sys
import json
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hardware import create_hardware_interface, HardwareInterface
from communication.client import MQTTClient
from hardware.data_structures import SensorReading


class SensorService:
    """Service that reads real sensor data and publishes to MQTT"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.hardware: Optional[HardwareInterface] = None
        self.mqtt_client: Optional[MQTTClient] = None
        self.running = False
        self.poll_interval = 0.1  # 10Hz sensor polling
        # Keep last known non-default values per category to avoid publishing zeros
        self._last_values: Dict[str, Dict[str, Any]] = {
            'gps': None,            # type: ignore
            'imu': None,            # type: ignore
            'tof': None,            # type: ignore
            'environmental': None,  # type: ignore
            'power': None           # type: ignore
        }
        
    async def initialize(self):
        """Initialize hardware interface and MQTT client"""
        try:
            self.logger.info("Initializing hardware sensor service...")
            
            # Initialize hardware interface
            self.hardware = create_hardware_interface()
            await self.hardware.initialize()
            self.logger.info("Hardware interface initialized")
            
            # Initialize MQTT client
            self.mqtt_client = MQTTClient(
                client_id="hardware_sensor_service",
                config={
                    'broker_host': 'localhost',
                    'broker_port': 1883,
                    'keepalive': 60,
                    'reconnect_delay': 5.0,
                    'max_reconnect_delay': 60.0,
                    'message_timeout': 30.0,
                    'auth': {
                        'enabled': False
                    },
                    'tls': {
                        'enabled': False
                    }
                }
            )
            # Use initialize() to construct underlying MQTT client and connect
            initialized = await self.mqtt_client.initialize()
            if not initialized:
                raise RuntimeError("MQTT client initialization failed")
            self.logger.info("MQTT client connected")
            
            self.logger.info("Hardware sensor service initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize sensor service: {e}")
            raise
    
    async def run(self):
        """Main service loop"""
        self.running = True
        self.logger.info("Starting hardware sensor service main loop")
        
        try:
            while self.running:
                # Read all sensor data
                sensor_data = await self.read_sensor_data()
                
                if sensor_data:
                    # Publish individual sensor data
                    await self.publish_sensor_data(sensor_data)
                
                # Wait before next poll cycle
                await asyncio.sleep(self.poll_interval)
                
        except asyncio.CancelledError:
            self.logger.info("Sensor service cancelled")
        except Exception as e:
            self.logger.error(f"Error in sensor service main loop: {e}")
            raise
    
    async def read_sensor_data(self) -> Optional[Dict[str, Any]]:
        """Read all sensor data with timeout protection"""
        try:
            # Use timeout to prevent hanging
            async with asyncio.timeout(5.0):
                # Get all sensor data from hardware interface
                raw_sensor_data = await self.hardware.get_all_sensor_data()
                
                if not raw_sensor_data:
                    return None
                
                # Convert to structured format for MQTT
                formatted_data = await self.format_sensor_data(raw_sensor_data)
                return formatted_data
                
        except asyncio.TimeoutError:
            self.logger.warning("Sensor data read timed out")
            return None
        except Exception as e:
            self.logger.error(f"Failed to read sensor data: {e}")
            return None
    
    async def format_sensor_data(self, raw_data: Dict[str, SensorReading]) -> Dict[str, Any]:
        """Format raw sensor readings into structured data"""
        formatted = {
            'timestamp': datetime.utcnow().isoformat(),
            'gps': {
                'latitude': 0.0,
                'longitude': 0.0,
                'altitude': 0.0,
                'accuracy': 0.0,
                'satellites': 0,
                'timestamp': datetime.utcnow().isoformat()
            },
            'imu': {
                'orientation': {'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0},
                'acceleration': {'x': 0.0, 'y': 0.0, 'z': 0.0},
                'gyroscope': {'x': 0.0, 'y': 0.0, 'z': 0.0},
                'temperature': 0.0,
                'timestamp': datetime.utcnow().isoformat()
            },
            'tof': {
                'left_distance': 0.0,
                'right_distance': 0.0,
                'timestamp': datetime.utcnow().isoformat()
            },
            'environmental': {
                'temperature': 0.0,
                'humidity': 0.0,
                'pressure': 0.0,
                'light_level': 0.0,
                'rain_detected': False,
                'timestamp': datetime.utcnow().isoformat()
            },
            'power': {
                'battery_voltage': 0.0,
                'battery_current': 0.0,
                'battery_level': 0.0,
                'solar_voltage': 0.0,
                'solar_current': 0.0,
                'charging': False,
                'timestamp': datetime.utcnow().isoformat()
            }
        }
        # Track which categories were updated in this cycle
        updated: Dict[str, bool] = {
            'gps': False,
            'imu': False,
            'tof': False,
            'environmental': False,
            'power': False,
        }

        # Map raw sensor data to formatted structure
        for sensor_id, reading in raw_data.items():
            if 'gps' in sensor_id.lower():
                if isinstance(reading.value, dict):
                    formatted['gps'].update({
                        'latitude': reading.value.get('latitude', 0.0),
                        'longitude': reading.value.get('longitude', 0.0),
                        'altitude': reading.value.get('altitude', 0.0),
                        'accuracy': reading.value.get('accuracy', 0.0),
                        'satellites': reading.value.get('satellites', 0),
                        'timestamp': reading.timestamp.isoformat() if reading.timestamp else datetime.utcnow().isoformat()
                    })
                    updated['gps'] = True
            
            elif 'imu' in sensor_id.lower() or 'bno085' in sensor_id.lower():
                if isinstance(reading.value, dict):
                    formatted['imu'].update({
                        'orientation': reading.value.get('orientation', {'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0}),
                        'acceleration': reading.value.get('acceleration', {'x': 0.0, 'y': 0.0, 'z': 0.0}),
                        'gyroscope': reading.value.get('gyroscope', {'x': 0.0, 'y': 0.0, 'z': 0.0}),
                        'temperature': reading.value.get('temperature', 0.0),
                        'timestamp': reading.timestamp.isoformat() if reading.timestamp else datetime.utcnow().isoformat()
                    })
                    updated['imu'] = True
            
            elif 'tof' in sensor_id.lower() or 'vl53l0x' in sensor_id.lower():
                # Prefer mapping per-sensor side when name indicates it
                distance_value = reading.value if isinstance(reading.value, (int, float)) else (
                    reading.metadata.get('distance_mm') if isinstance(reading.metadata, dict) else 0.0
                )
                sensor_lower = sensor_id.lower()
                if 'left' in sensor_lower:
                    formatted['tof']['left_distance'] = distance_value
                elif 'right' in sensor_lower:
                    formatted['tof']['right_distance'] = distance_value
                else:
                    # Unknown side - set all for backward compatibility
                    formatted['tof']['left_distance'] = distance_value
                    formatted['tof']['right_distance'] = distance_value
                formatted['tof']['timestamp'] = reading.timestamp.isoformat() if reading.timestamp else datetime.utcnow().isoformat()
                updated['tof'] = True
            
            elif 'environmental' in sensor_id.lower() or 'bme280' in sensor_id.lower():
                if isinstance(reading.value, dict):
                    formatted['environmental'].update({
                        'temperature': reading.value.get('temperature', 0.0),
                        'humidity': reading.value.get('humidity', 0.0),
                        'pressure': reading.value.get('pressure', 0.0),
                        'light_level': reading.value.get('light_level', 0.0),
                        'rain_detected': reading.value.get('rain_detected', False),
                        'timestamp': reading.timestamp.isoformat() if reading.timestamp else datetime.utcnow().isoformat()
                    })
                    updated['environmental'] = True
            
            elif 'power' in sensor_id.lower() or 'ina3221' in sensor_id.lower():
                if isinstance(reading.value, dict):
                    # Accept multiple key aliases from plugins/drivers
                    bat_v = reading.value.get('battery_voltage', reading.value.get('voltage', 0.0))
                    bat_c = reading.value.get('battery_current', reading.value.get('current', 0.0))
                    formatted['power'].update({
                        'battery_voltage': bat_v,
                        'battery_current': bat_c,
                        'battery_level': reading.value.get('battery_level', 0.0),
                        'solar_voltage': reading.value.get('solar_voltage', 0.0),
                        'solar_current': reading.value.get('solar_current', 0.0),
                        'charging': reading.value.get('charging', bat_c > 0.0),
                        'timestamp': reading.timestamp.isoformat() if reading.timestamp else datetime.utcnow().isoformat()
                    })
                    updated['power'] = True
        # Backfill categories that were not updated to avoid publishing zeros
        try:
            # Helper lambdas to detect default (all-zero/false) payloads
            def _is_default_gps(d: Dict[str, Any]) -> bool:
                return (d.get('latitude', 0.0) == 0.0 and d.get('longitude', 0.0) == 0.0)

            def _is_default_imu(d: Dict[str, Any]) -> bool:
                ori = d.get('orientation', {})
                acc = d.get('acceleration', {})
                gyro = d.get('gyroscope', {})
                return (
                    all(float(ori.get(k, 0.0)) == 0.0 for k in ('roll', 'pitch', 'yaw'))
                    and all(float(acc.get(k, 0.0)) == 0.0 for k in ('x', 'y', 'z'))
                    and all(float(gyro.get(k, 0.0)) == 0.0 for k in ('x', 'y', 'z'))
                )

            def _is_default_tof(d: Dict[str, Any]) -> bool:
                return all(float(d.get(k, 0.0) or 0.0) == 0.0 for k in ('left_distance','right_distance'))

            def _is_default_env(d: Dict[str, Any]) -> bool:
                return (
                    float(d.get('temperature', 0.0) or 0.0) == 0.0
                    and float(d.get('humidity', 0.0) or 0.0) == 0.0
                    and float(d.get('pressure', 0.0) or 0.0) == 0.0
                )

            def _is_default_power(d: Dict[str, Any]) -> bool:
                return (
                    float(d.get('battery_voltage', 0.0) or 0.0) == 0.0
                    and float(d.get('battery_current', 0.0) or 0.0) == 0.0
                )

            # For each category, if not updated and we have a prior value, backfill it
            now_iso = datetime.utcnow().isoformat()
            if (not updated['gps'] or _is_default_gps(formatted['gps'])) and self._last_values.get('gps'):
                prev = dict(self._last_values['gps'])
                prev['timestamp'] = now_iso
                formatted['gps'] = prev
                self.logger.debug("Backfilled GPS with last known values")

            if (not updated['imu'] or _is_default_imu(formatted['imu'])) and self._last_values.get('imu'):
                prev = dict(self._last_values['imu'])
                prev['timestamp'] = now_iso
                formatted['imu'] = prev
                self.logger.debug("Backfilled IMU with last known values")

            if (not updated['tof'] or _is_default_tof(formatted['tof'])) and self._last_values.get('tof'):
                prev = dict(self._last_values['tof'])
                prev['timestamp'] = now_iso
                formatted['tof'] = prev
                self.logger.debug("Backfilled ToF with last known values")

            if (not updated['environmental'] or _is_default_env(formatted['environmental'])) and self._last_values.get('environmental'):
                prev = dict(self._last_values['environmental'])
                prev['timestamp'] = now_iso
                formatted['environmental'] = prev
                self.logger.debug("Backfilled Environmental with last known values")

            if (not updated['power'] or _is_default_power(formatted['power'])) and self._last_values.get('power'):
                prev = dict(self._last_values['power'])
                prev['timestamp'] = now_iso
                formatted['power'] = prev
                self.logger.debug("Backfilled Power with last known values")
        except Exception as e:
            # Backfill is non-critical; continue on error
            self.logger.debug(f"Backfill skipped due to error: {e}")

        return formatted
    
    async def publish_sensor_data(self, sensor_data: Dict[str, Any]):
        """Publish sensor data to MQTT topics"""
        try:
            # Update last-known cache with any non-default values so we don't regress to zeros
            try:
                def _update_if_non_default(category: str, data: Dict[str, Any]):
                    if category == 'gps':
                        if not (data.get('latitude', 0.0) == 0.0 and data.get('longitude', 0.0) == 0.0):
                            self._last_values['gps'] = data.copy()
                    elif category == 'imu':
                        ori = data.get('orientation', {})
                        acc = data.get('acceleration', {})
                        gyro = data.get('gyroscope', {})
                        if (
                            any(float(ori.get(k, 0.0)) != 0.0 for k in ('roll', 'pitch', 'yaw'))
                            or any(float(acc.get(k, 0.0)) != 0.0 for k in ('x', 'y', 'z'))
                            or any(float(gyro.get(k, 0.0)) != 0.0 for k in ('x', 'y', 'z'))
                        ):
                            self._last_values['imu'] = data.copy()
                    elif category == 'tof':
                        if any(float(data.get(k, 0.0) or 0.0) > 0.0 for k in ('left_distance','right_distance')):
                            self._last_values['tof'] = data.copy()
                    elif category == 'environmental':
                        if any(float(data.get(k, 0.0) or 0.0) != 0.0 for k in ('temperature','humidity','pressure')):
                            self._last_values['environmental'] = data.copy()
                    elif category == 'power':
                        if float(data.get('battery_voltage', 0.0) or 0.0) != 0.0 or float(data.get('battery_current', 0.0) or 0.0) != 0.0:
                            self._last_values['power'] = data.copy()

                _update_if_non_default('gps', sensor_data.get('gps', {}))
                _update_if_non_default('imu', sensor_data.get('imu', {}))
                _update_if_non_default('tof', sensor_data.get('tof', {}))
                _update_if_non_default('environmental', sensor_data.get('environmental', {}))
                _update_if_non_default('power', sensor_data.get('power', {}))
            except Exception as e:
                self.logger.debug(f"Last-values cache update skipped: {e}")

            # Publish individual sensor categories
            topics = {
                'sensors/gps/data': sensor_data['gps'],
                'sensors/imu/data': sensor_data['imu'],
                'sensors/tof/data': sensor_data['tof'],
                'sensors/environmental/data': sensor_data['environmental'],
                'power/battery': sensor_data['power']
            }
            
            # Publish to each topic
            for topic, data in topics.items():
                full_topic = f"lawnberry/{topic}"
                await self.mqtt_client.publish(full_topic, data, qos=0)
            
            # Also publish combined data for comprehensive updates
            await self.mqtt_client.publish("lawnberry/sensors/all", sensor_data, qos=0)

            # Publish per-ToF sensor topics for finer grained consumers (left/right only)
            try:
                tof = sensor_data.get('tof', {})
                tof_ts = tof.get('timestamp', datetime.utcnow().isoformat())
                per_tof = {
                    'sensors/tof/left': {
                        'distance_mm': float(tof.get('left_distance', 0.0) or 0.0),
                        'timestamp': tof_ts,
                    },
                    'sensors/tof/right': {
                        'distance_mm': float(tof.get('right_distance', 0.0) or 0.0),
                        'timestamp': tof_ts,
                    },
                }
                for topic, data in per_tof.items():
                    await self.mqtt_client.publish(f"lawnberry/{topic}", data, qos=0)
            except Exception as e:
                self.logger.debug(f"Per-ToF publish skipped: {e}")
            
            # Publish system health status
            health_status = await self.hardware.get_system_health()
            if health_status:
                await self.mqtt_client.publish("lawnberry/system/health", health_status, qos=1)
                
        except Exception as e:
            self.logger.error(f"Failed to publish sensor data: {e}")
    
    async def stop(self):
        """Stop the sensor service"""
        self.logger.info("Stopping hardware sensor service...")
        self.running = False
        
        if self.mqtt_client:
            try:
                await asyncio.wait_for(self.mqtt_client.disconnect(), timeout=5.0)
            except asyncio.TimeoutError:
                self.logger.warning("MQTT disconnect timed out")
            except Exception as e:
                self.logger.warning(f"MQTT disconnect error: {e}")
            
        if self.hardware:
            try:
                await asyncio.wait_for(self.hardware.cleanup(), timeout=15.0)
                self.logger.info("Hardware cleanup completed")
            except asyncio.TimeoutError:
                self.logger.error("Hardware cleanup timed out")
            except Exception as e:
                self.logger.error(f"Hardware cleanup error: {e}")
        
        self.logger.info("Hardware sensor service stopped")


async def main():
    """Main service entry point with proper shutdown handling"""
    # Setup logging with safe fallback when /var/log is not writable
    log_handlers = [logging.StreamHandler()]
    try:
        log_dir = Path('/var/log/lawnberry')
        log_dir.mkdir(parents=True, exist_ok=True)
        log_handlers.insert(0, logging.FileHandler(str(log_dir / 'sensor_service.log')))
    except Exception:
        # Fallback to user-local log directory
        try:
            home_log_dir = Path.home() / '.lawnberry' / 'logs'
            home_log_dir.mkdir(parents=True, exist_ok=True)
            log_handlers.insert(0, logging.FileHandler(str(home_log_dir / 'sensor_service.log')))
        except Exception:
            pass

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=log_handlers,
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Starting LawnBerryPi Hardware Sensor Service")
    
    # Create service instance
    service = SensorService()
    shutdown_event = asyncio.Event()
    initialization_task = None
    service_task = None
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received shutdown signal {signum}")
        shutdown_event.set()
    
    # Setup signal handlers
    for sig in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(sig, signal_handler)
    
    try:
        # Initialize service with timeout
        logger.info("Initializing service...")
        initialization_task = asyncio.create_task(service.initialize())
        
        # Wait for either initialization completion or shutdown signal
        done, pending = await asyncio.wait(
            [initialization_task, asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
            timeout=60.0  # 60 second timeout for initialization
        )
        
        # Check if shutdown was requested during initialization
        if shutdown_event.is_set():
            logger.info("Shutdown requested during initialization")
            if initialization_task and not initialization_task.done():
                initialization_task.cancel()
                try:
                    await initialization_task
                except asyncio.CancelledError:
                    logger.info("Initialization cancelled successfully")
            return
        
        # Check if initialization completed successfully
        if initialization_task.done():
            try:
                await initialization_task  # This will raise if initialization failed
                logger.info("Service initialized successfully, starting main loop...")
            except Exception as e:
                logger.error(f"Service initialization failed: {e}")
                return
        else:
            logger.error("Service initialization timed out")
            initialization_task.cancel()
            return
        
        # Create service task
        service_task = asyncio.create_task(service.run())
        
        # Wait for either service completion or shutdown signal
        done, pending = await asyncio.wait(
            [service_task, asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED,
            timeout=None
        )
        
        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        logger.info("Service shutting down gracefully...")
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Service failed: {e}")
        sys.exit(1)
    finally:
        # Ensure proper cleanup with timeout
        try:
            await asyncio.wait_for(service.stop(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("Service stop timed out - forcing exit")
        except Exception as e:
            logger.error(f"Error during service stop: {e}")
        logger.info("Service shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
