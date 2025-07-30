#!/usr/bin/env python3
"""Test computer vision system imports"""

import sys
sys.path.append('.')

try:
    from src.vision import VisionManager, VisionConfig, ProcessingMode
    from src.vision.data_structures import ObjectType, SafetyLevel
    print("✓ Computer vision imports successful")
    
    # Test basic configuration
    config = VisionConfig()
    print("✓ Vision configuration created")
    print(f"  - Confidence threshold: {config.confidence_threshold}")
    print(f"  - Max processing time: {config.max_processing_time_ms}ms")
    print(f"  - TPU enabled: {config.enable_tpu}")
    print(f"  - Continuous learning: {config.enable_continuous_learning}")
    
    # Test data structures
    print("✓ Data structures available:")
    print(f"  - Object types: {len(list(ObjectType))} defined")
    print(f"  - Safety levels: {len(list(SafetyLevel))} defined")
    print(f"  - Processing modes: {len(list(ProcessingMode))} defined")
    
    print("✓ Computer vision system ready for integration")
    
except ImportError as e:
    print(f"✗ Import error: {e}")
except Exception as e:
    print(f"✗ Error: {e}")
