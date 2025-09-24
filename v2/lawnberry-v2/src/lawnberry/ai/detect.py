from __future__ import annotations
import os
from typing import Protocol, Any
class Detector(Protocol):
    def warmup(self) -> None: ...
    def infer(self, frame_bgr) -> list[dict[str, Any]]: ...
def get_detector() -> Detector:
    accel = os.getenv("LBY_ACCEL", "").lower()
    if accel == "hailo":
        try:
            from .hailo_runner import HailoDetector  # type: ignore
            d = HailoDetector(); d.warmup(); return d
        except Exception: pass
    if accel == "coral":
        try:
            from .coral_runner import CoralDetector  # type: ignore
            d = CoralDetector(); d.warmup(); return d
        except Exception: pass
    from .cpu_tflite_runner import CpuTFLiteDetector  # type: ignore
    d = CpuTFLiteDetector(); d.warmup(); return d
