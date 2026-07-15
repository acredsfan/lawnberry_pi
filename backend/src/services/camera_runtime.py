"""Select the camera interface without creating competing live device owners."""

from __future__ import annotations

import os

if os.getenv("SIM_MODE", "0") == "1":
    # Offline development/CI may embed the simulated owner in-process.
    from .camera_stream_service import camera_service
else:
    # Raspberry Pi hardware mode always consumes the standalone owner over IPC.
    from .camera_client import camera_client as camera_service

__all__ = ["camera_service"]
