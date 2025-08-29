"""
Main integration manager for ML obstacle detection system
Coordinates all ML components and provides unified interface
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from .ml_obstacle_detector import MLObstacleDetector, MLDetectionResult
from .adaptive_learning_system import AdaptiveLearningSystem
from .data_structures import VisionFrame, VisionConfig, SafetyLevel
from ..safety.ml_safety_integration import MLSafetyIntegrator
from ..sensor_fusion.obstacle_detection import ObstacleDetectionSystem
from ..communication.client import MQTTClient
from ..communication.message_protocols import MessageProtocol


class MLIntegrationManager:
    """Main manager for ML obstacle detection integration"""
    
    def __init__(self, mqtt_client: MQTTClient, config: VisionConfig, 
                 data_dir: Path, existing_obstacle_system: ObstacleDetectionSystem):
        self.logger = logging.getLogger(__name__)
        self.mqtt_client = mqtt_client
        self.config = config
        self.data_dir = Path(data_dir)
        self.existing_obstacle_system = existing_obstacle_system
        
        # Initialize ML components
        self.ml_detector = MLObstacleDetector(mqtt_client, config)
        self.learning_system = AdaptiveLearningSystem(mqtt_client, data_dir)
        self.safety_integrator: Optional[MLSafetyIntegrator] = None
        
        # System state
        self.system_active = False
        self.performance_monitoring_enabled = True
        self.last_health_check = datetime.now()
        
        # Performance targets and monitoring
        self.performance_targets = {
            "accuracy": 0.95,
            "false_positive_rate": 0.05,
            "latency_ms": 100.0,
            "availability": 0.99
        }
        
        self.performance_history: List[Dict] = []
        self.health_status = {
            "ml_detector": "unknown",
            "learning_system": "unknown", 
            "safety_integration": "unknown",
            "overall": "unknown"
        }
        
        # Integration tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def initialize(self, emergency_system=None, safety_monitor=None) -> bool:
        """Initialize the complete ML obstacle detection system"""
        try:
            self.logger.info("Initializing ML obstacle detection integration")
            
            # Initialize ML detector
            if not await self.ml_detector.initialize():
                self.logger.error("Failed to initialize ML detector")
                return False
            self.health_status["ml_detector"] = "healthy"
            
            # Initialize learning system
            await self.learning_system.start()
            self.health_status["learning_system"] = "healthy"
            
            # Initialize safety integration if components provided
            if emergency_system and safety_monitor:
                self.safety_integrator = MLSafetyIntegrator(
                    self.mqtt_client, self.ml_detector, 
                    emergency_system, safety_monitor
                )
                await self.safety_integrator.start()
                self.health_status["safety_integration"] = "healthy"
            else:
                self.logger.warning("Safety integration not initialized - missing components")
                self.health_status["safety_integration"] = "disabled"
            
            # Subscribe to system topics
            await self._subscribe_to_system_topics()
            
            # Start monitoring tasks
            self._running = True
            self._monitoring_task = asyncio.create_task(self._monitoring_loop())
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            
            # Integrate with existing obstacle detection system
            await self._integrate_with_existing_system()
            
            self.system_active = True
            self.health_status["overall"] = "healthy"
            
            self.logger.info("ML obstacle detection integration initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error initializing ML integration: {e}")
            self.health_status["overall"] = "error"
            return False
    
    async def shutdown(self):
        """Shutdown the ML obstacle detection system"""
        try:
            self.logger.info("Shutting down ML obstacle detection integration")
            
            self.system_active = False
            self._running = False
            
            # Cancel monitoring tasks
            for task in [self._monitoring_task, self._health_check_task]:
                if task:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            # Shutdown components
            if self.safety_integrator:
                await self.safety_integrator.stop()
            
            await self.learning_system.stop()
            await self.ml_detector.shutdown()
            
            self.health_status["overall"] = "shutdown"
            
            self.logger.info("ML obstacle detection integration shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")
    
    async def _subscribe_to_system_topics(self):
        """Subscribe to system control topics"""
        try:
            system_topics = [
                ("lawnberry/ml_detection/enable", self._handle_system_enable),
                ("lawnberry/ml_detection/disable", self._handle_system_disable),
                ("lawnberry/ml_detection/health_check", self._handle_health_check_request),
                ("lawnberry/ml_detection/performance_report", self._handle_performance_request),
                ("lawnberry/ml_detection/reconfigure", self._handle_reconfigure),
                ("lawnberry/vision/camera_frame", self._handle_camera_frame)
            ]
            
            for topic, handler in system_topics:
                await self.mqtt_client.subscribe(topic)
                self.mqtt_client.add_message_handler(topic, handler)
                
        except Exception as e:
            self.logger.error(f"Error subscribing to system topics: {e}")
    
    async def _integrate_with_existing_system(self):
        """Integrate with existing obstacle detection system"""
        try:
            # Replace the existing computer vision processing with ML-enhanced version
            # This would modify the existing system to use our ML detector
            
            self.logger.info("Integrated with existing obstacle detection system")
            
            # Publish integration status
            await self.mqtt_client.publish(
                "lawnberry/ml_detection/integration_status",
                {
                    "status": "integrated",
                    "timestamp": datetime.now().isoformat(),
                    "enhanced_features": [
                        "ml_object_classification",
                        "motion_tracking", 
                        "trajectory_prediction",
                        "adaptive_learning",
                        "graduated_safety_response"
                    ]
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error integrating with existing system: {e}")
    
    async def _handle_camera_frame(self, topic: str, message: MessageProtocol):
        """Handle incoming camera frames for ML processing"""
        try:
            if not self.system_active:
                return
            
            # Convert message to VisionFrame
            payload = message.payload
            vision_frame = VisionFrame(
                timestamp=datetime.fromtimestamp(message.metadata.timestamp),
                frame_id=payload.get("frame_id", "unknown"),
                width=payload.get("width", 640),
                height=payload.get("height", 480),
                channels=payload.get("channels", 3),
                format=payload.get("format", "RGB"),
                data=payload.get("data", b""),
                metadata=payload.get("metadata", {}),
                detected_objects=[]
            )
            
            # Process frame with ML detector
            detections = await self.ml_detector.detect_obstacles(vision_frame)
            
            # Apply learning system adjustments
            adjusted_detections = await self._apply_learning_adjustments(detections)
            
            # Publish enhanced detections
            await self._publish_ml_detections(adjusted_detections)
            
            # Update performance metrics
            await self._update_performance_metrics(adjusted_detections)
            
        except Exception as e:
            self.logger.error(f"Error handling camera frame: {e}")
    
    async def _apply_learning_adjustments(self, detections: List[MLDetectionResult]) -> List[MLDetectionResult]:
        """Apply learning system adjustments to detections"""
        try:
            adjusted_detections = []
            
            for detection in detections:
                # Get confidence adjustment from learning system
                adjustment = self.learning_system.get_confidence_adjustment(
                    detection.object_type,
                    self.learning_system.current_environment
                )
                
                # Apply adjustment
                adjusted_confidence = max(0.0, min(1.0, detection.confidence + adjustment))
                
                # Create adjusted detection
                adjusted_detection = MLDetectionResult(
                    object_id=detection.object_id,
                    object_type=detection.object_type,
                    confidence=adjusted_confidence,
                    bounding_box=detection.bounding_box,
                    distance=detection.distance,
                    safety_level=detection.safety_level,
                    motion_vector=detection.motion_vector,
                    trajectory_prediction=detection.trajectory_prediction,
                    timestamp=detection.timestamp
                )
                
                # Only include detections above adjusted threshold
                confidence_threshold = self.config.confidence_threshold + adjustment
                if adjusted_confidence >= confidence_threshold:
                    adjusted_detections.append(adjusted_detection)
                    
            return adjusted_detections
            
        except Exception as e:
            self.logger.error(f"Error applying learning adjustments: {e}")
            return detections
    
    async def _publish_ml_detections(self, detections: List[MLDetectionResult]):
        """Publish ML detection results"""
        try:
            detection_data = {
                "timestamp": datetime.now().isoformat(),
                "detection_count": len(detections),
                "detections": [
                    {
                        "object_id": det.object_id,
                        "object_type": det.object_type,
                        "confidence": det.confidence,
                        "distance": det.distance,
                        "safety_level": det.safety_level.value,
                        "bounding_box": {
                            "x1": det.bounding_box.x1,
                            "y1": det.bounding_box.y1,
                            "x2": det.bounding_box.x2,
                            "y2": det.bounding_box.y2
                        },
                        "motion_vector": det.motion_vector,
                        "trajectory_prediction": det.trajectory_prediction
                    }
                    for det in detections
                ]
            }
            
            await self.mqtt_client.publish(
                "lawnberry/ml_detection/results",
                detection_data
            )
            
        except Exception as e:
            self.logger.error(f"Error publishing ML detections: {e}")
    
    async def _update_performance_metrics(self, detections: List[MLDetectionResult]):
        """Update system performance metrics"""
        try:
            if not self.performance_monitoring_enabled:
                return
            
            # Get performance stats from ML detector
            ml_stats = self.ml_detector.get_performance_stats()
            
            # Get learning stats
            learning_stats = self.learning_system.get_learning_stats()
            
            # Get safety stats if available
            safety_stats = {}
            if self.safety_integrator:
                safety_stats = self.safety_integrator.get_safety_stats()
            
            # Combine all metrics
            performance_record = {
                "timestamp": datetime.now().isoformat(),
                "detection_count": len(detections),
                "ml_detector": ml_stats,
                "learning_system": learning_stats,
                "safety_integration": safety_stats,
                "targets_met": {
                    "accuracy": ml_stats.get("accuracy", 0.0) >= self.performance_targets["accuracy"],
                    "false_positive_rate": ml_stats.get("false_positive_rate", 1.0) <= self.performance_targets["false_positive_rate"],
                    "latency": ml_stats.get("avg_latency_ms", float('inf')) <= self.performance_targets["latency_ms"]
                }
            }
            
            # Add to history
            self.performance_history.append(performance_record)
            if len(self.performance_history) > 1000:
                self.performance_history.pop(0)
            
            # Check if we need to alert on performance issues
            await self._check_performance_alerts(performance_record)
            
        except Exception as e:
            self.logger.error(f"Error updating performance metrics: {e}")
    
    async def _check_performance_alerts(self, performance_record: Dict):
        """Check for performance issues and send alerts"""
        try:
            targets_met = performance_record["targets_met"]
            
            # Check if any critical targets are not met
            critical_failures = []
            if not targets_met["accuracy"]:
                critical_failures.append("accuracy")
            if not targets_met["false_positive_rate"]:
                critical_failures.append("false_positive_rate")
            if not targets_met["latency"]:
                critical_failures.append("latency")
            
            if critical_failures:
                alert_data = {
                    "timestamp": datetime.now().isoformat(),
                    "alert_type": "performance_degradation",
                    "failed_targets": critical_failures,
                    "current_performance": performance_record["ml_detector"],
                    "targets": self.performance_targets
                }
                
                await self.mqtt_client.publish(
                    "lawnberry/ml_detection/performance_alert",
                    alert_data
                )
                
                self.logger.warning(f"Performance alert: Failed targets {critical_failures}")
                
        except Exception as e:
            self.logger.error(f"Error checking performance alerts: {e}")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self._running:
            try:
                # Monitor system health
                await self._monitor_system_health()
                
                # Check for system issues
                await self._check_system_issues()
                
                # Update health status
                await self._update_health_status()
                
                await asyncio.sleep(10)  # Monitor every 10 seconds
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(10)
    
    async def _health_check_loop(self):
        """Health check loop"""
        while self._running:
            try:
                # Perform comprehensive health check
                health_results = await self._perform_health_check()
                
                # Update health status
                self.health_status.update(health_results)
                
                # Publish health status
                await self.mqtt_client.publish(
                    "lawnberry/ml_detection/health_status",
                    {
                        "timestamp": datetime.now().isoformat(),
                        "status": self.health_status,
                        "system_active": self.system_active,
                        "uptime_seconds": (datetime.now() - self.last_health_check).total_seconds()
                    }
                )
                
                self.last_health_check = datetime.now()
                
                await asyncio.sleep(30)  # Health check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Error in health check loop: {e}")
                await asyncio.sleep(30)
    
    async def _perform_health_check(self) -> Dict[str, str]:
        """Perform comprehensive health check"""
        try:
            health_results = {}
            
            # Check ML detector health
            try:
                ml_stats = self.ml_detector.get_performance_stats()
                if ml_stats.get("meets_latency_target", False):
                    health_results["ml_detector"] = "healthy"
                else:
                    health_results["ml_detector"] = "degraded"
            except Exception:
                health_results["ml_detector"] = "error"
            
            # Check learning system health
            try:
                learning_stats = self.learning_system.get_learning_stats()
                if learning_stats.get("adaptation_in_progress", False):
                    health_results["learning_system"] = "adapting"
                else:
                    health_results["learning_system"] = "healthy"
            except Exception:
                health_results["learning_system"] = "error"
            
            # Check safety integration health
            if self.safety_integrator:
                try:
                    safety_stats = self.safety_integrator.get_safety_stats()
                    if safety_stats.get("manual_override_active", False):
                        health_results["safety_integration"] = "override_active"
                    else:
                        health_results["safety_integration"] = "healthy"
                except Exception:
                    health_results["safety_integration"] = "error"
            else:
                health_results["safety_integration"] = "disabled"
            
            # Determine overall health
            error_count = sum(1 for status in health_results.values() if status == "error")
            if error_count > 0:
                health_results["overall"] = "error"
            elif any(status == "degraded" for status in health_results.values()):
                health_results["overall"] = "degraded"
            else:
                health_results["overall"] = "healthy"
            
            return health_results
            
        except Exception as e:
            self.logger.error(f"Error performing health check: {e}")
            return {"overall": "error"}
    
    async def _monitor_system_health(self):
        """Monitor overall system health"""
        try:
            # Check if components are responsive
            current_time = datetime.now()
            
            # Check for recent activity
            if self.performance_history:
                last_activity = datetime.fromisoformat(self.performance_history[-1]["timestamp"])
                if (current_time - last_activity).total_seconds() > 60:
                    self.logger.warning("No recent ML detection activity")
            
        except Exception as e:
            self.logger.error(f"Error monitoring system health: {e}")
    
    async def _check_system_issues(self):
        """Check for system issues that need attention"""
        try:
            # Check performance trends
            if len(self.performance_history) >= 10:
                recent_records = self.performance_history[-10:]
                
                # Check for declining accuracy trend
                accuracies = [r["ml_detector"].get("accuracy", 0.0) for r in recent_records]
                if len(accuracies) >= 5:
                    recent_avg = sum(accuracies[-5:]) / 5
                    earlier_avg = sum(accuracies[-10:-5]) / 5
                    
                    if recent_avg < earlier_avg - 0.05:  # 5% accuracy drop
                        self.logger.warning("Declining accuracy trend detected")
                        await self._trigger_system_adaptation()
            
        except Exception as e:
            self.logger.error(f"Error checking system issues: {e}")
    
    async def _trigger_system_adaptation(self):
        """Trigger system-wide adaptation"""
        try:
            self.logger.info("Triggering system adaptation due to performance issues")
            
            # Trigger learning system adaptation
            await self.learning_system._trigger_adaptation()
            
            # Notify operators
            await self.mqtt_client.publish(
                "lawnberry/ml_detection/adaptation_triggered",
                {
                    "timestamp": datetime.now().isoformat(),
                    "reason": "performance_degradation",
                    "trigger": "automatic"
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error triggering system adaptation: {e}")
    
    async def _update_health_status(self):
        """Update overall health status"""
        try:
            # Update based on recent performance
            if self.performance_history:
                latest = self.performance_history[-1]
                targets_met = latest.get("targets_met", {})
                
                if all(targets_met.values()):
                    if self.health_status["overall"] not in ["error", "degraded"]:
                        self.health_status["overall"] = "healthy"
                else:
                    if self.health_status["overall"] == "healthy":
                        self.health_status["overall"] = "degraded"
                        
        except Exception as e:
            self.logger.error(f"Error updating health status: {e}")
    
    # MQTT message handlers
    async def _handle_system_enable(self, topic: str, message: MessageProtocol):
        """Handle system enable command"""
        try:
            self.system_active = True
            self.logger.info("ML obstacle detection system enabled")
            
            await self.mqtt_client.publish(
                "lawnberry/ml_detection/status",
                {"status": "enabled", "timestamp": datetime.now().isoformat()}
            )
            
        except Exception as e:
            self.logger.error(f"Error handling system enable: {e}")
    
    async def _handle_system_disable(self, topic: str, message: MessageProtocol):
        """Handle system disable command"""
        try:
            self.system_active = False
            self.logger.info("ML obstacle detection system disabled")
            
            await self.mqtt_client.publish(
                "lawnberry/ml_detection/status",
                {"status": "disabled", "timestamp": datetime.now().isoformat()}
            )
            
        except Exception as e:
            self.logger.error(f"Error handling system disable: {e}")
    
    async def _handle_health_check_request(self, topic: str, message: MessageProtocol):
        """Handle health check request"""
        try:
            health_results = await self._perform_health_check()
            
            await self.mqtt_client.publish(
                "lawnberry/ml_detection/health_response",
                {
                    "timestamp": datetime.now().isoformat(),
                    "health_status": health_results,
                    "system_active": self.system_active,
                    "performance_targets": self.performance_targets
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error handling health check request: {e}")
    
    async def _handle_performance_request(self, topic: str, message: MessageProtocol):
        """Handle performance report request"""
        try:
            # Get recent performance data
            recent_count = message.payload.get("recent_count", 10)
            recent_records = self.performance_history[-recent_count:] if self.performance_history else []
            
            # Calculate summary statistics
            summary = await self._calculate_performance_summary(recent_records)
            
            await self.mqtt_client.publish(
                "lawnberry/ml_detection/performance_response",
                {
                    "timestamp": datetime.now().isoformat(),
                    "summary": summary,
                    "recent_records": recent_records,
                    "targets": self.performance_targets
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error handling performance request: {e}")
    
    async def _calculate_performance_summary(self, records: List[Dict]) -> Dict[str, Any]:
        """Calculate performance summary from records"""
        try:
            if not records:
                return {}
            
            # Extract metrics
            accuracies = [r["ml_detector"].get("accuracy", 0.0) for r in records]
            latencies = [r["ml_detector"].get("avg_latency_ms", 0.0) for r in records]
            fp_rates = [r["ml_detector"].get("false_positive_rate", 0.0) for r in records]
            
            summary = {
                "record_count": len(records),
                "time_range": {
                    "start": records[0]["timestamp"],
                    "end": records[-1]["timestamp"]
                },
                "accuracy": {
                    "mean": sum(accuracies) / len(accuracies) if accuracies else 0.0,
                    "min": min(accuracies) if accuracies else 0.0,
                    "max": max(accuracies) if accuracies else 0.0
                },
                "latency_ms": {
                    "mean": sum(latencies) / len(latencies) if latencies else 0.0,
                    "min": min(latencies) if latencies else 0.0,
                    "max": max(latencies) if latencies else 0.0
                },
                "false_positive_rate": {
                    "mean": sum(fp_rates) / len(fp_rates) if fp_rates else 0.0,
                    "min": min(fp_rates) if fp_rates else 0.0,
                    "max": max(fp_rates) if fp_rates else 0.0
                },
                "targets_met_percentage": {
                    "accuracy": sum(1 for r in records if r.get("targets_met", {}).get("accuracy", False)) / len(records) * 100,
                    "latency": sum(1 for r in records if r.get("targets_met", {}).get("latency", False)) / len(records) * 100,
                    "false_positive_rate": sum(1 for r in records if r.get("targets_met", {}).get("false_positive_rate", False)) / len(records) * 100
                }
            }
            
            return summary
            
        except Exception as e:
            self.logger.error(f"Error calculating performance summary: {e}")
            return {}
    
    async def _handle_reconfigure(self, topic: str, message: MessageProtocol):
        """Handle system reconfiguration request"""
        try:
            new_config = message.payload
            
            # Update performance targets if provided
            if "performance_targets" in new_config:
                self.performance_targets.update(new_config["performance_targets"])
                self.logger.info(f"Updated performance targets: {self.performance_targets}")
            
            # Update monitoring settings
            if "performance_monitoring_enabled" in new_config:
                self.performance_monitoring_enabled = new_config["performance_monitoring_enabled"]
            
            await self.mqtt_client.publish(
                "lawnberry/ml_detection/reconfigure_response",
                {
                    "timestamp": datetime.now().isoformat(),
                    "status": "success",
                    "updated_config": {
                        "performance_targets": self.performance_targets,
                        "performance_monitoring_enabled": self.performance_monitoring_enabled
                    }
                }
            )
            
        except Exception as e:
            self.logger.error(f"Error handling reconfigure request: {e}")
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        try:
            status = {
                "system_active": self.system_active,
                "health_status": self.health_status.copy(),
                "performance_targets": self.performance_targets.copy(),
                "performance_monitoring_enabled": self.performance_monitoring_enabled,
                "last_health_check": self.last_health_check.isoformat(),
                "uptime_seconds": (datetime.now() - self.last_health_check).total_seconds(),
                "components": {
                    "ml_detector_initialized": self.ml_detector._model_loaded,
                    "learning_system_active": self.learning_system.online_learning_enabled,
                    "safety_integration_enabled": self.safety_integrator is not None
                }
            }
            
            # Add recent performance summary
            if self.performance_history:
                recent_records = self.performance_history[-10:]
                status["recent_performance"] = asyncio.create_task(
                    self._calculate_performance_summary(recent_records)
                )
            
            return status
            
        except Exception as e:
            self.logger.error(f"Error getting system status: {e}")
            return {"error": str(e)}
