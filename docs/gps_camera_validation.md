# GPS and Camera Validation (Raspberry Pi OS Bookworm)

This guide shows how to quickly validate live GPS data flowing to the UI and camera streaming without disrupting obstacle detection.

Prereqs:
- Use the repository `venv` per project rules. Avoid system python.
- Ensure services are deployed to `/opt/lawnberry` using the installer if testing services; for a quick smoke test, you can run locally.

## Quick GPS Smoke Test

Run a bounded GPS test that auto-detects the port/baud, reads for ~20 seconds, and prints compact JSON lines when data is present.

Example:

```
test -x venv/bin/python || echo "ERROR: venv python missing"
timeout 30s venv/bin/python -m scripts.gps_smoke_test --duration 20 --interval 0.5
```

Notes:
- The test disables camera init by setting `LAWNBERY_DISABLE_CAMERA=1` to avoid camera conflicts during a quick GPS check.
- The GPS plugin avoids conflicting ports already assigned to `robohat`.
- Default GPS port/baud in `config/hardware.yaml` is `/dev/ttyACM1 @ 115200`. The plugin will auto-detect other ACM/USB/AMA ports if needed.

## Camera Sanity Check (shared access)

The Web API and Vision components both consume frames from the shared `HardwareInterface.get_camera_frame()` and a singleton `CameraManager`.

Check camera availability quickly:

```
python - <<'PY'
import asyncio
from src.hardware.hardware_interface import create_hardware_interface

async def main():
    hw = create_hardware_interface("config/hardware.yaml", shared=False, force_new=True)
    await hw.initialize()
    frame = await hw.get_camera_frame()
    print("frame_available", bool(frame))
    await hw.cleanup()

asyncio.run(main())
PY
```

If `False`, verify `/dev/video0` permissions and that no exclusive holder exists. The manager will try V4L2 then fall back to Picamera2 when available.

## Service Checklist

When validating end-to-end UI:
- Ensure Mosquitto (MQTT) service is running.
- Start/enable `lawnberry-api.service` and `lawnberry-sensor.service` (both allow `/dev/video0`).
- Confirm GPS updates on topic `lawnberry/sensors/gps/data` and camera stream endpoints under the Web API are reachable.

All long-running commands should use `timeout` to avoid stuck terminals.
