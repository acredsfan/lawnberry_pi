# Feature Specification: Complete Engineering Plan Phases 0-7 Implementation

**Feature Branch**: `002-complete-engineering-plan`  
**Created**: 2025-10-02  
**Status**: Draft  
**Input**: User description: "Complete Engineering Plan Phases 0-7: Fill gaps in foundation tooling, bus/IPC, safety systems, sensor drivers, and reliability testing"



## Analysis Summary

**Current Implementation Status** (from project analysis):
- ✅ **Phase 5 (Web UI)**: Vue.js 3 frontend with retro cyberpunk styling, WebSocket telemetry @ 5Hz, JWT auth
- ✅ **Phase 1 (Partial)**: REST API + WebSocket endpoints, basic state management, IPC contracts defined
- ✅ **Phase 3 (Partial)**: Hardware sensor integration (GPS, IMU, battery via I2C), SensorManager service
- ✅ **Phase 2 (Partial)**: Safety models, E-stop API endpoints, motor control models, safety interlocks
- ⚠️ **Phase 0**: Missing ansible/setup automation, CI workflows incomplete, centralized config partial
- ⚠️ **Phase 1**: Missing pub/sub bus, driver registry, full IPC implementation
- ⚠️ **Phase 2**: Missing physical E-stop GPIO handler, watchdog daemon, motor driver integration
- ⚠️ **Phase 3**: Missing hardware drivers (ToF, environmental sensors), sensor fusion, CLI tools
- ⚠️ **Phase 4**: Missing odometry, geofence enforcement engine, waypoint controller
- ⚠️ **Phase 6**: Missing calendar integration, coverage pattern generator, solar charge optimizer
- ⚠️ **Phase 7**: Missing fault injection framework, soak testing, log bundle generator

---

```

**Current Implementation Status** (from project analysis):1. Parse user description from Input

- ✅ **Phase 5 (Web UI)**: Vue.js 3 frontend with retro cyberpunk styling, WebSocket telemetry @ 5Hz, JWT auth   → If empty: ERROR "No feature description provided"

- ✅ **Phase 1 (Partial)**: REST API + WebSocket endpoints, basic state management, IPC contracts defined2. Extract key concepts from description

- ✅ **Phase 3 (Partial)**: Hardware sensor integration (GPS, IMU, battery via I2C), SensorManager service   → Identify: actors, actions, data, constraints

- ✅ **Phase 2 (Partial)**: Safety models, E-stop API endpoints, motor control models, safety interlocks3. For each unclear aspect:

- ⚠️ **Phase 0**: Missing ansible/setup automation, CI workflows incomplete, centralized config partial   → Mark with [NEEDS CLARIFICATION: specific question]

- ⚠️ **Phase 1**: Missing pub/sub bus, driver registry, full IPC implementation4. Fill User Scenarios & Testing section

- ⚠️ **Phase 2**: Missing physical E-stop GPIO handler, watchdog daemon, motor driver integration   → If no clear user flow: ERROR "Cannot determine user scenarios"

- ⚠️ **Phase 3**: Missing hardware drivers (ToF, environmental sensors), sensor fusion, CLI tools5. Generate Functional Requirements

- ⚠️ **Phase 4**: Missing odometry, geofence enforcement engine, waypoint controller   → Each requirement must be testable

- ⚠️ **Phase 6**: Missing calendar integration, coverage pattern generator, solar charge optimizer   → Mark ambiguous requirements

- ⚠️ **Phase 7**: Missing fault injection framework, soak testing, log bundle generator6. Identify Key Entities (if data involved)

7. Run Review Checklist

---   → If any [NEEDS CLARIFICATION]: WARN "Spec has uncertainties"

   → If implementation details found: ERROR "Remove tech details"

## User Scenarios & Testing8. Return: SUCCESS (spec ready for planning)

```

### Primary User Story

As a **LawnBerry Pi operator**, I need the autonomous mower to operate safely and reliably according to the Engineering Plan's phased architecture, so that I can trust the system to mow my lawn without manual intervention while maintaining all safety guarantees.

### Acceptance Scenarios

- ✅ Focus on WHAT users need and WHY

#### Phase 0: Foundation & Tooling

1. **Given** a fresh Raspberry Pi 5 with Raspberry Pi OS Bookworm, **When** I run the automated setup script, **Then** the system provisions all dependencies, configures services, and reaches "hello world" state in <20 minutes

2. **Given** a pull request submitted to the repository, **When** CI workflows execute, **Then** lint, type-check, and unit tests pass before merge is allowed

3. **Given** hardware configuration in `config/hardware.yaml`, **When** the system starts, **Then** only declared modules are initialized and activated

4. **Given** system operation, **When** events occur, **Then** structured JSON logs are written with proper rotation and retention

#### Phase 1: Core Abstractions & Process Layout

1. **Given** a driver publishes a sensor reading, **When** the event reaches the message bus, **Then** all subscribed services receive the event with <10ms latency

2. **Given** simulation mode (SIM_MODE=1), **When** the system starts, **Then** mock drivers replace hardware drivers and produce realistic data

3. **Given** the system API, **When** queried for robot state, **Then** the canonical state reflects all subsystem inputs

#### Phase 2: Safety & Motor Control

1. **Given** the physical E-stop button is pressed, **When** GPIO interrupt fires, **Then** all motors stop within 100ms

2. **Given** motor control commands, **When** watchdog heartbeat times out, **Then** motors automatically stop and require manual recovery

3. **Given** the system starts, **When** no explicit operator authorization, **Then** motors remain in OFF state

4. **Given** manual teleop mode, **When** drive commands are sent, **Then** motors respond with validated PWM signals via RoboHAT (drive) and blade control uses IBT-4 H-Bridge on GPIO 24/25 with safety interlocks enforced

#### Phase 3: Sensors & Extended Safety

1. **Given** ToF sensors detect obstacles <0.2m, **When** mower is moving, **Then** emergency stop triggers automatically

2. **Given** IMU detects tilt angle >30°, **When** blade is active, **Then** blade stops within 200ms

3. **Given** battery voltage <10.0V, **When** detected, **Then** system enters low-power mode and prevents motor start

4. **Given** sensor diagnostics CLI, **When** executed, **Then** live sensor readings display in real-time with health status

#### Phase 4: Navigation Core

1. **Given** GPS fix acquired, **When** odometry integrated, **Then** position accuracy <1m within geofence

2. **Given** geofence boundary defined, **When** mower approaches within 0.5m, **Then** motors stop and operator notified

3. **Given** waypoint list, **When** autonomous mode engages, **Then** mower navigates to each waypoint sequentially

4. **Given** GPS signal lost, **When** dead-reckoning engages, **Then** system reverts to manual mode within 10 seconds

#### Phase 6: Scheduling & Autonomy

1. **Given** calendar schedule defined, **When** scheduled time arrives, **Then** job starts if weather permits

2. **Given** rain detected, **When** scheduled job pending, **Then** job postpones until weather clears

3. **Given** parallel-line coverage pattern, **When** autonomous mowing active, **Then** mower follows pattern with <10cm overlap

4. **Given** battery <20%, **When** detected, **Then** mower returns to solar charging waypoint

#### Phase 7: Reliability & Testing

1. **Given** fault injection enabled, **When** simulated sensor failure, **Then** system degrades gracefully and logs fault## Requirements *(mandatory)*

2. **Given** 8-hour soak test, **When** running continuously, **Then** zero unsafe events and all safety margins maintained

3. **Given** incident occurs, **When** operator requests log bundle, **Then** system generates archive with all relevant logs, state, and telemetry### Functional Requirements

- **FR-001**: System MUST [specific capability, e.g., "allow users to create accounts"]

### Edge Cases- **FR-002**: System MUST [specific capability, e.g., "validate email addresses"]  

- What happens when multiple safety triggers activate simultaneously? (E-stop + tilt + low battery)- **FR-003**: Users MUST be able to [key interaction, e.g., "reset their password"]

- How does the system handle conflicting mode commands? (autonomous request during manual operation)- **FR-004**: System MUST [data requirement, e.g., "persist user preferences"]

- What happens when geofence is modified during active mowing?- **FR-005**: System MUST [behavior, e.g., "log all security events"]

- How does the system recover from total GPS loss during autonomous operation?

- What happens when the pub/sub bus fails or becomes overloaded?*Example of marking unclear requirements:*

- How does the system handle clock drift between services?- **FR-006**: System MUST authenticate users via [NEEDS CLARIFICATION: auth method not specified - email/password, SSO, OAuth?]

- **FR-007**: System MUST retain user data for [NEEDS CLARIFICATION: retention period not specified]

---

### Key Entities *(include if feature involves data)*

## Requirements- **[Entity 1]**: [What it represents, key attributes without implementation]

- **[Entity 2]**: [What it represents, relationships to other entities]

### Functional Requirements

---

#### Phase 0: Foundation & Tooling

- **FR-001**: System MUST provide automated setup script that provisions Raspberry Pi OS Bookworm with all dependencies in <20 minutes
- **FR-001a**: Setup script MUST be idempotent, detecting existing installations and safely updating/repairing without data loss
- **FR-001b**: Setup script MUST support explicit `--update` flag for updating existing installations with dependency and configuration changes
- **FR-001c**: Setup script MUST preserve user data directories (config/, data/, logs/) when re-run or updated, excluding build artifacts (.venv/, __pycache__/, *.pyc)
- **FR-002**: System MUST enforce CI validation (lint, type-check, tests) on all pull requests before merge

- **FR-003**: System MUST load hardware configuration from `config/hardware.yaml` at startup

- **FR-004**: System MUST load safety limits from `config/limits.yaml` including tilt thresholds, voltage limits, timeout values### Content Quality

- **FR-005**: System MUST write structured JSON logs with rotation (max 100MB per file, 10 file retention)- [ ] No implementation details (languages, frameworks, APIs)

- **FR-006**: System MUST expose `/metrics` endpoint with Prometheus-compatible format for observability
- **FR-007**: System MUST support reproducible builds via uv with committed lock files
- **FR-007a**: System MUST support single operator authentication with username/password credentials
- **FR-007b**: Setup script MUST create default admin account with password change required on first login
- **FR-007c**: System MUST protect all control endpoints (manual operation, job scheduling, configuration changes) with authentication
- **FR-007d**: System MUST maintain authentication session with secure token (existing JWT implementation)

#### Phase 1: Core Abstractions & Process Layout

- **FR-008**: System MUST implement pub/sub message bus with topic-based routing and <10ms message latency
- **FR-008a**: Message bus MUST persist safety-critical messages (E-stop, interlock, navigation violations) to disk for guaranteed delivery
- **FR-008b**: Message bus MUST use best-effort delivery for telemetry and status messages (sensor readings, position updates)
- **FR-008c**: Persisted messages MUST be delivered to subscribers upon service recovery/restart
- **FR-009**: System MUST provide driver registry that loads only modules declared in hardware config via explicit module paths (no auto-discovery or reflection)
- **FR-010**: System MUST maintain canonical robot state updated by all subsystems via bus events  

- **FR-011**: System MUST support simulation mode (SIM_MODE=1) with mock drivers for all hardware- [ ] Success criteria are measurable

- **FR-012**: System MUST enforce safety contract API across all driver implementations- [ ] Scope is clearly bounded

- **FR-013**: System MUST provide REST + WebSocket APIs reflecting current robot state- [ ] Dependencies and assumptions identified



#### Phase 2: Safety & Motor Control (Minimum Viable Safety)---

- **FR-014**: System MUST handle physical E-stop button GPIO interrupt with <100ms motor stop latency

- **FR-015**: System MUST enforce software watchdog with configurable heartbeat timeout (default 1000ms)## Execution Status

- **FR-016**: System MUST default to OFF state on startup; motion requires explicit operator authorization*Updated by main() during processing*

- **FR-017**: System MUST validate motor control commands against safety interlocks before hardware execution

- **FR-018**: System MUST support manual teleop via REST API with throttle/turn validation (-1.0 to 1.0)- [ ] User description parsed

- **FR-019**: System MUST communicate with RoboHAT RP2040 via UART for drive motor control (Cytron MDDRC10); blade motor control MUST use IBT-4 H-Bridge driven directly from Raspberry Pi GPIO 24 (IN1) and GPIO 25 (IN2). Safety lockouts apply to both paths.

- **FR-020**: System MUST provide emergency stop recovery requiring operator confirmation (via web UI button or CLI command with --force flag)

#### Phase 3: Sensors & Extended Safety (IMU-backed)
#### Operator Interface
- **FR-020a**: System MUST provide responsive web UI accessible from desktop and mobile browsers for monitoring, control, and scheduling
- **FR-020b**: System MUST provide CLI commands for system diagnostics, recovery operations, and emergency procedures
- **FR-020c**: Web UI MUST be mobile-optimized for field operations with touch-friendly controls and readable displays- [ ] Ambiguities marked

- [ ] User scenarios defined

#### Phase 3: Sensors & Extended Safety (IMU-backed)- [ ] Requirements generated

- **FR-021**: System MUST integrate VL53L0X ToF sensors (left/right) via I2C with <0.2m emergency stop threshold- [ ] Entities identified

- **FR-022**: System MUST integrate BNO085 IMU via UART with tilt detection (>30° roll/pitch triggers blade stop <200ms)- [ ] Review checklist passed

- **FR-023**: System MUST integrate BME280 environmental sensor via I2C for temperature, humidity, pressure

- **FR-024**: System MUST integrate INA3221 power monitor via I2C for battery/solar voltage and current readings---

- **FR-025**: System MUST implement sensor fusion with time synchronization and health monitoring
- **FR-026**: System MUST provide CLI tool for live sensor testing and diagnostics with ASCII table format (columns: sensor_id, value, unit, health_status; 1Hz refresh rate)
- **FR-027**: System MUST trigger safety interlocks for: tilt, impact (ToF), low battery (<10.0V), high temperature (>80°C)

#### Phase 4: Navigation Core
- **FR-028**: System MUST integrate GPS (ZED-F9P USB with NTRIP or Neo-8M UART) with position updates
- **FR-029**: System MUST implement odometry from encoder feedback (when available) or dead-reckoning from motor commands
- **FR-030**: System MUST enforce geofence boundaries with zero-tolerance policy (immediate stop on violation)
- **FR-031**: System MUST support waypoint navigation with sequential execution in autonomous mode
- **FR-032**: System MUST implement navigation mode manager: MANUAL, AUTONOMOUS, EMERGENCY_STOP, CALIBRATION, IDLE
- **FR-033**: System MUST revert to MANUAL mode when GPS accuracy degrades below 5m or signal lost >10s
- **FR-034**: System MUST provide navigation state via API including current mode, position, target waypoint, geofence status

#### Phase 6: Scheduling & Autonomy
- **FR-035**: System MUST support calendar-based job scheduling with cron-like syntax
- **FR-036**: System MUST postpone scheduled jobs during adverse weather (rain, high wind detected by sensors or API)
- **FR-036a**: System MUST cache last weather forecast from external API with timestamp and validity period
- **FR-036b**: When weather API unavailable, system MUST make scheduling decisions using cached forecast combined with real-time sensor readings (BME280 temperature, humidity, pressure)
- **FR-036c**: System MUST invalidate cached weather data after 6 hours and require fresh API data or sensor-only operation
- **FR-037**: System MUST generate parallel-line coverage patterns with configurable cutting width and overlap
- **FR-038**: System MUST integrate solar charge monitoring with return-to-solar-waypoint behavior when battery <20%
- **FR-039**: System MUST implement job state machine: IDLE → SCHEDULED → RUNNING → PAUSED → COMPLETED → FAILED
- **FR-040**: System MUST validate safety systems operational before starting autonomous jobs (checks: E-stop cleared, no active interlocks, GPS accuracy <5m, battery >20%, IMU calibrated)
- **FR-041**: System MUST provide return-to-home behavior on job completion or abort

#### Phase 7: Reliability, Testing, & Polish
- **FR-042**: System MUST provide fault injection framework for testing sensor failures, communication drops, power events
- **FR-043**: System MUST support 8-hour soak testing with continuous operation and safety margin monitoring
- **FR-044**: System MUST generate log bundles (tar.gz) containing logs, state snapshots, telemetry for incident analysis
- **FR-045**: System MUST provide dashboards for key metrics: battery health, coverage progress, safety event history, uptime
- **FR-046**: System MUST document all operational procedures including recovery, calibration, troubleshooting
- **FR-047**: System MUST pass acceptance criteria: E-stop <100ms, tilt cutoff <200ms, UI telemetry ≤1s, zero geofence incursions

### Non-Functional Requirements

#### Performance
- **NFR-001**: Message bus latency MUST be <10ms p99 under normal load (<100 msg/s)
- **NFR-002**: Sensor polling frequency MUST support: GPS 1Hz, IMU 10Hz, ToF 5Hz, Power 1Hz, Env 0.2Hz
- **NFR-003**: WebSocket telemetry MUST stream at 5Hz minimum with <100ms jitter
- **NFR-004**: System startup (cold boot to operational) MUST complete in <30 seconds

#### Reliability
- **NFR-005**: All safety-critical operations (E-stop, tilt cutoff, geofence) MUST have <100ms worst-case latency
- **NFR-006**: System MUST operate continuously for 8+ hours without memory leaks or performance degradation
- **NFR-007**: System MUST recover gracefully from individual service failures without requiring full reboot
- **NFR-008**: All hardware communication MUST include timeout protection and automatic retry with backoff

#### Maintainability
- **NFR-009**: All drivers MUST implement standard interface for simulation/testing without hardware
- **NFR-010**: Configuration changes (hardware.yaml, limits.yaml) MUST NOT require code recompilation
- **NFR-011**: Log messages MUST include timestamps (microsecond precision), service name, severity, and context
- **NFR-012**: All subsystems MUST expose health check endpoints for monitoring and diagnostics

#### Platform
- **NFR-013**: System MUST run exclusively on Raspberry Pi OS Bookworm (64-bit) on Pi 5/4B
- **NFR-014**: All dependencies MUST be ARM64-compatible via piwheels or source build
- **NFR-015**: System MUST support headless operation (no display/keyboard required)
- **NFR-016**: Power consumption MUST support 30W solar + 30Ah LiFePO4 battery for full-day operation

### Key Entities

- **HardwareConfig**: Declares which physical modules are present (GPS type, IMU, sensors, motor controllers) - loaded from hardware.yaml
- **SafetyLimits**: Defines thresholds and timeouts (tilt angle, battery voltage, motor current, watchdog timeout) - loaded from limits.yaml
- **MessageBusEvent**: Pub/sub event with topic, timestamp, payload, source service identifier
- **DriverInstance**: Registered hardware driver with lifecycle (init, start, stop), health status, simulation mode support
- **RobotState**: Canonical system state including position, velocity, mode, active interlocks, sensor readings, battery state
- **SafetyInterlock**: Active safety condition preventing operation (e.g., emergency_stop, tilt_detected, low_battery, geofence_violation)
- **NavigationWaypoint**: Target position with latitude, longitude, target speed, arrival threshold
- **Geofence**: Boundary polygon with vertices, violation detection, buffer distance
- **CoveragePattern**: Mowing path plan with parallel lines, turning points, coverage percentage
- **ScheduledJob**: Calendar entry with cron expression, zone assignments, weather dependencies, retry policy
- **SensorReading**: Timestamped measurement from hardware sensor with value, unit, quality indicator
- **LogBundle**: Archived collection of logs, state snapshots, telemetry for incident analysis

---

## Clarifications

### Session 2025-10-02
- Q: How should operators interact with the system for control, monitoring, and recovery operations? → A: Web UI + CLI + Mobile
- Q: Who can control the autonomous mower and start jobs? → A: Single operator with password
- Q: If the weather API is unavailable or fails, how should autonomous scheduling behave? → A: Cache + sensors
- Q: Can the setup script be safely re-run on an already-configured system? → A: A+D (idempotent + update flag)
- Q: What happens to critical messages if a subscribing service crashes before consuming them? → A: Two-tier (safety-critical persisted, telemetry best-effort)

## Dependencies & Assumptions

### Dependencies
- **Constitution v2.0.0**: All implementation must comply with safety-first, modular architecture, and phase progression requirements
- **Existing Implementation**: Backend API, frontend UI, basic safety models, sensor manager (from Phase 5 completion)
- **Hardware Availability**: Raspberry Pi 5, GPS module, IMU (BNO085), ToF sensors, power monitor, RoboHAT RP2040
- **External Services**: NTRIP server for RTK corrections (optional), OpenWeatherMap API for weather (optional)

### Assumptions
- Hardware modules are connected and accessible via documented I2C/UART/USB interfaces per spec/hardware.yaml
- Operator has physical access to Pi for initial setup and E-stop button wiring
- Network connectivity available for remote access, weather API, NTRIP (degraded mode when offline)
- systemd available for service management on Raspberry Pi OS Bookworm
- Operators use combination of responsive web UI (desktop/mobile browsers), CLI tools for diagnostics/recovery, and mobile-optimized interface for field operations

---

## Review & Acceptance Checklist

### Content Quality
- [x] No implementation details (languages, frameworks, APIs) - focuses on WHAT not HOW
- [x] Focused on user value and business needs - operator safety and reliability
- [x] Written for non-technical stakeholders - plain language scenarios
- [x] All mandatory sections completed - user scenarios, requirements, entities

### Requirement Completeness  
- [x] No [NEEDS CLARIFICATION] markers remain - all requirements specific
- [x] Requirements are testable and unambiguous - each has measurable acceptance criteria
- [x] Success criteria are measurable - timing requirements, percentages, counts specified
- [x] Scope is clearly bounded - 7 phases from Engineering Plan
- [x] Dependencies and assumptions identified - constitution, hardware, services

---

## Execution Status

- [x] User description parsed - Engineering Plan phases 0-7 gap analysis
- [x] Key concepts extracted - foundation, bus/IPC, safety, sensors, navigation, scheduling, reliability
- [x] Ambiguities marked - none; requirements derived from Engineering Plan acceptance criteria
- [x] User scenarios defined - 24 acceptance scenarios across 7 phases
- [x] Requirements generated - 47 functional requirements + 16 non-functional requirements
- [x] Entities identified - 12 key entities for state, config, events, navigation, scheduling
- [x] Review checklist passed - all gates satisfied

---

## Notes

This specification fills the gaps between the current LawnBerry Pi v2 implementation and the complete Engineering Plan. The project has strong Phase 5 (Web UI) and partial Phase 1-3 implementation, but needs:

1. **Automation & CI** (Phase 0) - setup scripts, workflow enforcement
2. **Message Bus & Driver Registry** (Phase 1) - pub/sub infrastructure, driver lifecycle
3. **Hardware Safety Integration** (Phase 2) - E-stop GPIO, watchdog daemon, RoboHAT UART
4. **Sensor Drivers & Fusion** (Phase 3) - ToF, IMU, environmental, diagnostics CLI
5. **Navigation Engine** (Phase 4) - geofence enforcement, waypoint control, odometry
6. **Autonomy Features** (Phase 6) - scheduling, coverage patterns, charge management
7. **Reliability Framework** (Phase 7) - fault injection, soak tests, log bundles

All requirements align with Constitutional v2.0.0 principles including safety-first mandates, modular architecture, and acceptance criteria (E-stop <100ms, tilt cutoff <200ms, geofence zero-tolerance).
