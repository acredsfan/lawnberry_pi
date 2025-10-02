<!--
Sync Impact Report:
Version: 1.4.0 → 2.0.0 (Major: Added Safety-First Mandate, Modular Architecture, Navigation, Scheduling, and Observability principles to align with Engineering Plan)
Modified principles: 
  - Principle III expanded with hardware simulation requirements
  - Principle IV enhanced with motor control safety interlocks
Added sections: 
  - Principle VI: Safety-First Engineering (NEW - critical safety requirements)
  - Principle VII: Modular Architecture (NEW - system decomposition)
  - Principle VIII: Navigation & Geofencing (NEW - autonomous operation constraints)
  - Principle IX: Scheduling & Autonomy (NEW - job execution rules)
  - Principle X: Observability & Debuggability (NEW - diagnostic requirements)
Removed sections: None
Templates requiring updates:
  - .specify/templates/plan-template.md (version reference) ✅ to be updated
  - .specify/templates/spec-template.md ✅ no change required
  - .specify/templates/tasks-template.md ✅ no change required
Follow-up TODOs: 
  - Update Phase 2 safety system documentation with constitutional safety latency requirements
  - Document geofencing validation procedures in operations manual
-->

# LawnBerry Pi Constitution

## Core Principles

### I. Platform Exclusivity
The LawnBerry Pi system MUST operate exclusively on Raspberry Pi OS Bookworm (64-bit) with Python 3.11.x runtime on Raspberry Pi 5 (primary) or Pi 4B (compatible). No cross-platform dependencies, alternate interpreters, or non-ARM64 Linux distributions are permitted. All development, testing, and deployment MUST assume this target platform exclusively.

### II. Package Isolation (NON-NEGOTIABLE)
AI acceleration dependencies MUST maintain strict isolation: `pycoral`/`edgetpu` are BANNED from the main environment and MUST use dedicated venv-coral. Coral USB acceleration operates in complete isolation from the main system. Hardware acceleration follows constitutional hierarchy: Coral USB (isolated venv-coral) → Hailo HAT (optional) → CPU fallback (TFLite/OpenCV). Package management via uv with committed lock files ensures reproducible builds.

### III. Test-First Development (NON-NEGOTIABLE)
TDD methodology is mandatory: Tests written → User approved → Tests fail → Implementation begins. Red-Green-Refactor cycle strictly enforced. Every feature starts with failing tests that define expected behavior. No implementation code without corresponding test coverage. Hardware simulation (SIM_MODE=1) MUST provide complete test coverage for CI execution without physical hardware dependencies. Mock drivers MUST replicate hardware behavior including latency, failure modes, and state transitions for comprehensive testing without physical hardware.

### IV. Hardware Resource Coordination
Hardware interfaces are single-owner resources requiring explicit coordination. Camera access is brokered exclusively through `camera-stream.service`; other services MUST subscribe to feeds via IPC and NEVER open the device directly. Sensors, motor controllers, and communication buses require coordination mechanisms (locks, IPC queues, or dedicated daemons) to prevent concurrent access conflicts. Resource ownership must be clearly defined and enforced. Motor control commands MUST pass through safety interlock validation before hardware execution. Emergency stop (E-stop) signals override all other commands with <100ms latency requirement.

### V. Constitutional Hardware Compliance
Hardware configuration MUST align with `spec/hardware.yaml` requirements. INA3221 power monitoring uses fixed channel assignments: Channel 1 (Battery), Channel 2 (Unused), Channel 3 (Solar Input). GPS supports either ZED-F9P USB with NTRIP corrections OR Neo-8M UART (mutually exclusive). Motor control via RoboHAT RP2040→Cytron MDDRC10 (preferred) or L298N fallback. HAT stacking conflicts (RoboHAT + Hailo HAT) are prohibited without constitutional amendment.

### VI. Safety-First Engineering (NON-NEGOTIABLE)
Safety is the paramount concern in all system operations. Motion MUST only occur when hard and soft safety failsafes are operational and verified. Emergency stop (E-stop) MUST stop all motors within 100ms. IMU tilt detection MUST trigger blade cutoff within 200ms. System MUST default to OFF state on startup; motion requires explicit operator authorization. Watchdog timer enforcement is mandatory for all control loops. Safety interlocks MUST prevent blade operation when drive motors are active. All safety violations MUST be logged with timestamps and require operator acknowledgement for recovery. Software watchdog heartbeat MUST be enforced for all motor control operations with automatic emergency stop on timeout.

### VII. Modular Architecture
System architecture follows strict modular boundaries aligned with Engineering Plan phases. Core modules include: `drivers/` (hardware shims for motors, blade, IMU, ToF, environmental sensors, power, GPS), `safety/` (interlocks, triggers, watchdog, E-stop coordination), `fusion/` (sensor fusion and state estimation), `nav/` (geofencing, path planner, controller), `api/` (REST + WebSocket), `ui/` (retro-neon frontend), `scheduler/` (calendar, weather integration, charge management), and `tools/` (CLIs, analyzers, calibration utilities). Each module exposes defined contracts and MUST NOT bypass interfaces to access implementation internals. Drivers MUST be hardware-agnostic with clean adapter interfaces to enable simulation, testing, and future hardware substitution.

### VIII. Navigation & Geofencing (MANDATORY)
Autonomous navigation MUST respect geofence boundaries with zero tolerance for incursions. GPS localization with optional RTK corrections provides primary positioning; odometry provides secondary dead-reckoning between GPS updates. Geofence violations MUST trigger immediate motor stop and operator notification. Waypoint navigation follows parallel-line coverage patterns with configurable overlap. Navigation mode manager coordinates state transitions between MANUAL, AUTONOMOUS, EMERGENCY_STOP, CALIBRATION, and IDLE modes. Missing or degraded GPS MUST NOT compromise safety; system reverts to MANUAL mode with restricted operation. All navigation commands are subject to safety interlock validation before motor execution.

### IX. Scheduling & Autonomy
Autonomous mowing operations execute via calendar-based scheduling with weather-aware postponement logic. Jobs MUST NOT start during rain, high wind, or low battery conditions. Solar charge management integrates with scheduling to optimize energy availability. Mowing schedules respect user-defined operating windows and geofence boundaries. Job execution state machine tracks IDLE → SCHEDULED → RUNNING → PAUSED → COMPLETED → FAILED transitions with audit logging. Autonomous operations MUST verify all safety systems operational before commencing; any safety fault aborts the job and requires operator intervention. Return-to-home and return-to-solar-waypoint behaviors are mandatory for charge management and safe parking.

### X. Observability & Debuggability
System MUST maintain comprehensive structured logging (JSON format) with configurable log levels and rotating file management. All safety events, motor commands, navigation decisions, and operator interactions are logged with microsecond-precision timestamps. Real-time telemetry streaming via WebSocket provides live system state visibility at 5Hz minimum. Diagnostic CLI tools enable live sensor testing, motor calibration, and fault analysis without UI dependency. Fault injection capabilities support reliability testing and operator training. Log bundles aggregate system state, sensor data, and audit trails for incident analysis. Metrics exposure via `/metrics` endpoint (Prometheus format) is recommended for production deployments. Dashboard visualizations present key performance indicators including battery state, coverage progress, safety system status, and environmental conditions.

## Technology Stack Requirements

All system components must use approved technologies and interfaces: Picamera2 + GStreamer for camera handling, python-periphery + lgpio for GPIO control, pyserial for UART communication, and systemd for service management. Backend API uses FastAPI with asyncio for concurrent operations. Frontend implements Vue.js 3 with retro 1980s cyberpunk aesthetic (Orbitron fonts, neon color palette: #00ffff, #ff00ff, #ffff00). Real-time communication via WebSocket telemetry streaming at 5Hz minimum. No frameworks or libraries outside the approved stack without constitutional amendment and compelling technical justification. All dependencies MUST be ARM64-compatible; x86-only dependencies are BANNED.

## Development Workflow

Every code change MUST update `/docs` and `/spec` documentation with CI validation preventing drift. No TODOs are permitted unless formatted as `TODO(v3):` with linked GitHub issue for future version planning. All services operate as managed systemd units with automatic startup, monitoring, and graceful shutdown. Service coordination respects camera ownership and hardware resource management protocols. Development follows phased approach: Phase 0 (Foundation & Tooling) → Phase 1 (Core Abstractions) → Phase 2 (Safety & Motor Control) → Phase 3 (Sensors & Extended Safety) → Phase 4 (Navigation Core) → Phase 5 (Web UI & Remote Access) → Phase 6 (Scheduling & Autonomy) → Phase 7 (Reliability & Polish). Feature branches MUST NOT skip phases; dependencies must be satisfied before advancing.

AI agents MUST maintain an `AGENT_JOURNAL.md` file in the `.specify/memory/` folder, documenting progress, changes made, decisions taken, and any information necessary for seamless handoff to other agents or developers. The journal MUST include timestamps, rationale for major decisions, and current project state to ensure continuity across development sessions. Safety-critical changes (E-stop, motor control, blade interlocks, geofencing) require explicit constitutional compliance verification in commit messages.

After completing assigned tasks for a session, the responsible agent MUST execute the repository workflows defined in `.github/workflows/`. Upon successful completion of these workflows, the agent MUST commit any resulting changes (generated artifacts, updated docs/specs, version bumps) to the current working branch with a clear, conventional commit message referencing the workflows run. If workflows fail, the agent MUST document failures and remediation steps in `AGENT_JOURNAL.md` and refrain from committing broken artifacts.

Agent execution rules (MANDATORY):
- Apply code changes directly in the repository.
- If tests or linting are needed, run them in the terminal on Linux/ARM64 (Raspberry Pi OS Bookworm). Do NOT add Windows/macOS-only dependencies or instructions.
- If any dependency is not available on ARM64, STOP and propose a Pi-compatible alternative in `AGENT_JOURNAL.md` (and PR description, if applicable) before proceeding.
- When done, summarize the changes and update `.specify/memory/AGENT_JOURNAL.md` with outcomes, rationale, and next steps.
  
Workspace editing and local context (STRICT):
- Always edit files directly in the local workspace. Do NOT download or fetch files via remote content APIs/tools to modify them. Locate and open files from the checked-out repository tree.
- Prefer local codebase search (editor search, ripgrep) to discover files and symbols. Use repository-aware tools before any remote content fetchers. If a remote fetch is ever necessary, justify it in the journal.

Git operations (OPTIONS):
- You MAY use MCP GitHub tools for commits and PRs if available and part of the workflow.
- You MAY alternatively use the GitHub CLI (`gh`) for git operations when it is installed and authenticated in the workspace. Choose one method per session and document which was used in `AGENT_JOURNAL.md`.
- All PRs MUST use `.github/pull_request_template.md` and include a brief note confirming constitutional compliance.

- For teams using MCP GitHub tools, use `#mcp_github_add_comment_to_pending_review` to perform the push/commit step in accordance with the established review flow after successful workflow completion. If using GitHub CLI, use `gh pr create` with the repository template.

## Governance

This constitution supersedes all other development practices and requirements. Constitutional amendments require formal documentation, approval process, and migration plan for affected systems. All pull requests and code reviews MUST verify constitutional compliance before approval. Complexity deviations require explicit justification with simpler alternatives documented. Development teams MUST use `spec/agent_rules.md` for runtime development guidance and implementation constraints.

**Acceptance Criteria (Core Safety Requirements)**:
- Emergency stop latency: <100ms from signal to motor halt
- IMU tilt cutoff latency: <200ms from threshold breach to blade stop
- UI telemetry update rate: ≤1s (1Hz minimum, 5Hz target)
- Navigation geofence incursions: 0 tolerance (immediate stop)
- Graceful degradation: Missing GPS → Manual mode remains safe
- Watchdog timeout enforcement: Mandatory for all motor operations

**Version**: 2.0.0 | **Ratified**: 2025-09-25 | **Last Amended**: 2025-10-02

---

## Constitutional Change Log

### 2.0.0 (2025-10-02) - Major: Engineering Plan Alignment
**Added Principles**:
- Principle VI: Safety-First Engineering - Codifies E-stop latency, watchdog enforcement, safety interlock requirements
- Principle VII: Modular Architecture - Defines system decomposition aligned with Engineering Plan module map
- Principle VIII: Navigation & Geofencing - Establishes zero-tolerance geofence policy and GPS degradation behavior
- Principle IX: Scheduling & Autonomy - Mandates weather-aware job execution and charge management integration
- Principle X: Observability & Debuggability - Requires structured logging, telemetry streaming, and diagnostic tooling

**Enhanced Principles**:
- Principle III: Added hardware simulation mock driver requirements for CI testing
- Principle IV: Expanded with motor control safety interlock mandates and E-stop override priority

**Rationale**: Project analysis revealed gaps between Engineering Plan safety requirements (Phases 2-7) and constitutional governance. Safety-first mandate was implicit but not constitutionally enforced. Navigation, scheduling, and observability principles were absent despite significant implementation. This amendment brings constitutional authority in line with engineering requirements and current system capabilities.

### 1.4.0 (2025-09-26) - Minor: Agent Execution Rules
**Changes**: Clarified mandatory local workspace editing, added GitHub CLI option for git operations
**Rationale**: Standardize agent workspace interaction patterns

### 1.3.0 (2025-09-25) - Minor: Initial Ratification
**Changes**: Established foundational principles I-V
**Rationale**: Bootstrap constitutional governance for LawnBerry Pi project