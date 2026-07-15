# LawnBerry Pi v2 - Operations Guide

This document summarizes common operational procedures and API references relevant to day-to-day use on Raspberry Pi OS (64-bit, Bookworm). All examples target Raspberry Pi 5 primarily, with Pi 4B compatibility noted where relevant.

## Services
- Backend API (FastAPI/Uvicorn): port 8081
- Web UI (Vite dev): port 3000 (proxy to /api → /api/v2)
- WebSocket: ws://127.0.0.1:8081/api/v2/ws/telemetry

## Startup behavior

Use these runtime defaults consistently when starting or validating the stack:

- **Local backend development**: run Uvicorn on port `8081`
- **Local frontend development**: run Vite on port `3000`
- **Deployed/systemd runtime**: backend remains on `8081`, frontend remains on `3000`
- **Playwright preview/E2E**: Vite preview runs on port `4173` by design

This means `8081`/`3000` are the canonical backend/frontend ports for both local development and deployed operation. The preview server on `4173` is intentional and only used for preview/E2E flows.

## On-device Wi-Fi failover

On the mower, Wi-Fi is managed by NetworkManager with two radios:

- `wlan1` is the current primary client radio and normally carries `wlan1-primary`
- `wlan0` is kept managed as a standby/backup scan radio

Operational notes:

- The built-in radio must remain managed by NetworkManager; on this Pi that is enforced with
  `/etc/udev/rules.d/100-manage-wlan0.rules`
- Backup NetworkManager profiles exist on `wlan0` for `Butters Read-Link`, `Link Outdoor`, and `Link_IoT`
- `/etc/NetworkManager/dispatcher.d/90-wifi-failover` promotes the best visible backup profile on `wlan0` if
  `wlan1` drops off Wi-Fi completely
- Backup profiles intentionally keep `autoconnect=false` so they do not steal the active route during normal
  operation; the dispatcher is what activates them on failure

Useful checks:

```bash
nmcli -f DEVICE,TYPE,STATE,CONNECTION dev status
nmcli -f NAME,DEVICE,AUTOCONNECT connection show
nmcli -f SSID,SIGNAL,CHAN,FREQ dev wifi list ifname wlan0 --rescan yes
journalctl -t wifi-failover -n 50 --no-pager
```

## Simulation vs hardware mode

The backend has two meaningful startup modes:

- **`SIM_MODE=1`**: pure simulation mode; skip hardware access entirely
- **`SIM_MODE=0`**: hardware mode; attempt real hardware initialization and degrade gracefully if individual devices fail

Important nuance: leaving `SIM_MODE` unset currently behaves like hardware mode because `backend/src/main.py` checks
`os.getenv("SIM_MODE", "0")`.

Recommended commands:

```bash
# Laptop / CI / simulation-safe local dev
SIM_MODE=1 python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081

# Raspberry Pi / hardware validation (starts the sole camera owner first)
sudo systemctl start lawnberry-camera.service lawnberry-backend.service
```

If you want a clean local-development experience without serial/GPIO warnings, always set `SIM_MODE=1` explicitly.
For an interactive hardware bench session without systemd, run the camera owner and backend from the repository root in
separate terminals with the same user-owned socket:

```bash
# Terminal 1
SIM_MODE=0 LAWNBERRY_CAMERA_SOCKET=/tmp/lawnberry-camera.sock \
  python -m backend.src.services.camera_stream_service

# Terminal 2
SIM_MODE=0 LAWNBERRY_CAMERA_SOCKET=/tmp/lawnberry-camera.sock \
  python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081
```

Do not start this manual camera owner while `lawnberry-camera.service` is active. Stop the manual owner when the bench
session ends; live hardware must have exactly one process opening the camera.

## Hardware configuration

Hardware configuration has one runtime source:

- `spec/hardware.yaml` is the tracked supported-hardware specification.
- `config/hardware.pi5.example.yaml` and `config/hardware.pi4.example.yaml` are tracked complete templates.
- `config/hardware.yaml` is the ignored, owner-only runtime file and may contain node-specific secrets.
- `config/hardware.local.yaml` is no longer loaded; `ensure` and `validate` fail if it exists so the
  legacy values cannot be silently ignored. Use the migration command below once if it exists.
- `config/limits.local.yaml` remains the separate ignored safety-limit override.

Commands:

```bash
uv run python scripts/manage_hardware_config.py ensure --profile auto
uv run python scripts/manage_hardware_config.py ensure --profile pi5
uv run python scripts/manage_hardware_config.py ensure --profile pi4
uv run python scripts/manage_hardware_config.py validate
uv run python scripts/manage_hardware_config.py migrate-legacy --profile auto
```

Normal setup and update flows never overwrite an existing `config/hardware.yaml`. After changing hardware configuration,
restart the backend so the validated typed config is reloaded.

## TLS/HTTPS Operations

TLS is managed automatically:
- On first setup, nginx is installed and configured with a self-signed certificate.
- If `LB_DOMAIN` and `LETSENCRYPT_EMAIL` are set in `.env`, the system provisions a valid Let’s Encrypt certificate and switches nginx to use it.
- A daily renewal timer validates and renews certificates; on issues or imminent expiry, the system falls back to self-signed to maintain availability.
- The fallback self-signed certificate now includes SAN entries for `localhost`, detected LAN IPv4 addresses, and configured domain/alt-domain values so browsers do not also fail with a hostname-mismatch error when you access the Pi by IP.

Useful commands:
```bash
# Check renewal timer status and last/next run
systemctl list-timers | grep lawnberry-cert-renewal

# Inspect recent renewal logs
journalctl -u lawnberry-cert-renewal.service -n 200 --no-pager

# Force a renewal/validation cycle
sudo systemctl start lawnberry-cert-renewal.service

# Dry-run renewal test
sudo certbot renew --dry-run

# Backend health and metrics for TLS status
curl -s http://127.0.0.1:8081/api/v2/health | jq '.subsystems.tls'
curl -s http://127.0.0.1:8081/metrics | grep lawnberry_tls_cert_
```

Environment variables (set in `.env`):
- `LB_DOMAIN` – primary domain (CN)
- `LETSENCRYPT_EMAIL` – contact email for Let’s Encrypt
- `ALT_DOMAINS` – optional hostname SANs (comma-separated), e.g., `www.example.com,api.example.com`; do not put LAN/private IPs here because Let’s Encrypt will not issue IP-address certificates
- `CLOUDFLARE_API_TOKEN` – optional, for DNS-01 (wildcards or no port 80)

The Cloudflare Tunnel connector token is not the DNS-01 API token and must not be stored in `.env`, a systemd
`ExecStart`, shell history, or the repository. LawnBerry installs the remotely managed connector with
`systemd/cloudflared.service`, which reads `/etc/cloudflared/tunnel-token` through `--token-file`. Manage and verify it
with:

```bash
# One-time migration from a legacy inline-token service
sudo python scripts/manage_cloudflared_service.py --migrate-existing

# Install a replacement token without echoing it
sudo python scripts/manage_cloudflared_service.py --prompt-token

# Prove the unit, file permissions, and live argv are safe
sudo python scripts/manage_cloudflared_service.py --check
```

If the connector token was exposed, first rotate it in **Cloudflare Dashboard → Networking → Tunnels** (or with a
short-lived API credential that has `Cloudflare Tunnel Write`), then install the replacement. The DNS-01 token in `.env`
should remain narrowly scoped and must not be expanded for routine tunnel administration.

Practical note: a self-signed certificate is still untrusted by default, but with SANs present the browser warning should now be about trust only, not both trust and hostname mismatch.

If you protect the public hostname with Cloudflare Access, HTTP-01 issuance will fail unless `/.well-known/acme-challenge/*` is excluded from the Access policy. Otherwise use DNS-01 with `CLOUDFLARE_API_TOKEN`.

## Health & Status
- GET http://127.0.0.1:8081/health → { status: "healthy" }
- GET http://127.0.0.1:8081/api/v2/dashboard/status → system status
- GET http://127.0.0.1:8081/api/v2/dashboard/telemetry → telemetry snapshot
- GET http://127.0.0.1:8081/api/v2/telemetry/stream → telemetry stream
- GET http://127.0.0.1:8081/api/v2/telemetry/export → export telemetry data

## Map & Planning
- GET/POST http://127.0.0.1:8081/api/v2/map/zones
- GET/PUT http://127.0.0.1:8081/api/v2/map/locations
- GET/PUT http://127.0.0.1:8081/api/v2/map/configuration → map configuration CRUD
- POST http://127.0.0.1:8081/api/v2/map/provider-fallback → trigger provider fallback
- GET http://127.0.0.1:8081/api/v2/nav/coverage-plan?config_id=default&spacing_m=0.6 → generated coverage preview polyline
- GET/POST/DELETE http://127.0.0.1:8081/api/v2/planning/jobs

Scheduled and compatibility mower-job starts have one execution owner: `JobsService` dispatches through
`MissionService`. For an in-memory compatibility `Job`, `mission_id` retains the linked identity and completion is projected
from that mission. For a persistence-backed schedule, `last_run` means only that `MissionService` accepted a dispatch; the
mission record remains authoritative afterward. A compatibility job may report `COMPLETED`, 100% progress, or success only
after its linked mission reaches `COMPLETED`. Qualification blocks, E-stop, conflicts, missing zones, rejected starts,
mission failure/abort/cancel, and unsupported job types remain explicit non-success outcomes. Elapsed time or synthetic
progress must never be treated as mission evidence.

## Control
- POST http://127.0.0.1:8081/api/v2/control/drive
- POST http://127.0.0.1:8081/api/v2/control/blade
- POST http://127.0.0.1:8081/api/v2/control/emergency-stop
- POST http://127.0.0.1:8081/api/v2/control/return-home → create a canonical blade-off mission; response includes `mission_id`
- POST http://127.0.0.1:8081/api/v2/control/emergency_clear → clear E-stop with confirmation
- GET http://127.0.0.1:8081/api/v2/hardware/robohat → RoboHAT status
- GET http://127.0.0.1:8081/api/v2/autonomy/readiness → blade/platform/pin readiness report
- GET http://127.0.0.1:8081/api/v2/autonomy/qualification → current qualification-evidence evaluation
- POST http://127.0.0.1:8081/api/v2/autonomy/qualification/evidence → store a qualification record
- GET http://127.0.0.1:8081/api/v2/camera/status → camera activity + FPS snapshot
- GET http://127.0.0.1:8081/api/v2/camera/frame → latest raw JPEG snapshot
- GET http://127.0.0.1:8081/api/v2/camera/stream.mjpeg → live MJPEG stream

Return-home requires current pose, configured home, a valid operating boundary, and a safe planned route. It runs through
`MissionService` and `MissionExecutor`; the endpoint never switches a navigation mode as a substitute for execution. Every
return leg is blade-off, and reaching the dock coordinate is not terminal until cached charging truth confirms docking.
If route planning, admission, or dock confirmation fails, the mission remains a non-success and the mower stays stopped.

On live hardware, `lawnberry-camera.service` is the only process that opens the camera. It publishes status, exact frames,
and automatic AI annotations over `/run/lawnberry/camera.sock`; the FastAPI camera and latest-inference endpoints consume
that IPC owner through `CameraClient`. The backend unit waits for the camera unit and must not fall back to opening the
device itself. `SIM_MODE=1` may embed the simulated owner for offline tests only. The camera and backend units both load
`/home/pi/lawnberry/.env`; their `ExecStart` contract then pins `SIM_MODE=0` and the shared
`/run/lawnberry/camera.sock`, so stale `.env` values cannot create a second embedded production owner. Idle power management
uses the same runtime-selected owner and therefore pauses/resumes the standalone service over IPC.
If hardware initialization fails and that owner falls back to generated frames, IPC and the camera status API explicitly
report `sim_mode=true` and `hardware_available=false`; those frames must not appear to come from confirmed hardware.

The Web UI now exposes a virtual joystick for manual drive control. Drag in any direction to stream drive vectors (linear/forward on the Y axis, angular/turn rate on the X axis). The slider underneath scales max velocity (10–100%). Releasing the joystick or pressing **Stop Motors** immediately sends a zero-vector command and clears the motion queue; the backend rate limiter has dedicated bursts for these endpoints to prevent inadvertent HTTP 429 responses during manual driving sessions.

Operational notes:

- The RoboHAT status endpoint now treats the firmware's `rc=disable` acknowledgement as controller-ready instead of leaving the UI stuck on a stale handshake-pending warning.
- Older RoboHAT CircuitPython builds may take about three seconds to begin responding after the USB serial port opens and may emit heartbeat lines like `[RC] steer=...` instead of the newer `get_rc_status` payload. Treat that as compatible firmware, not a missing board.
- Camera snapshot and MJPEG endpoints now emit raw JPEG bytes; if the live feed regresses again, verify intermediate proxies are not recompressing or buffering `/api/v2/camera/stream.mjpeg`.

## Manual drive safety gating

Manual drive now fails closed for **non-zero** movement commands on live hardware when the backend cannot confirm a safe local-control context.

- The RoboHAT controller must be connected and controller-ready before the joystick is enabled in the WebUI.
- The backend blocks non-zero drive commands with HTTP `423` if fresh hardware telemetry is unavailable, usable GPS position
  awareness is missing, or a ToF obstacle reading is at/inside the operator-configured `tof_obstacle_distance_meters`
  cutoff.
- Zero-vector stop commands remain allowed so an operator can still halt motion immediately while the controller is connected.
- The software watchdog is armed by hazardous actuator sources rather than by backend uptime alone. Idle camera, telemetry, or
  WebSocket stalls should not latch `watchdog_timeout`; that reason should indicate missed watchdog heartbeats while drive or
  blade control is armed.
- Autonomous obstacle clearance is calculated from speed, latency, conservative braking, front offset, and margin values in
  `config/limits.yaml`; `tof_obstacle_distance_meters` remains the manual near-field cutoff and is only a minimum floor
  for the autonomous stopping-distance model.

Useful checks:

```bash
curl -s http://127.0.0.1:8081/api/v2/hardware/robohat | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/dashboard/telemetry | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/sensors/health | python -m json.tool
```

If manual motion is blocked with `OBSTACLE_DETECTED`, `LOCATION_AWARENESS_UNAVAILABLE`, or `TELEMETRY_UNAVAILABLE`,
clear nearby obstacles and restore fresh hardware telemetry before retrying.

## Reference Mower Bench Validation

Aaron physically verified the following on the reference mower against `main@a1d01df` on 2026-07-10. The exact blade-power state and remaining bench conditions were not recorded, so this evidence must not be expanded beyond the listed behaviors:

- Forward/reverse drive polarity is correct.
- Left/right steering polarity is correct.
- **Stop Motors** immediately commands neutral.
- The 45° and 90° preset turns complete without the prior delayed-stop interruption.
- Obstacle lockouts stop motion and preserve the unlocked manual-control session as intended.

This is real bench evidence for those specific behaviors, not proof of ground, blade-enabled, geofence, RTK-loss, scheduled-mission, or autonomous mowing readiness. The reference mower has no dedicated physical E-stop, so no physical E-stop test was performed. Aaron has repeatedly verified that its accessible power button removes power from every component downstream of the solar charge controller, shutting down the Raspberry Pi and all mower hardware/motors.

## Mission execution safety feedback

Mission creation/start can succeed before the mower has enough verified autonomy feedback to traverse the first waypoint, so
watch the mission status contract instead of assuming `running` alone means the rover is moving.

- Live mission start and resume fail closed unless a user-confirmed mowing boundary and matching generated safe boundary
  are available. The generated safe-boundary payload records the confirmed-boundary revision hash; if the confirmed
  boundary changes, regenerate the safe boundary before autonomous motion.
- Mission preflight validates complete legs, including the current-position-to-first-waypoint leg, against the safe outer
  boundary and active exclusions. Endpoints inside the yard are not sufficient if the connecting segment crosses an
  exclusion or leaves a concave safe area.
- Nonzero mission drive commands pass through `MotorCommandGateway`, which checks fresh RTK-grade localization, dead
  reckoning state, current footprint containment, ToF obstacle state, and a short predictive swept-motion envelope before
  dispatching motor output.
- A dedicated live safety coordinator runs alongside mission execution. A single continuous ToF acquisition owner is the
  only code that reads both VL53L0X devices over I2C; the fast loop, telemetry, diagnostics, and navigation consume the
  same immutable sample IDs/timestamps. Its fast loop reads only cached ToF plus live IMU safety
  samples so tilt and near-field obstacle stops do not wait for GPS, Victron/power, environmental, camera, persistence,
  HTTP, or WebSocket work. Slow battery/temperature samples are evaluated separately and still fail closed on critical
  thresholds.
- Any localization, GPS freshness, pause, abort, geofence, obstacle, tilt, critical battery, thermal, or mission exception
  hold commands zero drive and blade-off through the command gateway. If blade-off acknowledgement is not confirmed, the
  mission path escalates through the emergency latch.
- Mission start/pause/resume/abort UI success is shown only after the lifecycle endpoint returns the requested canonical
  `MissionStatus`; HTTP errors and mismatched responses are reconciled from the status endpoint and remain visible as
  failures. Manual control never creates a browser-only unlock session: the backend must return `authorized=true` and a
  server-issued session ID, including in Cloudflare Access mode.
- Mission-start heading alignment is an explicit bootstrap step: the mower drives straight, polls the shared sensor manager,
  derives GPS course-over-ground from receiver course or actual coordinate deltas, then snaps the relative BNO085 yaw to
  that GPS movement vector before trusting IMU heading for waypoint turns.
- The bootstrap is blade-off and uses an explicit `heading_bootstrap` command through `MotorCommandGateway`; ordinary
  headingless mission commands remain blocked. Each command renewal requires a genuinely processed BNO085 SHTP game
  rotation report, a straight relative-yaw trace, unique non-cached GPS samples acquired after bootstrap start, and enough
  GPS-age + command-lease + braking reserve to stay under the configured travel cap.
- Default bootstrap travel is at least `0.25 m` and at most `0.60 m`. At the default `0.20 m/s`, `350 ms` lease, `200 ms`
  sensor cadence, and `0.50 m/s²` braking value, the stop reserve is `0.15 m`. Runtime also adds actual GPS sample age.
- While world heading is unknown, clearance is direction-independent around the raw GPS antenna and includes mower
  footprint, RTK uncertainty, fixed geofence allowance, antenna lever arm, and remaining bootstrap travel. This is a
  one-time center-yard alignment envelope, not the mowing-edge clearance or boundary-point stand-off.
- `data/calibration.json` is the canonical heading-alignment record used by both localization updates and mission admission.
  At startup, a newer authoritative snap from the legacy `data/imu_alignment.json` may be promoted without changing its
  original acquisition time and the legacy file is archived after promotion. Reuse additionally requires a finite value,
  an allowlisted source, a nonfuture timestamp, and the current BNO085 reset generation. A process restart or in-process
  IMU reinitialization therefore invalidates prior alignment and requires one fresh blade-off bootstrap. The GPS COG snap
  remains staged in memory until minimum travel is observed and a zero command is acknowledged through the gateway; an
  unconfirmed stop latches emergency and the staged record is discarded.
- During normal waypoint pursuit, GPS course-over-ground is treated as a movement vector/fallback rather than a continuous
  IMU calibration source. This avoids corrupting chassis heading while the mower is arcing, tank-turning, slipping, or
  maneuvering around obstacles.
- Manual ToF uses only the operator-set `tof_obstacle_distance_meters` near-field cutoff. Autonomous ToF uses
  `max(obstacle_min_clearance_m, speed × detection_latency + braking_distance + obstacle_fixed_margin_m)` measured
  from the front sensor face. `obstacle_front_offset_m` records body geometry and is not added to that measured range.
  Defaults are a 0.15 m floor and 0.10 m guard margin; the threshold still expands with speed and uses the configured
  conservative unknown-speed value when command speed is unavailable.
- If waypoint traversal cannot begin safely after the bounded verification window, the mission now fails with explicit detail
  instead of remaining indefinitely `running` / `executing` with no progress.
- RoboHAT drive commands now wait for an explicit firmware PWM acknowledgement before the backend reports them accepted; if
  the RP2040 rejects the command or never acknowledges it, the mission/manual-control path surfaces that as a controller
  failure instead of treating a successful serial write as motion success.
- Mission-style drive commands carry a short backend lease and the RP2040 firmware independently neutralizes stale serial
  motion if PWM renewal stops. Firmware also turns blade output off if blade command renewal stops.
- `GET /api/v2/control/status` reflects the navigation mode/path state, while
  `GET /api/v2/missions/{mission_id}/status` is the authoritative mission lifecycle/detail surface.
- `GET /api/v2/autonomy/readiness` also checks that the live safety loop and single ToF owner are running, each IMU/ToF
  sample is fresh, and each ToF side has at least five bounded-window acquisitions with no more than 25% failures
  before reporting blade-enabled autonomy ready. It also requires current qualification evidence for blade-capable starts.
- `GET /api/v2/autonomy/qualification` evaluates the latest retained evidence against the current commit SHA, sanitized
  hardware-config hash, safety-limits hash, runtime identity hash, and RoboHAT firmware version. Missing, stale, mismatched,
  interrupted, failed, simulation, dirty-tree, or incomplete evidence returns explicit `QUALIFICATION_*` blocker codes.
- Legacy `POST /api/v2/control/start` returns `409` with `MISSION_EXECUTOR_REQUIRED`; use
  `POST /api/v2/missions/{mission_id}/start` so a real mission executor is created.
- Blade-off diagnostics use the same mission start endpoint with
  `POST /api/v2/missions/{mission_id}/start?blade_off_diagnostic=true`. This mode is rejected if any waypoint has
  `blade_on=true`; it is a diagnostic path, not a safety bypass.

Useful checks:

```bash
curl -s http://127.0.0.1:8081/api/v2/control/status | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/missions/<mission-id>/status | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/hardware/robohat | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/dashboard/telemetry | python -m json.tool
curl -s http://127.0.0.1:8081/api/v2/autonomy/qualification | python -m json.tool
```

## Autonomy qualification evidence

Blade-enabled manual blade commands, blade-enabled mission starts, and scheduled mission dispatch now fail closed unless the
backend has current passing physical qualification evidence. The retained evidence lives under
`verification_artifacts/autonomy-qualification/` and is safe to review: user-owned hardware config is hashed after secret
key redaction, not logged or copied into the record.

Run only the non-destructive stages until Aaron is ready for a supervised physical stage:

```bash
sudo systemctl start lawnberry-camera.service lawnberry-backend.service
python scripts/run_autonomy_qualification.py --base-url http://127.0.0.1:8081 --output -
```

Store evidence only after reviewing the output and confirming the backend is a clean deployed commit on the mower:

```bash
python scripts/run_autonomy_qualification.py \
  --base-url http://127.0.0.1:8081 \
  --store \
  --operator aaron \
  --notes "non-destructive qualification"
```

Hazardous stages are intentionally staged. The runner never energizes them automatically. After a supervised checklist stage,
register its retained artifact with metadata bound to the context returned by `GET /api/v2/autonomy/qualification`: exact
`qualification_stage_id`, `commit_sha`, `hardware_config_hash`, `limits_hash`, `runtime_identity_hash`,
`robohat_firmware_version`, `result: "passed"`, and `operator_confirmed: true`. Then record that one result:

```bash
python scripts/run_autonomy_qualification.py \
  --stage wheels_raised_drive \
  --operator-confirmed \
  --stage-result wheels_raised_drive=passed \
  --artifact-id wheels_raised_drive=<verification-artifact-id> \
  --physical-intervention "verified master power cutoff" \
  --operator aaron \
  --store
```

By default the runner carries forward same-context stages from the latest immutable record; use `--fresh` to start a new
sequence. A physical pass without prerequisite stages, an artifact ID, or the configured intervention mechanism is recorded
as failed. The backend independently checks artifact metadata and current clean hardware context before accepting a fully
passing record. Every run attempts cleanup in `finally` by posting neutral drive and blade-off commands through the backend
owner APIs. If cleanup fails, treat the record as invalid and physically verify drive neutral plus blade off before further
work.

Preflight and emergency procedure:

1. Confirm `git rev-parse HEAD` matches the intended deployed commit and `git status --short` is clean.
2. Confirm `SIM_MODE=0`, `config/hardware.yaml`, `config/limits.yaml`, and RoboHAT firmware are the intended physical setup.
3. Confirm the configured independent intervention mechanism is reachable and removes hazardous power. Aaron's current mower
   uses its repeatedly verified master power cutoff; test a dedicated E-stop only on builds where one is installed.
4. Keep the mower wheels raised for drive-polarity and timeout stages; keep the blade physically disabled until the blade
   circuit test stage is explicitly approved.
5. After any exception, cancellation, service restart, rollback, config edit, firmware change, or failed stage, rerun
   qualification before enabling blade-capable operation.

Rollback:

1. Command neutral drive and blade off, then use the configured master cutoff or installed dedicated E-stop before changing
   code.
2. Roll back to the selected commit and restart backend/frontend services.
3. Treat all newer qualification evidence as invalid; commit changes intentionally invalidate the evidence hash.
4. Re-run the non-destructive qualification stages before any blade-off motion, then repeat the staged physical checklist.

## AI
- GET http://127.0.0.1:8081/api/v2/ai/status
- GET http://127.0.0.1:8081/api/v2/ai/datasets
- POST http://127.0.0.1:8081/api/v2/ai/datasets/{datasetId}/export
- POST http://127.0.0.1:8081/api/v2/ai/inference → infer an uploaded image
- POST http://127.0.0.1:8081/api/v2/ai/inference/latest → infer the latest available camera frame
- GET http://127.0.0.1:8081/api/v2/ai/results/recent

The current inference contract is a configured local JSON rule definition executed on the CPU. It does not claim a trained
neural model or active Coral/Hailo acceleration. Automatic camera processing passes sampled exact frame bytes and frame ID
to the standalone owner's injected processor at a bounded cadence within the single latest-frame consumer. It does not
create a task per frame or queue stale inference work, and CPU inference runs off the event loop.
`AI_CAMERA_INFERENCE_FPS` controls sampling and
`AI_CAMERA_INFERENCE_TIMEOUT_SECONDS` bounds how long a selected frame waits before delivery. A timed-out worker remains the
only tracked inference until it exits; its late result is discarded and no replacement worker is queued concurrently.

`processed_for_ai=true` means inference succeeded for that exact frame, including a valid result with zero detected objects.
Disabled, skipped, unavailable, failed, timed-out, late, or frame-mismatched work remains unprocessed, and simulation must
not inject hardcoded detections.

Camera AI results are informational only. They do not set navigation obstacle state, authorize motion, or replace the ToF,
localization, operating-area, qualification, and `MotorCommandGateway` safety paths. Any future promotion into mower safety
requires its own freshness, failure, validation, and physical-qualification contract.

## Settings
- GET/PUT http://127.0.0.1:8081/api/v2/settings → settings profile management
- GET http://127.0.0.1:8081/api/v2/docs/bundle → offline documentation bundle
- POST http://127.0.0.1:8081/api/v2/verification-artifacts → upload verification artifacts

## Systemd
See systemd/*.service and systemd/install_services.sh for installation. Backend service listens on port 8081.

Certificate renewal units:
- `lawnberry-cert-renewal.service` — on-demand renewal/validation + nginx reload + fallback
- `lawnberry-cert-renewal.timer` — runs the renewal daily with randomized delay

## WebSocket Topics
The V2 API provides WebSocket subscriptions for real-time data:
- `telemetry`: Real-time sensor and system telemetry data
- `control`: Control command echoes and lockout status
- `maps`: Map updates and provider status changes
- `ai`: AI processing results and status updates

Connect to ws://127.0.0.1:8081/api/v2/ws/telemetry and send:
```json
{
  "action": "subscribe",
  "topic": "telemetry"
}
```

## Latency Targets
Per constitutional requirements:
- **Pi 5**: API responses ≤250ms (p95)
- **Pi 4B**: API responses ≤350ms (p95)
- **WebSocket**: ≤100ms message delivery

Use `scripts/test_performance_degradation.py` to validate latency compliance.

## Telemetry Export
Export telemetry data for analysis:
```bash
curl -X POST http://127.0.0.1:8081/api/v2/telemetry/export \
  -H "Content-Type: application/json" \
  -d '{"start_time": "2025-01-01T00:00:00Z", "end_time": "2025-01-31T23:59:59Z", "format": "json"}'
```

## Offline Documentation
Generate offline documentation bundle:
```bash
cd .
python scripts/generate_docs_bundle.py
# Output: verification_artifacts/docs-bundle/lawnberry-docs-{timestamp}.tar.gz
```

## Emergency Stop Recovery
When the software emergency-stop latch is active, all motion is locked out. To clear it:

1) Confirm the mower is stationary, the blade is stopped, and the area is safe.
2) If the build includes the optional physical E-stop, release/reset it. Aaron's reference mower has no dedicated E-stop; its accessible power button is the verified local physical intervention method and removes power from every component downstream of the solar charge controller, including the Raspberry Pi and all mower hardware/motors.
3) If power was removed, restart the mower and re-run hardware health and autonomy-readiness checks before enabling motion.
4) Clear the software latch via API with the explicit confirmation flag:

```bash
curl -X POST http://127.0.0.1:8081/api/v2/control/emergency_clear \
  -H "Content-Type: application/json" \
  -d '{"confirmation": true}'
```

The system will return status EMERGENCY_CLEARED.

## Blade Safety Lockout
By default, blade engagement is locked out until safety preconditions are satisfied (no emergency stop, motors not active, authorization present). If a blade command is rejected, check active interlocks and remediate hazards before retrying.
Blade-enabled autonomy also requires `GET /api/v2/autonomy/readiness` to report no blocker reason codes, including no
`HARDWARE_PIN_CONFLICT`, an approved configured blade backend, and an online blade controller. Software controls do not replace
a quick, accessible physical intervention method. Aaron's reference mower uses a verified main power cutoff downstream of
its solar charge controller; a dedicated hardwired E-stop is optional but strongly recommended when a build has no equally
rapid way to remove hazardous actuator power.

## IMU Calibration
For best orientation accuracy, calibrate the IMU after installation:
- Warm up system for 2 minutes
- Perform figure-eight motions and gentle tilts on all axes
- In simulation (`SIM_MODE=1`), calibration is bypassed; in hardware mode (`SIM_MODE=0`), verify orientation health in `/api/v2/dashboard/telemetry`

## GPS Setup
- Preferred: ZED-F9P via USB; alternative: Neo-8M via UART
- If the displayed/navigation point is offset because the GPS antenna is not at the mower body
  center, set `gps.antenna_offset_forward_m` and `gps.antenna_offset_right_m` in
  `config/hardware.yaml`. Use meters; positive is forward/right from the mower point to the antenna.
  For an antenna 1.5 ft behind the desired mower point, use `gps.antenna_offset_forward_m: -0.46`.
- Localization owns the canonical pose: `body_center` is published only when the antenna-to-body correction is either not
  configured or can be applied with a verified world-frame heading. When heading is unavailable, telemetry exposes
  `antenna_position` with `antenna_correction_state="pending_heading"` instead of fabricating a mower-center coordinate.
- If only satellite imagery is shifted, use the display-only map alignment profile for the active source. Legacy
  `satellite_display_north_m` / `satellite_display_east_m` values are migrated into `legacy_satellite` and, when
  unambiguous, the current imagery source; they do not change navigation coordinates.
- Custom orthophoto/orthomosaic sources can be configured under `/api/v2/settings/maps` as `custom_sources` with an
  `xyz` or ArcGIS tile URL. Select them via `active_source_id` / `mission_planner.source_id` such as
  `custom:local_orthophoto`; each source keeps its own alignment profile.
- Stationary RTK reference averaging is available at `POST /api/v2/sensors/gps/stationary-average`. It accepts only fresh,
  unique, uncached, stationary RTK-fixed antenna samples observed from the canonical GPS owner's cache, rejects duplicate
  identities and spatial outliers, and returns an averaged reference measurement without writing any hidden GPS offset.
- `GET /api/v2/sensors/gps/status` is read-only: it reports the real sample age, cache/live state, sample ID, and serial
  open/read-in-progress state, lock contention, open/reopen counts, and last recovery reason without taking another serial
  read. A configured USB GPS remains authoritative across brief NMEA gaps; read exceptions or stale lock contention close
  only the GPS reader handle so the continuously running telemetry owner can promptly reacquire it instead of presenting
  one cached fix forever.
- NTRIP corrections:
  - If the rover already receives corrections directly (configured in u-center), no further changes are needed on the Pi.
  - When letting the Pi forward RTCM data, ensure `gps_ntrip_enabled: true` in `config/hardware.yaml` and update the `.env` file with the required `NTRIP_*` caster settings (host, mountpoint, credentials, serial device).
  - Restart the backend service after modifying `.env` so the connection is re-established.
- Validate GPS health via GET /api/v2/sensors/health and /api/v2/fusion/state

## Boundary point verification

The Maps UI generates a safe boundary with a default **0.05 m additional inset**. This value is not the mower radius:
runtime authorization separately includes the configured mower footprint, RTK uncertainty, fixed geofence allowance,
and swept-motion prediction.

1. Save the confirmed mowing boundary, then click **Generate Safe Boundary**.
2. Click **Prepare Drive-To-Confirm**, acknowledge on-site supervision, physical blade disablement, a clear route, the
   available master cutoff, and that the first leg may need a bounded straight blade-off heading bootstrap. Creating the
   session causes no motion. The checklist resets whenever it opens and must be freshly completed for every session.
3. Click **Go To Next Point** for one low-speed leg. The target is a computed center-safe stand-off inside the authoritative
   safe polygon; the mower never drives its center to the recorded physical edge. The UI disables repeat clicks while the
   request is pending, and the backend serializes verification mutations plus status reconciliation so one operator action
   creates at most one leg and polling cannot interrupt an in-flight admission. The response is reconciled against the
   observed asynchronous mission lifecycle instead of returning a stale idle state.
   If no reusable canonical alignment exists, the normal mission path performs the acknowledged center-yard bootstrap
   through `MotorCommandGateway` before approaching the point. The current `0.55 m` verification stand-off is the
   mower-center-to-reference distance (`0.35 m` footprint + `0.10 m` fixed allowance + RTK uncertainty + verification
   margin); it is not an extra mowing inset and does not prevent later edge coverage. Position-derived bootstrap COG
   retains its live RTK baseline across sub-0.15 m crawl steps so displacement can accumulate; the 0.05 m/s crawl floor
   remains subordinate to the unique-frame, displacement, straightness, radial-budget, and confirmed-stop gates.
4. Wait for the UI point state to advance through live status to `arrived`. `Confirm Point` stays disabled until then. A
   failed/interrupted leg and its mission detail remain visible after the active target clears so the cause is not hidden.
5. Confirming first reasserts zero drive and blade off, then requires at least five unique live stationary RTK-fixed samples
   at 0.05 m accuracy or better. Evidence records antenna and body-center coordinates plus residuals.
6. After a backend restart, a previously running leg becomes `interrupted` and must be explicitly retried. It is never
   silently treated as arrived or confirmable.

Keep the mower raised or wheels clear for the first blade-off leg, remain at the cutoff, and test one point at a time.

## Geofence Definition
Use the map configuration API to define boundaries and exclusion zones:
```bash
curl -X PUT http://127.0.0.1:8081/api/v2/map/configuration \
  -H "Content-Type: application/json" \
  -d '{"provider":"osm","zones":[{"zone_id":"boundary1","zone_type":"boundary","geometry":{"type":"Polygon","coordinates":[[[-122.4195,37.7750],[-122.4190,37.7750],[-122.4190,37.7745],[-122.4195,37.7745],[-122.4195,37.7750]]]}}]}'
```

## Telemetry Latency Troubleshooting
If dashboard telemetry latency exceeds targets:
- Reduce cadence via settings or WebSocket set_cadence
- Check CPU/memory usage; Pi 4B may require lower rates
- See also Performance Optimization below

## Performance Optimization
- Prefer Pi 5 for higher telemetry rates (target ≤250ms p95)
- On Pi 4B, reduce telemetry rate and background tasks (target ≤350ms p95)
- Use scripts/test_performance_degradation.py to measure and tune

## Documentation Troubleshooting
If documentation bundle generation fails:
- Check scripts/generate_docs_bundle.py output
- Ensure docs/ exists and markdown files are readable
- Re-run: python scripts/generate_docs_bundle.py --format tarball

## Verification Artifacts
Create verification artifacts to record validation evidence:
```bash
curl -X POST http://127.0.0.1:8081/api/v2/verification-artifacts \
  -H "Content-Type: application/json" \
  -d '{"type":"quickstart","location":"./verification_artifacts","summary":"Quickstart passed","linked_requirements":["FR-001","FR-047"],"created_by":"operator"}'
```

## Settings Management
- GET/PUT /api/v2/settings to retrieve/update the active profile
- Version conflicts return HTTP 409; update profile_version and retry
- Branding checksum validation ensures asset integrity

## Branding Assets
Branding assets are validated via checksum in settings. Provide a 64-character SHA-256 string; invalid lengths return error BRANDING_ASSET_MISMATCH.

## Constitutional Compliance
All API endpoints include remediation metadata in error responses:
```json
{
  "detail": "Validation error message",
  "remediation_link": "/docs/troubleshooting#validation-errors"
}
```

## CI/CD Gating and Quality Checks

### Automated CI Gates

The CI pipeline includes the following mandatory quality gates that must pass before merge:

#### 1. Lint and Format
- **Ruff linting**: Enforces Python code style
- **Ruff formatting**: Ensures consistent code formatting
- **Black formatting**: Additional Python formatting validation
- **Mypy type checking**: Strict type checking (currently non-blocking)
- **TODO policy**: Blocks unapproved TODOs (only TODO(v3) allowed)

#### 2. Constitutional Compliance
- **Forbidden packages**: Blocks pycoral/edgetpu (ARM64 compliance)
- **Import scanning**: Detects forbidden imports in source code
- **ARM64 reminder**: Documents platform-specific requirements

#### 3. Test Suite
- **Contract tests**: Validates all V2 API endpoints (tests/contract/)
- **Integration tests**: Validates service coordination (tests/integration/)
- **Unit tests**: Validates core services and stores (tests/unit/)
- **SIM_MODE**: All tests run in simulation mode for CI

#### 4. Telemetry Export
- **Export functionality**: Validates telemetry data export
- **Format validation**: Ensures export formats are valid (JSON/CSV)

#### 5. UI Regression
- **Frontend unit tests**: Validates Vue 3 components and stores
- **Build verification**: Ensures frontend builds without errors
- **Bundle validation**: Checks dist/ artifacts are created

#### 6. Performance Validation
- **Latency testing**: Validates API latency ≤350ms (CI target)
- **Degradation detection**: Alerts on performance regressions
- **Production targets**: ≤250ms (Pi 5), ≤350ms (Pi 4B)

#### 7. Documentation Drift
- **Markdown formatting**: Validates markdown consistency
- **Drift detection**: Prevents uncommitted documentation changes
- **Bundle freshness**: Ensures documentation bundle is up-to-date (<90 days old)

### Branch Protection Rules

Configure the following branch protection rules for the main branch:

1. **Require status checks to pass before merging**:
   - lint-and-format
   - constitutional-compliance
   - test
   - telemetry-export-test
   - ui-regression-test
   - performance-validation
   - contract-test-suite
   - integration-test-suite
   - docs-drift-check

2. **Require branches to be up to date before merging**: Enabled

3. **Require linear history**: Recommended

4. **Require signed commits**: Optional but recommended

### Remediating Failed CI Checks

#### Lint/Format Failures
```bash
# Auto-fix linting issues
ruff check --fix .

# Auto-format code
ruff format .
black .

# Check types
mypy --strict src
```

#### Test Failures
```bash
# Run specific test suite
pytest tests/contract/ -v
pytest tests/integration/ -v
pytest tests/unit/ -v

# Run with detailed output
pytest tests/contract/test_rest_api_telemetry.py -vv

# Frontend tests
cd frontend && npm test
```

#### Performance Failures
```bash
# Run performance tests locally
python scripts/test_performance_degradation.py --threshold-ms 250

# Check WebSocket performance
python scripts/test_websocket_load.py
```

#### Documentation Drift
```bash
# Format documentation
mdformat docs spec

# Regenerate documentation bundle
python scripts/generate_docs_bundle.py

# Check bundle freshness
python scripts/generate_docs_bundle.py --check-only
```

#### UI Regression
```bash
# Rebuild frontend
cd frontend
npm ci
npm run build

# Run tests
npm test
```

### Local Pre-Commit Validation

Run the full CI suite locally before pushing:

```bash
# Backend checks
ruff check .
ruff format --check .
black --check .
SIM_MODE=1 pytest tests/

# Frontend checks
cd frontend
npm test
npm run build

# Performance validation
python scripts/test_performance_degradation.py --threshold-ms 250

# Documentation validation
python scripts/generate_docs_bundle.py --check-only
```

### CI Performance Metrics

Target CI pipeline execution times:
- **Lint and Format**: <2 minutes
- **Test Suite**: <5 minutes
- **UI Regression**: <3 minutes
- **Performance Validation**: <2 minutes
- **Total Pipeline**: <15 minutes

### Monitoring CI Health

Track CI health metrics:
- **Pass rate**: Target >95%
- **Pipeline duration**: Monitor for degradation
- **Flaky tests**: Investigate and fix intermittent failures
- **Resource usage**: Monitor GitHub Actions minutes

### Emergency Bypass Procedures

⚠️ **Use only in emergency situations**

If CI is blocking a critical hotfix:
1. Document the reason for bypass
2. Create a follow-up issue to address the failure
3. Get approval from maintainer
4. Use admin override to merge
5. Fix the issue immediately after deployment

**DO NOT** bypass CI for:
- Constitutional compliance failures
- Security vulnerabilities
- Performance regressions
- Test failures in affected code paths

## Notes
- All commands and scripts are designed for ARM64 (Raspberry Pi OS Bookworm).
- Avoid adding platform-specific dependencies.
- All V2 API endpoints follow constitutional audit logging requirements.
- Settings profiles use versioning to prevent concurrent modification conflicts.
- CI gates enforce constitutional compliance and quality standards per FR-013.
