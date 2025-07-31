"""
Enhanced System Monitor - Automated performance management with predictive analytics
Integrates with dynamic resource manager for intelligent system optimization
"""

import asyncio
import logging
import psutil
import time
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import deque
from pathlib import Path
import numpy as np
from enum import Enum

from .dynamic_resource_manager import DynamicResourceManager, OperationMode, ResourceMetrics
from .performance_dashboard import PerformanceDashboard
from .system_monitor import SystemMonitor

logger = logging.getLogger(__name__)


class PredictionModel(Enum):
    """Types of prediction models"""
    LINEAR_TREND = "linear_trend"
    MOVING_AVERAGE = "moving_average"
    SEASONAL_PATTERN = "seasonal_pattern"
    WORKLOAD_BASED = "workload_based"


@dataclass
class PerformancePrediction:
    """Performance prediction result"""
    metric_name: str
    current_value: float
    predicted_value: float
    prediction_horizon_minutes: int
    confidence: float
    model_used: PredictionModel
    factors: List[str]
    timestamp: datetime


@dataclass
class AutomationRule:
    """Automated performance management rule"""
    rule_id: str
    name: str
    condition: str  # Condition to trigger rule
    action: str     # Action to take
    priority: int   # Rule priority (1-10, lower is higher)
    enabled: bool
    cooldown_minutes: int
    last_triggered: Optional[datetime] = None
    trigger_count: int = 0


@dataclass
class OptimizationSuggestion:
    """System optimization suggestion"""
    suggestion_id: str
    title: str
    description: str
    category: str  # performance, stability, efficiency
    impact_score: float  # 0-100, higher is more impactful
    difficulty: str  # easy, medium, hard
    estimated_improvement: str
    implementation_steps: List[str]
    confidence: float
    timestamp: datetime


class PredictiveAnalyzer:
    """Predictive analytics for system performance"""
    
    def __init__(self):
        self.metrics_history: deque = deque(maxlen=5000)  # Larger history for predictions
        self.predictions_cache: Dict[str, PerformancePrediction] = {}
        self.seasonal_patterns: Dict[str, Dict] = {}
        
    def add_metrics(self, metrics: ResourceMetrics):
        """Add metrics for predictive analysis"""
        self.metrics_history.append(metrics)
        
        # Update seasonal patterns
        self._update_seasonal_patterns(metrics)
    
    def _update_seasonal_patterns(self, metrics: ResourceMetrics):
        """Update seasonal patterns for prediction"""
        hour = metrics.timestamp.hour
        day_of_week = metrics.timestamp.weekday()
        
        # Track hourly patterns
        if 'hourly' not in self.seasonal_patterns:
            self.seasonal_patterns['hourly'] = {h: {'cpu': [], 'memory': []} for h in range(24)}
        
        self.seasonal_patterns['hourly'][hour]['cpu'].append(metrics.cpu_percent)
        self.seasonal_patterns['hourly'][hour]['memory'].append(metrics.memory_percent)
        
        # Keep only recent data for patterns (last 30 days worth)
        max_samples = 30
        for h in range(24):
            if len(self.seasonal_patterns['hourly'][h]['cpu']) > max_samples:
                self.seasonal_patterns['hourly'][h]['cpu'] = \
                    self.seasonal_patterns['hourly'][h]['cpu'][-max_samples:]
            if len(self.seasonal_patterns['hourly'][h]['memory']) > max_samples:
                self.seasonal_patterns['hourly'][h]['memory'] = \
                    self.seasonal_patterns['hourly'][h]['memory'][-max_samples:]
    
    def predict_resource_usage(self, metric: str, horizon_minutes: int = 30) -> Optional[PerformancePrediction]:
        """Predict future resource usage"""
        if len(self.metrics_history) < 20:
            return None
        
        recent_metrics = list(self.metrics_history)[-100:]  # Last 100 samples
        
        if metric == 'cpu_percent':
            values = [m.cpu_percent for m in recent_metrics]
        elif metric == 'memory_percent':
            values = [m.memory_percent for m in recent_metrics]
        elif metric == 'temperature':
            values = [m.temperature for m in recent_metrics if m.temperature is not None]
            if not values:
                return None
        else:
            return None
        
        current_value = values[-1]
        
        # Try different prediction models
        predictions = []
        
        # Linear trend prediction
        linear_pred = self._predict_linear_trend(values, horizon_minutes)
        if linear_pred is not None:
            predictions.append((linear_pred, PredictionModel.LINEAR_TREND, 0.7))
        
        # Moving average prediction
        ma_pred = self._predict_moving_average(values, horizon_minutes)
        if ma_pred is not None:
            predictions.append((ma_pred, PredictionModel.MOVING_AVERAGE, 0.6))
        
        # Seasonal pattern prediction
        seasonal_pred = self._predict_seasonal_pattern(metric, horizon_minutes)
        if seasonal_pred is not None:
            predictions.append((seasonal_pred, PredictionModel.SEASONAL_PATTERN, 0.8))
        
        # Workload-based prediction
        workload_pred = self._predict_workload_based(values, horizon_minutes)
        if workload_pred is not None:
            predictions.append((workload_pred, PredictionModel.WORKLOAD_BASED, 0.75))
        
        if not predictions:
            return None
        
        # Use ensemble approach - weighted average of predictions
        weighted_sum = sum(pred[0] * pred[2] for pred in predictions)
        total_weight = sum(pred[2] for pred in predictions)
        predicted_value = weighted_sum / total_weight
        
        # Use the model with highest confidence for metadata
        best_prediction = max(predictions, key=lambda x: x[2])
        model_used = best_prediction[1]
        confidence = best_prediction[2]
        
        # Generate factors that influenced prediction
        factors = self._identify_prediction_factors(metric, values, predicted_value)
        
        return PerformancePrediction(
            metric_name=metric,
            current_value=current_value,
            predicted_value=predicted_value,
            prediction_horizon_minutes=horizon_minutes,
            confidence=confidence,
            model_used=model_used,
            factors=factors,
            timestamp=datetime.now()
        )
    
    def _predict_linear_trend(self, values: List[float], horizon_minutes: int) -> Optional[float]:
        """Predict using linear trend analysis"""
        if len(values) < 10:
            return None
        
        # Use last 20 points for trend
        trend_values = values[-20:]
        x = np.arange(len(trend_values))
        
        # Calculate linear regression
        coeffs = np.polyfit(x, trend_values, 1)
        slope, intercept = coeffs
        
        # Predict future value
        future_x = len(trend_values) + (horizon_minutes / 5)  # Assuming 5-minute intervals
        predicted = slope * future_x + intercept
        
        # Clamp to reasonable bounds
        return max(0, min(100, predicted))
    
    def _predict_moving_average(self, values: List[float], horizon_minutes: int) -> Optional[float]:
        """Predict using exponential moving average"""
        if len(values) < 5:
            return None
        
        # Calculate exponential moving average
        alpha = 0.3  # Smoothing factor
        ema = values[0]
        
        for value in values[1:]:
            ema = alpha * value + (1 - alpha) * ema
        
        return ema
    
    def _predict_seasonal_pattern(self, metric: str, horizon_minutes: int) -> Optional[float]:
        """Predict using seasonal patterns"""
        if 'hourly' not in self.seasonal_patterns:
            return None
        
        future_time = datetime.now() + timedelta(minutes=horizon_minutes)
        future_hour = future_time.hour
        
        if metric == 'cpu_percent':
            historical_values = self.seasonal_patterns['hourly'][future_hour]['cpu']
        elif metric == 'memory_percent':
            historical_values = self.seasonal_patterns['hourly'][future_hour]['memory']
        else:
            return None
        
        if not historical_values:
            return None
        
        # Use median of historical values for that hour
        return np.median(historical_values)
    
    def _predict_workload_based(self, values: List[float], horizon_minutes: int) -> Optional[float]:
        """Predict based on workload patterns"""
        if len(values) < 15:
            return None
        
        # Analyze recent trend and variability
        recent = values[-10:]
        older = values[-20:-10]
        
        recent_avg = np.mean(recent)
        older_avg = np.mean(older)
        variability = np.std(recent)
        
        # If trend is increasing and variability is high, predict continued increase
        if recent_avg > older_avg and variability > 5:
            trend_factor = (recent_avg - older_avg) * 0.5
            return min(100, recent_avg + trend_factor)
        
        # If stable, predict continuation
        return recent_avg
    
    def _identify_prediction_factors(self, metric: str, values: List[float], predicted: float) -> List[str]:
        """Identify factors influencing the prediction"""
        factors = []
        current = values[-1]
        
        # Trend analysis
        if len(values) >= 10:
            recent_trend = np.mean(values[-5:]) - np.mean(values[-10:-5])
            if abs(recent_trend) > 2:
                direction = "increasing" if recent_trend > 0 else "decreasing"
                factors.append(f"{direction} trend")
        
        # Variability analysis
        variability = np.std(values[-10:]) if len(values) >= 10 else 0
        if variability > 10:
            factors.append("high variability")
        elif variability < 2:
            factors.append("stable pattern")
        
        # Magnitude analysis
        if current > 80:
            factors.append("high current usage")
        elif current < 20:
            factors.append("low current usage")
        
        # Prediction magnitude
        change = abs(predicted - current)
        if change > 10:
            factors.append("significant change expected")
        elif change < 2:
            factors.append("minimal change expected")
        
        return factors


class AutomationEngine:
    """Automated performance management engine"""
    
    def __init__(self, resource_manager: DynamicResourceManager):
        self.resource_manager = resource_manager
        self.rules: Dict[str, AutomationRule] = {}
        self.rule_history: deque = deque(maxlen=1000)
        
        # Initialize default automation rules
        self._initialize_default_rules()
    
    def _initialize_default_rules(self):
        """Initialize default automation rules"""
        
        # High CPU usage rule
        self.rules['high_cpu_pressure'] = AutomationRule(
            rule_id='high_cpu_pressure',
            name='High CPU Pressure Response',
            condition='cpu_percent > 85 for 3 minutes',
            action='reduce_non_critical_allocations',
            priority=1,
            enabled=True,
            cooldown_minutes=5
        )
        
        # Memory pressure rule
        self.rules['memory_pressure'] = AutomationRule(
            rule_id='memory_pressure',
            name='Memory Pressure Response',
            condition='memory_percent > 80 for 2 minutes',
            action='reduce_memory_allocations',
            priority=2,
            enabled=True,
            cooldown_minutes=3
        )
        
        # Temperature management rule
        self.rules['temperature_control'] = AutomationRule(
            rule_id='temperature_control',
            name='Temperature Control',
            condition='temperature > 75°C for 1 minute',
            action='reduce_cpu_intensive_tasks',
            priority=1,
            enabled=True,
            cooldown_minutes=2
        )
        
        # Low efficiency rule
        self.rules['efficiency_optimization'] = AutomationRule(
            rule_id='efficiency_optimization',
            name='Efficiency Optimization',
            condition='overall_efficiency < 60 for 10 minutes',
            action='rebalance_resources',
            priority=3,
            enabled=True,
            cooldown_minutes=15
        )
        
        # Idle resource recovery rule
        self.rules['idle_resource_recovery'] = AutomationRule(
            rule_id='idle_resource_recovery',
            name='Idle Resource Recovery',
            condition='cpu_percent < 30 and memory_percent < 50 for 5 minutes',
            action='increase_adaptive_allocations',
            priority=4,
            enabled=True,
            cooldown_minutes=10
        )
    
    async def evaluate_rules(self, current_metrics: ResourceMetrics, 
                           efficiency_scores: Dict[str, float]) -> List[str]:
        """Evaluate automation rules and return triggered actions"""
        triggered_actions = []
        current_time = datetime.now()
        
        for rule in self.rules.values():
            if not rule.enabled:
                continue
            
            # Check cooldown
            if (rule.last_triggered and 
                (current_time - rule.last_triggered).total_seconds() < rule.cooldown_minutes * 60):
                continue
            
            # Evaluate rule condition
            if await self._evaluate_condition(rule.condition, current_metrics, efficiency_scores):
                # Execute rule action
                action_result = await self._execute_action(rule.action, current_metrics)
                if action_result:
                    triggered_actions.append(f"{rule.name}: {action_result}")
                    rule.last_triggered = current_time
                    rule.trigger_count += 1
                    
                    # Log rule trigger
                    self.rule_history.append({
                        'rule_id': rule.rule_id,
                        'rule_name': rule.name,
                        'action': rule.action,
                        'result': action_result,
                        'timestamp': current_time,
                        'metrics': asdict(current_metrics)
                    })
                    
                    logger.info(f"Automation rule triggered: {rule.name} -> {action_result}")
        
        return triggered_actions
    
    async def _evaluate_condition(self, condition: str, metrics: ResourceMetrics, 
                                efficiency_scores: Dict[str, float]) -> bool:
        """Evaluate a rule condition"""
        try:
            # Simple condition evaluation (in production, use a proper expression parser)
            
            if 'cpu_percent > 85' in condition:
                return metrics.cpu_percent > 85
            
            if 'memory_percent > 80' in condition:
                return metrics.memory_percent > 80
            
            if 'temperature > 75' in condition and metrics.temperature:
                return metrics.temperature > 75
            
            if 'overall_efficiency < 60' in condition:
                return efficiency_scores.get('overall_efficiency', 100) < 60
            
            if 'cpu_percent < 30 and memory_percent < 50' in condition:
                return metrics.cpu_percent < 30 and metrics.memory_percent < 50
            
            return False
            
        except Exception as e:
            logger.error(f"Error evaluating condition '{condition}': {e}")
            return False
    
    async def _execute_action(self, action: str, metrics: ResourceMetrics) -> Optional[str]:
        """Execute an automation action"""
        try:
            if action == 'reduce_non_critical_allocations':
                # Reduce allocations for non-critical services
                decisions = []
                for service_name, profile in self.resource_manager.service_profiles.items():
                    if not profile.critical and profile.adaptive:
                        current_limits = self.resource_manager.current_allocations[service_name]
                        new_cpu = current_limits.cpu_percent * 0.8  # 20% reduction
                        
                        from .dynamic_resource_manager import AllocationDecision, ResourceType
                        decisions.append(AllocationDecision(
                            service_name=service_name,
                            resource_type=ResourceType.CPU,
                            old_value=current_limits.cpu_percent,
                            new_value=new_cpu,
                            reason="Automated CPU pressure response",
                            timestamp=datetime.now(),
                            confidence=0.9
                        ))
                
                if decisions:
                    await self.resource_manager._apply_allocation_decisions(decisions)
                    return f"Reduced CPU allocation for {len(decisions)} services"
            
            elif action == 'reduce_memory_allocations':
                # Reduce memory allocations
                decisions = []
                for service_name, profile in self.resource_manager.service_profiles.items():
                    if not profile.critical and profile.adaptive:
                        current_limits = self.resource_manager.current_allocations[service_name]
                        new_memory = current_limits.memory_mb * 0.85  # 15% reduction
                        
                        from .dynamic_resource_manager import AllocationDecision, ResourceType
                        decisions.append(AllocationDecision(
                            service_name=service_name,
                            resource_type=ResourceType.MEMORY,
                            old_value=current_limits.memory_mb,
                            new_value=new_memory,
                            reason="Automated memory pressure response",
                            timestamp=datetime.now(),
                            confidence=0.9
                        ))
                
                if decisions:
                    await self.resource_manager._apply_allocation_decisions(decisions)
                    return f"Reduced memory allocation for {len(decisions)} services"
            
            elif action == 'reduce_cpu_intensive_tasks':
                # Reduce CPU-intensive operations for thermal management
                await self.resource_manager.set_operation_mode(OperationMode.IDLE)
                return "Switched to idle mode for thermal management"
            
            elif action == 'rebalance_resources':
                # Trigger resource rebalancing
                current_metrics = await self.resource_manager._collect_metrics()
                decisions = await self.resource_manager._analyze_and_adapt(current_metrics)
                if decisions:
                    await self.resource_manager._apply_allocation_decisions(decisions)
                    return f"Rebalanced resources with {len(decisions)} changes"
            
            elif action == 'increase_adaptive_allocations':
                # Increase allocations when resources are idle
                decisions = await self.resource_manager._increase_allocations(
                    sorted(self.resource_manager.service_profiles.items(), 
                          key=lambda x: x[1].priority)
                )
                if decisions:
                    await self.resource_manager._apply_allocation_decisions(decisions)
                    return f"Increased allocations for {len(decisions)} services"
            
            return None
            
        except Exception as e:
            logger.error(f"Error executing action '{action}': {e}")
            return f"Error: {str(e)}"


class EnhancedSystemMonitor:
    """
    Enhanced system monitor with predictive analytics and automated optimization
    """
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        
        # Core components
        self.resource_manager = DynamicResourceManager(config_manager)
        self.dashboard = PerformanceDashboard(self.resource_manager)
        self.predictive_analyzer = PredictiveAnalyzer()
        self.automation_engine = AutomationEngine(self.resource_manager)
        
        # Monitoring state
        self.monitoring_active = False
        self.monitor_task: Optional[asyncio.Task] = None
        self.prediction_task: Optional[asyncio.Task] = None
        
        # Performance optimization
        self.optimization_suggestions: deque = deque(maxlen=100)
        self.optimization_interval = 300  # 5 minutes
        self.last_optimization_check = 0.0
        
        # Prediction settings
        self.prediction_interval = 60  # 1 minute
        self.prediction_horizons = [15, 30, 60]  # minutes
        
    async def initialize(self):
        """Initialize the enhanced system monitor"""
        logger.info("Initializing Enhanced System Monitor")
        
        # Initialize components
        await self.resource_manager.initialize()
        await self.dashboard.initialize()
        
        # Start monitoring
        await self.start_monitoring()
        
        logger.info("Enhanced System Monitor initialized")
    
    async def start_monitoring(self):
        """Start enhanced monitoring"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        
        # Start monitoring tasks
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        self.prediction_task = asyncio.create_task(self._prediction_loop())
        
        logger.info("Enhanced system monitoring started")
    
    async def stop_monitoring(self):
        """Stop enhanced monitoring"""
        self.monitoring_active = False
        
        # Cancel tasks
        if self.monitor_task:
            self.monitor_task.cancel()
        if self.prediction_task:
            self.prediction_task.cancel()
        
        # Wait for tasks to complete
        for task in [self.monitor_task, self.prediction_task]:
            if task:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Stop components
        await self.dashboard.stop_monitoring()
        await self.resource_manager.stop_monitoring()
        
        logger.info("Enhanced system monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main enhanced monitoring loop"""
        while self.monitoring_active:
            try:
                # Get current metrics
                current_metrics = await self.resource_manager._collect_metrics()
                
                # Add to predictive analyzer
                self.predictive_analyzer.add_metrics(current_metrics)
                
                # Get efficiency scores
                efficiency_scores = self.dashboard.analyzer.calculate_efficiency_scores()
                
                # Evaluate automation rules
                automation_actions = await self.automation_engine.evaluate_rules(
                    current_metrics, efficiency_scores
                )
                
                # Check for optimization opportunities
                if time.time() - self.last_optimization_check > self.optimization_interval:
                    await self._check_optimization_opportunities(current_metrics, efficiency_scores)
                    self.last_optimization_check = time.time()
                
                # Log automation actions
                if automation_actions:
                    logger.info(f"Automation actions taken: {automation_actions}")
                
                await asyncio.sleep(30)  # Enhanced monitoring every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in enhanced monitoring loop: {e}")
                await asyncio.sleep(30)
    
    async def _prediction_loop(self):
        """Predictive analytics loop"""
        while self.monitoring_active:
            try:
                # Generate predictions for key metrics
                predictions = {}
                
                for metric in ['cpu_percent', 'memory_percent', 'temperature']:
                    for horizon in self.prediction_horizons:
                        prediction = self.predictive_analyzer.predict_resource_usage(metric, horizon)
                        if prediction:
                            key = f"{metric}_{horizon}min"
                            predictions[key] = prediction
                            self.predictive_analyzer.predictions_cache[key] = prediction
                
                # Analyze predictions for proactive actions
                await self._analyze_predictions(predictions)
                
                await asyncio.sleep(self.prediction_interval)
                
            except Exception as e:
                logger.error(f"Error in prediction loop: {e}")
                await asyncio.sleep(self.prediction_interval)
    
    async def _analyze_predictions(self, predictions: Dict[str, PerformancePrediction]):
        """Analyze predictions for proactive optimization"""
        proactive_actions = []
        
        for pred_key, prediction in predictions.items():
            # Check for predicted problems
            if prediction.metric_name == 'cpu_percent' and prediction.predicted_value > 90:
                if prediction.confidence > 0.7:
                    proactive_actions.append(
                        f"Predicted high CPU usage ({prediction.predicted_value:.1f}%) "
                        f"in {prediction.prediction_horizon_minutes} minutes"
                    )
            
            elif prediction.metric_name == 'memory_percent' and prediction.predicted_value > 85:
                if prediction.confidence > 0.7:
                    proactive_actions.append(
                        f"Predicted high memory usage ({prediction.predicted_value:.1f}%) "
                        f"in {prediction.prediction_horizon_minutes} minutes"
                    )
            
            elif prediction.metric_name == 'temperature' and prediction.predicted_value > 75:
                if prediction.confidence > 0.6:
                    proactive_actions.append(
                        f"Predicted high temperature ({prediction.predicted_value:.1f}°C) "
                        f"in {prediction.prediction_horizon_minutes} minutes"
                    )
        
        # Take proactive actions if needed
        if proactive_actions:
            logger.info(f"Proactive predictions: {proactive_actions}")
            # Could trigger pre-emptive resource adjustments here
    
    async def _check_optimization_opportunities(self, metrics: ResourceMetrics, 
                                             efficiency_scores: Dict[str, float]):
        """Check for system optimization opportunities"""
        suggestions = []
        
        # Analyze current performance
        overall_efficiency = efficiency_scores.get('overall_efficiency', 100)
        cpu_efficiency = efficiency_scores.get('cpu_efficiency', 100)
        memory_efficiency = efficiency_scores.get('memory_efficiency', 100)
        
        # CPU optimization suggestions
        if cpu_efficiency < 70:
            if metrics.cpu_percent > 80:
                suggestions.append(OptimizationSuggestion(
                    suggestion_id=f"cpu_opt_{int(time.time())}",
                    title="Optimize CPU Usage",
                    description="CPU efficiency is low due to high utilization",
                    category="performance",
                    impact_score=80.0,
                    difficulty="medium",
                    estimated_improvement="10-20% better CPU efficiency",
                    implementation_steps=[
                        "Review high-CPU services",
                        "Consider load balancing",
                        "Optimize processing algorithms"
                    ],
                    confidence=0.8,
                    timestamp=datetime.now()
                ))
            elif metrics.cpu_percent < 30:
                suggestions.append(OptimizationSuggestion(
                    suggestion_id=f"cpu_underutil_{int(time.time())}",
                    title="Address CPU Under-utilization",
                    description="CPU resources are being under-utilized",
                    category="efficiency",
                    impact_score=60.0,
                    difficulty="easy",
                    estimated_improvement="5-10% better resource utilization",
                    implementation_steps=[
                        "Increase allocation for adaptive services",
                        "Consider running additional background tasks"
                    ],
                    confidence=0.7,
                    timestamp=datetime.now()
                ))
        
        # Memory optimization suggestions
        if memory_efficiency < 70:
            suggestions.append(OptimizationSuggestion(
                suggestion_id=f"memory_opt_{int(time.time())}",
                title="Optimize Memory Usage",
                description="Memory efficiency could be improved",
                category="performance",
                impact_score=75.0,
                difficulty="medium",
                estimated_improvement="15-25% better memory efficiency",
                implementation_steps=[
                    "Review memory allocation patterns",
                    "Implement memory pooling",
                    "Optimize data structures"
                ],
                confidence=0.75,
                timestamp=datetime.now()
            ))
        
        # System stability suggestions
        stability_score = self.dashboard._calculate_stability_score()
        if stability_score < 80:
            suggestions.append(OptimizationSuggestion(
                suggestion_id=f"stability_opt_{int(time.time())}",
                title="Improve System Stability",
                description="System shows stability issues with frequent resource changes",
                category="stability",
                impact_score=90.0,
                difficulty="hard",
                estimated_improvement="20-30% better stability",
                implementation_steps=[
                    "Review adaptation thresholds",
                    "Implement dampening mechanisms",
                    "Add service health checks"
                ],
                confidence=0.85,
                timestamp=datetime.now()
            ))
        
        # Add suggestions to queue
        for suggestion in suggestions:
            self.optimization_suggestions.append(suggestion)
            logger.info(f"New optimization suggestion: {suggestion.title}")
    
    async def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get comprehensive system status including predictions and suggestions"""
        # Get base dashboard data
        dashboard_data = await self.dashboard.get_dashboard_data()
        
        # Add predictions
        predictions = {}
        for key, prediction in self.predictive_analyzer.predictions_cache.items():
            predictions[key] = asdict(prediction)
        
        # Add automation status
        automation_status = {
            'rules_enabled': len([r for r in self.automation_engine.rules.values() if r.enabled]),
            'total_rules': len(self.automation_engine.rules),
            'recent_triggers': len([h for h in self.automation_engine.rule_history 
                                  if (datetime.now() - h['timestamp']).total_seconds() < 3600]),
            'rules': {
                rule_id: {
                    'name': rule.name,
                    'enabled': rule.enabled,
                    'trigger_count': rule.trigger_count,
                    'last_triggered': rule.last_triggered.isoformat() if rule.last_triggered else None
                }
                for rule_id, rule in self.automation_engine.rules.items()
            }
        }
        
        # Add optimization suggestions
        recent_suggestions = [
            asdict(suggestion) for suggestion in list(self.optimization_suggestions)[-10:]
        ]
        
        return {
            **dashboard_data,
            'predictions': predictions,
            'automation': automation_status,
            'optimization_suggestions': recent_suggestions,
            'enhanced_monitoring': {
                'active': self.monitoring_active,
                'prediction_models_active': len(self.predictive_analyzer.predictions_cache),
                'seasonal_patterns_learned': len(self.predictive_analyzer.seasonal_patterns),
                'total_suggestions_generated': len(self.optimization_suggestions)
            }
        }
    
    async def set_operation_mode(self, mode: OperationMode):
        """Set operation mode with enhanced monitoring"""
        await self.resource_manager.set_operation_mode(mode)
        logger.info(f"Enhanced monitoring: Operation mode changed to {mode.value}")
    
    async def get_performance_predictions(self, horizon_minutes: int = 30) -> Dict[str, Any]:
        """Get performance predictions for specified horizon"""
        predictions = {}
        
        for metric in ['cpu_percent', 'memory_percent', 'temperature']:
            prediction = self.predictive_analyzer.predict_resource_usage(metric, horizon_minutes)
            if prediction:
                predictions[metric] = asdict(prediction)
        
        return {
            'horizon_minutes': horizon_minutes,
            'predictions': predictions,
            'generated_at': datetime.now().isoformat()
        }
    
    async def enable_automation_rule(self, rule_id: str) -> bool:
        """Enable an automation rule"""
        if rule_id in self.automation_engine.rules:
            self.automation_engine.rules[rule_id].enabled = True
            logger.info(f"Enabled automation rule: {rule_id}")
            return True
        return False
    
    async def disable_automation_rule(self, rule_id: str) -> bool:
        """Disable an automation rule"""
        if rule_id in self.automation_engine.rules:
            self.automation_engine.rules[rule_id].enabled = False
            logger.info(f"Disabled automation rule: {rule_id}")
            return True
        return False
    
    async def shutdown(self):
        """Shutdown the enhanced system monitor"""
        logger.info("Shutting down Enhanced System Monitor")
        
        await self.stop_monitoring()
        await self.dashboard.shutdown()
        await self.resource_manager.shutdown()
        
        logger.info("Enhanced System Monitor shutdown complete")
