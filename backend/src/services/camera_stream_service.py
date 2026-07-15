"""
Camera Stream Service for LawnBerry Pi v2
Manages camera capture, streaming, and IPC communication
"""

import asyncio
import io
import json
import logging
import os
import signal
import stat
import threading
import time
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from ..core.observability import observability
from ..models.ai_processing import InferenceResult
from ..models.camera_stream import (
    CameraFrame,
    CameraMode,
    CameraStream,
    FrameFormat,
    FrameMetadata,
    StreamQuality,
    StreamStatistics,
)

# Try to import camera libraries with fallbacks for SIM_MODE

logger = observability.get_logger(__name__)

try:
    import cv2

    OPENCV_AVAILABLE = True
except Exception as exc:  # catch ABI mismatches as well
    OPENCV_AVAILABLE = False
    logger.warning(
        "OpenCV unavailable; camera service using simulation mode",
        extra={"library": "opencv", "error": str(exc)},
    )
    if "numpy" in str(exc).lower():
        logger.info(
            "OpenCV import failed due to numpy ABI mismatch",
            extra={"hint": "ensure numpy < 2.0 or rebuild OpenCV against installed version"},
        )

try:
    from picamera2 import Picamera2

    PICAMERA_AVAILABLE = True
except Exception as exc:
    Picamera2 = None  # Make available for test monkeypatching
    PICAMERA_AVAILABLE = False
    logger.warning(
        "PiCamera2 unavailable; falling back to OpenCV or simulation",
        extra={"library": "picamera2", "error": str(exc)},
    )


class AIFrameProcessor(Protocol):
    """Callable contract for exact-frame AI inference."""

    def __call__(
        self,
        image_bytes: bytes,
        *,
        frame_id: str,
    ) -> Awaitable[InferenceResult | None]: ...


class CameraStreamService:
    """
    Camera stream service with IPC support for multi-process architecture.
    Handles camera capture, frame processing, and client management.
    """

    def __init__(self, sim_mode: bool = False):
        self.sim_mode = sim_mode or os.getenv("SIM_MODE", "0") == "1"
        self.stream = CameraStream()
        self.clients: set[asyncio.StreamWriter] = set()
        configured_socket = os.getenv("LAWNBERRY_CAMERA_SOCKET")
        self.socket_path = configured_socket or (
            "/tmp/lawnberry-camera.sock"
            if self.sim_mode
            else "/run/lawnberry/camera.sock"
        )
        self.stream.service_endpoint = f"unix://{self.socket_path}"
        self._frame_clients: set[asyncio.StreamWriter] = set()
        self.frame_callbacks: list[Callable[[CameraFrame], None]] = []

        # Threading for camera capture
        self.capture_thread: threading.Thread | None = None
        self.capture_active = False
        self.frame_queue: asyncio.Queue[CameraFrame] | None = None
        self._frame_processing_task: asyncio.Task[None] | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self._last_queue_warning = 0.0

        # AI is injected from lifespan to keep camera ownership independent of
        # AIService and avoid a service import cycle. Sampling runs inside the
        # single latest-frame consumer; no task is created per frame.
        self._ai_processor: AIFrameProcessor | None = None
        self._ai_inference_task: asyncio.Task[InferenceResult | None] | None = None
        self._last_ai_inference_monotonic: float | None = None
        self._last_ai_warning_monotonic = float("-inf")
        self._monotonic: Callable[[], float] = time.monotonic
        try:
            ai_fps = float(os.getenv("AI_CAMERA_INFERENCE_FPS", "1.0"))
        except (TypeError, ValueError):
            ai_fps = 1.0
        self._ai_inference_fps = max(0.1, min(ai_fps, 5.0))
        self._ai_inference_interval_seconds = 1.0 / self._ai_inference_fps
        try:
            ai_timeout = float(os.getenv("AI_CAMERA_INFERENCE_TIMEOUT_SECONDS", "0.5"))
        except (TypeError, ValueError):
            ai_timeout = 0.5
        self._ai_inference_timeout_seconds = max(0.05, min(ai_timeout, 5.0))

        # IPC server
        self.ipc_server: asyncio.Server | None = None
        self.running = False

        # Camera backend
        self.camera = None
        self.executor = ThreadPoolExecutor(max_workers=2)
        self._executor_shutdown = False
        self.hardware_available = False

        # Frame storage
        self.storage_dir = Path("data/camera")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        try:
            timeout_raw = float(os.getenv("CAMERA_STREAM_CLIENT_TIMEOUT", "0.25"))
        except ValueError:
            timeout_raw = 0.25
        self._client_drain_timeout = max(0.05, min(timeout_raw, 5.0))
        self._enqueue_timeout = 1.0

    async def initialize(self) -> bool:
        """Initialize camera service and IPC."""
        try:
            logger.info(f"Initializing camera service (SIM_MODE={self.sim_mode})")
            self.loop = asyncio.get_running_loop()
            if self._executor_shutdown:
                self.executor = ThreadPoolExecutor(max_workers=2)
                self._executor_shutdown = False

            # Initialize camera backend
            if not self.sim_mode:
                success = await self._initialize_camera()
                if not success:
                    logger.warning("Camera initialization failed; enabling simulation fallback")
                    self.sim_mode = True
                    self.stream.capabilities.sensor_type = "Simulated Camera"

            # Set up IPC socket
            await self._setup_ipc_server()

            # Start with OFFLINE; start_streaming() will flip to STREAMING when appropriate
            self.stream.mode = CameraMode.OFFLINE
            self.running = True

            logger.info("Camera service initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Camera service initialization failed: {e}")
            return False

    async def _initialize_camera(self) -> bool:
        """Initialize camera hardware.

        All blocking libcamera/V4L2 calls are offloaded to a thread-pool executor so they
        cannot stall the asyncio event loop. A hard 15-second timeout ensures startup never
        hangs indefinitely even if the camera device is unresponsive.
        """
        try:
            loop = asyncio.get_running_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, self._initialize_camera_sync),
                timeout=15.0,
            )
        except TimeoutError:
            logger.error(
                "Camera hardware initialization timed out after 15 s; falling back to sim mode"
            )
            self.hardware_available = False
            return False
        except Exception as exc:
            logger.error("Camera initialization error: %s", exc)
            self.hardware_available = False
            return False

    def _initialize_camera_sync(self) -> bool:
        """Synchronous camera setup — runs in a thread-pool executor (never call from event loop)."""
        try:
            if PICAMERA_AVAILABLE:
                try:
                    logger.info("Initializing Pi Camera...")
                    self.camera = Picamera2()

                    # Configure camera.
                    # BGR888 delivers data in OpenCV-native BGR byte order so no
                    # colour-space conversion is needed before cv2.imencode.
                    config = self.camera.create_video_configuration(
                        main={
                            "format": "BGR888",
                            "size": (
                                self.stream.configuration.width,
                                self.stream.configuration.height,
                            ),
                        }
                    )
                    # 3 buffers: enough to avoid stalls while keeping pipeline
                    # latency at one frame.
                    try:
                        config["buffer_count"] = 3
                    except Exception:
                        pass
                    self.camera.configure(config)
                    self.camera.start()

                    # Apply desired frame rate constraints where supported
                    fps = self.stream.configuration.framerate
                    if fps > 0:
                        frame_duration_us = int(1_000_000 / fps)
                        try:
                            self.camera.set_controls(
                                {"FrameDurationLimits": (frame_duration_us, frame_duration_us)}
                            )
                        except Exception as exc:
                            logger.debug(
                                "Unable to enforce PiCamera2 frame duration limits: %s", exc
                            )

                    # Use the full sensor area so the output is not cropped/zoomed.
                    # Without this, Picamera2 defaults to a centre-crop when the
                    # requested resolution is smaller than the sensor's native size.
                    try:
                        max_crop = self.camera.camera_properties.get("ScalerCropMaximum")
                        if max_crop:
                            self.camera.set_controls({"ScalerCrop": max_crop})
                    except Exception as exc:
                        logger.debug("Unable to set ScalerCrop for full FOV: %s", exc)

                    # Update capabilities from camera
                    self.stream.capabilities.sensor_type = "Pi Camera v3"
                    self.stream.device_path = "picamera2"
                    self.hardware_available = True
                    return True
                except Exception as exc:
                    logger.error(
                        "PiCamera2 initialization failed, falling back to OpenCV: %s",
                        exc,
                    )
                    try:
                        if self.camera:
                            self.camera.close()
                    except Exception:
                        pass
                    self.camera = None

            if OPENCV_AVAILABLE:
                logger.info("Initializing OpenCV camera...")

                device_info = self._discover_opencv_device()
                if not device_info:
                    logger.error("Unable to locate a usable /dev/video* node")
                    return False

                device_path, friendly_name = device_info
                logger.info("Attempting to open camera device %s", device_path)
                api_preference = getattr(cv2, "CAP_V4L2", getattr(cv2, "CAP_ANY", 0))
                self.camera = cv2.VideoCapture(device_path, api_preference)

                if not self.camera or not self.camera.isOpened():
                    logger.error("Failed to open camera device %s with OpenCV", device_path)
                    return False

                # Set camera properties; best-effort because some drivers reject the request.
                width = self.stream.configuration.width
                height = self.stream.configuration.height
                fps = self.stream.configuration.framerate
                for prop, value in (
                    (cv2.CAP_PROP_FRAME_WIDTH, width),
                    (cv2.CAP_PROP_FRAME_HEIGHT, height),
                    (cv2.CAP_PROP_FPS, fps),
                ):
                    if not self.camera.set(prop, value):
                        logger.debug(
                            "Camera device %s rejected property %s=%s",
                            device_path,
                            prop,
                            value,
                        )

                # Perform a lightweight probe to ensure frames are readable.
                ok, frame = self.camera.read()
                if not ok or frame is None or frame.size == 0:
                    logger.error(
                        "Camera device %s opened but failed to deliver a probe frame",
                        device_path,
                    )
                    self.camera.release()
                    self.camera = None
                    return False

                logger.info(
                    "OpenCV camera %s ready (%sx%s @ %.2ffps)%s",
                    device_path,
                    frame.shape[1],
                    frame.shape[0],
                    fps,
                    f" [{friendly_name}]" if friendly_name else "",
                )
                self.stream.device_path = device_path
                if friendly_name:
                    self.stream.capabilities.sensor_type = friendly_name
                else:
                    self.stream.capabilities.sensor_type = "V4L2 Camera"
                self.hardware_available = True
                return True

            logger.warning("No camera libraries available")
            self.hardware_available = False
            return False

        except Exception as e:
            logger.error(f"Camera initialization error: {e}")
            self.hardware_available = False
            return False

    async def _setup_ipc_server(self):
        """Set up Unix socket IPC server."""
        try:
            Path(self.socket_path).parent.mkdir(parents=True, exist_ok=True)
            # Clean up existing socket
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)

            # Create IPC server
            self.ipc_server = await asyncio.start_unix_server(
                self._handle_client_connection, path=self.socket_path
            )

            # Set socket permissions
            os.chmod(self.socket_path, 0o666)

            logger.info(f"IPC server listening on {self.socket_path}")

        except Exception as e:
            logger.error(f"Failed to setup IPC server: {e}")
            raise

    async def _handle_client_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Handle new client connection."""
        client_addr = writer.get_extra_info("sockname")
        logger.info(f"New camera client connected: {client_addr}")

        self.clients.add(writer)
        self.stream.client_count = len(self.clients)

        try:
            while True:
                # Read client message
                data = await reader.readline()
                if not data:
                    break

                try:
                    message = json.loads(data.decode())
                    if message.get("command") == "unsubscribe_frames":
                        self._frame_clients.discard(writer)
                    response = await self._handle_client_message(message)

                    # Send response
                    response_data = json.dumps(response).encode() + b"\n"
                    writer.write(response_data)
                    await writer.drain()
                    if message.get("command") == "subscribe_frames" and response.get(
                        "status"
                    ) == "success":
                        # Subscribe only after the acknowledgement is flushed,
                        # so a frame can never precede the command response.
                        self._frame_clients.add(writer)

                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from client: {data}")
                except Exception as e:
                    logger.error(f"Error handling client message: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Client connection error: {e}")
        finally:
            self._frame_clients.discard(writer)
            self.clients.discard(writer)
            self.stream.client_count = len(self.clients)
            writer.close()
            await writer.wait_closed()
            logger.info(f"Camera client disconnected: {client_addr}")

    async def _handle_client_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle client message and return response."""
        command = message.get("command")

        if command == "get_status":
            status_payload = self.stream.model_dump(
                mode="json",
                exclude={"current_frame"},
            )
            # Service ownership state is not part of CameraStream itself, but
            # consumers must receive it with every status snapshot. In
            # particular, a live-mode owner that falls back after hardware
            # initialization fails must never look like a hardware camera.
            status_payload.update(
                {
                    "sim_mode": self.sim_mode,
                    "hardware_available": self.hardware_available,
                }
            )
            return {
                "status": "success",
                "data": status_payload,
            }

        elif command == "get_frame":
            frame = await self.get_current_frame()
            if frame:
                return {"status": "success", "data": frame.model_dump(mode="json")}
            else:
                return {"status": "error", "error": "No frame available"}

        elif command == "configure":
            config_data = message.get("configuration", {})
            success = await self.update_configuration(config_data)
            return {
                "status": "success" if success else "error",
                "message": "Configuration updated" if success else "Configuration update failed",
            }

        elif command == "start_streaming":
            success = await self.start_streaming()
            return {
                "status": "success" if success else "error",
                "message": "Streaming started" if success else "Failed to start streaming",
            }

        elif command == "stop_streaming":
            await self.stop_streaming()
            return {"status": "success", "message": "Streaming stopped"}

        elif command == "subscribe_frames":
            return {"status": "success", "message": "Frame subscription enabled"}

        elif command == "unsubscribe_frames":
            return {"status": "success", "message": "Frame subscription disabled"}

        else:
            return {"status": "error", "error": f"Unknown command: {command}"}

    async def start_streaming(self) -> bool:
        """Start camera streaming."""
        try:
            if (not self.sim_mode) and (not self.hardware_available):
                logger.warning(
                    "Camera hardware unavailable and SIM disabled; not starting streaming"
                )
                self.stream.is_active = False
                self.stream.mode = CameraMode.OFFLINE
                return False
            if self.capture_active:
                logger.warning("Streaming already active")
                return True

            logger.info("Starting camera streaming...")

            if not self.loop or self.loop.is_closed():
                self.loop = asyncio.get_running_loop()

            # Single-slot queue: always deliver the freshest frame with no buffering lag.
            self._enqueue_timeout = 0.5
            if self.frame_queue is None:
                self.frame_queue = asyncio.Queue(maxsize=1)
            else:
                while not self.frame_queue.empty():
                    try:
                        self.frame_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

            # Start capture thread
            self.capture_active = True
            self.capture_thread = threading.Thread(target=self._capture_frames_thread, daemon=True)
            self.capture_thread.start()

            # Keep exactly one consumer across stop/start cycles.
            if self._frame_processing_task is None or self._frame_processing_task.done():
                self._frame_processing_task = asyncio.create_task(
                    self._process_frames(),
                    name="camera-frame-processing",
                )

            self.stream.is_active = True
            self.stream.mode = CameraMode.STREAMING

            logger.info("Camera streaming started successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to start streaming: {e}")
            self.stream.mode = CameraMode.ERROR
            self.stream.error_message = str(e)
            return False

    async def stop_streaming(self):
        """Stop camera streaming."""
        logger.info("Stopping camera streaming...")

        self.capture_active = False

        if self.capture_thread and self.capture_thread.is_alive():
            await asyncio.to_thread(self.capture_thread.join, 5.0)
        self.capture_thread = None

        self.stream.is_active = False
        self.stream.mode = CameraMode.OFFLINE

        logger.info("Camera streaming stopped")

    def _capture_frames_thread(self):
        """Camera capture thread (runs in separate thread)."""
        logger.info("Camera capture thread started")
        next_frame_time: float | None = None

        while self.capture_active:
            try:
                loop_start = time.perf_counter()

                if self.sim_mode:
                    # In simulation mode, generate frames; in real mode, never simulate
                    frame_payload = self._generate_simulated_frame()
                else:
                    frame_payload = self._capture_real_frame()

                if frame_payload:
                    frame_data, dimensions = frame_payload
                    frame = self._create_frame_object(frame_data, dimensions)
                    self._schedule_frame_enqueue(frame)

                # Control frame rate
                processing_elapsed = time.perf_counter() - loop_start
                target_fps = self.stream.configuration.framerate or 1.0
                target_fps = max(target_fps, 0.1)
                target_interval = 1.0 / target_fps

                if next_frame_time is None:
                    next_frame_time = loop_start + target_interval
                else:
                    next_frame_time += target_interval

                now = time.perf_counter()
                if next_frame_time < now:
                    next_frame_time = now
                sleep_time = next_frame_time - now

                if sleep_time > 0:
                    time.sleep(sleep_time)

                total_duration = time.perf_counter() - loop_start
                self.stream.update_statistics(
                    frame_duration_ms=total_duration * 1000.0,
                    processing_time_ms=processing_elapsed * 1000.0,
                )

            except Exception as e:
                logger.error(f"Frame capture error: {e}")
                self.stream.statistics.encoding_errors += 1
                time.sleep(0.1)  # Brief pause on error

        logger.info("Camera capture thread stopped")

    def _schedule_frame_enqueue(self, frame: CameraFrame) -> None:
        """Schedule a frame enqueue on the main event loop."""
        if not self.loop or self.loop.is_closed():
            return

        async def _enqueue_async() -> None:
            if not self.frame_queue:
                return
            # Drain any stale frames so the consumer always gets the latest capture.
            while not self.frame_queue.empty():
                try:
                    self.frame_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            try:
                self.frame_queue.put_nowait(frame)
            except asyncio.QueueFull:
                self.stream.statistics.frames_dropped += 1

        try:
            future = asyncio.run_coroutine_threadsafe(_enqueue_async(), self.loop)
            try:
                future.result(timeout=self._enqueue_timeout)
            except FuturesTimeoutError:
                self.stream.statistics.frames_dropped += 1
                self.stream.statistics.buffer_overruns += 1
                future.cancel()
                now = time.monotonic()
                if now - self._last_queue_warning > 5.0:
                    logger.warning(
                        "Frame enqueue stalled; dropping frame to keep stream responsive"
                    )
                    self._last_queue_warning = now
            except Exception as exc:
                self.stream.statistics.frames_dropped += 1
                future.cancel()
                now = time.monotonic()
                if now - self._last_queue_warning > 5.0:
                    logger.error("Frame enqueue failed: %s", exc)
                    self._last_queue_warning = now
        except RuntimeError:
            # Loop may be closing; drop frame silently
            pass

    def _resolve_jpeg_quality(self) -> int:
        """Determine JPEG quality based on configured stream quality."""
        quality_map = {
            StreamQuality.LOW: 60,
            StreamQuality.MEDIUM: 72,
            StreamQuality.HIGH: 85,
            StreamQuality.ULTRA: 92,
        }
        quality_key: Any = self.stream.configuration.quality
        if isinstance(quality_key, str):
            try:
                quality_key = StreamQuality(quality_key)
            except ValueError:
                quality_key = None
        return quality_map.get(quality_key, 80)

    def _encode_numpy_frame_to_jpeg(
        self, frame: Any, *, color_space: str | None = None
    ) -> bytes | None:
        """Encode a numpy frame to JPEG, respecting the declared colour space."""
        quality = self._resolve_jpeg_quality()

        space = (color_space or "").upper()
        if not space and hasattr(frame, "ndim"):
            try:
                if frame.ndim == 2:
                    space = "GRAY"
                elif frame.ndim >= 3 and frame.shape[2] == 4:
                    space = "RGBA"
                else:
                    space = "RGB"
            except Exception:
                space = "RGB"
        if not space:
            space = "RGB"

        if OPENCV_AVAILABLE:
            try:
                if space == "RGB":
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                elif space == "RGBA":
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
                elif space == "BGRA":
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                else:
                    frame_bgr = frame
                success, buffer = cv2.imencode(
                    ".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality]
                )
                if success:
                    return buffer.tobytes()
            except Exception as exc:
                logger.warning("OpenCV JPEG encode failed: %s", exc)

        try:
            from PIL import Image

            if space == "BGR":
                frame = frame[:, :, ::-1]
                mode = "RGB"
            elif space == "BGRA":
                frame = frame[:, :, [2, 1, 0, 3]]
                mode = "RGBA"
            elif space == "GRAY":
                mode = "L"
            elif space == "RGBA":
                mode = "RGBA"
            else:
                mode = "RGB"
            image = Image.fromarray(frame, mode=mode)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality)
            return buffer.getvalue()
        except Exception as exc:
            logger.error("Fallback JPEG encoding failed: %s", exc)
            return None

    def _capture_real_frame(self) -> tuple[bytes, tuple[int, int]] | None:
        """Capture frame from real camera."""
        try:
            if PICAMERA_AVAILABLE and isinstance(self.camera, Picamera2):
                frame = self.camera.capture_array("main")
                if frame is None:
                    return None

                height, width = frame.shape[:2]
                encoded = self._encode_numpy_frame_to_jpeg(frame, color_space="RGB")
                if encoded:
                    return encoded, (width, height)

                # Fallback to slower capture_file path if encoding failed
                buffer = io.BytesIO()
                self.camera.capture_file(buffer, format="jpeg")
                return buffer.getvalue(), (
                    self.stream.configuration.width,
                    self.stream.configuration.height,
                )

            elif OPENCV_AVAILABLE and isinstance(self.camera, cv2.VideoCapture):
                # Capture with OpenCV
                ret, frame = self.camera.read()

                if ret:
                    height, width = frame.shape[:2]
                    success, buffer = cv2.imencode(
                        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._resolve_jpeg_quality()]
                    )

                    if success:
                        return buffer.tobytes(), (width, height)

            return None

        except Exception as e:
            logger.error(f"Real frame capture error: {e}")
            return None

    def _discover_opencv_device(self) -> tuple[str, str | None] | None:
        """Identify a usable V4L2 device for OpenCV capture."""
        # Honor explicit request first.
        explicit = os.getenv("CAMERA_DEVICE")
        if explicit:
            path = explicit if explicit.startswith("/dev/") else f"/dev/{explicit}"
            if Path(path).exists():
                friendly = None
                try:
                    friendly = (
                        (Path("/sys/class/video4linux") / Path(path).name / "name")
                        .read_text()
                        .strip()
                    )
                except Exception:
                    pass
                return path, friendly
            logger.warning("CAMERA_DEVICE %s was provided but does not exist", explicit)

        video_devices = []
        try:
            video_devices = sorted(Path("/dev").glob("video*"))
        except Exception as exc:  # pragma: no cover - filesystem failure
            logger.error("Failed to enumerate /dev/video* nodes: %s", exc)
            return None

        # Prefer lower indices but keep deterministic ordering.
        sys_class = Path("/sys/class/video4linux")

        for device in video_devices:
            try:
                info = device.stat()
                if not stat.S_ISCHR(info.st_mode):
                    continue
            except FileNotFoundError:
                continue

            friendly = None
            try:
                sys_entry = sys_class / device.name / "name"
                sys_text = sys_entry.read_text().strip()
                friendly = sys_text
                sys_name = sys_text.lower()
                if any(token in sys_name for token in ("decoder", "stat", "metadata", "output")):
                    logger.debug("Skipping %s (sysfs reports %s)", device, sys_text)
                    continue
            except FileNotFoundError:
                pass
            except Exception as exc:  # pragma: no cover - sysfs read failure
                logger.debug("Unable to inspect sysfs name for %s: %s", device, exc)
                friendly = None

            return device.as_posix(), friendly

        return None

    def _generate_simulated_frame(self) -> tuple[bytes, tuple[int, int]]:
        """Generate simulated camera frame for testing."""
        try:
            # Create a simple test pattern
            import io

            from PIL import Image, ImageDraw, ImageFont

            # Create image
            width = self.stream.configuration.width
            height = self.stream.configuration.height
            image = Image.new("RGB", (width, height), color="green")

            # Add some text and graphics
            draw = ImageDraw.Draw(image)

            # Draw test pattern
            draw.rectangle([10, 10, width - 10, height - 10], outline="white", width=2)
            draw.line([0, 0, width, height], fill="white", width=2)
            draw.line([width, 0, 0, height], fill="white", width=2)

            # Add timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                font = ImageFont.load_default()
                draw.text((20, 20), "LawnBerry Pi Camera", font=font, fill="white")
                draw.text((20, 40), f"SIM MODE: {timestamp}", font=font, fill="yellow")
                draw.text(
                    (20, height - 60),
                    f"Frame: {self.stream.statistics.frames_captured}",
                    font=font,
                    fill="white",
                )
            except Exception:
                # Fallback if font not available
                pass

            # Convert to JPEG bytes
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=85)
            return buffer.getvalue(), (width, height)

        except Exception as e:
            logger.error(f"Simulated frame generation error: {e}")
            # Return minimal JPEG
            minimal = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9"
            return minimal, (1, 1)

    def _create_frame_object(
        self, frame_data: bytes, dimensions: tuple[int, int] | None = None
    ) -> CameraFrame:
        """Create CameraFrame object from raw frame data."""
        frame_id = f"frame_{self.stream.statistics.frames_captured:06d}"

        if dimensions:
            width, height = dimensions
        else:
            width = self.stream.configuration.width
            height = self.stream.configuration.height

        metadata = FrameMetadata(
            frame_id=frame_id,
            timestamp=datetime.now(UTC),
            sequence_number=self.stream.statistics.frames_captured,
            width=width,
            height=height,
            format=FrameFormat.JPEG,
            size_bytes=len(frame_data),
        )

        frame = CameraFrame(metadata=metadata)
        frame.set_frame_data(frame_data)

        return frame

    async def _process_frames(self):
        """Process captured frames (runs in async context)."""
        logger.info("Frame processing task started")

        while self.running:
            try:
                if not self.frame_queue:
                    await asyncio.sleep(0.05)
                    continue
                # Get frame from queue with timeout
                frame = await asyncio.wait_for(self.frame_queue.get(), timeout=1.0)

                # Update current frame
                self.stream.current_frame = frame
                self.stream.last_frame_time = frame.metadata.timestamp

                # Process frame
                await self._process_single_frame(frame)

                # Notify callbacks
                for callback in self.frame_callbacks:
                    try:
                        callback(frame)
                    except Exception as e:
                        logger.warning(f"Frame callback error: {e}")

                # Auto-save if enabled
                if (
                    self.stream.auto_save_frames
                    and frame.metadata.sequence_number
                    % (self.stream.configuration.framerate * self.stream.save_interval_seconds)
                    == 0
                ):
                    await self._save_frame_to_disk(frame)

            except TimeoutError:
                # No frame received, continue
                continue
            except Exception as e:
                logger.error(f"Frame processing error: {e}")

        logger.info("Frame processing task stopped")

    async def _process_single_frame(self, frame: CameraFrame):
        """Process a single frame."""
        try:
            # Mark as processed
            self.stream.statistics.frames_processed += 1

            # AI processing if enabled
            if self.stream.ai_processing_enabled:
                await self._process_frame_for_ai(frame)

            # Broadcast to connected clients
            await self._broadcast_frame_to_clients(frame)

        except Exception as e:
            logger.error(f"Single frame processing error: {e}")

    async def _process_frame_for_ai(self, frame: CameraFrame):
        """Run bounded inference for this exact frame when the cadence is due."""
        frame.processed_for_ai = False
        frame.ai_annotations = []

        processor = self._ai_processor
        if not self.stream.ai_processing_enabled or processor is None:
            return
        # A timed-out to_thread worker cannot be force-cancelled. Keep its
        # shielded task tracked and skip new samples until it really finishes.
        if self._ai_inference_task is not None:
            return

        now = self._monotonic()
        if (
            self._last_ai_inference_monotonic is not None
            and now - self._last_ai_inference_monotonic
            < self._ai_inference_interval_seconds
        ):
            return

        frame_bytes = frame.get_frame_data()
        if not frame_bytes:
            return

        # Count attempts, including failures/unavailable results, so a broken
        # model cannot turn the camera loop into an unbounded retry loop.
        self._last_ai_inference_monotonic = now
        inference_task = asyncio.create_task(
            processor(
                frame_bytes,
                frame_id=frame.metadata.frame_id,
            ),
            name=f"camera-ai-{frame.metadata.frame_id}",
        )
        self._ai_inference_task = inference_task
        try:
            result = await asyncio.wait_for(
                asyncio.shield(inference_task),
                timeout=self._ai_inference_timeout_seconds,
            )
        except TimeoutError:
            self._warn_ai_processing(
                "AI processing timed out after %.3fs for frame %s",
                self._ai_inference_timeout_seconds,
                frame.metadata.frame_id,
            )
            inference_task.add_done_callback(self._discard_late_ai_result)
            return
        except asyncio.CancelledError:
            inference_task.cancel()
            if self._ai_inference_task is inference_task:
                self._ai_inference_task = None
            raise
        except Exception as exc:
            if self._ai_inference_task is inference_task:
                self._ai_inference_task = None
            self._warn_ai_processing("AI processing error: %s", exc)
            return
        if self._ai_inference_task is inference_task:
            self._ai_inference_task = None

        if result is None:
            return
        if getattr(result, "input_frame_id", None) != frame.metadata.frame_id:
            self._warn_ai_processing(
                "AI result frame mismatch: expected %s, received %s",
                frame.metadata.frame_id,
                getattr(result, "input_frame_id", None),
            )
            return

        try:
            frame.ai_annotations = [self._annotation_from_ai_result(result)]
        except Exception as exc:
            self._warn_ai_processing("Invalid AI inference result: %s", exc)
            frame.ai_annotations = []
            return

        # A completed inference with zero detections is still a truthful
        # processed result. Skips, failures, and provenance mismatches stay false.
        frame.processed_for_ai = True

    def _discard_late_ai_result(
        self,
        task: asyncio.Task[InferenceResult | None],
    ) -> None:
        """Consume a timed-out result without attaching it to a newer frame."""
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._warn_ai_processing("Timed-out AI processing later failed: %s", exc)
        finally:
            if self._ai_inference_task is task:
                self._ai_inference_task = None

    def _annotation_from_ai_result(self, result: InferenceResult) -> dict[str, Any]:
        task = getattr(result.task, "value", result.task)
        objects = []
        for detected in result.detected_objects:
            bbox = detected.bounding_box
            objects.append(
                {
                    "id": detected.object_id,
                    "class": detected.class_name,
                    "confidence": detected.confidence,
                    "bbox": [bbox.x, bbox.y, bbox.width, bbox.height],
                    "distance_estimate_m": detected.distance_estimate,
                    "relative_bearing_degrees": detected.relative_bearing,
                    "tracking_id": detected.tracking_id,
                }
            )
        return {
            "type": task,
            "inference_id": result.inference_id,
            "model_name": result.model_name,
            "model_version": result.model_version,
            "processing_time_ms": result.total_time_ms,
            "objects": objects,
        }

    def _warn_ai_processing(self, message: str, *args: Any) -> None:
        now = self._monotonic()
        if now - self._last_ai_warning_monotonic < 5.0:
            return
        self._last_ai_warning_monotonic = now
        logger.warning(message, *args)

    async def _broadcast_frame_to_clients(self, frame: CameraFrame):
        """Broadcast frame to connected clients."""
        if not self._frame_clients:
            return

        try:
            # Create frame message
            message = {"type": "frame", "data": frame.model_dump(mode="json")}
            message_data = json.dumps(message).encode() + b"\n"

            # Send to all clients
            disconnected_clients = set()

            for client in list(self._frame_clients):
                try:
                    client.write(message_data)
                    await asyncio.wait_for(client.drain(), timeout=self._client_drain_timeout)
                    self.stream.statistics.bytes_transmitted += len(message_data)
                except TimeoutError:
                    logger.warning(
                        "Camera client drain exceeded %.2fs; disconnecting",
                        self._client_drain_timeout,
                    )
                    disconnected_clients.add(client)
                    self.stream.statistics.transmission_errors += 1
                except Exception as e:
                    logger.warning(f"Failed to send frame to client: {e}")
                    disconnected_clients.add(client)

            # Clean up disconnected clients
            for client in disconnected_clients:
                self._frame_clients.discard(client)
                self.clients.discard(client)
                self.stream.client_count = len(self.clients)
                client.close()
            if disconnected_clients:
                await asyncio.gather(
                    *(client.wait_closed() for client in disconnected_clients),
                    return_exceptions=True,
                )

        except Exception as e:
            logger.error(f"Frame broadcast error: {e}")
            self.stream.statistics.transmission_errors += 1

    async def _save_frame_to_disk(self, frame: CameraFrame):
        """Save frame to disk storage."""
        try:
            timestamp = frame.metadata.timestamp.strftime("%Y%m%d_%H%M%S")
            filename = f"frame_{timestamp}_{frame.metadata.frame_id}.jpg"
            file_path = self.storage_dir / filename

            frame_data = frame.get_frame_data()
            if frame_data:
                await asyncio.get_event_loop().run_in_executor(
                    self.executor, file_path.write_bytes, frame_data
                )

                frame.stored_to_disk = True
                frame.file_path = str(file_path)

                logger.debug(f"Frame saved to {file_path}")

        except Exception as e:
            logger.error(f"Failed to save frame to disk: {e}")

    async def get_current_frame(self) -> CameraFrame | None:
        """Get the most recent frame."""
        return self.stream.current_frame

    async def update_configuration(self, config_data: dict[str, Any]) -> bool:
        """Update camera configuration."""
        try:
            # Update configuration
            for key, value in config_data.items():
                if hasattr(self.stream.configuration, key):
                    setattr(self.stream.configuration, key, value)

            # Apply configuration to camera if active
            if not self.sim_mode and self.camera:
                await self._apply_camera_configuration()

            logger.info(f"Camera configuration updated: {config_data}")
            return True

        except Exception as e:
            logger.error(f"Failed to update configuration: {e}")
            return False

    async def _apply_camera_configuration(self):
        """Apply configuration to camera hardware."""
        try:
            if PICAMERA_AVAILABLE and isinstance(self.camera, Picamera2):
                # Reconfigure Pi Camera with video-friendly settings
                config = self.camera.create_video_configuration(
                    main={
                        "format": "BGR888",
                        "size": (
                            self.stream.configuration.width,
                            self.stream.configuration.height,
                        ),
                    }
                )
                try:
                    config["buffer_count"] = 3
                except Exception:
                    pass

                try:
                    self.camera.stop()
                except Exception:
                    pass
                self.camera.configure(config)
                self.camera.start()

                fps = self.stream.configuration.framerate
                if fps > 0:
                    frame_duration_us = int(1_000_000 / fps)
                    try:
                        self.camera.set_controls(
                            {"FrameDurationLimits": (frame_duration_us, frame_duration_us)}
                        )
                    except Exception as exc:
                        logger.debug("Unable to enforce PiCamera2 frame duration limits: %s", exc)

                try:
                    max_crop = self.camera.camera_properties.get("ScalerCropMaximum")
                    if max_crop:
                        self.camera.set_controls({"ScalerCrop": max_crop})
                except Exception as exc:
                    logger.debug("Unable to set ScalerCrop for full FOV: %s", exc)

            elif OPENCV_AVAILABLE and isinstance(self.camera, cv2.VideoCapture):
                # Update OpenCV camera properties
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.stream.configuration.width)
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.stream.configuration.height)
                self.camera.set(cv2.CAP_PROP_FPS, self.stream.configuration.framerate)

        except Exception as e:
            logger.error(f"Failed to apply camera configuration: {e}")
            raise

    def add_frame_callback(self, callback: Callable[[CameraFrame], None]):
        """Add callback for frame processing."""
        self.frame_callbacks.append(callback)

    def set_ai_processor(
        self,
        processor: AIFrameProcessor | None,
        *,
        max_fps: float | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        """Inject exact-frame inference without coupling camera to AIService."""
        self._ai_processor = processor
        if max_fps is not None:
            self._ai_inference_fps = max(0.1, min(float(max_fps), 5.0))
            self._ai_inference_interval_seconds = 1.0 / self._ai_inference_fps
        if timeout_seconds is not None:
            self._ai_inference_timeout_seconds = max(
                0.05,
                min(float(timeout_seconds), 5.0),
            )
        self._last_ai_inference_monotonic = None

    def remove_frame_callback(self, callback: Callable[[CameraFrame], None]):
        """Remove frame callback."""
        if callback in self.frame_callbacks:
            self.frame_callbacks.remove(callback)

    async def get_stream_statistics(self) -> StreamStatistics:
        """Get current streaming statistics."""
        return self.stream.statistics

    async def reset_statistics(self):
        """Reset streaming statistics."""
        self.stream.statistics = StreamStatistics()
        logger.info("Camera statistics reset")

    async def shutdown(self):
        """Shutdown camera service."""
        logger.info("Shutting down camera service...")

        self.running = False

        # Stop streaming
        await self.stop_streaming()

        if self._frame_processing_task is not None:
            try:
                await self._frame_processing_task
            except asyncio.CancelledError:
                pass
            self._frame_processing_task = None

        if self._ai_inference_task is not None:
            self._ai_inference_task.cancel()
            await asyncio.gather(self._ai_inference_task, return_exceptions=True)
            self._ai_inference_task = None

        # Close camera
        if not self.sim_mode and self.camera:
            try:
                if PICAMERA_AVAILABLE and isinstance(self.camera, Picamera2):
                    self.camera.stop()
                    self.camera.close()
                elif OPENCV_AVAILABLE and isinstance(self.camera, cv2.VideoCapture):
                    self.camera.release()
            except Exception as e:
                logger.error(f"Error closing camera: {e}")

        # Close IPC server
        if self.ipc_server:
            self.ipc_server.close()
            await self.ipc_server.wait_closed()
            self.ipc_server = None

        client_writers = list(self.clients)
        for writer in client_writers:
            writer.close()
        if client_writers:
            await asyncio.gather(
                *(writer.wait_closed() for writer in client_writers),
                return_exceptions=True,
            )
        self.clients.clear()
        self._frame_clients.clear()
        self.stream.client_count = 0

        # Clean up socket
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        # Shutdown executor
        if not self._executor_shutdown:
            await asyncio.to_thread(self.executor.shutdown, wait=True)
            self._executor_shutdown = True

        # asyncio.Queue and the cached loop belong to the loop that initialized
        # this owner. Full shutdown must discard them before a later service
        # reinitialize (including tests and supervised in-process restarts).
        self.frame_queue = None
        self.loop = None
        self._last_ai_inference_monotonic = None

        logger.info("Camera service shutdown complete")


# Global camera service instance
camera_service = CameraStreamService()


def _get_ai_service():
    """Resolve AI lazily so importing the camera owner stays lightweight."""
    from .ai_service import get_ai_service

    return get_ai_service()


async def _configure_camera_ai() -> None:
    """Wire exact-frame and latest-frame AI paths to this camera owner."""
    ai_service = _get_ai_service()
    ai_service.set_camera_frame_provider(camera_service.get_current_frame)
    initialized = await ai_service.initialize()
    if not initialized:
        raise RuntimeError("AI service initialization returned false")
    camera_service.set_ai_processor(ai_service.infer_camera_frame)


async def main():
    """Main entry point for camera service."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    loop = asyncio.get_running_loop()

    def signal_handler(sig):
        logger.info(f"Received signal {sig}, shutting down...")
        camera_service.running = False

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler, sig)

    try:
        if not await camera_service.initialize():
            logger.error("Failed to initialize camera service")
            return 1

        # AI is optional for camera availability: wire it before capture so no
        # frame can be marked processed by an uninitialized processor, but keep
        # streaming when model setup is unavailable.
        try:
            await _configure_camera_ai()
        except Exception:
            logger.exception("AI setup failed; continuing camera stream without inference")

        if not await camera_service.start_streaming():
            logger.error("Failed to start camera streaming")
            return 1

        # Keep service running
        while camera_service.running:
            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"Camera service error: {e}")
        return 1

    finally:
        await camera_service.shutdown()

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
