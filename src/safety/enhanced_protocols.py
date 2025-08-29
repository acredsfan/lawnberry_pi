"""
Enhanced Safety Protocols
Implements graduated response systems, weather-based safety, and emergency features
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from ..communication import MQTTClient, MessageProtocol
from ..hardware.data_structures import GPSReading
from .access_control import SafetyAccessLevel, SafetyAccessController
from .sensor_fusion_safety import EnvironmentalConditions, FusedObstacleDetection

logger = logging.getLogger(__name__)


class ViolationType(Enum):
    """Types of safety violations"""
    BOUNDARY_BREACH = "boundary_breach"
    WEATHER_VIOLATION = "weather_violation"
    OBSTACLE_COLLISION = "obstacle_collision"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    MAINTENANCE_OVERRIDE = "maintenance_override"
    EMERGENCY_STOP_TRIGGERED = "emergency_stop_triggered"


class ResponseLevel(Enum):
    """Graduated response levels"""
    WARNING = "warning"
    CAUTION = "caution"
    IMMEDIATE_ACTION = "immediate_action"
    EMERGENCY_STOP = "emergency_stop"
    SYSTEM_SHUTDOWN = "system_shutdown"


class WeatherCondition(Enum):
    """Weather conditions affecting safety"""
    CLEAR = "clear"
    LIGHT_RAIN = "light_rain"
    HEAVY_RAIN = "heavy_rain"
    SNOW = "snow"
    HEAVY_SNOW = "heavy_snow"
    WIND = "wind"
    STORM = "storm"
    FOG = "fog"
    EXTREME_HEAT = "extreme_heat"
    EXTREME_COLD = "extreme_cold"


@dataclass
class SafetyEvent:
    """Safety event record"""
    event_id: str
    event_type: ViolationType
    timestamp: datetime
    severity: ResponseLevel
    location: Optional[Tuple[float, float]] = None
    description: str = ""
    user_involved: Optional[str] = None
    automated_response: List[str] = field(default_factory=list)
    manual_response: List[str] = field(default_factory=list)
    resolved: bool = False
    resolution_time: Optional[datetime] = None


@dataclass
class EmergencyContact:
    """Emergency contact information"""
    name: str
    role: str
    phone: str
    email: str
    priority: int  # 1 = highest priority
    notification_methods: List[str] = field(default_factory=lambda: ["email", "sms"])


@dataclass
class GeoFenceZone:
    """Geofence zone definition"""
    zone_id: str
    name: str
    center: Tuple[float, float]  # lat, lon
    radius: float  # meters
    zone_type: str  # "allowed", "restricted", "warning"
    access_levels: List[SafetyAccessLevel] = field(default_factory=list)
    active_times: List[Tuple[str, str]] = field(default_factory=list)  # ("09:00", "17:00")


class EnhancedSafetyProtocols:
    """Enhanced safety protocols with graduated response and emergency features"""
    
    def __init__(self, mqtt_client: MQTTClient, access_controller: SafetyAccessController, 
                 config: Dict[str, Any]):
        self.mqtt_client = mqtt_client
        self.access_controller = access_controller
        self.config = config
        
        # Safety event tracking
        self.safety_events: List[SafetyEvent] = []
        self.active_violations: Dict[str, SafetyEvent] = {}  # violation_id -> event
        
        # Emergency contacts
        self.emergency_contacts: List[EmergencyContact] = []
        self._load_emergency_contacts()
        
        # Geofencing
        self.geofence_zones: Dict[str, GeoFenceZone] = {}
        self.current_location: Optional[Tuple[float, float]] = None
        
        # Weather-based safety
        self.weather_safety_rules: Dict[WeatherCondition, Dict[str, Any]] = self._initialize_weather_rules()
        self.current_weather: Optional[WeatherCondition] = None
        self.weather_override_active: bool = False
        
        # Response protocols
        self.response_escalation_times = {
            ResponseLevel.WARNING: timedelta(minutes=5),
            ResponseLevel.CAUTION: timedelta(minutes=2),
            ResponseLevel.IMMEDIATE_ACTION: timedelta(seconds=30),
            ResponseLevel.EMERGENCY_STOP: timedelta(seconds=5),
            ResponseLevel.SYSTEM_SHUTDOWN: timedelta(seconds=1)
        }
        
        # Remote shutdown capability
        self.remote_shutdown_enabled = True
        self.remote_shutdown_tokens: Dict[str, Dict[str, Any]] = {}
        
        # Callbacks
        self.violation_callbacks: List[Callable] = []
        self.emergency_callbacks: List[Callable] = []
        
        # Tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._escalation_task: Optional[asyncio.Task] = None
        self._weather_task: Optional[asyncio.Task] = None
        self._running = False
    
    def _load_emergency_contacts(self):
        """Load emergency contacts from configuration"""
        contacts_config = self.config.get('emergency_contacts', [])
        for contact_data in contacts_config:
            contact = EmergencyContact(
                name=contact_data['name'],
                role=contact_data['role'],
                phone=contact_data['phone'],
                email=contact_data['email'],
                priority=contact_data.get('priority', 5),
                notification_methods=contact_data.get('notification_methods', ['email'])
            )
            self.emergency_contacts.append(contact)
        
        # Sort by priority
        self.emergency_contacts.sort(key=lambda x: x.priority)
    
    def _initialize_weather_rules(self) -> Dict[WeatherCondition, Dict[str, Any]]:
        """Initialize weather-based safety rules"""
        return {
            WeatherCondition.CLEAR: {
                "allowed_operations": ["mowing", "charging", "navigation"],
                "response_level": ResponseLevel.WARNING,
                "restrictions": []
            },
            WeatherCondition.LIGHT_RAIN: {
                "allowed_operations": ["charging", "navigation"],
                "response_level": ResponseLevel.CAUTION,
                "restrictions": ["no_mowing", "reduce_speed"]
            },
            WeatherCondition.HEAVY_RAIN: {
                "allowed_operations": ["charging"],
                "response_level": ResponseLevel.IMMEDIATE_ACTION,
                "restrictions": ["no_mowing", "no_navigation", "return_to_base"]
            },
            WeatherCondition.SNOW: {
                "allowed_operations": ["charging"],
                "response_level": ResponseLevel.IMMEDIATE_ACTION,
                "restrictions": ["no_mowing", "no_navigation", "return_to_base"]
            },
            WeatherCondition.HEAVY_SNOW: {
                "allowed_operations": [],
                "response_level": ResponseLevel.EMERGENCY_STOP,
                "restrictions": ["complete_shutdown", "emergency_shelter"]
            },
            WeatherCondition.WIND: {
                "allowed_operations": ["mowing", "charging", "navigation"],
                "response_level": ResponseLevel.CAUTION,
                "restrictions": ["reduce_speed", "extra_sensor_validation"]
            },
            WeatherCondition.STORM: {
                "allowed_operations": [],
                "response_level": ResponseLevel.EMERGENCY_STOP,
                "restrictions": ["complete_shutdown", "emergency_shelter"]
            },
            WeatherCondition.FOG: {
                "allowed_operations": ["charging"],
                "response_level": ResponseLevel.IMMEDIATE_ACTION,
                "restrictions": ["no_mowing", "no_navigation", "enhanced_sensors"]
            },
            WeatherCondition.EXTREME_HEAT: {
                "allowed_operations": ["charging"],
                "response_level": ResponseLevel.CAUTION,
                "restrictions": ["no_mowing", "thermal_protection", "reduce_activity"]
            },
            WeatherCondition.EXTREME_COLD: {
                "allowed_operations": ["charging"],
                "response_level": ResponseLevel.CAUTION,
                "restrictions": ["no_mowing", "battery_protection", "reduce_activity"]
            }
        }
    
    async def start(self):
        """Start enhanced safety protocols"""
        logger.info("Starting enhanced safety protocols")
        self._running = True
        
        # Subscribe to system events
        await self._subscribe_to_events()
        
        # Start monitoring tasks
        self._monitoring_task = asyncio.create_task(self._safety_monitoring_loop())
        self._escalation_task = asyncio.create_task(self._escalation_monitoring_loop())
        self._weather_task = asyncio.create_task(self._weather_monitoring_loop())
    
    async def stop(self):
        """Stop enhanced safety protocols"""
        logger.info("Stopping enhanced safety protocols")
        self._running = False
        
        for task in [self._monitoring_task, self._escalation_task, self._weather_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    
    async def _subscribe_to_events(self):
        """Subscribe to system events (standardized lawnberry/* topics)"""
        # GPS updates
        gps_topic = "lawnberry/sensors/gps/data"
        await self.mqtt_client.subscribe(gps_topic)
        self.mqtt_client.add_message_handler(gps_topic, lambda t, m: asyncio.create_task(self._wrapped_handler(self._handle_location_update, t, m)))

        # Environmental data (BME280 etc.)
        env_topic = "lawnberry/sensors/environmental/data"
        await self.mqtt_client.subscribe(env_topic)
        self.mqtt_client.add_message_handler(env_topic, lambda t, m: asyncio.create_task(self._wrapped_handler(self._handle_environmental_data, t, m)))

        # Safety violation notifications
        violation_topic = "lawnberry/safety/violation"
        await self.mqtt_client.subscribe(violation_topic)
        self.mqtt_client.add_message_handler(violation_topic, lambda t, m: asyncio.create_task(self._wrapped_handler(self._handle_safety_violation, t, m)))

        # System-wide emergency events
        emergency_topic = "lawnberry/safety/emergency"
        await self.mqtt_client.subscribe(emergency_topic)
        self.mqtt_client.add_message_handler(emergency_topic, lambda t, m: asyncio.create_task(self._wrapped_handler(self._handle_emergency_event, t, m)))

        # Remote shutdown requests
        remote_shutdown_topic = "lawnberry/system/remote_shutdown"
        await self.mqtt_client.subscribe(remote_shutdown_topic)
        self.mqtt_client.add_message_handler(remote_shutdown_topic, lambda t, m: asyncio.create_task(self._wrapped_handler(self._handle_remote_shutdown, t, m)))

    async def _wrapped_handler(self, handler: Callable, topic: str, message):
        """Normalize MQTT handler payloads to dict for internal handlers."""
        try:
            payload: Dict[str, Any]
            if hasattr(message, 'payload'):
                payload = message.payload  # MessageProtocol
            else:
                import json as _json
                payload = _json.loads(message) if isinstance(message, str) else {}
            await handler(payload)
        except Exception as e:
            logger.error(f"EnhancedProtocols handler error for {topic}: {e}")
    
    async def _handle_location_update(self, data: Dict[str, Any]):
        """Handle GPS location updates for geofencing"""
        lat = data.get('latitude')
        lon = data.get('longitude')
        if lat is not None and lon is not None:
            self.current_location = (lat, lon)
            await self._check_geofence_violations()
    
    async def _handle_environmental_data(self, data: Dict[str, Any]):
        """Handle environmental data for weather-based safety"""
        weather_condition = self._determine_weather_condition(data)
        if weather_condition != self.current_weather:
            self.current_weather = weather_condition
            await self._apply_weather_safety_rules()
    
    async def _handle_safety_violation(self, data: Dict[str, Any]):
        """Handle safety violation events"""
        violation_type = ViolationType(data.get('type', 'boundary_breach'))
        await self._record_safety_violation(violation_type, data)
    
    async def _handle_emergency_event(self, data: Dict[str, Any]):
        """Handle emergency events"""
        await self._trigger_emergency_response(data)
    
    async def _handle_remote_shutdown(self, data: Dict[str, Any]):
        """Handle remote shutdown requests"""
        if self.remote_shutdown_enabled:
            token = data.get('token')
            if await self._validate_shutdown_token(token):
                await self._execute_remote_shutdown(data)
    
    def _determine_weather_condition(self, env_data: Dict[str, Any]) -> WeatherCondition:
        """Determine weather condition from environmental data"""
        temp = env_data.get('temperature', 20.0)
        humidity = env_data.get('humidity', 50.0)
        wind_speed = env_data.get('wind_speed', 0.0)
        precipitation = env_data.get('precipitation', False)
        visibility = env_data.get('visibility', 1000.0)
        
        # Extreme temperatures
        if temp > 40.0:
            return WeatherCondition.EXTREME_HEAT
        elif temp < -5.0:
            return WeatherCondition.EXTREME_COLD
        
        # Precipitation
        if precipitation:
            if temp < 2.0:
                return WeatherCondition.HEAVY_SNOW if humidity > 80 else WeatherCondition.SNOW
            else:
                return WeatherCondition.HEAVY_RAIN if humidity > 90 else WeatherCondition.LIGHT_RAIN
        
        # Visibility
        if visibility < 100:
            return WeatherCondition.FOG
        
        # Wind
        if wind_speed > 15.0:
            return WeatherCondition.STORM
        elif wind_speed > 8.0:
            return WeatherCondition.WIND
        
        return WeatherCondition.CLEAR
    
    async def _check_geofence_violations(self):
        """Check for geofence violations"""
        if not self.current_location:
            return
        
        for zone_id, zone in self.geofence_zones.items():
            distance = self._calculate_distance(self.current_location, zone.center)
            
            if zone.zone_type == "restricted" and distance <= zone.radius:
                await self._handle_geofence_violation(zone, "entered_restricted_zone")
            elif zone.zone_type == "allowed" and distance > zone.radius:
                await self._handle_geofence_violation(zone, "left_allowed_zone")
            elif zone.zone_type == "warning" and distance <= zone.radius:
                await self._handle_geofence_violation(zone, "entered_warning_zone")
    
    def _calculate_distance(self, point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
        """Calculate distance between two GPS coordinates"""
        import math
        
        lat1, lon1 = math.radians(point1[0]), math.radians(point1[1])
        lat2, lon2 = math.radians(point2[0]), math.radians(point2[1])
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # Earth's radius in meters
        r = 6371000
        return c * r
    
    async def _handle_geofence_violation(self, zone: GeoFenceZone, violation_reason: str):
        """Handle geofence violation"""
        violation_data = {
            'type': ViolationType.BOUNDARY_BREACH.value,
            'zone_id': zone.zone_id,
            'zone_name': zone.name,
            'violation_reason': violation_reason,
            'location': self.current_location,
            'timestamp': datetime.now().isoformat()
        }
        
        await self._record_safety_violation(ViolationType.BOUNDARY_BREACH, violation_data)
    
    async def _apply_weather_safety_rules(self):
        """Apply weather-based safety rules"""
        if not self.current_weather:
            return
        
        rules = self.weather_safety_rules[self.current_weather]
        response_level = rules['response_level']
        restrictions = rules['restrictions']
        
        logger.info(f"Applying weather safety rules for {self.current_weather.value}: {restrictions}")
        
        # Apply restrictions
        for restriction in restrictions:
            await self._apply_safety_restriction(restriction, f"Weather condition: {self.current_weather.value}")
        
        # Trigger appropriate response
        if response_level in [ResponseLevel.EMERGENCY_STOP, ResponseLevel.SYSTEM_SHUTDOWN]:
            violation_data = {
                'type': ViolationType.WEATHER_VIOLATION.value,
                'weather_condition': self.current_weather.value,
                'restrictions': restrictions,
                'timestamp': datetime.now().isoformat()
            }
            await self._record_safety_violation(ViolationType.WEATHER_VIOLATION, violation_data)
    
    async def _apply_safety_restriction(self, restriction: str, reason: str):
        """Apply a specific safety restriction"""
        restriction_commands = {
            'no_mowing': {'command': 'STOP_MOWING', 'reason': reason},
            'no_navigation': {'command': 'STOP_NAVIGATION', 'reason': reason},
            'return_to_base': {'command': 'RETURN_TO_BASE', 'reason': reason},
            'complete_shutdown': {'command': 'EMERGENCY_SHUTDOWN', 'reason': reason},
            'reduce_speed': {'command': 'REDUCE_SPEED', 'factor': 0.5, 'reason': reason},
            'enhance_sensors': {'command': 'ENHANCE_SENSOR_MONITORING', 'reason': reason}
        }
        
        if restriction in restriction_commands:
            command_data = restriction_commands[restriction]
            await self.mqtt_client.publish("system/safety_command", command_data)
            logger.info(f"Applied safety restriction: {restriction} - {reason}")
    
    async def _record_safety_violation(self, violation_type: ViolationType, data: Dict[str, Any]):
        """Record a safety violation and trigger appropriate response"""
        event_id = f"{violation_type.value}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        # Determine severity based on violation type and context
        severity = self._determine_violation_severity(violation_type, data)
        
        event = SafetyEvent(
            event_id=event_id,
            event_type=violation_type,
            timestamp=datetime.now(),
            severity=severity,
            location=data.get('location'),
            description=self._generate_violation_description(violation_type, data),
            user_involved=data.get('user'),
            automated_response=[],
            manual_response=[]
        )
        
        self.safety_events.append(event)
        self.active_violations[event_id] = event
        
        # Trigger graduated response
        await self._trigger_graduated_response(event)
        
        # Notify callbacks
        for callback in self.violation_callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Error in violation callback: {e}")
        
        logger.warning(f"Safety violation recorded: {event.description}")
    
    def _determine_violation_severity(self, violation_type: ViolationType, data: Dict[str, Any]) -> ResponseLevel:
        """Determine the severity of a safety violation"""
        severity_mapping = {
            ViolationType.BOUNDARY_BREACH: ResponseLevel.IMMEDIATE_ACTION,
            ViolationType.WEATHER_VIOLATION: ResponseLevel.CAUTION,
            ViolationType.OBSTACLE_COLLISION: ResponseLevel.EMERGENCY_STOP,
            ViolationType.UNAUTHORIZED_ACCESS: ResponseLevel.WARNING,
            ViolationType.MAINTENANCE_OVERRIDE: ResponseLevel.CAUTION,
            ViolationType.EMERGENCY_STOP_TRIGGERED: ResponseLevel.EMERGENCY_STOP
        }
        
        base_severity = severity_mapping.get(violation_type, ResponseLevel.WARNING)
        
        # Escalate based on context
        if data.get('repeat_violation', False):
            severity_levels = [ResponseLevel.WARNING, ResponseLevel.CAUTION, ResponseLevel.IMMEDIATE_ACTION, ResponseLevel.EMERGENCY_STOP]
            current_index = severity_levels.index(base_severity)
            if current_index < len(severity_levels) - 1:
                base_severity = severity_levels[current_index + 1]
        
        return base_severity
    
    def _generate_violation_description(self, violation_type: ViolationType, data: Dict[str, Any]) -> str:
        """Generate a human-readable description of the violation"""
        descriptions = {
            ViolationType.BOUNDARY_BREACH: f"Boundary violation in zone {data.get('zone_name', 'unknown')}",
            ViolationType.WEATHER_VIOLATION: f"Weather safety violation: {data.get('weather_condition', 'unknown')}",
            ViolationType.OBSTACLE_COLLISION: f"Obstacle collision detected at {data.get('location', 'unknown location')}",
            ViolationType.UNAUTHORIZED_ACCESS: f"Unauthorized access attempt by {data.get('user', 'unknown user')}",
            ViolationType.MAINTENANCE_OVERRIDE: f"Maintenance safety override by {data.get('user', 'unknown user')}",
            ViolationType.EMERGENCY_STOP_TRIGGERED: "Emergency stop triggered"
        }
        
        return descriptions.get(violation_type, f"Safety violation: {violation_type.value}")
    
    async def _trigger_graduated_response(self, event: SafetyEvent):
        """Trigger graduated response based on event severity"""
        severity = event.severity
        
        response_actions = {
            ResponseLevel.WARNING: [
                self._send_warning_notification,
                self._log_warning_event
            ],
            ResponseLevel.CAUTION: [
                self._send_caution_notification,
                self._apply_precautionary_measures,
                self._increase_monitoring
            ],
            ResponseLevel.IMMEDIATE_ACTION: [
                self._send_urgent_notification,
                self._trigger_immediate_safety_measures,
                self._notify_emergency_contacts
            ],
            ResponseLevel.EMERGENCY_STOP: [
                self._trigger_emergency_stop,
                self._send_emergency_notification,
                self._notify_all_emergency_contacts,
                self._activate_emergency_protocols
            ],
            ResponseLevel.SYSTEM_SHUTDOWN: [
                self._trigger_system_shutdown,
                self._send_critical_notification,
                self._notify_all_emergency_contacts,
                self._activate_emergency_protocols
            ]
        }
        
        actions = response_actions.get(severity, [])
        for action in actions:
            try:
                await action(event)
                event.automated_response.append(action.__name__)
            except Exception as e:
                logger.error(f"Error executing response action {action.__name__}: {e}")
    
    async def _send_warning_notification(self, event: SafetyEvent):
        """Send warning notification"""
        await self.mqtt_client.publish("lawnberry/notifications/warning", {
            'event_id': event.event_id,
            'message': f"Safety warning: {event.description}",
            'timestamp': event.timestamp.isoformat()
        })
    
    async def _send_caution_notification(self, event: SafetyEvent):
        """Send caution notification"""
        await self.mqtt_client.publish("lawnberry/notifications/caution", {
            'event_id': event.event_id,
            'message': f"Safety caution: {event.description}",
            'timestamp': event.timestamp.isoformat(),
            'requires_attention': True
        })
    
    async def _send_urgent_notification(self, event: SafetyEvent):
        """Send urgent notification"""
        await self.mqtt_client.publish("lawnberry/notifications/urgent", {
            'event_id': event.event_id,
            'message': f"Urgent safety issue: {event.description}",
            'timestamp': event.timestamp.isoformat(),
            'requires_immediate_attention': True
        })
    
    async def _send_emergency_notification(self, event: SafetyEvent):
        """Send emergency notification"""
        await self.mqtt_client.publish("lawnberry/notifications/emergency", {
            'event_id': event.event_id,
            'message': f"EMERGENCY: {event.description}",
            'timestamp': event.timestamp.isoformat(),
            'emergency_response_required': True
        })
    
    async def _send_critical_notification(self, event: SafetyEvent):
        """Send critical system notification"""
        await self.mqtt_client.publish("lawnberry/notifications/critical", {
            'event_id': event.event_id,
            'message': f"CRITICAL SYSTEM EVENT: {event.description}",
            'timestamp': event.timestamp.isoformat(),
            'system_shutdown_initiated': True
        })
    
    async def _log_warning_event(self, event: SafetyEvent):
        """Log warning event"""
        logger.warning(f"Safety warning logged: {event.description}")
    
    async def _apply_precautionary_measures(self, event: SafetyEvent):
        """Apply precautionary safety measures"""
        await self.mqtt_client.publish("system/safety_command", {
            'command': 'APPLY_PRECAUTIONS',
            'event_id': event.event_id,
            'measures': ['reduce_speed', 'increase_sensor_frequency', 'enhanced_monitoring']
        })
    
    async def _increase_monitoring(self, event: SafetyEvent):
        """Increase safety monitoring frequency"""
        await self.mqtt_client.publish("system/safety_command", {
            'command': 'INCREASE_MONITORING',
            'event_id': event.event_id,
            'monitoring_level': 'enhanced'
        })
    
    async def _trigger_immediate_safety_measures(self, event: SafetyEvent):
        """Trigger immediate safety measures"""
        await self.mqtt_client.publish("system/safety_command", {
            'command': 'IMMEDIATE_SAFETY_MEASURES',
            'event_id': event.event_id,
            'measures': ['stop_blade', 'reduce_speed', 'return_to_safe_area']
        })
    
    async def _trigger_emergency_stop(self, event: SafetyEvent):
        """Trigger emergency stop"""
        await self.mqtt_client.publish("lawnberry/system/emergency_stop", {
            'event_id': event.event_id,
            'reason': event.description,
            'timestamp': event.timestamp.isoformat()
        })
    
    async def _trigger_system_shutdown(self, event: SafetyEvent):
        """Trigger complete system shutdown"""
        await self.mqtt_client.publish("lawnberry/system/shutdown", {
            'event_id': event.event_id,
            'reason': event.description,
            'timestamp': event.timestamp.isoformat(),
            'shutdown_type': 'emergency'
        })
    
    async def _notify_emergency_contacts(self, event: SafetyEvent):
        """Notify primary emergency contacts"""
        # Notify first 2 emergency contacts
        contacts_to_notify = self.emergency_contacts[:2]
        for contact in contacts_to_notify:
            await self._send_contact_notification(contact, event)
    
    async def _notify_all_emergency_contacts(self, event: SafetyEvent):
        """Notify all emergency contacts"""
        for contact in self.emergency_contacts:
            await self._send_contact_notification(contact, event)
    
    async def _send_contact_notification(self, contact: EmergencyContact, event: SafetyEvent):
        """Send notification to emergency contact"""
        message = f"Lawnberry Safety Alert\n\nEvent: {event.description}\nTime: {event.timestamp}\nSeverity: {event.severity.value}\n\nLocation: {event.location or 'Unknown'}\n\nPlease check the system immediately."
        
        if 'email' in contact.notification_methods:
            await self._send_email_notification(contact, event, message)
        
        if 'sms' in contact.notification_methods:
            await self._send_sms_notification(contact, event, message)
    
    async def _send_email_notification(self, contact: EmergencyContact, event: SafetyEvent, message: str):
        """Send email notification"""
        try:
            smtp_config = self.config.get('smtp', {})
            if not smtp_config:
                logger.warning("No SMTP configuration found for email notifications")
                return
            
            msg = MIMEMultipart()
            msg['From'] = smtp_config['from_email']
            msg['To'] = contact.email
            msg['Subject'] = f"Lawnberry Safety Alert - {event.severity.value.upper()}"
            
            msg.attach(MIMEText(message, 'plain'))
            
            server = smtplib.SMTP(smtp_config['server'], smtp_config['port'])
            if smtp_config.get('use_tls', True):
                server.starttls()
            if smtp_config.get('username') and smtp_config.get('password'):
                server.login(smtp_config['username'], smtp_config['password'])
            
            text = msg.as_string()
            server.sendmail(smtp_config['from_email'], contact.email, text)
            server.quit()
            
            logger.info(f"Email notification sent to {contact.name} ({contact.email})")
            
        except Exception as e:
            logger.error(f"Failed to send email notification to {contact.name}: {e}")
    
    async def _send_sms_notification(self, contact: EmergencyContact, event: SafetyEvent, message: str):
        """Send SMS notification (placeholder - requires SMS service integration)"""
        # This would integrate with an SMS service like Twilio
        logger.info(f"SMS notification would be sent to {contact.name} ({contact.phone}): {message[:100]}...")
    
    async def _activate_emergency_protocols(self, event: SafetyEvent):
        """Activate emergency protocols"""
        await self.mqtt_client.publish("lawnberry/system/emergency_protocols", {
            'event_id': event.event_id,
            'protocols': ['secure_system', 'preserve_data', 'prepare_diagnostics'],
            'timestamp': event.timestamp.isoformat()
        })
    
    async def _trigger_emergency_response(self, data: Dict[str, Any]):
        """Trigger comprehensive emergency response"""
        emergency_type = data.get('type', 'unknown')
        severity = ResponseLevel.EMERGENCY_STOP
        
        event = SafetyEvent(
            event_id=f"emergency_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            event_type=ViolationType.EMERGENCY_STOP_TRIGGERED,
            timestamp=datetime.now(),
            severity=severity,
            description=f"Emergency response triggered: {emergency_type}",
            location=data.get('location')
        )
        
        await self._trigger_graduated_response(event)
        
        # Trigger emergency callbacks
        for callback in self.emergency_callbacks:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Error in emergency callback: {e}")
    
    async def _validate_shutdown_token(self, token: str) -> bool:
        """Validate remote shutdown token"""
        # This would implement proper token validation
        # For now, just check if token exists in config
        valid_tokens = self.config.get('remote_shutdown_tokens', [])
        return token in valid_tokens
    
    async def _execute_remote_shutdown(self, data: Dict[str, Any]):
        """Execute remote shutdown"""
        logger.critical("Remote shutdown command received and validated")
        
        shutdown_event = SafetyEvent(
            event_id=f"remote_shutdown_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            event_type=ViolationType.EMERGENCY_STOP_TRIGGERED,
            timestamp=datetime.now(),
            severity=ResponseLevel.SYSTEM_SHUTDOWN,
            description="Remote emergency shutdown activated",
            user_involved=data.get('user', 'remote_operator')
        )
        
        await self._trigger_graduated_response(shutdown_event)
    
    async def _safety_monitoring_loop(self):
        """Main safety monitoring loop"""
        while self._running:
            try:
                # Check for unresolved violations that need escalation
                current_time = datetime.now()
                for event in self.active_violations.values():
                    if not event.resolved:
                        time_since_event = current_time - event.timestamp
                        escalation_time = self.response_escalation_times.get(event.severity, timedelta(minutes=5))
                        
                        if time_since_event > escalation_time:
                            await self._escalate_violation(event)
                
                await asyncio.sleep(10.0)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Error in safety monitoring loop: {e}")
                await asyncio.sleep(10.0)
    
    async def _escalation_monitoring_loop(self):
        """Monitor for violation escalation"""
        while self._running:
            try:
                # This would implement more sophisticated escalation logic
                await asyncio.sleep(30.0)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error in escalation monitoring loop: {e}")
                await asyncio.sleep(30.0)
    
    async def _weather_monitoring_loop(self):
        """Monitor weather conditions and apply safety rules"""
        while self._running:
            try:
                if self.current_weather and not self.weather_override_active:
                    await self._apply_weather_safety_rules()
                
                await asyncio.sleep(60.0)  # Check every minute
                
            except Exception as e:
                logger.error(f"Error in weather monitoring loop: {e}")
                await asyncio.sleep(60.0)
    
    async def _escalate_violation(self, event: SafetyEvent):
        """Escalate a safety violation to higher severity"""
        severity_levels = [ResponseLevel.WARNING, ResponseLevel.CAUTION, ResponseLevel.IMMEDIATE_ACTION, ResponseLevel.EMERGENCY_STOP, ResponseLevel.SYSTEM_SHUTDOWN]
        current_index = severity_levels.index(event.severity)
        
        if current_index < len(severity_levels) - 1:
            event.severity = severity_levels[current_index + 1]
            logger.warning(f"Escalating violation {event.event_id} to {event.severity.value}")
            await self._trigger_graduated_response(event)
    
    def register_violation_callback(self, callback: Callable):
        """Register callback for safety violations"""
        self.violation_callbacks.append(callback)
    
    def register_emergency_callback(self, callback: Callable):
        """Register callback for emergency events"""
        self.emergency_callbacks.append(callback)
    
    async def add_geofence_zone(self, zone: GeoFenceZone):
        """Add a geofence zone"""
        self.geofence_zones[zone.zone_id] = zone
        logger.info(f"Added geofence zone: {zone.name}")
    
    async def remove_geofence_zone(self, zone_id: str):
        """Remove a geofence zone"""
        if zone_id in self.geofence_zones:
            del self.geofence_zones[zone_id]
            logger.info(f"Removed geofence zone: {zone_id}")
    
    async def resolve_violation(self, event_id: str, resolution_notes: str = ""):
        """Mark a safety violation as resolved"""
        if event_id in self.active_violations:
            event = self.active_violations[event_id]
            event.resolved = True
            event.resolution_time = datetime.now()
            event.manual_response.append(f"Resolved: {resolution_notes}")
            
            del self.active_violations[event_id]
            logger.info(f"Safety violation {event_id} marked as resolved")
    
    async def get_safety_status(self) -> Dict[str, Any]:
        """Get comprehensive safety status"""
        return {
            "active_violations": len(self.active_violations),
            "total_events_today": len([e for e in self.safety_events if e.timestamp.date() == datetime.now().date()]),
            "current_weather": self.current_weather.value if self.current_weather else None,
            "weather_override_active": self.weather_override_active,
            "geofence_zones": len(self.geofence_zones),
            "emergency_contacts": len(self.emergency_contacts),
            "remote_shutdown_enabled": self.remote_shutdown_enabled,
            "recent_violations": [
                {
                    "event_id": event.event_id,
                    "type": event.event_type.value,
                    "severity": event.severity.value,
                    "timestamp": event.timestamp.isoformat(),
                    "resolved": event.resolved
                }
                for event in sorted(self.safety_events[-10:], key=lambda x: x.timestamp, reverse=True)
            ]
        }
