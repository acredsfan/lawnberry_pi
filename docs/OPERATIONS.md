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

## On-device Wi-Fi recovery

The mower has one production Wi-Fi client: the external high-gain USB radio `wlan1`, using the
`wlan1-primary` NetworkManager profile on the dual-band `Butters Read-Link` eero mesh. The internal
`wlan0` radio is shielded by the mower and solar panel, so it is deliberately unmanaged after
commissioning and must not be promoted as a fallback.

`/etc/NetworkManager/conf.d/90-lawnberry-wlan1-only.conf` makes that choice persistent. The retired
`90-wifi-failover` dispatcher and `100-manage-wlan0.rules` udev override must remain absent.

`lawnberry-wifi-recovery.service` observes local state only: USB enumeration, `wlan1`, NetworkManager
association, IPv4 assignment, and a default route. It performs these bounded actions:

- missing `2357:0138`: cycle only USB hub `3`, port `1`, settle udev, and load `88x2bu`
- enumerated adapter without `wlan1`: load the driver once, then use the same targeted USB cycle
- NetworkManager already activating/deactivating `wlan1`: wait without issuing a competing activation
- disconnected/no IPv4/no route: activate only `wlan1-primary` on `wlan1`
- healthy local route: take no action

USB cycles have a five-minute cooldown and a persistent three-per-hour budget. The service cannot
reboot the Pi, restart NetworkManager globally, reset another USB port, enable `wlan0`, or use an
internet/DNS probe as evidence that the radio failed. The legacy `/opt/wifi-watchdog` service must
remain disabled and masked.

The `88x2bu` policy forces this adapter to USB2 mode even when physically connected to a USB3 port
and disables driver and USB autosuspend. If the adapter is moved, identify its new dedicated port
with `uhubctl` and update `LAWNBERRY_WIFI_USB_HUB`/`LAWNBERRY_WIFI_USB_PORT` in the unit before enabling
recovery; never guess a port because the neighboring hub port carries GPS.

Useful checks:

```bash
nmcli -f DEVICE,TYPE,STATE,CONNECTION dev status
nmcli -f NAME,DEVICE,AUTOCONNECT connection show
lsusb -d 2357:0138
ip -4 route show default dev wlan1
systemctl status lawnberry-wifi-recovery.service
journalctl -u lawnberry-wifi-recovery.service -n 50 --no-pager
sudo cat /run/lawnberry-wifi-recovery/status.json
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
- GET http://127.0.0.1:8081/health → aggregate compatibility health; inspect `overall_status` and subsystem detail
- GET http://127.0.0.1:8081/api/v2/system/info → exact serving commit, build source, version, and process start time
- GET http://127.0.0.1:8081/api/v2/dashboard/status → system state with source, sample age, freshness, and nullable unknowns
- GET http://127.0.0.1:8081/api/v2/dashboard/telemetry → telemetry snapshot with source/freshness metadata
- GET http://127.0.0.1:8081/api/v2/telemetry/stream → telemetry stream
- GET http://127.0.0.1:8081/api/v2/telemetry/export → export telemetry data

An HTTP 200 means the endpoint answered, not that physical hardware is present. `source=simulated` is test data,
`source=unavailable` is not a measurement, and stale or null fields must remain unknown in the UI. Compare the
`commit_sha` from `/api/v2/system/info` with the intended deployed commit before accepting qualification evidence.

## Map & Planning
- GET/POST http://127.0.0.1:8081/api/v2/map/zones
- GET/PUT http://127.0.0.1:8081/api/v2/map/locations
- GET/PUT http://127.0.0.1:8081/api/v2/map/configuration → map configuration CRUD
- POST http://127.0.0.1:8081/api/v2/map/provider-fallback → trigger provider fallback
- GET http://127.0.0.1:8081/api/v2/nav/coverage-plan?config_id=default&spacing_m=0.6 → generated coverage preview polyline
- GET/POST/DELETE http://127.0.0.1:8081/api/v2/planning/jobs
- GET http://127.0.0.1:8081/api/v2/planning/capabilities → only patterns and route-safety features implemented by this build
- POST http://127.0.0.1:8081/api/v2/planning/jobs/{job_id}/start|pause|resume|cancel

Scheduled and compatibility mower-job starts have one execution owner: `JobsService` dispatches through
`MissionService`. For an in-memory compatibility `Job`, `mission_id` retains the linked identity and completion is projected
from that mission. A missing `MissionService` dependency is a startup wiring failure and aborts before any scheduled
occurrence is claimed. Persistence-backed schedules atomically claim one occurrence per scheduled instant. Multi-zone jobs run
one ordered child mission per zone; the first path leg and every inter-zone approach are blade-off transit. `last_run` means
only that `MissionService` accepted the first child. The occurrence exposes `mission_ids`, `zones_completed`, progress, and
terminal detail, and restart recovery reconciles the active child before any later zone is admitted. A job may report
`completed` only after every linked child reaches `completed`. Qualification blocks, E-stop, conflicts, missing zones,
rejected starts, mission failure/abort/cancel, and unsupported job types remain explicit non-success outcomes. A blocked
occurrence is durable and is not retried every scheduler poll; a rejected start deletes the idle mission record. Elapsed
time, browser-local mutation, or synthetic progress must never be treated as mission evidence.

All persisted mission-definition mutations share the mower-wide lifecycle lock. Create, update, single/bulk delete,
return-home creation, and start/resume/pause/abort cannot interleave between admission checks and navigation-task
ownership; an active mission is skipped or rejected instead of being changed or removed underneath motion.

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
and automatic AI results over `/run/lawnberry/camera.sock`; the FastAPI camera and perception endpoints consume
that IPC owner through `CameraClient`. The backend unit waits for the camera unit and must not fall back to opening the
device itself. `SIM_MODE=1` may embed the simulated owner for offline tests only. The camera and backend units both load
`/home/pi/lawnberry/.env`; their `ExecStart` contract then pins `SIM_MODE=0` and the shared
`/run/lawnberry/camera.sock`, so stale `.env` values cannot create a second embedded production owner. Idle power management
uses the same runtime-selected owner and therefore pauses/resumes capture and gates camera-owner inference over IPC.
Opening either the Control MJPEG route or snapshot route registers viewer demand through `PowerManager`, starts capture,
and issues an immediate AI-owner enable attempt; streaming does not wait for a detector result, while inference readiness
becomes true only after a timely exact-frame result. After the final viewer/mission demand expires, capture and inference
share one 30-second idle boundary. Day/night policy uses wrap-normalized solar right ascension and civil twilight rather
than wall-clock guesses, so daylight inference is not accidentally power-paused.
If hardware initialization fails and that owner falls back to generated frames, IPC and the camera status API explicitly
report `sim_mode=true` and `hardware_available=false`; those frames must not appear to come from confirmed hardware.

The Web UI now exposes a virtual joystick for manual drive control. Drag in any direction to stream drive vectors (linear/forward on the Y axis, angular/turn rate on the X axis). The slider underneath scales max velocity (10–100%). Releasing the joystick or pressing **Stop Motors** immediately sends a zero-vector command and clears the motion queue; the backend rate limiter has dedicated bursts for these endpoints to prevent inadvertent HTTP 429 responses during manual driving sessions.

Operational notes:

- The RoboHAT status endpoint now treats the firmware's `rc=disable` acknowledgement as controller-ready instead of leaving the UI stuck on a stale handshake-pending warning.
- Older RoboHAT CircuitPython builds may take about three seconds to begin responding after the USB serial port opens and may emit heartbeat lines like `[RC] steer=...` instead of the newer `get_rc_status` payload. Treat that as compatible firmware, not a missing board.
- Camera snapshot and MJPEG endpoints now emit raw JPEG bytes; if the live feed regresses again, verify intermediate proxies are not recompressing or buffering `/api/v2/camera/stream.mjpeg`.
- The UI's `IPC clients` count is the number of local camera-owner socket clients, not a browser-viewer count. Snapshot
  fallback remains active after its own image load and stops only after the primary MJPEG source actually recovers.

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
- `GET /api/v2/power/state` is the canonical operator view of battery source, sample age, SOC, remaining energy, and reserve. Mission admission uses the same cached state plus a conservative path/return forecast. Reaching the return reserve first stops drive and blade and starts the normal blade-off return-home mission; reaching critical SOC latches an emergency stop instead.
- Any localization, GPS freshness, pause, abort, geofence, obstacle, tilt, critical battery, thermal, or mission exception
  hold commands zero drive and blade-off through the command gateway. If blade-off acknowledgement is not confirmed, the
  mission path escalates through the emergency latch.
- Mission start/pause/resume/abort UI success is shown only after the lifecycle endpoint returns the requested canonical
  `MissionStatus`; HTTP errors and mismatched responses are reconciled from the status endpoint and remain visible as
  failures. Manual control never creates a browser-only unlock session: the backend must return `authorized=true` and a
  server-issued session ID, including in Cloudflare Access mode.
- Mission lifecycle mutations are serialized across the single mower. Admission rechecks task/status conflicts while
  holding the lifecycle lock, rejects a second running/paused mission, and creates exactly one tracked navigation task;
  concurrent requests cannot overwrite task ownership.
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
  before reporting blade-enabled autonomy ready. Blade-capable starts also require current schema-v2
  `full_blade_autonomy` evidence.
- `GET /api/v2/health` keeps IMU transport and calibration truth distinct: an online BNO085 that reports
  `uncalibrated` is degraded and remains unusable for autonomous heading until valid calibration evidence returns.
- `GET /api/v2/autonomy/qualification` evaluates typed blade-off, supervised-prerequisite, and full evidence against the
  current commit SHA, sanitized hardware-config hash, safety-limits hash, runtime identity hash, and RoboHAT firmware version.
  Missing, schema-v1, stale, mismatched, interrupted, failed, simulation, dirty-tree, or incomplete evidence returns explicit
  fail-closed reason codes.
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

## Two-phase autonomy qualification

Schema v2 separates evidence from temporary test authority. Ordinary manual blade activation, blade-capable mission starts,
and scheduled dispatch require current `full_blade_autonomy` evidence. The only pre-full-qualification blade path is one
authenticated, local, session-bound supervised-test permit; it is not a general blade override and it cannot be inherited by
a mission or schedule.

| Level | Meaning | Authority |
| --- | --- | --- |
| `blade_off_diagnostic` | Non-destructive configuration, neutral-service, and sensor checks. | Blade-off diagnostics only. |
| `supervised_blade_test_prerequisite` | All required blade-off, wheels-raised, boundary, obstacle, shutdown, scheduler, and WebUI recovery evidence is current. | May qualify an operator to request one supervised-test permit; does not authorize an ordinary blade command or mission. |
| `full_blade_autonomy` | Prerequisite evidence plus current artifact-backed `supervised_blade_enabled` evidence and a matching server cleanup receipt. | Satisfies the qualification portion of ordinary blade/mission/scheduler admission; all independent live readiness and safety gates still apply. |

`GET /api/v2/autonomy/qualification` reports `requested_level`, `available_level`, `prerequisite_ok`,
`full_autonomy_ok`, distinct reason-code lists, the redacted permit status, and `camera_ai_safety_role: "advisory"`.
Camera degradation may be recorded as operational evidence, but camera/AI does not replace or weaken ToF, geofence,
localization, live-safety, or gateway stops.

Retained records live under `verification_artifacts/autonomy-qualification/`. Hardware configuration is hashed only after
secret-key redaction. Never put credentials, raw reusable permit tokens, or private machine identity in notes, artifacts, or
logs.

### Disabled-by-default permit bounds

The tracked limits intentionally ship fail closed:

```yaml
supervised_test_enabled: false
supervised_test_permit_ttl_s: 0
supervised_test_max_duration_s: 0
supervised_test_max_speed_mps: 0.0
```

Do not replace these zeros with guessed values. Aaron must first approve the actual mower, test lane, cutoff/blade-isolation
method, supervision controls, maximum issuance TTL, active duration, and speed. When enabled, every bound must be positive and
the supervised speed cannot exceed the existing blade-off bootstrap speed ceiling. A limits edit changes `limits_hash`, so
restart the backend and repeat the prerequisite evidence in that final approved context before requesting a permit.

### Evidence runner: recording only

Run only non-destructive collection until a physical stage is deliberately approved:

```bash
sudo systemctl start lawnberry-camera.service lawnberry-backend.service
python scripts/run_autonomy_qualification.py --base-url http://127.0.0.1:8081 --output -
```

Store evidence only after confirming `SIM_MODE=0`, the intended clean commit, the final hardware/limits configuration, runtime
identity, and RoboHAT firmware:

```bash
python scripts/run_autonomy_qualification.py \
  --base-url http://127.0.0.1:8081 \
  --store \
  --operator aaron \
  --notes "non-destructive qualification"
```

The runner never activates a permit and never energizes drive or blade hardware. For a physical stage, it only records the
operator's explicit pass/fail/interrupted result and an existing retained artifact. Artifact metadata must match the current
server context exactly: `qualification_stage_id`, `commit_sha`, `hardware_config_hash`, `limits_hash`,
`runtime_identity_hash`, `robohat_firmware_version`, `result: "passed"`, and `operator_confirmed: true`.

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

By default the runner carries forward same-context stages from the latest immutable schema-v2 record; use `--fresh` to begin
a new sequence. It attempts neutral drive and blade-off cleanup through backend owner APIs in `finally`, but that software
attempt is not proof that a physical actuator stopped. A cleanup error means interrupted/failed evidence and requires physical
neutral/blade-off confirmation before further work.

### Authenticated permit lifecycle and local actuation

Use the canonical login/session from `docs/authentication-config.md`. Every endpoint below requires a valid, non-revoked
operator session. Issue, activate, drive, blade, and complete additionally require a loopback, private, or link-local client
address after the canonical proxy identity rules are applied. Status and revoke intentionally remain available to an
authenticated remote operator so loss of LAN locality cannot prevent inspection or a safe stop. A public/remote request can
never create, activate, or use the permit.

| Step | Endpoint | Request/response contract |
| --- | --- | --- |
| Inspect | `GET /api/v2/autonomy/qualification/supervised-test/permit` | Returns only redacted status metadata, including state (`absent`, `issued`, `active`, `completed`, `revoked`, or `expired`); polling never extends a deadline. |
| Issue | `POST /api/v2/autonomy/qualification/supervised-test/permit` | Requires `operator_confirmed`, `local_supervision_confirmed`, and `physical_intervention_mechanism`. It succeeds only in hardware mode with current prerequisite evidence, full qualification not already current, approved nonzero limits, idle missions/actuators, and no existing permit. The bearer `permit_token` is returned once. |
| Activate | `POST /api/v2/autonomy/qualification/supervised-test/permit/activate` | Requires the issued `permit_token` from the same authenticated session. Activation is one-use and starts the approved active-duration deadline. |
| Bounded drive | `POST /api/v2/autonomy/qualification/supervised-test/drive` | Requires the active token plus `left_normalized`, `right_normalized`, and a `duration_ms` no longer than the command lease. Physical speed is bounded by the approved permit ceiling. |
| Blade state | `POST /api/v2/autonomy/qualification/supervised-test/blade` | Requires the active token and explicit `active`. Dispatch still goes through `MotorCommandGateway` and all live admission checks. |
| Complete | `POST /api/v2/autonomy/qualification/supervised-test/complete` | Requires the active token and `cleanup_confirmed`. The server first commands neutral and blade off through the gateway. A receipt is evidence-eligible only when the permit authorized at least one nonzero drive command and one blade-enable command and both cleanup commands were acknowledged. |
| Revoke | `POST /api/v2/autonomy/qualification/supervised-test/revoke` | Requires any authenticated operator session and a short `reason`; neither local-network identity nor the permit token is required, so another operator can stop/revoke remotely. It commands neutral and blade off before revocation. |

Do not copy a permit token into logs or retained evidence. The permit-issue intervention description is retained only as a
SHA-256 binding in the permit audit/receipt; status exposes only whether it was confirmed. The token is bound to the issuing session, prerequisite record, commit,
clean-tree state, hardware configuration, safety limits, runtime identity, hardware mode, and RoboHAT firmware. Issuance and
activation are serialized with the mower-wide mission lifecycle lock. A permit is memory-only: backend restart starts with no
permit. Active expiry has a gateway deadline cleanup that requests neutral/blade off, while bounded per-command drive and blade
leases independently expire stale output. Expiry, reuse, session/context drift, E-stop, live-safety fault, command timeout/NACK,
controller loss, unconfirmed cleanup, shutdown, or emergency cleanup makes the permit terminal and requires explicit operator
review plus a new permit.

After a completed supervised run, retain a separate physical artifact for `supervised_blade_enabled`. Its registry metadata must
include the returned `supervised_test_receipt_id` in addition to the normal context fields. The eligible receipt proves only that
the bounded server path authorized both drive and blade-enable work and completed acknowledged cleanup; it does not prove that
the blade test passed. Aaron still records the
physical result. Full qualification rejects missing, mismatched, reused-context, or ineligible receipts.

After the registry artifact exists, record the operator-reviewed stage result without passing the permit token to the runner:

```bash
python scripts/run_autonomy_qualification.py \
  --stage supervised_blade_enabled \
  --operator-confirmed \
  --stage-result supervised_blade_enabled=passed \
  --artifact-id supervised_blade_enabled=<verification-artifact-id> \
  --physical-intervention "verified master power cutoff" \
  --operator aaron \
  --store
```

Use `failed` or `interrupted` instead of `passed` whenever that is the physical truth. The backend validates the referenced
artifact and receipt; the runner cannot promote an API success into a pass.

Qualification audit events record the schema/level, record ID, stage, reason codes, context hashes, redacted permit ID, permit
lifecycle transition, acknowledgment/lease result, cleanup outcome, scheduler denial, and advisory camera role where relevant.
They must not record the reusable permit token, NTRIP or Cloudflare credentials, API secrets, raw machine identity, or other
operator secrets. Use the redacted status endpoint and reason codes for troubleshooting; do not increase log verbosity in a
way that exposes request bodies carrying the token.

### Emergency, interruption, and recovery

1. Operate the verified master cutoff or installed dedicated E-stop whenever immediate physical intervention is needed.
   Software must never claim that the physical cutoff operated.
2. If the backend is responsive, issue the authenticated revoke request locally or remotely. It requests zero drive and blade
   off through the gateway before invalidating the permit; do not delay physical intervention to make this request.
3. Verify drive neutral and blade stopped physically. Treat any missing acknowledgment, process death, serial loss, or cleanup
   error as unconfirmed even though command leases and the RoboHAT watchdog should independently expire output.
4. Inspect the E-stop latch, live-safety reason codes, controller health, and redacted permit state. Clear a software E-stop
   only after the physical cause is corrected and the area is safe.
5. Restart, expiry, emergency, safety fault, config/limits/firmware change, context drift, or interruption always requires a
   new permit and operator review. Never resume a hazardous stage or mission automatically.

Scheduled jobs cannot issue, inherit, consume, or coexist with an issued/active supervised-test permit. Scheduler startup also
requires confirmed hardware-neutral/blade-off state and power readiness. Dispatch remains blocked until current full
qualification is accepted, and unattended use requires additional repeated field evidence plus Aaron's explicit approval.

### Ordered physical checklist for Aaron

Run every physical stage on the final clean commit with `SIM_MODE=0`, current `config/hardware.yaml`, final approved
`config/limits.yaml`, the actual RoboHAT firmware, a clear work area, and the verified cutoff immediately reachable.

1. **Configuration and service neutral:** verify the Pi profile, pins, serial/I2C/USB devices, firmware, blade backend,
   cutoff, clean tree, and health/readiness APIs. With wheels raised and blade power isolated, prove start/restart/stop stays
   neutral and blade off.
2. **Wheels-raised drive and fail-safe:** confirm drive directions, bounded commands, lease expiry, API E-stop, backend
   termination, serial loss, and the master cutoff. Retain acknowledgments and stopping evidence.
3. **Stationary outdoor RTK/geofence:** keep drive and blade disabled; collect unique RTK-fixed samples and verify antenna/body
   correction, safe boundary, exclusions, stationary drift, and loss-of-fix rejection.
4. **Blade-off boundary bootstrap:** first wheels raised, then on clear ground with blade power disabled; verify low-speed COG
   accumulation, bounded travel/straightness/radial envelope, confirmed stop, truthful UI state, and no duplicate admission.
5. **Blade-off straight-line and obstacle test:** measure cross-track error and stop distance; test stale/lost ToF, obstacle
   appearance, RTK loss, network loss, and backend/process failure.
6. **Scheduler/WebUI recovery:** run only a blade-off multi-zone diagnostic occurrence. Verify exact-due dispatch, durable
   ordered children, blade-off transit, pause/resume/cancel, restart/network recovery, and no duplicate, orphan, or unsafe
   automatic restart.
7. **Supervised blade-enabled test:** only after steps 1–6 pass, Aaron approves nonzero bounds, the schema-v2 prerequisite is
   current, and one operator is stationed at the cutoff with no bystanders or pets. Use the minimum approved lane, speed, and
   duration; verify blade acknowledgment, motion gating, obstacle/E-stop response, command expiry, and cleanup. Retain a
   pass/fail/interrupted artifact plus the matching cleanup receipt; never infer a pass from the API response.
8. **Limited controlled mowing:** only after the backend accepts current `full_blade_autonomy` evidence. Begin with one short,
   supervised daylight mission inside the verified boundary. Do not approve unattended scheduling until repeated controlled
   runs satisfy the separate acceptance decision.

Software tests, simulation, replay, generated artifacts, wheels-raised testing, and blade-off testing prove narrower claims;
none establishes autonomous, production, unattended, or scheduled-mowing readiness.

### Schema-v1 migration and rollback

- Schema-v1 records remain immutable historical evidence, but schema v2 returns `QUALIFICATION_SCHEMA_MISMATCH` and will not
  reinterpret them as containing `supervised_blade_enabled` evidence. Do not edit an old JSON record or repoint `latest.json`
  to bypass requalification; create a new schema-v2 record in the current context.
- On migration/startup failure, leave the tracked permit settings disabled, confirm neutral/blade off, and keep autonomy
  blocked. Permit state is never restored across a process restart.
- Before rollback, command neutral/blade off, use the physical cutoff, and revoke any permit while the current backend is
  responsive. Deploy the selected clean commit, restart services, and confirm startup-neutral state.
- Evidence from the newer schema/context is not authorization for the older build. Older evidence is valid only under that
  build's exact historical commit/config/limits/runtime/firmware contract. Never downgrade software merely to reuse evidence.
- After either migration or rollback, repeat non-destructive checks and the applicable physical checklist before restoring
  any blade-capable authority.

## AI
- GET http://127.0.0.1:8081/api/v2/ai/status
- GET http://127.0.0.1:8081/api/v2/ai/perception/latest
- POST http://127.0.0.1:8081/api/v2/ai/inference → embedded SIM/CI uploaded-image diagnostic
- POST http://127.0.0.1:8081/api/v2/ai/inference/latest → embedded SIM/CI latest-frame diagnostic
- GET http://127.0.0.1:8081/api/v2/ai/results/recent

The production inference contract is a configured ONNX detector executed by OpenCV DNN on the CPU. The repository does not
bundle a model binary, dataset, training job, export pipeline, or active Coral/Hailo acceleration. The tracked manifest
template and pinned baseline-model provisioning steps are in `docs/perception-runtime.md`; the ignored runtime manifest and
model must both be present before `model_ready=true`. Automatic camera processing passes sampled exact frame bytes,
frame ID, and source timestamp
to the standalone owner's injected processor at a bounded cadence within the single latest-frame consumer. It does not
create a task per frame or queue stale inference work, and CPU inference runs off the event loop.
`AI_CAMERA_INFERENCE_FPS` controls sampling and
`AI_CAMERA_INFERENCE_TIMEOUT_SECONDS` defaults to 3 seconds for the measured Pi 5
YOLOv5n CPU range (~1.0-1.95 seconds). Inference runs outside frame delivery, so
Control streaming continues while the selected frame is processed. A timed-out
worker remains the only tracked inference until it exits; its late result is
discarded and no replacement worker is queued concurrently. The baseline manifest
uses a 5-second source-frame freshness bound, leaving a bounded 2-second margin for
IPC polling and consumers after the owner deadline.
`ai_model_loaded=true` reports artifact/runtime initialization only;
`ai_runtime_ready=true` additionally requires a successful automatic exact-frame
result inside the deadline and freshness window. Timeout, runtime/provenance
failure, capture stop, or staleness clears operational readiness, and mission
startup waits boundedly for it to recover before navigation dispatch.

In hardware mode, `lawnberry-camera.service` owns both camera capture and automatic sampled inference. FastAPI validates
matching detector metadata, ingests the owner's typed results over camera IPC, and exposes them through
`GET /api/v2/ai/perception/latest` and the status/recent-result surfaces. The two `POST /api/v2/ai/inference...` routes are
embedded-backend diagnostics for `SIM_MODE=1` and CI; they return `503` in hardware mode rather than loading a second model
or forwarding an uploaded image to the camera owner.

`processed_for_ai=true` means inference succeeded for that exact frame, including a valid result with zero detected objects.
Disabled, skipped, unavailable, failed, timed-out, late, or frame-mismatched work remains unprocessed, and simulation must
not inject hardcoded detections.

Fresh results from the exact configured model may create short-lived semantic entries in the route-planning cost map. A
semantic multiplier can only increase obstacle clearance; it cannot create or clear the active obstacle safety interlock,
authorize motion, or replace ToF, localization, operating-area, qualification, and `MotorCommandGateway` checks. Stale,
unproven, non-camera, or mismatched-model results are rejected. This route-cost use is not a claim that the detector is
physically qualified for unattended mowing.

## Settings
- GET/PUT http://127.0.0.1:8081/api/v2/settings → settings profile management
- GET http://127.0.0.1:8081/api/v2/docs/bundle → offline documentation bundle
- POST http://127.0.0.1:8081/api/v2/verification-artifacts → upload verification artifacts

## Systemd
See systemd/*.service and systemd/install_services.sh for installation. Backend service listens on port 8081.

Sensor acquisition is owned by the backend's shared `SensorManager`; there is no independent
`lawnberry-sensors.service`. Running `sudo bash systemd/install_services.sh` disables and removes that historical
sleep-only unit during an upgrade. A green status from an old installed copy is not sensor-health evidence. Use the
dashboard and sensor endpoints above, then inspect backend logs for the canonical owner.

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

## Replacing a saved boundary

On the Maps page, select **Boundary** to load the existing boundary with its editable blue point handles. **Discard
Draft** only abandons unsaved edits; it never deletes the saved boundary. To start over with a smaller test area, select
**Delete Saved Boundary** and confirm. That removes the old boundary, its generated safe area, and any completed or
cancelled verification message. An in-progress verification must be cancelled first, so a blade-off leg cannot lose the
area it was created to check.

After deletion, select **Boundary**, click the map to make the smaller area, save it, and select **Generate Safe
Boundary**. The generated safe area must be recreated before drive-to-confirm is available. This does not turn off
obstacle avoidance: if the mower sees an obstacle inside its stopping clearance, it remains stopped until the path is
clear.

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
