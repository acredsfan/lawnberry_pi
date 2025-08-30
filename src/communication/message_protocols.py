"""
Message Protocols and Data Structures
Standardized message formats for MQTT communication
"""

import json
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, Union, List
from enum import Enum
from datetime import datetime


class MessageType(Enum):
    """Message type enumeration"""
    SENSOR_DATA = "sensor_data"
    COMMAND = "command"
    RESPONSE = "response"
    STATUS = "status"
    EVENT = "event"
    HEARTBEAT = "heartbeat"
    ALERT = "alert"


class Priority(Enum):
    """Message priority levels"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class MessageMetadata:
    """Message metadata"""
    timestamp: float
    message_id: str
    sender: str
    message_type: MessageType
    priority: Priority = Priority.NORMAL
    correlation_id: Optional[str] = None
    expires_at: Optional[float] = None
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'timestamp': self.timestamp,
            'message_id': self.message_id,
            'sender': self.sender,
            'message_type': self.message_type.value,
            'priority': self.priority.value,
            'correlation_id': self.correlation_id,
            'expires_at': self.expires_at,
            'retry_count': self.retry_count
        }


@dataclass
class MessageProtocol:
    """Base message protocol"""
    metadata: MessageMetadata
    payload: Dict[str, Any]
    
    def to_json(self) -> str:
        """Serialize to JSON"""
        # Ensure JSON is RFC 8259 compliant: replace NaN/Infinity with null
        import math

        def _sanitize(obj):
            try:
                if isinstance(obj, float):
                    return obj if math.isfinite(obj) else None
                if isinstance(obj, (int, str, bool)) or obj is None:
                    return obj
                if isinstance(obj, list):
                    return [_sanitize(i) for i in obj]
                if isinstance(obj, dict):
                    return {k: _sanitize(v) for k, v in obj.items()}
                return obj
            except Exception:
                try:
                    return str(obj)
                except Exception:
                    return None

        data = {
            'metadata': self.metadata.to_dict(),
            'payload': _sanitize(self.payload),
        }
        return json.dumps(data, allow_nan=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'MessageProtocol':
        """Deserialize from JSON"""
        data = json.loads(json_str)
        metadata = MessageMetadata(
            timestamp=data['metadata']['timestamp'],
            message_id=data['metadata']['message_id'],
            sender=data['metadata']['sender'],
            message_type=MessageType(data['metadata']['message_type']),
            priority=Priority(data['metadata']['priority']),
            correlation_id=data['metadata'].get('correlation_id'),
            expires_at=data['metadata'].get('expires_at'),
            retry_count=data['metadata'].get('retry_count', 0)
        )
        return cls(metadata=metadata, payload=data['payload'])


@dataclass
class SensorData(MessageProtocol):
    """Sensor data message"""
    
    @classmethod
    def create(cls, sender: str, sensor_type: str, data: Dict[str, Any], 
               device_id: Optional[str] = None) -> 'SensorData':
        """Create sensor data message"""
        import uuid
        
        metadata = MessageMetadata(
            timestamp=time.time(),
            message_id=str(uuid.uuid4()),
            sender=sender,
            message_type=MessageType.SENSOR_DATA,
            priority=Priority.NORMAL
        )
        
        payload = {
            'sensor_type': sensor_type,
            'device_id': device_id,
            'data': data,
            'units': {},  # Unit information
            'quality': 1.0,  # Data quality indicator (0.0-1.0)
            'status': 'healthy'  # Device status
        }
        
        return cls(metadata=metadata, payload=payload)


@dataclass 
class CommandMessage(MessageProtocol):
    """Command message"""
    
    @classmethod
    def create(cls, sender: str, target: str, command: str, 
               parameters: Dict[str, Any] = None, priority: Priority = Priority.NORMAL) -> 'CommandMessage':
        """Create command message"""
        import uuid
        
        metadata = MessageMetadata(
            timestamp=time.time(),
            message_id=str(uuid.uuid4()),
            sender=sender,
            message_type=MessageType.COMMAND,
            priority=priority,
            correlation_id=str(uuid.uuid4())
        )
        
        payload = {
            'target': target,
            'command': command,
            'parameters': parameters or {},
            'timeout': 30.0,  # Default timeout in seconds
            'require_ack': True
        }
        
        return cls(metadata=metadata, payload=payload)


@dataclass
class ResponseMessage(MessageProtocol):
    """Response message"""
    
    @classmethod
    def create(cls, sender: str, correlation_id: str, success: bool,
               result: Any = None, error: str = None) -> 'ResponseMessage':
        """Create response message"""
        import uuid
        
        metadata = MessageMetadata(
            timestamp=time.time(),
            message_id=str(uuid.uuid4()),
            sender=sender,
            message_type=MessageType.RESPONSE,
            priority=Priority.NORMAL,
            correlation_id=correlation_id
        )
        
        payload = {
            'success': success,
            'result': result,
            'error': error,
            'execution_time': None  # Can be filled by handler
        }
        
        return cls(metadata=metadata, payload=payload)


@dataclass
class StatusMessage(MessageProtocol):
    """Status/heartbeat message"""
    
    @classmethod
    def create(cls, sender: str, status: str, details: Dict[str, Any] = None) -> 'StatusMessage':
        """Create status message"""
        import uuid
        
        metadata = MessageMetadata(
            timestamp=time.time(),
            message_id=str(uuid.uuid4()),
            sender=sender,
            message_type=MessageType.STATUS,
            priority=Priority.LOW
        )
        
        payload = {
            'status': status,  # 'healthy', 'degraded', 'error', 'offline'
            'uptime': 0,
            'version': '1.0.0',
            'details': details or {},
            'resources': {
                'cpu_usage': 0.0,
                'memory_usage': 0.0,
                'disk_usage': 0.0
            }
        }
        
        return cls(metadata=metadata, payload=payload)


@dataclass
class EventMessage(MessageProtocol):
    """Event notification message"""
    
    @classmethod
    def create(cls, sender: str, event_type: str, event_data: Dict[str, Any],
               priority: Priority = Priority.NORMAL) -> 'EventMessage':
        """Create event message"""
        import uuid
        
        metadata = MessageMetadata(
            timestamp=time.time(),
            message_id=str(uuid.uuid4()),
            sender=sender,
            message_type=MessageType.EVENT,
            priority=priority
        )
        
        payload = {
            'event_type': event_type,
            'event_data': event_data,
            'source': sender,
            'category': 'system'  # 'system', 'safety', 'navigation', etc.
        }
        
        return cls(metadata=metadata, payload=payload)


@dataclass
class AlertMessage(MessageProtocol):
    """Alert/emergency message"""
    
    @classmethod
    def create(cls, sender: str, alert_type: str, message: str,
               severity: str = 'warning') -> 'AlertMessage':
        """Create alert message"""
        import uuid
        
        metadata = MessageMetadata(
            timestamp=time.time(),
            message_id=str(uuid.uuid4()),
            sender=sender,
            message_type=MessageType.ALERT,
            priority=Priority.CRITICAL if severity == 'critical' else Priority.HIGH
        )
        
        payload = {
            'alert_type': alert_type,
            'severity': severity,  # 'info', 'warning', 'error', 'critical'
            'message': message,
            'acknowledged': False,
            'auto_resolve': False,
            'context': {}
        }
        
        return cls(metadata=metadata, payload=payload)


class MessageValidator:
    """Message validation utilities"""
    
    @staticmethod
    def validate_message(message: MessageProtocol) -> bool:
        """Validate message structure and content"""
        try:
            # Check required fields
            if not message.metadata.message_id:
                return False
            if not message.metadata.sender:
                return False
            if not message.metadata.timestamp:
                return False
            
            # Check payload exists
            if message.payload is None:
                return False
            
            # Type-specific validation
            msg_type = message.metadata.message_type
            
            if msg_type == MessageType.SENSOR_DATA:
                required_fields = ['sensor_type', 'data']
                return all(field in message.payload for field in required_fields)
            
            elif msg_type == MessageType.COMMAND:
                required_fields = ['target', 'command']
                return all(field in message.payload for field in required_fields)
            
            elif msg_type == MessageType.RESPONSE:
                required_fields = ['success']
                return all(field in message.payload for field in required_fields)
            
            return True
            
        except Exception:
            return False
    
    @staticmethod
    def sanitize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize payload data"""
        # Remove any potentially dangerous content
        sanitized = {}
        for key, value in payload.items():
            # Basic sanitization - extend as needed
            if isinstance(value, str) and len(value) > 10000:
                value = value[:10000] + "... [truncated]"
            sanitized[key] = value
        return sanitized


class MessageCompressor:
    """Message compression utilities"""
    
    @staticmethod
    def compress_message(message: MessageProtocol) -> bytes:
        """Compress message for transmission"""
        import gzip
        json_str = message.to_json()
        return gzip.compress(json_str.encode('utf-8'))
    
    @staticmethod
    def decompress_message(compressed_data: bytes) -> MessageProtocol:
        """Decompress message"""
        import gzip
        json_str = gzip.decompress(compressed_data).decode('utf-8')
        return MessageProtocol.from_json(json_str)
