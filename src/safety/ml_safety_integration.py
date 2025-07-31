"""
Enhanced safety system integration with ML obstacle detection
Provides graduated response system and seamless integration
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple, Set
from enum import Enum
from dataclasses import dataclass

from ..vision.ml_obstacle_detector import MLObstacleDetector, MLDetectionResult
from ..vision.data_structures import SafetyLevel
from ..communication import MQTTClient, MessageProtocol
from .emergency_response import EmergencyResponseSystem
from .safety_monitor import SafetyMonitor


class ResponseLevel(Enum):
    """Graduated response levels"""
    CONTINUE = "continue"
    SLOW_DOWN = "slow_down"
    STOP_AND_ASSESS = "stop_and_assess"
    EMERGENCY_STOP = "emergency_stop"
    RETREAT = "retreat"


@dataclass
class SafetyResponse:
    """Safety response configuration"""
    level: ResponseLevel
    action_timeout_ms: int
    required_clearance_distance: float
    retry_attempts: int
    escalation_time_s: int


class MLSafetyIntegrator:
    """Integrates ML obstacle detection with safety system"""
    
    def __init__(self, mqtt_client: MQTTClient, 
                 ml_detector: MLObstacleDetector,
                 emergency_system: EmergencyResponseSystem,
                 safety_monitor: SafetyMonitor):
        self.logger = logging.getLogger(__name__)
        self.mqtt_client = mqtt_client
        self.ml_detector = ml_detector
        self.emergency_system = emergency_system
        self.safety_monitor = safety_monitor
        
        # Response configuration
        self.response_matrix = {
            # Object type -> Safety level -> Response configuration
            "person": {
                SafetyLevel.CRITICAL: SafetyResponse(
                    ResponseLevel.EMERGENCY_STOP, 50, 4.5, 0, 0
                ),
                SafetyLevel.HIGH: SafetyResponse(
                    ResponseLevel.EMERGENCY_STOP, 100, 3.0, 0, 2
                ),
                SafetyLevel.MEDIUM: SafetyResponse(
                    ResponseLevel.STOP_AND_ASSESS, 200, 2.0, 3, 5
                )
            },
            "child": {
                SafetyLevel.CRITICAL: SafetyResponse(
                    ResponseLevel.EMERGENCY_STOP, 50, 5.0, 0, 0
                ),
                SafetyLevel.HIGH: SafetyResponse(
                    ResponseLevel.EMERGENCY_STOP, 50, 4.0, 0, 0
                ),
                SafetyLevel.MEDIUM: SafetyResponse(
                    ResponseLevel.STOP_AND_ASSESS, 100, 3.0, 2, 3
                )
            },
            "pet": {
                SafetyLevel.CRITICAL: SafetyResponse(
                    ResponseLevel.EMERGENCY_STOP, 100, 2.0, 0, 1
                ),
                SafetyLevel.HIGH: SafetyResponse(
                    ResponseLevel.STOP_AND_ASSESS, 200, 1.5, 2, 3
                ),
                SafetyLevel.MEDIUM: SafetyResponse(
                    ResponseLevel.SLOW_DOWN, 500, 1.0, 3, 5
                )
            },
            "dog": {
                SafetyLevel.CRITICAL: SafetyResponse(
                    ResponseLevel.EMERGENCY_STOP, 100, 2.5, 0, 1
                ),
                SafetyLevel.HIGH: SafetyResponse(
                    ResponseLevel.STOP_AND_ASSESS, 200, 2.0, 2, 3
                ),
                SafetyLevel.MEDIUM: SafetyResponse(
                    ResponseLevel.SLOW_DOWN, 500, 1.5, 3, 5
                )
            },
            "cat": {
                SafetyLevel.CRITICAL: SafetyResponse(
                    ResponseLevel.STOP_AND_ASSESS, 150, 1.5, 1, 2
                ),
                SafetyLevel.HIGH: SafetyResponse(
                    ResponseLevel.SLOW_DOWN, 300, 1.0, 2, 4
                ),
                SafetyLevel.MEDIUM: SafetyResponse(
                    ResponseLevel.SLOW_DOWN, 500, 0.8, 3, 6
                )
            },
            "toy": {
                SafetyLevel.CRITICAL: SafetyResponse(
                    ResponseLevel.STOP_AND_ASSESS, 200, 0.5, 2, 3
                ),
                SafetyLevel.HIGH: SafetyResponse(
                    ResponseLevel.SLOW_DOWN, 400, 0.3, 3, 5
                ),
                SafetyLevel.MEDIUM: SafetyResponse(
                    ResponseLevel.CONTINUE, 0, 0.2, 0, 0
                )
            },
            "moving_object": {
                SafetyLevel.CRITICAL: SafetyResponse(
                    ResponseLevel.EMERGENCY_STOP, 100, 1.0, 0, 1
                ),
                SafetyLevel.HIGH: SafetyResponse(
                    ResponseLevel.STOP_AND_ASSESS, 200, 0.8, 2, 3
                ),
                SafetyLevel.MEDIUM: SafetyResponse(
                    ResponseLevel.SLOW_DOWN, 300, 0.5, 3, 5
                )
            },
            "static_object": {
                SafetyLevel.CRITICAL: SafetyResponse(
                    ResponseLevel.STOP_AND_ASSESS, 300, 0.5, 3, 5
                ),
                SafetyLevel.HIGH: SafetyResponse(
                    ResponseLevel.SLOW_DOWN, 500, 0.3, 3, 8
                ),
                SafetyLevel.MEDIUM: SafetyResponse(
                    ResponseLevel.CONTINUE, 0, 0.2, 0, 0
                )
            },
            "unknown": {
                SafetyLevel.CRITICAL: SafetyResponse(
                    ResponseLevel.STOP_AND_ASSESS, 200, 1.0, 2, 3
                ),
                SafetyLevel.HIGH: SafetyResponse(
                    ResponseLevel.SLOW_DOWN, 400, 0.8, 3, 5
                ),
                SafetyLevel.MEDIUM: SafetyResponse(
                    ResponseLevel.SLOW_DOWN, 600, 0.5, 3, 8
                )
            }
        }
        
        # Current system state
        self.current_response_level = ResponseLevel.CONTINUE
        self.active_responses: Dict[str, Dict] = {}
        self.response_history: List[Dict] = []
        
        # Override mechanisms
        self.manual_override_active = False
        self.override_expiry: Optional[datetime] = None
        self.false_positive_suppressions: Set[str] = set()
        
        # Performance tracking
        self.response_times: List[float] = []
        self.false_positive_count = 0
        self.correct_response_count = 0
        
        # Integration tasks
        self._integration_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start(self):
        """Start the ML safety integration system"""
        try:
            self.logger.info("Starting ML safety integration system")
            
            # Register with ML detector
            self.ml_detector.register_safety_callback(self._handle_ml_detection)
            
            # Subscribe to MQTT topics
            await self._subscribe_to_topics()
            
            # Start integration loop
            self._running = True
            self._integration_task = asyncio.create_task(self._integration_loop())
            
            self.logger.info("ML safety integration system started")
            
        except Exception as e:
            self.logger.error(f"Error starting ML safety integration: {e}")
    
    async def stop(self):
        """Stop the ML safety integration system"""
        try:
            self.logger.info("Stopping ML safety integration system")
            
            self._running = False
            if self._integration_task:
                self._integration_task.cancel()
                try:
                    await self._integration_task
                except asyncio.CancelledError:
                    pass
            
            self.logger.info("ML safety integration system stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping ML safety integration: {e}")
    
    async def _subscribe_to_topics(self):
        """Subscribe to relevant MQTT topics"""
        try:
            await self.mqtt_client.subscribe(
                "lawnberry/safety/manual_override",
                self._handle_manual_override
            )
            
            await self.mqtt_client.subscribe(
                "lawnberry/safety/false_positive_report",
                self._handle_false_positive_report
            )
            
            await self.mqtt_client.subscribe(
                "lawnberry/navigation/position",
                self._handle_position_update
            )
            
        except Exception as e:
            self.logger.error(f"Error subscribing to topics: {e}")
    
    async def _integration_loop(self):
        """Main integration loop"""
        while self._running:
            try:
                # Check for expired overrides
                await self._check_override_expiry()
                
                # Update response status
                await self._update_response_status()
                
                # Clean up old responses
                await self._cleanup_old_responses()
                
                await asyncio.sleep(0.1)  # 10Hz update rate
                
            except Exception as e:
                self.logger.error(f"Error in integration loop: {e}")
                await asyncio.sleep(0.1)
    
    async def _handle_ml_detection(self, event_type: str, detections: List[MLDetectionResult]):
        """Handle ML detection events"""
        try:
            start_time = datetime.now()
            
            if event_type == "emergency_stop":
                await self._handle_emergency_detections(detections)
            else:
                await self._handle_regular_detections(detections)
            
            # Track response time
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            self.response_times.append(response_time)
            if len(self.response_times) > 100:
                self.response_times.pop(0)
            
        except Exception as e:
            self.logger.error(f"Error handling ML detection: {e}")
    
    async def _handle_emergency_detections(self, detections: List[MLDetectionResult]):
        """Handle emergency-level detections"""
        try:
            if self.manual_override_active:
                self.logger.warning("Emergency detection ignored due to manual override")
                return
            
            # Process each detection
            for detection in detections:
                response_config = self._get_response_config(detection)
                if response_config and response_config.level == ResponseLevel.EMERGENCY_STOP:
                    await self._execute_emergency_stop(detection, response_config)
                    
        except Exception as e:
            self.logger.error(f"Error handling emergency detections: {e}")
    
    async def _handle_regular_detections(self, detections: List[MLDetectionResult]):
        """Handle regular-level detections"""
        try:
            if self.manual_override_active:
                return
            
            # Group detections by response level
            response_groups = {}
            for detection in detections:
                if detection.object_id in self.false_positive_suppressions:
                    continue
                    
                response_config = self._get_response_config(detection)
                if response_config:
                    level = response_config.level
                    if level not in response_groups:
                        response_groups[level] = []
                    response_groups[level].append((detection, response_config))
            
            # Execute responses in priority order
            priority_order = [
                ResponseLevel.EMERGENCY_STOP,
                ResponseLevel.RETREAT,
                ResponseLevel.STOP_AND_ASSESS,
                ResponseLevel.SLOW_DOWN,
                ResponseLevel.CONTINUE
            ]
            
            for level in priority_order:
                if level in response_groups:
                    await self._execute_response_level(level, response_groups[level])
                    break  # Execute highest priority response only
                    
        except Exception as e:
            self.logger.error(f"Error handling regular detections: {e}")
    
    def _get_response_config(self, detection: MLDetectionResult) -> Optional[SafetyResponse]:
        """Get response configuration for a detection"""
        try:
            object_type = detection.object_type
            safety_level = detection.safety_level
            
            # Check if we have specific configuration for this object type
            if object_type in self.response_matrix:
                type_responses = self.response_matrix[object_type]
                if safety_level in type_responses:
                    return type_responses[safety_level]
            
            # Fall back to unknown object response
            if "unknown" in self.response_matrix:
                unknown_responses = self.response_matrix["unknown"]
                if safety_level in unknown_responses:
                    return unknown_responses[safety_level]
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting response config: {e}")
            return None
    
    async def _execute_emergency_stop(self, detection: MLDetectionResult, config: SafetyResponse):
        """Execute emergency stop response"""
        try:
            self.logger.critical(f"Executing emergency stop for {detection.object_type} at distance {detection.distance:.2f}m")
            
            # Trigger emergency response system
            await self.emergency_system.trigger_emergency_stop(
                reason=f"ML detection: {detection.object_type}",
                severity="critical",
                timeout_ms=config.action_timeout_ms
            )
            
            # Update system state
            self.current_response_level = ResponseLevel.EMERGENCY_STOP
            
            # Record response
            response_record = {
                "timestamp": datetime.now(),
                "detection_id": detection.object_id,
                "object_type": detection.object_type,
                "confidence": detection.confidence,
                "distance": detection.distance,
                "response_level": ResponseLevel.EMERGENCY_STOP,
                "response_time_ms": config.action_timeout_ms
            }
            self.response_history.append(response_record)
            
            # Publish safety alert
            await self._publish_safety_alert(detection, config, ResponseLevel.EMERGENCY_STOP)
            
            self.correct_response_count += 1
            
        except Exception as e:
            self.logger.error(f"Error executing emergency stop: {e}")
    
    async def _execute_response_level(self, level: ResponseLevel, 
                                    detections_and_configs: List[Tuple[MLDetectionResult, SafetyResponse]]):
        """Execute response for a specific level"""
        try:
            if not detections_and_configs:
                return
            
            # Get the most critical detection
            detection, config = max(detections_and_configs, 
                                  key=lambda x: (x[0].confidence, 1.0 / max(x[0].distance, 0.1)))
            
            self.logger.info(f"Executing {level.value} response for {detection.object_type}")
            
            if level == ResponseLevel.STOP_AND_ASSESS:
                await self._execute_stop_and_assess(detection, config)
            elif level == ResponseLevel.SLOW_DOWN:
                await self._execute_slow_down(detection, config)
            elif level == ResponseLevel.RETREAT:
                await self._execute_retreat(detection, config)
            
            # Update current response level
            if self._response_priority(level) > self._response_priority(self.current_response_level):
                self.current_response_level = level
            
        except Exception as e:
            self.logger.error(f"Error executing response level {level}: {e}")
    
    def _response_priority(self, level: ResponseLevel) -> int:
        """Get numerical priority for response level"""
        priorities = {
            ResponseLevel.CONTINUE: 0,
            ResponseLevel.SLOW_DOWN: 1,
            ResponseLevel.STOP_AND_ASSESS: 2,
            ResponseLevel.RETREAT: 3,
            ResponseLevel.EMERGENCY_STOP: 4
        }
        return priorities.get(level, 0)
    
    async def _execute_stop_and_assess(self, detection: MLDetectionResult, config: SafetyResponse):
        """Execute stop and assess response"""
        try:
            # Send stop command
            await self.mqtt_client.publish(
                "lawnberry/navigation/stop",
                {
                    "reason": f"ML detection: {detection.object_type}",
                    "timeout_ms": config.action_timeout_ms,
                    "clearance_distance": config.required_clearance_distance
                }
            )
            
            # Record active response
            self.active_responses[detection.object_id] = {
                "response_level": ResponseLevel.STOP_AND_ASSESS,
                "start_time": datetime.now(),
                "config": config,
                "detection": detection,
                "retry_count": 0
            }
            
            # Publish alert
            await self._publish_safety_alert(detection, config, ResponseLevel.STOP_AND_ASSESS)
            
            self.correct_response_count += 1
            
        except Exception as e:
            self.logger.error(f"Error executing stop and assess: {e}")
    
    async def _execute_slow_down(self, detection: MLDetectionResult, config: SafetyResponse):
        """Execute slow down response"""
        try:
            # Calculate safe speed based on distance
            safe_speed = max(0.1, min(0.5, detection.distance / 2.0))
            
            # Send slow down command
            await self.mqtt_client.publish(
                "lawnberry/navigation/set_speed",
                {
                    "speed": safe_speed,
                    "reason": f"ML detection: {detection.object_type}",
                    "clearance_distance": config.required_clearance_distance
                }
            )
            
            # Record active response
            self.active_responses[detection.object_id] = {
                "response_level": ResponseLevel.SLOW_DOWN,
                "start_time": datetime.now(),
                "config": config,
                "detection": detection,
                "retry_count": 0
            }
            
            # Publish alert
            await self._publish_safety_alert(detection, config, ResponseLevel.SLOW_DOWN)
            
            self.correct_response_count += 1
            
        except Exception as e:
            self.logger.error(f"Error executing slow down: {e}")
    
    async def _execute_retreat(self, detection: MLDetectionResult, config: SafetyResponse):
        """Execute retreat response"""
        try:
            # Calculate retreat direction (opposite to detection)
            retreat_distance = config.required_clearance_distance + 1.0
            
            # Send retreat command
            await self.mqtt_client.publish(
                "lawnberry/navigation/retreat",
                {
                    "distance": retreat_distance,
                    "reason": f"ML detection: {detection.object_type}",
                    "timeout_ms": config.action_timeout_ms
                }
            )
            
            # Record active response
            self.active_responses[detection.object_id] = {
                "response_level": ResponseLevel.RETREAT,
                "start_time": datetime.now(),
                "config": config,
                "detection": detection,
                "retry_count": 0
            }
            
            # Publish alert
            await self._publish_safety_alert(detection, config, ResponseLevel.RETREAT)
            
            self.correct_response_count += 1
            
        except Exception as e:
            self.logger.error(f"Error executing retreat: {e}")
    
    async def _publish_safety_alert(self, detection: MLDetectionResult, 
                                  config: SafetyResponse, response_level: ResponseLevel):
        """Publish safety alert"""
        try:
            alert_data = {
                "timestamp": datetime.now().isoformat(),
                "detection_id": detection.object_id,
                "object_type": detection.object_type,
                "confidence": detection.confidence,
                "distance": detection.distance,
                "safety_level": detection.safety_level.value,
                "response_level": response_level.value,
                "clearance_distance": config.required_clearance_distance,
                "motion_vector": detection.motion_vector,
                "trajectory_prediction": detection.trajectory_prediction
            }
            
            await self.mqtt_client.publish(
                "lawnberry/safety/ml_alert",
                alert_data
            )
            
        except Exception as e:
            self.logger.error(f"Error publishing safety alert: {e}")
    
    async def _handle_manual_override(self, topic: str, message: MessageProtocol):
        """Handle manual override commands"""
        try:
            payload = message.payload
            override_type = payload.get("type")
            duration_seconds = payload.get("duration_seconds", 300)  # 5 min default
            
            if override_type == "enable":
                self.manual_override_active = True
                self.override_expiry = datetime.now() + timedelta(seconds=duration_seconds)
                self.logger.warning(f"Manual override enabled for {duration_seconds} seconds")
                
                # Clear active responses
                self.active_responses.clear()
                self.current_response_level = ResponseLevel.CONTINUE
                
            elif override_type == "disable":
                self.manual_override_active = False
                self.override_expiry = None
                self.logger.info("Manual override disabled")
                
        except Exception as e:
            self.logger.error(f"Error handling manual override: {e}")
    
    async def _handle_false_positive_report(self, topic: str, message: MessageProtocol):
        """Handle false positive reports"""
        try:
            payload = message.payload
            detection_id = payload.get("detection_id")
            object_type = payload.get("object_type")
            
            if detection_id:
                self.false_positive_suppressions.add(detection_id)
                self.false_positive_count += 1
                
                # Remove from active responses
                if detection_id in self.active_responses:
                    del self.active_responses[detection_id]
                
                self.logger.info(f"False positive reported for {object_type} (ID: {detection_id})")
                
                # TODO: Feed back to learning system
                
        except Exception as e:
            self.logger.error(f"Error handling false positive report: {e}")
    
    async def _handle_position_update(self, topic: str, message: MessageProtocol):
        """Handle robot position updates"""
        try:
            # Update active responses based on current position
            current_position = message.payload
            
            for detection_id, response_data in list(self.active_responses.items()):
                detection = response_data["detection"]
                config = response_data["config"]
                
                # Check if we're now at safe distance
                # (simplified - would need proper distance calculation)
                if self._is_safe_distance_achieved(current_position, detection, config):
                    await self._clear_response(detection_id)
                    
        except Exception as e:
            self.logger.error(f"Error handling position update: {e}")
    
    def _is_safe_distance_achieved(self, position: Dict, detection: MLDetectionResult, 
                                 config: SafetyResponse) -> bool:
        """Check if safe distance has been achieved"""
        try:
            # Simplified distance check - in real implementation would use proper geometry
            return detection.distance > config.required_clearance_distance * 1.2
        except Exception as e:
            self.logger.error(f"Error checking safe distance: {e}")
            return False
    
    async def _clear_response(self, detection_id: str):
        """Clear an active response"""
        try:
            if detection_id in self.active_responses:
                response_data = self.active_responses[detection_id]
                del self.active_responses[detection_id]
                
                self.logger.info(f"Cleared response for detection {detection_id}")
                
                # If no more active responses, return to normal operation
                if not self.active_responses:
                    self.current_response_level = ResponseLevel.CONTINUE
                    await self.mqtt_client.publish(
                        "lawnberry/navigation/resume",
                        {"reason": "All obstacles cleared"}
                    )
                    
        except Exception as e:
            self.logger.error(f"Error clearing response: {e}")
    
    async def _check_override_expiry(self):
        """Check if manual override has expired"""
        try:
            if (self.manual_override_active and self.override_expiry and 
                datetime.now() > self.override_expiry):
                self.manual_override_active = False
                self.override_expiry = None
                self.logger.info("Manual override expired")
                
        except Exception as e:
            self.logger.error(f"Error checking override expiry: {e}")
    
    async def _update_response_status(self):
        """Update status of active responses"""
        try:
            current_time = datetime.now()
            expired_responses = []
            
            for detection_id, response_data in self.active_responses.items():
                start_time = response_data["start_time"]
                config = response_data["config"]
                
                # Check if response has timed out
                elapsed_time = (current_time - start_time).total_seconds()
                if elapsed_time > config.escalation_time_s:
                    # Escalate or retry
                    if response_data["retry_count"] < config.retry_attempts:
                        response_data["retry_count"] += 1
                        response_data["start_time"] = current_time
                        await self._retry_response(detection_id, response_data)
                    else:
                        expired_responses.append(detection_id)
            
            # Clean up expired responses
            for detection_id in expired_responses:
                await self._escalate_response(detection_id)
                
        except Exception as e:
            self.logger.error(f"Error updating response status: {e}")
    
    async def _retry_response(self, detection_id: str, response_data: Dict):
        """Retry a response"""
        try:
            self.logger.info(f"Retrying response for detection {detection_id}")
            
            detection = response_data["detection"]
            config = response_data["config"]
            level = response_data["response_level"]
            
            # Re-execute the response
            if level == ResponseLevel.STOP_AND_ASSESS:
                await self._execute_stop_and_assess(detection, config)
            elif level == ResponseLevel.SLOW_DOWN:
                await self._execute_slow_down(detection, config)
            elif level == ResponseLevel.RETREAT:
                await self._execute_retreat(detection, config)
                
        except Exception as e:
            self.logger.error(f"Error retrying response: {e}")
    
    async def _escalate_response(self, detection_id: str):
        """Escalate a response that has failed"""
        try:
            if detection_id in self.active_responses:
                response_data = self.active_responses[detection_id]
                current_level = response_data["response_level"]
                
                self.logger.warning(f"Escalating response for detection {detection_id} from {current_level}")
                
                # Escalate to next level
                if current_level == ResponseLevel.SLOW_DOWN:
                    response_data["response_level"] = ResponseLevel.STOP_AND_ASSESS
                    await self._execute_stop_and_assess(
                        response_data["detection"], 
                        response_data["config"]
                    )
                elif current_level == ResponseLevel.STOP_AND_ASSESS:
                    response_data["response_level"] = ResponseLevel.EMERGENCY_STOP
                    await self._execute_emergency_stop(
                        response_data["detection"],
                        response_data["config"]
                    )
                else:
                    # Already at highest level, clear response
                    await self._clear_response(detection_id)
                    
        except Exception as e:
            self.logger.error(f"Error escalating response: {e}")
    
    async def _cleanup_old_responses(self):
        """Clean up old response history"""
        try:
            current_time = datetime.now()
            cutoff_time = current_time - timedelta(hours=1)
            
            # Keep only recent history
            self.response_history = [
                record for record in self.response_history
                if record["timestamp"] > cutoff_time
            ]
            
            # Clean up false positive suppressions after 24 hours
            cutoff_time_fp = current_time - timedelta(hours=24)
            # Would need timestamp tracking for suppressions in real implementation
            
        except Exception as e:
            self.logger.error(f"Error cleaning up old responses: {e}")
    
    def get_safety_stats(self) -> Dict[str, Any]:
        """Get safety integration statistics"""
        try:
            total_responses = self.correct_response_count + self.false_positive_count
            
            stats = {
                "current_response_level": self.current_response_level.value,
                "active_responses_count": len(self.active_responses),
                "manual_override_active": self.manual_override_active,
                "total_responses": total_responses,
                "correct_responses": self.correct_response_count,
                "false_positives": self.false_positive_count,
                "accuracy": (self.correct_response_count / total_responses) if total_responses > 0 else 0.0,
                "avg_response_time_ms": np.mean(self.response_times) if self.response_times else 0.0,
                "max_response_time_ms": max(self.response_times) if self.response_times else 0.0,
                "recent_responses": len([r for r in self.response_history 
                                       if (datetime.now() - r["timestamp"]).total_seconds() < 3600])
            }
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting safety stats: {e}")
            return {}
