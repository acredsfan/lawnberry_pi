import asyncio

import pytest

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
