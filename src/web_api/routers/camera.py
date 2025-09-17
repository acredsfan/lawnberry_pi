"""
Camera streaming API endpoints used by the web UI.
This router pulls frames from the shared HardwareInterface stored on app.state,
falling back to cached camera frames when the API process does not own the camera.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

try:  # pragma: no cover
    import cv2  # type: ignore
except Exception:  # noqa
    cv2 = None  # type: ignore
try:  # pragma: no cover
    import numpy as np  # type: ignore
except Exception:  # noqa
    np = None  # type: ignore

from ..dependencies import get_system_manager
from ..utils.camera_cache import CACHE_PATH, get_cache_mtime, load_cached_frame

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/camera", tags=["camera"])

_CACHE_STREAM_INTERVAL = max(
    0.1, float(os.getenv("LAWNBERY_CAMERA_CACHE_STREAM_INTERVAL", "0.2"))
)


@router.get("/stream")
async def camera_stream(system_manager=Depends(get_system_manager)) -> StreamingResponse:
    """Get live camera stream as MJPEG."""

    try:
        hardware_interface = getattr(system_manager, "hardware_interface", None)
        if not hardware_interface:
            logger.warning("Hardware interface not available, streaming from cache")
            return _cached_stream()

        async def generate_stream():
            frame_count = 0
            last_cache_mtime = get_cache_mtime()
            cached_frame: Optional[bytes] = None

            try:
                while True:
                    try:
                        frame = await hardware_interface.get_camera_frame()
                        if frame and frame.data:
                            cached_frame = frame.data
                            yield _wrap_mjpeg_frame(frame.data)
                            frame_count += 1
                        else:
                            cache_mtime = get_cache_mtime()
                            if cache_mtime and cache_mtime != last_cache_mtime:
                                cached = await load_cached_frame()
                                if cached:
                                    cached_frame, _ = cached
                                    last_cache_mtime = cache_mtime

                            if cached_frame:
                                yield _wrap_mjpeg_frame(cached_frame)
                            else:
                                placeholder = _generate_placeholder_frame(
                                    f"Waiting for camera... ({frame_count})"
                                )
                                yield _wrap_mjpeg_frame(placeholder)

                        await asyncio.sleep(1 / 30)

                    except Exception as exc:  # pragma: no cover - best effort to keep stream alive
                        logger.error(f"Stream frame error: {exc}")
                        error_frame = _generate_error_frame(f"Frame error: {str(exc)[:30]}")
                        yield _wrap_mjpeg_frame(error_frame)
                        await asyncio.sleep(1)

            except Exception as exc:  # pragma: no cover
                logger.error(f"Stream generation error: {exc}")
                final_error = _generate_error_frame("Stream terminated")
                yield _wrap_mjpeg_frame(final_error)

        return StreamingResponse(
            generate_stream(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "X-Accel-Buffering": "no",
            },
        )

    except Exception as exc:
        logger.error(f"Error setting up camera stream: {exc}")
        return _cached_stream()


@router.get("/frame")
async def get_camera_frame(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Return a single camera frame as base64 encoded JPEG."""

    try:
        hardware_interface = getattr(system_manager, "hardware_interface", None)
        if hardware_interface:
            frame = await hardware_interface.get_camera_frame()
            if frame and frame.data:
                frame_b64 = base64.b64encode(frame.data).decode("utf-8")
                return {
                    "success": True,
                    "message": "Frame captured successfully",
                    "data": {
                        "frame_id": frame.frame_id,
                        "timestamp": frame.timestamp.isoformat(),
                        "width": frame.width,
                        "height": frame.height,
                        "format": frame.format,
                        "data": frame_b64,
                        "source": frame.metadata.get("source", "live") if frame.metadata else "live",
                    },
                }

        cached_payload = await _cached_frame_payload()
        if cached_payload:
            return cached_payload

        return {
            "success": False,
            "message": "No camera frame available",
            "data": None,
        }

    except Exception as exc:
        logger.error(f"Error getting camera frame: {exc}")
        return {
            "success": False,
            "message": f"Camera frame error: {str(exc)}",
            "data": None,
        }


@router.get("/status")
async def get_camera_status(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Return camera system status including cached frame details."""

    try:
        hardware_interface = getattr(system_manager, "hardware_interface", None)
        if not hardware_interface:
            return await _cached_status_payload("Hardware interface not initialized")

        camera_manager = getattr(hardware_interface, "camera_manager", None)
        if not camera_manager:
            return await _cached_status_payload("Camera manager not available")

        frame = await hardware_interface.get_camera_frame()
        if frame and frame.data:
            return {
                "success": True,
                "data": {
                    "available": True,
                    "capturing": getattr(camera_manager, "_capturing", False),
                    "device_path": getattr(camera_manager, "device_path", "/dev/video0"),
                    "buffer_size": getattr(camera_manager, "_buffer_size", 0),
                    "last_frame": {
                        "available": True,
                        "frame_id": frame.frame_id,
                        "timestamp": frame.timestamp.isoformat(),
                        "resolution": f"{frame.width}x{frame.height}",
                        "format": frame.format,
                        "source": frame.metadata.get("source", "live") if frame.metadata else "live",
                    },
                },
            }

        cached_status = await _cached_status_payload("Serving cached camera frame")
        cached_status["data"].update(
            {
                "capturing": getattr(camera_manager, "_capturing", False),
                "device_path": getattr(camera_manager, "device_path", "/dev/video0"),
                "buffer_size": getattr(camera_manager, "_buffer_size", 0),
            }
        )
        return cached_status

    except Exception as exc:
        logger.error(f"Error getting camera status: {exc}")
        return {
            "success": False,
            "message": f"Camera status error: {str(exc)}",
            "data": {
                "available": False,
                "capturing": False,
                "error": str(exc),
            },
        }


def _wrap_mjpeg_frame(frame_bytes: bytes) -> bytes:
    return b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"


async def _cached_frame_payload() -> Optional[Dict[str, Any]]:
    cached = await load_cached_frame()
    if not cached:
        return None

    frame_bytes, metadata = cached
    frame_b64 = base64.b64encode(frame_bytes).decode("utf-8")

    return {
        "success": True,
        "message": "Cached frame served",
        "data": {
            "frame_id": metadata.get("frame_id"),
            "timestamp": metadata.get("timestamp"),
            "width": metadata.get("width"),
            "height": metadata.get("height"),
            "format": metadata.get("format", "jpeg"),
            "data": frame_b64,
            "source": "cache",
        },
    }


async def _cached_status_payload(message: str) -> Dict[str, Any]:
    cached = await load_cached_frame()
    metadata: Dict[str, Any] = cached[1] if cached else {}
    resolution = None
    if metadata.get("width") and metadata.get("height"):
        resolution = f"{metadata['width']}x{metadata['height']}"

    return {
        "success": True,
        "data": {
            "available": cached is not None,
            "capturing": False,
            "message": message,
            "device_path": metadata.get("device_path", str(CACHE_PATH)),
            "buffer_size": None,
            "last_frame": {
                "available": cached is not None,
                "frame_id": metadata.get("frame_id"),
                "timestamp": metadata.get("timestamp"),
                "resolution": resolution,
                "format": metadata.get("format", "jpeg"),
                "source": "cache" if cached else None,
            },
        },
    }


def _cached_stream() -> StreamingResponse:
    async def generate_cached_stream():
        last_mtime = None
        last_frame: Optional[bytes] = None

        while True:
            try:
                cache_mtime = get_cache_mtime()
                if cache_mtime and cache_mtime != last_mtime:
                    cached = await load_cached_frame()
                    if cached:
                        last_frame, _ = cached
                        last_mtime = cache_mtime

                if last_frame:
                    yield _wrap_mjpeg_frame(last_frame)
                else:
                    placeholder = _generate_placeholder_frame("Waiting for cached camera")
                    yield _wrap_mjpeg_frame(placeholder)

                await asyncio.sleep(_CACHE_STREAM_INTERVAL)

            except Exception as exc:  # pragma: no cover - logging only
                logger.error(f"Cached stream error: {exc}")
                error_frame = _generate_error_frame("Cache stream error")
                yield _wrap_mjpeg_frame(error_frame)
                await asyncio.sleep(1.0)

    return StreamingResponse(
        generate_cached_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",
        },
    )


# --- Placeholder helpers retained for compatibility ---


def _placeholder_stream() -> StreamingResponse:
    """Generate a placeholder stream when camera system is not available"""

    async def generate_placeholder():
        frame_count = 0
        try:
            while True:
                frame = _generate_placeholder_frame(f"Camera initializing... ({frame_count})")
                yield _wrap_mjpeg_frame(frame)
                frame_count += 1
                await asyncio.sleep(1 / 5)  # 5 FPS placeholder
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception as exc:  # pragma: no cover
            logger.error(f"Placeholder stream error: {exc}")

    return StreamingResponse(
        generate_placeholder(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


def _generate_placeholder_frame(message: str = "Camera Not Available") -> bytes:
    """Generate a placeholder frame when camera is not available"""
    try:
        if cv2 is None or np is None:
            raise RuntimeError("OpenCV or NumPy not available")

        height, width = 480, 640
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:] = (64, 64, 64)

        cv2.putText(
            frame,
            message,
            (width // 2 - 120, height // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (255, 255, 255),
            2,
        )
        cv2.putText(
            frame,
            "LawnBerryPi",
            (width // 2 - 60, height // 2 + 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2,
        )

        _, buffer = cv2.imencode(".jpg", frame)
        return buffer.tobytes()

    except Exception:
        # Minimal JPEG placeholder
        return (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06"
            b"\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f"
            b"\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \\",#\x1c\x1c(7),01444\x1f'9=82<.342"
            b"\xff\xc0\x00\x11\x08\x01\xe0\x02\x80\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4"
            b"\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08"
            b"\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9"
        )


def _generate_error_frame(error_message: str) -> bytes:
    """Generate an error frame with message"""
    try:
        if cv2 is None or np is None:
            raise RuntimeError("OpenCV or NumPy not available")

        height, width = 480, 640
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:] = (40, 40, 80)

        cv2.putText(
            frame,
            "Camera Error",
            (width // 2 - 80, height // 2 - 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (255, 255, 255),
            2,
        )

        if len(error_message) > 40:
            error_message = error_message[:37] + "..."

        cv2.putText(
            frame,
            error_message,
            (20, height // 2 + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 200, 200),
            1,
        )

        _, buffer = cv2.imencode(".jpg", frame)
        return buffer.tobytes()

    except Exception:
        return _generate_placeholder_frame()
