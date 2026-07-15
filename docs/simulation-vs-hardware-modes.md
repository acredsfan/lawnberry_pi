# LawnBerry Simulation vs Hardware Modes

This document explains the two runtime modes used by LawnBerry Pi and, just as importantly, what happens when you do
not set `SIM_MODE` explicitly.

## The short version

| Mode | How to start it | What it does |
|---|---|---|
| **Simulation mode** | `SIM_MODE=1 ...` | Skips hardware access entirely and uses simulation-safe behavior. |
| **Hardware mode** | `SIM_MODE=0 ...` | Attempts real hardware initialization and falls back gracefully when individual devices are missing. |
| **Unset `SIM_MODE`** | no env var | Behaves like hardware mode today because startup checks `os.getenv("SIM_MODE", "0")`. |

Hardware configuration follows the same split:

- `SIM_MODE=1` can run from a fresh clone without `config/hardware.yaml`.
- hardware mode requires ignored `config/hardware.yaml`, created from `config/hardware.pi5.example.yaml` or
  `config/hardware.pi4.example.yaml`.
- `hardware.local.yaml` is not a runtime overlay. If it exists, run
  `uv run python scripts/manage_hardware_config.py migrate-legacy --profile auto`.

## What the backend actually does

`backend/src/main.py` uses `os.getenv("SIM_MODE", "0") == "0"` to decide whether to attempt hardware-only startup work such
as ToF pair addressing. That means:

- `SIM_MODE=1` is the **only** pure simulation path
- `SIM_MODE=0` enables hardware initialization
- leaving `SIM_MODE` unset currently behaves like `SIM_MODE=0`

The backend is also intentionally **best-effort** during startup:

- RoboHAT initialization is wrapped in `try/except`
- camera initialization is wrapped in `try/except`
- missing devices do **not** necessarily crash startup

That best-effort behavior is useful, but it is not the same thing as a pure simulation run.

## Recommended usage

### Laptop or CI development

Use pure simulation mode:

```bash
SIM_MODE=1 python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081
```

Use this when:

- developing away from the mower
- running tests on machines without GPIO / serial hardware
- validating API or frontend behavior without touching real devices

Expected behavior:

- no real GPIO / serial hardware access
- cleaner logs
- simulated telemetry and device behavior, explicitly labeled `source=simulated`
- no physical autonomy-qualification credit; simulation evidence cannot unlock blade-enabled autonomy

### On-device Raspberry Pi validation

Use the paired hardware services. The camera service is the sole live camera-device owner; the backend consumes its Unix
socket and does not open the device itself:

```bash
sudo systemctl start lawnberry-camera.service lawnberry-backend.service
```

For an interactive bench run without systemd, use two terminals from the repository root. Both commands must name the
same user-owned socket:

```bash
# Terminal 1: sole camera owner
SIM_MODE=0 LAWNBERRY_CAMERA_SOCKET=/tmp/lawnberry-camera.sock \
  python -m backend.src.services.camera_stream_service

# Terminal 2: backend IPC client
SIM_MODE=0 LAWNBERRY_CAMERA_SOCKET=/tmp/lawnberry-camera.sock \
  python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081
```

Do not run the manual owner while `lawnberry-camera.service` is active.

Use this when:

- validating on the mower or a hardware bench
- checking real sensors, RoboHAT, camera, GPS, IMU, and power telemetry
- running hardware self-tests

Expected behavior:

- the backend attempts real hardware initialization
- any missing device may log warnings
- functioning devices still come online when possible

## Graceful fallback vs pure simulation

These are different states.

### Pure simulation (`SIM_MODE=1`)

- hardware access is skipped by design
- no dependency on actual GPIO/UART/I2C devices
- preferred for local development and CI

### Graceful fallback (`SIM_MODE=0` with missing hardware)

- hardware initialization is attempted
- some devices may fail and log warnings
- the backend may still continue running in a partially simulated / partially unavailable state
- dashboard, telemetry, camera, AI, power, and weather surfaces must report their actual source, freshness, and
  availability; missing measurements remain null/unknown instead of healthy-looking zeroes

This hybrid behavior is useful for resilience testing, but it can confuse people if it is mistaken for full simulation.

Use `GET /api/v2/system/info` to identify the exact serving build. Use
`GET /api/v2/dashboard/status`, `GET /api/v2/dashboard/telemetry`, `GET /api/v2/camera/status`, and
`GET /api/v2/power/state` to inspect source/freshness. An endpoint answering successfully does not prove attached
hardware, and `hardware_available=false` or `source=unavailable` must be treated as unavailable evidence.

## Common workflows

### Local backend development

```bash
cd backend
SIM_MODE=1 python -m uvicorn src.main:app --host 0.0.0.0 --port 8081 --reload
```

### Frontend development against a simulated backend

```bash
cd backend
SIM_MODE=1 python -m uvicorn src.main:app --host 0.0.0.0 --port 8081 --reload

cd frontend
npm run dev -- --host 0.0.0.0 --port 3000
```

### On-device hardware self-test

```bash
sudo systemctl start lawnberry-camera.service lawnberry-backend.service
curl http://localhost:8081/api/v2/system/selftest | jq
```

## Validation tips

### Simulation mode checks

- confirm you launched with `SIM_MODE=1`
- verify API responses work without hardware present
- expect simulated telemetry rather than live sensor data

### Hardware mode checks

- confirm you launched with `SIM_MODE=0`
- confirm exactly one camera owner is active and the backend uses the same socket
- confirm `uv run python scripts/manage_hardware_config.py validate` succeeds
- inspect `journalctl` or backend logs for device initialization messages
- verify self-test, RoboHAT status, and sensor health endpoints

## Related files

- `backend/src/main.py`
- `systemd/lawnberry-backend.service`
- `docs/TESTING.md`
- `docs/OPERATIONS.md`
- `docs/developer-toolkit.md`
- `config/hardware.yaml`
