"""
Localization system with GPS-RTK integration, IMU processing, and Kalman filtering
"""

import asyncio
import numpy as np
from datetime import datetime
from typing import Optional, Tuple, Dict, Any
import logging
from dataclasses import dataclass

from ..hardware.data_structures import GPSReading, IMUReading, RoboHATStatus
from ..communication import MQTTClient, MessageProtocol, SensorData
from .data_structures import PoseEstimate, LocalizationData


logger = logging.getLogger(__name__)


@dataclass
class KalmanState:
    """Extended Kalman Filter state for sensor fusion"""
    # State vector: [x, y, z, vx, vy, vz, qw, qx, qy, qz, wx, wy, wz]
    # Position (3), velocity (3), quaternion (4), angular velocity (3) = 13 states
    state: np.ndarray
    covariance: np.ndarray
    timestamp: datetime
    
    def __post_init__(self):
        if self.state.shape != (13,):
            raise ValueError("State vector must have 13 elements")
        if self.covariance.shape != (13, 13):
            raise ValueError("Covariance matrix must be 13x13")


class LocalizationSystem:
    """
    Localization system combining GPS-RTK, IMU, and wheel encoder data
    using Extended Kalman Filter for accurate position estimation
    """
    
    def __init__(self, mqtt_client: MQTTClient):
        self.mqtt_client = mqtt_client
        self.update_rate = 10  # Hz for navigation
        self.safety_update_rate = 20  # Hz for safety functions
        
        # Current state
        self._current_pose: Optional[PoseEstimate] = None
        self._kalman_state: Optional[KalmanState] = None
        
        # Reference point for local coordinates (set on first GPS fix)
        self._reference_lat: Optional[float] = None
        self._reference_lon: Optional[float] = None
        self._reference_alt: Optional[float] = None
        
        # Sensor data buffers
        self._latest_gps: Optional[GPSReading] = None
        self._latest_imu: Optional[IMUReading] = None
        self._latest_encoder: Optional[RoboHATStatus] = None
        
        # Process noise parameters
        self._process_noise_position = 0.01  # m/s²
        self._process_noise_velocity = 0.1   # m/s²
        self._process_noise_orientation = 0.01  # rad/s
        self._process_noise_angular_vel = 0.1   # rad/s²
        
        # Measurement noise parameters  
        self._gps_noise_position = 0.05  # meters (RTK accuracy)
        self._imu_noise_orientation = 0.01  # rad
        self._encoder_noise_velocity = 0.1  # m/s
        
        # Tasks
        self._localization_task: Optional[asyncio.Task] = None
        self._safety_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Performance tracking
        self._update_count = 0
        self._last_update_time = datetime.now()
        
    async def start(self):
        """Start the localization system"""
        logger.info("Starting localization system")
        self._running = True
        
        # Subscribe to sensor data
        await self._subscribe_to_sensors()
        
        # Start processing tasks
        self._localization_task = asyncio.create_task(self._localization_loop())
        self._safety_task = asyncio.create_task(self._safety_loop())
        
    async def stop(self):
        """Stop the localization system"""
        logger.info("Stopping localization system")
        self._running = False
        
        if self._localization_task:
            self._localization_task.cancel()
            try:
                await self._localization_task
            except asyncio.CancelledError:
                pass
                
        if self._safety_task:
            self._safety_task.cancel()
            try:
                await self._safety_task
            except asyncio.CancelledError:
                pass
    
    async def _subscribe_to_sensors(self):
        """Subscribe to sensor data topics"""
        topics = [
            ("lawnberry/sensors/gps", self._handle_gps_data),
            ("lawnberry/sensors/imu", self._handle_imu_data),
            ("lawnberry/sensors/robohat", self._handle_encoder_data),
        ]
        for topic, handler in topics:
            await self.mqtt_client.subscribe(topic)
            self.mqtt_client.add_message_handler(topic, handler)
    
    async def _handle_gps_data(self, topic: str, message: MessageProtocol):
        """Handle GPS sensor data"""
        try:
            gps_data = message.payload
            self._latest_gps = GPSReading(
                timestamp=datetime.fromtimestamp(message.metadata.timestamp),
                sensor_id=gps_data.get('sensor_id', 'gps'),
                value=gps_data,
                unit='degrees',
                port=gps_data.get('port', '/dev/ttyACM1'),
                baud_rate=gps_data.get('baud_rate', 115200),
                latitude=gps_data['latitude'],
                longitude=gps_data['longitude'],
                altitude=gps_data['altitude'],
                accuracy=gps_data['accuracy'],
                satellites=gps_data['satellites'],
                fix_type=gps_data['fix_type']
            )
            
            # Set reference point on first RTK fix
            if self._reference_lat is None and self._latest_gps.fix_type == 'rtk':
                self._set_reference_point(
                    self._latest_gps.latitude,
                    self._latest_gps.longitude, 
                    self._latest_gps.altitude
                )
                logger.info(f"Reference point set: {self._reference_lat:.8f}, {self._reference_lon:.8f}")
                
        except Exception as e:
            logger.error(f"Error processing GPS data: {e}")
    
    async def _handle_imu_data(self, topic: str, message: MessageProtocol):
        """Handle IMU sensor data"""
        try:
            # Accept either (topic, message) where message has .payload, or
            # direct dict-like payloads used by some tests. Support nested
            # shapes where sensor values may be under a 'value' key.
            raw = None
            if isinstance(message, dict):
                raw = message
                timestamp_val = message.get('timestamp', None)
            else:
                raw = getattr(message, 'payload', None) or {}
                timestamp_val = getattr(getattr(message, 'metadata', None), 'timestamp', None)

            def _get(key, default=None):
                # Look in raw, then in raw.get('value', {}) for legacy shapes
                if not raw:
                    return default
                if key in raw:
                    return raw.get(key)
                val = raw.get('value') if isinstance(raw, dict) else None
                if isinstance(val, dict) and key in val:
                    return val.get(key)
                return default

            quat = _get('quaternion') or _get('orientation')
            accel = _get('acceleration')
            angvel = _get('angular_velocity') or _get('gyroscope')
            mag = _get('magnetic_field')

            # Normalize to tuples with sensible defaults
            try:
                quaternion = tuple(quat) if quat is not None else (0.0, 0.0, 0.0, 1.0)
            except Exception:
                quaternion = (0.0, 0.0, 0.0, 1.0)

            try:
                acceleration = tuple(accel) if accel is not None else (0.0, 0.0, 0.0)
            except Exception:
                # Accept dict with x,y,z
                if isinstance(accel, dict):
                    acceleration = (
                        float(accel.get('x', 0.0)),
                        float(accel.get('y', 0.0)),
                        float(accel.get('z', 0.0))
                    )
                else:
                    acceleration = (0.0, 0.0, 0.0)

            try:
                angular_velocity = tuple(angvel) if angvel is not None else (0.0, 0.0, 0.0)
            except Exception:
                if isinstance(angvel, dict):
                    angular_velocity = (
                        float(angvel.get('x', 0.0)),
                        float(angvel.get('y', 0.0)),
                        float(angvel.get('z', 0.0))
                    )
                else:
                    angular_velocity = (0.0, 0.0, 0.0)

            try:
                magnetic_field = tuple(mag) if mag is not None else None
            except Exception:
                magnetic_field = None

            ts = datetime.fromtimestamp(timestamp_val) if timestamp_val is not None else datetime.now()

            self._latest_imu = IMUReading(
                timestamp=ts,
                sensor_id=_get('sensor_id', 'bno085'),
                value=raw,
                unit='mixed',
                port=_get('port', '/dev/ttyAMA4'),
                baud_rate=_get('baud_rate', 115200),
                quaternion=quaternion,
                acceleration=acceleration,
                angular_velocity=angular_velocity,
                magnetic_field=magnetic_field
            )
        except Exception as e:
            logger.error(f"Error processing IMU data: {e}")
    
    async def _handle_encoder_data(self, topic: str, message: MessageProtocol):
        """Handle wheel encoder data from RoboHAT"""
        try:
            encoder_data = message.payload
            self._latest_encoder = RoboHATStatus(
                timestamp=datetime.fromtimestamp(message.metadata.timestamp),
                rc_enabled=encoder_data['rc_enabled'],
                steer_pwm=encoder_data['steer_pwm'],
                throttle_pwm=encoder_data['throttle_pwm'],
                encoder_position=encoder_data['encoder_position'],
                connection_active=encoder_data['connection_active']
            )
        except Exception as e:
            logger.error(f"Error processing encoder data: {e}")
    
    def _set_reference_point(self, lat: float, lon: float, alt: float):
        """Set reference point for local coordinate system"""
        self._reference_lat = lat
        self._reference_lon = lon
        self._reference_alt = alt
        
        # Initialize Kalman filter with first position
        self._initialize_kalman_filter(lat, lon, alt)
    
    def _initialize_kalman_filter(self, lat: float, lon: float, alt: float):
        """Initialize Extended Kalman Filter"""
        # Initial state: [x, y, z, vx, vy, vz, qw, qx, qy, qz, wx, wy, wz]
        initial_state = np.zeros(13)
        initial_state[0:3] = [0, 0, 0]  # Position (local coordinates start at origin)
        initial_state[3:6] = [0, 0, 0]  # Velocity
        initial_state[6:10] = [1, 0, 0, 0]  # Quaternion (identity)
        initial_state[10:13] = [0, 0, 0]  # Angular velocity
        
        # Initial covariance (high uncertainty initially)
        initial_covariance = np.eye(13)
        initial_covariance[0:3, 0:3] *= 1.0  # Position uncertainty (1m)
        initial_covariance[3:6, 3:6] *= 0.1  # Velocity uncertainty (0.1 m/s)
        initial_covariance[6:10, 6:10] *= 0.1  # Orientation uncertainty
        initial_covariance[10:13, 10:13] *= 0.1  # Angular velocity uncertainty
        
        self._kalman_state = KalmanState(
            state=initial_state,
            covariance=initial_covariance,
            timestamp=datetime.now()
        )
        
        logger.info("Kalman filter initialized")
    
    def _gps_to_local(self, lat: float, lon: float, alt: float) -> Tuple[float, float, float]:
        """Convert GPS coordinates to local Cartesian coordinates"""
        if self._reference_lat is None:
            return 0.0, 0.0, 0.0
        
        # Simple flat-earth approximation for local coordinates
        # For more accuracy, could use UTM projection
        R_earth = 6378137.0  # Earth radius in meters
        
        dlat = np.radians(lat - self._reference_lat)
        dlon = np.radians(lon - self._reference_lon)
        
        x = R_earth * dlon * np.cos(np.radians(self._reference_lat))
        y = R_earth * dlat
        z = alt - self._reference_alt
        
        return x, y, z
    
    def _local_to_gps(self, x: float, y: float, z: float) -> Tuple[float, float, float]:
        """Convert local Cartesian coordinates to GPS coordinates"""
        if self._reference_lat is None:
            return 0.0, 0.0, 0.0
        
        R_earth = 6378137.0  # Earth radius in meters
        
        dlat = y / R_earth
        dlon = x / (R_earth * np.cos(np.radians(self._reference_lat)))
        
        lat = self._reference_lat + np.degrees(dlat)
        lon = self._reference_lon + np.degrees(dlon)
        alt = self._reference_alt + z
        
        return lat, lon, alt
    
    async def _localization_loop(self):
        """Main localization processing loop (10Hz)"""
        while self._running:
            try:
                await self._update_localization()
                await asyncio.sleep(1.0 / self.update_rate)
            except Exception as e:
                logger.error(f"Error in localization loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _safety_loop(self):
        """Safety-critical localization updates (20Hz)"""
        while self._running:
            try:
                await self._update_safety_pose()
                await asyncio.sleep(1.0 / self.safety_update_rate)
            except Exception as e:
                logger.error(f"Error in safety loop: {e}")
                await asyncio.sleep(0.05)
    
    async def _update_localization(self):
        """Update localization using Kalman filter"""
        if self._kalman_state is None:
            return
        
        current_time = datetime.now()
        dt = (current_time - self._kalman_state.timestamp).total_seconds()
        
        if dt <= 0:
            return
        
        # Prediction step
        self._predict_state(dt)
        
        # Update with GPS if available
        if self._latest_gps and self._latest_gps.fix_type in ['3d', 'rtk']:
            await self._update_with_gps()
        
        # Update with IMU
        if self._latest_imu:
            await self._update_with_imu()
        
        # Update with encoder data
        if self._latest_encoder:
            await self._update_with_encoder()
        
        # Generate pose estimate
        pose = self._generate_pose_estimate()
        self._current_pose = pose
        
        # Publish localization data
        await self._publish_localization_data()
        
        # Update timestamp
        self._kalman_state.timestamp = current_time
        self._update_count += 1
    
    def _predict_state(self, dt: float):
        """Predict state using motion model"""
        if self._kalman_state is None:
            return
        
        # State transition model (constant velocity + angular motion)
        F = np.eye(13)
        
        # Position = position + velocity * dt
        F[0:3, 3:6] = np.eye(3) * dt
        
        # Quaternion integration with angular velocity
        # Simplified: quaternion remains constant (will be corrected by measurements)
        
        # Predict state
        self._kalman_state.state = F @ self._kalman_state.state
        
        # Process noise matrix
        Q = np.eye(13)
        Q[0:3, 0:3] *= self._process_noise_position * dt**2
        Q[3:6, 3:6] *= self._process_noise_velocity * dt
        Q[6:10, 6:10] *= self._process_noise_orientation * dt
        Q[10:13, 10:13] *= self._process_noise_angular_vel * dt
        
        # Predict covariance
        self._kalman_state.covariance = F @ self._kalman_state.covariance @ F.T + Q
    
    async def _update_with_gps(self):
        """Update Kalman filter with GPS measurement"""
        if not self._latest_gps or self._kalman_state is None:
            return
        
        # Convert GPS to local coordinates
        x_gps, y_gps, z_gps = self._gps_to_local(
            self._latest_gps.latitude,
            self._latest_gps.longitude,
            self._latest_gps.altitude
        )
        
        # Measurement vector (position only)
        z = np.array([x_gps, y_gps, z_gps])
        
        # Measurement matrix (observe position states)
        H = np.zeros((3, 13))
        H[0:3, 0:3] = np.eye(3)
        
        # Measurement noise (based on GPS accuracy)
        R = np.eye(3) * max(self._latest_gps.accuracy, self._gps_noise_position)**2
        
        # Innovation
        y = z - H @ self._kalman_state.state
        
        # Innovation covariance
        S = H @ self._kalman_state.covariance @ H.T + R
        
        # Kalman gain
        K = self._kalman_state.covariance @ H.T @ np.linalg.inv(S)
        
        # Update state and covariance
        self._kalman_state.state = self._kalman_state.state + K @ y
        I_KH = np.eye(13) - K @ H
        self._kalman_state.covariance = I_KH @ self._kalman_state.covariance
    
    async def _update_with_imu(self):
        """Update Kalman filter with IMU measurement"""
        if not self._latest_imu or self._kalman_state is None:
            return
        
        # Update orientation from quaternion
        qw, qx, qy, qz = self._latest_imu.quaternion
        
        # Measurement vector (quaternion)
        z = np.array([qw, qx, qy, qz])
        
        # Measurement matrix (observe quaternion states)
        H = np.zeros((4, 13))
        H[0:4, 6:10] = np.eye(4)
        
        # Measurement noise
        R = np.eye(4) * self._imu_noise_orientation**2
        
        # Innovation
        y = z - H @ self._kalman_state.state
        
        # Innovation covariance
        S = H @ self._kalman_state.covariance @ H.T + R
        
        # Kalman gain
        K = self._kalman_state.covariance @ H.T @ np.linalg.inv(S)
        
        # Update state and covariance
        self._kalman_state.state = self._kalman_state.state + K @ y
        I_KH = np.eye(13) - K @ H
        self._kalman_state.covariance = I_KH @ self._kalman_state.covariance
        
        # Normalize quaternion
        q_norm = np.linalg.norm(self._kalman_state.state[6:10])
        if q_norm > 0:
            self._kalman_state.state[6:10] /= q_norm
        
        # Update angular velocity
        self._kalman_state.state[10:13] = np.array(self._latest_imu.angular_velocity)
    
    async def _update_with_encoder(self):
        """Update Kalman filter with wheel encoder data"""
        # This would estimate velocity from encoder changes
        # Implementation depends on encoder setup and wheel parameters
        pass
    
    def _generate_pose_estimate(self) -> PoseEstimate:
        """Generate pose estimate from current Kalman state"""
        if self._kalman_state is None:
            return None
        
        state = self._kalman_state.state
        
        # Convert local position back to GPS coordinates
        lat, lon, alt = self._local_to_gps(state[0], state[1], state[2])
        
        # Extract covariance for position and orientation (6x6)
        pose_covariance = np.zeros((6, 6))
        pose_covariance[0:3, 0:3] = self._kalman_state.covariance[0:3, 0:3]  # Position
        pose_covariance[3:6, 3:6] = self._kalman_state.covariance[6:9, 6:9]  # Orientation (3x3 from quaternion)
        
        return PoseEstimate(
            timestamp=datetime.now(),
            latitude=lat,
            longitude=lon,
            altitude=alt,
            x=state[0],
            y=state[1],
            z=state[2],
            qw=state[6],
            qx=state[7],
            qy=state[8],
            qz=state[9],
            vx=state[3],
            vy=state[4],
            vz=state[5],
            wx=state[10],
            wy=state[11],
            wz=state[12],
            covariance=pose_covariance,
            gps_accuracy=self._latest_gps.accuracy if self._latest_gps else 0.0,
            imu_quality=1.0,  # Could be calculated from IMU calibration status
            fusion_confidence=self._calculate_fusion_confidence()
        )
    
    def _calculate_fusion_confidence(self) -> float:
        """Calculate fusion confidence based on sensor health and covariance"""
        if self._kalman_state is None:
            return 0.0
        
        # Base confidence on position uncertainty
        pos_uncertainty = np.trace(self._kalman_state.covariance[0:3, 0:3])
        confidence = 1.0 / (1.0 + pos_uncertainty)
        
        # Factor in GPS availability and quality
        if self._latest_gps:
            if self._latest_gps.fix_type == 'rtk':
                confidence *= 1.0
            elif self._latest_gps.fix_type == '3d':
                confidence *= 0.8
            else:
                confidence *= 0.5
        else:
            confidence *= 0.3
        
        return min(confidence, 1.0)
    
    async def _update_safety_pose(self):
        """Fast update for safety-critical pose information"""
        # Provide latest pose estimate for safety systems
        if self._current_pose:
            safety_data = {
                'pose': {
                    'x': self._current_pose.x,
                    'y': self._current_pose.y,
                    'z': self._current_pose.z,
                    'qw': self._current_pose.qw,
                    'qx': self._current_pose.qx,
                    'qy': self._current_pose.qy,
                    'qz': self._current_pose.qz,
                    'timestamp': self._current_pose.timestamp.isoformat()
                },
                'confidence': self._current_pose.fusion_confidence
            }
            
            message = SensorData.create(
                sender="localization_system",
                sensor_type="pose_safety",
                data=safety_data
            )
            
            await self.mqtt_client.publish("lawnberry/safety/pose", message)
    
    async def _publish_localization_data(self):
        """Publish localization data to MQTT"""
        if not self._current_pose:
            return
        
        localization_data = LocalizationData(
            pose=self._current_pose,
            gps_fix_type=self._latest_gps.fix_type if self._latest_gps else 'none',
            satellites_visible=self._latest_gps.satellites if self._latest_gps else 0,
            wheel_encoder_position=self._latest_encoder.encoder_position if self._latest_encoder else 0,
            estimated_distance_traveled=0.0,  # Would calculate from encoder changes
            filter_state=self._kalman_state.state if self._kalman_state else None,
            filter_covariance=self._kalman_state.covariance if self._kalman_state else None
        )
        
        # Convert to publishable format
        data = {
            'pose': {
                'timestamp': self._current_pose.timestamp.isoformat(),
                'latitude': self._current_pose.latitude,
                'longitude': self._current_pose.longitude,
                'altitude': self._current_pose.altitude,
                'x': self._current_pose.x,
                'y': self._current_pose.y,
                'z': self._current_pose.z,
                'qw': self._current_pose.qw,
                'qx': self._current_pose.qx,
                'qy': self._current_pose.qy,
                'qz': self._current_pose.qz,
                'vx': self._current_pose.vx,
                'vy': self._current_pose.vy,
                'vz': self._current_pose.vz,
                'wx': self._current_pose.wx,
                'wy': self._current_pose.wy,
                'wz': self._current_pose.wz,
                'gps_accuracy': self._current_pose.gps_accuracy,
                'fusion_confidence': self._current_pose.fusion_confidence
            },
            'gps_fix_type': localization_data.gps_fix_type,
            'satellites_visible': localization_data.satellites_visible,
            'wheel_encoder_position': localization_data.wheel_encoder_position,
            'update_count': self._update_count
        }
        
        message = SensorData.create(
            sender="localization_system",
            sensor_type="localization",
            data=data
        )
        
        await self.mqtt_client.publish("lawnberry/sensors/localization", message)
    
    def get_current_pose(self) -> Optional[PoseEstimate]:
        """Get current pose estimate"""
        return self._current_pose
    
    def get_position_accuracy(self) -> float:
        """Get current position accuracy estimate in meters"""
        if not self._kalman_state:
            return float('inf')
        
        # Return trace of position covariance as accuracy estimate
        return np.sqrt(np.trace(self._kalman_state.covariance[0:3, 0:3]))
