cd# Implementation Plan: LawnBerry Pi v2

**Branch**: `001-build-lawnberry-pi` | **Date**: 2025-09-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/home/pi/lawnberry_pi/specs/001-build-lawnberry-pi/spec.md`

## Summary
Primary requirement: Build autonomous robotic lawn mower system with real-time monitoring and control capabilities. Technical approach: FastAPI backend with WebSocket hub, React frontend, multi-tier AI acceleration, SQLite persistence, and systemd service management following Raspberry Pi OS Bookworm platform constraints.

## Technical Context
**Language/Version**: Python 3.11 (constitutional requirement)  
**Primary Dependencies**: FastAPI, websockets, structlog, pydantic, React+Vite, sqlite-utils  
**Storage**: SQLite for runs/faults/settings, filesystem for logs/video  
**Testing**: pytest-asyncio for async testing, contract tests, integration tests with simulation  
**Target Platform**: Raspberry Pi OS Bookworm (ARM64) - Pi 5 primary, Pi 4B compatible  
**Project Type**: web (backend FastAPI + frontend React)  
**Performance Goals**: Real-time telemetry (<100ms latency), video streaming (720p@15fps), AI inference (<200ms)  
**Constraints**: ARM64 only, isolated Coral venv, systemd service management, offline-capable  
**Scale/Scope**: Single mower unit, 8 modules, 3 services, comprehensive testing and documentation

## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- ✅ **Platform Exclusivity**: Python 3.11, RPi OS Bookworm (ARM64), Pi 5/4B only
- ✅ **AI Acceleration Hierarchy**: coral_runner (isolated venv), hailo_runner, cpu_tflite_runner fallback
- ✅ **Code Quality Gates**: uv lock, ruff/black/mypy, pytest-asyncio, src/ layout
- ✅ **Documentation-as-Contract**: Will update /docs and /spec, load hardware.yaml/agent_rules.md
- ✅ **Runtime Standards**: systemd units, .env via dotenv, Picamera2, periphery+lgpio, pyserial
- ✅ **Hardware Compliance**: Support BNO085, INA3221, VL53L0X, hall encoders, Cytron MDDRC10
- ✅ **Test-Driven Development**: TDD with contract/integration/unit tests, hardware interface tests

## Project Structure

### Documentation (this feature)
```
specs/001-build-lawnberry-pi/
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
src/lawnberry/
├── models/              # Pydantic data models
├── services/            # Business logic services
├── api/                 # FastAPI endpoints
├── core/               # WebSocket hub, config
└── runners/            # AI acceleration runners

tests/
├── contract/           # API contract tests
├── integration/        # Service integration tests
└── unit/              # Unit tests

frontend/
├── src/
│   ├── components/     # React components
│   ├── pages/         # Main UI pages
│   └── services/      # WebSocket/API clients
└── tests/

systemd/               # Service definitions
scripts/               # Installation and setup
```

**Structure Decision**: Option 2 (Web application) - FastAPI backend + React frontend detected

## Phase 0: Outline & Research
No NEEDS CLARIFICATION items detected in Technical Context. All technology choices specified by user in arguments.

**Research Tasks**:
1. FastAPI + WebSocket best practices for real-time telemetry
2. AI acceleration integration patterns (TFLite, Coral TPU, Hailo)
3. Raspberry Pi hardware interface patterns (GPIO, I2C, UART)
4. React retro 80s theme implementation approaches
5. SQLite schema design for telemetry and operational data
6. SystemD service orchestration for multi-service deployment

**Research.md Generation**: Technology decisions, integration patterns, and implementation approaches.

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

**Entity Extraction**: 10 key entities from spec → data-model.md
**API Contract Generation**: WebSocket events + REST endpoints → /contracts/
**Contract Test Generation**: Test files for each API contract
**Integration Scenarios**: User story validation → quickstart.md
**Agent Context Update**: Run update-agent-context.sh for copilot integration

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, .github/copilot-instructions.md

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Multi-service architecture: backend services (mower-core, camera-stream) + webui
- TDD approach: Contract tests → Integration tests → Implementation
- Module-based development: 8 core modules (sensors, navigation, motion, safety, power, camera, webui, ai)
- AI runner isolation: Separate tasks for each acceleration tier
- Frontend build integration: React build process and deployment

**Ordering Strategy**:
- Setup: Project structure, dependencies, linting
- Tests: Contract tests for APIs, integration tests for services
- Core: Models, services, WebSocket hub
- Modules: Individual module implementation
- AI: Runner implementations with proper environment isolation
- Frontend: React UI development
- Integration: Service orchestration, systemd units
- Deployment: Scripts, documentation, migration tools

**Estimated Output**: 35-40 numbered, ordered tasks covering full system implementation

## Complexity Tracking
*No constitutional violations identified*

## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [x] Phase 0: Research complete (/plan command)
- [x] Phase 1: Design complete (/plan command)
- [x] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [x] Initial Constitution Check: PASS
- [x] Post-Design Constitution Check: PASS
- [x] All NEEDS CLARIFICATION resolved
- [x] Complexity deviations documented

---
*Based on Constitution v1.0.0 - See `/memory/constitution.md`*
