"""
Performance Dashboard - Real-time monitoring and analytics for dynamic resource management
Provides comprehensive visibility into system performance and resource allocation decisions
"""

import asyncio
import logging
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import deque
import numpy as np
from pathlib import Path

from .dynamic_resource_manager import DynamicResourceManager, ResourceMetrics, AllocationDecision, OperationMode

logger = logging.getLogger(__name__)


@dataclass
class PerformanceAlert:
    """Performance alert definition"""
    id: str
    level: str  # info, warning, critical
    title: str
    message: str
    timestamp: datetime
    acknowledged: bool = False
    auto_resolved: bool = False
    metadata: Dict[str, Any] = None


@dataclass
class ServicePerformanceStats:
    """Performance statistics for a service"""
    service_name: str
    avg_cpu_usage: float
    peak_cpu_usage: float
    avg_memory_usage: float
    peak_memory_usage: float
    allocation_changes: int
    performance_score: float  # 0-100, higher is better
    last_updated: datetime


@dataclass
class SystemPerformanceSnapshot:
    """Complete system performance snapshot"""
    timestamp: datetime
    overall_cpu_efficiency: float
    overall_memory_efficiency: float
    resource_allocation_efficiency: float
    adaptation_responsiveness: float
    system_stability_score: float
    operation_mode: str
    active_alerts: int
    total_services: int
    services_optimized: int


class PerformanceAnalyzer:
    """Advanced performance analysis engine"""
    
    def __init__(self):
        self.metrics_history: deque = deque(maxlen=2000)
        self.allocation_history: deque = deque(maxlen=1000)
        self.performance_scores: Dict[str, deque] = {}
        
    def add_metrics(self, metrics: ResourceMetrics):
        """Add new metrics for analysis"""
        self.metrics_history.append(metrics)
        
    def add_allocation_decision(self, decision: AllocationDecision):
        """Add allocation decision for analysis"""
        self.allocation_history.append(decision)
        
    def calculate_efficiency_scores(self) -> Dict[str, float]:
        """Calculate various efficiency scores"""
        if len(self.metrics_history) < 10:
            return {}
        
        recent_metrics = list(self.metrics_history)[-60:]  # Last minute
        
        # CPU Efficiency: How well CPU is utilized without being overloaded
        cpu_values = [m.cpu_percent for m in recent_metrics]
        cpu_efficiency = self._calculate_utilization_efficiency(cpu_values, target_range=(40, 75))
        
        # Memory Efficiency: How well memory is utilized
        memory_values = [m.memory_percent for m in recent_metrics]
        memory_efficiency = self._calculate_utilization_efficiency(memory_values, target_range=(30, 70))
        
        # Load Balance Efficiency: How balanced the load is across cores
        load_values = [m.load_average[0] for m in recent_metrics if m.load_average]
        load_efficiency = self._calculate_load_balance_efficiency(load_values)
        
        # Temperature Efficiency: How well thermal management is working
        temp_values = [m.temperature for m in recent_metrics if m.temperature]
        temp_efficiency = self._calculate_temperature_efficiency(temp_values)
        
        return {
            'cpu_efficiency': cpu_efficiency,
            'memory_efficiency': memory_efficiency,
            'load_balance_efficiency': load_efficiency,
            'temperature_efficiency': temp_efficiency,
            'overall_efficiency': np.mean([cpu_efficiency, memory_efficiency, load_efficiency, temp_efficiency])
        }
    
    def _calculate_utilization_efficiency(self, values: List[float], target_range: tuple) -> float:
        """Calculate efficiency based on target utilization range"""
        if not values:
            return 0.0
        
        target_min, target_max = target_range
        efficiency_scores = []
        
        for value in values:
            if target_min <= value <= target_max:
                # In optimal range
                efficiency_scores.append(100.0)
            elif value < target_min:
                # Under-utilized
                efficiency_scores.append(50.0 + (value / target_min) * 50.0)
            else:
                # Over-utilized
                over_util = (value - target_max) / (100 - target_max)
                efficiency_scores.append(max(0.0, 50.0 - over_util * 50.0))
        
        return np.mean(efficiency_scores)
    
    def _calculate_load_balance_efficiency(self, load_values: List[float]) -> float:
        """Calculate load balance efficiency based on load average"""
        if not load_values:
            return 100.0
        
        # For 4-core Pi, ideal load is around 2-3
        ideal_load = 2.5
        efficiency_scores = []
        
        for load in load_values:
            if load <= ideal_load:
                efficiency_scores.append(100.0)
            else:
                # Penalize high load
                over_load = (load - ideal_load) / ideal_load
                efficiency_scores.append(max(0.0, 100.0 - over_load * 30.0))
        
        return np.mean(efficiency_scores)
    
    def _calculate_temperature_efficiency(self, temp_values: List[float]) -> float:
        """Calculate thermal efficiency"""
        if not temp_values:
            return 100.0
        
        efficiency_scores = []
        for temp in temp_values:
            if temp < 60:
                efficiency_scores.append(100.0)
            elif temp < 70:
                efficiency_scores.append(90.0)
            elif temp < 80:
                efficiency_scores.append(70.0)
            else:
                efficiency_scores.append(max(0.0, 50.0 - (temp - 80) * 5))
        
        return np.mean(efficiency_scores)
    
    def analyze_adaptation_effectiveness(self) -> Dict[str, Any]:
        """Analyze how effective resource adaptations have been"""
        if len(self.allocation_history) < 5:
            return {'effectiveness_score': 0.0, 'analysis': 'Insufficient data'}
        
        recent_decisions = list(self.allocation_history)[-20:]
        
        # Group decisions by service
        service_decisions = {}
        for decision in recent_decisions:
            if decision.service_name not in service_decisions:
                service_decisions[decision.service_name] = []
            service_decisions[decision.service_name].append(decision)
        
        effectiveness_scores = []
        analysis_details = {}
        
        for service_name, decisions in service_decisions.items():
            if len(decisions) < 2:
                continue
            
            # Analyze decision confidence and outcomes
            avg_confidence = np.mean([d.confidence for d in decisions])
            decision_frequency = len(decisions)
            
            # Check for oscillation (rapid back-and-forth changes)
            oscillation_score = self._detect_oscillation(decisions)
            
            # Service effectiveness score
            service_effectiveness = (avg_confidence * 0.4 + 
                                   (100 - min(decision_frequency * 5, 50)) * 0.3 + 
                                   oscillation_score * 0.3)
            
            effectiveness_scores.append(service_effectiveness)
            analysis_details[service_name] = {
                'effectiveness': service_effectiveness,
                'avg_confidence': avg_confidence,
                'decision_count': decision_frequency,
                'oscillation_score': oscillation_score
            }
        
        overall_effectiveness = np.mean(effectiveness_scores) if effectiveness_scores else 0.0
        
        return {
            'effectiveness_score': overall_effectiveness,
            'service_details': analysis_details,
            'total_decisions': len(recent_decisions),
            'analysis': self._generate_effectiveness_analysis(overall_effectiveness, analysis_details)
        }
    
    def _detect_oscillation(self, decisions: List[AllocationDecision]) -> float:
        """Detect oscillating resource allocations"""
        if len(decisions) < 3:
            return 100.0
        
        # Look for rapid changes in opposite directions
        oscillations = 0
        for i in range(len(decisions) - 2):
            curr_change = decisions[i+1].new_value - decisions[i].old_value
            next_change = decisions[i+2].new_value - decisions[i+1].old_value
            
            # Oscillation if changes are in opposite directions and significant
            if (curr_change > 0 and next_change < 0 and abs(next_change) > abs(curr_change) * 0.5) or \
               (curr_change < 0 and next_change > 0 and abs(next_change) > abs(curr_change) * 0.5):
                oscillations += 1
        
        # Score inversely related to oscillations
        oscillation_penalty = min(oscillations * 20, 80)
        return max(20.0, 100.0 - oscillation_penalty)
    
    def _generate_effectiveness_analysis(self, overall_score: float, details: Dict) -> str:
        """Generate human-readable analysis of adaptation effectiveness"""
        if overall_score >= 80:
            return "Resource adaptations are highly effective with confident decisions and stable allocations."
        elif overall_score >= 60:
            return "Resource adaptations are moderately effective. Some optimization opportunities exist."
        elif overall_score >= 40:
            return "Resource adaptations show mixed effectiveness. Review thresholds and decision logic."
        else:
            return "Resource adaptations may be ineffective. Consider adjusting adaptation parameters."


class PerformanceDashboard:
    """
    Comprehensive performance monitoring dashboard
    """
    
    def __init__(self, resource_manager: DynamicResourceManager):
        self.resource_manager = resource_manager
        self.analyzer = PerformanceAnalyzer()
        
        # Dashboard state
        self.active_alerts: Dict[str, PerformanceAlert] = {}
        self.service_stats: Dict[str, ServicePerformanceStats] = {}
        self.dashboard_history: deque = deque(maxlen=500)
        
        # Alert thresholds
        self.alert_thresholds = {
            'cpu_critical': 90.0,
            'cpu_warning': 80.0,
            'memory_critical': 85.0,
            'memory_warning': 75.0,
            'temperature_critical': 80.0,
            'temperature_warning': 70.0,
            'efficiency_warning': 60.0,
            'efficiency_critical': 40.0
        }
        
        # Monitoring state
        self.monitoring_active = False
        self.update_task: Optional[asyncio.Task] = None
        self.update_interval = 5.0  # seconds
        
    async def initialize(self):
        """Initialize the performance dashboard"""
        logger.info("Initializing Performance Dashboard")
        
        # Initialize service stats
        for service_name in self.resource_manager.service_profiles.keys():
            self.service_stats[service_name] = ServicePerformanceStats(
                service_name=service_name,
                avg_cpu_usage=0.0,
                peak_cpu_usage=0.0,
                avg_memory_usage=0.0,
                peak_memory_usage=0.0,
                allocation_changes=0,
                performance_score=100.0,
                last_updated=datetime.now()
            )
        
        # Start monitoring
        await self.start_monitoring()
        logger.info("Performance Dashboard initialized")
    
    async def start_monitoring(self):
        """Start dashboard monitoring"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.update_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Performance Dashboard monitoring started")
    
    async def stop_monitoring(self):
        """Stop dashboard monitoring"""
        self.monitoring_active = False
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except asyncio.CancelledError:
                pass
        logger.info("Performance Dashboard monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main dashboard monitoring loop"""
        while self.monitoring_active:
            try:
                await self._update_dashboard()
                await asyncio.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Error in dashboard monitoring loop: {e}")
                await asyncio.sleep(self.update_interval)
    
    async def _update_dashboard(self):
        """Update dashboard data and check for alerts"""
        try:
            # Get current system status
            system_status = await self.resource_manager.get_current_status()
            
            # Update analyzer with latest metrics
            if self.resource_manager.metrics_history:
                latest_metrics = list(self.resource_manager.metrics_history)[-1]
                self.analyzer.add_metrics(latest_metrics)
            
            # Update analyzer with allocation decisions
            if self.resource_manager.allocation_history:
                for decision in list(self.resource_manager.allocation_history)[-10:]:
                    self.analyzer.add_allocation_decision(decision)
            
            # Calculate efficiency scores
            efficiency_scores = self.analyzer.calculate_efficiency_scores()
            
            # Analyze adaptation effectiveness
            adaptation_analysis = self.analyzer.analyze_adaptation_effectiveness()
            
            # Update service statistics
            await self._update_service_stats(system_status)
            
            # Check for alerts
            await self._check_alerts(system_status, efficiency_scores)
            
            # Create performance snapshot
            snapshot = SystemPerformanceSnapshot(
                timestamp=datetime.now(),
                overall_cpu_efficiency=efficiency_scores.get('cpu_efficiency', 0.0),
                overall_memory_efficiency=efficiency_scores.get('memory_efficiency', 0.0),
                resource_allocation_efficiency=adaptation_analysis.get('effectiveness_score', 0.0),
                adaptation_responsiveness=self._calculate_responsiveness_score(),
                system_stability_score=self._calculate_stability_score(),
                operation_mode=system_status['operation_mode'],
                active_alerts=len([a for a in self.active_alerts.values() if not a.acknowledged]),
                total_services=len(self.service_stats),
                services_optimized=self._count_optimized_services()
            )
            
            self.dashboard_history.append(snapshot)
            
        except Exception as e:
            logger.error(f"Error updating dashboard: {e}")
    
    async def _update_service_stats(self, system_status: Dict[str, Any]):
        """Update service performance statistics"""
        allocations = system_status.get('service_allocations', {})
        
        for service_name, stats in self.service_stats.items():
            if service_name in allocations:
                allocation = allocations[service_name]
                
                # Update allocation change count
                if hasattr(stats, '_last_cpu_allocation'):
                    if stats._last_cpu_allocation != allocation['cpu_percent']:
                        stats.allocation_changes += 1
                
                stats._last_cpu_allocation = allocation['cpu_percent']
                stats._last_memory_allocation = allocation['memory_mb']
                
                # Calculate performance score based on efficiency and stability
                stats.performance_score = self._calculate_service_performance_score(service_name, allocation)
                stats.last_updated = datetime.now()
    
    def _calculate_service_performance_score(self, service_name: str, allocation: Dict) -> float:
        """Calculate performance score for a service"""
        base_score = 100.0
        
        # Penalize excessive allocation changes (instability)
        stats = self.service_stats[service_name]
        if stats.allocation_changes > 10:
            base_score -= min(stats.allocation_changes * 2, 30)
        
        # Reward efficient resource usage
        profile = self.resource_manager.service_profiles.get(service_name)
        if profile:
            base_limits = profile.base_limits
            
            # CPU efficiency
            cpu_ratio = allocation['cpu_percent'] / base_limits.cpu_percent
            if 0.8 <= cpu_ratio <= 1.2:  # Within 20% of base
                base_score += 10
            elif cpu_ratio > 2.0:  # Excessive allocation
                base_score -= 20
            
            # Memory efficiency
            memory_ratio = allocation['memory_mb'] / base_limits.memory_mb
            if 0.8 <= memory_ratio <= 1.2:  # Within 20% of base
                base_score += 10
            elif memory_ratio > 2.0:  # Excessive allocation
                base_score -= 20
        
        return max(0.0, min(100.0, base_score))
    
    async def _check_alerts(self, system_status: Dict[str, Any], efficiency_scores: Dict[str, float]):
        """Check for performance alerts"""
        current_metrics = system_status.get('current_metrics', {})
        if not current_metrics:
            return
        
        # Check CPU alerts
        cpu_percent = current_metrics.get('cpu_percent', 0)
        if cpu_percent >= self.alert_thresholds['cpu_critical']:
            await self._create_alert('cpu_critical', 'Critical CPU Usage', 
                                   f"CPU usage at {cpu_percent:.1f}% (critical threshold: {self.alert_thresholds['cpu_critical']}%)")
        elif cpu_percent >= self.alert_thresholds['cpu_warning']:
            await self._create_alert('cpu_warning', 'High CPU Usage', 
                                   f"CPU usage at {cpu_percent:.1f}% (warning threshold: {self.alert_thresholds['cpu_warning']}%)")
        
        # Check memory alerts
        memory_percent = current_metrics.get('memory_percent', 0)
        if memory_percent >= self.alert_thresholds['memory_critical']:
            await self._create_alert('memory_critical', 'Critical Memory Usage', 
                                   f"Memory usage at {memory_percent:.1f}% (critical threshold: {self.alert_thresholds['memory_critical']}%)")
        elif memory_percent >= self.alert_thresholds['memory_warning']:
            await self._create_alert('memory_warning', 'High Memory Usage', 
                                   f"Memory usage at {memory_percent:.1f}% (warning threshold: {self.alert_thresholds['memory_warning']}%)")
        
        # Check temperature alerts
        temperature = current_metrics.get('temperature')
        if temperature:
            if temperature >= self.alert_thresholds['temperature_critical']:
                await self._create_alert('temp_critical', 'Critical Temperature', 
                                       f"Temperature at {temperature:.1f}°C (critical threshold: {self.alert_thresholds['temperature_critical']}°C)")
            elif temperature >= self.alert_thresholds['temperature_warning']:
                await self._create_alert('temp_warning', 'High Temperature', 
                                       f"Temperature at {temperature:.1f}°C (warning threshold: {self.alert_thresholds['temperature_warning']}°C)")
        
        # Check efficiency alerts
        overall_efficiency = efficiency_scores.get('overall_efficiency', 100.0)
        if overall_efficiency <= self.alert_thresholds['efficiency_critical']:
            await self._create_alert('efficiency_critical', 'Critical System Efficiency', 
                                   f"Overall efficiency at {overall_efficiency:.1f}% (critical threshold: {self.alert_thresholds['efficiency_critical']}%)")
        elif overall_efficiency <= self.alert_thresholds['efficiency_warning']:
            await self._create_alert('efficiency_warning', 'Low System Efficiency', 
                                   f"Overall efficiency at {overall_efficiency:.1f}% (warning threshold: {self.alert_thresholds['efficiency_warning']}%)")
        
        # Auto-resolve alerts that no longer apply
        await self._auto_resolve_alerts(current_metrics, efficiency_scores)
    
    async def _create_alert(self, alert_id: str, title: str, message: str):
        """Create or update a performance alert"""
        level = 'critical' if 'critical' in alert_id else 'warning' if 'warning' in alert_id else 'info'
        
        if alert_id not in self.active_alerts:
            self.active_alerts[alert_id] = PerformanceAlert(
                id=alert_id,
                level=level,
                title=title,
                message=message,
                timestamp=datetime.now(),
                acknowledged=False,
                auto_resolved=False,
                metadata={}
            )
            logger.warning(f"Performance alert created: {title} - {message}")
        else:
            # Update existing alert
            self.active_alerts[alert_id].message = message
            self.active_alerts[alert_id].timestamp = datetime.now()
    
    async def _auto_resolve_alerts(self, current_metrics: Dict, efficiency_scores: Dict):
        """Auto-resolve alerts that no longer apply"""
        to_resolve = []
        
        for alert_id, alert in self.active_alerts.items():
            should_resolve = False
            
            if alert_id == 'cpu_critical' and current_metrics.get('cpu_percent', 0) < self.alert_thresholds['cpu_critical']:
                should_resolve = True
            elif alert_id == 'cpu_warning' and current_metrics.get('cpu_percent', 0) < self.alert_thresholds['cpu_warning']:
                should_resolve = True
            elif alert_id == 'memory_critical' and current_metrics.get('memory_percent', 0) < self.alert_thresholds['memory_critical']:
                should_resolve = True
            elif alert_id == 'memory_warning' and current_metrics.get('memory_percent', 0) < self.alert_thresholds['memory_warning']:
                should_resolve = True
            elif alert_id == 'temp_critical' and (not current_metrics.get('temperature') or 
                                                 current_metrics.get('temperature', 0) < self.alert_thresholds['temperature_critical']):
                should_resolve = True
            elif alert_id == 'temp_warning' and (not current_metrics.get('temperature') or 
                                                current_metrics.get('temperature', 0) < self.alert_thresholds['temperature_warning']):
                should_resolve = True
            elif alert_id == 'efficiency_critical' and efficiency_scores.get('overall_efficiency', 100) > self.alert_thresholds['efficiency_critical']:
                should_resolve = True
            elif alert_id == 'efficiency_warning' and efficiency_scores.get('overall_efficiency', 100) > self.alert_thresholds['efficiency_warning']:
                should_resolve = True
            
            if should_resolve:
                to_resolve.append(alert_id)
        
        for alert_id in to_resolve:
            self.active_alerts[alert_id].auto_resolved = True
            logger.info(f"Auto-resolved alert: {self.active_alerts[alert_id].title}")
    
    def _calculate_responsiveness_score(self) -> float:
        """Calculate how responsive the resource adaptation system is"""
        if not self.resource_manager.allocation_history:
            return 100.0
        
        recent_decisions = list(self.resource_manager.allocation_history)[-10:]
        if not recent_decisions:
            return 100.0
        
        # Measure time between decisions and confidence
        response_scores = []
        for decision in recent_decisions:
            # Higher confidence = better responsiveness
            confidence_score = decision.confidence * 100
            
            # Recent decisions score higher
            time_since = (datetime.now() - decision.timestamp).total_seconds()
            recency_score = max(0, 100 - time_since / 60)  # Decay over 1 minute
            
            response_scores.append((confidence_score + recency_score) / 2)
        
        return np.mean(response_scores) if response_scores else 100.0
    
    def _calculate_stability_score(self) -> float:
        """Calculate system stability score"""
        if len(self.dashboard_history) < 5:
            return 100.0
        
        recent_snapshots = list(self.dashboard_history)[-10:]
        
        # Look for stability in key metrics
        cpu_efficiencies = [s.overall_cpu_efficiency for s in recent_snapshots]
        memory_efficiencies = [s.overall_memory_efficiency for s in recent_snapshots]
        
        # Lower variance = higher stability
        cpu_stability = max(0, 100 - np.std(cpu_efficiencies) * 2)
        memory_stability = max(0, 100 - np.std(memory_efficiencies) * 2)
        
        # Factor in alert frequency
        alert_penalty = min(len(self.active_alerts) * 10, 50)
        
        return max(0, (cpu_stability + memory_stability) / 2 - alert_penalty)
    
    def _count_optimized_services(self) -> int:
        """Count services that are performing optimally"""
        optimized = 0
        for stats in self.service_stats.values():
            if stats.performance_score >= 80.0 and stats.allocation_changes < 5:
                optimized += 1
        return optimized
    
    async def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data"""
        latest_snapshot = self.dashboard_history[-1] if self.dashboard_history else None
        
        # Get current resource manager status
        resource_status = await self.resource_manager.get_current_status()
        
        # Get efficiency scores
        efficiency_scores = self.analyzer.calculate_efficiency_scores()
        
        # Get adaptation analysis
        adaptation_analysis = self.analyzer.analyze_adaptation_effectiveness()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'system_overview': {
                'operation_mode': resource_status['operation_mode'],
                'monitoring_active': self.monitoring_active,
                'total_services': len(self.service_stats),
                'services_optimized': self._count_optimized_services(),
                'active_alerts': len([a for a in self.active_alerts.values() if not a.acknowledged]),
                'system_stability': self._calculate_stability_score(),
                'adaptation_responsiveness': self._calculate_responsiveness_score()
            },
            'resource_utilization': resource_status,
            'efficiency_metrics': efficiency_scores,
            'adaptation_analysis': adaptation_analysis,
            'service_performance': {
                name: asdict(stats) for name, stats in self.service_stats.items()
            },
            'active_alerts': {
                alert_id: asdict(alert) for alert_id, alert in self.active_alerts.items()
                if not alert.auto_resolved
            },
            'performance_history': [
                asdict(snapshot) for snapshot in list(self.dashboard_history)[-50:]
            ] if self.dashboard_history else [],
            'recent_allocations': [
                {
                    'service_name': d.service_name,
                    'resource_type': d.resource_type.value,
                    'old_value': d.old_value,
                    'new_value': d.new_value,
                    'reason': d.reason,
                    'timestamp': d.timestamp.isoformat(),
                    'confidence': d.confidence
                }
                for d in list(self.resource_manager.allocation_history)[-20:]
            ] if self.resource_manager.allocation_history else []
        }
    
    async def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge a performance alert"""
        if alert_id in self.active_alerts:
            self.active_alerts[alert_id].acknowledged = True
            logger.info(f"Alert acknowledged: {alert_id}")
            return True
        return False
    
    async def get_performance_report(self, hours: int = 24) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Filter history by time period
        period_snapshots = [
            s for s in self.dashboard_history 
            if s.timestamp >= cutoff_time
        ]
        
        if not period_snapshots:
            return {'message': 'Insufficient data for requested time period'}
        
        # Calculate summary statistics
        cpu_efficiencies = [s.overall_cpu_efficiency for s in period_snapshots]
        memory_efficiencies = [s.overall_memory_efficiency for s in period_snapshots]
        stability_scores = [s.system_stability_score for s in period_snapshots]
        
        # Count allocation decisions in period
        period_decisions = [
            d for d in self.resource_manager.allocation_history
            if d.timestamp >= cutoff_time
        ]
        
        return {
            'report_period_hours': hours,
            'snapshots_analyzed': len(period_snapshots),
            'performance_summary': {
                'avg_cpu_efficiency': np.mean(cpu_efficiencies),
                'min_cpu_efficiency': np.min(cpu_efficiencies),
                'max_cpu_efficiency': np.max(cpu_efficiencies),
                'avg_memory_efficiency': np.mean(memory_efficiencies),
                'min_memory_efficiency': np.min(memory_efficiencies),
                'max_memory_efficiency': np.max(memory_efficiencies),
                'avg_stability_score': np.mean(stability_scores),
                'total_allocation_decisions': len(period_decisions),
                'avg_decisions_per_hour': len(period_decisions) / max(hours, 1)
            },
            'service_analysis': {
                name: {
                    'performance_score': stats.performance_score,
                    'allocation_changes': stats.allocation_changes,
                    'stability_rating': 'High' if stats.allocation_changes < 5 else 
                                      'Medium' if stats.allocation_changes < 15 else 'Low'
                }
                for name, stats in self.service_stats.items()
            },
            'recommendations': self._generate_recommendations(period_snapshots, period_decisions)
        }
    
    def _generate_recommendations(self, snapshots: List, decisions: List) -> List[str]:
        """Generate performance optimization recommendations"""
        recommendations = []
        
        if not snapshots:
            return recommendations
        
        # Analyze CPU efficiency
        cpu_efficiencies = [s.overall_cpu_efficiency for s in snapshots]
        avg_cpu_efficiency = np.mean(cpu_efficiencies)
        
        if avg_cpu_efficiency < 60:
            recommendations.append("Consider reviewing CPU allocation thresholds - efficiency is consistently low")
        
        # Analyze memory efficiency
        memory_efficiencies = [s.overall_memory_efficiency for s in snapshots]
        avg_memory_efficiency = np.mean(memory_efficiencies)
        
        if avg_memory_efficiency < 60:
            recommendations.append("Consider optimizing memory usage patterns - efficiency is consistently low")
        
        # Analyze allocation frequency
        if len(decisions) > len(snapshots) * 0.5:  # More than 0.5 decisions per snapshot
            recommendations.append("High frequency of resource reallocations detected - consider tuning adaptation sensitivity")
        
        # Analyze stability
        stability_scores = [s.system_stability_score for s in snapshots]
        avg_stability = np.mean(stability_scores)
        
        if avg_stability < 70:
            recommendations.append("System stability is below optimal - review adaptation parameters and thresholds")
        
        # Service-specific recommendations
        for name, stats in self.service_stats.items():
            if stats.allocation_changes > 20:
                recommendations.append(f"Service '{name}' shows high allocation volatility - consider adjusting its adaptation settings")
        
        if not recommendations:
            recommendations.append("System performance is optimal - no immediate recommendations")
        
        return recommendations
    
    async def shutdown(self):
        """Shutdown the performance dashboard"""
        logger.info("Shutting down Performance Dashboard")
        await self.stop_monitoring()
