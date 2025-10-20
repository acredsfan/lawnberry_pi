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
import socket
import stat
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Callable, Any, Tuple
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from ..models.camera_stream import (
    CameraStream, CameraFrame, CameraMode, FrameFormat, 
    StreamQuality, CameraConfiguration, FrameMetadata,
    StreamStatistics
)

# Try to import camera libraries with fallbacks for SIM_MODE
try:
    import cv2
    OPENCV_AVAILABLE = True
except Exception as exc:  # catch ABI mismatches as well
    OPENCV_AVAILABLE = False
    print(f"OpenCV not available - camera service will run in simulation mode ({exc})")
    if "numpy" in str(exc).lower():
        print("Hint: ensure numpy < 2.0 or rebuild OpenCV against the installed numpy version.")

try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
except Exception as exc:
    PICAMERA_AVAILABLE = False
    print(f"PiCamera2 not available - using OpenCV or simulation mode ({exc})")


logger = logging.getLogger(__name__)


class CameraStreamService:
    """
    Camera stream service with IPC support for multi-process architecture.
    Handles camera capture, frame processing, and client management.
    """
    
    def __init__(self, sim_mode: bool = False):
        self.sim_mode = sim_mode or os.getenv('SIM_MODE', '0') == '1'
        self.stream = CameraStream()
        self.clients: Set[asyncio.StreamWriter] = set()
        self.socket_path = "/tmp/lawnberry-camera.sock"
        self.frame_callbacks: List[Callable[[CameraFrame], None]] = []
        
        # Threading for camera capture
        self.capture_thread: Optional[threading.Thread] = None
        self.capture_active = False
        self.frame_queue: Optional[asyncio.Queue[CameraFrame]] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_queue_warning = 0.0
        
        # IPC server
        self.ipc_server: Optional[asyncio.Server] = None
        self.running = False
        
        # Camera backend
        self.camera = None
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.hardware_available = False
        
        # Frame storage
        self.storage_dir = Path("/var/lib/lawnberry/camera")
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
        """Initialize camera hardware."""
        try:
            if PICAMERA_AVAILABLE:
                try:
                    logger.info("Initializing Pi Camera...")
                    self.camera = Picamera2()

                    # Configure camera
                    config = self.camera.create_video_configuration(
                        main={
                            "format": "RGB888",
                            "size": (
                                self.stream.configuration.width,
                                self.stream.configuration.height,
                            ),
                        }
                    )
                    # Keep buffer small to minimise latency
                    try:
                        config["buffer_count"] = max(3, min(6, self.stream.configuration.buffer_size))
                    except Exception:
                        pass
                    self.camera.configure(config)
                    self.camera.start()

                    # Apply desired frame rate constraints where supported
                    fps = self.stream.configuration.framerate
                    if fps > 0:
                        frame_duration_us = int(1_000_000 / fps)
                        try:
                            self.camera.set_controls({
                                "FrameDurationLimits": (frame_duration_us, frame_duration_us)
                            })
                        except Exception as exc:
                            logger.debug("Unable to enforce PiCamera2 frame duration limits: %s", exc)

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
            # Clean up existing socket
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
            
            # Create IPC server
            self.ipc_server = await asyncio.start_unix_server(
                self._handle_client_connection,
                path=self.socket_path
            )
            
            # Set socket permissions
            os.chmod(self.socket_path, 0o666)
            
            logger.info(f"IPC server listening on {self.socket_path}")
            
        except Exception as e:
            logger.error(f"Failed to setup IPC server: {e}")
            raise
    
    async def _handle_client_connection(self, reader: asyncio.StreamReader, 
                                      writer: asyncio.StreamWriter):
        """Handle new client connection."""
        client_addr = writer.get_extra_info('sockname')
        logger.info(f"New camera client connected: {client_addr}")
        
        self.clients.add(writer)
        self.stream.client_count = len(self.clients)
        
        try:
            while True:
                # Read client message
                data = await reader.read(1024)
                if not data:
                    break
                
                try:
                    message = json.loads(data.decode())
                    response = await self._handle_client_message(message)
                    
                    # Send response
                    response_data = json.dumps(response).encode() + b'\n'
                    writer.write(response_data)
                    await writer.drain()
                    
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from client: {data}")
                except Exception as e:
                    logger.error(f"Error handling client message: {e}")
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Client connection error: {e}")
        finally:
            self.clients.discard(writer)
            self.stream.client_count = len(self.clients)
            writer.close()
            await writer.wait_closed()
            logger.info(f"Camera client disconnected: {client_addr}")
    
    async def _handle_client_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client message and return response."""
        command = message.get('command')
        
        if command == 'get_status':
            return {
                'status': 'success',
                'data': self.stream.model_dump()
            }
        
        elif command == 'get_frame':
            frame = await self.get_current_frame()
            if frame:
                return {
                    'status': 'success',
                    'data': frame.model_dump()
                }
            else:
                return {
                    'status': 'error',
                    'error': 'No frame available'
                }
        
        elif command == 'configure':
            config_data = message.get('configuration', {})
            success = await self.update_configuration(config_data)
            return {
                'status': 'success' if success else 'error',
                'message': 'Configuration updated' if success else 'Configuration update failed'
            }
        
        elif command == 'start_streaming':
            success = await self.start_streaming()
            return {
                'status': 'success' if success else 'error',
                'message': 'Streaming started' if success else 'Failed to start streaming'
            }
        
        elif command == 'stop_streaming':
            await self.stop_streaming()
            return {
                'status': 'success',
                'message': 'Streaming stopped'
            }
        
        else:
            return {
                'status': 'error',
                'error': f'Unknown command: {command}'
            }
    
    async def start_streaming(self) -> bool:
        """Start camera streaming."""
        try:
            if (not self.sim_mode) and (not self.hardware_available):
                logger.warning("Camera hardware unavailable and SIM disabled; not starting streaming")
                self.stream.is_active = False
                self.stream.mode = CameraMode.OFFLINE
                return False
            if self.capture_active:
                logger.warning("Streaming already active")
                return True
            
            logger.info("Starting camera streaming...")

            if not self.loop or self.loop.is_closed():
                self.loop = asyncio.get_running_loop()

            # Refresh frame queue with current configuration buffer size
            buffer_size = max(1, int(self.stream.configuration.buffer_size))
            fps = self.stream.configuration.framerate or 1.0
            self._enqueue_timeout = max(1.0, min(3.0, buffer_size / max(0.5, fps)))
            self.frame_queue = asyncio.Queue(maxsize=buffer_size)
            
            # Start capture thread
            self.capture_active = True
            self.capture_thread = threading.Thread(
                target=self._capture_frames_thread,
                daemon=True
            )
            self.capture_thread.start()
            
            # Start frame processing task
            asyncio.create_task(self._process_frames())
            
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
            self.capture_thread.join(timeout=5.0)
        
        self.stream.is_active = False
        self.stream.mode = CameraMode.OFFLINE
        
        logger.info("Camera streaming stopped")
    
    def _capture_frames_thread(self):
        """Camera capture thread (runs in separate thread)."""
        logger.info("Camera capture thread started")
        next_frame_time: Optional[float] = None

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
            await self.frame_queue.put(frame)

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
                    logger.warning("Frame enqueue stalled; dropping frame to keep stream responsive")
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

    def _encode_numpy_frame_to_jpeg(self, frame: Any) -> Optional[bytes]:
        """Encode an RGB numpy frame to JPEG, preferring OpenCV."""
        quality = self._resolve_jpeg_quality()

        if OPENCV_AVAILABLE:
            try:
                if frame.ndim >= 3 and frame.shape[2] == 3:
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
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

            image = Image.fromarray(frame)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality)
            return buffer.getvalue()
        except Exception as exc:
            logger.error("Fallback JPEG encoding failed: %s", exc)
            return None

    def _capture_real_frame(self) -> Optional[Tuple[bytes, Tuple[int, int]]]:
        """Capture frame from real camera."""
        try:
            if PICAMERA_AVAILABLE and isinstance(self.camera, Picamera2):
                frame = self.camera.capture_array("main")
                if frame is None:
                    return None

                height, width = frame.shape[:2]
                encoded = self._encode_numpy_frame_to_jpeg(frame)
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
                        '.jpg',
                        frame,
                        [cv2.IMWRITE_JPEG_QUALITY, self._resolve_jpeg_quality()]
                    )
                    
                    if success:
                        return buffer.tobytes(), (width, height)
            
            return None
            
        except Exception as e:
            logger.error(f"Real frame capture error: {e}")
            return None

    def _discover_opencv_device(self) -> Optional[Tuple[str, Optional[str]]]:
        """Identify a usable V4L2 device for OpenCV capture."""
        # Honor explicit request first.
        explicit = os.getenv("CAMERA_DEVICE")
        if explicit:
            path = explicit if explicit.startswith("/dev/") else f"/dev/{explicit}"
            if Path(path).exists():
                friendly = None
                try:
                    friendly = (Path("/sys/class/video4linux") / Path(path).name / "name").read_text().strip()
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
                sys_entry = (sys_class / device.name / "name")
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
    
    def _generate_simulated_frame(self) -> Tuple[bytes, Tuple[int, int]]:
        """Generate simulated camera frame for testing."""
        try:
            # Create a simple test pattern
            import io
            from PIL import Image, ImageDraw, ImageFont
            
            # Create image
            width = self.stream.configuration.width
            height = self.stream.configuration.height
            image = Image.new('RGB', (width, height), color='green')
            
            # Add some text and graphics
            draw = ImageDraw.Draw(image)
            
            # Draw test pattern
            draw.rectangle([10, 10, width-10, height-10], outline='white', width=2)
            draw.line([0, 0, width, height], fill='white', width=2)
            draw.line([width, 0, 0, height], fill='white', width=2)
            
            # Add timestamp
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            try:
                font = ImageFont.load_default()
                draw.text((20, 20), f"LawnBerry Pi Camera", font=font, fill='white')
                draw.text((20, 40), f"SIM MODE: {timestamp}", font=font, fill='yellow')
                draw.text((20, height-60), f"Frame: {self.stream.statistics.frames_captured}", 
                         font=font, fill='white')
            except:
                # Fallback if font not available
                pass
            
            # Convert to JPEG bytes
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            return buffer.getvalue(), (width, height)
            
        except Exception as e:
            logger.error(f"Simulated frame generation error: {e}")
            # Return minimal JPEG
            minimal = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x00\x01\x00\x01\x01\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9'
            return minimal, (1, 1)
    
    def _create_frame_object(self, frame_data: bytes, dimensions: Optional[Tuple[int, int]] = None) -> CameraFrame:
        """Create CameraFrame object from raw frame data."""
        frame_id = f"frame_{self.stream.statistics.frames_captured:06d}"

        if dimensions:
            width, height = dimensions
        else:
            width = self.stream.configuration.width
            height = self.stream.configuration.height
        
        metadata = FrameMetadata(
            frame_id=frame_id,
            timestamp=datetime.now(timezone.utc),
            sequence_number=self.stream.statistics.frames_captured,
            width=width,
            height=height,
            format=FrameFormat.JPEG,
            size_bytes=len(frame_data)
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
                frame = await asyncio.wait_for(
                    self.frame_queue.get(), timeout=1.0
                )
                
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
                if (self.stream.auto_save_frames and 
                    frame.metadata.sequence_number % 
                    (self.stream.configuration.framerate * self.stream.save_interval_seconds) == 0):
                    await self._save_frame_to_disk(frame)
                
            except asyncio.TimeoutError:
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
        """Process frame for AI analysis (placeholder)."""
        try:
            # This would integrate with AI processing service
            # For now, just mark as processed
            frame.processed_for_ai = True
            
            # Add dummy AI annotations in simulation mode
            if self.sim_mode:
                frame.ai_annotations = [
                    {
                        "type": "object_detection",
                        "objects": [
                            {"class": "grass", "confidence": 0.95, "bbox": [0, 0, 100, 100]}
                        ],
                        "processing_time_ms": 15.5
                    }
                ]
            
        except Exception as e:
            logger.warning(f"AI processing error: {e}")
    
    async def _broadcast_frame_to_clients(self, frame: CameraFrame):
        """Broadcast frame to connected clients."""
        if not self.clients:
            return
        
        try:
            # Create frame message
            message = {
                "type": "frame",
                "data": frame.model_dump(mode="json")
            }
            message_data = json.dumps(message).encode() + b'\n'
            
            # Send to all clients
            disconnected_clients = set()
            
            for client in list(self.clients):
                try:
                    client.write(message_data)
                    await asyncio.wait_for(client.drain(), timeout=self._client_drain_timeout)
                    self.stream.statistics.bytes_transmitted += len(message_data)
                except asyncio.TimeoutError:
                    logger.warning("Camera client drain exceeded %.2fs; disconnecting", self._client_drain_timeout)
                    disconnected_clients.add(client)
                    self.stream.statistics.transmission_errors += 1
                except Exception as e:
                    logger.warning(f"Failed to send frame to client: {e}")
                    disconnected_clients.add(client)
            
            # Clean up disconnected clients
            for client in disconnected_clients:
                self.clients.discard(client)
                self.stream.client_count = len(self.clients)
            
        except Exception as e:
            logger.error(f"Frame broadcast error: {e}")
            self.stream.statistics.transmission_errors += 1
    
    async def _save_frame_to_disk(self, frame: CameraFrame):
        """Save frame to disk storage."""
        try:
            timestamp = frame.metadata.timestamp.strftime('%Y%m%d_%H%M%S')
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
    
    async def get_current_frame(self) -> Optional[CameraFrame]:
        """Get the most recent frame."""
        return self.stream.current_frame
    
    async def update_configuration(self, config_data: Dict[str, Any]) -> bool:
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
                        "format": "RGB888",
                        "size": (
                            self.stream.configuration.width,
                            self.stream.configuration.height,
                        ),
                    }
                )
                try:
                    config["buffer_count"] = max(3, min(6, self.stream.configuration.buffer_size))
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
                        self.camera.set_controls({
                            "FrameDurationLimits": (frame_duration_us, frame_duration_us)
                        })
                    except Exception as exc:
                        logger.debug("Unable to enforce PiCamera2 frame duration limits: %s", exc)
                
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
        
        # Clean up socket
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        
        logger.info("Camera service shutdown complete")


# Global camera service instance
camera_service = CameraStreamService()


async def main():
    """Main entry point for camera service."""
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Handle shutdown signals
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(camera_service.shutdown())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize and start camera service
        if await camera_service.initialize():
            await camera_service.start_streaming()
            
            # Keep service running
            while camera_service.running:
                await asyncio.sleep(1)
        else:
            logger.error("Failed to initialize camera service")
            return 1
    
    except Exception as e:
        logger.error(f"Camera service error: {e}")
        return 1
    
    finally:
        await camera_service.shutdown()
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))