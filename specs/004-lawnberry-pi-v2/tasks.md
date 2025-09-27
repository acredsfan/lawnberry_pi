# Tasks: LawnBerry Pi v2 Unified System

**Input**: Design documents from `/home/pi/lawnberry/specs/004-lawnberry-pi-v2/`
**Prerequisites**: plan.md (required), research.md, data-model.md, contracts/

## Execution Flow (main)
```
1. Load plan.md from feature directory
   → If not found: ERROR "No implementation plan found"
   → Extract: tech stack, libraries, structure
2. Load optional design documents:
   → data-model.md: Extract entities → model tasks
   → contracts/: Each file → contract test task
   → research.md: Extract decisions → setup tasks
3. Generate tasks by category:
   → Setup: project init, dependencies, linting
   → Tests: contract tests, integration tests
   → Core: models, services, CLI commands
   → Integration: DB, middleware, logging
   → Polish: unit tests, performance, docs
4. Apply task rules:
   → Different files = mark [P] for parallel
   → Same file = sequential (no [P])
   → Tests before implementation (TDD)
5. Number tasks sequentially (T001, T002...)
6. Generate dependency graph
7. Create parallel execution examples
8. Validate task completeness:
   → All contracts have tests?
   → All entities have model tasks?
   → All endpoints implemented?
9. Return: SUCCESS (tasks ready for execution)
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact absolute file paths in descriptions

## Phase 3.1: Setup (Environment & Structure)
- [x] T001 Create backend and frontend skeletons [web app]
      Paths: /home/pi/lawnberry/backend/, /home/pi/lawnberry/frontend/
- [x] T002 Initialize backend Python project (uv + pyproject) at /home/pi/lawnberry/backend/
- [x] T003 [P] Configure backend lint/format (ruff/black) at /home/pi/lawnberry/backend/
- [x] T004 Initialize frontend (Vue 3 + Vite) at /home/pi/lawnberry/frontend/
- [x] T005 [P] Configure frontend lint/format (eslint/prettier) at /home/pi/lawnberry/frontend/
- [x] T006 Setup tests folders
      Paths: /home/pi/lawnberry/tests/{contract,integration,unit}/
- [x] T007 Constitutional bootstrap (ARM64 checks, isolation policy docs)
      Paths: /home/pi/lawnberry/README.md, /home/pi/lawnberry/docs/constitution.md

## Phase 3.2: Tests First (TDD) — MUST FAIL BEFORE IMPLEMENTATION
- [x] T008 [P] Contract test for REST API from /home/pi/lawnberry/specs/004-lawnberry-pi-v2/contracts/rest-api.yaml
      File: /home/pi/lawnberry/tests/contract/test_rest_api.py
- [x] T009 [P] Contract test for WebSocket API from /home/pi/lawnberry/specs/004-lawnberry-pi-v2/contracts/websocket-api.yaml
      File: /home/pi/lawnberry/tests/contract/test_websocket_api.py
- [x] T010 [P] Integration tests: Core autonomous operation scenarios (1-3)
      File: /home/pi/lawnberry/tests/integration/test_autonomous_operation.py
- [x] T011 [P] Integration tests: WebUI experience scenarios (4-8)
      File: /home/pi/lawnberry/tests/integration/test_webui_experience.py
- [x] T012 [P] Integration tests: Hardware & platform compliance (9-11)
      File: /home/pi/lawnberry/tests/integration/test_hardware_compliance.py
- [x] T013 [P] Integration tests: Migration & maintenance (12) 
      File: /home/pi/lawnberry/tests/integration/test_migration_v1_to_v2.py
- [x] T014 [P] Edge case tests (GPS loss, sensor failure, Wi-Fi loss, weather, E-Stop, Pi4B degradation, hardware absence, SIM_MODE)
      File: /home/pi/lawnberry/tests/integration/test_edge_cases.py
- [x] T015 Unit test scaffolds for models/services (placeholders)
      Path: /home/pi/lawnberry/tests/unit/

## Phase 3.3: Backend Core (Models, Services, API) — Implement after tests are failing
- [x] T016 [P] Create models package
      Path: /home/pi/lawnberry/backend/src/models/__init__.py
- [x] T017 [P] SensorData model from data-model.md
      File: /home/pi/lawnberry/backend/src/models/sensor_data.py
- [x] T018 [P] NavigationState model
      File: /home/pi/lawnberry/backend/src/models/navigation_state.py
- [x] T019 [P] MotorControl model
      File: /home/pi/lawnberry/backend/src/models/motor_control.py
- [x] T020 [P] PowerManagement model
      File: /home/pi/lawnberry/backend/src/models/power_management.py
- [x] T021 [P] CameraStream model
      File: /home/pi/lawnberry/backend/src/models/camera_stream.py
- [x] T022 [P] AIProcessing model
      File: /home/pi/lawnberry/backend/src/models/ai_processing.py
- [x] T023 [P] TrainingData model
      File: /home/pi/lawnberry/backend/src/models/training_data.py
- [x] T024 [P] WebUIPageContracts model
      File: /home/pi/lawnberry/backend/src/models/webui_contracts.py
- [x] T025 [P] TelemetryExchange model
      File: /home/pi/lawnberry/backend/src/models/telemetry_exchange.py
- [x] T026 [P] UserSession model
      File: /home/pi/lawnberry/backend/src/models/user_session.py
- [x] T027 [P] HardwareBaseline model
      File: /home/pi/lawnberry/backend/src/models/hardware_baseline.py
- [x] T028 [P] SystemConfiguration model
      File: /home/pi/lawnberry/backend/src/models/system_configuration.py
- [x] T029 [P] OperationalData model
      File: /home/pi/lawnberry/backend/src/models/operational_data.py

- [x] T030 Create services package
      Path: /home/pi/lawnberry/backend/src/services/__init__.py
- [x] T031 Sensor manager service (I2C/UART coordination, validation flags)
      File: /home/pi/lawnberry/backend/src/services/sensor_manager.py
- [x] T032 Navigation service (sensor fusion, dead reckoning, safety)
      File: /home/pi/lawnberry/backend/src/services/navigation_service.py
- [x] T033 Motor control service (RoboHAT/Cytron, L298N fallback)
      File: /home/pi/lawnberry/backend/src/services/motor_service.py
- [x] T034 Power management service (INA3221 channels, sun-seeking)
      File: /home/pi/lawnberry/backend/src/services/power_service.py
- [x] T035 Camera stream service client (IPC to camera-stream.service)
      File: /home/pi/lawnberry/backend/src/services/camera_client.py
- [x] T036 AI processing service (TFLite/OpenCV, Coral venv, Hailo)
      File: /home/pi/lawnberry/backend/src/services/ai_service.py
- [x] T037 Telemetry hub (WebSocket publisher)
      File: /home/pi/lawnberry/backend/src/services/telemetry_hub.py
- [x] T038 Auth service (shared operator credential, JWT)
      File: /home/pi/lawnberry/backend/src/services/auth_service.py

- [x] T039 Create API package
      Path: /home/pi/lawnberry/backend/src/api/__init__.py
- [x] T040 REST API scaffolding (FastAPI router, base wiring)
      File: /home/pi/lawnberry/backend/src/api/rest.py

      Implement each endpoint as its own task (same file → sequential, no [P]):
- [x] T041 Implement POST /auth/login
      File: /home/pi/lawnberry/backend/src/api/rest.py
- [x] T042 Implement GET /dashboard/status
      File: /home/pi/lawnberry/backend/src/api/rest.py
 - [x] T043 Implement GET /dashboard/telemetry
      File: /home/pi/lawnberry/backend/src/api/rest.py
 - [x] T044 Implement GET /map/zones
      File: /home/pi/lawnberry/backend/src/api/rest.py
 - [x] T045 Implement POST /map/zones
      File: /home/pi/lawnberry/backend/src/api/rest.py
 - [x] T046 Implement GET /map/locations
      File: /home/pi/lawnberry/backend/src/api/rest.py
 - [x] T047 Implement PUT /map/locations
      File: /home/pi/lawnberry/backend/src/api/rest.py
 - [x] T048 Implement POST /control/drive
      File: /home/pi/lawnberry/backend/src/api/rest.py
 - [x] T049 Implement POST /control/blade
      File: /home/pi/lawnberry/backend/src/api/rest.py
 - [x] T050 Implement POST /control/emergency-stop
      File: /home/pi/lawnberry/backend/src/api/rest.py
- [x] T051 Implement GET /planning/jobs
      File: /home/pi/lawnberry/backend/src/api/rest.py
- [x] T052 Implement POST /planning/jobs
      File: /home/pi/lawnberry/backend/src/api/rest.py
- [x] T053 Implement DELETE /planning/jobs/{jobId}
      File: /home/pi/lawnberry/backend/src/api/rest.py
- [x] T054 Implement GET /ai/datasets
      File: /home/pi/lawnberry/backend/src/api/rest.py
- [x] T055 Implement POST /ai/datasets/{datasetId}/export
      File: /home/pi/lawnberry/backend/src/api/rest.py
- [x] T056 Implement GET /settings/system
      File: /home/pi/lawnberry/backend/src/api/rest.py
- [x] T057 Implement PUT /settings/system
      File: /home/pi/lawnberry/backend/src/api/rest.py

- [x] T058 WebSocket endpoint for telemetry hub
      File: /home/pi/lawnberry/backend/src/api/rest.py
- [x] T059 Backend app entrypoint
      File: /home/pi/lawnberry/backend/src/main.py

## Phase 3.4: Backend Integration & Infra
- [x] T060 SQLite persistence layer and migrations
      File: /home/pi/lawnberry/backend/src/core/persistence.py
- [x] T061 Configuration management (JSON files, atomic writes)
      File: /home/pi/lawnberry/backend/src/core/config.py
- [x] T062 Logging & observability (structured logs, metrics)
      File: /home/pi/lawnberry/backend/src/core/observability.py
- [x] T063 Systemd service files for backend services
      Path: /home/pi/lawnberry/systemd/
- [x] T064 IPC sockets and coordination contracts
      File: /home/pi/lawnberry/backend/src/core/ipc.py

## Phase 3.5: Frontend Tests (TDD) — MUST FAIL BEFORE IMPLEMENTATION
- [x] T065 [P] E2E test: Dashboard live telemetry @ 5Hz
      File: /home/pi/lawnberry/frontend/tests/e2e/test_dashboard.spec.ts
- [x] T066 [P] E2E test: Map setup polygon + validation
      File: /home/pi/lawnberry/frontend/tests/e2e/test_map_setup.spec.ts
- [x] T067 [P] E2E test: Manual control gated by auth
      File: /home/pi/lawnberry/frontend/tests/e2e/test_manual_control.spec.ts
- [x] T068 [P] E2E test: AI training export (COCO/YOLO)
      File: /home/pi/lawnberry/frontend/tests/e2e/test_ai_training.spec.ts
- [x] T069 [P] Integration tests: WebSocket client cadence control
      File: /home/pi/lawnberry/frontend/tests/integration/test_ws_client.ts
- [x] T070 [P] Unit tests: Components scaffolds
      Path: /home/pi/lawnberry/frontend/tests/unit/

## Phase 3.6: Frontend Implementation
- [x] T071 Create Vue app skeleton
      Path: /home/pi/lawnberry/frontend/src/
- [x] T072 Pages x7 (Dashboard, Map Setup, Manual Control, Mow Planning, AI Training, Settings, Docs Hub)
      Path: /home/pi/lawnberry/frontend/src/pages/
- [x] T073 Components (widgets for telemetry, maps, controls)
      Path: /home/pi/lawnberry/frontend/src/components/
- [x] T074 Services (REST client, WS client, auth)
      Path: /home/pi/lawnberry/frontend/src/services/
- [x] T075 Retro 1980s theme assets
      Path: /home/pi/lawnberry/frontend/src/assets/

## Phase 3.7: Compliance, Docs, and CI
- [x] T076 Documentation updates (API refs, operational procedures)
      Paths: /home/pi/lawnberry/docs/
- [x] T077 Constitutional compliance script (platform, isolation, resource ownership)
      File: /home/pi/lawnberry/scripts/check_constitution.sh
- [x] T078 Update / quickstart verification scripts
      Files: /home/pi/lawnberry/scripts/test_latency.py, /home/pi/lawnberry/scripts/test_websocket_load.py
- [x] T079 Performance tests (<100ms latency target)
      Files: /home/pi/lawnberry/scripts/test_performance_degradation.py
- [x] T080 Workflows run & journal update (post-merge/PR validation)
      Action: Run `.github/workflows` then update `/home/pi/lawnberry/lawnberry-rebuild/.specify/memory/AGENT_JOURNAL.md`

## Phase 3.8: Coverage Additions from Analysis
- [x] T081 Weather integration service (BME280 + OpenWeatherMap client)
      Files: /home/pi/lawnberry/backend/src/services/weather_service.py, /home/pi/lawnberry/backend/src/core/weather_client.py
- [x] T082 [P] Weather rules in Mow Planning (gate scheduling, optimal windows)
      File: /home/pi/lawnberry/backend/src/services/navigation_service.py
- [x] T083 [P] REST endpoints for weather data and planning advice
      File: /home/pi/lawnberry/backend/src/api/rest.py
- [ ] T084 [P] Frontend weather UI elements on Mow Planning
      Path: /home/pi/lawnberry/frontend/src/pages/
- [x] T085 Caching: Implement ETag/Last-Modified + Cache-Control on cacheable GETs
      Files: /home/pi/lawnberry/backend/src/api/rest.py
- [x] T086 [P] Contract tests for caching semantics (ETag/If-None-Match)
      File: /home/pi/lawnberry/tests/contract/test_caching.py
- [x] T087 Audit logging middleware and persistence
      Files: /home/pi/lawnberry/backend/src/core/persistence.py, /home/pi/lawnberry/backend/src/api/rest.py
- [x] T088 [P] Tests for audit logs (manual control, config changes, exports)
      File: /home/pi/lawnberry/tests/integration/test_audit_logging.py
- [x] T089 Backups and migration scripts (+ tests)
      Files: /home/pi/lawnberry/scripts/backup.sh, /home/pi/lawnberry/scripts/restore.sh, /home/pi/lawnberry/tests/integration/test_backup_migration.py
- [x] T090 Auth hardening: rate limiting and lockout on /auth/login
      File: /home/pi/lawnberry/backend/src/api/rest.py
- [x] T091 [P] Tests for login rate limit and lockout
      File: /home/pi/lawnberry/tests/integration/test_auth_hardening.py
- [x] T092 WebSocket reconnection/backoff + resubscribe
      File: /home/pi/lawnberry/backend/src/api/rest.py
- [x] T093 [P] Frontend WS client reconnection/resubscribe tests
      File: /home/pi/lawnberry/frontend/tests/integration/test_ws_resilience.spec.ts
- [ ] T094 Dead-reckoning acceptance tests (drift bounds)
      File: /home/pi/lawnberry/tests/integration/test_dead_reckoning.py
- [x] T095 Docs drift detection CI step
      File: /home/pi/lawnberry/.github/workflows/docs-drift.yml
- [x] T096 Systemd health probes and boot order validation tests
      Files: /home/pi/lawnberry/tests/integration/test_systemd_health.py
- [ ] T097 Frontend auth handling (JWT storage, expiry), gated routes tests
      Files: /home/pi/lawnberry/frontend/src/services/auth.ts, /home/pi/lawnberry/frontend/tests/integration/test_auth_routes.ts
- [ ] T098 Offline maps mode (OSM fallback without key) + tests
      Files: /home/pi/lawnberry/frontend/src/pages/map_setup.ts, /home/pi/lawnberry/frontend/tests/integration/test_offline_maps.ts
- [ ] T099 Docs Hub content build/serve and tests
      Files: /home/pi/lawnberry/frontend/src/pages/docs_hub.tsx, /home/pi/lawnberry/tests/integration/test_docs_hub.py
- [ ] T100 Privacy & log rotation policy and checks
      Files: /home/pi/lawnberry/docs/privacy.md, /home/pi/lawnberry/backend/src/core/logging.py

## Dependencies
- Tests (T008–T015) before backend implementation (T016–T059)
- Backend core (T016–T059) before backend integration (T060–T064)
- Frontend tests (T065–T070) before frontend implementation (T071–T075)
- Observability/Docs/Perf (T076–T079) after core & integration
- Coverage additions (T081–T100) interleave as follows:
      * Weather and caching: T081–T086 after REST scaffolding (T040–T057)
      * Audit, backups/migration, auth hardening: T087–T091 after services and API
      * WS resilience & dead-reckoning: T092–T094 after telemetry and navigation
      * Docs CI and systemd health: T095–T096 near end before T080
      * Frontend auth/offline maps/docs hub: T097–T099 after frontend skeleton
      * Privacy/log rotation: T100 after observability
- Workflows/journal (T080) at the end of the session

## Parallel Execution Examples
```
# Launch contract & integration tests scaffolds in parallel (after setup):
T008, T009, T010, T011, T012, T013, T014, T015

# Implement models in parallel:
T017–T029 (distinct files)

# Frontend E2E tests in parallel:
T065–T070

# Example Task agent commands:
# (Run these in separate terminals or with your Task agent's parallel mode)
agent run T008
agent run T009
agent run T010
agent run T011
agent run T012
agent run T013
agent run T014
agent run T015
```

## Validation Checklist
- [ ] All contracts have corresponding tests → T008, T009
- [ ] All entities have model tasks → T017–T029
- [ ] All tests precede implementation → Sections 3.2 and 3.5
- [ ] Parallel tasks operate on distinct files → [P] flags used
- [ ] Each task specifies exact absolute file path
- [ ] Constitutional rules explicitly covered → T007, T077, T080

