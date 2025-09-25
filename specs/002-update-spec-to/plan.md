# Implementation Plan: WebUI Page & Hardware Alignment Update

**Branch**: `002-update-spec-to` | **Date**: 2025-09-24 | **Spec**: `/home/pi/lawnberry_pi/specs/002-update-spec-to/spec.md`
**Input**: Feature specification from `/home/pi/lawnberry_pi/specs/002-update-spec-to/spec.md`

## Summary
- Extracted all clarifications and baseline requirements from the updated spec so the seven WebUI pages (`Dashboard`, `Map Setup`, `Manual Control`, `Mow Planning`, `AI Training`, `Settings`, `Docs Hub`) each call out their route mapping plus REST and WebSocket dependencies.
- Documented how telemetry streams provide a 5 Hz default cadence (expandable to 10 Hz under normal operations and degradable to 1 Hz for diagnostics), how the single shared operator credential gates sensitive controls, and how COCO + YOLO dataset exports are produced.
- Mapped hardware expectations directly to `spec/hardware.yaml`, keeping preferred/alternative components, INA3221 channel assignments, motor controller hierarchy, GPS selection rules, and acceleration hierarchy aligned with the constitution.
- Captured retro LawnBerry Pi branding requirements (logo, icon set, robot pin marker) that must flow through Dashboard, Manual Control, and Docs Hub surfaces.
- Produced research, data modeling, contract, and quickstart artifacts that downstream commands and implementers will follow when refreshing the specification and validating service coverage.

## Technical Context
**Performance Goals**: Dashboard telemetry broadcast at 5 Hz default (expandable to 10 Hz) with operator overrides; export jobs must finish ≤5 minutes for 5k-image batches
**Scale/Scope**: Seven WebUI surfaces, six core REST endpoints, five WebSocket topics, two dataset export formats, single shared credential path, three branded asset touchpoints
| Telemetry cadence expectations | Verified 5 Hz default with operator-adjustable range (10 Hz headroom, 1 Hz diagnostic mode); documented impacts on bandwidth, buffering, and downshift triggers. |
**Language/Version**: Markdown documentation + YAML references (Raspberry Pi OS Bookworm, Python 3.11 ecosystem)
| REST/WebSocket coverage | Catalogued existing service surfaces, noted deltas (Map Setup diff endpoints, Manual Control command channel acknowledgement), and linked each page to concrete REST routes and WebSocket topics. |
| Branding assets | Confirmed requirement to surface `LawnBerryPi_logo.png`, `LawnBerryPi_icon2.png`, and LawnBerry Pi robot pin markers across Dashboard, Manual Control, and Docs Hub per platform story. |
**Primary Dependencies**: `spec/hardware.yaml`, existing LawnBerry REST/WebSocket surfaces, dataset export tooling (COCO JSON, YOLO TXT)
**Storage**: Git-tracked Markdown/YAML artifacts within `/home/pi/lawnberry_pi/specs/002-update-spec-to`
**Testing**: Documentation diff reviews, contract schema validation via OpenAPI/AsyncAPI linting, constitution cross-checks
**Target Platform**: LawnBerry Pi v2 mower fleet (Raspberry Pi OS Bookworm 64-bit on Pi 5 / Pi 4B)
**Project Type**: single (documentation + contract alignment)
**Constraints**: Must respect AI acceleration hierarchy (Coral → Hailo → CPU), uphold INA3221 channel assignments, forbid pycoral in main env, keep simulation parity for every page/contract

## Constitution Check
- **Platform Exclusivity**: Documentation keeps focus on Raspberry Pi OS Bookworm with Python 3.11 runtimes; no cross-platform deviation introduced. ✅
- **AI Acceleration Hierarchy**: Plan reiterates Coral → Hailo → CPU ordering and confines Coral usage to USB/isolated venv as mandated. ✅
- **Documentation-as-Contract**: Every artifact references `spec/hardware.yaml`, ensuring documentation remains the source of truth. ✅
- **Hardware Compliance**: INA3221 channel mapping, RoboHAT occupancy, and acceleration conflicts are explicitly preserved in hardware alignment notes. ✅
- **Runtime & Communications Standards**: Contracts lean on existing REST + WebSocket infrastructure without introducing forbidden transports. ✅

All guardrails pass; no constitutional violations to justify.

## Project Structure

### Documentation (this feature)
```
/home/pi/lawnberry_pi/specs/002-update-spec-to/
├── plan.md              # Implementation plan (this document)
├── research.md          # Phase 0 findings (generated)
├── data-model.md        # Phase 1 entity definitions (generated)
├── quickstart.md        # Phase 1 validation workflow (generated)
├── contracts/           # Phase 1 OpenAPI + AsyncAPI specs (generated)
└── spec.md              # Feature specification (input)
```

### Source Code (repository root)
```
src/
├── ai/
├── services/
├── contracts/
└── lib/

tests/
├── contract/
├── integration/
└── unit/
```

**Structure Decision**: Option 1 (single project). Existing repo already separates `src/` and `tests/`; no additional frontend/backend split is needed for this documentation-forward feature.

## Phase 0: Outline & Research
| Item | Outcome |
| --- | --- |
| Telemetry cadence expectations | Verified 5 Hz default with operator-adjustable range (10 Hz headroom, 1 Hz diagnostic mode); documented impacts on bandwidth, buffering, and downshift triggers. |
| Authentication scheme | Locked to single shared operator credential with manual control hard gate; contrasted against per-user RBAC and rejected due to added complexity. |
| Dataset export formats | Confirmed COCO JSON + YOLO TXT must be generated in one export job; evaluated Pascal VOC as an alternative and discarded. |
| REST/WebSocket coverage | Catalogued existing service surfaces, noted deltas (Map Setup diff endpoints, Manual Control command channel acknowledgement), and linked each page to concrete REST routes and WebSocket topics. |
| Branding assets | Confirmed requirement to surface `LawnBerryPi_logo.png`, `LawnBerryPi_icon2.png`, and LawnBerry Pi robot pin markers across Dashboard, Manual Control, and Docs Hub per platform story. |
| Hardware manifest alignment | Diffed `spec/hardware.yaml` elements to ensure spec callouts cover preferred/alternate hardware, conflicts, and INA3221 assignments. |

See `research.md` for detailed rationale and alternatives.

## Phase 1: Design & Contracts
- Authored `data-model.md` capturing `WebUIPage`, `TelemetryStream`, `DatasetExportJob`, `HardwareProfile`, and `OperatorCredential` entities with relationships and validation rules.
- Generated OpenAPI specification at `contracts/webui-openapi.yaml` for REST endpoints supporting each page, including dataset export job management.
- Produced AsyncAPI channels in `contracts/webui-websocket.yaml` for telemetry, map editing broadcasts, manual-control feedback, mowing job events, and AI training progress.
- Drafted `quickstart.md` guiding reviewers through contract validation, spec updates, and hardware cross-checks.
- Updated GitHub Copilot agent context via `.specify/scripts/bash/update-agent-context.sh copilot` so assistant memory reflects the new documentation & contract focus.

## Phase 2: Task Planning Approach
- `/tasks` will read this plan plus generated artifacts to enumerate documentation edits, contract wiring, and validation steps.
- Expected task clusters:
	* Update spec sections per WebUI page (seven tasks, each referencing REST + WS contracts).
	* Align hardware section with manifest (preferred, alternative, conflict, INA3221 mapping).
	* Capture authentication + dataset export narratives and link to contracts.
	* Create verification tasks for OpenAPI + AsyncAPI linting and simulation parity checks.
- Tasks will be grouped in TDD order: produce/update contracts/tests before adjusting specification prose, then verify hardware alignment.
- Parallelization: Page-specific edits can proceed concurrently once shared contract language is staged; contract linting and spec editing remain serialized to prevent drift.

## Phase 3+: Future Implementation
**Phase 3**: `/tasks` command generates `tasks.md` from this plan.  
**Phase 4**: Implement documentation, contract references, and supporting tests per tasks list.  
**Phase 5**: Run doc linting, OpenAPI/AsyncAPI validation, and manual Quickstart walkthrough.

## Complexity Tracking
| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *(none)* | – | – |

## Progress Tracking
**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [x] Phase 2: Task planning complete (/plan command - approach documented)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented (none identified)

---
*Based on Constitution v1.2.0 - See `/home/pi/lawnberry_pi/v2/lawnberry-v2/.specify/memory/constitution.md`*
