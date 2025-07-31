"""
Comprehensive TPU performance dashboard with real-time analytics and monitoring.
Provides detailed insights into TPU performance, model efficiency, and health status.
"""

import asyncio
import logging
import json
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import deque
import numpy as np

from .coral_tpu_manager import CoralTPUManager
from .cloud_training_manager import CloudTrainingManager


class TPUPerformanceDashboard:
    """Comprehensive TPU performance monitoring and analytics dashboard"""
    
    def __init__(self, tpu_manager: CoralTPUManager, cloud_training_manager: Optional[CloudTrainingManager] = None):
        self.logger = logging.getLogger(__name__)
        self.tpu_manager = tpu_manager
        self.cloud_training_manager = cloud_training_manager
        
        # Performance tracking
        self._performance_history = deque(maxlen=1000)
        self._health_history = deque(maxlen=500)
        self._cache_performance = deque(maxlen=200)
        
        # Analytics
        self._analytics_data = {
            'performance_trends': {},
            'efficiency_metrics': {},
            'optimization_recommendations': [],
            'alerts': [],
            'model_comparisons': {}
        }
        
        # Monitoring intervals
        self._monitoring_active = False
        self._monitoring_task = None
        self._update_interval = 5.0  # seconds
        
    async def initialize(self) -> bool:
        """Initialize TPU dashboard"""
        try:
            self.logger.info("Initializing TPU Performance Dashboard...")
            
            # Start monitoring
            await self.start_monitoring()
            
            self.logger.info("TPU Performance Dashboard initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize TPU dashboard: {e}")
            return False
    
    async def start_monitoring(self):
        """Start real-time TPU monitoring"""
        if self._monitoring_active:
            return
        
        self._monitoring_active = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        self.logger.info("TPU performance monitoring started")
    
    async def stop_monitoring(self):
        """Stop TPU monitoring"""
        self._monitoring_active = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        self.logger.info("TPU performance monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self._monitoring_active:
            try:
                # Collect performance data
                await self._collect_performance_data()
                
                # Update analytics
                await self._update_analytics()
                
                # Check for alerts
                await self._check_alerts()
                
                await asyncio.sleep(self._update_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in TPU monitoring loop: {e}")
                await asyncio.sleep(self._update_interval * 2)
    
    async def _collect_performance_data(self):
        """Collect current TPU performance data"""
        try:
            # Get TPU stats
            tpu_stats = self.tpu_manager.get_performance_stats()
            
            # Create performance record
            performance_record = {
                'timestamp': time.time(),
                'tpu_available': tpu_stats.get('tpu_available', False),
                'inference_count': tpu_stats.get('total_inferences', 0),
                'cache_hit_rate': tpu_stats.get('cache_hit_rate', 0.0),
                'average_inference_time': tpu_stats.get('average_inference_time_ms', 0.0),
                'health_status': tpu_stats.get('health_status', {}),
                'optimization_settings': tpu_stats.get('optimization_settings', {}),
                'model_info': tpu_stats.get('model_info', {})
            }
            
            # Add to history
            self._performance_history.append(performance_record)
            
            # Track health separately
            if 'health_status' in tpu_stats:
                health_record = {
                    'timestamp': time.time(),
                    **tpu_stats['health_status']
                }
                self._health_history.append(health_record)
            
            # Track cache performance
            cache_record = {
                'timestamp': time.time(),
                'hit_rate': tpu_stats.get('cache_hit_rate', 0.0),
                'hits': tpu_stats.get('cache_hits', 0),
                'misses': tpu_stats.get('cache_misses', 0)
            }
            self._cache_performance.append(cache_record)
            
        except Exception as e:
            self.logger.error(f"Error collecting TPU performance data: {e}")
    
    async def _update_analytics(self):
        """Update performance analytics"""
        try:
            if len(self._performance_history) < 2:
                return
            
            # Calculate performance trends
            self._analytics_data['performance_trends'] = self._calculate_performance_trends()
            
            # Calculate efficiency metrics
            self._analytics_data['efficiency_metrics'] = self._calculate_efficiency_metrics()
            
            # Generate optimization recommendations
            self._analytics_data['optimization_recommendations'] = self._generate_optimization_recommendations()
            
        except Exception as e:
            self.logger.error(f"Error updating TPU analytics: {e}")
    
    def _calculate_performance_trends(self) -> Dict[str, Any]:
        """Calculate performance trends over time"""
        try:
            recent_data = list(self._performance_history)[-50:]  # Last 50 records
            if len(recent_data) < 10:
                return {}
            
            # Extract metrics
            timestamps = [r['timestamp'] for r in recent_data]
            inference_times = [r['average_inference_time'] for r in recent_data]
            cache_hit_rates = [r['cache_hit_rate'] for r in recent_data]
            
            # Calculate trends
            trends = {}
            
            # Inference time trend
            if len(inference_times) >= 10:
                recent_avg = np.mean(inference_times[-10:])
                older_avg = np.mean(inference_times[-20:-10]) if len(inference_times) >= 20 else np.mean(inference_times[:-10])
                
                trends['inference_time'] = {
                    'current_avg': recent_avg,
                    'previous_avg': older_avg,
                    'trend_direction': 'improving' if recent_avg < older_avg else 'degrading' if recent_avg > older_avg else 'stable',
                    'change_percent': ((recent_avg - older_avg) / older_avg * 100) if older_avg > 0 else 0
                }
            
            # Cache performance trend
            if len(cache_hit_rates) >= 10:
                recent_cache_avg = np.mean(cache_hit_rates[-10:])
                older_cache_avg = np.mean(cache_hit_rates[-20:-10]) if len(cache_hit_rates) >= 20 else np.mean(cache_hit_rates[:-10])
                
                trends['cache_performance'] = {
                    'current_hit_rate': recent_cache_avg,
                    'previous_hit_rate': older_cache_avg,
                    'trend_direction': 'improving' if recent_cache_avg > older_cache_avg else 'degrading' if recent_cache_avg < older_cache_avg else 'stable',
                    'change_percent': ((recent_cache_avg - older_cache_avg) / older_cache_avg * 100) if older_cache_avg > 0 else 0
                }
            
            # Overall performance score
            performance_score = self._calculate_performance_score(recent_data[-1])
            trends['overall_performance'] = {
                'score': performance_score,
                'rating': self._get_performance_rating(performance_score)
            }
            
            return trends
            
        except Exception as e:
            self.logger.error(f"Error calculating performance trends: {e}")
            return {}
    
    def _calculate_efficiency_metrics(self) -> Dict[str, Any]:
        """Calculate TPU efficiency metrics"""
        try:
            if not self._performance_history:
                return {}
            
            recent_data = list(self._performance_history)[-100:]  # Last 100 records
            
            metrics = {}
            
            # Throughput metrics
            if len(recent_data) >= 2:
                time_span = recent_data[-1]['timestamp'] - recent_data[0]['timestamp']
                if time_span > 0:
                    total_inferences = recent_data[-1]['inference_count'] - recent_data[0]['inference_count']
                    metrics['throughput_fps'] = total_inferences / time_span
                    
                    # Average inference time
                    avg_inference_time = np.mean([r['average_inference_time'] for r in recent_data if r['average_inference_time'] > 0])
                    metrics['average_inference_time_ms'] = avg_inference_time
                    
                    # Theoretical max FPS
                    if avg_inference_time > 0:
                        metrics['theoretical_max_fps'] = 1000 / avg_inference_time
            
            # Cache efficiency
            if self._cache_performance:
                cache_data = list(self._cache_performance)[-50:]
                cache_hit_rates = [c['hit_rate'] for c in cache_data]
                metrics['cache_efficiency'] = {
                    'average_hit_rate': np.mean(cache_hit_rates),
                    'hit_rate_stability': 1.0 - (np.std(cache_hit_rates) / np.mean(cache_hit_rates)) if np.mean(cache_hit_rates) > 0 else 0,
                    'total_hits': sum([c['hits'] for c in cache_data]),
                    'total_requests': sum([c['hits'] + c['misses'] for c in cache_data])
                }
            
            # Health metrics
            if self._health_history:
                health_data = list(self._health_history)[-20:]
                metrics['health_metrics'] = {
                    'average_temperature': np.mean([h.get('temperature', 0) for h in health_data]),
                    'average_power_draw': np.mean([h.get('power_draw', 0) for h in health_data]),
                    'average_utilization': np.mean([h.get('utilization', 0) for h in health_data]),
                    'error_rate': np.mean([h.get('error_count', 0) for h in health_data]) / len(health_data) if health_data else 0
                }
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error calculating efficiency metrics: {e}")
            return {}
    
    def _generate_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """Generate optimization recommendations based on performance data"""
        recommendations = []
        
        try:
            if not self._performance_history:
                return recommendations
            
            recent_data = self._performance_history[-1]
            trends = self._analytics_data.get('performance_trends', {})
            efficiency = self._analytics_data.get('efficiency_metrics', {})
            
            # Check inference time performance
            if 'inference_time' in trends:
                inference_trend = trends['inference_time']
                if inference_trend['current_avg'] > 20:  # Slow inference
                    recommendations.append({
                        'type': 'performance',
                        'priority': 'high',
                        'title': 'Slow Inference Times Detected',
                        'description': f"Average inference time is {inference_trend['current_avg']:.1f}ms, which is above optimal range",
                        'suggestions': [
                            'Check model complexity and consider using a lighter model',
                            'Verify TPU is properly connected and not thermal throttling',
                            'Enable batching if processing multiple images',
                            'Check for system resource contention'
                        ]
                    })
            
            # Check cache performance
            cache_hit_rate = recent_data.get('cache_hit_rate', 0)
            if cache_hit_rate < 0.3:  # Low cache hit rate
                recommendations.append({
                    'type': 'cache',
                    'priority': 'medium',
                    'title': 'Low Cache Hit Rate',
                    'description': f"Cache hit rate is {cache_hit_rate:.1%}, indicating poor cache efficiency",
                    'suggestions': [
                        'Increase cache size if memory allows',
                        'Review cache eviction policy',
                        'Check for highly variable input data',
                        'Consider adjusting cache similarity threshold'
                    ]
                })
            
            # Check TPU health
            health_status = recent_data.get('health_status', {})
            temperature = health_status.get('temperature', 0)
            if temperature > 70:  # High temperature
                recommendations.append({
                    'type': 'health',
                    'priority': 'high',
                    'title': 'High TPU Temperature',
                    'description': f"TPU temperature is {temperature:.1f}°C, which may cause thermal throttling",
                    'suggestions': [
                        'Improve ventilation around TPU device',
                        'Reduce inference frequency if possible',
                        'Check for dust buildup on TPU device',
                        'Monitor for thermal throttling in performance'
                    ]
                })
            
            # Check utilization
            utilization = health_status.get('utilization', 0)
            if utilization < 0.1:  # Very low utilization
                recommendations.append({
                    'type': 'utilization',
                    'priority': 'low',
                    'title': 'Low TPU Utilization',
                    'description': f"TPU utilization is {utilization:.1%}, indicating underuse of available processing power",
                    'suggestions': [
                        'Consider enabling batching to process multiple images together',
                        'Increase inference frequency if appropriate for application',
                        'Use TPU for additional computer vision tasks',
                        'Consider using multiple models simultaneously'
                    ]
                })
            
            # Check for degrading performance
            if 'inference_time' in trends and trends['inference_time']['trend_direction'] == 'degrading':
                change_percent = trends['inference_time']['change_percent']
                if change_percent > 10:  # Significant degradation
                    recommendations.append({
                        'type': 'performance',
                        'priority': 'high',
                        'title': 'Performance Degradation Detected',
                        'description': f"Inference times have increased by {change_percent:.1f}% recently",
                        'suggestions': [
                            'Check system resources and memory usage',
                            'Restart TPU service if performance continues to degrade',
                            'Monitor for memory leaks in application',
                            'Check TPU device connection and drivers'
                        ]
                    })
            
            return recommendations
            
        except Exception as e:
            self.logger.error(f"Error generating optimization recommendations: {e}")
            return recommendations
    
    def _calculate_performance_score(self, performance_data: Dict[str, Any]) -> float:
        """Calculate overall performance score (0-100)"""
        try:
            score = 100.0
            
            # Inference time score (lower is better)
            inference_time = performance_data.get('average_inference_time', 50)
            if inference_time > 30:
                score -= min(30, (inference_time - 15) * 2)  # Penalty for slow inference
            
            # Cache hit rate score
            cache_hit_rate = performance_data.get('cache_hit_rate', 0)
            score += cache_hit_rate * 20  # Bonus for good cache performance
            
            # Health score
            health_status = performance_data.get('health_status', {})
            temperature = health_status.get('temperature', 40)
            if temperature > 70:
                score -= min(20, (temperature - 70) * 2)  # Penalty for high temperature
            
            error_count = health_status.get('error_count', 0)
            if error_count > 0:
                score -= min(15, error_count * 5)  # Penalty for errors
            
            # TPU availability
            if not performance_data.get('tpu_available', True):
                score -= 50  # Major penalty if TPU not available
            
            return max(0, min(100, score))
            
        except Exception as e:
            self.logger.error(f"Error calculating performance score: {e}")
            return 50.0
    
    def _get_performance_rating(self, score: float) -> str:
        """Get performance rating based on score"""
        if score >= 90:
            return 'Excellent'
        elif score >= 80:
            return 'Good'
        elif score >= 70:
            return 'Fair'
        elif score >= 60:
            return 'Poor'
        else:
            return 'Critical'
    
    async def _check_alerts(self):
        """Check for alert conditions"""
        try:
            alerts = []
            
            if not self._performance_history:
                return
            
            recent_data = self._performance_history[-1]
            
            # Critical alerts
            if not recent_data.get('tpu_available', True):
                alerts.append({
                    'level': 'critical',
                    'title': 'TPU Unavailable',
                    'message': 'TPU device is not available for inference',
                    'timestamp': time.time()
                })
            
            health_status = recent_data.get('health_status', {})
            temperature = health_status.get('temperature', 0)
            if temperature > 80:
                alerts.append({
                    'level': 'critical',
                    'title': 'TPU Overheating',
                    'message': f'TPU temperature ({temperature:.1f}°C) is critically high',
                    'timestamp': time.time()
                })
            
            # Warning alerts
            inference_time = recent_data.get('average_inference_time', 0)
            if inference_time > 50:
                alerts.append({
                    'level': 'warning',
                    'title': 'Slow Inference Performance',
                    'message': f'Average inference time ({inference_time:.1f}ms) is above recommended levels',
                    'timestamp': time.time()
                })
            
            # Update alerts (keep only recent ones)
            current_time = time.time()
            self._analytics_data['alerts'] = [
                alert for alert in self._analytics_data.get('alerts', [])
                if current_time - alert['timestamp'] < 3600  # Keep alerts for 1 hour
            ]
            
            # Add new alerts
            self._analytics_data['alerts'].extend(alerts)
            
        except Exception as e:
            self.logger.error(f"Error checking TPU alerts: {e}")
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data"""
        try:
            # Current status
            current_stats = self.tpu_manager.get_performance_stats()
            
            # Historical data (last hour)
            current_time = time.time()
            hour_ago = current_time - 3600
            
            recent_performance = [
                record for record in self._performance_history
                if record['timestamp'] > hour_ago
            ]
            
            recent_health = [
                record for record in self._health_history  
                if record['timestamp'] > hour_ago
            ]
            
            # Dashboard data
            dashboard_data = {
                'status': {
                    'tpu_available': current_stats.get('tpu_available', False),
                    'model_loaded': bool(current_stats.get('model_info', {}).get('name')),
                    'monitoring_active': self._monitoring_active,
                    'last_update': current_time
                },
                'current_performance': current_stats,
                'performance_trends': self._analytics_data.get('performance_trends', {}),
                'efficiency_metrics': self._analytics_data.get('efficiency_metrics', {}),
                'optimization_recommendations': self._analytics_data.get('optimization_recommendations', []),
                'alerts': self._analytics_data.get('alerts', []),
                'historical_data': {
                    'performance_history': recent_performance,
                    'health_history': recent_health,
                    'cache_performance': list(self._cache_performance)[-50:]  # Last 50 records
                },
                'cloud_training_status': None
            }
            
            # Add cloud training status if available
            if self.cloud_training_manager:
                cloud_status = await self.cloud_training_manager.get_training_status()
                dashboard_data['cloud_training_status'] = cloud_status
            
            return dashboard_data
            
        except Exception as e:
            self.logger.error(f"Error getting dashboard data: {e}")
            return {
                'status': {'tpu_available': False, 'monitoring_active': False},
                'error': str(e)
            }
    
    async def export_performance_report(self, duration_hours: int = 24) -> Dict[str, Any]:
        """Export detailed performance report"""
        try:
            current_time = time.time()
            start_time = current_time - (duration_hours * 3600)
            
            # Filter data by time range
            performance_data = [
                record for record in self._performance_history
                if record['timestamp'] > start_time
            ]
            
            health_data = [
                record for record in self._health_history
                if record['timestamp'] > start_time
            ]
            
            # Generate report
            report = {
                'report_info': {
                    'generated_at': datetime.now().isoformat(),
                    'duration_hours': duration_hours,
                    'data_points': len(performance_data),
                    'start_time': datetime.fromtimestamp(start_time).isoformat(),
                    'end_time': datetime.fromtimestamp(current_time).isoformat()
                },
                'summary': {
                    'total_inferences': performance_data[-1]['inference_count'] - performance_data[0]['inference_count'] if performance_data else 0,
                    'average_inference_time': np.mean([r['average_inference_time'] for r in performance_data]) if performance_data else 0,
                    'cache_hit_rate': np.mean([r['cache_hit_rate'] for r in performance_data]) if performance_data else 0,
                    'uptime_percentage': len([r for r in performance_data if r['tpu_available']]) / len(performance_data) * 100 if performance_data else 0
                },
                'performance_data': performance_data,
                'health_data': health_data,
                'analytics': self._analytics_data.copy(),
                'model_info': self.tpu_manager.get_performance_stats().get('model_info', {})
            }
            
            return report
            
        except Exception as e:
            self.logger.error(f"Error exporting performance report: {e}")
            return {'error': str(e)}
    
    async def shutdown(self):
        """Shutdown TPU dashboard"""
        try:
            await self.stop_monitoring()
            self.logger.info("TPU Performance Dashboard shutdown complete")
        except Exception as e:
            self.logger.error(f"Error during TPU dashboard shutdown: {e}")
