# Testing Guide (ARM64/Raspberry Pi OS Bookworm)

This project prioritizes TDD and ARM64 compatibility. Below are the common workflows to run tests locally on a Raspberry Pi.

## 1) Python backend tests

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Run the full test suite:

```bash
SIM_MODE=1 pytest -q
```

Storage isolation note:

- Tests now run with isolated runtime paths (`DB_PATH`, `LAWN_DATA_DIR`, and `LAWN_SETTINGS_DIR`)
  so they do not mutate live `data/` or `config/` state on the Pi.
- `SIM_MODE=1` tests do not require `config/hardware.yaml`; hardware-mode startup does.

- Contract tests validate the FastAPI REST + WebSocket API.
- Integration tests include backups/migration and more.
- Placeholder integration tests (future work) are skipped by default.

## 1a) Simulation mode vs hardware mode

Use simulation mode for laptops, CI, and general backend development:

```bash
SIM_MODE=1 python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081
```

Use hardware mode only when validating on the Raspberry Pi or attached bench hardware:

```bash
SIM_MODE=0 python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081
```

Important behavior note:

- `SIM_MODE=1` is the pure simulation path
- `SIM_MODE=0` attempts real hardware initialization
- leaving `SIM_MODE` unset currently behaves like hardware mode because startup checks `os.getenv("SIM_MODE", "0")`

See `docs/simulation-vs-hardware-modes.md` for the full explanation.

Run placeholder integration tests explicitly:

```bash
RUN_PLACEHOLDER_INTEGRATION=1 pytest -q tests/integration
```

## 2) Frontend tests and lint (optional)

From `frontend/`:

```bash
npm ci
npm run lint
npm run test
npm run build
```

All frontend dependencies are compatible with ARM64.

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
  tests/unit/test_autonomy_readiness_service.py \
  tests/unit/test_config_loader.py \
  tests/unit/test_ibt4_blade_driver.py \
  tests/unit/test_command_gateway.py \
  tests/integration/test_scheduled_mission_dispatch.py \
  -x -q -m "not hardware"
python -m py_compile robohat-rp2040-code/code.py
```

## 3c) Live safety, canonical pose, and map alignment slice

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
  tests/unit/test_stationary_rtk_averaging.py \
  tests/unit/test_autonomy_readiness_service.py \
  tests/unit/test_command_gateway.py \
  tests/integration/test_satellite_settings_api.py \
  -x -q -m "not hardware"

cd frontend
npm run type-check
npm test -- --run frontend/tests/unit/mapDisplayTransform.spec.ts frontend/tests/unit/mapProviders.spec.ts frontend/tests/unit/composables/useMowerTelemetry.spec.ts
```

This slice proves software behavior only. Hardware validation still needs the staged blade-disabled,
wheels-raised, outdoor blade-off, then limited blade-on sequence before any field-readiness claim.

Update one of the following to satisfy the guard:
- `docs/**`
- `spec/**`
- `README.md`
- `.specify/memory/AGENT_JOURNAL.md`

## 4) On-device hardware testing (RPi)

Run the backend and call the hardware self-test endpoint:

```bash
SIM_MODE=0 uvicorn backend.src.main:app --host 0.0.0.0 --port 8081
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
- If placeholder tests fail intentionally, run them only when implementing the corresponding features.
