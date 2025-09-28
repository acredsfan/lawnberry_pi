# Tasks: LawnBerry Pi v2 — Complete Rebuild to Production Operation

**Input**: Design documents from `/specs/005-complete-the-rebuild/`
**Prerequisites**: plan.md (required), research.md, data-model.md, contracts/

## Phase 3.1: Setup
- [ ] T001 Configure backend test scaffolding and env
  - Paths: /home/pi/lawnberry/lawnberry-rebuild/backend/src, /home/pi/lawnberry/lawnberry-rebuild/tests
  - Add pytest config if missing, ensure SIM_MODE=1 supported in tests
- [ ] T002 [P] Prepare frontend test and branding scaffolding
  - Paths: /home/pi/lawnberry/lawnberry-rebuild/frontend, /home/pi/lawnberry/lawnberry-rebuild/frontend/tests
  - Ensure vite+vitest setup and place LawnBerry assets (logo, icon, pin)
- [ ] T003 [P] Add CI hooks for docs/spec drift checks
  - Paths: /home/pi/lawnberry/lawnberry-rebuild/.github, /home/pi/lawnberry/docs

## Phase 3.2: Tests First (TDD) — Contract & Integration
- [ ] T004 [P] Contract tests for API status endpoint
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/contract/test_status.py
  - Contract: /home/pi/lawnberry/specs/005-complete-the-rebuild/contracts/openapi.yaml (/api/v1/status)
- [ ] T005 [P] Contract tests for auth login (MFA start)
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/contract/test_auth_login.py
  - Contract: /home/pi/lawnberry/specs/005-complete-the-rebuild/contracts/openapi.yaml (/api/v1/auth/login)
- [ ] T006 [P] Contract tests for zones CRUD
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/contract/test_zones.py
  - Contract: /home/pi/lawnberry/specs/005-complete-the-rebuild/contracts/openapi.yaml (/api/v1/maps/zones)
- [ ] T007 [P] Contract tests for jobs queue/list
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/contract/test_jobs.py
  - Contract: /home/pi/lawnberry/specs/005-complete-the-rebuild/contracts/openapi.yaml (/api/v1/mow/jobs)
- [ ] T008 [P] WebSocket topic contract tests
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/contract/test_websocket_topics.py
  - Spec: /home/pi/lawnberry/specs/005-complete-the-rebuild/contracts/websocket-topics.md
- [ ] T009 [P] Integration test: Dashboard telemetry 5 Hz (<100ms)
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_dashboard_telemetry.py
  - Scenario: quickstart.md and spec acceptance
- [ ] T010 [P] Integration test: Manual control gated by MFA
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_manual_control_auth.py
  - Scenario: FR-018, Clarifications (MFA)
- [ ] T011 [P] Integration test: GPS loss policy grace then stop/alert
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_gps_loss_policy.py
  - Scenario: FR-002 (≤2 min dead reckoning, reduced speed, then stop/alert)
- [ ] T012 [P] Integration test: Map cost adaptive use then OSM fallback
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_map_cost_control.py
  - Scenario: FR-010 (adaptive then fallback)
- [ ] T013 [P] Integration test: ACME TLS provisioning flow
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_acme_tls.py
  - Scenario: FR-028 (HTTP-01 auto renew, fail-closed)

## Phase 3.3: Core Models & Services (after tests added and failing)
- [ ] T014 [P] Model: SensorData
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/sensor_data.py
- [ ] T015 [P] Model: NavigationState
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/navigation_state.py
- [ ] T016 [P] Model: MotorCommand
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/motor_command.py
- [ ] T017 [P] Model: PowerReading
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/power_reading.py
- [ ] T018 [P] Model: Job
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/job.py
- [ ] T019 [P] Model: Zone
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/zone.py
- [ ] T020 [P] Model: UserSession
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/user_session.py
- [ ] T021 [P] Model: Alert
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/alert.py

- [ ] T022 Service: Telemetry/WebSocket hub
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/websocket_hub.py
- [ ] T023 Service: Auth (MFA TOTP + backup codes)
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/auth_service.py
- [ ] T024 Service: Maps (Google + OSM adaptive)
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/maps_service.py
- [ ] T025 Service: Jobs/Mow planning
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/jobs_service.py
- [ ] T026 Service: ACME TLS manager (HTTP-01)
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/acme_service.py

## Phase 3.4: Endpoints & Topics (after services)
- [ ] T027 Implement GET /api/v1/status
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/api/rest.py
- [ ] T028 Implement POST /api/v1/auth/login (MFA start)
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/api/rest.py
- [ ] T029 Implement /api/v1/maps/zones (GET/POST)
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/api/rest.py
- [ ] T030 Implement /api/v1/mow/jobs (GET/POST)
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/api/rest.py
- [ ] T031 Implement WebSocket topics
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/api/rest.py & /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/websocket_hub.py

## Phase 3.5: Frontend Pages & Branding
- [ ] T032 Dashboard page (80s branding, live telemetry)
  - Path: /home/pi/lawnberry/lawnberry-rebuild/frontend/src/views/Dashboard.vue
- [ ] T033 Map Setup page (Google default, OSM fallback, pin asset)
  - Path: /home/pi/lawnberry/lawnberry-rebuild/frontend/src/views/MapSetup.vue
- [ ] T034 Manual Control page (auth‑gated)
  - Path: /home/pi/lawnberry/lawnberry-rebuild/frontend/src/views/ManualControl.vue
- [ ] T035 Mow Planning page
  - Path: /home/pi/lawnberry/lawnberry-rebuild/frontend/src/views/MowPlanning.vue
- [ ] T036 AI Training page (dataset export UX)
  - Path: /home/pi/lawnberry/lawnberry-rebuild/frontend/src/views/AITraining.vue
- [ ] T037 Settings page (hardware, sim, cadence, maps, ACME)
  - Path: /home/pi/lawnberry/lawnberry-rebuild/frontend/src/views/Settings.vue
- [ ] T038 Docs Hub page (offline docs & search)
  - Path: /home/pi/lawnberry/lawnberry-rebuild/frontend/src/views/DocsHub.vue

## Phase 3.6: Integration & Systemd
- [ ] T039 systemd unit for frontend (lawnberry-frontend.service)
  - Path: /home/pi/lawnberry/lawnberry-rebuild/systemd/lawnberry-frontend.service
- [ ] T040 ACME challenge port handling and renewal timer
  - Path: /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/acme_service.py & systemd timers
- [ ] T041 Camera service ownership and IPC wiring
  - Path: /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/camera_stream_service.py

## Phase 3.7: Polish & Docs
- [ ] T042 [P] Unit tests for auth MFA flows
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/unit/test_auth_mfa.py
- [ ] T043 [P] Performance tests for telemetry pipeline
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_telemetry_perf.py
- [ ] T044 [P] Documentation: Install/setup/run/migration (Docs Hub)
  - Paths: /home/pi/lawnberry/docs, /home/pi/lawnberry/specs/005-complete-the-rebuild/quickstart.md
- [ ] T045 [P] Final cutover plan and rollback validation
  - File: /home/pi/lawnberry/specs/005-complete-the-rebuild/research.md (append), plus release notes

## Parallel Execution Guidance
- Launch in parallel:
  - [P] T002, T003
  - [P] T004–T008 (contract & WS tests)
  - [P] T009–T013 (integration tests)
  - [P] T014–T021 (models)
- Sequential groups:
  - Services (T022–T026) before Endpoints (T027–T031)
  - Endpoints before Frontend integration (T032–T038)

## Validation Checklist
- [ ] All contracts have corresponding tests (T004–T008)
- [ ] All entities have model tasks (T014–T021)
- [ ] All tests precede implementation
- [ ] Parallel tasks target different files
- [ ] Each task specifies absolute file paths
- [ ] No [P] tasks write to the same file
