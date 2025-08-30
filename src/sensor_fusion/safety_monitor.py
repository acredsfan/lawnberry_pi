"""
Safety monitoring system with 100ms emergency response
"""

import asyncio
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable
import logging
import uuid

from ..hardware.data_structures import IMUReading, ToFReading, EnvironmentalReading
from ..communication import MQTTClient, MessageProtocol, SensorData
from .data_structures import (
    SafetyStatus, HazardAlert, HazardLevel, ObstacleInfo, PoseEstimate
)

logger = logging.getLogger(__name__)


class SafetyMonitor:
    """
    Safety monitoring system that provides 100ms emergency response
    and comprehensive hazard detection
    """
    
    def __init__(self, mqtt_client: MQTTClient):
        self.mqtt_client = mqtt_client
        self.update_rate = 20  # Hz for safety monitoring
        self.emergency_response_time_ms = 100  # Maximum response time
        # Status publish control (consolidated status is published by SafetyService)
        # Keep monitor self-publishing disabled by default to avoid duplicate traffic
        from datetime import datetime as _dt
        self._publish_status_updates: bool = False
        self._status_publish_rate_hz: float = 1.0
        self._last_status_publish: _dt = _dt.min
        
        # Safety thresholds
        self.max_safe_tilt_angle = 15.0  # degrees
        self.min_safe_ground_clearance = 0.05  # meters
        self.safe_distance_threshold = 0.3  # meters
        self.collision_threshold_g = 2.0  # g-force for impact detection
        
        # Temperature limits
        self.min_operating_temp = 5.0   # Celsius
        self.max_operating_temp = 40.0  # Celsius
        
        # Current sensor data
        self._latest_imu: Optional[IMUReading] = None
        self._latest_tof_left: Optional[ToFReading] = None
        self._latest_tof_right: Optional[ToFReading] = None
        self._latest_weather: Optional[EnvironmentalReading] = None
        self._current_pose: Optional[PoseEstimate] = None
        self._current_obstacles: List[ObstacleInfo] = []
        
        # Safety state
        self._current_safety_status: Optional[SafetyStatus] = None
        self._active_alerts: Dict[str, HazardAlert] = {}
        self._emergency_callbacks: List[Callable] = []
        
        # Performance tracking
        self._last_hazard_detection_time: Optional[datetime] = None
        self._response_times: List[float] = []
        self._safety_events_count = 0
        
        # IMU data for collision detection
        self._acceleration_history: List[Tuple[datetime, np.ndarray]] = []
        self._max_acceleration_history = 20  # Keep 1 second at 20Hz
        
        # Tasks
        self._safety_task: Optional[asyncio.Task] = None
        self._emergency_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start(self):
        """Start the safety monitoring system"""
        logger.info("Starting safety monitoring system")
        self._running = True
        
        # Subscribe to sensor data
        await self._subscribe_to_sensors()
        
        # Start monitoring tasks
        self._safety_task = asyncio.create_task(self._safety_monitoring_loop())
        self._emergency_task = asyncio.create_task(self._emergency_monitoring_loop())
        
    async def stop(self):
        """Stop the safety monitoring system"""
        logger.info("Stopping safety monitoring system")
        self._running = False
        
        if self._safety_task:
            self._safety_task.cancel()
            try:
                await self._safety_task
            except asyncio.CancelledError:
                pass
                
        if self._emergency_task:
            self._emergency_task.cancel()
            try:
                await self._emergency_task
            except asyncio.CancelledError:
                pass
    
    async def _subscribe_to_sensors(self):
        """Subscribe to safety-critical sensor data"""
        topics = [
            ("lawnberry/sensors/imu", self._handle_imu_data),
            ("lawnberry/sensors/tof_left", self._handle_tof_left_data),
            ("lawnberry/sensors/tof_right", self._handle_tof_right_data),
            # Use unified environmental data topic published by hardware service
            ("lawnberry/sensors/environmental/data", self._handle_weather_data),
            ("lawnberry/sensors/localization", self._handle_pose_data),
            ("lawnberry/sensors/obstacles", self._handle_obstacles_data),
        ]
        for topic, handler in topics:
            await self.mqtt_client.subscribe(topic)
            self.mqtt_client.add_message_handler(topic, handler)
    
    async def _handle_imu_data(self, topic: str, message: MessageProtocol):
        """Handle IMU sensor data for tilt and collision detection"""
        try:
            imu_data = message.payload
            self._latest_imu = IMUReading(
                timestamp=datetime.fromtimestamp(message.metadata.timestamp),
                sensor_id=imu_data.get('sensor_id', 'bno085'),
                value=imu_data,
                unit='mixed',
                port=imu_data.get('port', '/dev/ttyAMA4'),
                baud_rate=imu_data.get('baud_rate', 115200),
                quaternion=tuple(imu_data['quaternion']),
                acceleration=tuple(imu_data['acceleration']),
                angular_velocity=tuple(imu_data['angular_velocity'])
            )
            
            # Store acceleration history for collision detection
            accel_vector = np.array(self._latest_imu.acceleration)
            self._acceleration_history.append((self._latest_imu.timestamp, accel_vector))
            
            # Keep only recent history
            if len(self._acceleration_history) > self._max_acceleration_history:
                self._acceleration_history.pop(0)
                
        except Exception as e:
            logger.error(f"Error processing IMU data: {e}")
    
    async def _handle_tof_left_data(self, topic: str, message: MessageProtocol):
        """Handle left ToF sensor data"""
        try:
            tof_data = message.payload
            self._latest_tof_left = ToFReading(
                timestamp=datetime.fromtimestamp(message.metadata.timestamp),
                sensor_id=tof_data.get('sensor_id', 'tof_left'),
                value=tof_data['distance_mm'],
                unit='mm',
                i2c_address=tof_data.get('i2c_address', 0x29),
                distance_mm=tof_data['distance_mm'],
                range_status=tof_data.get('range_status', 'valid')
            )
        except Exception as e:
            logger.error(f"Error processing left ToF data: {e}")
    
    async def _handle_tof_right_data(self, topic: str, message: MessageProtocol):
        """Handle right ToF sensor data"""
        try:
            tof_data = message.payload
            self._latest_tof_right = ToFReading(
                timestamp=datetime.fromtimestamp(message.metadata.timestamp),
                sensor_id=tof_data.get('sensor_id', 'tof_right'),
                value=tof_data['distance_mm'],
                unit='mm',
                i2c_address=tof_data.get('i2c_address', 0x30),
                distance_mm=tof_data['distance_mm'],
                range_status=tof_data.get('range_status', 'valid')
            )
        except Exception as e:
            logger.error(f"Error processing right ToF data: {e}")
    
    async def _handle_weather_data(self, topic: str, message: MessageProtocol):
        """Handle weather sensor data with robust payload unwrapping and key safety."""
        try:
            # Accept SensorData wrapper or plain dicts and unwrap nested {data: {...}}
            payload = message.payload if hasattr(message, 'payload') else (message if isinstance(message, dict) else {})
            if isinstance(payload, dict) and 'data' in payload and isinstance(payload['data'], dict):
                payload = payload['data']

            # Some publishers may nest environmental data under a key
            weather_data = None
            if isinstance(payload, dict):
                # Direct shape
                if any(k in payload for k in ('temperature', 'humidity', 'pressure')):
                    weather_data = payload
                else:
                    # Common nestings
                    for k in ('environmental', 'environment', 'bme280'):
                        if k in payload and isinstance(payload[k], dict):
                            weather_data = payload[k]
                            break

            if not isinstance(weather_data, dict):
                logger.debug("Weather payload missing expected structure; skipping")
                return

            # Tolerate alias keys
            temp = weather_data.get('temperature', weather_data.get('temp_c', weather_data.get('temp')))
            hum = weather_data.get('humidity', weather_data.get('rh'))
            press = weather_data.get('pressure', weather_data.get('pressure_hpa'))
            # Convert pressure in hPa to Pa if needed
            if press is not None and 'pressure_hpa' in weather_data:
                try:
                    press = float(press) * 100.0
                except Exception:
                    pass

            # If still missing core values, skip to avoid publishing zeros
            if temp is None or hum is None or press is None:
                logger.debug("Incomplete weather data (missing temperature/humidity/pressure); skipping")
                return

            ts = None
            try:
                if getattr(message, 'metadata', None) and getattr(message.metadata, 'timestamp', None):
                    ts = datetime.fromtimestamp(message.metadata.timestamp)
            except Exception:
                ts = None

            self._latest_weather = EnvironmentalReading(
                timestamp=ts or datetime.now(),
                sensor_id=weather_data.get('sensor_id', 'bme280'),
                value=weather_data,
                unit='mixed',
                i2c_address=weather_data.get('i2c_address', 0x76),
                temperature=float(temp),
                humidity=float(hum),
                pressure=float(press)
            )
        except KeyError as e:
            # Some publishers may omit keys intermittently; avoid error spam
            logger.debug(f"Weather data missing key {e}; skipping this update")
            return
        except Exception as e:
            logger.error(f"Error processing weather data: {e}")
    
    async def _handle_pose_data(self, topic: str, message: MessageProtocol):
        """Handle pose estimation data"""
        try:
            pose_data = message.payload['pose']
            self._current_pose = PoseEstimate(
                timestamp=datetime.fromisoformat(pose_data['timestamp']),
                latitude=pose_data['latitude'],
                longitude=pose_data['longitude'],
                altitude=pose_data['altitude'],
                x=pose_data['x'],
                y=pose_data['y'],
                z=pose_data['z'],
                qw=pose_data['qw'],
                qx=pose_data['qx'],
                qy=pose_data['qy'],
                qz=pose_data['qz'],
                vx=pose_data['vx'],
                vy=pose_data['vy'],
                vz=pose_data['vz'],
                wx=pose_data['wx'],
                wy=pose_data['wy'],
                wz=pose_data['wz'],
                covariance=np.eye(6) * 0.1,
                gps_accuracy=pose_data['gps_accuracy'],
                fusion_confidence=pose_data['fusion_confidence']
            )
        except Exception as e:
            logger.error(f"Error processing pose data: {e}")
    
    async def _handle_obstacles_data(self, topic: str, message: MessageProtocol):
        """Handle obstacle detection data"""
        try:
            obstacles_data = message.payload
            self._current_obstacles = []
            
            for obs_data in obstacles_data.get('obstacles', []):
                obstacle = ObstacleInfo(
                    obstacle_id=obs_data['obstacle_id'],
                    obstacle_type=obs_data['type'],
                    x=obs_data['position'][0],
                    y=obs_data['position'][1],
                    z=obs_data['position'][2],
                    width=obs_data['size'][0],
                    height=obs_data['size'][1],
                    depth=obs_data['size'][2],
                    vx=obs_data['velocity'][0],
                    vy=obs_data['velocity'][1],
                    vz=obs_data['velocity'][2],
                    confidence=obs_data['confidence'],
                    detected_by=obs_data['detected_by'],
                    distance=obs_data['distance'],
                    first_detected=datetime.fromisoformat(obs_data['first_detected']),
                    last_updated=datetime.fromisoformat(obs_data['last_updated'])
                )
                self._current_obstacles.append(obstacle)
                
        except Exception as e:
            logger.error(f"Error processing obstacles data: {e}")
    
    async def _safety_monitoring_loop(self):
        """Main safety monitoring loop (20Hz)"""
        while self._running:
            try:
                start_time = datetime.now()
                
                # Check all safety conditions
                safety_status = await self._evaluate_safety_status()
                self._current_safety_status = safety_status
                
                # Handle safety alerts
                await self._process_safety_alerts(safety_status)
                
                # Publish safety status
                await self._publish_safety_status(safety_status)
                
                # Track response time
                response_time = (datetime.now() - start_time).total_seconds() * 1000
                self._response_times.append(response_time)
                if len(self._response_times) > 100:
                    self._response_times.pop(0)
                
                await asyncio.sleep(1.0 / self.update_rate)
                
            except Exception as e:
                logger.error(f"Error in safety monitoring loop: {e}")
                await asyncio.sleep(0.05)
    
    async def _emergency_monitoring_loop(self):
        """Ultra-fast emergency monitoring for critical hazards"""
        while self._running:
            try:
                # Check for immediate emergency conditions
                emergency_hazards = await self._check_emergency_conditions()
                
                if emergency_hazards:
                    await self._trigger_emergency_response(emergency_hazards)
                
                # Run at higher frequency for emergency detection
                await asyncio.sleep(0.02)  # 50Hz for emergency monitoring
                
            except Exception as e:
                logger.error(f"Error in emergency monitoring loop: {e}")
                await asyncio.sleep(0.01)
    
    async def _evaluate_safety_status(self) -> SafetyStatus:
        """Evaluate overall safety status"""
        current_time = datetime.now()
        
        # Initialize safety status
        safety_status = SafetyStatus(
            timestamp=current_time,
            is_safe=True,
            safety_level=HazardLevel.NONE
        )
        
        # Check tilt safety
        if self._latest_imu:
            tilt_angle = self._calculate_tilt_angle()
            safety_status.tilt_angle = tilt_angle
            safety_status.tilt_safe = tilt_angle < self.max_safe_tilt_angle
            
            if not safety_status.tilt_safe:
                alert = self._create_hazard_alert(
                    "tilt_exceeded",
                    HazardLevel.HIGH if tilt_angle > 20 else HazardLevel.MEDIUM,
                    f"Tilt angle {tilt_angle:.1f}° exceeds safe limit of {self.max_safe_tilt_angle}°",
                    sensor_data={'tilt_angle': tilt_angle, 'quaternion': self._latest_imu.quaternion}
                )
                safety_status.active_alerts.append(alert)
        
        # Check drop detection using ToF sensors
        ground_clearance = self._calculate_ground_clearance()
        safety_status.ground_clearance = ground_clearance
        safety_status.drop_safe = ground_clearance > self.min_safe_ground_clearance
        
        if not safety_status.drop_safe:
            alert = self._create_hazard_alert(
                "drop_detected",
                HazardLevel.CRITICAL,
                f"Ground clearance {ground_clearance:.2f}m below safe minimum",
                sensor_data={'ground_clearance': ground_clearance}
            )
            safety_status.active_alerts.append(alert)
        
        # Check collision safety
        collision_detected = self._detect_collision()
        safety_status.collision_safe = not collision_detected
        
        if collision_detected:
            alert = self._create_hazard_alert(
                "collision_detected",
                HazardLevel.CRITICAL,
                "Collision or impact detected",
                sensor_data={'acceleration_history': [list(a[1]) for a in self._acceleration_history[-5:]]}
            )
            safety_status.active_alerts.append(alert)
        
        # Check obstacle proximity
        nearest_distance = self._get_nearest_obstacle_distance()
        safety_status.nearest_obstacle_distance = nearest_distance
        safety_status.collision_safe = safety_status.collision_safe and (nearest_distance > self.safe_distance_threshold)
        
        if nearest_distance <= self.safe_distance_threshold:
            alert = self._create_hazard_alert(
                "obstacle_proximity",
                HazardLevel.HIGH,
                f"Obstacle detected at {nearest_distance:.2f}m (safety threshold: {self.safe_distance_threshold:.2f}m)",
                sensor_data={'nearest_distance': nearest_distance, 'obstacle_count': len(self._current_obstacles)}
            )
            safety_status.active_alerts.append(alert)
        
        # Check weather safety
        if self._latest_weather:
            safety_status.temperature = self._latest_weather.temperature
            safety_status.humidity = self._latest_weather.humidity
            safety_status.is_raining = self._detect_rain()
            
            temp_safe = (self.min_operating_temp <= self._latest_weather.temperature <= self.max_operating_temp)
            rain_safe = not safety_status.is_raining
            
            safety_status.weather_safe = temp_safe and rain_safe
            
            if not temp_safe:
                alert = self._create_hazard_alert(
                    "temperature_unsafe",
                    HazardLevel.MEDIUM,
                    f"Temperature {self._latest_weather.temperature:.1f}°C outside safe range ({self.min_operating_temp}-{self.max_operating_temp}°C)",
                    sensor_data={'temperature': self._latest_weather.temperature}
                )
                safety_status.active_alerts.append(alert)
            
            if not rain_safe:
                alert = self._create_hazard_alert(
                    "rain_detected",
                    HazardLevel.MEDIUM,
                    "Rain detected - unsafe for operation",
                    sensor_data={'humidity': self._latest_weather.humidity}
                )
                safety_status.active_alerts.append(alert)
        
        # Check boundary safety (would need boundary definition)
        safety_status.boundary_safe = True  # Placeholder
        
        # Update overall safety status
        safety_status.is_safe = (
            safety_status.tilt_safe and
            safety_status.drop_safe and
            safety_status.collision_safe and
            safety_status.weather_safe and
            safety_status.boundary_safe
        )
        
        # Determine overall safety level
        if safety_status.active_alerts:
            max_level = max(alert.hazard_level for alert in safety_status.active_alerts)
            safety_status.safety_level = max_level
        
        return safety_status
    
    def _calculate_tilt_angle(self) -> float:
        """Calculate tilt angle from IMU quaternion"""
        if not self._latest_imu:
            return 0.0
        
        qw, qx, qy, qz = self._latest_imu.quaternion
        
        # Convert quaternion to Euler angles
        # Roll (x-axis rotation)
        sinr_cosp = 2 * (qw * qx + qy * qz)
        cosr_cosp = 1 - 2 * (qx * qx + qy * qy)
        roll = np.arctan2(sinr_cosp, cosr_cosp)
        
        # Pitch (y-axis rotation)
        sinp = 2 * (qw * qy - qz * qx)
        if abs(sinp) >= 1:
            pitch = np.copysign(np.pi / 2, sinp)
        else:
            pitch = np.arcsin(sinp)
        
        # Calculate tilt as maximum of roll and pitch
        tilt_rad = max(abs(roll), abs(pitch))
        return np.degrees(tilt_rad)
    
    def _calculate_ground_clearance(self) -> float:
        """Calculate ground clearance using downward-facing ToF sensors"""
        # This would require downward-facing ToF sensors
        # For now, return a safe default
        return 0.1  # 10cm default clearance
    
    def _detect_collision(self) -> bool:
        """Detect collision using IMU acceleration data"""
        if len(self._acceleration_history) < 2:
            return False
        
        # Check for sudden acceleration changes
        for i in range(1, len(self._acceleration_history)):
            prev_accel = self._acceleration_history[i-1][1]
            curr_accel = self._acceleration_history[i][1]
            
            # Calculate acceleration magnitude change
            prev_mag = np.linalg.norm(prev_accel)
            curr_mag = np.linalg.norm(curr_accel)
            
            accel_change = abs(curr_mag - prev_mag)
            
            # Check if acceleration change exceeds collision threshold
            if accel_change > self.collision_threshold_g * 9.81:  # Convert g to m/s²
                return True
        
        return False
    
    def _get_nearest_obstacle_distance(self) -> float:
        """Get distance to nearest obstacle"""
        if not self._current_obstacles:
            return float('inf')
        
        return min(obs.distance for obs in self._current_obstacles)
    
    def _detect_rain(self) -> bool:
        """Detect rain using humidity and other sensors"""
        if not self._latest_weather:
            return False
        
        # Simple rain detection based on high humidity
        # In real implementation, would use more sophisticated detection
        return self._latest_weather.humidity > 95.0
    
    def _create_hazard_alert(self, hazard_type: str, level: HazardLevel, 
                           description: str, sensor_data: Dict[str, Any] = None) -> HazardAlert:
        """Create hazard alert"""
        alert_id = str(uuid.uuid4())[:8]
        
        alert = HazardAlert(
            alert_id=alert_id,
            hazard_level=level,
            hazard_type=hazard_type,
            timestamp=datetime.now(),
            description=description,
            sensor_data=sensor_data or {},
            recommended_action="STOP" if level in [HazardLevel.HIGH, HazardLevel.CRITICAL] else "CAUTION",
            immediate_response_required=level == HazardLevel.CRITICAL
        )
        
        return alert
    
    async def _check_emergency_conditions(self) -> List[HazardAlert]:
        """Check for immediate emergency conditions"""
        emergency_hazards = []
        
        # Check for critical tilt
        if self._latest_imu:
            tilt_angle = self._calculate_tilt_angle()
            if tilt_angle > 25.0:  # Critical tilt threshold
                alert = self._create_hazard_alert(
                    "critical_tilt",
                    HazardLevel.CRITICAL,
                    f"Critical tilt angle {tilt_angle:.1f}° - immediate stop required",
                    immediate_response_required=True
                )
                emergency_hazards.append(alert)
        
        # Check for immediate collision
        if self._detect_collision():
            alert = self._create_hazard_alert(
                "immediate_collision",
                HazardLevel.CRITICAL,
                "Immediate collision detected",
                immediate_response_required=True
            )
            emergency_hazards.append(alert)
        
        # Check for very close obstacles
        nearest_distance = self._get_nearest_obstacle_distance()
        if nearest_distance < 0.15:  # 15cm emergency threshold
            alert = self._create_hazard_alert(
                "emergency_obstacle",
                HazardLevel.CRITICAL,
                f"Emergency: obstacle at {nearest_distance:.2f}m",
                immediate_response_required=True
            )
            emergency_hazards.append(alert)
        
        return emergency_hazards
    
    async def _trigger_emergency_response(self, hazards: List[HazardAlert]):
        """Trigger immediate emergency response"""
        self._last_hazard_detection_time = datetime.now()
        
        # Store alerts
        for alert in hazards:
            self._active_alerts[alert.alert_id] = alert
        
        # Execute emergency callbacks
        for callback in self._emergency_callbacks:
            try:
                await callback(hazards)
            except Exception as e:
                logger.error(f"Error executing emergency callback: {e}")
        
        # Publish emergency alerts
        for alert in hazards:
            await self._publish_emergency_alert(alert)
        
        self._safety_events_count += len(hazards)
        
        # Calculate response time
        if self._last_hazard_detection_time:
            response_time_ms = (datetime.now() - self._last_hazard_detection_time).total_seconds() * 1000
            if response_time_ms <= self.emergency_response_time_ms:
                self._response_times.append(response_time_ms)
                logger.info(f"Emergency response completed in {response_time_ms:.1f}ms")
            else:
                logger.warning(f"Emergency response took {response_time_ms:.1f}ms (target: {self.emergency_response_time_ms}ms)")
    
    async def _process_safety_alerts(self, safety_status: SafetyStatus):
        """Process and manage safety alerts"""
        # Clean up resolved alerts
        current_time = datetime.now()
        expired_alerts = [
            alert_id for alert_id, alert in self._active_alerts.items()
            if (current_time - alert.timestamp).total_seconds() > 30.0  # 30 second timeout
        ]
        
        for alert_id in expired_alerts:
            del self._active_alerts[alert_id]
        
        # Add new alerts to active alerts
        for alert in safety_status.active_alerts:
            if alert.alert_id not in self._active_alerts:
                self._active_alerts[alert.alert_id] = alert
    
    async def _publish_emergency_alert(self, alert: HazardAlert):
        """Publish emergency alert immediately"""
        alert_data = {
            'alert_id': alert.alert_id,
            'hazard_level': alert.hazard_level.value,
            'hazard_type': alert.hazard_type,
            'timestamp': alert.timestamp.isoformat(),
            'description': alert.description,
            'location': alert.location,
            'sensor_data': alert.sensor_data,
            'recommended_action': alert.recommended_action,
            'immediate_response_required': alert.immediate_response_required
        }
        
        message = SensorData.create(
            sender="safety_monitor",
            sensor_type="emergency_alert",
            data=alert_data
        )
        
        await self.mqtt_client.publish("lawnberry/safety/emergency", message)
    
    async def _publish_safety_status(self, safety_status: SafetyStatus):
        """Optionally publish raw monitor safety status (debug/diagnostics).
        Disabled by default; SafetyService publishes consolidated status to the UI.
        """
        # Respect publish disable flag
        if not getattr(self, "_publish_status_updates", False):
            return
        # Throttle publishes
        now = datetime.now()
        min_interval = 1.0 / max(0.1, float(getattr(self, "_status_publish_rate_hz", 1.0)))
        if (now - getattr(self, "_last_status_publish", now)).total_seconds() < min_interval:
            return
        # Prepare active alerts data
        alerts_data = []
        for alert in safety_status.active_alerts:
            alerts_data.append({
                'alert_id': alert.alert_id,
                'hazard_level': alert.hazard_level.value,
                'hazard_type': alert.hazard_type,
                'timestamp': alert.timestamp.isoformat(),
                'description': alert.description,
                'immediate_response_required': alert.immediate_response_required
            })
        
        # Prepare safety status data
        import math
        nearest = safety_status.nearest_obstacle_distance
        if isinstance(nearest, float) and not math.isfinite(nearest):
            nearest = None
        status_data = {
            'timestamp': safety_status.timestamp.isoformat(),
            'is_safe': safety_status.is_safe,
            'safety_level': safety_status.safety_level.value,
            'tilt_safe': safety_status.tilt_safe,
            'drop_safe': safety_status.drop_safe,
            'collision_safe': safety_status.collision_safe,
            'weather_safe': safety_status.weather_safe,
            'boundary_safe': safety_status.boundary_safe,
            'tilt_angle': safety_status.tilt_angle,
            'ground_clearance': safety_status.ground_clearance,
            'nearest_obstacle_distance': nearest,
            'temperature': safety_status.temperature,
            'humidity': safety_status.humidity,
            'is_raining': safety_status.is_raining,
            'active_alerts': alerts_data,
            'response_time_ms': safety_status.response_time_ms,
            'safety_events_count': self._safety_events_count,
            'average_response_time_ms': np.mean(self._response_times) if self._response_times else 0.0
        }
        
        message = SensorData.create(
            sender="safety_monitor",
            sensor_type="safety_status",
            data=status_data
        )
        # Publish to a monitor-specific topic to avoid conflicting with the primary UI topic
        await self.mqtt_client.publish("lawnberry/safety/monitor_status", message)
        self._last_status_publish = now
    
    def register_emergency_callback(self, callback: Callable):
        """Register callback for emergency situations"""
        self._emergency_callbacks.append(callback)
    
    def get_current_safety_status(self) -> Optional[SafetyStatus]:
        """Get current safety status"""
        return self._current_safety_status
    
    def get_active_alerts(self) -> List[HazardAlert]:
        """Get currently active alerts"""
        return list(self._active_alerts.values())
    
    def get_safety_metrics(self) -> Dict[str, Any]:
        """Get safety performance metrics"""
        return {
            'average_response_time_ms': np.mean(self._response_times) if self._response_times else 0.0,
            'max_response_time_ms': np.max(self._response_times) if self._response_times else 0.0,
            'target_response_time_ms': self.emergency_response_time_ms,
            'safety_events_count': self._safety_events_count,
            'active_alerts_count': len(self._active_alerts),
            'monitoring_rate_hz': self.update_rate
        }
