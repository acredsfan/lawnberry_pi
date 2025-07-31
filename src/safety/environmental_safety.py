"""
Environmental Safety System
Implements slope detection, surface analysis, and environmental monitoring using sensor fusion
"""

import asyncio
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import statistics

from ..hardware.data_structures import IMUReading, ToFReading, EnvironmentalReading, CameraFrame
from ..communication import MQTTClient, MessageProtocol
from .sensor_fusion_safety import SensorFusionSafetySystem, EnvironmentalConditions

logger = logging.getLogger(__name__)


class SurfaceType(Enum):
    """Types of surfaces detected"""
    GRASS_DRY = "grass_dry"
    GRASS_WET = "grass_wet"
    GRASS_THICK = "grass_thick"
    DIRT = "dirt"
    GRAVEL = "gravel"
    PAVEMENT = "pavement"
    MULCH = "mulch"
    LEAVES = "leaves"
    WATER = "water"
    UNKNOWN = "unknown"


class TerrainCondition(Enum):
    """Terrain conditions affecting safety"""
    SAFE = "safe"
    CAUTION = "caution"
    UNSAFE = "unsafe"
    PROHIBITED = "prohibited"


class WildlifeType(Enum):
    """Types of wildlife detected"""
    BIRD = "bird"
    SMALL_MAMMAL = "small_mammal"
    LARGE_MAMMAL = "large_mammal"
    REPTILE = "reptile"
    INSECT_SWARM = "insect_swarm"
    UNKNOWN = "unknown"


@dataclass
class SlopeAnalysis:
    """Slope analysis result"""
    angle_degrees: float
    direction: Tuple[float, float]  # Unit vector indicating slope direction
    confidence: float
    measurement_method: str  # "imu", "vision", "fusion"
    stability_factor: float  # 0.0 to 1.0, higher is more stable
    safety_assessment: TerrainCondition


@dataclass
class SurfaceAnalysis:
    """Surface condition analysis"""
    surface_type: SurfaceType
    moisture_level: float  # 0.0 to 1.0
    roughness: float  # 0.0 to 1.0
    grip_factor: float  # 0.0 to 1.0, higher is better grip
    mowing_suitability: float  # 0.0 to 1.0, higher is more suitable
    confidence: float
    analysis_method: str


@dataclass
class WildlifeDetection:
    """Wildlife detection result"""
    wildlife_type: WildlifeType
    position: Tuple[float, float, float]  # x, y, z relative to mower
    size_estimate: Tuple[float, float, float]  # width, height, depth
    movement_vector: Optional[Tuple[float, float, float]] = None
    threat_level: float = 0.0  # 0.0 to 1.0
    confidence: float = 0.0
    detection_method: str = "vision"
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class EnvironmentalHazard:
    """Environmental hazard assessment"""
    hazard_id: str
    hazard_type: str
    location: Tuple[float, float, float]
    severity: float  # 0.0 to 1.0
    recommended_action: str
    expiry_time: Optional[datetime] = None


class EnvironmentalSafetySystem:
    """Environmental safety system using sensor fusion"""
    
    def __init__(self, mqtt_client: MQTTClient, sensor_fusion: SensorFusionSafetySystem, 
                 config: Dict[str, Any]):
        self.mqtt_client = mqtt_client
        self.sensor_fusion = sensor_fusion
        self.config = config
        
        # Safety thresholds
        self.max_safe_slope = config.get('max_safe_slope_degrees', 15.0)
        self.caution_slope = config.get('caution_slope_degrees', 10.0)
        self.min_grip_factor = config.get('min_grip_factor', 0.6)
        self.min_stability_factor = config.get('min_stability_factor', 0.7)
        
        # Environmental monitoring
        self.slope_history: List[SlopeAnalysis] = []
        self.surface_history: List[SurfaceAnalysis] = []
        self.wildlife_detections: List[WildlifeDetection] = []
        self.environmental_hazards: Dict[str, EnvironmentalHazard] = {}
        
        # Current conditions
        self.current_slope: Optional[SlopeAnalysis] = None
        self.current_surface: Optional[SurfaceAnalysis] = None
        self.current_environmental_conditions: Optional[EnvironmentalConditions] = None
        
        # Sensor data buffers
        self.imu_buffer: List[IMUReading] = []
        self.tof_buffer: List[ToFReading] = []
        self.camera_buffer: List[Dict[str, Any]] = []
        self.env_buffer: List[EnvironmentalReading] = []
        
        # Analysis parameters
        self.analysis_window_size = 20  # Number of readings to analyze
        self.analysis_frequency_hz = 5  # Analysis frequency
        self.wildlife_detection_threshold = 0.7
        
        # Callbacks
        self.slope_callbacks: List[Callable] = []
        self.surface_callbacks: List[Callable] = []
        self.wildlife_callbacks: List[Callable] = []
        self.hazard_callbacks: List[Callable] = []
        
        # Tasks
        self._analysis_task: Optional[asyncio.Task] = None
        self._wildlife_monitoring_task: Optional[asyncio.Task] = None
        self._hazard_monitoring_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self):
        """Start environmental safety system"""
        logger.info("Starting environmental safety system")
        self._running = True
        
        # Subscribe to sensor data
        await self._subscribe_to_sensors()
        
        # Start analysis tasks
        self._analysis_task = asyncio.create_task(self._environmental_analysis_loop())
        self._wildlife_monitoring_task = asyncio.create_task(self._wildlife_monitoring_loop())
        self._hazard_monitoring_task = asyncio.create_task(self._hazard_monitoring_loop())
    
    async def stop(self):
        """Stop environmental safety system"""
        logger.info("Stopping environmental safety system")
        self._running = False
        
        for task in [self._analysis_task, self._wildlife_monitoring_task, self._hazard_monitoring_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    
    async def _subscribe_to_sensors(self):
        """Subscribe to sensor data streams"""
        await self.mqtt_client.subscribe("sensor/imu", self._handle_imu_data)
        await self.mqtt_client.subscribe("sensor/tof/combined", self._handle_tof_data)
        await self.mqtt_client.subscribe("vision/analysis", self._handle_vision_data)
        await self.mqtt_client.subscribe("sensor/environmental", self._handle_environmental_data)
    
    async def _handle_imu_data(self, data: Dict[str, Any]):
        """Handle IMU data for slope analysis"""
        imu_reading = IMUReading(
            timestamp=datetime.now(),
            acceleration_x=data.get('acceleration_x', 0.0),
            acceleration_y=data.get('acceleration_y', 0.0),
            acceleration_z=data.get('acceleration_z', 0.0),
            gyroscope_x=data.get('gyroscope_x', 0.0),
            gyroscope_y=data.get('gyroscope_y', 0.0),
            gyroscope_z=data.get('gyroscope_z', 0.0),
            magnetometer_x=data.get('magnetometer_x', 0.0),
            magnetometer_y=data.get('magnetometer_y', 0.0),
            magnetometer_z=data.get('magnetometer_z', 0.0),
            temperature=data.get('temperature', 20.0)
        )
        
        self.imu_buffer.append(imu_reading)
        if len(self.imu_buffer) > self.analysis_window_size:
            self.imu_buffer.pop(0)
    
    async def _handle_tof_data(self, data: Dict[str, Any]):
        """Handle ToF data for surface analysis"""
        tof_reading = ToFReading(
            timestamp=datetime.now(),
            distance=data.get('distance', 0.0),
            signal_strength=data.get('signal_strength', 0),
            ambient_light=data.get('ambient_light', 0),
            temperature=data.get('temperature', 20.0),
            sensor_id=data.get('sensor_id', 'combined')
        )
        
        self.tof_buffer.append(tof_reading)
        if len(self.tof_buffer) > self.analysis_window_size:
            self.tof_buffer.pop(0)
    
    async def _handle_vision_data(self, data: Dict[str, Any]):
        """Handle vision data for surface and wildlife analysis"""
        self.camera_buffer.append({
            'timestamp': datetime.now(),
            'data': data
        })
        if len(self.camera_buffer) > self.analysis_window_size:
            self.camera_buffer.pop(0)
    
    async def _handle_environmental_data(self, data: Dict[str, Any]):
        """Handle environmental sensor data"""
        env_reading = EnvironmentalReading(
            timestamp=datetime.now(),
            temperature=data.get('temperature', 20.0),
            humidity=data.get('humidity', 50.0),
            pressure=data.get('pressure', 1013.25),
            light_level=data.get('light_level', 1000.0),
            uv_index=data.get('uv_index', 0.0),
            wind_speed=data.get('wind_speed', 0.0),
            wind_direction=data.get('wind_direction', 0.0),
            precipitation=data.get('precipitation', False)
        )
        
        self.env_buffer.append(env_reading)
        if len(self.env_buffer) > self.analysis_window_size:
            self.env_buffer.pop(0)
    
    async def _environmental_analysis_loop(self):
        """Main environmental analysis loop"""
        while self._running:
            try:
                # Perform slope analysis
                if len(self.imu_buffer) >= 5:
                    slope_analysis = await self._analyze_slope()
                    if slope_analysis:
                        await self._process_slope_analysis(slope_analysis)
                
                # Perform surface analysis
                if len(self.tof_buffer) >= 5 and len(self.camera_buffer) >= 3:
                    surface_analysis = await self._analyze_surface()
                    if surface_analysis:
                        await self._process_surface_analysis(surface_analysis)
                
                # Sleep for analysis frequency
                await asyncio.sleep(1.0 / self.analysis_frequency_hz)
                
            except Exception as e:
                logger.error(f"Error in environmental analysis loop: {e}")
                await asyncio.sleep(1.0)
    
    async def _analyze_slope(self) -> Optional[SlopeAnalysis]:
        """Analyze slope using IMU data and sensor fusion"""
        if not self.imu_buffer:
            return None
        
        # Get recent IMU readings
        recent_readings = self.imu_buffer[-10:]
        
        # Calculate average accelerometer readings
        acc_x_values = [r.acceleration_x for r in recent_readings]
        acc_y_values = [r.acceleration_y for r in recent_readings]
        acc_z_values = [r.acceleration_z for r in recent_readings]
        
        avg_acc_x = statistics.mean(acc_x_values)
        avg_acc_y = statistics.mean(acc_y_values)
        avg_acc_z = statistics.mean(acc_z_values)
        
        # Calculate slope angle using gravity vector
        gravity_magnitude = np.sqrt(avg_acc_x**2 + avg_acc_y**2 + avg_acc_z**2)
        if gravity_magnitude < 0.1:  # Avoid division by zero
            return None
        
        # Normalize acceleration vector
        norm_acc_x = avg_acc_x / gravity_magnitude
        norm_acc_y = avg_acc_y / gravity_magnitude
        norm_acc_z = avg_acc_z / gravity_magnitude
        
        # Calculate slope angle (assuming Z is up when level)
        slope_angle = np.degrees(np.arccos(abs(norm_acc_z)))
        
        # Calculate slope direction
        slope_direction = np.array([norm_acc_x, norm_acc_y])
        if np.linalg.norm(slope_direction) > 0:
            slope_direction = slope_direction / np.linalg.norm(slope_direction)
        
        # Calculate confidence based on measurement stability
        acc_x_std = statistics.stdev(acc_x_values) if len(acc_x_values) > 1 else 0
        acc_y_std = statistics.stdev(acc_y_values) if len(acc_y_values) > 1 else 0
        acc_z_std = statistics.stdev(acc_z_values) if len(acc_z_values) > 1 else 0
        
        stability = 1.0 - min(1.0, (acc_x_std + acc_y_std + acc_z_std) / 3.0)
        confidence = max(0.1, stability)
        
        # Calculate stability factor
        stability_factor = max(0.0, 1.0 - (slope_angle / 45.0))  # Decreases with steeper slopes
        
        # Determine safety assessment
        if slope_angle > self.max_safe_slope:
            safety_assessment = TerrainCondition.UNSAFE
        elif slope_angle > self.caution_slope:
            safety_assessment = TerrainCondition.CAUTION
        else:
            safety_assessment = TerrainCondition.SAFE
        
        return SlopeAnalysis(
            angle_degrees=slope_angle,
            direction=tuple(slope_direction),
            confidence=confidence,
            measurement_method="imu",
            stability_factor=stability_factor,
            safety_assessment=safety_assessment
        )
    
    async def _analyze_surface(self) -> Optional[SurfaceAnalysis]:
        """Analyze surface conditions using ToF and vision data"""
        if not self.tof_buffer or not self.camera_buffer:
            return None
        
        # Analyze ToF data for surface roughness
        recent_tof = self.tof_buffer[-10:]
        distances = [r.distance for r in recent_tof]
        
        if not distances:
            return None
        
        # Calculate roughness from distance variation
        distance_std = statistics.stdev(distances) if len(distances) > 1 else 0
        roughness = min(1.0, distance_std / 0.1)  # Normalize to 0-1
        
        # Analyze vision data for surface type
        recent_vision = self.camera_buffer[-5:]
        surface_type = await self._classify_surface_from_vision(recent_vision)
        
        # Determine moisture level from environmental data
        moisture_level = await self._estimate_moisture_level()
        
        # Calculate grip factor based on surface type and conditions
        grip_factor = self._calculate_grip_factor(surface_type, moisture_level, roughness)
        
        # Calculate mowing suitability
        mowing_suitability = self._calculate_mowing_suitability(surface_type, moisture_level, grip_factor)
        
        # Overall confidence based on data quality
        tof_confidence = 1.0 - min(1.0, distance_std / 0.2)
        vision_confidence = 0.8  # Placeholder - would be based on vision analysis quality
        confidence = (tof_confidence + vision_confidence) / 2.0
        
        return SurfaceAnalysis(
            surface_type=surface_type,
            moisture_level=moisture_level,
            roughness=roughness,
            grip_factor=grip_factor,
            mowing_suitability=mowing_suitability,
            confidence=confidence,
            analysis_method="tof_vision_fusion"
        )
    
    async def _classify_surface_from_vision(self, vision_data: List[Dict[str, Any]]) -> SurfaceType:
        """Classify surface type from vision data"""
        # This is a simplified implementation
        # In practice, this would use computer vision algorithms
        
        if not vision_data:
            return SurfaceType.UNKNOWN
        
        # Analyze latest vision data
        latest_data = vision_data[-1]['data']
        
        # Look for surface indicators in vision data
        surface_features = latest_data.get('surface_features', {})
        
        # Simple classification based on features
        if surface_features.get('water_detected', False):
            return SurfaceType.WATER
        elif surface_features.get('vegetation_density', 0) > 0.8:
            return SurfaceType.GRASS_THICK
        elif surface_features.get('vegetation_density', 0) > 0.3:
            if surface_features.get('moisture_indicators', 0) > 0.6:
                return SurfaceType.GRASS_WET
            else:
                return SurfaceType.GRASS_DRY
        elif surface_features.get('hard_surface', False):
            return SurfaceType.PAVEMENT
        elif surface_features.get('loose_material', False):
            return SurfaceType.GRAVEL
        
        return SurfaceType.GRASS_DRY  # Default assumption
    
    async def _estimate_moisture_level(self) -> float:
        """Estimate surface moisture level from environmental data"""
        if not self.env_buffer:
            return 0.5  # Default moderate moisture
        
        recent_env = self.env_buffer[-5:]
        
        # Calculate moisture based on humidity and precipitation
        avg_humidity = statistics.mean([r.humidity for r in recent_env])
        has_precipitation = any([r.precipitation for r in recent_env])
        
        moisture_level = avg_humidity / 100.0
        if has_precipitation:
            moisture_level = min(1.0, moisture_level + 0.3)
        
        return moisture_level
    
    def _calculate_grip_factor(self, surface_type: SurfaceType, moisture_level: float, roughness: float) -> float:
        """Calculate grip factor based on surface conditions"""
        base_grip = {
            SurfaceType.GRASS_DRY: 0.8,
            SurfaceType.GRASS_WET: 0.5,
            SurfaceType.GRASS_THICK: 0.6,
            SurfaceType.DIRT: 0.7,
            SurfaceType.GRAVEL: 0.6,
            SurfaceType.PAVEMENT: 0.9,
            SurfaceType.MULCH: 0.4,
            SurfaceType.LEAVES: 0.3,
            SurfaceType.WATER: 0.0,
            SurfaceType.UNKNOWN: 0.5
        }
        
        grip = base_grip.get(surface_type, 0.5)
        
        # Adjust for moisture (wet surfaces generally have less grip)
        grip *= (1.0 - moisture_level * 0.4)
        
        # Adjust for roughness (some roughness can improve grip)
        optimal_roughness = 0.3
        roughness_factor = 1.0 - abs(roughness - optimal_roughness) * 0.5
        grip *= roughness_factor
        
        return max(0.0, min(1.0, grip))
    
    def _calculate_mowing_suitability(self, surface_type: SurfaceType, moisture_level: float, grip_factor: float) -> float:
        """Calculate mowing suitability score"""
        base_suitability = {
            SurfaceType.GRASS_DRY: 1.0,
            SurfaceType.GRASS_WET: 0.3,
            SurfaceType.GRASS_THICK: 0.7,
            SurfaceType.DIRT: 0.1,
            SurfaceType.GRAVEL: 0.0,
            SurfaceType.PAVEMENT: 0.0,
            SurfaceType.MULCH: 0.2,
            SurfaceType.LEAVES: 0.4,
            SurfaceType.WATER: 0.0,
            SurfaceType.UNKNOWN: 0.5
        }
        
        suitability = base_suitability.get(surface_type, 0.5)
        
        # Reduce suitability for wet conditions
        if moisture_level > 0.7:
            suitability *= 0.3
        elif moisture_level > 0.5:
            suitability *= 0.6
        
        # Factor in grip for safety
        suitability *= grip_factor
        
        return max(0.0, min(1.0, suitability))
    
    async def _process_slope_analysis(self, analysis: SlopeAnalysis):
        """Process slope analysis results"""
        self.current_slope = analysis
        self.slope_history.append(analysis)
        
        # Maintain history size
        if len(self.slope_history) > 100:
            self.slope_history.pop(0)
        
        # Check for unsafe slopes
        if analysis.safety_assessment in [TerrainCondition.UNSAFE, TerrainCondition.PROHIBITED]:
            await self._trigger_slope_safety_response(analysis)
        
        # Trigger callbacks
        for callback in self.slope_callbacks:
            try:
                await callback(analysis)
            except Exception as e:
                logger.error(f"Error in slope callback: {e}")
        
        # Publish slope data
        await self.mqtt_client.publish("safety/slope_analysis", {
            'angle_degrees': analysis.angle_degrees,
            'safety_assessment': analysis.safety_assessment.value,
            'stability_factor': analysis.stability_factor,
            'confidence': analysis.confidence,
            'timestamp': datetime.now().isoformat()
        })
    
    async def _process_surface_analysis(self, analysis: SurfaceAnalysis):
        """Process surface analysis results"""
        self.current_surface = analysis
        self.surface_history.append(analysis)
        
        # Maintain history size
        if len(self.surface_history) > 100:
            self.surface_history.pop(0)
        
        # Check for unsuitable surfaces
        if analysis.mowing_suitability < 0.3 or analysis.grip_factor < self.min_grip_factor:
            await self._trigger_surface_safety_response(analysis)
        
        # Trigger callbacks
        for callback in self.surface_callbacks:
            try:
                await callback(analysis)
            except Exception as e:
                logger.error(f"Error in surface callback: {e}")
        
        # Publish surface data
        await self.mqtt_client.publish("safety/surface_analysis", {
            'surface_type': analysis.surface_type.value,
            'moisture_level': analysis.moisture_level,
            'grip_factor': analysis.grip_factor,
            'mowing_suitability': analysis.mowing_suitability,
            'confidence': analysis.confidence,
            'timestamp': datetime.now().isoformat()
        })
    
    async def _trigger_slope_safety_response(self, analysis: SlopeAnalysis):
        """Trigger safety response for slope hazards"""
        hazard_id = f"slope_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        severity = 0.5
        if analysis.safety_assessment == TerrainCondition.UNSAFE:
            severity = 0.8
        elif analysis.safety_assessment == TerrainCondition.PROHIBITED:
            severity = 1.0
        
        recommended_action = "reduce_speed"
        if analysis.angle_degrees > self.max_safe_slope:
            recommended_action = "stop_mowing_return_to_safe_area"
        
        hazard = EnvironmentalHazard(
            hazard_id=hazard_id,
            hazard_type="unsafe_slope",
            location=(0.0, 0.0, 0.0),  # Current position
            severity=severity,
            recommended_action=recommended_action,
            expiry_time=datetime.now() + timedelta(minutes=5)
        )
        
        self.environmental_hazards[hazard_id] = hazard
        
        # Publish safety alert
        await self.mqtt_client.publish("safety/environmental_hazard", {
            'hazard_id': hazard_id,
            'type': 'unsafe_slope',
            'slope_angle': analysis.angle_degrees,
            'severity': severity,
            'action': recommended_action,
            'timestamp': datetime.now().isoformat()
        })
        
        logger.warning(f"Slope safety hazard detected: {analysis.angle_degrees:.1f}° slope")
    
    async def _trigger_surface_safety_response(self, analysis: SurfaceAnalysis):
        """Trigger safety response for surface hazards"""
        hazard_id = f"surface_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        severity = 1.0 - analysis.mowing_suitability
        
        if analysis.surface_type == SurfaceType.WATER:
            recommended_action = "emergency_stop_avoid_water"
            severity = 1.0
        elif analysis.grip_factor < self.min_grip_factor:
            recommended_action = "reduce_speed_increase_traction"
        else:
            recommended_action = "avoid_mowing_this_area"
        
        hazard = EnvironmentalHazard(
            hazard_id=hazard_id,
            hazard_type="unsuitable_surface",
            location=(0.0, 0.0, 0.0),  # Current position
            severity=severity,
            recommended_action=recommended_action,
            expiry_time=datetime.now() + timedelta(minutes=10)
        )
        
        self.environmental_hazards[hazard_id] = hazard
        
        # Publish safety alert
        await self.mqtt_client.publish("safety/environmental_hazard", {
            'hazard_id': hazard_id,
            'type': 'unsuitable_surface',
            'surface_type': analysis.surface_type.value,
            'grip_factor': analysis.grip_factor,
            'mowing_suitability': analysis.mowing_suitability,
            'severity': severity,
            'action': recommended_action,
            'timestamp': datetime.now().isoformat()
        })
        
        logger.warning(f"Surface safety hazard detected: {analysis.surface_type.value} with grip {analysis.grip_factor:.2f}")
    
    async def _wildlife_monitoring_loop(self):
        """Monitor for wildlife detection"""
        while self._running:
            try:
                if self.camera_buffer:
                    # Analyze recent camera data for wildlife
                    wildlife_detections = await self._detect_wildlife()
                    for detection in wildlife_detections:
                        await self._process_wildlife_detection(detection)
                
                await asyncio.sleep(2.0)  # Check every 2 seconds
                
            except Exception as e:
                logger.error(f"Error in wildlife monitoring loop: {e}")
                await asyncio.sleep(2.0)
    
    async def _detect_wildlife(self) -> List[WildlifeDetection]:
        """Detect wildlife from camera data"""
        detections = []
        
        if not self.camera_buffer:
            return detections
        
        recent_data = self.camera_buffer[-3:]  # Last 3 frames
        
        for frame_data in recent_data:
            vision_data = frame_data['data']
            objects = vision_data.get('detected_objects', [])
            
            for obj in objects:
                obj_class = obj.get('class', '').lower()
                confidence = obj.get('confidence', 0.0)
                
                if confidence < self.wildlife_detection_threshold:
                    continue
                
                # Classify wildlife type
                wildlife_type = self._classify_wildlife(obj_class)
                if wildlife_type == WildlifeType.UNKNOWN:
                    continue
                
                # Extract position and size
                position = (
                    obj.get('distance', 1.0),
                    obj.get('x_offset', 0.0),
                    obj.get('height_offset', 0.0)
                )
                
                size = (
                    obj.get('width', 0.2),
                    obj.get('height', 0.2),
                    obj.get('depth', 0.2)
                )
                
                # Calculate threat level
                threat_level = self._calculate_wildlife_threat(wildlife_type, position, obj)
                
                detection = WildlifeDetection(
                    wildlife_type=wildlife_type,
                    position=position,
                    size_estimate=size,
                    threat_level=threat_level,
                    confidence=confidence,
                    detection_method="vision",
                    timestamp=frame_data['timestamp']
                )
                
                detections.append(detection)
        
        return detections
    
    def _classify_wildlife(self, obj_class: str) -> WildlifeType:
        """Classify detected object as wildlife type"""
        wildlife_mapping = {
            'bird': WildlifeType.BIRD,
            'cat': WildlifeType.SMALL_MAMMAL,
            'dog': WildlifeType.LARGE_MAMMAL,
            'rabbit': WildlifeType.SMALL_MAMMAL,
            'squirrel': WildlifeType.SMALL_MAMMAL,
            'deer': WildlifeType.LARGE_MAMMAL,
            'snake': WildlifeType.REPTILE,
            'lizard': WildlifeType.REPTILE,
            'bee': WildlifeType.INSECT_SWARM,
            'wasp': WildlifeType.INSECT_SWARM
        }
        
        return wildlife_mapping.get(obj_class, WildlifeType.UNKNOWN)
    
    def _calculate_wildlife_threat(self, wildlife_type: WildlifeType, position: Tuple[float, float, float], 
                                 obj_data: Dict[str, Any]) -> float:
        """Calculate threat level for wildlife detection"""
        distance = position[0]  # Distance from mower
        
        # Base threat levels
        base_threat = {
            WildlifeType.BIRD: 0.3,
            WildlifeType.SMALL_MAMMAL: 0.6,
            WildlifeType.LARGE_MAMMAL: 0.8,
            WildlifeType.REPTILE: 0.4,
            WildlifeType.INSECT_SWARM: 0.2,
            WildlifeType.UNKNOWN: 0.5
        }
        
        threat = base_threat.get(wildlife_type, 0.5)
        
        # Increase threat for closer animals
        if distance < 0.5:
            threat = min(1.0, threat * 2.0)
        elif distance < 1.0:
            threat = min(1.0, threat * 1.5)
        
        # Increase threat for larger animals
        size = obj_data.get('size_estimate', 0.2)
        if size > 0.5:
            threat = min(1.0, threat * 1.3)
        
        return threat
    
    async def _process_wildlife_detection(self, detection: WildlifeDetection):
        """Process wildlife detection"""
        self.wildlife_detections.append(detection)
        
        # Maintain detection history
        if len(self.wildlife_detections) > 100:
            self.wildlife_detections.pop(0)
        
        # Trigger safety response for high-threat wildlife
        if detection.threat_level > 0.7:
            await self._trigger_wildlife_safety_response(detection)
        
        # Trigger callbacks
        for callback in self.wildlife_callbacks:
            try:
                await callback(detection)
            except Exception as e:
                logger.error(f"Error in wildlife callback: {e}")
        
        # Publish wildlife detection
        await self.mqtt_client.publish("safety/wildlife_detection", {
            'wildlife_type': detection.wildlife_type.value,
            'position': detection.position,
            'threat_level': detection.threat_level,
            'confidence': detection.confidence,
            'timestamp': detection.timestamp.isoformat()
        })
    
    async def _trigger_wildlife_safety_response(self, detection: WildlifeDetection):
        """Trigger safety response for wildlife detection"""
        hazard_id = f"wildlife_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        # Determine action based on wildlife type and threat level
        if detection.wildlife_type == WildlifeType.LARGE_MAMMAL and detection.threat_level > 0.8:
            recommended_action = "emergency_stop_avoid_animal"
        elif detection.threat_level > 0.7:
            recommended_action = "stop_mowing_wait_for_animal_to_move"
        else:
            recommended_action = "reduce_speed_monitor_animal"
        
        hazard = EnvironmentalHazard(
            hazard_id=hazard_id,
            hazard_type="wildlife_detected",
            location=detection.position,
            severity=detection.threat_level,
            recommended_action=recommended_action,
            expiry_time=datetime.now() + timedelta(minutes=2)
        )
        
        self.environmental_hazards[hazard_id] = hazard
        
        # Publish safety alert
        await self.mqtt_client.publish("safety/environmental_hazard", {
            'hazard_id': hazard_id,
            'type': 'wildlife_detected',
            'wildlife_type': detection.wildlife_type.value,
            'position': detection.position,
            'threat_level': detection.threat_level,
            'action': recommended_action,
            'timestamp': datetime.now().isoformat()
        })
        
        logger.warning(f"Wildlife safety response: {detection.wildlife_type.value} detected with threat level {detection.threat_level:.2f}")
    
    async def _hazard_monitoring_loop(self):
        """Monitor and cleanup expired hazards"""
        while self._running:
            try:
                current_time = datetime.now()
                expired_hazards = []
                
                for hazard_id, hazard in self.environmental_hazards.items():
                    if hazard.expiry_time and hazard.expiry_time < current_time:
                        expired_hazards.append(hazard_id)
                
                # Remove expired hazards
                for hazard_id in expired_hazards:
                    del self.environmental_hazards[hazard_id]
                    logger.debug(f"Expired environmental hazard: {hazard_id}")
                
                await asyncio.sleep(30.0)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in hazard monitoring loop: {e}")
                await asyncio.sleep(30.0)
    
    def register_slope_callback(self, callback: Callable):
        """Register callback for slope analysis"""
        self.slope_callbacks.append(callback)
    
    def register_surface_callback(self, callback: Callable):
        """Register callback for surface analysis"""
        self.surface_callbacks.append(callback)
    
    def register_wildlife_callback(self, callback: Callable):
        """Register callback for wildlife detection"""
        self.wildlife_callbacks.append(callback)
    
    def register_hazard_callback(self, callback: Callable):
        """Register callback for environmental hazards"""
        self.hazard_callbacks.append(callback)
    
    async def get_environmental_status(self) -> Dict[str, Any]:
        """Get comprehensive environmental safety status"""
        return {
            "current_slope": {
                "angle_degrees": self.current_slope.angle_degrees if self.current_slope else None,
                "safety_assessment": self.current_slope.safety_assessment.value if self.current_slope else None,
                "stability_factor": self.current_slope.stability_factor if self.current_slope else None
            },
            "current_surface": {
                "surface_type": self.current_surface.surface_type.value if self.current_surface else None,
                "moisture_level": self.current_surface.moisture_level if self.current_surface else None,
                "grip_factor": self.current_surface.grip_factor if self.current_surface else None,
                "mowing_suitability": self.current_surface.mowing_suitability if self.current_surface else None
            },
            "active_hazards": len(self.environmental_hazards),
            "recent_wildlife_detections": len([d for d in self.wildlife_detections if (datetime.now() - d.timestamp).seconds < 300]),
            "safety_thresholds": {
                "max_safe_slope": self.max_safe_slope,
                "min_grip_factor": self.min_grip_factor,
                "min_stability_factor": self.min_stability_factor
            }
        }
