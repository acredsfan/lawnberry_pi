"""Computer Vision System

This module provides comprehensive computer vision capabilities for the autonomous mower,
including object detection, obstacle classification, and scene understanding.

Main components:
- VisionManager: Main orchestration and API
- CameraProcessor: Low-level camera frame processing
- ObjectDetector: AI-powered object detection and classification
- CoralTPUManager: Coral TPU hardware acceleration
- TrainingManager: Continuous learning and model adaptation
"""

from .vision_manager import VisionManager
from .camera_processor import CameraProcessor
from .object_detector import ObjectDetector
from .coral_tpu_manager import CoralTPUManager
from .training_manager import TrainingManager
from .data_structures import *

__all__ = [
    'VisionManager',
    'CameraProcessor', 
    'ObjectDetector',
    'CoralTPUManager',
    'TrainingManager'
]
