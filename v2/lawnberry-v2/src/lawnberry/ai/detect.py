"""AI detection interface for LawnBerry Pi v2."""

from __future__ import annotations

import os
from typing import Any, Protocol


class Detector(Protocol):
    """AI detection interface."""

    def warmup(self) -> None:
        """Warm up the detector model."""
        ...

    def infer(self, frame_bgr) -> list[dict[str, Any]]:
        """Run inference on a frame."""
        ...


def get_detector() -> Detector:
    """Get detector instance based on acceleration preference."""
    accel = os.getenv("LBY_ACCEL", "").lower()
    if accel == "hailo":
        try:
            from .hailo_runner import HailoDetector  # type: ignore

            detector = HailoDetector()
            detector.warmup()
            return detector
        except Exception:
            pass
    if accel == "coral":
        try:
            from .coral_runner import CoralDetector  # type: ignore

            detector = CoralDetector()
            detector.warmup()
            return detector
        except Exception:
            pass
    from .cpu_tflite_runner import CpuTFLiteDetector  # type: ignore

    detector = CpuTFLiteDetector()
    detector.warmup()
    return detector
