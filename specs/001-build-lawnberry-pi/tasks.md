# Tasks: LawnBerry Pi v2

**Input**: Design documents from `/home/pi/lawnberry_pi/specs/001-build-lawnberry-pi/`
**Prerequisites**: plan.md (✓), research.md (✓), data-model.md (✓), contracts/ (✓)

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Each task must end with passing tests + updated docs
- Include exact file paths in descriptions

## Phase 3.1: Foundation & AI Runners

### T001 [X] Scaffold v2 layout, pyproject (ARM64 guards), pre-commit, CI
Create complete project structure with constitutional compliance:
- `pyproject.toml` with ARM64 platform guards, forbidden packages, and AI runner isolation notes
- `src/lawnberry/` package layout with modules for GPS (F9P/Neo-8M), sensors, motion (RoboHAT/L298N), safety, power (INA3221 fixed map), camera, AI runners, web UI
- `.pre-commit-config.yaml` with ruff/black/mypy hooks
- `.github/workflows/ci.yml` with lint/test/docs-drift/TODO checks
- Update `/docs/architecture.md` with v2 structure overview
- Tests: `tests/test_project_structure.py` validates directory layout and pyproject.toml constraints

### T002 [X] CPU TFLite runner + unit tests with synthetic frames; docs page
Implement fallback AI acceleration tier:
- `src/lawnberry/runners/cpu_tflite_runner.py` with TensorFlow Lite inference
- `tests/unit/test_cpu_tflite_runner.py` with synthetic frame generation and mock models
- `/docs/ai-acceleration/cpu-tflite.md` with performance benchmarks and usage examples
- Tests verify inference pipeline with synthetic 720p frames, error handling, and model loading

### T003 [P] Hailo runner (optional) + setup script; skip gracefully if device absent
Implement optional mid-tier AI acceleration:
- `src/lawnberry/runners/hailo_runner.py` with device detection and graceful fallback
- `scripts/setup_env_hailo.sh` for SDK installation and environment setup
- `tests/unit/test_hailo_runner.py` with device presence mocking
- `/docs/ai-acceleration/hailo.md` with setup instructions and troubleshooting
- Tests verify graceful degradation when hardware absent

### T004 [P] Coral isolation: venv-coral + service template; docs warn about SDK versions
Implement top-tier AI acceleration with constitutional isolation:
- `scripts/setup_coral_venv.sh` creating isolated virtual environment
- `src/lawnberry/runners/coral_runner.py` with subprocess communication to isolated venv
- `systemd/coral-runner.service.template` for isolated service management
- `/docs/ai-acceleration/coral-tpu.md` with SDK version warnings and isolation rationale
- Tests: `tests/integration/test_coral_isolation.py` validates environment separation

## Phase 3.2: Core Systems

### T005 Camera pipeline: Picamera2→GStreamer; streaming endpoint; tests
Implement constitutional camera requirements:
- `src/lawnberry/services/camera_service.py` with Picamera2 + GStreamer pipeline
- `src/lawnberry/api/camera.py` streaming endpoint at `/camera/stream`
- `tests/integration/test_camera_pipeline.py` with mock Picamera2 for CI
- `/docs/hardware/camera.md` with pipeline architecture and performance tuning
- Tests verify 720p@15fps streaming, format conversion, and error recovery

### T006 WebSocket hub: telemetry/control schema; e2e sim
Implement real-time communication backbone:
- `src/lawnberry/core/websocket_hub.py` with event routing and client management
- `src/lawnberry/models/websocket_events.py` implementing contracts/websocket-events.md schemas
- `tests/integration/test_websocket_e2e.py` with full simulation environment
- `/docs/api/websocket-hub.md` with event flow diagrams and client examples
- Tests verify <100ms telemetry latency, event routing, and connection management

### T007 Safety & motion: interlocks, estop, motor driver abstraction; tests
Implement critical safety systems:
- `src/lawnberry/services/safety_service.py` with emergency stop and interlocks
- `src/lawnberry/services/motion_service.py` with abstraction that prioritizes RoboHAT→Cytron MDDRC10 and cleanly falls back to L298N
- `tests/unit/test_safety_interlocks.py` with comprehensive safety scenario testing
- `/docs/safety/emergency-systems.md` with safety protocol documentation
- Tests verify <10ms emergency stop response, interlock logic, hall encoder feedback on RoboHAT path, and graceful L298N fallback

### T008 Sensor IO: BNO085, INA3221, VL53L0X; sim adapters + real drivers; tests
Implement constitutional hardware interface requirements:
- `src/lawnberry/services/sensor_service.py` with BNO085 (UART4), INA3221 (fixed channels), VL53L0X pair, BME280, SSD1306 drivers
- `src/lawnberry/services/gps_service.py` covering ZED-F9P USB + NTRIP (preferred) and Neo-8M UART alternative with mutual exclusion guards
- `src/lawnberry/adapters/sim_sensors.py` for testing without hardware (mirrors SIM_MODE=1 behavior)
- `tests/integration/test_sensor_io.py` with both simulation and hardware modes, asserting INA3221 channel invariants and GPS mode exclusivity
- `/docs/hardware/sensors.md` with calibration procedures, GPS configuration, and troubleshooting matrix
- Tests verify sensor accuracy, error handling, INA3221 channel enforcement, and simulation compatibility

### T009 Telemetry aggregation service, REST snapshot, and SQLite rollups
Implement TelemetrySnapshot pipeline for REST + WebSocket delivery:
- `src/lawnberry/services/telemetry_service.py` collecting SensorData, PowerManagement, NavigationState, JobStatus, WeatherSnapshot, CameraStream
- `src/lawnberry/api/telemetry.py` exposing `/api/v1/telemetry/snapshot`, `/api/v1/telemetry/history`, and health endpoints
- `tests/contract/test_telemetry_contract.py` verifying JSON schema matches `contracts/telemetry.json`
- `tests/integration/test_telemetry_snapshot.py` ensuring SIM_MODE + hardware modes emit consistent snapshots under 100 ms
- `/docs/api/telemetry.md` documenting REST/WS payloads, rate limits, and snapshot fields
- Wire telemetry service into WebSocket hub topic `telemetry` with consistent snapshot IDs and persistence windows

### T010 Map, job, weather, and dataset APIs with persistence + WebSocket fan-out
Implement CRUD and streaming services backing new WebUI surfaces:
- `src/lawnberry/services/map_service.py`, `job_service.py`, `weather_service.py`, `dataset_service.py` respecting data-model entities
- `src/lawnberry/api/map.py`, `jobs.py`, `weather.py`, `datasets.py` under `/api/v1/`
- WebSocket topic publishers for `map`, `jobs`, `events`, and `ai` integrated with hub
- `tests/contract/test_map_api.py`, `tests/contract/test_job_api.py`, `tests/contract/test_dataset_api.py` for REST schemas and permissions
- `tests/integration/test_scheduler_flow.py` covering job lifecycle (schedule → run → complete/cancel) with map overlays + telemetry coupling
- `/docs/api/map-and-jobs.md` + `/docs/api/datasets.md` detailing routes, payloads, and safety guards
- Ensure SQLite persistence tables (`geo`, `jobs`, `weather_cache`, `ai_images`) and migration scripts exist with rollbacks

## Phase 3.3: User Interface & Deployment

### T011 WebUI branding + full surface implementation; build script
Implement constitutional React frontend across all mandated routes:
- `frontend/src/pages/DashboardPage.tsx`, `MapSetupPage.tsx`, `ManualControlPage.tsx`, `MowPlanPage.tsx`, `AiTrainPage.tsx`, `SettingsPage.tsx`, `DocsHubPage.tsx`
- `frontend/src/components/Telemetry/RetroTelemetryDashboard.tsx`, `Map/ZoneEditor.tsx`, `Jobs/Timeline.tsx`, `AI/DatasetGallery.tsx`
- `frontend/src/services/api-client.ts` for REST clients (telemetry, map, jobs, weather, datasets, settings)
- `frontend/src/services/websocket-client.ts` handling `telemetry`, `map`, `jobs`, `events`, `ai`, `logs` topics with reconnection/backoff
- `scripts/build_frontend.sh` with Vite production build process, asset hashing, and retro shader pipeline
- `/docs/ui/retro-theme.md` updated with per-page guidelines, joystick/manual control UX, and branding usage instructions for logo/icon/pin assets
- Ensure header/footer render `frontend/public/LawnBerryPi_logo.png`, favicon/PWA manifest use `frontend/public/LawnBerryPi_icon2.png`, and map markers incorporate `frontend/public/assets/robot-pin.png`
- Tests: `frontend/tests/dashboard.test.tsx`, `map-setup.test.tsx`, `manual-control.test.tsx`, `mow-plan.test.tsx`, `ai-train.test.tsx`, `settings.test.tsx` verifying real-time data display, map overlays, job timeline progression, dataset moderation flow, and branding enforcement

### T012 Systemd units + install scripts; docs for enable/disable
Implement constitutional service management:
- `systemd/mower-core.service`, `systemd/camera-stream.service`, `systemd/webui.service`
- `scripts/pi_bootstrap.sh` with complete automated installation
- `tests/integration/test_systemd_services.py` with service lifecycle testing
- `/docs/deployment/systemd.md` with service management, Wi-Fi-first networking, and SIM_MODE toggles
- Tests verify service dependencies, restart policies, WebUI asset build integration, and installation automation

### T013 Docs site (mkdocs), ADRs; "handoff" journal template
Implement constitutional documentation-as-contract:
- `mkdocs.yml` configuration with material theme
- `/docs/adrs/` directory with Architecture Decision Records template
- `/docs/templates/handoff-journal.md` for project handoff documentation
- `.github/workflows/docs-drift-check.yml` enforcing docs synchronization
- Tests: `tests/test_docs_completeness.py` validates documentation coverage and links, including new API/WebSocket references

### T014 Migration guide from v1; mark legacy folder
Complete v2 transition requirements:
- `scripts/migrate_from_v1.sh` with configuration and data migration
- `/docs/migration/v1-to-v2.md` with step-by-step migration procedures
- `legacy/` folder creation with v1 deprecation notices
- `tests/integration/test_v1_migration.py` with migration scenario validation
- Tests verify configuration preservation, data migration integrity, and rollback procedures, including telemetry/map/job history carryover

## Dependencies
- T001 (foundation) before all other tasks
- T002-T004 (AI runners) can run in parallel after T001
- T005-T008 (core systems) require T001, can run in parallel with each other
- T009 (telemetry aggregation) depends on T005-T008 and integrates with T006 (WebSocket hub)
- T010 (map/job/weather/dataset APIs) depends on T006-T009 for data sources and hub integration
- T011 (WebUI) requires T006 (WebSocket hub), T009 (telemetry service), and T010 (map/job/dataset APIs)
- T012 (systemd) requires T005-T011 (services and WebUI) to be complete
- T013-T014 (docs/migration) can run in parallel after T012

## Parallel Execution Examples

### Phase 3.1 Parallel Block (after T001):
```bash
# Launch T002-T004 together:
Task: "CPU TFLite runner + unit tests with synthetic frames; docs page"
Task: "Hailo runner (optional) + setup script; skip gracefully if device absent"
Task: "Coral isolation: venv-coral + service template; docs warn about SDK versions"
```

### Phase 3.2 Parallel Block (after T001):
```bash
# Launch T005-T008 together:
Task: "Camera pipeline: Picamera2→GStreamer; streaming endpoint; tests"
Task: "WebSocket hub: telemetry/control schema; e2e sim"  
Task: "Safety & motion: interlocks, estop, motor driver abstraction; tests"
Task: "Sensor IO: BNO085, INA3221, VL53L0X; sim adapters + real drivers; tests"
```

### Phase 3.2 Sequential Follow-up:
```bash
# After core services and hub (T005-T008) finish, tackle data/APIs:
Task: "Telemetry aggregation service, REST snapshot, and SQLite rollups"
Task: "Map, job, weather, and dataset APIs with persistence + WebSocket fan-out"
```

### Phase 3.3 Final Parallel Block:
```bash
# Launch T013-T014 together (after T012):
Task: "Docs site (mkdocs), ADRs; handoff journal template"
Task: "Migration guide from v1; mark legacy folder"
```

## Validation Checklist
- [x] All 14 tasks are atomic and end with passing tests + updated docs
- [x] Each task specifies exact file paths and deliverables
- [x] Constitutional requirements addressed (ARM64, isolation, TDD, docs-as-contract)
- [x] Dependencies clearly defined with parallel execution opportunities
- [x] Tests include both unit and integration coverage with simulation support
- [x] Documentation updated for each component following constitutional requirements

## Notes
- Each task must be completed with working tests before proceeding
- Documentation updates are mandatory per constitutional requirements
- ARM64 platform constraints enforced throughout
- AI acceleration hierarchy (Coral → Hailo → CPU) maintained with proper isolation
- Safety systems prioritized with comprehensive testing requirements