import asyncio
import io

import numpy as np
import pytest
from PIL import Image

import backend.src.services.camera_stream_service as camera_module
from backend.src.services.camera_stream_service import CameraStreamService


@pytest.mark.asyncio
async def test_slow_camera_client_is_dropped():
    service = CameraStreamService(sim_mode=True)
    service.running = True
    service.stream.statistics.frames_captured = 1
    service._client_drain_timeout = 0.05

    class SlowWriter:
        def __init__(self):
            self.buffer = b""

        def write(self, data):
            self.buffer += data

        async def drain(self):
            await asyncio.sleep(0.2)

    slow_client = SlowWriter()
    service.clients.add(slow_client)

    frame = service._create_frame_object(b"data", (10, 10))

    await service._broadcast_frame_to_clients(frame)

    assert slow_client not in service.clients
    assert service.stream.statistics.transmission_errors > 0


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
    for observed, exp in zip(rgb_pixel, expected):
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
