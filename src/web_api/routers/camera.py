"""
Camera streaming API endpoints used by the web UI.
This router pulls frames from the shared HardwareInterface stored on app.state.
"""

import asyncio
import logging
from typing import Dict, Any
from datetime import datetime
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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/camera", tags=["camera"])


@router.get("/stream")
async def camera_stream(system_manager=Depends(get_system_manager)) -> StreamingResponse:
    """Get live camera stream as MJPEG"""
    try:
        # Get hardware interface (exposed in app.state)
        hardware_interface = getattr(system_manager, 'hardware_interface', None)
        if not hardware_interface:
            logger.warning("Hardware interface not available, using placeholder stream")
            return _placeholder_stream()
        
        async def generate_stream():
            """Generate MJPEG stream from camera frames"""
            frame_count = 0
            try:
                while True:
                    try:
                        # Get latest camera frame (already JPEG bytes)
                        frame = await hardware_interface.get_camera_frame()
                        if frame and frame.data:
                            # Frame is already in JPEG format from CameraManager
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + frame.data + b'\r\n')
                            frame_count += 1
                        else:
                            # Generate a placeholder frame if camera not available
                            placeholder = _generate_placeholder_frame(f"Waiting for camera... ({frame_count})")
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + placeholder + b'\r\n')
                        
                        await asyncio.sleep(1/30)  # 30 FPS
                        
                    except Exception as e:
                        logger.error(f"Stream frame error: {e}")
                        # Send error frame but continue streaming
                        error_frame = _generate_error_frame(f"Frame error: {str(e)[:30]}")
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + error_frame + b'\r\n')
                        await asyncio.sleep(1)  # Wait longer on error
                        
            except Exception as e:
                logger.error(f"Stream generation error: {e}")
                # Send final error frame
                final_error = _generate_error_frame("Stream terminated")
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + final_error + b'\r\n')
        
        return StreamingResponse(
            generate_stream(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
        
    except Exception as e:
        logger.error(f"Error setting up camera stream: {e}")
        return _placeholder_stream()


@router.get("/frame")
async def get_camera_frame(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get single camera frame as base64"""
    try:
        hardware_interface = getattr(system_manager, 'hardware_interface', None)
        if not hardware_interface:
            return {
                "success": False,
                "message": "Hardware interface not available",
                "data": None
            }
        
        frame = await hardware_interface.get_camera_frame()
        if not frame:
            return {
                "success": False,
                "message": "No camera frame available",
                "data": None
            }
        
        import base64
        frame_b64 = base64.b64encode(frame.data).decode('utf-8')
        
        return {
            "success": True,
            "message": "Frame captured successfully",
            "data": {
                "frame_id": frame.frame_id,
                "timestamp": frame.timestamp.isoformat(),
                "width": frame.width,
                "height": frame.height,
                "format": frame.format,
                "data": frame_b64
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting camera frame: {e}")
        return {
            "success": False,
            "message": f"Camera frame error: {str(e)}",
            "data": None
        }


@router.get("/status")
async def get_camera_status(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get camera system status"""
    try:
        hardware_interface = getattr(system_manager, 'hardware_interface', None)
        if not hardware_interface:
            return {
                "success": True,
                "data": {
                    "available": False,
                    "capturing": False,
                    "message": "Hardware interface not initialized",
                    "error": "System starting up"
                }
            }
        
        # Get camera manager status
        camera_manager = getattr(hardware_interface, 'camera_manager', None)
        if not camera_manager:
            return {
                "success": True,
                "data": {
                    "available": False,
                    "capturing": False,
                    "message": "Camera manager not available",
                    "device_path": "unknown"
                }
            }
        
        # Test camera functionality
        frame = await hardware_interface.get_camera_frame()
        
        return {
            "success": True,
            "data": {
                "available": True,
                "capturing": getattr(camera_manager, '_capturing', False),
                "device_path": getattr(camera_manager, 'device_path', '/dev/video0'),
                "buffer_size": getattr(camera_manager, '_buffer_size', 0),
                "last_frame": {
                    "available": frame is not None,
                    "frame_id": frame.frame_id if frame else None,
                    "timestamp": frame.timestamp.isoformat() if frame else None,
                    "resolution": f"{frame.width}x{frame.height}" if frame else None,
                    "format": frame.format if frame else None
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting camera status: {e}")
        return {
            "success": False,
            "message": f"Camera status error: {str(e)}",
            "data": {
                "available": False,
                "capturing": False,
                "error": str(e)
            }
        }


def _placeholder_stream() -> StreamingResponse:
    """Generate a placeholder stream when camera system is not available"""
    async def generate_placeholder():
        frame_count = 0
        while True:
            frame_count += 1
            placeholder = _generate_placeholder_frame(f"Camera System Loading... ({frame_count})")
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + placeholder + b'\r\n')
            await asyncio.sleep(1)  # 1 FPS for placeholder
    
    return StreamingResponse(
        generate_placeholder(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


def _generate_placeholder_frame(message: str = "Camera Not Available") -> bytes:
    """Generate a placeholder frame when camera is not available. Falls back to tiny JPEG if deps missing."""
    if not (cv2 and np):
        return b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x01\xe0\x02\x80\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9'
    try:  # pragma: no cover
        height, width = 480, 640
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        for y in range(height):
            intensity = int(64 + 32 * np.sin(y * 0.02))
            frame[y, :] = (intensity, intensity//2, intensity//3)
        cv2.putText(frame, "LawnBerryPi Camera", (40, height//2 - 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(frame, message[:40], (40, height//2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        timestamp = datetime.now().strftime("%H:%M:%S")
        cv2.putText(frame, timestamp, (width - 140, height - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 255, 150), 1)
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buffer.tobytes()
    except Exception:
        return b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x01\xe0\x02\x80\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9'


def _generate_error_frame(error_message: str) -> bytes:
    """Generate an error frame with message"""
    try:
        height, width = 480, 640
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:] = (20, 20, 60)  # Dark blue/red background
        
        # Add error text
        cv2.putText(frame, "Camera Error", (width//2 - 80, height//2 - 40), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (100, 100, 255), 2)
        
        # Truncate long error messages
        if len(error_message) > 50:
            error_message = error_message[:47] + "..."
            
        cv2.putText(frame, error_message, (20, height//2 + 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 255), 1)
        
        # Add timestamp
        timestamp = datetime.now().strftime("%H:%M:%S")
        cv2.putText(frame, timestamp, (width - 100, height - 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 200), 1)
        
        # Encode as JPEG
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buffer.tobytes()
        
    except Exception:
        # Return placeholder on error
        return _generate_placeholder_frame("Error generating error frame")
