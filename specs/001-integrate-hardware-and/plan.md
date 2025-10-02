
# Implementation Plan: Integrate Hardware & Complete UI

**Branch**: `001-integrate-hardware-and` | **Date**: 2024-05-07 | **Spec**: [`specs/001-integrate-hardware-and/spec.md`](./spec.md)
**Input**: Feature specification from `/specs/001-integrate-hardware-and/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → If not found: ERROR "No feature spec at {path}"
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → Detect Project Type from context (web=frontend+backend, mobile=app+api)
   → Set Structure Decision based on project type
3. Fill the Constitution Check section based on the content of the constitution document.
4. Evaluate Constitution Check section below
   → If violations exist: Document in Complexity Tracking
   → If no justification possible: ERROR "Simplify approach first"
   → Update Progress Tracking: Initial Constitution Check
5. Execute Phase 0 → research.md
   → If NEEDS CLARIFICATION remain: ERROR "Resolve unknowns"
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, agent-specific template file (e.g., `CLAUDE.md` for Claude Code, `.github/copilot-instructions.md` for GitHub Copilot, `GEMINI.md` for Gemini CLI, `QWEN.md` for Qwen Code or `AGENTS.md` for opencode).
7. Re-evaluate Constitution Check section
   → If new violations: Refactor design, return to Phase 1
   → Update Progress Tracking: Post-Design Constitution Check
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
9. STOP - Ready for /tasks command
```

**IMPORTANT**: The /plan command STOPS at step 7. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary
Integrate all LawnBerry Pi v2 hardware telemetry through the FastAPI backend and WebSocket hub while validating 5 Hz streams against hardware ranges, expose RoboHAT firmware health metadata, and restore Dashboard, Map Setup, Control, and Settings pages with constitutional branding and offline-ready documentation. The approach reuses existing backend services, augments audit logging, enforces Google Maps with OSM fallback, adds telemetry export workflows for diagnostic power data, threads RTK/GNSS fallback and IMU orientation health cues through the telemetry pipeline, and codifies performance checks (≤250 ms latency on Pi 5 / ≤350 ms on Pi 4B) with automated pytest, script coverage, and CI gating that blocks deployment if telemetry/UI/doc validations regress. Frontend flows will surface contextual remediation prompts that deep-link into the refreshed documentation bundle whenever validations fail.

## Technical Context
**Language/Version**: Python 3.11 (backend), TypeScript + Vue 3 (frontend)  
**Primary Dependencies**: FastAPI, Uvicorn, Pydantic v2, websockets, Vue 3 + Vite, Pinia, Leaflet/Google Maps SDK  
**Storage**: SQLite (`data/lawnberry.db`), JSON config files under `/config`, filesystem artifacts  
**Testing**: pytest (contract/integration/unit), Vitest + Playwright (frontend), custom perf scripts in `scripts/`  
**Target Platform**: Raspberry Pi OS Lite Bookworm (64-bit) on Raspberry Pi 5 (16 GB) with Raspberry Pi 4B graceful degradation
**Project Type**: web (split frontend + backend)
**Performance Goals**: ≤250 ms dashboard telemetry latency on Pi 5; ≤350 ms on Pi 4B fallback; 5 Hz telemetry cadence configurable 1–10 Hz  
**Constraints**: Offline-accessible Docs Hub, mandatory LawnBerry branding assets, accelerator isolation (Coral/Hailo), SIM_MODE coverage for CI, hardware manifest immutability, CI workflows that fail builds on telemetry/UI/doc regression  
**Scale/Scope**: Single residential mower deployment; multiple UI pages (Dashboard, Map Setup, Control, Settings) and documentation bundle refresh

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- PASS – Platform exclusivity & degradation guardrail upheld via Pi OS Lite Bookworm targeting Pi 5 (16 GB) with explicit Pi 4B fallback validation steps in quickstart.
- PASS – Package isolation hierarchy preserved by keeping accelerator enablement optional and gated behind detection toggles with isolated environments.
- PASS – Test-first development enforced through contract/integration pytest expansions, SIM_MODE parity, and perf guardrail scripts.
- PASS – Hardware resource coordination maintained by reusing single-owner daemons and RoboHAT watchdog handshake documented in research.
- PASS – Constitutional hardware compliance satisfied by honoring `spec/hardware.yaml`, INA3221 mapping, and firmware version exposure.
- PASS – LawnBerry identity & assets protected by restoring retro-themed UI, verifying branding checksums, and updating Docs Hub content.

## Project Structure

### Documentation (this feature)
```
specs/[###-feature]/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
# Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure]
```

**Structure Decision**: Option 2 (Web application: backend + frontend)

## Phase 0: Outline & Research
1. **Extract unknowns from Technical Context** above:
   - For each NEEDS CLARIFICATION → research task
   - For each dependency → best practices task
   - For each integration → patterns task

2. **Generate and dispatch research agents**:
   ```
   For each unknown in Technical Context:
     Task: "Research {unknown} for {feature context}"
   For each technology choice:
     Task: "Find best practices for {tech} in {domain}"
   ```

3. **Consolidate findings** in `research.md` using format:
   - Decision: [what was chosen]
   - Rationale: [why chosen]
   - Alternatives considered: [what else evaluated]

**Output**: research.md with all NEEDS CLARIFICATION resolved

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

1. **Extract entities from feature spec** → `data-model.md`:
   - Entity name, fields, relationships
   - Validation rules from requirements
   - State transitions if applicable

2. **Generate API contracts** from functional requirements:
   - For each user action → endpoint
   - Use standard REST/GraphQL patterns
   - Output OpenAPI/GraphQL schema to `/contracts/`

3. **Generate contract tests** from contracts:
   - One test file per endpoint
   - Assert request/response schemas
   - Tests must fail (no implementation yet)

4. **Extract test scenarios** from user stories:
   - Each story → integration test scenario
   - Quickstart test = story validation steps

5. **Update agent file incrementally** (O(1) operation):
   - Run `.specify/scripts/bash/update-agent-context.sh copilot`
     **IMPORTANT**: Execute it exactly as specified above. Do not add or remove any arguments.
   - If exists: Add only NEW tech from current plan
   - Preserve manual additions between markers
   - Update recent changes (keep last 3)
   - Keep under 150 lines for token efficiency
   - Output to repository root

6. **Document CI gating strategy**:
       - Identify telemetry/UI/doc workflows requiring blocking status checks
       - Plan updates to `.github/workflows/` ensuring FR-013 compliance
       - Capture remediation steps for failed gates in documentation bundle

7. **Design remediation guidance hooks**:
    - Map telemetry, control, and settings validation failures to specific documentation entries
    - Capture required fields in API responses and WebUI states for contextual help links
    - Update quickstart/verification notes describing how operators access remediation prompts

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, agent-specific file

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Load `.specify/templates/tasks-template.md` as base
- Generate tasks from Phase 1 design docs (contracts, data model, quickstart)
- Each contract → contract test task [P]
- Each entity → model creation task [P] 
- Each user story → integration test task
- Implementation tasks to make tests pass

**Ordering Strategy**:
- TDD order: Tests before implementation 
- Dependency order: Models before services before UI
- Mark [P] for parallel execution (independent files)

**Estimated Output**: 25-30 numbered, ordered tasks in tasks.md

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |


## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [ ] Phase 1: Design complete (/plan command)
- [ ] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [ ] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [ ] Complexity deviations documented

---
*Based on Constitution v1.5.0 - See `/.specify/memory/constitution.md`*
