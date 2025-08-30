"""
Emergency Controller - Provides immediate emergency response and software-based emergency controls
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from ..communication import MQTTClient, MessageProtocol, SensorData

logger = logging.getLogger(__name__)


@dataclass
class EmergencyAction:
    """Emergency action definition"""
    action_id: str
    action_type: str  # STOP_MOTORS, DISABLE_BLADE, ALERT, SAFE_POSITION, SHUTDOWN
    priority: int     # 1=highest, 10=lowest
    timeout_ms: int   # Maximum time to execute
    description: str
    mqtt_topic: str
    mqtt_payload: Dict[str, Any]


class EmergencyController:
    """
    Emergency controller providing immediate response to critical safety conditions
    Implements software-based emergency controls without requiring physical hardware
    """
    
    def __init__(self, mqtt_client: MQTTClient, config):
        self.mqtt_client = mqtt_client
        self.config = config
        
        # Emergency response state
        self._emergency_active = False
        self._emergency_reason = ""
        self._emergency_timestamp: Optional[datetime] = None
        self._emergency_acknowledged = False
        
        # Emergency actions configuration
        self._emergency_actions = self._initialize_emergency_actions()
        
        # Performance tracking
        self._last_emergency_response_time = 0.0
        self._emergency_count = 0
        self._failed_emergency_responses = 0
        
        # Control state
        self._motors_stopped = False
        self._blade_disabled = False
        self._system_shutdown_requested = False
        
        # Tasks
        self._emergency_task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._running = False
        # Heartbeat tracking (used by watchdog)
        self._last_heartbeat_time: datetime = datetime.now()
        
    async def start(self):
        """Start the emergency controller"""
        logger.info("Starting emergency controller")
        self._running = True
        
        # Subscribe to emergency topics
        await self._subscribe_to_emergency_topics()
        
        # Start watchdog and monitoring tasks
        self._emergency_task = asyncio.create_task(self._emergency_monitoring_loop())
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        
        logger.info("Emergency controller started")
    
    async def stop(self):
        """Stop the emergency controller"""
        logger.info("Stopping emergency controller")
        self._running = False
        
        if self._emergency_task:
            self._emergency_task.cancel()
            try:
                await self._emergency_task
            except asyncio.CancelledError:
                pass
        
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
    
    def _initialize_emergency_actions(self) -> List[EmergencyAction]:
        """Initialize emergency action definitions"""
        return [
            EmergencyAction(
                action_id="stop_motors",
                action_type="STOP_MOTORS",
                priority=1,
                timeout_ms=50,
                description="Stop all motor movement immediately",
                mqtt_topic="lawnberry/motors/emergency_stop",
                mqtt_payload={"command": "emergency_stop", "immediate": True}
            ),
            EmergencyAction(
                action_id="disable_blade",
                action_type="DISABLE_BLADE",
                priority=1,
                timeout_ms=50,
                description="Disable cutting blade immediately",
                mqtt_topic="lawnberry/blade/emergency_disable",
                mqtt_payload={"command": "disable", "immediate": True}
            ),
            EmergencyAction(
                action_id="alert_all_systems",
                action_type="ALERT",
                priority=2,
                timeout_ms=100,
                description="Alert all systems of emergency",
                mqtt_topic="lawnberry/system/emergency_alert",
                mqtt_payload={"alert_level": "CRITICAL", "immediate_response_required": True}
            ),
            EmergencyAction(
                action_id="safe_position",
                action_type="SAFE_POSITION",
                priority=3,
                timeout_ms=200,
                description="Move to safe position if possible",
                mqtt_topic="lawnberry/navigation/safe_position",
                mqtt_payload={"command": "emergency_safe_position"}
            ),
            EmergencyAction(
                action_id="system_shutdown",
                action_type="SHUTDOWN",
                priority=10,
                timeout_ms=5000,
                description="Initiate safe system shutdown",
                mqtt_topic="lawnberry/system/shutdown",
                mqtt_payload={"command": "emergency_shutdown", "grace_period_s": 30}
            )
        ]
    
    async def _subscribe_to_emergency_topics(self):
        """Subscribe to emergency-related MQTT topics using standardized API"""
        topics = [
            ("lawnberry/emergency/acknowledge", self._handle_emergency_acknowledge),
            ("lawnberry/emergency/reset", self._handle_emergency_reset),
            ("lawnberry/motors/status", self._handle_motor_status),
            ("lawnberry/blade/status", self._handle_blade_status),
            ("lawnberry/system/heartbeat", self._handle_system_heartbeat)
        ]

        for topic, handler in topics:
            await self.mqtt_client.subscribe(topic)
            self.mqtt_client.add_message_handler(topic, handler)
    
    async def execute_emergency_stop(self, reason: str = "Emergency stop requested") -> bool:
        """Execute immediate emergency stop sequence"""
        start_time = datetime.now()
        
        try:
            logger.critical(f"EXECUTING EMERGENCY STOP: {reason}")
            
            # Set emergency state
            self._emergency_active = True
            self._emergency_reason = reason
            self._emergency_timestamp = start_time
            self._emergency_acknowledged = False
            self._emergency_count += 1
            
            # Execute emergency actions in priority order
            success = await self._execute_emergency_actions(reason)
            
            # Calculate response time
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            self._last_emergency_response_time = response_time
            
            if success:
                logger.critical(f"Emergency stop completed successfully in {response_time:.1f}ms")
            else:
                logger.error(f"Emergency stop had failures, completed in {response_time:.1f}ms")
                self._failed_emergency_responses += 1
            
            # Publish emergency status
            await self._publish_emergency_status()
            
            return success and response_time <= self.config.emergency_response_time_ms
            
        except Exception as e:
            logger.error(f"Critical error in emergency stop execution: {e}")
            self._failed_emergency_responses += 1
            return False
    
    async def _execute_emergency_actions(self, reason: str) -> bool:
        """Execute all emergency actions in priority order"""
        all_success = True
        
        # Sort actions by priority
        sorted_actions = sorted(self._emergency_actions, key=lambda a: a.priority)
        
        # Execute high priority actions immediately and concurrently
        immediate_actions = [a for a in sorted_actions if a.priority <= 2]
        lower_priority_actions = [a for a in sorted_actions if a.priority > 2]
        
        # Execute immediate actions concurrently for fastest response
        if immediate_actions:
            immediate_tasks = [
                self._execute_single_emergency_action(action, reason)
                for action in immediate_actions
            ]
            
            immediate_results = await asyncio.gather(*immediate_tasks, return_exceptions=True)
            
            # Check immediate action results
            for i, result in enumerate(immediate_results):
                if isinstance(result, Exception):
                    logger.error(f"Emergency action {immediate_actions[i].action_id} failed: {result}")
                    all_success = False
                elif not result:
                    all_success = False
        
        # Execute lower priority actions sequentially
        for action in lower_priority_actions:
            try:
                success = await self._execute_single_emergency_action(action, reason)
                if not success:
                    all_success = False
            except Exception as e:
                logger.error(f"Emergency action {action.action_id} failed: {e}")
                all_success = False
        
        return all_success
    
    async def _execute_single_emergency_action(self, action: EmergencyAction, reason: str) -> bool:
        """Execute a single emergency action with timeout"""
        try:
            # Prepare action payload
            payload = action.mqtt_payload.copy()
            payload.update({
                "emergency_reason": reason,
                "timestamp": datetime.now().isoformat(),
                "action_id": action.action_id
            })
            
            # Create message
            message = SensorData.create(
                sender="emergency_controller",
                sensor_type="emergency_action",
                data=payload
            )
            
            # Execute with timeout
            success = await asyncio.wait_for(
                self.mqtt_client.publish(action.mqtt_topic, message, qos=2),
                timeout=action.timeout_ms / 1000.0
            )
            
            if success:
                logger.info(f"Emergency action {action.action_id} executed successfully")
                
                # Update internal state based on action type
                if action.action_type == "STOP_MOTORS":
                    self._motors_stopped = True
                elif action.action_type == "DISABLE_BLADE":
                    self._blade_disabled = True
                elif action.action_type == "SHUTDOWN":
                    self._system_shutdown_requested = True
            else:
                logger.error(f"Emergency action {action.action_id} failed to publish")
            
            return success
            
        except asyncio.TimeoutError:
            logger.error(f"Emergency action {action.action_id} timed out after {action.timeout_ms}ms")
            return False
        except Exception as e:
            logger.error(f"Emergency action {action.action_id} failed: {e}")
            return False
    
    async def _emergency_monitoring_loop(self):
        """Monitor emergency state and ensure continued safety"""
        while self._running:
            try:
                if self._emergency_active and not self._emergency_acknowledged:
                    # Continuously enforce emergency state
                    await self._enforce_emergency_state()
                    
                    # Check for emergency timeout (auto-reset after 5 minutes if not acknowledged)
                    if (self._emergency_timestamp and 
                        (datetime.now() - self._emergency_timestamp).total_seconds() > 300):
                        logger.warning("Emergency state auto-timeout after 5 minutes")
                        await self._auto_reset_emergency()
                
                await asyncio.sleep(1.0)  # Check every second
                
            except Exception as e:
                logger.error(f"Error in emergency monitoring loop: {e}")
                await asyncio.sleep(1.0)
    
    async def _watchdog_loop(self):
        """Watchdog to ensure system responsiveness"""
        # Use instance heartbeat timestamp updated by _handle_system_heartbeat
        watchdog_timeout = float(getattr(self.config, 'heartbeat_timeout_s', 10.0))
        
        while self._running:
            try:
                # Check for system heartbeat timeout
                if (datetime.now() - self._last_heartbeat_time).total_seconds() > watchdog_timeout:
                    logger.error("System heartbeat timeout detected")
                    await self.execute_emergency_stop("System heartbeat timeout")
                    self._last_heartbeat_time = datetime.now()  # Reset to avoid spam
                
                await asyncio.sleep(1.0)
                
            except Exception as e:
                logger.error(f"Error in watchdog loop: {e}")
                await asyncio.sleep(1.0)
    
    async def _enforce_emergency_state(self):
        """Continuously enforce emergency state until acknowledged"""
        try:
            # Re-send critical stop commands if not confirmed
            if not self._motors_stopped:
                await self.mqtt_client.publish(
                    "lawnberry/motors/emergency_stop",
                    SensorData.create(
                        sender="emergency_controller",
                        sensor_type="emergency_enforcement",
                        data={"command": "emergency_stop", "enforce": True}
                    ),
                    qos=2
                )
            
            if not self._blade_disabled:
                await self.mqtt_client.publish(
                    "lawnberry/blade/emergency_disable",
                    SensorData.create(
                        sender="emergency_controller",
                        sensor_type="emergency_enforcement",
                        data={"command": "disable", "enforce": True}
                    ),
                    qos=2
                )
                
        except Exception as e:
            logger.error(f"Error enforcing emergency state: {e}")
    
    async def acknowledge_emergency(self, acknowledged_by: str = "user") -> bool:
        """Acknowledge emergency and allow system recovery"""
        if not self._emergency_active:
            return False
        
        try:
            logger.info(f"Emergency acknowledged by {acknowledged_by}")
            self._emergency_acknowledged = True
            
            # Publish acknowledgment
            await self.mqtt_client.publish(
                "lawnberry/emergency/status",
                SensorData.create(
                    sender="emergency_controller",
                    sensor_type="emergency_acknowledgment",
                    data={
                        "acknowledged": True,
                        "acknowledged_by": acknowledged_by,
                        "timestamp": datetime.now().isoformat(),
                        "emergency_reason": self._emergency_reason
                    }
                ),
                qos=2
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error acknowledging emergency: {e}")
            return False
    
    async def reset_emergency(self, reset_by: str = "user") -> bool:
        """Reset emergency state and allow normal operation"""
        if not self._emergency_active or not self._emergency_acknowledged:
            return False
        
        try:
            logger.info(f"Emergency reset by {reset_by}")
            
            # Reset emergency state
            self._emergency_active = False
            self._emergency_reason = ""
            self._emergency_timestamp = None
            self._emergency_acknowledged = False
            
            # Reset control states
            self._motors_stopped = False
            self._blade_disabled = False
            self._system_shutdown_requested = False
            
            # Publish reset status
            await self.mqtt_client.publish(
                "lawnberry/emergency/status",
                SensorData.create(
                    sender="emergency_controller",
                    sensor_type="emergency_reset",
                    data={
                        "emergency_active": False,
                        "reset_by": reset_by,
                        "timestamp": datetime.now().isoformat()
                    }
                ),
                qos=2
            )
            
            logger.info("Emergency state reset successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting emergency: {e}")
            return False

    async def _publish_emergency_status(self):
        """Publish current emergency status for dashboards and other services."""
        try:
            status_payload = {
                'timestamp': datetime.now().isoformat(),
                'emergency_active': self._emergency_active,
                'emergency_reason': self._emergency_reason,
                'emergency_timestamp': self._emergency_timestamp.isoformat() if self._emergency_timestamp else None,
                'acknowledged': self._emergency_acknowledged,
                'motors_stopped': self._motors_stopped,
                'blade_disabled': self._blade_disabled,
                'system_shutdown_requested': self._system_shutdown_requested,
                'last_response_time_ms': self._last_emergency_response_time,
                'emergency_count': self._emergency_count,
                'failed_responses': self._failed_emergency_responses,
            }

            message = SensorData.create(
                sender="emergency_controller",
                sensor_type="emergency_status",
                data=status_payload,
            )

            # Publish to a status topic and to safety alerts for visibility
            await self.mqtt_client.publish("lawnberry/emergency/status", message)
            if self._emergency_active:
                await self.mqtt_client.publish("lawnberry/safety/alerts/emergency", message)
        except Exception as e:
            logger.error(f"Error publishing emergency status: {e}")
    
    async def _handle_emergency_acknowledge(self, topic: str, message: MessageProtocol):
        """Handle emergency acknowledgment message"""
        try:
            data = message.payload
            acknowledged_by = data.get('acknowledged_by', 'unknown')
            await self.acknowledge_emergency(acknowledged_by)
        except Exception as e:
            logger.error(f"Error handling emergency acknowledge: {e}")
    
    async def _handle_emergency_reset(self, topic: str, message: MessageProtocol):
        """Handle emergency reset message"""
        try:
            data = message.payload
            reset_by = data.get('reset_by', 'unknown')
            await self.reset_emergency(reset_by)
        except Exception as e:
            logger.error(f"Error handling emergency reset: {e}")
    
    async def _handle_system_heartbeat(self, topic: str, message: MessageProtocol):
        """Handle system heartbeat to reset watchdog"""
        try:
            # Heartbeat received, system is responsive
            self._last_heartbeat_time = datetime.now()
            logger.debug("System heartbeat received; watchdog timer reset")
        except Exception as e:
            logger.error(f"Error handling system heartbeat: {e}")

    async def _handle_motor_status(self, topic: str, message: MessageProtocol):
        """Handle motor status updates to confirm emergency enforcement"""
        try:
            data = message.payload if hasattr(message, 'payload') else {}
            # Accept multiple schemas for robustness
            # Prefer explicit stopped/enabled flags; fall back to PWM neutral or state strings
            stopped = (
                bool(data.get('stopped')) or
                (str(data.get('state', '')).lower() in {'stopped', 'disabled', 'idle'}) or
                (isinstance(data.get('throttle_pwm'), (int, float)) and 1475 <= float(data['throttle_pwm']) <= 1525)
            )
            if stopped:
                if not self._motors_stopped:
                    logger.info("Motor status indicates motors are stopped")
                self._motors_stopped = True
        except Exception as e:
            logger.error(f"Error handling motor status: {e}")

    async def _handle_blade_status(self, topic: str, message: MessageProtocol):
        """Handle blade status updates to confirm blade is disabled"""
        try:
            data = message.payload if hasattr(message, 'payload') else {}
            # Consider blade_enabled False, or state 'disabled' as confirmation
            disabled = (
                (data.get('blade_enabled') is False) or
                (str(data.get('state', '')).lower() in {'disabled', 'stopped', 'off'})
            )
            if disabled:
                if not self._blade_disabled:
                    logger.info("Blade status indicates blade is disabled")
                self._blade_disabled = True
        except Exception as e:
            logger.error(f"Error handling blade status: {e}")
    
    def get_current_status(self) -> Dict[str, Any]:
        """Get current emergency controller status"""
        return {
            'emergency_active': self._emergency_active,
            'emergency_reason': self._emergency_reason,
            'emergency_timestamp': self._emergency_timestamp.isoformat() if self._emergency_timestamp else None,
            'emergency_acknowledged': self._emergency_acknowledged,
            'motors_stopped': self._motors_stopped,
            'blade_disabled': self._blade_disabled,
            'system_shutdown_requested': self._system_shutdown_requested,
            'last_response_time_ms': self._last_emergency_response_time,
            'emergency_count': self._emergency_count,
            'failed_responses': self._failed_emergency_responses
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get emergency controller performance metrics"""
        return {
            'total_emergencies': self._emergency_count,
            'failed_responses': self._failed_emergency_responses,
            'success_rate': (self._emergency_count - self._failed_emergency_responses) / max(1, self._emergency_count),
            'last_response_time_ms': self._last_emergency_response_time,
            'target_response_time_ms': self.config.emergency_response_time_ms,
            'current_emergency_active': self._emergency_active
        }
