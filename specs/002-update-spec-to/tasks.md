# Tasks: WebUI Page & Hardware Alignment Update

**Input**: Design documents from `/specs/002-update-spec-to/`
**Prerequisites**: `plan.md` (required), `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

## Phase 3.1: Setup
- [ ] T001 Restructure the WebUI section in `specs/002-update-spec-to/spec.md` by adding a "Page Overview" table that lists all seven pages and links to future subsections.
- [ ] T002 Add a "Hardware Alignment Scope" subsection in `specs/002-update-spec-to/spec.md` describing how updates will mirror `/spec/hardware.yaml`, including placeholders for preferred, alternative, and conflict notes.

## Phase 3.2: Tests First (TDD) ⚠️ execute before Phase 3.3
- [ ] T003 [P] Create contract validation test `tests/contract/test_webui_rest_contracts.py` that loads `specs/002-update-spec-to/contracts/webui-openapi.yaml` and asserts every documented endpoint (dashboard, map, manual, mow planning, AI training, settings, docs) is present with required response schemas.
- [ ] T004 [P] Create contract validation test `tests/contract/test_webui_websocket_contracts.py` that loads `specs/002-update-spec-to/contracts/webui-websocket.yaml` and asserts telemetry cadence defaults, heartbeat intervals, and topic coverage for all five channels.
- [ ] T005 [P] Add integration test `tests/integration/test_webui_pages_contract_matrix.py` that parses `specs/002-update-spec-to/spec.md` and fails unless each page subsection references at least one REST endpoint and one WebSocket topic from the contracts.
- [ ] T006 [P] Add integration test `tests/integration/test_shared_operator_auth.py` ensuring `specs/002-update-spec-to/spec.md` documents the shared operator credential gate for manual control and dataset exports.
- [ ] T007 [P] Add integration test `tests/integration/test_hardware_manifest_alignment.py` that compares the hardware section of `specs/002-update-spec-to/spec.md` against `/spec/hardware.yaml` for INA3221 channels, acceleration hierarchy, and conflict notes.

## Phase 3.3: Core Implementation (models → documentation)
### Data model implementations (can run in parallel)
- [ ] T008 [P] Implement `WebUIPage` dataclass in `src/lawnberry/specs/webui_page.py` mirroring the fields defined in `data-model.md`.
- [ ] T009 [P] Implement `TelemetryStream` dataclass in `src/lawnberry/specs/telemetry_stream.py` with cadence, schema, and criticality fields.
- [ ] T010 [P] Implement `RestContract` dataclass in `src/lawnberry/specs/rest_contract.py` capturing method, path, schemas, auth, and caching metadata.
- [ ] T011 [P] Implement `WebSocketTopic` dataclass in `src/lawnberry/specs/websocket_topic.py` with message schema, heartbeat, and backfill flags.
- [ ] T012 [P] Implement `DatasetExportJob` dataclass in `src/lawnberry/specs/dataset_export_job.py` with requested formats, status states, and artifact URLs.
- [ ] T013 [P] Implement `HardwareProfile` dataclass in `src/lawnberry/specs/hardware_profile.py` describing preferred/alternate components, conflicts, and bus requirements.
- [ ] T014 [P] Implement `OperatorCredential` dataclass in `src/lawnberry/specs/operator_credential.py` covering permissions and rotation metadata.

### Documentation updates (sequential edits to spec.md)
- [ ] T015 Document the `Dashboard` page subsection in `specs/002-update-spec-to/spec.md`, linking to `/api/dashboard/state`, `/api/dashboard/alerts`, and the `telemetry/updates` topic with 1 Hz cadence notes.
- [ ] T016 Document the `Map Setup` page subsection in `specs/002-update-spec-to/spec.md`, describing zone editing workflows and references to `/api/map/zones` plus `map/updates` broadcasts.
- [ ] T017 Document the `Manual Control` page subsection in `specs/002-update-spec-to/spec.md`, including shared credential requirements, `/api/manual/command`, and `manual/feedback` acknowledgements.
- [ ] T018 Document the `Mow Planning` page subsection in `specs/002-update-spec-to/spec.md`, referencing `/api/mow/jobs`, `/api/mow/jobs/{jobId}`, and `mow/jobs/{jobId}/events` progress.
- [ ] T019 Document the `AI Training` page subsection in `specs/002-update-spec-to/spec.md`, highlighting dataset review, `/api/ai/datasets`, `/api/ai/datasets/export`, and `ai/training/progress` messaging with COCO + YOLO exports.
- [ ] T020 Document the `Settings` page subsection in `specs/002-update-spec-to/spec.md`, covering `/api/settings/profile`, hardware selection, simulation toggles, and cadence overrides.
- [ ] T021 Document the `Docs Hub` page subsection in `specs/002-update-spec-to/spec.md`, citing `/api/docs/index` and on-device documentation expectations.

## Phase 3.4: Integration & Alignment
- [ ] T022 Enrich the hardware section in `specs/002-update-spec-to/spec.md` with preferred vs. alternate listings, RoboHAT limitations, and INA3221 channel mapping sourced from `/spec/hardware.yaml`.
- [ ] T023 Update `specs/002-update-spec-to/quickstart.md` to reference the new page subsections, contract matrix, and simulation validation steps.
- [ ] T024 Update `specs/002-update-spec-to/research.md` with final decisions and trade-offs observed during implementation, including any rejected alternatives.
- [ ] T025 Add a cross-reference appendix to `specs/002-update-spec-to/spec.md` that maps each `data-model.md` entity to its REST/WS contract usage.

## Phase 3.5: Polish & Verification
- [ ] T026 [P] Run `spectacular lint specs/002-update-spec-to/contracts/webui-openapi.yaml` and capture results in the MR/PR discussion.
- [ ] T027 [P] Run `asyncapi validate specs/002-update-spec-to/contracts/webui-websocket.yaml` and capture results in the MR/PR discussion.
- [ ] T028 Execute repository quality gates (`uv lock`, `ruff`, `black`, `mypy`, `pytest`) to ensure constitutional compliance after documentation and model updates.
- [ ] T029 [P] Update `docs/architecture.md` with a brief note describing the WebUI specification alignment work and links to the updated spec.

## Dependencies
- T001 → T015-T021 (page subsections rely on the overview table).
- T002 → T022, T025 (alignment scope must exist before filling details and cross-references).
- T003-T007 must be completed and observed failing before starting T008 and onwards.
- T008-T014 unblock page documentation tasks (structures referenced in appendix).
- T015-T021 must finish before T022-T025 integrate cross references.
- T026-T028 require all documentation and models to be in place.

## Parallel Execution Example
```
# Run contract and integration tests together after Phase 3.1:
/tasks run T003 T004 T005 T006 T007

# Implement dataclasses concurrently:
/tasks run T008 T009 T010 T011 T012 T013 T014

# Finish polish commands once documentation is merged:
/tasks run T026 T027 T029
```

## Notes
- Mark tasks complete as soon as the change lands in the repository.
- [P] tasks touch independent files or commands and can be run in parallel safely.
- Always commit after each sequential milestone (Setup → Tests → Models → Documentation → Integration → Polish).
