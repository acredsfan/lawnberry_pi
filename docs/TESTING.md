# Testing Guide (ARM64/Raspberry Pi OS Bookworm)

This project prioritizes TDD and ARM64 compatibility. Below are the common workflows to run tests locally on a Raspberry Pi.

## 1) Python backend tests

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Run the safe backend unit suite from the locked project environment:

```bash
SIM_MODE=1 uv run pytest tests/unit/ -q -m "not hardware"
```

Storage isolation note:

- Tests now run with isolated runtime paths (`DB_PATH`, `LAWN_DATA_DIR`, and `LAWN_SETTINGS_DIR`)
  so they do not mutate live `data/` or `config/` state on the Pi.
- `SIM_MODE=1` tests do not require `config/hardware.yaml`; hardware-mode startup does.

- Contract tests validate the FastAPI REST + WebSocket API.
- Integration tests include backups/migration and more.
- Critical autonomy, GPS-loss, power, perception, authentication, and OpenAPI contracts are executable tests; they must
  not be replaced by unconditional skips or placeholder assertions.

## 1a) Simulation mode vs hardware mode

Use simulation mode for laptops, CI, and general backend development:

```bash
SIM_MODE=1 python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081
```

Use hardware mode only when validating on the Raspberry Pi or attached bench hardware:

```bash
sudo systemctl start lawnberry-camera.service lawnberry-backend.service
```

For a manual bench session, first run the standalone owner from the repository root in terminal 1:

```bash
SIM_MODE=0 LAWNBERRY_CAMERA_SOCKET=/tmp/lawnberry-camera.sock \
  python -m backend.src.services.camera_stream_service
```

Then run the backend against that exact socket in terminal 2:

```bash
SIM_MODE=0 LAWNBERRY_CAMERA_SOCKET=/tmp/lawnberry-camera.sock \
  python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081
```

Never run the manual owner while `lawnberry-camera.service` is active.

Important behavior note:

- `SIM_MODE=1` is the pure simulation path
- `SIM_MODE=0` attempts real hardware initialization
- leaving `SIM_MODE` unset currently behaves like hardware mode because startup checks `os.getenv("SIM_MODE", "0")`

See `docs/simulation-vs-hardware-modes.md` for the full explanation.

## 2) Frontend tests, type checking, lint, and build

From `frontend/`:

```bash
npm ci
npm run lint
npm run type-check
npm run test
npm run build
```

The `webui-build` pull-request workflow runs `npm ci`, type checking, the complete Vitest suite, and the production
build. A green bundle alone is not sufficient because it can miss browser-state and truthful-fallback regressions.

## 2a) Critical autonomy/runtime regression slice

Use isolated state and the locked Python environment:

```bash
tmpdir=$(mktemp -d)
SIM_MODE=1 \
LAWNBERRY_SKIP_HW_INIT=1 \
LAWN_DATA_DIR="$tmpdir/data" \
DB_PATH="$tmpdir/lawnberry.db" \
LAWN_SETTINGS_DIR="$tmpdir/settings" \
uv run pytest -o addopts='' -q -m "not hardware" \
  tests/integration/test_autonomous_operation.py \
  tests/integration/test_gps_loss_policy.py \
  tests/integration/test_manual_control_auth.py \
  tests/contract/test_openapi_schema.py \
  tests/unit/test_energy_service.py \
  tests/unit/test_detector_runtime.py \
  tests/unit/test_build_info.py \
  tests/unit/test_dashboard_status_truth.py \
  tests/unit/test_sanitization_middleware.py \
  tests/unit/test_systemd_sensor_retirement.py
```

Regenerate and compare the public contract after route/model changes:

```bash
SIM_MODE=1 LAWNBERRY_SKIP_HW_INIT=1 \
  uv run python scripts/generate_openapi.py openapi.generated.json
diff -u openapi.json openapi.generated.json

cd frontend
npm run generate-types
```

All frontend dependencies are compatible with ARM64.

## 2b) Dependency security audits

The `dep-audit` pull-request workflow is blocking. It audits only third-party Python requirements
and the committed npm lockfile; known vulnerabilities must be upgraded or explicitly reviewed,
not hidden with `|| true`.

Run the same checks locally:

```bash
uv export --frozen --format requirements-txt --all-extras \
  --no-emit-project --no-hashes \
  | uvx pip-audit -r /dev/stdin --progress-spinner off

cd frontend
npm ci --ignore-scripts
npm audit
```

`tests/unit/test_dependency_audit_workflow.py` protects the fail-closed workflow contract.

## 3) Docs drift guard

CI will fail if code changes without corresponding documentation or journal updates. You can run the check locally:

```bash
bash scripts/check_docs_drift.sh
```

## 3a) Hardware configuration contract slice

For changes that touch `ConfigLoader`, hardware templates, setup, startup reporting, health, RoboHAT config consumption,
or runtime redaction:

```bash
tmpdir=$(mktemp -d)
SIM_MODE=1 \
LAWN_DATA_DIR="$tmpdir/data" \
DB_PATH="$tmpdir/data/lawnberry.db" \
LAWN_SETTINGS_DIR="$tmpdir/config" \
python -m pytest \
  tests/unit/test_config_loader.py \
  tests/unit/test_startup_config_report.py \
  tests/unit/test_hardware_config_manager.py \
  tests/unit/test_platform_pin_registry.py \
  tests/contract/test_driver_registry.py \
  -q -m "not hardware"

bash -n scripts/setup.sh
uv run python scripts/manage_hardware_config.py validate
```

Use temporary roots in tests for migration and ensure commands. Do not touch the real node `config/hardware.yaml` from
automated tests.
The manager tests must cover the fail-closed legacy path: `ensure` and `validate` return non-zero when
`config/hardware.local.yaml` exists, and `migrate-legacy` restores original files if any post-backup step fails.

## 3b) Autonomous readiness regression slice

For platform/pin validation, blade controller safety, GPS freshness, dynamic obstacle clearance,
command leases, and scheduled mission due detection:

```bash
tmpdir=$(mktemp -d)
SIM_MODE=1 \
LAWN_DATA_DIR="$tmpdir" \
DB_PATH="$tmpdir/lawnberry.db" \
LAWN_SETTINGS_DIR="$tmpdir/config" \
python -m pytest \
  tests/unit/test_platform_pin_registry.py \
  tests/unit/test_obstacle_clearance.py \
  tests/unit/test_gps_sample_freshness.py \
  tests/unit/test_autonomy_qualification_service.py \
  tests/unit/test_autonomy_qualification_runner.py \
  tests/unit/test_autonomy_readiness_service.py \
  tests/unit/test_config_loader.py \
  tests/unit/test_ibt4_blade_driver.py \
  tests/unit/test_command_gateway.py \
  tests/unit/test_wlan1_usb_recovery.py \
  tests/integration/test_scheduled_mission_dispatch.py \
  tests/integration/test_wifi_watchdog_disabled_tiers.py \
  -x -q -m "not hardware"
python -m py_compile robohat-rp2040-code/code.py
```

## 3c) Autonomy qualification gate regression slice

For changes to schema-v2 qualification levels, supervised-test permits, blade authorization, mission start, scheduler
dispatch, WebSocket recovery, or the Wi-Fi watchdog regression tasks:

```bash
tmpdir=$(mktemp -d)
SIM_MODE=1 \
LAWN_DATA_DIR="$tmpdir" \
DB_PATH="$tmpdir/lawnberry.db" \
LAWN_SETTINGS_DIR="$tmpdir/config" \
python -m pytest \
  tests/unit/test_autonomy_qualification_service.py \
  tests/unit/test_autonomy_qualification_runner.py \
  tests/unit/test_supervised_qualification_permit.py \
  tests/unit/test_two_phase_qualification_adversarial.py \
  tests/unit/test_autonomy_readiness_service.py \
  tests/unit/test_command_gateway.py \
  tests/unit/test_sanitization_middleware.py \
  tests/unit/test_mission_service.py \
  tests/unit/test_jobs_service_execution.py \
  tests/unit/test_live_safety_coordinator.py \
  tests/unit/test_wlan1_usb_recovery.py \
  tests/integration/test_scheduled_mission_dispatch.py \
  tests/integration/test_wifi_watchdog_disabled_tiers.py \
  tests/contract/test_supervised_qualification_api.py \
  tests/test_mission_api.py \
  -o addopts='' -x -q -m "not hardware"

SIM_MODE=1 LAWNBERRY_SKIP_HW_INIT=1 \
  python -m pytest \
  tests/unit/test_jwt_manager.py \
  tests/contract/test_health_endpoints.py \
  tests/contract/test_openapi_schema.py \
  tests/integration/test_navigation_replay.py \
  -o addopts='' -q -m "not hardware"

SIM_MODE=1 LAWNBERRY_SKIP_HW_INIT=1 \
  uv run python scripts/generate_openapi.py openapi.generated.json
diff -u openapi.json openapi.generated.json

cd frontend
npm test -- \
  tests/unit/MissionPlannerView.spec.ts \
  tests/unit/missionStore.spec.ts \
  tests/unit/viteWebSocketProxy.spec.ts \
  tests/integration/test_ws_resilience.spec.ts
npm run type-check
npm run build
```

This slice must prove all three typed evidence levels (`blade_off_diagnostic`,
`supervised_blade_test_prerequisite`, and `full_blade_autonomy`), schema-v1 rejection, artifact/cleanup-receipt validation,
one-permit concurrency, issuance/activation deadlines, single-session and single-use behavior, restart absence, context drift,
speed/lease bounds, mission/scheduler denial, gateway enforcement, live-safety revocation, and startup/shutdown cleanup. Permit
tests must use isolated fakes in `SIM_MODE=1`; they exercise authorization logic only and must never create physical evidence
or open actuator hardware. API tests must prove authenticated status/revoke remain remotely available for safe inspection/stop
while issue/activate/drive/blade/complete require local/LAN identity. They must also cover active-expiry gateway cleanup,
independent drive/blade command leases, and scheduler startup denial until hardware-neutral/blade-off state plus power readiness
are confirmed. OpenAPI generation must include the authenticated supervised-test status, issue, activate, drive, blade,
complete, and revoke contracts.

The camera stage remains advisory in this schema. Tests should prove camera degradation cannot weaken independent ToF,
geofence, localization, live-safety, or gateway stops; they should not turn advisory detector availability into a blade
qualification blocker.

### Physical qualification test order (Aaron only)

Automated green results are only the first of seven operational gates:

1. **Software tests:** run the isolated backend/frontend/OpenAPI checks. No software test may issue physical commands or
   register a physical pass.
2. **Non-destructive on-device checks:** on the clean final commit in `SIM_MODE=0`, confirm config/limits/firmware identity,
   service startup-neutral state, health truth, and the verified physical cutoff with wheels raised and blade power isolated.
3. **Blade-off physical qualification:** perform wheels-raised drive/fail-safe, stationary RTK/geofence, blade-off boundary
   bootstrap, straight-line/obstacle, and blade-off scheduler/WebUI recovery stages in the order documented in
   `docs/OPERATIONS.md#ordered-physical-checklist-for-aaron`. Retain immutable artifacts for each result.
4. **Supervised-test permit:** only after Aaron approves nonzero TTL/duration/speed bounds and the current schema-v2
   prerequisite evaluates `prerequisite_ok=true`, request and activate one local authenticated permit. Polling must not extend
   it; a restart, emergency, safety fault, session/context change, or interruption requires a new permit.
5. **Supervised blade-enabled evidence:** Aaron performs the minimum approved test at the cutoff. Record pass, fail, or
   interrupted independently of the API response. Confirm the status records at least one authorized drive and blade-enable
   command, confirm neutral/blade-off cleanup, and bind the evidence-eligible server receipt ID to the
   `supervised_blade_enabled` artifact.
6. **Full qualification:** verify `full_autonomy_ok=true` in the unchanged commit/config/limits/runtime/firmware context.
   Ordinary blade commands, missions, and schedules remain blocked until this succeeds.
7. **Limited controlled mowing:** begin with one short supervised daylight mission. Unattended scheduling remains prohibited
   until repeated controlled field runs and Aaron's separate explicit approval.

For emergency/restart cases, physically confirm neutral drive and a stopped blade; an accepted cleanup request or watchdog
lease is not physical proof. The evidence runner records operator-reviewed results and always attempts cleanup, but it never
activates a permit or actuates the mower. Report every hardware stage separately from software pass counts and never describe
simulation, replay, wheels-raised, or blade-off results as autonomous readiness.

`tests/integration/test_wifi_watchdog_disabled_tiers.py` imports the installed `/opt/wifi-watchdog` package on the Pi and
skips only when that runtime package is absent. It monkeypatches recovery commands, so it must not reboot, cycle interfaces,
or reset USB devices during automated tests.

`tests/unit/test_wlan1_usb_recovery.py` is the production Wi-Fi recovery contract. It proves local-state classification,
targeted `2357:0138` USB-port cycling, persistent cooldown/budget behavior, `wlan1-primary`-only reconnects, USB2/power
policy, and the absence of host reboot or global NetworkManager restart paths. The older
`tests/integration/test_wifi_watchdog_disabled_tiers.py` remains a regression test for the installed legacy package while
that package exists, but `wifi-watchdog.service` is disabled and is not the production recovery owner.

`tests/unit/test_jwt_manager.py` is the PyJWT 2.13 compatibility contract: HS256 round-trip, expiration, invalid signature,
algorithm allow-list, and fail-closed missing/blank signing secret. `tests/contract/test_health_endpoints.py` intentionally
points at a missing hardware config and requires `critical`; healthy sensor mocks must not hide that blocker. The navigation
replay contract keeps its exact synthetic parity threshold and must not be loosened to make CI pass.

## 3d) Live safety, canonical pose, and map alignment slice

For changes that touch blade-off holds, live sensor safety, canonical GPS antenna/body-center pose,
operating-area authorization, stationary RTK averaging, or source-specific map alignment:

```bash
tmpdir=$(mktemp -d)
SIM_MODE=1 \
LAWN_DATA_DIR="$tmpdir" \
DB_PATH="$tmpdir/lawnberry.db" \
LAWN_SETTINGS_DIR="$tmpdir/config" \
python -m pytest \
  tests/unit/test_mission_executor.py \
  tests/unit/test_live_safety_coordinator.py \
  tests/unit/test_localization_service.py \
  tests/unit/test_telemetry_service.py \
  tests/unit/test_operating_area_service.py \
  tests/unit/test_boundary_verification.py \
  tests/unit/test_stationary_rtk_averaging.py \
  tests/unit/test_gps_driver.py \
  tests/unit/test_gps_status_endpoint.py \
  tests/unit/test_obstacle_clearance.py \
  tests/unit/test_autonomy_readiness_service.py \
  tests/unit/test_command_gateway.py \
  tests/integration/test_satellite_settings_api.py \
  -x -q -m "not hardware"

cd frontend
npm run type-check
npm test -- --run frontend/tests/unit/mapDisplayTransform.spec.ts frontend/tests/unit/mapProviders.spec.ts frontend/tests/unit/composables/useMowerTelemetry.spec.ts
```

These slices prove software behavior only. Physical qualification still needs the staged blade-disabled,
wheels-raised, outdoor blade-off, then limited blade-on sequence before any field-readiness claim. Simulation evidence is
never accepted as physical qualification evidence by the backend gate.

## 3e) Job execution and camera AI contract slice

For changes to `JobsService` mission dispatch/lifecycle projection or automatic camera inference:

```bash
tmpdir=$(mktemp -d)
SIM_MODE=1 \
LAWNBERRY_SKIP_HW_INIT=1 \
LAWN_DATA_DIR="$tmpdir" \
DB_PATH="$tmpdir/lawnberry.db" \
LAWN_SETTINGS_DIR="$tmpdir/config" \
python -m pytest \
  tests/unit/test_jobs_service_execution.py \
  tests/unit/test_job_state_machine.py \
  tests/unit/test_mission_service.py \
  tests/unit/test_mission_ws_push.py \
  tests/unit/test_power_manager_gps.py \
  tests/unit/test_camera_client.py \
  tests/unit/test_camera_systemd_contract.py \
  tests/unit/test_camera_stream_service.py \
  tests/unit/test_ai_service.py \
  tests/unit/test_camera_router_contract.py \
  tests/integration/test_scheduled_mission_dispatch.py \
  tests/integration/test_jobs_service_lifecycle.py \
  tests/contract/test_jobs.py \
  tests/contract/test_rest_api_planning.py \
  tests/test_ai_api.py \
  -o addopts='' -q -m "not hardware"
```

V41 coverage must prove that every documented mower-job compatibility start dispatches through `MissionService`, retains
the linked mission ID, advances `last_run` only after an accepted start, and records completion/success only after the linked
mission reaches `COMPLETED`. Blocked, rejected, failed, aborted, cancelled, and unsupported paths must remain non-successful;
tests must not sleep through or assert synthetic timed progress.

V42 coverage must prove exact frame bytes/ID reach the injected processor, successful annotations derive from its result, a
successful zero-object result is still truthfully processed, and disabled/skipped/unavailable/failed/timed-out/late or
frame-mismatched inference leaves `processed_for_ai=false` with no dummy detections. Use a fake clock and a controlled slow
processor to prove bounded sampling, bounded frame-delivery wait, late-result discard, and one tracked in-flight worker with
no stale backlog; prove CPU-bound inference runs off the event loop and concurrent inference callers remain serialized.
Tests must also prove camera AI results do not mutate navigation/safety state or invoke `MotorCommandGateway`.

These are deterministic software contracts. They prove neither trained-model accuracy nor Coral/Hailo execution, and they
do not qualify camera detections for mower safety. On-Pi camera/model latency, CPU/memory load, dropped-frame behavior, and
known-target/no-target accuracy require separate observational evidence before any broader claim.
The IPC/router contract test also forces live camera initialization to fail and verifies the standalone owner's simulation
fallback remains visible as `sim_mode=true` and `hardware_available=false`, including fail-closed handling of older status
payloads that omit those fields.

Update one of the following to satisfy the guard:
- `docs/**`
- `spec/**`
- `README.md`
- `.specify/memory/AGENT_JOURNAL.md`

## 4) On-device hardware testing (RPi)

Run the backend and call the hardware self-test endpoint:

```bash
sudo systemctl start lawnberry-camera.service lawnberry-backend.service
# Then from another shell on the Pi:
curl http://localhost:8081/api/v2/system/selftest | jq
```

Enable the hardware self-test integration test:

```bash
RUN_HW_TESTS=1 pytest -q tests/integration/test_hardware_selftest.py
```

Notes:
- Use `SIM_MODE=0` for on-device hardware validation so the backend initializes real hardware paths instead of staying simulation-safe.
- Use `SIM_MODE=1` for local development and CI if you want to avoid hardware-init warnings entirely.
- The self-test is safe on systems without hardware: it catches missing devices and returns a report.
- For I2C/serial access, ensure the user is in groups `i2c` and `dialout`.

### Reference mower physical validation record

Aaron physically verified the following against `main@a1d01df` on 2026-07-10. The exact blade-power state and remaining bench conditions were not recorded:

- forward/reverse polarity;
- left/right polarity;
- **Stop Motors** immediate neutral command;
- 45° and 90° preset turns;
- obstacle lockout behavior.

These results close only those bench checks. They do not substitute for wheels-on-ground control tuning, outdoor RTK/geofence validation, loss-of-fix tests, scheduled mission execution, blade shutdown tests, or controlled autonomous mowing.

The reference mower has no dedicated physical E-stop. Aaron has repeatedly verified that its accessible power button removes power from every component downstream of the solar charge controller, shutting down the Raspberry Pi and all mower hardware/motors. A dedicated hardwired E-stop remains optional, but is strongly recommended for builds without another quick, accessible physical control that removes hazardous actuator power. Test the actual intervention control installed on each build; do not record an E-stop test for hardware that is not present.

## 5) Troubleshooting

- Ensure you’re on Raspberry Pi OS (64-bit) Bookworm.
- Avoid non-ARM64 dependencies. If needed, propose a Pi-compatible alternative first.
- Use `uv run` for repository verification so the result uses the locked dependency set rather than a drifting system
  interpreter. An unconditional skip in a critical contract is a missing test, not a passing result.
