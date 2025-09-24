# Tasks: LawnBerry Pi v2

**Input**: Design documents from `/home/pi/lawnberry_pi/specs/001-build-lawnberry-pi/`
**Prerequisites**: plan.md (✓), research.md (✓), data-model.md (✓), contracts/ (✓)

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Each task must end with passing tests + updated docs
- Include exact file paths in descriptions

## Phase 3.1: Foundation & AI Runners

### T001 Scaffold v2 layout, pyproject (ARM64 guards), pre-commit, CI
Create complete project structure with constitutional compliance:
- `pyproject.toml` with ARM64 platform guards and forbidden packages
- `src/lawnberry/` package layout with 8 modules
- `.pre-commit-config.yaml` with ruff/black/mypy hooks
- `.github/workflows/ci.yml` with lint/test/docs-drift/TODO checks
- Update `/docs/architecture.md` with v2 structure overview
- Tests: `tests/test_project_structure.py` validates directory layout and pyproject.toml constraints

### T002 [P] CPU TFLite runner + unit tests with synthetic frames; docs page
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
- `src/lawnberry/services/motion_service.py` with Cytron MDDRC10 abstraction
- `tests/unit/test_safety_interlocks.py` with comprehensive safety scenario testing
- `/docs/safety/emergency-systems.md` with safety protocol documentation
- Tests verify <10ms emergency stop response, interlock logic, and motor control abstraction

### T008 Sensor IO: BNO085, INA3221, VL53L0X; sim adapters + real drivers; tests
Implement constitutional hardware interface requirements:
- `src/lawnberry/services/sensor_service.py` with BNO085, INA3221, VL53L0X drivers
- `src/lawnberry/adapters/sim_sensors.py` for testing without hardware
- `tests/integration/test_sensor_io.py` with both simulation and hardware modes
- `/docs/hardware/sensors.md` with calibration procedures and troubleshooting
- Tests verify sensor accuracy, error handling, and simulation compatibility

## Phase 3.3: User Interface & Deployment

### T009 WebUI minimal (retro theme), live telemetry, control actions; build script
Implement constitutional React frontend:
- `frontend/src/components/RetroTelemetryDashboard.tsx` with 80s aesthetic
- `frontend/src/services/websocket-client.ts` connecting to WebSocket hub
- `scripts/build_frontend.sh` with Vite production build process
- `/docs/ui/retro-theme.md` with design guidelines and component library
- Tests: `frontend/tests/telemetry-dashboard.test.tsx` validates real-time data display

### T010 Systemd units + install scripts; docs for enable/disable
Implement constitutional service management:
- `systemd/mower-core.service`, `systemd/camera-stream.service`, `systemd/webui.service`
- `scripts/pi_bootstrap.sh` with complete automated installation
- `tests/integration/test_systemd_services.py` with service lifecycle testing
- `/docs/deployment/systemd.md` with service management and troubleshooting
- Tests verify service dependencies, restart policies, and installation automation

### T011 Docs site (mkdocs), ADRs; "handoff" journal template
Implement constitutional documentation-as-contract:
- `mkdocs.yml` configuration with material theme
- `/docs/adrs/` directory with Architecture Decision Records template
- `/docs/templates/handoff-journal.md` for project handoff documentation
- `.github/workflows/docs-drift-check.yml` enforcing docs synchronization
- Tests: `tests/test_docs_completeness.py` validates documentation coverage and links

### T012 Migration guide from v1; mark legacy folder
Complete v2 transition requirements:
- `scripts/migrate_from_v1.sh` with configuration and data migration
- `/docs/migration/v1-to-v2.md` with step-by-step migration procedures
- `legacy/` folder creation with v1 deprecation notices
- `tests/integration/test_v1_migration.py` with migration scenario validation
- Tests verify configuration preservation, data migration integrity, and rollback procedures

## Dependencies
- T001 (foundation) before all other tasks
- T002-T004 (AI runners) can run in parallel after T001
- T005-T008 (core systems) require T001, can run in parallel with each other
- T009 (UI) requires T006 (WebSocket hub) for real-time data
- T010 (systemd) requires T005-T008 (services) to be complete
- T011-T012 (docs/migration) can run in parallel after T010

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

### Phase 3.3 Final Parallel Block:
```bash
# Launch T011-T012 together (after T010):
Task: "Docs site (mkdocs), ADRs; handoff journal template"
Task: "Migration guide from v1; mark legacy folder"
```

## Validation Checklist
- [x] All 12 tasks are atomic and end with passing tests + updated docs
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