# Implementation Plan: LawnBerry Pi v2 — Complete Rebuild to Production Operation

**Branch**: `005-complete-the-rebuild` | **Date**: 2025-09-27 | **Spec**: /home/pi/lawnberry/specs/005-complete-the-rebuild/spec.md
**Input**: Feature specification from `/specs/005-complete-the-rebuild/spec.md`

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
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, agent-specific template file
7. Re-evaluate Constitution Check section
   → If new violations: Refactor design, return to Phase 1
   → Update Progress Tracking: Post-Design Constitution Check
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
9. STOP - Ready for /tasks command
```

## Summary
From the spec: deliver a production-ready autonomous mower system with WebUI (7 pages), real hardware operation (non-sim), safety-first control, AI detection with acceleration hierarchy, centralized WebSocket hub, REST API, single shared operator credential with MFA, built-in secure remote access (ACME HTTP-01 TLS), adaptive Google Maps usage with OSM fallback, and a final cutover replacing the original build.

## Technical Context
**Language/Version**: Python 3.11 (Raspberry Pi OS Bookworm, ARM64)  
**Primary Dependencies**: Picamera2 + GStreamer, python-periphery + lgpio, pyserial; WebUI stack (frontend present in repo); systemd  
**Storage**: On-device persistence (files/SQLite) per existing repo patterns  
**Testing**: pytest-based tests in `tests/` with SIM_MODE=1 for CI; add contract/integration tests per plan  
**Target Platform**: Raspberry Pi 5 (primary), Pi 4B (compatible)  
**Project Type**: web (frontend + backend)  
**Performance Goals**: WebSocket telemetry at 5 Hz default (<100ms latency), scalable to 10 Hz; graceful degrade to 1 Hz  
**Constraints**: Package isolation (Coral in venv-coral), systemd-managed services, camera single-owner via IPC, INA3221 channel mapping, GPS mutually exclusive configs  
**Scale/Scope**: Single-device deployment with LAN/optional remote access; user-operated mower

## Constitution Check
Gates from constitution:
- Platform exclusivity: Raspberry Pi OS Bookworm 64-bit; Python 3.11.x
- Package isolation: Coral in isolated venv-coral; ban pycoral/edgetpu in main env
- Test-first development: add/extend failing tests before implementation; SIM_MODE=1 coverage
- Hardware resource coordination: camera service owns device; other consumers via IPC
- Hardware compliance: INA3221 channel mapping; GPS configs; motor controller options; HAT conflicts avoided

Status: Initial check PASS (no conflicts planned).

## Project Structure
Structure Decision: Web application (frontend + backend present) per template Option 2.

## Phase 0: Outline & Research
Create `/home/pi/lawnberry/specs/005-complete-the-rebuild/research.md` consolidating decisions:
- MFA specifics (TOTP format, backup code count)
- ACME HTTP-01 reachability and port handling on Pi + systemd integration
- Adaptive map usage thresholds and OSM fallback triggers on Pi hardware
- Dead reckoning constraints (speed cap, sensor fusion trust window)
- Service ownership and IPC framing for camera stream

## Phase 1: Design & Contracts
Outputs:
- `/home/pi/lawnberry/specs/005-complete-the-rebuild/data-model.md` (entities: SensorData, NavigationState, MotorCommand, PowerReading, Job, Zone, UserSession, Alert, etc.)
- `/home/pi/lawnberry/specs/005-complete-the-rebuild/contracts/` REST + WebSocket topic contracts (OpenAPI plus topic matrix)
- `/home/pi/lawnberry/specs/005-complete-the-rebuild/quickstart.md` (bring-up, SIM_MODE, non-sim hardware run, remote access TLS)
- Update agent context via `.specify/scripts/bash/update-agent-context.sh copilot`

## Phase 2: Task Planning Approach
Describe tasks generation in `plan.md` (do not create `tasks.md`).

## Complexity Tracking
None expected.

## Progress Tracking
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
- [ ] Complexity deviations documented
