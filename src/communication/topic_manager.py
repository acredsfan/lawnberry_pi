"""
Topic Manager
Manages hierarchical MQTT topic structure and routing
"""

import re
from typing import Dict, Any, List, Set, Optional, Callable
from dataclasses import dataclass
from enum import Enum


class TopicType(Enum):
    """Topic type enumeration"""
    SENSOR_DATA = "sensors"
    COMMANDS = "commands"
    RESPONSES = "responses"
    STATUS = "status"
    EVENTS = "events"
    ALERTS = "alerts"
    NAVIGATION = "navigation"
    SAFETY = "safety"
    POWER = "power"
    VISION = "vision"
    WEATHER = "weather"
    SYSTEM = "system"


@dataclass
class TopicDefinition:
    """Topic definition with metadata"""
    pattern: str
    topic_type: TopicType
    description: str
    qos: int = 1
    retained: bool = False
    rate_limit: Optional[int] = None  # messages per minute
    validators: List[Callable] = None
    
    def __post_init__(self):
        if self.validators is None:
            self.validators = []


class TopicManager:
    """Manages MQTT topic hierarchy and routing"""
    
    def __init__(self, base_namespace: str = "lawnberry"):
        self.base_namespace = base_namespace
        self.topic_definitions: Dict[str, TopicDefinition] = {}
        self.subscriptions: Dict[str, Set[str]] = {}  # topic -> set of client_ids
        self._setup_standard_topics()
    
    def _setup_standard_topics(self):
        """Setup standard topic definitions"""
        
        # Sensor data topics
        self.register_topic(
            "sensors/+/data",
            TopicType.SENSOR_DATA,
            "Individual sensor data streams",
            qos=1,
            rate_limit=100
        )
        
        self.register_topic(
            "sensors/+/status",
            TopicType.STATUS,
            "Sensor health and status",
            qos=1,
            retained=True,
            rate_limit=20
        )
        
        # Command and response topics
        self.register_topic(
            "commands/+",
            TopicType.COMMANDS,
            "Service command topics",
            qos=2
        )
        
        self.register_topic(
            "responses/+",
            TopicType.RESPONSES,
            "Command response topics",
            qos=2
        )
        
        # Navigation topics
        self.register_topic(
            "navigation/position",
            TopicType.NAVIGATION,
            "Current mower position",
            qos=1,
            retained=True,
            rate_limit=20
        )
        
        self.register_topic(
            "navigation/path",
            TopicType.NAVIGATION,
            "Current navigation path",
            qos=1,
            retained=True,
            rate_limit=10
        )
        
        self.register_topic(
            "navigation/status",
            TopicType.NAVIGATION,
            "Navigation system status",
            qos=1,
            retained=True,
            rate_limit=5
        )
        
        # Safety topics
        self.register_topic(
            "safety/alerts/+",
            TopicType.ALERTS,
            "Safety alert topics by type",
            qos=2,
            retained=True
        )
        
        self.register_topic(
            "safety/emergency_stop",
            TopicType.ALERTS,
            "Emergency stop command",
            qos=2,
            retained=True
        )
        
        self.register_topic(
            "safety/hazards",
            TopicType.ALERTS,
            "Detected hazards",
            qos=2,
            rate_limit=50
        )
        
        # Power management topics
        self.register_topic(
            "power/battery",
            TopicType.POWER,
            "Battery status and metrics",
            qos=1,
            retained=True,
            rate_limit=20
        )
        
        self.register_topic(
            "power/solar",
            TopicType.POWER,
            "Solar charging status",
            qos=1,
            retained=True,
            rate_limit=20
        )
        
        self.register_topic(
            "power/consumption",
            TopicType.POWER,
            "Power consumption metrics",
            qos=1,
            rate_limit=60
        )
        
        # Vision system topics
        self.register_topic(
            "vision/detections",
            TopicType.VISION,
            "Object detection results",
            qos=1,
            rate_limit=30
        )
        
        self.register_topic(
            "vision/frame_analysis",
            TopicType.VISION,
            "Frame analysis results",
            qos=0,
            rate_limit=10
        )
        
        # Weather topics
        self.register_topic(
            "weather/current",
            TopicType.WEATHER,
            "Current weather conditions",
            qos=1,
            retained=True,
            rate_limit=12  # Every 5 minutes
        )
        
        self.register_topic(
            "weather/forecast",
            TopicType.WEATHER,
            "Weather forecast data",
            qos=1,
            retained=True,
            rate_limit=1  # Every hour
        )
        
        self.register_topic(
            "weather/alerts",
            TopicType.WEATHER,
            "Weather alerts and warnings",
            qos=2,
            retained=True,
            rate_limit=20
        )
        
        # System topics
        self.register_topic(
            "system/health",
            TopicType.STATUS,
            "Overall system health",
            qos=1,
            retained=True,
            rate_limit=5
        )
        
        self.register_topic(
            "system/services/+/status",
            TopicType.STATUS,
            "Individual service status",
            qos=1,
            retained=True,
            rate_limit=10
        )
        
        self.register_topic(
            "system/events/+",
            TopicType.EVENTS,
            "System events by category",
            qos=1,
            rate_limit=60
        )
        
        self.register_topic(
            "system/logs/+",
            TopicType.EVENTS,
            "System logs by level",
            qos=0,
            rate_limit=100
        )
    
    def register_topic(self, pattern: str, topic_type: TopicType, description: str,
                      qos: int = 1, retained: bool = False, rate_limit: Optional[int] = None,
                      validators: List[Callable] = None):
        """Register a topic definition"""
        topic_def = TopicDefinition(
            pattern=pattern,
            topic_type=topic_type,
            description=description,
            qos=qos,
            retained=retained,
            rate_limit=rate_limit,
            validators=validators or []
        )
        
        self.topic_definitions[pattern] = topic_def
    
    def get_full_topic(self, topic: str) -> str:
        """Get full topic with namespace"""
        if topic.startswith(f"{self.base_namespace}/"):
            return topic
        return f"{self.base_namespace}/{topic}"
    
    def parse_topic(self, full_topic: str) -> Optional[Dict[str, str]]:
        """Parse topic into components"""
        if not full_topic.startswith(f"{self.base_namespace}/"):
            return None
        
        topic = full_topic[len(self.base_namespace) + 1:]
        parts = topic.split('/')
        
        if len(parts) < 2:
            return None
        
        return {
            'category': parts[0],
            'subcategory': parts[1] if len(parts) > 1 else None,
            'identifier': parts[2] if len(parts) > 2 else None,
            'action': parts[3] if len(parts) > 3 else None,
            'full_topic': full_topic,
            'relative_topic': topic
        }
    
    def match_topic_pattern(self, topic: str, pattern: str) -> bool:
        """Check if topic matches pattern (supports MQTT wildcards)"""
        # Convert MQTT wildcards to regex
        regex_pattern = pattern.replace('+', '[^/]+').replace('#', '.*')
        regex_pattern = f"^{regex_pattern}$"
        
        return bool(re.match(regex_pattern, topic))
    
    def find_topic_definition(self, topic: str) -> Optional[TopicDefinition]:
        """Find topic definition for a given topic"""
        relative_topic = topic
        if topic.startswith(f"{self.base_namespace}/"):
            relative_topic = topic[len(self.base_namespace) + 1:]
        
        for pattern, definition in self.topic_definitions.items():
            if self.match_topic_pattern(relative_topic, pattern):
                return definition
        
        return None
    
    def get_recommended_qos(self, topic: str) -> int:
        """Get recommended QoS for topic"""
        definition = self.find_topic_definition(topic)
        return definition.qos if definition else 1
    
    def should_retain(self, topic: str) -> bool:
        """Check if topic should be retained"""
        definition = self.find_topic_definition(topic)
        return definition.retained if definition else False
    
    def get_rate_limit(self, topic: str) -> Optional[int]:
        """Get rate limit for topic"""
        definition = self.find_topic_definition(topic)
        return definition.rate_limit if definition else None
    
    def validate_message(self, topic: str, message: Any) -> bool:
        """Validate message for topic"""
        definition = self.find_topic_definition(topic)
        if not definition or not definition.validators:
            return True
        
        for validator in definition.validators:
            try:
                if not validator(message):
                    return False
            except Exception:
                return False
        
        return True
    
    def subscribe_client(self, client_id: str, topic: str):
        """Track client subscription"""
        full_topic = self.get_full_topic(topic)
        if full_topic not in self.subscriptions:
            self.subscriptions[full_topic] = set()
        self.subscriptions[full_topic].add(client_id)
    
    def unsubscribe_client(self, client_id: str, topic: str):
        """Remove client subscription"""
        full_topic = self.get_full_topic(topic)
        if full_topic in self.subscriptions:
            self.subscriptions[full_topic].discard(client_id)
            if not self.subscriptions[full_topic]:
                del self.subscriptions[full_topic]
    
    def get_subscribers(self, topic: str) -> Set[str]:
        """Get subscribers for topic"""
        full_topic = self.get_full_topic(topic)
        return self.subscriptions.get(full_topic, set()).copy()
    
    def get_topics_for_service(self, service_name: str) -> List[str]:
        """Get relevant topics for a service"""
        topics = []
        
        # Service-specific patterns
        service_patterns = {
            'sensors': ['sensors/+/data', 'sensors/+/status'],
            'navigation': ['navigation/+', 'commands/navigation', 'responses/navigation'],
            'safety': ['safety/+', 'commands/safety', 'responses/safety'],
            'power': ['power/+', 'commands/power', 'responses/power'],
            'vision': ['vision/+', 'commands/vision', 'responses/vision'],
            'weather': ['weather/+', 'commands/weather', 'responses/weather'],
            'system': ['system/+', 'commands/system', 'responses/system']
        }
        
        if service_name in service_patterns:
            for pattern in service_patterns[service_name]:
                topics.append(self.get_full_topic(pattern))
        
        # Add common topics
        common_topics = [
            'system/health',
            'safety/emergency_stop',
            'system/events/error'
        ]
        
        for topic in common_topics:
            topics.append(self.get_full_topic(topic))
        
        return topics
    
    def get_topic_hierarchy(self) -> Dict[str, Any]:
        """Get topic hierarchy structure"""
        hierarchy = {}
        
        for pattern, definition in self.topic_definitions.items():
            parts = pattern.split('/')
            current = hierarchy
            
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            
            # Add leaf with definition info
            leaf = parts[-1]
            current[leaf] = {
                'type': definition.topic_type.value,
                'description': definition.description,
                'qos': definition.qos,
                'retained': definition.retained,
                'rate_limit': definition.rate_limit
            }
        
        return hierarchy
    
    def generate_topic_documentation(self) -> str:
        """Generate documentation for all topics"""
        doc_lines = [
            f"# MQTT Topic Structure for {self.base_namespace}",
            "",
            "## Topic Hierarchy",
            ""
        ]
        
        # Group by topic type
        by_type = {}
        for pattern, definition in self.topic_definitions.items():
            topic_type = definition.topic_type.value
            if topic_type not in by_type:
                by_type[topic_type] = []
            by_type[topic_type].append((pattern, definition))
        
        for topic_type, topics in sorted(by_type.items()):
            doc_lines.append(f"### {topic_type.title()}")
            doc_lines.append("")
            
            for pattern, definition in sorted(topics):
                full_pattern = f"{self.base_namespace}/{pattern}"
                doc_lines.append(f"- **{full_pattern}**")
                doc_lines.append(f"  - Description: {definition.description}")
                doc_lines.append(f"  - QoS: {definition.qos}")
                doc_lines.append(f"  - Retained: {definition.retained}")
                if definition.rate_limit:
                    doc_lines.append(f"  - Rate Limit: {definition.rate_limit} msg/min")
                doc_lines.append("")
        
        return "\n".join(doc_lines)


# Singleton instance
topic_manager = TopicManager()

# Module-level convenience functions for legacy imports/tests that treat this module
# as a function namespace (e.g., tests importing `src.communication.topic_manager`):
def match_topic_pattern(topic: str, pattern: str) -> bool:
    """Module-level wrapper: check if topic matches pattern (MQTT wildcards)."""
    return topic_manager.match_topic_pattern(topic, pattern)

def find_topic_definition(topic: str) -> Optional[TopicDefinition]:
    """Module-level wrapper: find topic definition for a given topic."""
    return topic_manager.find_topic_definition(topic)

def get_recommended_qos(topic: str) -> int:
    """Module-level wrapper: recommended QoS for topic."""
    return topic_manager.get_recommended_qos(topic)

def should_retain(topic: str) -> bool:
    """Module-level wrapper: whether topic should be retained."""
    return topic_manager.should_retain(topic)

def get_rate_limit(topic: str) -> Optional[int]:
    """Module-level wrapper: rate limit for topic if any."""
    return topic_manager.get_rate_limit(topic)

def get_topic_hierarchy() -> Dict[str, Any]:
    """Module-level wrapper: produce topic hierarchy structure."""
    return topic_manager.get_topic_hierarchy()
