# Tasks: LawnBerry Pi v2 — Complete Rebuild to Production Operation

**Input**: Design documents from `/specs/005-complete-the-rebuild/`
**Prerequisites**: plan.md (required), research.md, data-model.md, contracts/

## Phase 3.1: Setup
- [X] T001 Configure backend test scaffolding and env
  - Paths: /home/pi/lawnberry/lawnberry-rebuild/backend/src, /home/pi/lawnberry/lawnberry-rebuild/tests
  - Add pytest config if missing, ensure SIM_MODE=1 supported in tests
- [X] T002 [P] Prepare frontend test and branding scaffolding
  - Paths: /home/pi/lawnberry/lawnberry-rebuild/frontend, /home/pi/lawnberry/lawnberry-rebuild/frontend/tests
  - Ensure vite+vitest setup and place LawnBerry assets (logo, icon, pin)
- [X] T003 [P] Add CI hooks for docs/spec drift checks
  - Paths: /home/pi/lawnberry/lawnberry-rebuild/.github, /home/pi/lawnberry/docs

## Phase 3.2: Tests First (TDD) — Contract & Integration
- [X] T004 [P] Contract tests for API status endpoint
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/contract/test_status.py
  - Contract: /home/pi/lawnberry/specs/005-complete-the-rebuild/contracts/openapi.yaml (/api/v1/status)
- [X] T005 [P] Contract tests for auth login (MFA start)
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/contract/test_auth_login.py
  - Contract: /home/pi/lawnberry/specs/005-complete-the-rebuild/contracts/openapi.yaml (/api/v1/auth/login)
- [X] T006 [P] Contract tests for zones CRUD
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/contract/test_zones.py
  - Contract: /home/pi/lawnberry/specs/005-complete-the-rebuild/contracts/openapi.yaml (/api/v1/maps/zones)
- [X] T007 [P] Contract tests for jobs queue/list
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/contract/test_jobs.py
  - Contract: /home/pi/lawnberry/specs/005-complete-the-rebuild/contracts/openapi.yaml (/api/v1/mow/jobs)
- [X] T008 [P] WebSocket topic contract tests
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/contract/test_websocket_topics.py
  - Spec: /home/pi/lawnberry/specs/005-complete-the-rebuild/contracts/websocket-topics.md
- [X] T009 [P] Integration test: Dashboard telemetry 5 Hz (<100ms)
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_dashboard_telemetry.py
  - Scenario: quickstart.md and spec acceptance
- [X] T010 [P] Integration test: Manual control gated by MFA
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_manual_control_auth.py
  - Scenario: FR-018, Clarifications (MFA)
- [X] T011 [P] Integration test: GPS loss policy grace then stop/alert
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_gps_loss_policy.py
  - Scenario: FR-002 (≤2 min dead reckoning, reduced speed, then stop/alert)
- [X] T012 [P] Integration test: Map cost adaptive use then OSM fallback
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_map_cost_control.py
  - Scenario: FR-010 (adaptive then fallback)
- [X] T013 [P] Integration test: ACME TLS provisioning flow
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_acme_tls.py
  - Scenario: FR-028 (HTTP-01 auto renew, fail-closed)
- [X] T013a [P] Integration test: Remote access configuration (Cloudflare/ngrok)
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_remote_access_config.py
  - Scenario: FR-027 (Cloudflare tunnels, ngrok, user-defined configurations)
- [X] T013b [P] Integration test: Configurable authentication security levels
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_auth_security_levels.py
  - Scenario: FR-018 (password, TOTP, Google Auth, Cloudflare tunnel auth)
- [X] T013c [P] Integration test: Maps API key management and bypass
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_maps_api_management.py
  - Scenario: FR-010 (user API keys, bypass options, validation)

## Phase 3.3: Core Models & Services (after tests added and failing)
- [X] T014 [P] Model: SensorData
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/sensor_data.py
- [X] T015 [P] Model: NavigationState
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/navigation_state.py
- [X] T016 [P] Model: MotorCommand
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/motor_command.py
- [X] T017 [P] Model: PowerReading
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/power_reading.py
- [X] T018 [P] Model: Job
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/job.py
- [X] T019 [P] Model: Zone
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/zone.py
- [X] T020 [P] Model: UserSession
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/user_session.py
- [X] T021 [P] Model: Alert
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/alert.py
- [X] T021a [P] Model: RemoteAccessConfig
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/remote_access_config.py
  - Support Cloudflare tunnel, ngrok, and custom configurations
- [X] T021b [P] Model: AuthSecurityConfig
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/models/auth_security_config.py
  - Support configurable security levels and MFA options

- [X] T022 Service: Telemetry/WebSocket hub
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/websocket_hub.py
- [X] T023 Service: Auth (configurable security levels, MFA options)
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/auth_service.py
  - Support password, TOTP, Google Auth, Cloudflare tunnel auth
- [X] T024 Service: Maps (Google + OSM adaptive, user API keys)
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/maps_service.py
  - Support user-supplied API keys, bypass options, validation
- [X] T025 Service: Jobs/Mow planning
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/jobs_service.py
- [X] T026 Service: ACME TLS manager (HTTP-01)
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/acme_service.py
- [X] T026a Service: Remote access manager (Cloudflare/ngrok)
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/remote_access_service.py
  - Support Cloudflare tunnel setup, ngrok configuration, custom options

## Phase 3.4: Endpoints & Topics (after services)
- [X] T027 Implement GET /api/v1/status
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/api/rest_v1.py
- [X] T028 Implement POST /api/v1/auth/login (MFA start)
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/api/rest_v1.py
- [X] T029 Implement /api/v1/maps/zones (GET/POST)
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/api/rest_v1.py
- [X] T030 Implement /api/v1/mow/jobs (GET/POST)
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/api/rest_v1.py
- [X] T031 Implement WebSocket topics
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/api/rest.py & /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/websocket_hub.py
- [X] T031a Implement enhanced Settings endpoints (FR-029)
  - File: /home/pi/lawnberry/lawnberry-rebuild/backend/src/api/rest_v1.py
  - Support remote access, auth levels, maps API, GPS policies configuration

## Phase 3.5: Frontend Pages & Branding
- [X] T032 Dashboard page (80s branding, live telemetry)
  - Path: /home/pi/lawnberry/lawnberry-rebuild/frontend/src/views/Dashboard.vue
- [X] T033 Map Setup page (configurable provider, API key input, pin asset)
  - Path: /home/pi/lawnberry/lawnberry-rebuild/frontend/src/views/MapSetup.vue
  - Support Google Maps/OSM toggle, user API key input, bypass options
- [X] T034 Manual Control page (auth‑gated with security level awareness)
  - Path: /home/pi/lawnberry/lawnberry-rebuild/frontend/src/views/ManualControl.vue
  - Adapt to user's configured authentication security level
- [X] T035 Mow Planning page
  - Path: /home/pi/lawnberry/lawnberry-rebuild/frontend/src/views/MowPlanning.vue
- [X] T036 AI Training page (dataset export UX)
  - Path: /home/pi/lawnberry/lawnberry-rebuild/frontend/src/views/AITraining.vue
- [X] T037 Enhanced Settings page (remote access, auth levels, maps, GPS)
  - Path: /home/pi/lawnberry/lawnberry-rebuild/frontend/src/views/Settings.vue
  - Add Cloudflare/ngrok setup, auth security config, maps API management, GPS policy settings
- [X] T038 Docs Hub page (offline docs & search, setup guides)
  - Path: /home/pi/lawnberry/lawnberry-rebuild/frontend/src/views/DocsHub.vue
  - Include guides for remote access setup, API key acquisition, auth configuration

## Phase 3.6: Integration & Systemd
- [X] T039 systemd unit for frontend (lawnberry-frontend.service)
  - Path: /home/pi/lawnberry/lawnberry-rebuild/systemd/lawnberry-frontend.service
- [X] T040 ACME challenge port handling and renewal timer
  - Path: /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/acme_service.py & systemd timers
- [X] T041 Camera service ownership and IPC wiring
  - Path: /home/pi/lawnberry/lawnberry-rebuild/backend/src/services/camera_stream_service.py
- [X] T041a Remote access service integration
  - Path: /home/pi/lawnberry/lawnberry-rebuild/systemd/lawnberry-remote-access.service
  - systemd integration for Cloudflare tunnel and ngrok services

## Phase 3.7: Polish & Docs
- [X] T042 [P] Unit tests for enhanced auth flows (security levels)
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/unit/test_auth_security_levels.py
- [X] T043 [P] Performance tests for telemetry pipeline
  - File: /home/pi/lawnberry/lawnberry-rebuild/tests/integration/test_telemetry_perf.py
- [X] T044 [P] Enhanced documentation: Install/setup/run/migration with new guides
  - Paths: /home/pi/lawnberry/docs, /home/pi/lawnberry/specs/005-complete-the-rebuild/quickstart.md
  - Include Cloudflare tunnel setup, ngrok configuration, API key acquisition guides
- [X] T044a [P] Documentation: Remote access setup guides
  - File: /home/pi/lawnberry/lawnberry-rebuild/docs/remote-access-setup.md
  - Comprehensive guides for Cloudflare tunnels, ngrok, custom configurations
- [X] T044b [P] Documentation: Authentication configuration guide
  - File: /home/pi/lawnberry/lawnberry-rebuild/docs/authentication-config.md
  - Guide for security levels, TOTP setup, Google Auth, backup codes
- [X] T044c [P] Documentation: Maps API key acquisition guide
  - File: /home/pi/lawnberry/lawnberry-rebuild/docs/maps-api-setup.md
  - Step-by-step guide for obtaining Google Maps API keys, OSM setup
- [X] T045 [P] Final cutover plan and rollback validation
  - File: /home/pi/lawnberry/lawnberry-rebuild/docs/cutover-rollback-plan.md
  - Complete cutover plan with rollback procedures and validation steps

## Parallel Execution Guidance
- Launch in parallel:
  - [P] T002, T003
  - [P] T004–T008 (contract & WS tests)
  - [P] T009–T013c (integration tests including new ones)
  - [P] T014–T021b (models including new config models)
- Sequential groups:
  - Services (T022–T026a) before Endpoints (T027–T031a)
  - Endpoints before Frontend integration (T032–T038)
  - Enhanced Settings (T037) depends on T031a (Settings endpoints)

## New Requirements Coverage
- **FR-027**: Remote access options → T013a, T021a, T026a, T037, T041a, T044a
- **FR-018**: Configurable authentication → T013b, T021b, T023, T034, T037, T042, T044b  
- **FR-010**: Enhanced maps with user API keys → T013c, T024, T033, T037, T044c
- **FR-029**: Comprehensive configuration management → T031a, T037
- **FR-025**: Enhanced documentation → T038, T044a-c

## Validation Checklist
- [X] All new contracts have corresponding tests (T013a–T013c)
- [X] All new entities have model tasks (T021a–T021b)
- [X] All tests precede implementation
- [X] Parallel tasks target different files
- [X] Each task specifies absolute file paths
- [X] No [P] tasks write to the same file
- [X] New FR requirements mapped to specific tasks

## Implementation Status: COMPLETE ✅

**All phases completed successfully:**
- ✅ Phase 3.1: Setup (T001-T003)
- ✅ Phase 3.2: Tests First - TDD (T004-T013c) 
- ✅ Phase 3.3: Core Models & Services (T014-T026a)
- ✅ Phase 3.4: Endpoints & Topics (T027-T031a)
- ✅ Phase 3.5: Frontend Pages & Branding (T032-T038)
- ✅ Phase 3.6: Integration & Systemd (T039-T041a)
- ✅ Phase 3.7: Polish & Documentation (T042-T045)

**Key Achievements:**
- Dual API architecture (v1/v2) with backward compatibility
- Configurable authentication (4 security levels)
- Remote access via Cloudflare tunnels/ngrok
- Smart maps management with cost controls
- Real-time telemetry at 5Hz via WebSocket
- Comprehensive systemd service integration
- Complete documentation suite with setup guides
- Production-ready with cutover/rollback procedures

**System Status:** Ready for production deployment
