"""
Comprehensive Power Management System
Handles battery monitoring, solar charging, and intelligent power optimization.
"""

import asyncio
import logging
import json
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import math
import statistics

# Optional heavy dependencies: numpy and scikit-learn may not be installed in test
try:
    import numpy as np
except Exception:
    np = None

try:
    from sklearn.linear_model import LinearRegression
    from sklearn.ensemble import RandomForestRegressor
    SKLEARN_AVAILABLE = True
except Exception:
    SKLEARN_AVAILABLE = False

    # Lightweight fallbacks to avoid import errors during tests. These do not provide
    # real ML functionality but keep the code paths runnable in CI/dev without scikit-learn.
    class LinearRegression:
        def fit(self, X, y):
            return None

        def predict(self, X):
            # Return zeros matching expected shape
            return [0 for _ in range(len(X))]

    class RandomForestRegressor:
        def __init__(self, *args, **kwargs):
            pass

        def fit(self, X, y):
            return None

        def predict(self, X):
            return [0 for _ in range(len(X))]
import pickle
import os

from ..hardware.hardware_interface import HardwareInterface
from ..communication.client import MQTTClient
from ..data_management.cache_manager import CacheManager
from ..weather.weather_service import WeatherService


class PowerMode(Enum):
    """Power management operational modes"""
    HIGH_PERFORMANCE = "high_performance"
    ECO_MODE = "eco_mode"
    CHARGING_MODE = "charging_mode"
    EMERGENCY_MODE = "emergency_mode"


class ChargingMode(Enum):
    """Charging strategy modes"""
    AUTO = "auto"
    MANUAL = "manual"
    ECO = "eco"


class PowerOptimizationProfile(Enum):
    """User-configurable power optimization profiles"""
    MAXIMUM_PERFORMANCE = "max_performance"
    BALANCED = "balanced"
    POWER_SAVER = "power_saver"
    MAXIMUM_EFFICIENCY = "max_efficiency"
    CUSTOM = "custom"


@dataclass
class PowerProfile:
    """User-configurable power profile settings"""
    name: str
    performance_weight: float  # 0.0 to 1.0
    efficiency_weight: float   # 0.0 to 1.0
    cpu_governor: str
    sensor_reduction_factor: float  # 0.0 to 1.0
    camera_quality_factor: float   # 0.0 to 1.0
    motor_efficiency_mode: bool
    description: str


@dataclass
class MLPrediction:
    """Machine learning prediction result"""
    value: float
    confidence: float
    model_version: str
    timestamp: datetime


class ChargingLocationML:
    """Machine learning for optimal charging location prediction"""
    
    def __init__(self):
        self.solar_efficiency_model = None
        self.weather_pattern_model = None
        self.seasonal_model = None
        self.model_path = "data/ml_models/charging_location"
        self._training_data = []
        
    async def initialize(self):
        """Initialize ML models"""
        os.makedirs(self.model_path, exist_ok=True)
        await self._load_models()
        
    async def _load_models(self):
        """Load trained models from disk"""
        try:
            solar_model_path = os.path.join(self.model_path, "solar_efficiency.pkl")
            if os.path.exists(solar_model_path):
                with open(solar_model_path, 'rb') as f:
                    self.solar_efficiency_model = pickle.load(f)
                    
            weather_model_path = os.path.join(self.model_path, "weather_pattern.pkl")
            if os.path.exists(weather_model_path):
                with open(weather_model_path, 'rb') as f:
                    self.weather_pattern_model = pickle.load(f)
                    
            seasonal_model_path = os.path.join(self.model_path, "seasonal.pkl")
            if os.path.exists(seasonal_model_path):
                with open(seasonal_model_path, 'rb') as f:
                    self.seasonal_model = pickle.load(f)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Could not load ML models: {e}")
            
    async def _save_models(self):
        """Save trained models to disk"""
        try:
            if self.solar_efficiency_model:
                with open(os.path.join(self.model_path, "solar_efficiency.pkl"), 'wb') as f:
                    pickle.dump(self.solar_efficiency_model, f)
                    
            if self.weather_pattern_model:
                with open(os.path.join(self.model_path, "weather_pattern.pkl"), 'wb') as f:
                    pickle.dump(self.weather_pattern_model, f)
                    
            if self.seasonal_model:
                with open(os.path.join(self.model_path, "seasonal.pkl"), 'wb') as f:
                    pickle.dump(self.seasonal_model, f)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Could not save ML models: {e}")
            
    def add_training_data(self, location: Tuple[float, float], solar_power: float, 
                         weather_data: Dict, seasonal_factor: float, timestamp: datetime):
        """Add training data point"""
        self._training_data.append({
            'latitude': location[0],
            'longitude': location[1],
            'solar_power': solar_power,
            'hour': timestamp.hour,
            'day_of_year': timestamp.timetuple().tm_yday,
            'temperature': weather_data.get('temperature', 20),
            'humidity': weather_data.get('humidity', 50),
            'cloud_cover': weather_data.get('cloud_cover', 0),
            'wind_speed': weather_data.get('wind_speed', 0),
            'seasonal_factor': seasonal_factor
        })
        
        # Retrain models periodically
        if len(self._training_data) % 100 == 0:
            asyncio.create_task(self._retrain_models())
            
    async def _retrain_models(self):
        """Retrain ML models with accumulated data"""
        if len(self._training_data) < 50:  # Need minimum data points
            return
            
        try:
            data = np.array([[d['latitude'], d['longitude'], d['hour'], d['day_of_year'],
                            d['temperature'], d['humidity'], d['cloud_cover'], d['wind_speed']]
                           for d in self._training_data])
            targets = np.array([d['solar_power'] for d in self._training_data])
            
            # Train solar efficiency model
            self.solar_efficiency_model = RandomForestRegressor(n_estimators=100, random_state=42)
            self.solar_efficiency_model.fit(data, targets)
            
            # Train weather pattern model (simplified)
            weather_data = np.array([[d['temperature'], d['humidity'], d['cloud_cover'], d['wind_speed']]
                                   for d in self._training_data])
            self.weather_pattern_model = LinearRegression()
            self.weather_pattern_model.fit(weather_data, targets)
            
            # Train seasonal model
            seasonal_data = np.array([[d['day_of_year'], d['hour']] for d in self._training_data])
            seasonal_targets = np.array([d['seasonal_factor'] for d in self._training_data])
            self.seasonal_model = RandomForestRegressor(n_estimators=50, random_state=42)
            self.seasonal_model.fit(seasonal_data, seasonal_targets)
            
            await self._save_models()
            logging.getLogger(__name__).info("ML models retrained successfully")
            
        except Exception as e:
            logging.getLogger(__name__).error(f"Error retraining ML models: {e}")
            
    async def predict_solar_efficiency(self, location: Tuple[float, float], 
                                     weather_data: Dict, timestamp: datetime) -> MLPrediction:
        """Predict solar efficiency for location and conditions"""
        try:
            if not self.solar_efficiency_model:
                return MLPrediction(0.5, 0.0, "no_model", timestamp)
                
            features = np.array([[location[0], location[1], timestamp.hour, 
                                timestamp.timetuple().tm_yday,
                                weather_data.get('temperature', 20),
                                weather_data.get('humidity', 50),
                                weather_data.get('cloud_cover', 0),
                                weather_data.get('wind_speed', 0)]])
            
            prediction = self.solar_efficiency_model.predict(features)[0]
            
            # Calculate confidence based on training data variance
            confidence = min(1.0, len(self._training_data) / 1000.0)
            
            return MLPrediction(
                value=max(0.0, min(1.0, prediction / 30.0)),  # Normalize to 0-1
                confidence=confidence,
                model_version="v1.0",
                timestamp=timestamp
            )
            
        except Exception as e:
            logging.getLogger(__name__).error(f"Error predicting solar efficiency: {e}")
            return MLPrediction(0.5, 0.0, "error", timestamp)


@dataclass
class BatteryMetrics:
    """Battery status and health metrics"""
    voltage: float  # V
    current: float  # A
    power: float    # W
    state_of_charge: float  # 0.0 - 1.0
    temperature: Optional[float] = None  # °C
    health: float = 1.0  # 0.0 - 1.0
    cycles: int = 0
    capacity_remaining: float = 1.0  # 0.0 - 1.0
    time_remaining: Optional[int] = None  # minutes
    voltage_trend: float = 0.0  # V/hour
    current_trend: float = 0.0  # A/hour


@dataclass
class SolarMetrics:
    """Solar charging status and efficiency"""
    voltage: float  # V
    current: float  # A
    power: float    # W
    daily_energy: float = 0.0  # Wh
    efficiency: float = 0.0  # 0.0 - 1.0
    peak_power_today: float = 0.0  # W
    charging_rate: float = 0.0  # A


@dataclass
class PowerConsumption:
    """Power consumption by component"""
    total: float  # W
    cpu: float = 0.0  # W
    sensors: float = 0.0  # W
    motors: float = 0.0  # W
    camera: float = 0.0  # W
    communication: float = 0.0  # W
    other: float = 0.0  # W


@dataclass
class SunnySpot:
    """Optimal charging location data"""
    latitude: float
    longitude: float
    efficiency_rating: float  # 0.0 - 1.0
    last_measured: datetime
    time_of_day_optimal: List[int]  # Hours when this spot is best
    seasonal_factor: float = 1.0  # Seasonal adjustment
    obstacles_nearby: bool = False


class PowerManager:
    """Comprehensive power management system"""
    
    def __init__(self, 
                 hardware_interface: HardwareInterface,
                 mqtt_client: MQTTClient,
                 cache_manager: CacheManager,
                 weather_service: Optional[WeatherService] = None):
        
        self.logger = logging.getLogger(__name__)
        self.hardware = hardware_interface
        self.mqtt = mqtt_client
        self.cache = cache_manager
        self.weather = weather_service
        
        # Configuration
        self.config = self._load_config()
        
        # State management
        self.current_mode = PowerMode.HIGH_PERFORMANCE
        self.charging_mode = ChargingMode.AUTO
        self.power_saving_enabled = False
        
        # User-configurable power optimization
        self.current_optimization_profile = PowerOptimizationProfile.BALANCED
        self.power_profiles = self._initialize_power_profiles()
        self.custom_profile_settings = {}
        
        # Machine learning system
        self.charging_location_ml = ChargingLocationML()
        
        # Battery monitoring
        self.battery_metrics = BatteryMetrics(12.0, 0.0, 0.0, 0.5)
        self.solar_metrics = SolarMetrics(0.0, 0.0, 0.0)
        self.power_consumption = PowerConsumption(0.0)
        
        # Sunny spot management with ML enhancement
        self.sunny_spots: List[SunnySpot] = []
        self.current_sunny_spot: Optional[SunnySpot] = None
        self.sunny_spot_learning_enabled = True
        self.auto_sunny_spot_discovery = True
        
        # Historical data for trends
        self.battery_history: List[BatteryMetrics] = []
        self.solar_history: List[SolarMetrics] = []
        self.consumption_history: List[PowerConsumption] = []
        
        # Advanced battery management
        self.battery_health_tracker = {}
        self.charging_cycle_optimizer = {}
        self.temperature_protection_active = False
        
        # Automatic shutdown system
        self.auto_shutdown_enabled = True
        self.user_shutdown_thresholds = {
            'critical': 0.05,  # 5%
            'warning': 0.15,   # 15%
            'return_to_base': 0.25  # 25%
        }
        self.shutdown_behavior = 'graceful'  # 'graceful', 'immediate', 'smart'
        
        # Emergency power management
        self.emergency_reserve_enabled = True
        self.emergency_reserve_threshold = 0.03  # 3%
        self.critical_functions_only = False
        
        # Tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._optimization_task: Optional[asyncio.Task] = None
        self._sunny_spot_task: Optional[asyncio.Task] = None
        self._ml_training_task: Optional[asyncio.Task] = None
        self._battery_health_task: Optional[asyncio.Task] = None
        
        # Safety thresholds (now user-configurable)
        self.CRITICAL_BATTERY_LEVEL = 0.05  # 5%
        self.LOW_BATTERY_LEVEL = 0.20  # 20%
        self.OPTIMAL_BATTERY_LEVEL = 0.80  # 80%
        self.MAX_TEMPERATURE = 60.0  # °C
        self.MIN_TEMPERATURE = -20.0  # °C
        
        # Charging parameters for LiFePO4
        self.NOMINAL_VOLTAGE = 12.8  # V
        self.MAX_CHARGE_VOLTAGE = 14.6  # V
        self.MIN_DISCHARGE_VOLTAGE = 10.0  # V
        self.FLOAT_VOLTAGE = 13.6  # V
        
        self._initialized = False
        self._shutdown_event = asyncio.Event()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load power management configuration"""
        return {
            'monitoring_interval': 5.0,  # seconds
            'optimization_interval': 30.0,  # seconds  
            'sunny_spot_update_interval': 300.0,  # seconds
            'coulomb_counting_enabled': True,
            'voltage_calibration_points': [
                (10.0, 0.0),   # 0% SoC
                (12.0, 0.2),   # 20% SoC
                (12.8, 0.5),   # 50% SoC
                (13.2, 0.8),   # 80% SoC
                (14.0, 1.0)    # 100% SoC
            ],
            'power_components': {
                'cpu_base': 2.0,      # W base CPU power
                'cpu_scaling': 3.0,   # W additional per scaling step
                'sensor_power': 0.5,  # W per active sensor
                'camera_power': 2.5,  # W camera power
                'motor_idle': 1.0,    # W motor idle power
                'motor_active': 15.0, # W motor active power
                'comm_power': 1.5     # W communication power
            }
        }
    
    def _initialize_power_profiles(self) -> Dict[PowerOptimizationProfile, PowerProfile]:
        """Initialize predefined power optimization profiles"""
        return {
            PowerOptimizationProfile.MAXIMUM_PERFORMANCE: PowerProfile(
                name="Maximum Performance",
                performance_weight=1.0,
                efficiency_weight=0.0,
                cpu_governor="performance",
                sensor_reduction_factor=0.0,
                camera_quality_factor=1.0,
                motor_efficiency_mode=False,
                description="Prioritize performance over power efficiency"
            ),
            PowerOptimizationProfile.BALANCED: PowerProfile(
                name="Balanced",
                performance_weight=0.6,
                efficiency_weight=0.4,
                cpu_governor="ondemand",
                sensor_reduction_factor=0.2,
                camera_quality_factor=0.8,
                motor_efficiency_mode=True,
                description="Balance between performance and efficiency"
            ),
            PowerOptimizationProfile.POWER_SAVER: PowerProfile(
                name="Power Saver",
                performance_weight=0.3,
                efficiency_weight=0.7,
                cpu_governor="powersave",
                sensor_reduction_factor=0.5,
                camera_quality_factor=0.5,
                motor_efficiency_mode=True,
                description="Prioritize power saving with acceptable performance"
            ),
            PowerOptimizationProfile.MAXIMUM_EFFICIENCY: PowerProfile(
                name="Maximum Efficiency",
                performance_weight=0.0,
                efficiency_weight=1.0,
                cpu_governor="powersave",
                sensor_reduction_factor=0.7,
                camera_quality_factor=0.3,
                motor_efficiency_mode=True,
                description="Maximum power efficiency, minimum performance"
            ),
            PowerOptimizationProfile.CUSTOM: PowerProfile(
                name="Custom",
                performance_weight=0.5,
                efficiency_weight=0.5,
                cpu_governor="ondemand",
                sensor_reduction_factor=0.3,
                camera_quality_factor=0.7,
                motor_efficiency_mode=True,
                description="User-customized power profile"
            )
        }
    
    async def initialize(self) -> bool:
        """Initialize power management system"""
        if self._initialized:
            return True
        
        try:
            self.logger.info("Initializing advanced power management system...")
            
            # Initialize machine learning system
            await self.charging_location_ml.initialize()
            
            # Load historical data
            await self._load_historical_data()
            
            # Load user configuration
            await self._load_user_power_config()
            
            # Start monitoring tasks
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
            self._optimization_task = asyncio.create_task(self._optimization_loop())
            self._sunny_spot_task = asyncio.create_task(self._sunny_spot_loop())
            self._ml_training_task = asyncio.create_task(self._ml_training_loop())
            self._battery_health_task = asyncio.create_task(self._battery_health_loop())
            
            # Subscribe to MQTT topics
            await self._setup_mqtt_subscriptions()
            
            self._initialized = True
            self.logger.info("Advanced power management system initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize power management: {e}")
            return False
    
    async def _load_user_power_config(self):
        """Load user power configuration from cache or file"""
        try:
            # Try to load from cache first
            cached_config = await self.cache.get("power_user_config")
            if cached_config:
                self.current_optimization_profile = PowerOptimizationProfile(
                    cached_config.get('optimization_profile', 'balanced')
                )
                self.custom_profile_settings = cached_config.get('custom_settings', {})
                self.user_shutdown_thresholds = cached_config.get('shutdown_thresholds', 
                                                                self.user_shutdown_thresholds)
                self.shutdown_behavior = cached_config.get('shutdown_behavior', 'graceful')
                
            self.logger.info("User power configuration loaded")
        except Exception as e:
            self.logger.warning(f"Could not load user power config: {e}")
    
    async def _ml_training_loop(self):
        """Machine learning training and optimization loop"""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                # Collect training data from current location and conditions
                if self.current_sunny_spot and self.weather:
                    current_pos = await self.hardware.get_sensor_data("gps")
                    if current_pos:
                        weather_data = await self.weather.get_current_weather()
                        if weather_data:
                            location = (current_pos.get('latitude', 0), current_pos.get('longitude', 0))
                            seasonal_factor = self._calculate_seasonal_factor()
                            
                            self.charging_location_ml.add_training_data(
                                location,
                                self.solar_metrics.power,
                                weather_data.__dict__ if hasattr(weather_data, '__dict__') else {},
                                seasonal_factor,
                                datetime.now()
                            )
                            
            except Exception as e:
                self.logger.error(f"Error in ML training loop: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    async def _battery_health_loop(self):
        """Advanced battery health monitoring and optimization loop"""
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                
                # Update battery health metrics
                await self._update_battery_health()
                
                # Check for temperature protection
                await self._check_temperature_protection()
                
                # Optimize charging cycles
                await self._optimize_charging_cycles()
                
                # Check for emergency shutdown conditions
                await self._check_emergency_shutdown()
                
            except Exception as e:
                self.logger.error(f"Error in battery health loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error

    async def shutdown(self):
        """Shutdown power management system"""
        self.logger.info("Shutting down advanced power management system...")
        
        self._shutdown_event.set()
        
        # Cancel tasks
        tasks = [self._monitoring_task, self._optimization_task, self._sunny_spot_task,
                self._ml_training_task, self._battery_health_task]
        for task in tasks:
            if task and not task.done():
                task.cancel()
                
        # Wait for tasks to complete
        await asyncio.gather(*[t for t in tasks if t], return_exceptions=True)
        
        # Save historical data and ML models
        await self._save_historical_data()
        await self.charging_location_ml._save_models()
        
        self._initialized = False
        self.logger.info("Advanced power management system shutdown complete")
    
    async def _monitoring_loop(self):
        """Main monitoring loop for battery and solar data"""
        while not self._shutdown_event.is_set():
            try:
                # Read power monitor data
                power_data = await self.hardware.get_sensor_data("power_monitor")
                if power_data:
                    await self._update_battery_metrics(power_data)
                
                # Read solar data if available
                solar_data = await self._read_solar_data()
                if solar_data:
                    await self._update_solar_metrics(solar_data)
                
                # Calculate power consumption
                await self._calculate_power_consumption()
                
                # Publish data to MQTT
                await self._publish_power_data()
                
                # Store in cache for quick access
                await self._update_cache()
                
                # Safety checks
                await self._perform_safety_checks()
                
                await asyncio.sleep(self.config['monitoring_interval'])
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.config['monitoring_interval'])
    
    async def _update_battery_metrics(self, power_data: Any):
        """Update battery metrics from power monitor data"""
        try:
            # Extract raw measurements
            voltage = power_data.voltage
            current = power_data.current
            power = power_data.power
            
            # Calculate State of Charge using voltage calibration
            soc = self._calculate_soc_from_voltage(voltage)
            
            # Update coulomb counting if enabled
            if self.config['coulomb_counting_enabled']:
                soc = await self._update_coulomb_counting(current, soc)
            
            # Calculate temperature from environmental sensor if available
            temp_data = await self.hardware.get_sensor_data("environmental")
            temperature = temp_data.temperature if temp_data else None
            
            # Calculate trends
            voltage_trend, current_trend = self._calculate_trends()
            
            # Estimate time remaining
            time_remaining = self._estimate_time_remaining(current, soc)
            
            # Update metrics
            self.battery_metrics = BatteryMetrics(
                voltage=voltage,
                current=current,
                power=power,
                state_of_charge=soc,
                temperature=temperature,
                health=self._calculate_battery_health(),
                cycles=self.battery_metrics.cycles,
                capacity_remaining=self._calculate_capacity_remaining(),
                time_remaining=time_remaining,
                voltage_trend=voltage_trend,
                current_trend=current_trend
            )
            
            # Add to history
            self.battery_history.append(self.battery_metrics)
            if len(self.battery_history) > 1000:  # Keep last 1000 readings
                self.battery_history.pop(0)
                
        except Exception as e:
            self.logger.error(f"Error updating battery metrics: {e}")
    
    def _calculate_soc_from_voltage(self, voltage: float) -> float:
        """Calculate State of Charge from voltage using calibration curve"""
        cal_points = self.config['voltage_calibration_points']
        
        # Handle edge cases
        if voltage <= cal_points[0][0]:
            return cal_points[0][1]
        if voltage >= cal_points[-1][0]:
            return cal_points[-1][1]
        
        # Linear interpolation between calibration points
        for i in range(len(cal_points) - 1):
            v1, soc1 = cal_points[i]
            v2, soc2 = cal_points[i + 1]
            
            if v1 <= voltage <= v2:
                # Linear interpolation
                ratio = (voltage - v1) / (v2 - v1)
                return soc1 + ratio * (soc2 - soc1)
        
        return 0.5  # Fallback
    
    async def _update_coulomb_counting(self, current: float, voltage_soc: float) -> float:
        """Update SoC using coulomb counting with voltage calibration"""
        try:
            # Get last SoC from cache
            last_data = await self.cache.get("power:battery:last_soc")
            if not last_data:
                return voltage_soc
            
            last_soc = last_data.get('soc', voltage_soc)
            last_time = datetime.fromisoformat(last_data.get('timestamp'))
            
            # Calculate time delta
            current_time = datetime.now()
            time_delta_hours = (current_time - last_time).total_seconds() / 3600.0
            
            # Coulomb counting: ΔSoC = (current × time) / battery_capacity
            battery_capacity_ah = 30.0  # 30Ah battery
            soc_delta = (current * time_delta_hours) / battery_capacity_ah
            
            # Update SoC
            coulomb_soc = last_soc + soc_delta
            
            # Blend with voltage-based SoC for accuracy
            # More weight on coulomb counting during discharge/charge
            # More weight on voltage when current is low
            current_abs = abs(current)
            if current_abs > 0.5:  # Active discharge/charge
                blended_soc = 0.8 * coulomb_soc + 0.2 * voltage_soc
            else:  # Low current - voltage more reliable
                blended_soc = 0.3 * coulomb_soc + 0.7 * voltage_soc
            
            # Clamp to valid range
            blended_soc = max(0.0, min(1.0, blended_soc))
            
            # Store for next iteration
            await self.cache.set("power:battery:last_soc", {
                'soc': blended_soc,
                'timestamp': current_time.isoformat()
            })
            
            return blended_soc
            
        except Exception as e:
            self.logger.error(f"Error in coulomb counting: {e}")
            return voltage_soc
    
    def _calculate_trends(self) -> Tuple[float, float]:
        """Calculate voltage and current trends from history"""
        if len(self.battery_history) < 2:
            return 0.0, 0.0
        
        try:
            # Use last 10 readings for trend calculation
            recent_history = self.battery_history[-10:]
            
            if len(recent_history) < 2:
                return 0.0, 0.0
            
            # Calculate time span
            time_span_hours = len(recent_history) * self.config['monitoring_interval'] / 3600.0
            
            # Calculate voltage trend
            voltage_start = recent_history[0].voltage
            voltage_end = recent_history[-1].voltage
            voltage_trend = (voltage_end - voltage_start) / time_span_hours
            
            # Calculate current trend
            current_start = recent_history[0].current
            current_end = recent_history[-1].current
            current_trend = (current_end - current_start) / time_span_hours
            
            return voltage_trend, current_trend
            
        except Exception as e:
            self.logger.error(f"Error calculating trends: {e}")
            return 0.0, 0.0
    
    def _estimate_time_remaining(self, current: float, soc: float) -> Optional[int]:
        """Estimate remaining battery time based on current consumption"""
        try:
            if current >= 0:  # Charging or no load
                return None
            
            # Battery capacity and current SoC
            battery_capacity_ah = 30.0
            remaining_capacity_ah = battery_capacity_ah * soc
            
            # Current draw (make positive for calculation)
            current_draw = abs(current)
            
            # Simple time remaining calculation
            if current_draw > 0.01:  # Avoid division by very small numbers
                time_remaining_hours = remaining_capacity_ah / current_draw
                return int(time_remaining_hours * 60)  # Convert to minutes
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error estimating time remaining: {e}")
            return None
    
    def _calculate_battery_health(self) -> float:
        """Calculate battery health based on various factors"""
        try:
            # Base health
            health = 1.0
            
            # Temperature effects
            if self.battery_metrics.temperature:
                temp = self.battery_metrics.temperature
                if temp > 45.0:  # High temperature degradation
                    health *= 0.95
                elif temp < -10.0:  # Low temperature effects
                    health *= 0.98
            
            # Cycle count effects (simplified)
            cycle_factor = max(0.8, 1.0 - (self.battery_metrics.cycles * 0.0001))
            health *= cycle_factor
            
            # Voltage variance effects
            if len(self.battery_history) > 10:
                recent_voltages = [h.voltage for h in self.battery_history[-10:]]
                voltage_std = statistics.stdev(recent_voltages)
                if voltage_std > 0.5:  # High voltage variance
                    health *= 0.99
            
            return max(0.0, min(1.0, health))
            
        except Exception as e:
            self.logger.error(f"Error calculating battery health: {e}")
            return 1.0
    
    def _calculate_capacity_remaining(self) -> float:
        """Calculate remaining battery capacity based on health and age"""
        try:
            # Base capacity
            base_capacity = 1.0
            
            # Health-based degradation
            capacity = base_capacity * self.battery_metrics.health
            
            # Cycle-based degradation (LiFePO4 specific)
            cycle_degradation = max(0.8, 1.0 - (self.battery_metrics.cycles * 0.00005))
            capacity *= cycle_degradation
            
            return max(0.5, min(1.0, capacity))  # Never go below 50%
            
        except Exception as e:
            self.logger.error(f"Error calculating capacity remaining: {e}")
            return 1.0
    
    async def _read_solar_data(self) -> Optional[Dict[str, Any]]:
        """Read solar charging data from MPPT controller or estimation"""
        try:
            # Try to read from solar charge controller (if available)
            # For now, estimate based on weather and time of day
            
            current_time = datetime.now()
            hour = current_time.hour
            
            # Basic solar estimation based on time of day
            if 6 <= hour <= 18:  # Daylight hours
                # Peak solar around noon
                time_factor = 1.0 - abs(hour - 12) / 6.0
                max_solar_power = 30.0  # 30W panel
                
                # Weather factor
                weather_factor = 1.0
                if self.weather:
                    try:
                        weather_data = await self.weather.get_current_weather()
                        if weather_data:
                            cloud_cover = weather_data.get('cloud_cover', 0.0)
                            weather_factor = 1.0 - (cloud_cover * 0.8)
                    except:
                        pass
                
                # Calculate estimated solar power
                estimated_power = max_solar_power * time_factor * weather_factor
                estimated_voltage = 14.0  # Typical solar panel voltage
                estimated_current = estimated_power / estimated_voltage if estimated_voltage > 0 else 0.0
                
                return {
                    'voltage': estimated_voltage,
                    'current': estimated_current,
                    'power': estimated_power,
                    'estimated': True
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error reading solar data: {e}")
            return None
    
    async def _update_solar_metrics(self, solar_data: Dict[str, Any]):
        """Update solar charging metrics"""
        try:
            voltage = solar_data.get('voltage', 0.0)
            current = solar_data.get('current', 0.0)
            power = solar_data.get('power', 0.0)
            
            # Calculate daily energy (cumulative)
            time_delta_hours = self.config['monitoring_interval'] / 3600.0
            energy_increment = power * time_delta_hours
            
            # Update peak power today
            peak_power_today = max(self.solar_metrics.peak_power_today, power)
            
            # Calculate efficiency (actual vs theoretical max)
            theoretical_max = 30.0  # 30W panel
            efficiency = power / theoretical_max if theoretical_max > 0 else 0.0
            
            # Update metrics
            self.solar_metrics = SolarMetrics(
                voltage=voltage,
                current=current,
                power=power,
                daily_energy=self.solar_metrics.daily_energy + energy_increment,
                efficiency=efficiency,
                peak_power_today=peak_power_today,
                charging_rate=current
            )
            
            # Add to history
            self.solar_history.append(self.solar_metrics)
            if len(self.solar_history) > 1000:
                self.solar_history.pop(0)
            
            # Reset daily energy at midnight
            if datetime.now().hour == 0 and datetime.now().minute == 0:
                self.solar_metrics.daily_energy = 0.0
                self.solar_metrics.peak_power_today = 0.0
                
        except Exception as e:
            self.logger.error(f"Error updating solar metrics: {e}")
    
    async def _calculate_power_consumption(self):
        """Calculate current power consumption by component"""
        try:
            config = self.config['power_components']
            
            # Base CPU power
            cpu_power = config['cpu_base']
            
            # Add CPU scaling based on current mode
            if self.current_mode == PowerMode.HIGH_PERFORMANCE:
                cpu_power += config['cpu_scaling'] * 2
            elif self.current_mode == PowerMode.ECO_MODE:
                cpu_power += config['cpu_scaling'] * 0.5
            
            # Sensor power (based on active sensors)
            active_sensors = await self._count_active_sensors()
            sensor_power = active_sensors * config['sensor_power']
            
            # Camera power
            camera_power = config['camera_power'] if await self._is_camera_active() else 0.0
            
            # Motor power (estimate based on current mode)
            motor_power = config['motor_idle']
            if self.current_mode in [PowerMode.HIGH_PERFORMANCE, PowerMode.ECO_MODE]:
                motor_power = config['motor_active']
            
            # Communication power
            comm_power = config['comm_power']
            
            # Calculate total
            total_power = cpu_power + sensor_power + camera_power + motor_power + comm_power
            
            self.power_consumption = PowerConsumption(
                total=total_power,
                cpu=cpu_power,
                sensors=sensor_power,
                motors=motor_power,
                camera=camera_power,
                communication=comm_power,
                other=0.0
            )
            
            # Add to history
            self.consumption_history.append(self.power_consumption)
            if len(self.consumption_history) > 1000:
                self.consumption_history.pop(0)
                
        except Exception as e:
            self.logger.error(f"Error calculating power consumption: {e}")
    
    async def _count_active_sensors(self) -> int:
        """Count currently active sensors"""
        try:
            # Get all sensor health data
            sensor_data = await self.hardware.get_all_sensor_data()
            if not sensor_data:
                return 0
            
            # Count sensors that are responding
            active_count = 0
            for sensor_name, data in sensor_data.items():
                if data and hasattr(data, 'timestamp'):
                    # Consider sensor active if data is recent (< 30 seconds old)
                    if (datetime.now() - data.timestamp).total_seconds() < 30:
                        active_count += 1
            
            return active_count
            
        except Exception as e:
            self.logger.error(f"Error counting active sensors: {e}")
            return 5  # Reasonable default
    
    async def _is_camera_active(self) -> bool:
        """Check if camera is currently active"""
        try:
            # Check if camera manager is capturing
            return self.hardware.camera_manager.is_capturing if hasattr(self.hardware, 'camera_manager') else False
        except:
            return False
    
    async def _optimization_loop(self):
        """Power optimization and mode management loop"""
        while not self._shutdown_event.is_set():
            try:
                # Determine optimal power mode
                optimal_mode = await self._determine_optimal_power_mode()
                
                # Switch mode if needed
                if optimal_mode != self.current_mode:
                    await self._switch_power_mode(optimal_mode)
                
                # Optimize charging strategy
                await self._optimize_charging_strategy()
                
                # Check if we need to navigate to sunny spot
                await self._check_sunny_spot_navigation()
                
                # Update power saving settings
                await self._update_power_saving()
                
                await asyncio.sleep(self.config['optimization_interval'])
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in optimization loop: {e}")
                await asyncio.sleep(self.config['optimization_interval'])
    
    async def _determine_optimal_power_mode(self) -> PowerMode:
        """Determine optimal power mode based on current conditions"""
        try:
            soc = self.battery_metrics.state_of_charge
            
            # Emergency mode for critically low battery
            if soc <= self.CRITICAL_BATTERY_LEVEL:
                return PowerMode.EMERGENCY_MODE
            
            # Charging mode when battery is low and solar is available
            if soc <= self.LOW_BATTERY_LEVEL and self.solar_metrics.power > 5.0:
                return PowerMode.CHARGING_MODE
            
            # Eco mode for low battery or power saving enabled
            if soc <= self.LOW_BATTERY_LEVEL or self.power_saving_enabled:
                return PowerMode.ECO_MODE
            
            # High performance mode when battery is good
            if soc >= self.OPTIMAL_BATTERY_LEVEL:
                return PowerMode.HIGH_PERFORMANCE
            
            # Default to current mode
            return self.current_mode
            
        except Exception as e:
            self.logger.error(f"Error determining optimal power mode: {e}")
            return PowerMode.ECO_MODE
    
    async def _switch_power_mode(self, new_mode: PowerMode):
        """Switch to new power mode"""
        try:
            old_mode = self.current_mode
            self.current_mode = new_mode
            
            self.logger.info(f"Switching power mode: {old_mode.value} -> {new_mode.value}")
            
            # Apply mode-specific settings
            if new_mode == PowerMode.EMERGENCY_MODE:
                await self._apply_emergency_mode()
            elif new_mode == PowerMode.CHARGING_MODE:
                await self._apply_charging_mode()
            elif new_mode == PowerMode.ECO_MODE:
                await self._apply_eco_mode()
            elif new_mode == PowerMode.HIGH_PERFORMANCE:
                await self._apply_high_performance_mode()
            
            # Publish mode change
            await self.mqtt.publish(
                "power/mode_change",
                {
                    "old_mode": old_mode.value,
                    "new_mode": new_mode.value,
                    "timestamp": datetime.now().isoformat(),
                    "battery_soc": self.battery_metrics.state_of_charge
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error switching power mode: {e}")
    
    async def _apply_emergency_mode(self):
        """Apply emergency power mode settings"""
        try:
            # Disable non-critical sensors
            await self._disable_non_critical_sensors()
            
            # Reduce CPU frequency
            await self._set_cpu_frequency("powersave")
            
            # Stop camera if running
            if hasattr(self.hardware, 'camera_manager'):
                await self.hardware.camera_manager.stop_capture()
            
            # Navigate to safe location if possible
            await self.mqtt.publish("commands/navigation", {
                "command": "emergency_return_home",
                "reason": "critical_battery_level"
            })
            
        except Exception as e:
            self.logger.error(f"Error applying emergency mode: {e}")
    
    async def _apply_charging_mode(self):
        """Apply charging mode settings"""
        try:
            # Reduce power consumption
            await self._set_cpu_frequency("ondemand")
            
            # Keep only critical sensors active
            await self._enable_critical_sensors_only()
            
            # Navigate to best sunny spot if not already there
            if self.sunny_spots and not self.current_sunny_spot:
                best_spot = await self._find_best_sunny_spot()
                if best_spot:
                    await self._navigate_to_sunny_spot(best_spot)
            
        except Exception as e:
            self.logger.error(f"Error applying charging mode: {e}")
    
    async def _apply_eco_mode(self):
        """Apply eco power mode settings"""
        try:
            # Reduce CPU frequency
            await self._set_cpu_frequency("ondemand")
            
            # Reduce sensor sampling rates
            await self._reduce_sensor_rates()
            
            # Lower camera resolution/framerate if needed
            if hasattr(self.hardware, 'camera_manager'):
                await self.hardware.camera_manager.set_low_power_mode(True)
            
        except Exception as e:
            self.logger.error(f"Error applying eco mode: {e}")
    
    async def _apply_high_performance_mode(self):
        """Apply high performance mode settings"""
        try:
            # Maximum CPU frequency
            await self._set_cpu_frequency("performance")
            
            # Enable all sensors
            await self._enable_all_sensors()
            
            # Full camera resolution/framerate
            if hasattr(self.hardware, 'camera_manager'):
                await self.hardware.camera_manager.set_low_power_mode(False)
            
        except Exception as e:
            self.logger.error(f"Error applying high performance mode: {e}")
    
    async def _sunny_spot_loop(self):
        """Sunny spot learning and management loop"""
        while not self._shutdown_event.is_set():
            try:
                if self.sunny_spot_learning_enabled:
                    await self._update_sunny_spot_data()
                
                # Clean up old sunny spot data
                await self._cleanup_old_sunny_spots()
                
                # Optimize sunny spot rankings
                await self._optimize_sunny_spot_rankings()
                
                await asyncio.sleep(self.config['sunny_spot_update_interval'])
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in sunny spot loop: {e}")
                await asyncio.sleep(self.config['sunny_spot_update_interval'])
    
    async def _update_sunny_spot_data(self):
        """Update sunny spot data based on current location and solar efficiency"""
        try:
            # Get current GPS position
            gps_data = await self.hardware.get_sensor_data("gps")
            if not gps_data or not hasattr(gps_data, 'latitude'):
                return
            
            current_lat = gps_data.latitude
            current_lon = gps_data.longitude
            
            # Only update if we're getting good solar power
            if self.solar_metrics.power > 10.0:  # > 10W
                # Find existing spot or create new one
                existing_spot = self._find_nearby_sunny_spot(current_lat, current_lon)
                
                if existing_spot:
                    # Update existing spot
                    await self._update_existing_sunny_spot(existing_spot)
                else:
                    # Create new sunny spot
                    await self._create_new_sunny_spot(current_lat, current_lon)
                
        except Exception as e:
            self.logger.error(f"Error updating sunny spot data: {e}")
    
    def _find_nearby_sunny_spot(self, lat: float, lon: float, radius_m: float = 5.0) -> Optional[SunnySpot]:
        """Find existing sunny spot within radius"""
        for spot in self.sunny_spots:
            distance = self._calculate_distance(lat, lon, spot.latitude, spot.longitude)
            if distance <= radius_m:
                return spot
        return None
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two GPS coordinates in meters"""
        # Simplified distance calculation (good enough for small distances)
        lat_diff = lat1 - lat2
        lon_diff = lon1 - lon2
        
        # Approximate meters per degree (at mid-latitudes)
        meters_per_lat_degree = 111320.0
        meters_per_lon_degree = 111320.0 * math.cos(math.radians((lat1 + lat2) / 2))
        
        distance_m = math.sqrt(
            (lat_diff * meters_per_lat_degree) ** 2 + 
            (lon_diff * meters_per_lon_degree) ** 2
        )
        
        return distance_m
    
    async def _update_existing_sunny_spot(self, spot: SunnySpot):
        """Update efficiency rating of existing sunny spot"""
        try:
            current_hour = datetime.now().hour
            current_efficiency = self.solar_metrics.efficiency
            
            # Update efficiency rating with exponential moving average
            alpha = 0.1  # Learning rate
            spot.efficiency_rating = (1 - alpha) * spot.efficiency_rating + alpha * current_efficiency
            
            # Update optimal time of day
            if current_efficiency > 0.7 and current_hour not in spot.time_of_day_optimal:
                spot.time_of_day_optimal.append(current_hour)
                spot.time_of_day_optimal.sort()
            
            spot.last_measured = datetime.now()
            
            self.logger.debug(f"Updated sunny spot efficiency: {spot.efficiency_rating:.2f}")
            
        except Exception as e:
            self.logger.error(f"Error updating existing sunny spot: {e}")
    
    async def _obstacles_present(self) -> bool:
        """Check for nearby obstacles using ToF sensors."""
        try:
            readings = await self.hardware_interface.tof_manager.read_all_sensors()
            return any(r.distance_mm < 1000 for r in readings.values())
        except Exception:
            return False

    async def _create_new_sunny_spot(self, lat: float, lon: float):
        """Create new sunny spot entry"""
        try:
            current_hour = datetime.now().hour
            
            new_spot = SunnySpot(
                latitude=lat,
                longitude=lon,
                efficiency_rating=self.solar_metrics.efficiency,
                last_measured=datetime.now(),
                time_of_day_optimal=[current_hour] if self.solar_metrics.efficiency > 0.5 else [],
                seasonal_factor=self._calculate_seasonal_factor(),
                obstacles_nearby=await self._obstacles_present()
            )
            
            self.sunny_spots.append(new_spot)
            self.logger.info(f"Created new sunny spot at ({lat:.6f}, {lon:.6f}) with efficiency {new_spot.efficiency_rating:.2f}")
            
        except Exception as e:
            self.logger.error(f"Error creating new sunny spot: {e}")
    
    def _calculate_seasonal_factor(self) -> float:
        """Calculate seasonal adjustment factor based on current date"""
        try:
            current_date = datetime.now()
            day_of_year = current_date.timetuple().tm_yday
            
            # Peak solar around summer solstice (day 172)
            seasonal_factor = 0.5 + 0.5 * math.cos(2 * math.pi * (day_of_year - 172) / 365)
            return max(0.3, min(1.0, seasonal_factor))
            
        except:
            return 1.0
    
    async def _find_best_sunny_spot(self) -> Optional[SunnySpot]:
        """Find the best sunny spot for current conditions"""
        try:
            if not self.sunny_spots:
                return None
            
            current_hour = datetime.now().hour
            best_spot = None
            best_score = 0.0
            
            for spot in self.sunny_spots:
                # Calculate score based on efficiency, time of day, and recency
                efficiency_score = spot.efficiency_rating
                
                # Time of day bonus
                time_score = 1.0 if current_hour in spot.time_of_day_optimal else 0.5
                
                # Recency penalty (prefer recently measured spots)
                age_hours = (datetime.now() - spot.last_measured).total_seconds() / 3600.0
                recency_score = max(0.1, 1.0 - age_hours / 168.0)  # Decay over 1 week
                
                # Seasonal adjustment
                seasonal_score = spot.seasonal_factor
                
                # Obstacle penalty
                obstacle_score = 0.5 if spot.obstacles_nearby else 1.0
                
                # Combined score
                total_score = efficiency_score * time_score * recency_score * seasonal_score * obstacle_score
                
                if total_score > best_score:
                    best_score = total_score
                    best_spot = spot
            
            return best_spot
            
        except Exception as e:
            self.logger.error(f"Error finding best sunny spot: {e}")
            return None
    
    async def _navigate_to_sunny_spot(self, spot: SunnySpot):
        """Navigate to specified sunny spot"""
        try:
            self.logger.info(f"Navigating to sunny spot at ({spot.latitude:.6f}, {spot.longitude:.6f})")
            
            # Send navigation command
            await self.mqtt.publish("commands/navigation", {
                "command": "navigate_to_position",
                "latitude": spot.latitude,
                "longitude": spot.longitude,
                "purpose": "solar_charging",
                "priority": "high" if self.battery_metrics.state_of_charge < 0.3 else "normal"
            })
            
            self.current_sunny_spot = spot
            
        except Exception as e:
            self.logger.error(f"Error navigating to sunny spot: {e}")
    
    async def _set_cpu_frequency(self, governor: str):
        """Set CPU frequency governor"""
        try:
            # This would typically interact with Linux cpufreq
            # For now, just log the action
            self.logger.info(f"Setting CPU governor to: {governor}")
            
            # In real implementation:
            # with open('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor', 'w') as f:
            #     f.write(governor)
            
        except Exception as e:
            self.logger.error(f"Error setting CPU frequency: {e}")
    
    async def _disable_non_critical_sensors(self):
        """Disable non-critical sensors to save power"""
        try:
            # Keep GPS, IMU, and power monitor active
            critical_sensors = ['gps', 'imu', 'power_monitor']
            
            # Disable others
            all_sensors = await self.hardware.get_all_sensor_data()
            for sensor_name in all_sensors.keys():
                if sensor_name not in critical_sensors:
                    # Send disable command via MQTT
                    await self.mqtt.publish(f"commands/sensors/{sensor_name}", {
                        "command": "disable",
                        "reason": "power_saving"
                    })
            
        except Exception as e:
            self.logger.error(f"Error disabling non-critical sensors: {e}")
    
    async def _enable_critical_sensors_only(self):
        """Enable only critical sensors"""
        try:
            critical_sensors = ['gps', 'imu', 'power_monitor', 'environmental']
            
            for sensor_name in critical_sensors:
                await self.mqtt.publish(f"commands/sensors/{sensor_name}", {
                    "command": "enable",
                    "reason": "critical_operation"
                })
            
        except Exception as e:
            self.logger.error(f"Error enabling critical sensors: {e}")
    
    async def _reduce_sensor_rates(self):
        """Reduce sensor sampling rates to save power"""
        try:
            # Reduce update rates for all sensors
            sensors_config = {
                'tof_left': {'rate': 2.0},      # 2 Hz instead of 10 Hz
                'tof_right': {'rate': 2.0},
                'environmental': {'rate': 0.1}, # Every 10 seconds
                'gps': {'rate': 1.0},           # 1 Hz instead of 5 Hz
                'imu': {'rate': 10.0}           # 10 Hz instead of 50 Hz
            }
            
            for sensor_name, config in sensors_config.items():
                await self.mqtt.publish(f"commands/sensors/{sensor_name}", {
                    "command": "set_rate",
                    "rate": config['rate']
                })
            
        except Exception as e:
            self.logger.error(f"Error reducing sensor rates: {e}")
    
    async def _enable_all_sensors(self):
        """Enable all sensors at full rates"""
        try:
            # Full update rates for all sensors
            sensors_config = {
                'tof_left': {'rate': 10.0},
                'tof_right': {'rate': 10.0},
                'environmental': {'rate': 1.0},
                'gps': {'rate': 5.0},
                'imu': {'rate': 50.0}
            }
            
            for sensor_name, config in sensors_config.items():
                await self.mqtt.publish(f"commands/sensors/{sensor_name}", {
                    "command": "enable",
                    "rate": config['rate']
                })
            
        except Exception as e:
            self.logger.error(f"Error enabling all sensors: {e}")
    
    async def _optimize_charging_strategy(self):
        """Optimize charging strategy based on current conditions"""
        try:
            if self.charging_mode == ChargingMode.AUTO:
                # Automatic charging optimization
                await self._auto_optimize_charging()
            elif self.charging_mode == ChargingMode.ECO:
                # Eco charging strategy
                await self._eco_charging_strategy()
            # Manual mode doesn't need optimization
            
        except Exception as e:
            self.logger.error(f"Error optimizing charging strategy: {e}")
    
    async def _auto_optimize_charging(self):
        """Automatic charging optimization based on conditions"""
        try:
            soc = self.battery_metrics.state_of_charge
            solar_power = self.solar_metrics.power
            
            # If battery is low and solar power is good, prioritize charging
            if soc < 0.3 and solar_power > 15.0:
                # Navigate to best sunny spot if not already there
                if not self.current_sunny_spot:
                    best_spot = await self._find_best_sunny_spot()
                    if best_spot:
                        await self._navigate_to_sunny_spot(best_spot)
                
                # Switch to charging mode
                if self.current_mode != PowerMode.CHARGING_MODE:
                    await self._switch_power_mode(PowerMode.CHARGING_MODE)
            
        except Exception as e:
            self.logger.error(f"Error in auto charging optimization: {e}")
    
    async def _eco_charging_strategy(self):
        """Eco charging strategy - minimal power consumption"""
        try:
            # Always prefer eco mode when in eco charging
            if self.current_mode not in [PowerMode.EMERGENCY_MODE, PowerMode.CHARGING_MODE]:
                await self._switch_power_mode(PowerMode.ECO_MODE)
            
        except Exception as e:
            self.logger.error(f"Error in eco charging strategy: {e}")
    
    async def _check_sunny_spot_navigation(self):
        """Check if we should navigate to a sunny spot"""
        try:
            soc = self.battery_metrics.state_of_charge
            
            # Navigate to sunny spot if battery is low and no charging happening
            if (soc <= self.LOW_BATTERY_LEVEL and 
                self.solar_metrics.power < 5.0 and 
                not self.current_sunny_spot):
                
                best_spot = await self._find_best_sunny_spot()
                if best_spot:
                    current_hour = datetime.now().hour
                    
                    # Only navigate if it's likely to be sunny at this spot
                    if (current_hour in best_spot.time_of_day_optimal or 
                        (6 <= current_hour <= 18 and best_spot.efficiency_rating > 0.5)):
                        
                        await self._navigate_to_sunny_spot(best_spot)
            
        except Exception as e:
            self.logger.error(f"Error checking sunny spot navigation: {e}")
    
    async def _update_power_saving(self):
        """Update power saving settings based on conditions"""
        try:
            soc = self.battery_metrics.state_of_charge
            
            # Enable power saving if battery is low
            should_save_power = soc <= self.LOW_BATTERY_LEVEL
            
            if should_save_power != self.power_saving_enabled:
                self.power_saving_enabled = should_save_power
                
                await self.mqtt.publish("power/power_saving", {
                    "enabled": should_save_power,
                    "reason": "low_battery" if should_save_power else "battery_recovered",
                    "battery_soc": soc
                })
            
        except Exception as e:
            self.logger.error(f"Error updating power saving: {e}")
    
    async def _perform_safety_checks(self):
        """Perform safety checks on power system"""
        try:
            battery = self.battery_metrics
            
            # Critical battery level
            if battery.state_of_charge <= self.CRITICAL_BATTERY_LEVEL:
                await self.mqtt.publish("safety/power_critical", {
                    "level": "critical",
                    "message": f"Battery critically low: {battery.state_of_charge:.1%}",
                    "action_required": "immediate_charging_or_shutdown"
                })
            
            # Temperature checks
            if battery.temperature:
                if battery.temperature > self.MAX_TEMPERATURE:
                    await self.mqtt.publish("safety/power_temperature", {
                        "level": "warning",
                        "message": f"Battery temperature high: {battery.temperature:.1f}°C",
                        "action_required": "reduce_power_consumption"
                    })
                elif battery.temperature < self.MIN_TEMPERATURE:
                    await self.mqtt.publish("safety/power_temperature", {
                        "level": "warning", 
                        "message": f"Battery temperature low: {battery.temperature:.1f}°C",
                        "action_required": "warming_required"
                    })
            
            # Voltage checks
            if battery.voltage < self.MIN_DISCHARGE_VOLTAGE:
                await self.mqtt.publish("safety/power_voltage", {
                    "level": "critical",
                    "message": f"Battery voltage critically low: {battery.voltage:.2f}V",
                    "action_required": "immediate_shutdown"
                })
            
        except Exception as e:
            self.logger.error(f"Error performing safety checks: {e}")
    
    async def _publish_power_data(self):
        """Publish power data to MQTT topics"""
        try:
            # Battery data
            battery_data = {
                "voltage": self.battery_metrics.voltage,
                "current": self.battery_metrics.current,
                "power": self.battery_metrics.power,
                "state_of_charge": self.battery_metrics.state_of_charge,
                "temperature": self.battery_metrics.temperature,
                "health": self.battery_metrics.health,
                "cycles": self.battery_metrics.cycles,
                "time_remaining": self.battery_metrics.time_remaining,
                "charging_mode": self.charging_mode.value,
                "power_saving_enabled": self.power_saving_enabled,
                "timestamp": datetime.now().isoformat()
            }
            
            await self.mqtt.publish("power/battery", battery_data)
            
            # Solar data
            solar_data = {
                "voltage": self.solar_metrics.voltage,
                "current": self.solar_metrics.current,
                "power": self.solar_metrics.power,
                "daily_energy": self.solar_metrics.daily_energy,
                "efficiency": self.solar_metrics.efficiency,
                "timestamp": datetime.now().isoformat()
            }
            
            await self.mqtt.publish("power/solar", solar_data)
            
            # Consumption data
            consumption_data = asdict(self.power_consumption)
            consumption_data["timestamp"] = datetime.now().isoformat()
            
            await self.mqtt.publish("power/consumption", consumption_data)
            
        except Exception as e:
            self.logger.error(f"Error publishing power data: {e}")
    
    async def _update_cache(self):
        """Update cache with current power data"""
        try:
            # Cache battery data
            await self.cache.set("power:battery", asdict(self.battery_metrics))
            
            # Cache solar data
            await self.cache.set("power:solar", asdict(self.solar_metrics))
            
            # Cache consumption data
            await self.cache.set("power:consumption", asdict(self.power_consumption))
            
            # Cache sunny spots
            sunny_spots_data = [asdict(spot) for spot in self.sunny_spots]
            await self.cache.set("power:sunny_spots", sunny_spots_data)
            
        except Exception as e:
            self.logger.error(f"Error updating cache: {e}")
    
    async def _setup_mqtt_subscriptions(self):
        """Setup MQTT subscriptions for power management"""
        try:
            # Subscribe to power commands
            await self.mqtt.subscribe("commands/power", self._handle_power_command)
            
            # Subscribe to navigation status for sunny spot tracking
            await self.mqtt.subscribe("navigation/status", self._handle_navigation_status)
            
            # Subscribe to weather updates
            await self.mqtt.subscribe("weather/current", self._handle_weather_update)
            
        except Exception as e:
            self.logger.error(f"Error setting up MQTT subscriptions: {e}")
    
    async def _handle_power_command(self, topic: str, payload: Dict[str, Any]):
        """Handle power management commands"""
        try:
            command = payload.get('command')
            
            if command == "set_charging_mode":
                mode = payload.get('mode', 'auto')
                if mode in ['auto', 'manual', 'eco']:
                    self.charging_mode = ChargingMode(mode)
                    self.logger.info(f"Charging mode set to: {mode}")
            
            elif command == "set_power_saving":
                enabled = payload.get('enabled', False)
                self.power_saving_enabled = enabled
                self.logger.info(f"Power saving {'enabled' if enabled else 'disabled'}")
            
            elif command == "navigate_to_sunny_spot":
                best_spot = await self._find_best_sunny_spot()
                if best_spot:
                    await self._navigate_to_sunny_spot(best_spot)
            
            elif command == "emergency_shutdown":
                await self._emergency_shutdown()
            
        except Exception as e:
            self.logger.error(f"Error handling power command: {e}")
    
    async def _handle_navigation_status(self, topic: str, payload: Dict[str, Any]):
        """Handle navigation status updates"""
        try:
            status = payload.get('status')
            
            if status == "arrived_at_destination":
                purpose = payload.get('purpose')
                if purpose == "solar_charging":
                    self.logger.info("Arrived at sunny spot for charging")
                    # Update current sunny spot based on GPS position
                    # This would be implemented with actual GPS data
            
            elif status == "navigation_failed":
                purpose = payload.get('purpose')
                if purpose == "solar_charging":
                    self.logger.warning("Failed to navigate to sunny spot")
                    self.current_sunny_spot = None
            
        except Exception as e:
            self.logger.error(f"Error handling navigation status: {e}")
    
    async def _handle_weather_update(self, topic: str, payload: Dict[str, Any]):
        """Handle weather updates for solar prediction"""
        try:
            cloud_cover = payload.get('cloud_cover', 0.0)
            
            # Update solar estimation based on weather
            if hasattr(self, '_weather_cloud_cover'):
                self._weather_cloud_cover = cloud_cover
            
        except Exception as e:
            self.logger.error(f"Error handling weather update: {e}")
    
    async def _emergency_shutdown(self):
        """Emergency shutdown sequence"""
        try:
            self.logger.warning("Initiating emergency power shutdown")
            
            # Switch to emergency mode
            await self._switch_power_mode(PowerMode.EMERGENCY_MODE)
            
            # Publish emergency shutdown notice
            await self.mqtt.publish("system/emergency_shutdown", {
                "reason": "power_critical",
                "battery_soc": self.battery_metrics.state_of_charge,
                "timestamp": datetime.now().isoformat()
            })
            
            # Navigate to safe location
            await self.mqtt.publish("commands/navigation", {
                "command": "emergency_return_home",
                "reason": "power_emergency"
            })
            
        except Exception as e:
            self.logger.error(f"Error in emergency shutdown: {e}")
    
    async def _load_historical_data(self):
        """Load historical power data from cache/database"""
        try:
            # Load sunny spots
            sunny_spots_data = await self.cache.get("power:sunny_spots")
            if sunny_spots_data:
                self.sunny_spots = [
                    SunnySpot(**spot_data) for spot_data in sunny_spots_data
                ]
            
            # Load battery cycle count
            battery_data = await self.cache.get("power:battery_cycles")
            if battery_data:
                self.battery_metrics.cycles = battery_data.get('cycles', 0)
            
        except Exception as e:
            self.logger.error(f"Error loading historical data: {e}")
    
    async def _save_historical_data(self):
        """Save historical power data to cache/database"""
        try:
            # Save sunny spots
            sunny_spots_data = [asdict(spot) for spot in self.sunny_spots]
            await self.cache.set("power:sunny_spots", sunny_spots_data)
            
            # Save battery cycle count
            await self.cache.set("power:battery_cycles", {
                'cycles': self.battery_metrics.cycles
            })
            
        except Exception as e:
            self.logger.error(f"Error saving historical data: {e}")
    
    async def _cleanup_old_sunny_spots(self):
        """Remove old sunny spot data"""
        try:
            current_time = datetime.now()
            
            # Remove spots older than 30 days
            self.sunny_spots = [
                spot for spot in self.sunny_spots
                if (current_time - spot.last_measured).days < 30
            ]
            
        except Exception as e:
            self.logger.error(f"Error cleaning up sunny spots: {e}")
    
    async def _optimize_sunny_spot_rankings(self):
        """Optimize sunny spot rankings based on recent performance"""
        try:
            # Sort spots by efficiency rating
            self.sunny_spots.sort(key=lambda x: x.efficiency_rating, reverse=True)
            
            # Keep only top 50 spots to prevent memory bloat
            if len(self.sunny_spots) > 50:
                self.sunny_spots = self.sunny_spots[:50]
            
        except Exception as e:
            self.logger.error(f"Error optimizing sunny spot rankings: {e}")
    
    # Public API methods
    
    async def get_power_status(self) -> Dict[str, Any]:
        """Get current power system status"""
        return {
            "battery": asdict(self.battery_metrics),
            "solar": asdict(self.solar_metrics),
            "consumption": asdict(self.power_consumption),
            "mode": self.current_mode.value,
            "charging_mode": self.charging_mode.value,
            "power_saving_enabled": self.power_saving_enabled,
            "sunny_spots_count": len(self.sunny_spots),
            "current_sunny_spot": asdict(self.current_sunny_spot) if self.current_sunny_spot else None
        }
    
    async def set_charging_mode(self, mode: str) -> bool:
        """Set charging mode"""
        try:
            if mode in ['auto', 'manual', 'eco']:
                self.charging_mode = ChargingMode(mode)
                self.logger.info(f"Charging mode set to: {mode}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error setting charging mode: {e}")
            return False
    
    async def enable_power_saving(self, enabled: bool):
        """Enable or disable power saving mode"""
        self.power_saving_enabled = enabled
        self.logger.info(f"Power saving {'enabled' if enabled else 'disabled'}")
    
    async def get_sunny_spots(self) -> List[Dict[str, Any]]:
        """Get list of known sunny spots"""
        return [asdict(spot) for spot in self.sunny_spots]
    
    async def force_navigate_to_best_sunny_spot(self) -> bool:
        """Force navigation to best sunny spot"""
        try:
            best_spot = await self._find_best_sunny_spot()
            if best_spot:
                await self._navigate_to_sunny_spot(best_spot)
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error forcing navigation to sunny spot: {e}")
            return False
