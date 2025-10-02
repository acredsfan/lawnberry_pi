# Tasks: Integrate Hardware & Complete UI

**Input**: Design documents from `/specs/001-integrate-hardware-and/`
**Prerequisites**: `plan.md` (required), `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

## Execution Flow (main)
```
1. Load plan.md and extract tech stack, structure, constraints
2. Load optional artifacts when available:
   → data-model.md → entity/model tasks
   → contracts/ → contract test tasks
   → research.md → domain decisions and guardrails
   → quickstart.md → validation & performance scenarios
3. Generate tasks by category (setup → tests → models → implementation → polish)
4. Apply task rules:
   → Different files = mark [P] for parallel work
   → Same file = sequential (no [P])
   → Tests before implementation (TDD)
5. Number tasks sequentially (T001, T002, ...)
6. Capture dependencies and parallel examples
7. Validate coverage: every contract, entity, endpoint, and user story represented
```

## Format: `[ID] [P?] Description`
- **[P]**: Task can run in parallel (touches independent files once prerequisites met)
- Include exact file paths in each description

## Path Conventions
- Backend: `backend/src/`, `backend/tests/`
- Frontend: `frontend/src/`, `frontend/tests/`
- Scripts & docs: `scripts/`, `docs/`, `verification_artifacts/`

## Phase 3.1: Setup
- [X] T001 Update backend dependency manifest in `pyproject.toml` to add geometry validation and firmware telemetry tooling required for map overlap checks and RoboHAT latency measurements while preserving accelerator isolation, then run `.specify/scripts/bash/update-agent-context.sh copilot` to record the refreshed dependency set in the agent context.
- [X] T002 [P] Augment `frontend/package.json` with Google Maps loader, Leaflet (or equivalent), telemetry charting libs, and type definitions; refresh npm scripts to lint/test the new map UI stack.

## Phase 3.2: Tests First (TDD) ⚠️ MUST COMPLETE BEFORE 3.3
**Contract Tests**
- [X] T003 [P] Expand `tests/contract/test_rest_api_telemetry.py` to assert GET `/api/v2/telemetry/stream` pagination, RTK/IMU orientation state fields with fallback messaging when corrections drop, GET `/api/v2/telemetry/export` diagnostic downloads (power metrics), and POST `/api/v2/telemetry/ping` latency guardrails (≤250 ms / ≤350 ms).
- [X] T004 [P] Extend `tests/contract/test_rest_api_control.py` with coverage for GET `/api/v2/hardware/robohat` plus POST `/api/v2/control/{drive,blade,emergency}` safety responses and audit IDs.
- [X] T005 [P] Update `tests/contract/test_rest_api_maps.py` to validate GET/PUT `/api/v2/map/configuration` persistence, overlap rejection, and provider fallback semantics.
- [X] T006 [P] Extend `tests/contract/test_rest_api_settings.py` for GET/PUT `/api/v2/settings` including profile_version conflicts, latency targets, and branding checksum checks.
- [X] T007 [P] Add `tests/contract/test_docs_and_verification.py` covering GET `/api/v2/docs/bundle` responses and POST `/api/v2/verification-artifacts` validation of linked FRs.
- [X] T008 [P] Expand `tests/contract/test_websocket_topics.py` to enforce handshake, auth, payload schema, and latency headers for `/api/v2/ws/{telemetry,control,settings,notifications}`.

**Integration Tests**
- [X] T009 [P] Enhance `tests/integration/test_dashboard_telemetry.py` to drive SIM_MODE + hardware fixtures validating 5 Hz streams, latency budgets, RTK dropout recovery with fallback messaging and doc link surfacing, telemetry export downloads for diagnostics, and evidence capture.
- [X] T010 [P] Enhance `tests/integration/test_maps_api_management.py` to execute the Map Setup scenario (markers, polygons, backend acknowledgement, OSM fallback).
- [X] T011 [P] Create `tests/integration/test_control_manual_flow.py` to verify manual drive/blade/emergency commands, RoboHAT watchdog echoes, audit logging, and remediation prompts that reference control troubleshooting documentation when safety lockouts occur.
- [X] T012 [P] Create `tests/integration/test_settings_experience.py` for full Settings page lifecycle (hardware/network/telemetry panels, profile version bump, SQLite parity) and validation failure scenarios that surface contextual help links into the documentation bundle.
- [X] T013 [P] Extend `tests/integration/test_docs_hub.py` to confirm offline bundle generation, checksum validation, and documentation freshness alerts.
- [X] T014 [P] Update `tests/integration/test_telemetry_perf.py` to measure Raspberry Pi 4B graceful degradation via `--device pi4` thresholds and SIM_MODE backoffs.

## Phase 3.3: Core Implementation (Data Models)
- [X] T015 [P] Implement `HardwareTelemetryStream` schema in `backend/src/models/telemetry_exchange.py` with GPS, IMU, motors, blade, battery fields. Include RTK metadata, orientation data, and latency tracking.
- [X] T016 [P] Extend `backend/src/models/zone.py` with `MapConfiguration` supporting markers (Home, AM Sun, PM Sun), boundary/exclusion polygons, overlap rejection (via Shapely if available), and provider metadata (Google Maps/OSM fallback).
- [X] T017 [P] Create `backend/src/models/control_session.py` with `ControlCommand`, `ControlAuditEntry`, `EmergencyState`. Track safety interlocks, latency, watchdog acknowledgement, and status_reason for troubleshooting link logic.
- [X] T018 [P] Update `backend/src/models/system_configuration.py` with `SettingsProfile` consolidating hardware calibration, network, telemetry cadence (1–10 Hz), simulation_mode, AI acceleration choice, branding checksum, and version bump helpers.
- [X] T019 [P] Add `DocumentationBundle` to `backend/src/models/webui_contracts.py` with offline generation (tarball/ZIP), checksum validation, freshness alerts (>90 days stale warning), and path traversal protection helpers.
- [X] T020 [P] Create `backend/src/models/verification_artifact.py` modeling artifact types, linked requirements, persistence identifiers, and timestamps.

## Phase 3.4: Integration (Backend & Frontend)
- [X] T021 Implement telemetry backend domain: update `backend/src/services/telemetry_hub.py`, `backend/src/services/sensor_manager.py`, `backend/src/core/persistence.py`, and `scripts/test_performance_degradation.py` to persist `HardwareTelemetryStream`, compute latency stats, derive RTK fallback/orientation states, expose `/api/v2/telemetry/export` diagnostic downloads, broadcast `/api/v2/ws/telemetry`, align ping responses, and attach remediation doc references to degraded telemetry payloads.
- [X] T022 Wire telemetry & dashboard UI: extend `frontend/src/services/api.ts`, `frontend/src/services/websocket.ts`, `frontend/src/composables/useWebSocket.ts`, `frontend/src/stores/system.ts`, `frontend/src/views/DashboardView.vue`, and add `frontend/src/types/telemetry.ts` to render live metrics with latency badges, show RTK fallback/orientation banners with remediation links, and provide power-metric export/download controls.
- [X] T023 Build control backend domain: add `backend/src/services/robohat_service.py`, extend `backend/src/services/motor_service.py` and `backend/src/services/websocket_hub.py`, and expose `/api/v2/hardware/robohat` plus `/api/v2/control/{drive,blade,emergency}` in `backend/src/api/rest.py` with audit + lockout logic.
- [X] T024 Refresh control UI: create `frontend/src/stores/control.ts`, update `frontend/src/views/ControlView.vue`, and extend `frontend/src/services/api.ts`/`frontend/src/services/websocket.ts` for command submission, lockout indicators, echo telemetry, and remediation callouts that deep-link to the control troubleshooting docs when safety interlocks trigger.
- [X] T025 Complete map backend domain: extend `backend/src/services/maps_service.py`, `backend/src/core/persistence.py`, and `/api/v2/map/configuration` handlers in `backend/src/api/rest.py` for GeoJSON validation, persistence, and provider fallback.
- [X] T026 Rebuild map UI: create `frontend/src/stores/map.ts`, add/edit `frontend/src/components/map/BoundaryEditor.vue`, and update `frontend/src/views/MapsView.vue` plus `frontend/src/services/api.ts` for marker placement and polygon editing.
- [X] T027 Deliver settings & documentation backend: extend `backend/src/core/config.py`, add/update `backend/src/services/settings_service.py`, `backend/src/core/persistence.py`, and `/api/v2/settings`, `/api/v2/docs/bundle`, `/api/v2/verification-artifacts` handlers in `backend/src/api/rest.py`, plus implement `scripts/generate_docs_bundle.py`, ensuring validation errors return remediation metadata linked to documentation entries.
- [X] T028 Upgrade settings/docs UI: update `frontend/src/views/SettingsView.vue`, `frontend/src/views/DocsHubView.vue`, `frontend/src/stores/system.ts`, and add `frontend/src/types/settings.ts` to manage panels, branding checksum checks, docs manifest, offline indicators, and contextual remediation prompts that link operators to the correct documentation pages.

## Phase 3.5: Polish & Evidence
- [X] **T029**: Add focused unit tests for new services/stores (`tests/unit/test_telemetry_service.py`, `tests/unit/test_control_session.py`, `frontend/tests/unit/systemStore.spec.ts`, `frontend/tests/unit/controlStore.spec.ts`)
- [X] **T030**: Update operator documentation in `docs/hardware-overview.md`, `docs/hardware-feature-matrix.md`, `docs/OPERATIONS.md`, and author `verification_artifacts/001-integrate-hardware-and/README.md` plus `AGENT_JOURNAL.md` entries aligning with quickstart evidence
- [X] **T031**: Harden CI gating by extending `.github/workflows/ci.yml` (and related pipelines) to run telemetry export, UI regression, and documentation drift checks; ensure failures block deployment per FR-013
- [X] **T032**: Document the new CI gates in `docs/OPERATIONS.md` and update branch protection notes / runbooks so operators know how to remediate failing status checks

## Dependencies
- Setup (T001–T002) must precede all other tasks.
- Contract & integration tests (T003–T014) must run before any implementation tasks.
- Data model tasks (T015–T020) unblock backend integration tasks (T021–T027).
- Telemetry backend (T021) must complete before telemetry frontend (T022).
- Control backend (T023) precedes control frontend (T024).
- Map backend (T025) precedes map frontend (T026).
- Settings/documentation backend (T027) precedes UI updates (T028) and polish doc work (T030).
- CI gating (T031) executes after functional validation to wire pipelines before final documentation (T032).
- Polish tasks (T029–T032) run after all functional work is complete.

## Parallel Execution Example
```bash
# Kick off independent contract and integration tests once setup is done
copilot tasks run --id T003 --id T005 --id T007 --id T009

# Later, execute model tasks in parallel after tests are failing
copilot tasks run --id T015 --id T016 --id T019 --id T020
```

## Notes
- Ensure every test added in Phase 3.2 fails before starting Phase 3.3 work.
- Maintain constitutional guardrails: Raspberry Pi 5 primary, Pi 4B graceful degradation, branding asset integrity, and SIM_MODE parity.
- Capture telemetry and UI artifacts during execution to satisfy verification requirements in T030.
