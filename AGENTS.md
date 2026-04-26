# LawnBerry Agent Instructions

## Project Orientation

- LawnBerry Pi is a Raspberry Pi autonomous mower system with a FastAPI backend, Vue 3 frontend, hardware drivers, systemd deployment units, and operations tooling.
- Treat this as a live robotics/control system, not a greenfield web app. Safety, hardware state, and runtime drift matter.
- Start substantial work by reading `docs/developer-toolkit.md`, then the task-relevant docs under `docs/`, `spec/hardware.yaml`, and `.github/copilot-instructions.md`.
- Keep changes focused. Do not rewrite broad subsystems, rename files, or alter hardware conventions unless the task explicitly requires it.

## Repository Map

- `backend/` contains the Python 3.11 FastAPI app.
- `backend/src/main.py` is the backend entrypoint and wires routers, middleware, lifespan startup, telemetry, hardware services, camera, AI, and mission recovery.
- `backend/src/api/` contains REST and WebSocket-facing routers.
- `backend/src/services/` contains domain services such as RoboHAT, navigation, mission, telemetry, weather, maps, auth, camera, and AI.
- `backend/src/drivers/` contains hardware adapters. Be conservative here and prefer simulation-safe imports.
- `backend/src/nav/` contains geofence, coverage, waypoint, path-planning, odometry, and GPS degradation logic.
- `backend/src/safety/` contains safety validation, interlock, E-stop, watchdog, and motor authorization logic.
- `backend/src/core/` contains config loading, state, persistence, observability, logging, and environment validation.
- `frontend/` contains the Vue 3 + Vite + Pinia application.
- `frontend/src/views/`, `frontend/src/components/`, `frontend/src/stores/`, `frontend/src/services/`, and `frontend/src/composables/` are the main frontend work areas.
- `config/` contains runtime config; avoid committing real secrets or local-only values.
- `systemd/` contains Raspberry Pi service units and timers.
- `scripts/` contains setup, validation, diagnostics, backups, TLS, and hook tooling.
- `tests/` contains backend unit, integration, contract, HIL, and soak tests.
- `docs/` and `spec/` are part of the product contract; update them when behavior, hardware scope, ports, or public interfaces change.
- `docs/diagnostics-replay.md` documents the telemetry capture + replay harness used to regression-check navigation refactors.

## Runtime Contract

- Backend API runs on port `8081`.
- Frontend local/deployed UI runs on port `3000`.
- Playwright preview/E2E uses port `4173`.
- Backend WebSocket telemetry is `ws://127.0.0.1:8081/api/v2/ws/telemetry`.
- Use `SIM_MODE=1` for local development, CI, and tests unless explicitly validating hardware.
- Use `SIM_MODE=0` only for on-device or bench hardware validation.
- Leaving `SIM_MODE` unset currently behaves like hardware mode because startup defaults to `os.getenv("SIM_MODE", "0")`.
- Runtime services may keep stale Python bytecode; after changing systemd-served Python code, clear `*.pyc`/`__pycache__` before restart if validating on-device.

## Development Commands

- Backend dev server: `SIM_MODE=1 python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081`
- Hardware backend server: `SIM_MODE=0 python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081`
- Backend tests: `SIM_MODE=1 python -m pytest tests/unit/ -x -q -m "not hardware"`
- Broader backend tests: `SIM_MODE=1 python -m pytest tests/ -x -q -m "not hardware"`
- Backend lint: `python -m ruff check backend/src tests`
- Frontend install: `cd frontend && npm ci`
- Frontend dev server: `cd frontend && npm run dev -- --host 0.0.0.0 --port 3000`
- Frontend build: `cd frontend && npm run build`
- Frontend tests: `cd frontend && npm test`
- Frontend E2E: `cd frontend && npm run test:e2e`
- Docs drift check: `bash scripts/check_docs_drift.sh`

## Testing Rules

- Prefer targeted tests near changed code before broad suites.
- Do not run hardware/HIL/soak tests unless the user asks or the task is specifically hardware validation.
- Avoid unfiltered `python -m pytest tests/` on the Pi; some tests can block on hardware I/O. Use `SIM_MODE=1`, `-m "not hardware"`, and targeted paths.
- Unit tests under `tests/unit/` are the safest default for backend changes.
- Contract and integration tests may exercise persistence, startup, and API interactions; run them when changing API behavior.
- Frontend changes should generally pass `npm run type-check`, `npm test`, or `npm run build` depending on scope.
- Do not add a new test framework or formatter. Use the configured pytest, ruff, black, ESLint, Prettier, Vitest, and Playwright tooling.

## Coding Conventions

- Python target is 3.11; use type hints for public or non-trivial code.
- Python formatting/lint expectations come from `pyproject.toml`: line length `100`, ruff rules `E`, `F`, `I`, `UP`, and `B`.
- Use Pydantic v2 patterns in backend models and FastAPI router code.
- Keep hardware imports lazy or guarded so simulation and CI stay usable without devices.
- Vue code uses Vue 3, TypeScript, Pinia, Vite, ESLint, and Prettier.
- Use PascalCase for Vue components and camelCase for props, methods, composables, and store actions.
- Keep frontend API and WebSocket behavior centralized in `frontend/src/services/` and reusable state in `frontend/src/stores/` or `frontend/src/composables/`.
- Do not hardcode runtime limits, hardware addresses, ports, or secrets when a config file already owns the value.

## Safety-Critical Hardware Rules

- Do not probe, scan, or auto-detect `/dev/ttyAMA4`; it is the BNO085 IMU UART and incorrect opens can corrupt sensor state until power cycle.
- Fixed serial conventions from repo docs:
  - RoboHAT RP2040 USB CDC: `/dev/robohat` -> `/dev/ttyACM0`
  - BNO085 IMU: `/dev/ttyAMA4`
  - ZED-F9P GPS: `/dev/lawnberry-gps`
  - Hardware UART to RP2040: `/dev/serial0`
- Preserve the BNO085 heading convention unless deliberately changing navigation math: `adjusted_yaw = (-raw_yaw + imu_yaw_offset_degrees) % 360.0`.
- Do not change `imu_yaw_offset_degrees` to `180` as a shortcut for heading issues; investigate GPS COG bootstrap and `data/imu_alignment.json`.
- Motor control has two interdependent compensation layers:
  - `backend/src/services/navigation_service.py` swaps left/right assignments for navigation.
  - `backend/src/services/robohat_service.py` inverts arcade mix sign.
- If motor, navigation, RoboHAT, or drive endpoint behavior changes, validate both joystick/manual drive and mission/navigation paths.
- Safety-critical changes to RoboHAT USB, GPS probing, E-stop, watchdog, ToF gating, blade control, or motor authorization require hardware validation before claiming real-world correctness.

## Documentation and Drift

- Update docs in the same pass when changing runtime behavior, ports, safety behavior, hardware scope, public APIs, setup, operations, or testing workflows.
- If callable interfaces change under `backend/src/**`, `frontend/src/**`, `scripts/**`, or `.specify/scripts/**`, update `docs/code_structure_overview.md`.
- The canonical hardware baseline is `spec/hardware.yaml`.
- `docs/OPERATIONS.md` is the runtime operations reference.
- `docs/TESTING.md` is the test workflow reference.
- `docs/simulation-vs-hardware-modes.md` explains SIM vs hardware behavior.
- `CONTRIBUTING.md` defines TODO policy and contribution expectations.

## Secrets and Local Artifacts

- Do not print or commit secrets from `.env`, `config/secrets.json`, `config/maps_settings.json`, tokens, API keys, certificates, or runtime DB files.
- Treat `data/`, `logs/`, `.pytest_cache/`, `.ruff_cache/`, `.venv/`, and generated verification artifacts as local/runtime unless a task explicitly concerns them.
- Existing user changes may be present. Check `git status --short` before editing and do not revert unrelated modifications.

## TODO Policy

- New TODOs must follow the tracked format from `CONTRIBUTING.md`, for example: `TODO(v3): Add retry logic - Issue #123`.
- Do not add vague `TODO`, `FIXME`, `XXX`, or `HACK` comments without an issue reference.

## Validation Before Handoff

- Run the smallest meaningful validation command for the files changed when feasible.
- If validation is skipped, state exactly why and name the command the user can run.
- For backend runtime validation, prefer health checks on `http://127.0.0.1:8081` after startup.
- For frontend runtime validation, prefer `npm run build` or a targeted Vitest/Playwright command depending on the change.
