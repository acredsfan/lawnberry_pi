"""
Data Models
Standardized data structures for all system components
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from enum import Enum
import json


class DataType(Enum):
    """Data type enumeration"""
    SENSOR = "sensor"
    NAVIGATION = "navigation"
    OPERATIONAL = "operational"
    CONFIGURATION = "configuration"
    PERFORMANCE = "performance"
    SAFETY = "safety"


class Priority(Enum):
    """Data priority levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class SensorReading:
    """Standardized sensor data structure"""
    sensor_id: str
    sensor_type: str
    timestamp: datetime
    value: Union[float, int, Dict[str, Any]]
    unit: str = ""
    quality: float = 1.0  # 0.0 to 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            'sensor_id': self.sensor_id,
            'sensor_type': self.sensor_type,
            'timestamp': self.timestamp.isoformat(),
            'value': self.value,
            'unit': self.unit,
            'quality': self.quality,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SensorReading':
        """Create from dictionary"""
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class NavigationData:
    """Navigation and path planning data"""
    timestamp: datetime
    position: Dict[str, float]  # {'lat': float, 'lng': float, 'alt': float}
    heading: float
    speed: float
    target_position: Optional[Dict[str, float]] = None
    path_points: List[Dict[str, float]] = field(default_factory=list)
    obstacles: List[Dict[str, Any]] = field(default_factory=list)
    coverage_map: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'position': self.position,
            'heading': self.heading,
            'speed': self.speed,
            'target_position': self.target_position,
            'path_points': self.path_points,
            'obstacles': self.obstacles,
            'coverage_map': self.coverage_map
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'NavigationData':
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class OperationalState:
    """Current operational state"""
    state: str
    mode: str
    battery_level: float
    current_task: Optional[str] = None
    progress: float = 0.0
    estimated_completion: Optional[datetime] = None
    last_update: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'state': self.state,
            'mode': self.mode,
            'battery_level': self.battery_level,
            'current_task': self.current_task,
            'progress': self.progress,
            'estimated_completion': self.estimated_completion.isoformat() if self.estimated_completion else None,
            'last_update': self.last_update.isoformat(),
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OperationalState':
        data['last_update'] = datetime.fromisoformat(data['last_update'])
        if data.get('estimated_completion'):
            data['estimated_completion'] = datetime.fromisoformat(data['estimated_completion'])
        return cls(**data)


@dataclass
class PerformanceMetric:
    """Performance and analytics data"""
    metric_name: str
    timestamp: datetime
    value: Union[float, int]
    category: str
    tags: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'metric_name': self.metric_name,
            'timestamp': self.timestamp.isoformat(),
            'value': self.value,
            'category': self.category,
            'tags': self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PerformanceMetric':
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class OperationalLog:
    """Detailed activity logging"""
    timestamp: datetime
    level: str  # INFO, WARNING, ERROR, CRITICAL
    component: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'timestamp': self.timestamp.isoformat(),
            'level': self.level,
            'component': self.component,
            'message': self.message,
            'context': self.context,
            'correlation_id': self.correlation_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OperationalLog':
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


@dataclass
class ConfigurationData:
    """System configuration data"""
    config_id: str
    section: str
    key: str
    value: Any
    data_type: str
    last_modified: datetime = field(default_factory=datetime.now)
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'config_id': self.config_id,
            'section': self.section,
            'key': self.key,
            'value': self.value,
            'data_type': self.data_type,
            'last_modified': self.last_modified.isoformat(),
            'version': self.version,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConfigurationData':
        data['last_modified'] = datetime.fromisoformat(data['last_modified'])
        return cls(**data)
