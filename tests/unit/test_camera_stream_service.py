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
