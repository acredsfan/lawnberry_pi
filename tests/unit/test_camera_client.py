import asyncio
import json
from contextlib import suppress

import pytest

from backend.src.models.ai_processing import InferenceResult, InferenceTask
from backend.src.models.camera_stream import CameraFrame, CameraStream, FrameMetadata
from backend.src.services.camera_client import CameraClient


@pytest.mark.asyncio
async def test_camera_client_consumes_owner_status_and_annotated_frame(tmp_path):
    socket_path = tmp_path / "camera.sock"
    stream = CameraStream(is_active=True)
    frame = CameraFrame(
        metadata=FrameMetadata(
            frame_id="frame-owner-1",
            width=32,
            height=24,
            size_bytes=4,
        ),
        processed_for_ai=True,
        ai_annotations=[
            {
                "type": "obstacle_detection",
                "objects": [{"class": "obstacle", "confidence": 0.9}],
            }
        ],
    )
    frame.set_frame_data(b"jpeg")
    perception = InferenceResult(
        inference_id="inference-owner-1",
        task=InferenceTask.OBSTACLE_DETECTION,
        model_name="detector",
        model_runtime="opencv_dnn",
        model_sha256="a" * 64,
        input_frame_id="frame-owner-1",
        input_width=32,
        input_height=24,
    )
    commands: list[str] = []

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while raw := await reader.readline():
                request = json.loads(raw)
                command = request["command"]
                commands.append(command)
                if command == "get_status":
                    status_payload = stream.model_dump(mode="json")
                    status_payload.update(
                        {
                            "sim_mode": False,
                            "requested_sim_mode": False,
                            "hardware_fallback_active": False,
                            "hardware_available": True,
                            "ai_model_loaded": True,
                            "ai_runtime_ready": True,
                            "ai_runtime_error": None,
                            "ai_model_sha256": "a" * 64,
                        }
                    )
                    response = {
                        "status": "success",
                        "data": status_payload,
                    }
                elif command == "get_frame":
                    response = {
                        "status": "success",
                        "data": frame.model_dump(mode="json"),
                    }
                elif command == "get_perception":
                    response = {
                        "status": "success",
                        "data": perception.model_dump(mode="json"),
                    }
                elif command == "set_ai_enabled":
                    stream.ai_processing_enabled = bool(request["enabled"])
                    response = {
                        "status": "success",
                        "data": {"ai_processing_enabled": stream.ai_processing_enabled},
                    }
                elif command == "start_streaming":
                    stream.is_active = True
                    response = {"status": "success", "message": "started"}
                elif command == "stop_streaming":
                    stream.is_active = False
                    response = {"status": "success", "message": "stopped"}
                else:
                    response = {"status": "error", "error": "unsupported"}
                response["request_id"] = request.get("request_id")
                response["command"] = command
                writer.write(json.dumps(response).encode() + b"\n")
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handle_client, path=str(socket_path))
    client = CameraClient(
        str(socket_path),
        request_timeout_seconds=1.0,
        startup_timeout_seconds=0.0,
    )
    try:
        assert await client.initialize() is True
        assert client.running is True
        assert client.stream.is_active is True
        assert client.sim_mode is False
        assert client.hardware_available is True
        assert client.ai_model_loaded is True
        assert client.ai_runtime_ready is True
        assert client.ai_model_sha256 == "a" * 64
        assert client.has_recent_activity(30.0) is False

        received = await client.get_current_frame()
        assert received is not None
        assert received.metadata.frame_id == "frame-owner-1"
        assert received.get_frame_data() == b"jpeg"
        assert received.processed_for_ai is True
        assert received.ai_annotations[0]["objects"][0]["class"] == "obstacle"
        assert client.has_recent_activity(30.0) is True

        received_perception = await client.get_latest_perception()
        assert received_perception is not None
        assert received_perception.input_frame_id == "frame-owner-1"

        await client.set_ai_enabled(False)
        assert client.stream.ai_processing_enabled is False

        await client.stop_streaming()
        assert client.stream.is_active is False
        assert await client.start_streaming() is True
        assert client.stream.is_active is True

        await client.shutdown()
        assert client.running is False
        assert commands == [
            "get_status",
            "get_frame",
            "get_perception",
            "set_ai_enabled",
            "stop_streaming",
            "start_streaming",
        ]
    finally:
        await client.shutdown()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_camera_client_fails_fast_when_owner_socket_is_absent(tmp_path):
    client = CameraClient(
        str(tmp_path / "missing.sock"),
        request_timeout_seconds=0.1,
        startup_timeout_seconds=0.0,
    )

    assert await client.initialize() is False
    assert client.running is False
    assert client.sim_mode is True
    assert client.hardware_available is False


@pytest.mark.asyncio
async def test_camera_client_fails_closed_when_owner_omits_topology(tmp_path):
    socket_path = tmp_path / "legacy-camera.sock"
    stream = CameraStream(is_active=True)

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = json.loads(await reader.readline())
            writer.write(
                json.dumps(
                    {
                        "status": "success",
                        "request_id": request.get("request_id"),
                        "command": request.get("command"),
                        "data": stream.model_dump(mode="json"),
                    }
                ).encode()
                + b"\n"
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handle_client, path=str(socket_path))
    client = CameraClient(
        str(socket_path),
        request_timeout_seconds=1.0,
        startup_timeout_seconds=0.0,
    )
    try:
        assert await client.initialize() is True
        assert client.sim_mode is True
        assert client.hardware_available is False
    finally:
        await client.shutdown()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_cancelled_camera_request_discards_late_ipc_response(tmp_path):
    socket_path = tmp_path / "camera.sock"
    stream = CameraStream(is_active=True)
    status_payload = stream.model_dump(mode="json")
    status_payload.update({"sim_mode": False, "hardware_available": True})
    frame = CameraFrame(
        metadata=FrameMetadata(
            frame_id="cancelled-frame",
            width=32,
            height=24,
            size_bytes=4,
        )
    )
    frame.set_frame_data(b"jpeg")
    request_seen = asyncio.Event()
    release_response = asyncio.Event()
    connection_count = 0
    delayed_once = False

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal connection_count, delayed_once
        connection_count += 1
        try:
            while raw := await reader.readline():
                request = json.loads(raw)
                command = request["command"]
                if command == "get_frame" and not delayed_once:
                    delayed_once = True
                    request_seen.set()
                    await release_response.wait()
                    data = frame.model_dump(mode="json")
                elif command == "get_status":
                    data = status_payload
                else:
                    data = None
                response = {
                    "status": "success",
                    "request_id": request.get("request_id"),
                    "command": command,
                    "data": data,
                }
                writer.write(json.dumps(response).encode() + b"\n")
                await writer.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            writer.close()
            with suppress(BrokenPipeError, ConnectionResetError):
                await writer.wait_closed()

    server = await asyncio.start_unix_server(handle_client, path=str(socket_path))
    client = CameraClient(
        str(socket_path),
        request_timeout_seconds=1.0,
        startup_timeout_seconds=0.0,
    )
    try:
        pending = asyncio.create_task(client.get_current_frame())
        await asyncio.wait_for(request_seen.wait(), timeout=1.0)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending

        release_response.set()
        await asyncio.sleep(0.05)
        status = await client.get_camera_status()

        assert status["is_active"] is True
        assert client.hardware_available is True
        assert connection_count >= 2
    finally:
        release_response.set()
        await client.shutdown()
        server.close()
        await server.wait_closed()
