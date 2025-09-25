# Implementation Plan: LawnBerry Pi v2 Unified System

**Branch**: `004-lawnberry-pi-v2` | **Date**: 2025-09-25 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/home/pi/lawnberry/specs/004-lawnberry-pi-v2/spec.md`

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
Autonomous robotic lawn mower system with comprehensive WebUI providing real-time monitoring, manual control, autonomous operation planning, AI-powered obstacle detection, and system configuration. Technical approach centers on constitutional compliance with platform exclusivity (Raspberry Pi OS Bookworm, Python 3.11.x), package isolation for AI acceleration, test-first development, hardware resource coordination, and systemd service management.

## Technical Context
**Language/Version**: Python 3.11.x (constitutional requirement)
**Primary Dependencies**: FastAPI/Flask (WebUI), Picamera2+GStreamer (camera), python-periphery+lgpio (GPIO), pyserial (UART), systemd (services), uv (package management)
**Storage**: SQLite/files for operational data, configuration persistence, historical metrics
**Testing**: pytest with SIM_MODE=1 hardware simulation, contract tests, integration tests
**Target Platform**: Raspberry Pi OS Bookworm (64-bit) on Pi 5 (primary) or Pi 4B (compatible)
**Project Type**: web - autonomous system backend + comprehensive WebUI frontend
**Performance Goals**: <100ms WebUI latency, 5Hz telemetry (scalable to 10Hz), real-time obstacle detection
**Constraints**: ARM64-only dependencies, constitutional package isolation, camera service exclusive ownership, no Ethernet runtime dependency
**Scale/Scope**: Single-user autonomous mower system, 7 WebUI pages, 25+ functional requirements, constitutional compliance

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Platform Exclusivity**: ✅ PASS - Raspberry Pi OS Bookworm 64-bit, Python 3.11.x exclusively
**Package Isolation**: ✅ PASS - pycoral/edgetpu banned from main env, Coral in venv-coral, uv dependency management
**Test-First Development**: ✅ PASS - TDD mandatory, SIM_MODE=1 simulation, comprehensive test coverage
**Hardware Resource Coordination**: ✅ PASS - Camera service exclusive ownership, single-owner resources, proper coordination
**Constitutional Hardware Compliance**: ✅ PASS - INA3221 fixed channels, GPS options (ZED-F9P/Neo-8M), motor control alignment
**Technology Stack**: ✅ PASS - Approved technologies (Picamera2, python-periphery, pyserial, systemd), retro WebUI aesthetic
**Development Workflow**: ✅ PASS - Documentation updates, agent journaling, workflow execution, ARM64 validation

## Project Structure

### Documentation (this feature)
```
specs/004-lawnberry-pi-v2/
├── plan.md              # This file (/plan command output)
├── research.md          # Phase 0 output (/plan command)
├── data-model.md        # Phase 1 output (/plan command)
├── quickstart.md        # Phase 1 output (/plan command)
├── contracts/           # Phase 1 output (/plan command)
└── tasks.md             # Phase 2 output (/tasks command - NOT created by /plan)
```

### Source Code (repository root)
```
# Option 2: Web application (backend + frontend detected)
backend/
├── src/
│   ├── models/          # Sensor data, navigation, power, configuration entities
│   ├── services/        # Hardware coordination, AI processing, telemetry
│   ├── api/             # REST endpoints, WebSocket hub
│   └── core/            # Safety protocols, constitutional compliance
└── tests/
    ├── contract/        # API contract tests
    ├── integration/     # Hardware-in-the-loop, simulation
    └── unit/            # Component tests

frontend/
├── src/
│   ├── components/      # Dashboard, Map, Control, Planning, Training, Settings, Docs
│   ├── pages/           # Seven mandated WebUI pages
│   ├── services/        # WebSocket client, REST client, authentication
│   └── assets/          # Retro 1980s branding assets
└── tests/
    ├── e2e/             # User scenario validation
    ├── integration/     # API integration tests
    └── unit/            # Component tests
```

**Structure Decision**: Option 2 (Web application) - autonomous system backend with comprehensive WebUI frontend

## Phase 0: Outline & Research
1. **Extract unknowns from Technical Context** above:
   - No NEEDS CLARIFICATION markers - specification is comprehensive
   - Dependencies well-defined through constitutional requirements
   - Integration patterns established via clarifications

2. **Generate and dispatch research agents**:
   ```
   Task: "Research FastAPI vs Flask for autonomous system backend with WebSocket support"
   Task: "Find best practices for Picamera2+GStreamer integration with exclusive service ownership"
   Task: "Research ARM64-compatible AI acceleration libraries (TFLite, OpenCV-DNN)"
   Task: "Find patterns for systemd service coordination and hardware resource management"
   Task: "Research retro 1980s WebUI frameworks and design patterns"
   ```

3. **Consolidate findings** in `research.md` using format:
   - Decision: [what was chosen]
   - Rationale: [why chosen]
   - Alternatives considered: [what else evaluated]

**Output**: research.md with all technical decisions resolved

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

1. **Extract entities from feature spec** → `data-model.md`:
   - Hardware entities: Sensor data, navigation state, motor control, power management
   - AI entities: Camera stream, AI processing, training data
   - WebUI entities: Page contracts, telemetry exchange, user session
   - System entities: Hardware baseline, configuration, operational data

2. **Generate API contracts** from functional requirements:
   - REST API for WebUI functionality (FR-017)
   - WebSocket hub for real-time telemetry (FR-016)
   - Hardware service interfaces for sensor coordination
   - Output OpenAPI specifications to `/contracts/`

3. **Generate contract tests** from contracts:
   - One test file per endpoint/service
   - Assert request/response schemas
   - Tests must fail (no implementation yet)

4. **Extract test scenarios** from user stories:
   - 12 acceptance scenarios → integration test scenarios
   - Edge cases → negative test scenarios
   - Constitutional compliance → validation tests

5. **Update agent file incrementally** (O(1) operation):
   - Run `.specify/scripts/bash/update-agent-context.sh copilot`
   - Add new tech stack from current plan
   - Preserve manual additions between markers
   - Update recent changes (keep last 3)
   - Keep under 150 lines for token efficiency
   - Output to repository root

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, .github/copilot-instructions.md

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Load `.specify/templates/tasks-template.md` as base
- Generate tasks from Phase 1 design docs (contracts, data model, quickstart)
- Each contract → contract test task [P]
- Each entity → model creation task [P] 
- Each user story → integration test task
- Implementation tasks to make tests pass
- Constitutional compliance validation tasks

**Ordering Strategy**:
- TDD order: Tests before implementation 
- Constitutional order: Platform setup → Package isolation → Hardware coordination → Services → WebUI
- Dependency order: Backend models → Backend services → Backend API → Frontend services → Frontend components
- Mark [P] for parallel execution (independent files)

**Estimated Output**: 40-50 numbered, ordered tasks in tasks.md covering:
- Environment setup and constitutional compliance
- Backend test suite (contract, integration, unit)
- Backend implementation (models, services, API)
- Frontend test suite (e2e, integration, unit)
- Frontend implementation (components, pages, services)
- System integration and validation

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)  
**Phase 4**: Implementation (execute tasks.md following constitutional principles)  
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

No constitutional violations identified. All requirements align with established principles.

## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [ ] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented (none required)

---
*Based on Constitution v1.3.0 - See `/.specify/memory/constitution.md`*
