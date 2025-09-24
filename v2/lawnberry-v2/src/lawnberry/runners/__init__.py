"""AI acceleration runners for LawnBerry Pi v2.

This module implements the constitutional AI acceleration hierarchy:
- Coral TPU (isolated venv) - top tier
- Hailo AI Hat (optional) - mid tier
- CPU TFLite (fallback) - base tier

Each runner provides the same interface with graceful degradation.
"""

from .cpu_tflite_runner import CpuTFLiteDetector, CpuTFLiteError

__all__ = [
    "CpuTFLiteDetector",
    "CpuTFLiteError",
]
