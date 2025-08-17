"""
Sensor Fusion Engine
Combines IMU, GPS, ToF, and camera data for accurate localization and obstacle detection
"""

from .fusion_engine import SensorFusionEngine
from .localization import LocalizationSystem
from .obstacle_detection import ObstacleDetectionSystem
from .safety_monitor import SafetyMonitor
from .data_structures import (
    PoseEstimate, ObstacleMap, SafetyStatus, SensorHealthMetrics,
    LocalizationData, ObstacleData, HazardAlert
)

# Re-export safety/obstacle related types for tests and callers
from .data_structures import ObstacleInfo, ObstacleType, HazardLevel

__all__ = [
    'SensorFusionEngine',
    'LocalizationSystem', 
    'ObstacleDetectionSystem',
    'SafetyMonitor',
    'PoseEstimate',
    'ObstacleMap',
    'SafetyStatus',
    'SensorHealthMetrics',
    'LocalizationData',
    'ObstacleData',
    'HazardAlert'
    ,'ObstacleInfo', 'ObstacleType', 'HazardLevel'
]
