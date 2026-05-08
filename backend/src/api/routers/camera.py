import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from ...services.camera_stream_service import camera_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/camera/status")
async def get_camera_status():
    """Get camera service status."""
    try:
        stats = await camera_service.get_stream_statistics()
        last_frame_time = getattr(camera_service.stream, "last_frame_time", None)
        mode = getattr(camera_service.stream, "mode", None)
        client_count = getattr(camera_service.stream, "client_count", 0)
        is_active = bool(getattr(camera_service.stream, "is_active", False))
        return {
            "initialized": camera_service.running,  # Use 'running' instead of 'initialized'
            "streaming": is_active,
            "active": is_active,
            "mode": str(
                getattr(
                    mode, "value", mode or ("simulation" if camera_service.sim_mode else "offline")
                )
            ),
            "sim_mode": camera_service.sim_mode,
            "client_count": client_count,
            "last_frame_time": last_frame_time.isoformat()
            if hasattr(last_frame_time, "isoformat")
            else last_frame_time,
            "fps": getattr(stats, "current_fps", getattr(stats, "fps", 0)),
            "statistics": {
                "frames_captured": getattr(stats, "frames_captured", 0),
                "frames_processed": getattr(stats, "frames_processed", 0),
                "fps": getattr(stats, "current_fps", getattr(stats, "fps", 0)),
                "average_fps": getattr(stats, "average_fps", 0),
            }
            if stats
            else {},
        }
    except Exception as e:
        logger.error(f"Failed to get camera status: {e}")
        return {
            "initialized": False,
            "streaming": False,
            "active": False,
            "mode": "offline",
            "sim_mode": True,
            "client_count": 0,
            "last_frame_time": None,
            "statistics": {},
        }


@router.post("/camera/start")
async def start_camera(payload: dict | None = None):
    """Start camera streaming."""
    try:
        if not camera_service.running:
            await camera_service.initialize()

        if not camera_service.stream.is_active:
            await camera_service.start_streaming()

        return {"status": "started", "streaming": camera_service.stream.is_active}
    except Exception as e:
        logger.error(f"Failed to start camera: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/camera/stop")
async def stop_camera(payload: dict | None = None):
    """Stop camera streaming."""
    try:
        if camera_service.stream.is_active:
            camera_service.stop_streaming()
        return {"status": "stopped", "streaming": camera_service.stream.is_active}
    except Exception as e:
        logger.error(f"Failed to stop camera: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/camera/frame")
async def get_current_frame():
    """Get the most recent camera frame as JPEG."""
    try:
        frame = await camera_service.get_current_frame()
        if frame is None:
            raise HTTPException(status_code=404, detail="No frame available")

        frame_bytes = frame.get_frame_data() if hasattr(frame, "get_frame_data") else None
        if not frame_bytes:
            raise HTTPException(status_code=404, detail="No frame bytes available")

        return Response(
            content=frame_bytes,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get current frame: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


_MJPEG_TARGET_FPS = 5
_MJPEG_INTERVAL = 1.0 / _MJPEG_TARGET_FPS


@router.get("/camera/stream.mjpeg")
async def stream_mjpeg(
    request: Request,
    client: str | None = Query(None),
    session_id: str | None = Query(None),
    ts: str | None = Query(None),
):
    """Stream camera frames as Motion JPEG."""

    async def generate_mjpeg():
        """Generate MJPEG stream at a fixed target rate.

        Uses timestamp-based pacing so the loop never drifts above the target
        FPS regardless of how long frame retrieval takes.  Client disconnection
        is detected via request.is_disconnected() so the generator exits
        promptly instead of leaking until the next write raises an OSError.
        """
        next_tick = time.monotonic()

        while True:
            if await request.is_disconnected():
                break

            frame = await camera_service.get_current_frame()
            if frame is not None:
                frame_bytes = frame.get_frame_data() if hasattr(frame, "get_frame_data") else None
                if frame_bytes:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        + f"Content-Length: {len(frame_bytes)}\r\n\r\n".encode()
                        + frame_bytes
                        + b"\r\n"
                    )

            # Pace to target FPS; skip tick if we're already behind so the
            # generator never queues up a backlog of work.
            next_tick += _MJPEG_INTERVAL
            remaining = next_tick - time.monotonic()
            if remaining > 0:
                await asyncio.sleep(remaining)
            else:
                # Already behind; reset clock and yield control briefly.
                next_tick = time.monotonic()
                await asyncio.sleep(0)

    try:
        if not camera_service.running:
            await camera_service.initialize()
        if not getattr(camera_service.stream, "is_active", False):
            await camera_service.start_streaming()
        return StreamingResponse(
            generate_mjpeg(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        logger.error(f"Failed to start MJPEG stream: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
