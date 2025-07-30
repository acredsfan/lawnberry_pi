"""
Analytics Engine
Performance analysis, reporting, and predictive maintenance
"""

import asyncio
import logging
import statistics
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import defaultdict, deque

from .cache_manager import CacheManager
from .database_manager import DatabaseManager
from .models import PerformanceMetric, SensorReading, DataType


@dataclass
class AnalyticsResult:
    """Analytics computation result"""
    metric_name: str
    value: float
    unit: str
    timestamp: datetime
    confidence: float = 1.0
    metadata: Dict[str, Any] = None


class AnalyticsEngine:
    """Advanced analytics and performance monitoring engine"""
    
    def __init__(self, cache_manager: CacheManager, db_manager: DatabaseManager):
        self.logger = logging.getLogger(__name__)
        self.cache = cache_manager
        self.db = db_manager
        
        # Analytics configuration
        self.analysis_window = timedelta(hours=24)
        self.trend_window = timedelta(days=7)
        self.performance_thresholds = {
            'battery_efficiency': 0.8,
            'coverage_rate': 0.9,
            'navigation_accuracy': 0.95,
            'sensor_reliability': 0.98
        }
        
        # Real-time analytics buffers
        self._sensor_buffers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._performance_buffers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        
        # Analytics tasks
        self._analytics_task: Optional[asyncio.Task] = None
        self._analytics_interval = 60  # seconds
        
        # Predictive models (simplified)
        self._battery_model: Dict[str, Any] = {}
        self._maintenance_predictors: Dict[str, Any] = {}
        
        self._initialized = False
    
    async def initialize(self) -> bool:
        """Initialize analytics engine"""
        try:
            # Load historical data for model initialization
            await self._initialize_models()
            
            # Start analytics loop
            self._analytics_task = asyncio.create_task(self._analytics_loop())
            
            self._initialized = True
            self.logger.info("Analytics engine initialized")
            return True
            
        except Exception as e:
            self.logger.error(f"Analytics engine initialization failed: {e}")
            return False
    
    async def _initialize_models(self):
        """Initialize predictive models with historical data"""
        try:
            # Initialize battery efficiency model
            recent_time = datetime.now() - timedelta(days=30)
            battery_readings = await self.db.get_sensor_readings(
                sensor_type="battery",
                start_time=recent_time,
                limit=10000
            )
            
            if battery_readings:
                self._battery_model = await self._build_battery_model(battery_readings)
                self.logger.info(f"Battery model initialized with {len(battery_readings)} readings")
            
        except Exception as e:
            self.logger.error(f"Model initialization error: {e}")
    
    async def _build_battery_model(self, readings: List[SensorReading]) -> Dict[str, Any]:
        """Build battery performance prediction model"""
        try:
            # Extract battery data
            discharge_rates = []
            charge_rates = []
            temperatures = []
            
            for reading in readings:
                if isinstance(reading.value, dict):
                    if 'discharge_rate' in reading.value:
                        discharge_rates.append(reading.value['discharge_rate'])
                    if 'charge_rate' in reading.value:
                        charge_rates.append(reading.value['charge_rate'])
                    if 'temperature' in reading.value:
                        temperatures.append(reading.value['temperature'])
            
            model = {
                'avg_discharge_rate': statistics.mean(discharge_rates) if discharge_rates else 0,
                'avg_charge_rate': statistics.mean(charge_rates) if charge_rates else 0,
                'discharge_std': statistics.stdev(discharge_rates) if len(discharge_rates) > 1 else 0,
                'charge_std': statistics.stdev(charge_rates) if len(charge_rates) > 1 else 0,
                'optimal_temp_range': (min(temperatures), max(temperatures)) if temperatures else (20, 30),
                'last_updated': datetime.now()
            }
            
            return model
            
        except Exception as e:
            self.logger.error(f"Battery model building error: {e}")
            return {}
    
    async def add_sensor_data(self, reading: SensorReading):
        """Add sensor reading to analytics buffers"""
        try:
            buffer_key = f"{reading.sensor_type}_{reading.sensor_id}"
            self._sensor_buffers[buffer_key].append({
                'timestamp': reading.timestamp,
                'value': reading.value,
                'quality': reading.quality
            })
            
            # Real-time analytics for critical sensors
            if reading.sensor_type in ['battery', 'safety', 'navigation']:
                await self._process_real_time_analytics(reading)
                
        except Exception as e:
            self.logger.error(f"Error adding sensor data to analytics: {e}")
    
    async def _process_real_time_analytics(self, reading: SensorReading):
        """Process real-time analytics for critical sensors"""
        try:
            buffer_key = f"{reading.sensor_type}_{reading.sensor_id}"
            buffer = self._sensor_buffers[buffer_key]
            
            if len(buffer) < 10:  # Need minimum data points
                return
            
            # Calculate real-time metrics
            recent_values = [item['value'] for item in list(buffer)[-10:]]
            recent_qualities = [item['quality'] for item in list(buffer)[-10:]]
            
            # Detect anomalies
            if len(recent_values) > 5:
                avg_value = statistics.mean(recent_values) if isinstance(recent_values[0], (int, float)) else None
                avg_quality = statistics.mean(recent_qualities)
                
                if avg_quality < 0.8:  # Quality threshold
                    await self._trigger_quality_alert(reading.sensor_id, avg_quality)
                
                if avg_value is not None:
                    # Check for significant deviations
                    if len(recent_values) > 1:
                        std_dev = statistics.stdev(recent_values)
                        latest_value = recent_values[-1]
                        
                        if abs(latest_value - avg_value) > 2 * std_dev:
                            await self._trigger_anomaly_alert(reading.sensor_id, latest_value, avg_value)
            
        except Exception as e:
            self.logger.error(f"Real-time analytics processing error: {e}")
    
    async def _trigger_quality_alert(self, sensor_id: str, quality: float):
        """Trigger alert for poor sensor quality"""
        alert_data = {
            'type': 'sensor_quality_degraded',
            'sensor_id': sensor_id,
            'quality': quality,
            'timestamp': datetime.now().isoformat(),
            'severity': 'warning' if quality > 0.5 else 'critical'
        }
        
        await self.cache.publish('analytics_alerts', alert_data)
        self.logger.warning(f"Sensor quality alert: {sensor_id} quality={quality:.2f}")
    
    async def _trigger_anomaly_alert(self, sensor_id: str, current_value: float, expected_value: float):
        """Trigger alert for sensor anomaly"""
        deviation = abs(current_value - expected_value) / expected_value * 100
        
        alert_data = {
            'type': 'sensor_anomaly',
            'sensor_id': sensor_id,
            'current_value': current_value,
            'expected_value': expected_value,
            'deviation_percent': deviation,
            'timestamp': datetime.now().isoformat(),
            'severity': 'warning' if deviation < 50 else 'critical'
        }
        
        await self.cache.publish('analytics_alerts', alert_data)
        self.logger.warning(f"Sensor anomaly alert: {sensor_id} deviation={deviation:.1f}%")
    
    async def calculate_coverage_efficiency(self, time_window: timedelta = None) -> AnalyticsResult:
        """Calculate mowing coverage efficiency"""
        try:
            window = time_window or self.analysis_window
            start_time = datetime.now() - window
            
            # Get navigation data
            nav_data = await self.db.get_sensor_readings(
                sensor_type="navigation",
                start_time=start_time
            )
            
            if not nav_data:
                return AnalyticsResult("coverage_efficiency", 0.0, "percentage", datetime.now(), 0.0)
            
            # Calculate coverage metrics
            total_area = 0
            covered_area = 0
            overlapped_area = 0
            
            # Simplified coverage calculation
            for reading in nav_data:
                if isinstance(reading.value, dict) and 'coverage_map' in reading.value:
                    coverage_data = reading.value['coverage_map']
                    if coverage_data:
                        total_area = max(total_area, coverage_data.get('total_area', 0))
                        covered_area = max(covered_area, coverage_data.get('covered_area', 0))
                        overlapped_area += coverage_data.get('overlap', 0)
            
            # Calculate efficiency
            if total_area > 0:
                coverage_ratio = covered_area / total_area
                overlap_penalty = min(overlapped_area / covered_area, 0.5) if covered_area > 0 else 0
                efficiency = max(0, coverage_ratio - overlap_penalty)
            else:
                efficiency = 0.0
            
            confidence = min(len(nav_data) / 100, 1.0)  # More data = higher confidence
            
            return AnalyticsResult(
                "coverage_efficiency",
                efficiency * 100,
                "percentage",
                datetime.now(),
                confidence,
                {
                    'total_area': total_area,
                    'covered_area': covered_area,
                    'overlap_area': overlapped_area,
                    'data_points': len(nav_data)
                }
            )
            
        except Exception as e:
            self.logger.error(f"Coverage efficiency calculation error: {e}")
            return AnalyticsResult("coverage_efficiency", 0.0, "percentage", datetime.now(), 0.0)
    
    async def analyze_battery_performance(self) -> AnalyticsResult:
        """Analyze battery performance and predict maintenance needs"""
        try:
            # Get recent battery data
            start_time = datetime.now() - self.analysis_window
            battery_readings = await self.db.get_sensor_readings(
                sensor_type="battery",
                start_time=start_time
            )
            
            if not battery_readings:
                return AnalyticsResult("battery_performance", 0.0, "score", datetime.now(), 0.0)
            
            # Analyze battery metrics
            charge_cycles = 0
            avg_discharge_rate = 0
            avg_charge_rate = 0
            temperature_violations = 0
            
            discharge_rates = []
            charge_rates = []
            
            for reading in battery_readings:
                if isinstance(reading.value, dict):
                    if 'cycle_count' in reading.value:
                        charge_cycles = max(charge_cycles, reading.value['cycle_count'])
                    
                    if 'discharge_rate' in reading.value:
                        discharge_rates.append(reading.value['discharge_rate'])
                    
                    if 'charge_rate' in reading.value:
                        charge_rates.append(reading.value['charge_rate'])
                    
                    if 'temperature' in reading.value:
                        temp = reading.value['temperature']
                        if temp < 0 or temp > 45:  # Temperature limits
                            temperature_violations += 1
            
            # Calculate performance score
            performance_score = 1.0
            
            # Factor in discharge rate stability
            if discharge_rates:
                avg_discharge_rate = statistics.mean(discharge_rates)
                if len(discharge_rates) > 1:
                    discharge_stability = 1 - (statistics.stdev(discharge_rates) / avg_discharge_rate)
                    performance_score *= max(0, discharge_stability)
            
            # Factor in charge rate efficiency
            if charge_rates:
                avg_charge_rate = statistics.mean(charge_rates)
                expected_charge_rate = self._battery_model.get('avg_charge_rate', avg_charge_rate)
                if expected_charge_rate > 0:
                    charge_efficiency = min(avg_charge_rate / expected_charge_rate, 1.0)
                    performance_score *= charge_efficiency
            
            # Factor in temperature violations
            if len(battery_readings) > 0:
                temp_performance = 1 - (temperature_violations / len(battery_readings))
                performance_score *= temp_performance
            
            confidence = min(len(battery_readings) / 200, 1.0)
            
            return AnalyticsResult(
                "battery_performance",
                performance_score * 100,
                "score",
                datetime.now(),
                confidence,
                {
                    'charge_cycles': charge_cycles,
                    'avg_discharge_rate': avg_discharge_rate,
                    'avg_charge_rate': avg_charge_rate,
                    'temperature_violations': temperature_violations,
                    'data_points': len(battery_readings)
                }
            )
            
        except Exception as e:
            self.logger.error(f"Battery performance analysis error: {e}")
            return AnalyticsResult("battery_performance", 0.0, "score", datetime.now(), 0.0)
    
    async def predict_maintenance_needs(self) -> List[Dict[str, Any]]:
        """Predict upcoming maintenance needs"""
        try:
            predictions = []
            
            # Battery maintenance prediction
            battery_result = await self.analyze_battery_performance()
            if battery_result.value < 80:  # Below 80% performance
                days_to_maintenance = max(1, int((100 - battery_result.value) * 2))
                predictions.append({
                    'component': 'battery',
                    'maintenance_type': 'replacement' if battery_result.value < 60 else 'calibration',
                    'urgency': 'high' if battery_result.value < 60 else 'medium',
                    'estimated_days': days_to_maintenance,
                    'confidence': battery_result.confidence,
                    'details': battery_result.metadata
                })
            
            # Sensor maintenance prediction
            for sensor_type in ['gps', 'imu', 'camera', 'tof']:
                sensor_health = await self._analyze_sensor_health(sensor_type)
                if sensor_health['reliability'] < 0.9:
                    predictions.append({
                        'component': sensor_type,
                        'maintenance_type': 'calibration',
                        'urgency': 'medium' if sensor_health['reliability'] > 0.8 else 'high',
                        'estimated_days': int((1 - sensor_health['reliability']) * 30),
                        'confidence': sensor_health['confidence'],
                        'details': sensor_health
                    })
            
            # Navigation system check
            coverage_result = await self.calculate_coverage_efficiency()
            if coverage_result.value < 85:  # Below 85% efficiency
                predictions.append({
                    'component': 'navigation',
                    'maintenance_type': 'optimization',
                    'urgency': 'low',
                    'estimated_days': 14,
                    'confidence': coverage_result.confidence,
                    'details': coverage_result.metadata
                })
            
            return predictions
            
        except Exception as e:
            self.logger.error(f"Maintenance prediction error: {e}")
            return []
    
    async def _analyze_sensor_health(self, sensor_type: str) -> Dict[str, Any]:
        """Analyze individual sensor health"""
        try:
            start_time = datetime.now() - self.analysis_window
            readings = await self.db.get_sensor_readings(
                sensor_type=sensor_type,
                start_time=start_time
            )
            
            if not readings:
                return {'reliability': 0.0, 'confidence': 0.0, 'error_rate': 1.0}
            
            # Calculate reliability metrics
            high_quality_readings = sum(1 for r in readings if r.quality >= 0.9)
            reliability = high_quality_readings / len(readings)
            
            # Calculate error rate
            error_readings = sum(1 for r in readings if r.quality < 0.5)
            error_rate = error_readings / len(readings)
            
            # Calculate data freshness
            latest_reading = max(readings, key=lambda r: r.timestamp)
            data_age = (datetime.now() - latest_reading.timestamp).total_seconds()
            freshness = max(0, 1 - (data_age / 3600))  # 1 hour threshold
            
            confidence = min(len(readings) / 100, 1.0)
            
            return {
                'reliability': reliability,
                'error_rate': error_rate,
                'freshness': freshness,
                'confidence': confidence,
                'total_readings': len(readings),
                'high_quality_readings': high_quality_readings
            }
            
        except Exception as e:
            self.logger.error(f"Sensor health analysis error for {sensor_type}: {e}")
            return {'reliability': 0.0, 'confidence': 0.0, 'error_rate': 1.0}
    
    async def generate_performance_report(self, time_window: timedelta = None) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        try:
            window = time_window or self.trend_window
            
            # Calculate all metrics
            coverage_result = await self.calculate_coverage_efficiency(window)
            battery_result = await self.analyze_battery_performance()
            maintenance_predictions = await self.predict_maintenance_needs()
            
            # Get system statistics
            db_stats = await self.db.get_statistics()
            cache_stats = await self.cache.get_stats()
            
            # Sensor health summary
            sensor_health = {}
            for sensor_type in ['gps', 'imu', 'camera', 'tof', 'battery']:
                sensor_health[sensor_type] = await self._analyze_sensor_health(sensor_type)
            
            # Calculate overall system health
            health_scores = [h['reliability'] for h in sensor_health.values() if h['confidence'] > 0.5]
            overall_health = statistics.mean(health_scores) * 100 if health_scores else 0
            
            report = {
                'report_generated': datetime.now().isoformat(),
                'time_window_days': window.days,
                'overall_health_score': overall_health,
                'performance_metrics': {
                    'coverage_efficiency': {
                        'value': coverage_result.value,
                        'unit': coverage_result.unit,
                        'confidence': coverage_result.confidence,
                        'details': coverage_result.metadata
                    },
                    'battery_performance': {
                        'value': battery_result.value,
                        'unit': battery_result.unit,
                        'confidence': battery_result.confidence,
                        'details': battery_result.metadata
                    }
                },
                'sensor_health': sensor_health,
                'maintenance_predictions': maintenance_predictions,
                'system_statistics': {
                    'database': db_stats,
                    'cache': cache_stats
                },
                'recommendations': await self._generate_recommendations(
                    coverage_result, battery_result, sensor_health, maintenance_predictions
                )
            }
            
            # Cache the report
            await self.cache.set(DataType.PERFORMANCE, "latest_report", report, ttl=3600)
            
            return report
            
        except Exception as e:
            self.logger.error(f"Performance report generation error: {e}")
            return {'error': str(e), 'report_generated': datetime.now().isoformat()}
    
    async def _generate_recommendations(self, coverage_result, battery_result, 
                                      sensor_health, maintenance_predictions) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # Coverage recommendations
        if coverage_result.value < 85:
            recommendations.append("Consider optimizing mowing patterns for better coverage efficiency")
        
        # Battery recommendations
        if battery_result.value < 80:
            recommendations.append("Battery performance is declining - schedule maintenance check")
        
        # Sensor recommendations
        poor_sensors = [s for s, h in sensor_health.items() if h['reliability'] < 0.9]
        if poor_sensors:
            recommendations.append(f"Calibrate or service sensors: {', '.join(poor_sensors)}")
        
        # Maintenance recommendations
        urgent_maintenance = [p for p in maintenance_predictions if p['urgency'] == 'high']
        if urgent_maintenance:
            components = [p['component'] for p in urgent_maintenance]
            recommendations.append(f"Urgent maintenance needed for: {', '.join(components)}")
        
        # Data quality recommendations
        if not recommendations:
            recommendations.append("System is performing well - continue regular monitoring")
        
        return recommendations
    
    async def _analytics_loop(self):
        """Background analytics processing loop"""
        while True:
            try:
                await asyncio.sleep(self._analytics_interval)
                
                # Update models periodically
                if datetime.now().hour == 2:  # 2 AM daily update
                    await self._initialize_models()
                
                # Generate and cache key metrics
                coverage_result = await self.calculate_coverage_efficiency(timedelta(hours=1))
                await self.cache.set(DataType.PERFORMANCE, "hourly_coverage", 
                                   coverage_result.to_dict(), ttl=3600)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Analytics loop error: {e}")
    
    async def shutdown(self):
        """Shutdown analytics engine"""
        if self._analytics_task:
            self._analytics_task.cancel()
            try:
                await self._analytics_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Analytics engine shutdown complete")
