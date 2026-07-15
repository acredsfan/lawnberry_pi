import asyncio
import io
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest
from PIL import Image

import backend.src.services.camera_stream_service as camera_module
from backend.src.services.ai_service import AIService
from backend.src.services.camera_stream_service import CameraStreamService
from backend.src.services.detector_runtime import DetectorManifest, RuntimeDetection


def test_live_camera_socket_path_defaults_to_shared_runtime_directory(monkeypatch):
    monkeypatch.delenv("LAWNBERRY_CAMERA_SOCKET", raising=False)
    monkeypatch.delenv("SIM_MODE", raising=False)

    service = CameraStreamService(sim_mode=False)

    assert service.socket_path == "/run/lawnberry/camera.sock"
    assert service.stream.service_endpoint == "unix:///run/lawnberry/camera.sock"


def test_sim_camera_socket_path_defaults_to_tmp(monkeypatch):
    monkeypatch.delenv("LAWNBERRY_CAMERA_SOCKET", raising=False)

    service = CameraStreamService(sim_mode=True)

    assert service.socket_path == "/tmp/lawnberry-camera.sock"
    assert service.stream.service_endpoint == "unix:///tmp/lawnberry-camera.sock"


def test_camera_socket_path_honors_environment(monkeypatch, tmp_path):
    socket_path = tmp_path / "camera.sock"
    monkeypatch.setenv("LAWNBERRY_CAMERA_SOCKET", str(socket_path))

    service = CameraStreamService(sim_mode=True)

    assert service.socket_path == str(socket_path)
    assert service.stream.service_endpoint == f"unix://{socket_path}"


@pytest.mark.asyncio
async def test_slow_camera_client_is_dropped():
    service = CameraStreamService(sim_mode=True)
    service.running = True
    service.stream.statistics.frames_captured = 1
    service._client_drain_timeout = 0.05

    class SlowWriter:
        def __init__(self):
            self.buffer = b""
            self.closed = False

        def write(self, data):
            self.buffer += data

        async def drain(self):
            await asyncio.sleep(0.2)

        def close(self):
            self.closed = True

        async def wait_closed(self):
            return None

    slow_client = SlowWriter()
    service.clients.add(slow_client)
    service._frame_clients.add(slow_client)

    frame = service._create_frame_object(b"data", (10, 10))

    await service._broadcast_frame_to_clients(frame)

    assert slow_client not in service.clients
    assert slow_client.closed is True
    assert service.stream.statistics.transmission_errors > 0


@pytest.mark.asyncio
async def test_ipc_status_and_frame_responses_are_json_serializable():
    service = CameraStreamService(sim_mode=True)
    service.stream.last_frame_time = datetime.now(UTC)
    frame = service._create_frame_object(b"jpeg", (10, 10))
    service.stream.current_frame = frame

    status_response = await service._handle_client_message({"command": "get_status"})
    frame_response = await service._handle_client_message({"command": "get_frame"})

    json.dumps(status_response)
    json.dumps(frame_response)
    assert "current_frame" not in status_response["data"]


@pytest.mark.asyncio
async def test_camera_owner_applies_ai_power_gate_and_clears_cached_result():
    service = CameraStreamService(sim_mode=True)
    service._latest_ai_result = SimpleNamespace()

    disabled = await service._handle_client_message(
        {"command": "set_ai_enabled", "enabled": False}
    )

    assert disabled["data"]["ai_processing_enabled"] is False
    assert service._latest_ai_result is None

    enabled = await service._handle_client_message(
        {"command": "set_ai_enabled", "enabled": True}
    )
    assert enabled["data"]["ai_processing_enabled"] is True


@pytest.mark.asyncio
async def test_command_responses_are_not_interleaved_with_frame_broadcasts(tmp_path):
    service = CameraStreamService(sim_mode=True)
    service.socket_path = str(tmp_path / "camera.sock")
    frame = service._create_frame_object(b"jpeg", (10, 10))
    service.stream.current_frame = frame
    assert await service.initialize() is True

    reader, writer = await asyncio.open_unix_connection(service.socket_path)
    try:
        for _ in range(20):
            if service.clients:
                break
            await asyncio.sleep(0.01)
        assert len(service.clients) == 1

        writer.write(json.dumps({"command": "get_status"}).encode() + b"\n")
        await writer.drain()
        await service._broadcast_frame_to_clients(frame)

        status = json.loads(await asyncio.wait_for(reader.readline(), timeout=1.0))
        assert status["status"] == "success"
        assert "current_frame" not in status["data"]

        writer.write(json.dumps({"command": "get_frame"}).encode() + b"\n")
        await writer.drain()
        await service._broadcast_frame_to_clients(frame)

        frame_response = json.loads(await asyncio.wait_for(reader.readline(), timeout=1.0))
        assert frame_response["status"] == "success"
        assert frame_response["data"]["metadata"]["frame_id"] == frame.metadata.frame_id

        # Newline framing must preserve separate commands even when the OS
        # coalesces both writes into one stream read.
        writer.write(
            json.dumps({"command": "get_status"}).encode()
            + b"\n"
            + json.dumps({"command": "get_frame"}).encode()
            + b"\n"
        )
        await writer.drain()
        coalesced_status = json.loads(
            await asyncio.wait_for(reader.readline(), timeout=1.0)
        )
        coalesced_frame = json.loads(
            await asyncio.wait_for(reader.readline(), timeout=1.0)
        )
        assert coalesced_status["status"] == "success"
        assert coalesced_frame["data"]["metadata"]["frame_id"] == frame.metadata.frame_id

        writer.write(json.dumps({"command": "subscribe_frames"}).encode() + b"\n")
        await writer.drain()
        subscription = json.loads(await asyncio.wait_for(reader.readline(), timeout=1.0))
        assert subscription == {
            "status": "success",
            "message": "Frame subscription enabled",
        }

        await service._broadcast_frame_to_clients(frame)
        event = json.loads(await asyncio.wait_for(reader.readline(), timeout=1.0))
        assert event["type"] == "frame"
        assert event["data"]["metadata"]["frame_id"] == frame.metadata.frame_id
    finally:
        writer.close()
        await writer.wait_closed()
        await service.shutdown()


@pytest.mark.parametrize(
    "color_space,pixel_value",
    [
        ("RGB", [10, 40, 180]),
        ("BGR", [180, 40, 10]),
    ],
)
def test_encode_numpy_frame_preserves_expected_rgb(monkeypatch, color_space, pixel_value):
    service = CameraStreamService(sim_mode=True)
    monkeypatch.setattr(camera_module, "OPENCV_AVAILABLE", False)

    frame = np.array([[pixel_value]], dtype=np.uint8)
    encoded = service._encode_numpy_frame_to_jpeg(frame, color_space=color_space)
    assert encoded is not None

    image = Image.open(io.BytesIO(encoded)).convert("RGB")
    rgb_pixel = list(image.getpixel((0, 0)))

    if color_space == "RGB":
        expected = pixel_value
    else:
        # BGR input should round-trip to RGB by swapping channels
        expected = [pixel_value[2], pixel_value[1], pixel_value[0]]

    assert len(rgb_pixel) == len(expected)
    for observed, exp in zip(rgb_pixel, expected, strict=True):
        assert abs(observed - exp) <= 2


def test_picamera2_uses_full_sensor_crop_for_full_fov(monkeypatch):
    """PiCamera2 should be configured to use the full sensor area, not a zoomed crop."""

    class FakeCamera:
        def __init__(self):
            self.camera_properties = {"ScalerCropMaximum": (0, 0, 4056, 3040)}
            self.controls = []
            self.config = None
            self.started = False

        def create_video_configuration(self, main):
            self.config = {"main": main}
            return {"buffer_count": 3}

        def configure(self, config):
            self.config = config

        def start(self):
            self.started = True

        def set_controls(self, controls):
            self.controls.append(controls)

        def close(self):
            pass

    monkeypatch.setattr(camera_module, "PICAMERA_AVAILABLE", True)
    monkeypatch.setattr(camera_module, "Picamera2", FakeCamera)

    service = CameraStreamService(sim_mode=False)
    service.stream.configuration.width = 1280
    service.stream.configuration.height = 720
    service.stream.configuration.framerate = 15.0

    assert service._initialize_camera_sync() is True
    assert isinstance(service.camera, FakeCamera)
    assert service.camera.started is True
    assert any("ScalerCrop" in call for call in service.camera.controls)
    assert service.camera.controls[-1]["ScalerCrop"] == (0, 0, 4056, 3040)


@pytest.mark.asyncio
async def test_v42_camera_ai_uses_canonical_inference_result():
    """V42: a frame is marked processed only after AIService returns a result."""
    service = CameraStreamService(sim_mode=True)
    frame = service._create_frame_object(b"jpeg-bytes", (640, 480))
    result = SimpleNamespace(
        inference_id="inference-1",
        input_frame_id=frame.metadata.frame_id,
        task="obstacle_detection",
        model_name="test-detector",
        model_version="1.0",
        model_runtime="opencv_dnn",
        model_sha256="a" * 64,
        timestamp=datetime.now(UTC),
        source_frame_timestamp=frame.metadata.timestamp,
        total_time_ms=12.5,
        detected_objects=[
            SimpleNamespace(
                object_id="object-1",
                class_name="obstacle",
                confidence=0.91,
                bounding_box=SimpleNamespace(x=0.1, y=0.2, width=0.3, height=0.4),
                distance_estimate=None,
                relative_bearing=None,
                angular_width_degrees=18.6,
                tracking_id=None,
                semantic_cost_multiplier=1.5,
            )
        ],
    )
    processor = AsyncMock(return_value=result)
    service.set_ai_processor(processor, max_fps=5.0)

    await service._process_frame_for_ai(frame)

    assert frame.processed_for_ai is True
    assert frame.ai_annotations == [
        {
            "type": "obstacle_detection",
            "inference_id": "inference-1",
            "model_name": "test-detector",
            "model_version": "1.0",
            "model_runtime": "opencv_dnn",
            "model_sha256": "a" * 64,
            "timestamp": result.timestamp.isoformat(),
            "source_frame_timestamp": frame.metadata.timestamp.isoformat(),
            "input_frame_id": frame.metadata.frame_id,
            "processing_time_ms": 12.5,
            "objects": [
                {
                    "id": "object-1",
                    "class": "obstacle",
                    "confidence": 0.91,
                    "bbox": [0.1, 0.2, 0.3, 0.4],
                    "distance_estimate_m": None,
                    "relative_bearing_degrees": None,
                    "angular_width_degrees": 18.6,
                    "tracking_id": None,
                    "semantic_cost_multiplier": 1.5,
                }
            ],
        }
    ]
    processor.assert_awaited_once_with(
        b"jpeg-bytes",
        frame_id=frame.metadata.frame_id,
        source_frame_timestamp=frame.metadata.timestamp,
    )


@pytest.mark.asyncio
async def test_v42_camera_ai_never_fakes_success_and_respects_cadence():
    """V42: skipped or failed inference leaves the frame explicitly unprocessed."""
    service = CameraStreamService(sim_mode=True)
    processor = AsyncMock(side_effect=RuntimeError("model unavailable"))
    service.set_ai_processor(processor, max_fps=5.0)
    failed_frame = service._create_frame_object(b"failed", (640, 480))

    await service._process_frame_for_ai(failed_frame)

    assert failed_frame.processed_for_ai is False
    assert failed_frame.ai_annotations == []

    processor = AsyncMock(return_value=SimpleNamespace())
    service.set_ai_processor(processor, max_fps=5.0)
    service._last_ai_inference_monotonic = service._monotonic()
    skipped_frame = service._create_frame_object(b"skipped", (640, 480))

    await service._process_frame_for_ai(skipped_frame)

    assert skipped_frame.processed_for_ai is False
    assert skipped_frame.ai_annotations == []
    processor.assert_not_awaited()


@pytest.mark.asyncio
async def test_v42_camera_ai_rejects_mismatched_frame_provenance():
    service = CameraStreamService(sim_mode=True)
    processor = AsyncMock(
        return_value=SimpleNamespace(input_frame_id="different-frame")
    )
    service.set_ai_processor(processor)
    frame = service._create_frame_object(b"jpeg-bytes", (640, 480))

    await service._process_frame_for_ai(frame)

    assert frame.processed_for_ai is False
    assert frame.ai_annotations == []


@pytest.mark.asyncio
async def test_camera_ai_rejects_mismatched_source_timestamp():
    service = CameraStreamService(sim_mode=True)
    frame = service._create_frame_object(b"jpeg-bytes", (640, 480))
    processor = AsyncMock(
        return_value=SimpleNamespace(
            input_frame_id=frame.metadata.frame_id,
            source_frame_timestamp=datetime.now(UTC),
        )
    )
    service.set_ai_processor(processor)

    await service._process_frame_for_ai(frame)

    assert frame.processed_for_ai is False
    assert frame.ai_annotations == []


@pytest.mark.asyncio
async def test_v42_zero_detections_is_a_truthful_processed_result():
    service = CameraStreamService(sim_mode=True)
    frame = service._create_frame_object(b"jpeg-bytes", (640, 480))
    processor = AsyncMock(
        return_value=SimpleNamespace(
            inference_id="inference-empty",
            input_frame_id=frame.metadata.frame_id,
            task="obstacle_detection",
            model_name="test-detector",
            model_version="1.0",
            model_runtime="opencv_dnn",
            model_sha256="a" * 64,
            timestamp=datetime.now(UTC),
            source_frame_timestamp=frame.metadata.timestamp,
            total_time_ms=4.0,
            detected_objects=[],
        )
    )
    service.set_ai_processor(processor)

    await service._process_frame_for_ai(frame)

    assert frame.processed_for_ai is True
    assert frame.ai_annotations[0]["objects"] == []


@pytest.mark.asyncio
async def test_v42_timed_out_inference_stays_single_flight_and_does_not_mark_frames():
    service = CameraStreamService(sim_mode=True)
    release = asyncio.Event()

    async def slow_processor(
        image_bytes: bytes,
        *,
        frame_id: str,
        source_frame_timestamp=None,
    ):
        await release.wait()
        return SimpleNamespace(input_frame_id=frame_id)

    processor = AsyncMock(side_effect=slow_processor)
    service.set_ai_processor(processor, max_fps=5.0, timeout_seconds=0.05)
    timed_out_frame = service._create_frame_object(b"first", (640, 480))
    service._broadcast_frame_to_clients = AsyncMock()

    await service._process_single_frame(timed_out_frame)

    assert timed_out_frame.processed_for_ai is False
    assert timed_out_frame.ai_annotations == []
    assert service._ai_inference_task is not None
    service._broadcast_frame_to_clients.assert_awaited_once_with(timed_out_frame)

    # Even if cadence is due again, a timed-out worker remains the only
    # in-flight inference until it actually finishes.
    service._last_ai_inference_monotonic = None
    next_frame = service._create_frame_object(b"second", (640, 480))
    await service._process_frame_for_ai(next_frame)
    processor.assert_awaited_once()
    assert next_frame.processed_for_ai is False

    release.set()
    await asyncio.wait_for(service._ai_inference_task, timeout=1.0)
    await asyncio.sleep(0)
    assert service._ai_inference_task is None


@pytest.mark.asyncio
async def test_v42_real_ai_service_annotates_without_motion_authority(
    tmp_path,
    monkeypatch,
):
    from backend.src.control.command_gateway import MotorCommandGateway
    from backend.src.core.state_manager import get_safety_state

    dispatch_drive = AsyncMock(side_effect=AssertionError("camera AI cannot command motion"))
    dispatch_blade = AsyncMock(side_effect=AssertionError("camera AI cannot command blades"))
    monkeypatch.setattr(MotorCommandGateway, "dispatch_drive", dispatch_drive)
    monkeypatch.setattr(MotorCommandGateway, "dispatch_blade", dispatch_blade)
    safety_before = dict(get_safety_state())
    class CameraTestRuntime:
        manifest = DetectorManifest(
            model_name="camera-test-detector",
            model_path=str(tmp_path / "camera.onnx"),
            input_width=64,
            input_height=64,
            class_labels=["obstacle"],
        )
        model_path = tmp_path / "camera.onnx"
        model_sha256 = "c" * 64
        ready = False
        last_error = None

        def initialize(self):
            self.ready = True

        def infer(self, _rgb, _threshold):
            return [RuntimeDetection("obstacle", 0.9, 0.25, 0.25, 0.5, 0.5)]
    pixels = np.full((64, 64, 3), [20, 160, 20], dtype=np.uint8)
    pixels[16:48, 16:48] = [220, 20, 20]
    image_buffer = io.BytesIO()
    Image.fromarray(pixels, mode="RGB").save(image_buffer, format="JPEG")

    ai_service = AIService(
        model_path=str(tmp_path / "ai-detector.json"),
        confidence_threshold=0.2,
        detector_runtime=CameraTestRuntime(),
    )
    await ai_service.initialize()
    service = CameraStreamService(sim_mode=True)
    service.set_ai_processor(ai_service.infer_camera_frame, timeout_seconds=1.0)
    frame = service._create_frame_object(image_buffer.getvalue(), (64, 64))

    await service._process_frame_for_ai(frame)

    assert frame.processed_for_ai is True
    assert frame.ai_annotations[0]["model_name"] == "camera-test-detector"
    assert frame.ai_annotations[0]["objects"][0]["class"] == "obstacle"
    assert get_safety_state() == safety_before
    dispatch_drive.assert_not_awaited()
    dispatch_blade.assert_not_awaited()


def test_shutdown_clears_loop_bound_state_for_reinitialize(tmp_path):
    service = CameraStreamService(sim_mode=True)
    service.socket_path = str(tmp_path / "camera.sock")

    async def run_cycle():
        assert await service.initialize() is True
        assert await service.start_streaming() is True
        queue = service.frame_queue
        loop = service.loop
        executor = service.executor
        await asyncio.sleep(0.02)
        await service.shutdown()
        assert service.frame_queue is None
        assert service.loop is None
        return queue, loop, executor

    first_queue, first_loop, first_executor = asyncio.run(run_cycle())
    second_queue, second_loop, second_executor = asyncio.run(run_cycle())

    assert first_queue is not second_queue
    assert first_loop is not second_loop
    assert first_executor is not second_executor


@pytest.mark.asyncio
async def test_standalone_main_wires_ai_before_streaming(monkeypatch):
    order: list[str] = []

    class FakeAIService:
        def set_camera_frame_provider(self, provider):
            order.append("ai.provider")
            self.provider = provider

        async def initialize(self):
            order.append("ai.initialize")
            return True

        async def infer_camera_frame(
            self,
            image_bytes: bytes,
            *,
            frame_id: str,
            source_frame_timestamp=None,
        ):
            return None

    class FakeCameraOwner:
        def __init__(self):
            self.running = False
            self.ai_processor = None
            self.shutdown_calls = 0

        async def initialize(self):
            order.append("camera.initialize")
            self.running = True
            return True

        def set_ai_processor(self, processor):
            order.append("camera.ai_processor")
            self.ai_processor = processor

        async def start_streaming(self):
            order.append("camera.start")
            self.running = False
            return True

        async def get_current_frame(self):
            return None

        async def shutdown(self):
            self.shutdown_calls += 1
            self.running = False

    camera = FakeCameraOwner()
    ai_service = FakeAIService()
    monkeypatch.setattr(camera_module, "camera_service", camera)
    monkeypatch.setattr(camera_module, "_get_ai_service", lambda: ai_service, raising=False)

    assert await camera_module.main() == 0

    assert order == [
        "camera.initialize",
        "ai.provider",
        "ai.initialize",
        "camera.ai_processor",
        "camera.start",
    ]
    assert camera.ai_processor == ai_service.infer_camera_frame
    assert camera.shutdown_calls == 1


@pytest.mark.asyncio
async def test_standalone_main_streams_when_ai_setup_fails(monkeypatch):
    class FailingAIService:
        def __init__(self):
            self.initialize_called = False

        def set_camera_frame_provider(self, provider):
            self.provider = provider

        async def initialize(self):
            self.initialize_called = True
            raise RuntimeError("model setup failed")

    class FakeCameraOwner:
        def __init__(self):
            self.running = False
            self.start_calls = 0

        async def initialize(self):
            self.running = True
            return True

        def set_ai_processor(self, processor):
            raise AssertionError("failed AI must not be injected")

        async def start_streaming(self):
            self.start_calls += 1
            self.running = False
            return True

        async def get_current_frame(self):
            return None

        async def shutdown(self):
            self.running = False

    camera = FakeCameraOwner()
    ai_service = FailingAIService()
    monkeypatch.setattr(camera_module, "camera_service", camera)
    monkeypatch.setattr(camera_module, "_get_ai_service", lambda: ai_service, raising=False)

    assert await camera_module.main() == 0

    assert ai_service.initialize_called is True
    assert camera.start_calls == 1
