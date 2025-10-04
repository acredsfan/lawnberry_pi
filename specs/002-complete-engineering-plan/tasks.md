# Tasks: Complete Engineering Plan Phases 0-7 Implementation

**Input**: Design documents from `/home/pi/lawnberry/specs/002-complete-engineering-plan/`
**Prerequisites**: plan.md, research.md, data-model.md, contracts/api-contract.md, quickstart.md

## Execution Flow (main)
```
✅ Loaded plan.md: Python 3.11 + FastAPI backend, existing Vue.js 3 frontend
✅ Loaded data-model.md: 12 entities identified
✅ Loaded contracts/api-contract.md: REST + WebSocket APIs across 7 phases
✅ Loaded research.md: 10 technology decisions finalized
✅ Task generation: TDD order (tests first), grouped by Engineering Plan phases
✅ Parallelization: 42 tasks marked [P] (independent files, no dependencies)
✅ Validation: All contracts have tests, all entities have models, constitutional compliance verified
```

**IMPORTANT - Constitutional Requirement**: Throughout task execution, continuously update `.specify/memory/AGENT_JOURNAL.md` with progress, decisions, and blockers. This is NOT a single-task deliverable (T093) but an ongoing documentation requirement per Constitution Development Workflow. Update journal after completing each phase or when making significant architectural decisions.

## Path Conventions
**Project Structure**: Web application (Option 2)
- Backend: `/home/pi/lawnberry/backend/src/` and `/home/pi/lawnberry/backend/tests/`
- Frontend: `/home/pi/lawnberry/frontend/src/` (already complete from Phase 5)
- Config: `/home/pi/lawnberry/config/`
- Scripts: `/home/pi/lawnberry/scripts/`
- Docs: `/home/pi/lawnberry/docs/`

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Exact file paths included in task descriptions
- Constitutional compliance notes where applicable

---

## Phase 0: Foundation & Tooling (FR-001 to FR-007)

### Setup & Infrastructure

- [x] **T001** [P] Create setup automation script at `scripts/setup.sh` with idempotent installation, --update flag support, <20 minute target (FR-001, FR-001a, FR-001b, FR-001c)
  - **Acceptance**: Script detects existing installation, preserves data (config/, data/, logs/ directories) (config/, data/, logs/ directories), completes in <20 minutes, validates headless operation (NFR-015)
  - **Constitutional**: Principle I (Platform Exclusivity) - Pi OS Bookworm only, ARM64 dependencies

- [x] **T001.5** [P] Create example configuration files at `config/hardware.yaml` and `config/limits.yaml` with documentation (FR-003, FR-004)
  - **Acceptance**: Example configs include all required fields with inline comments, validation examples, default values aligned with SafetyLimits model
  - **Constitutional**: Principle V (Hardware Compliance) - Document INA3221 channel assignments, GPS type options

- [x] **T002** [P] Create GitHub Actions CI workflow at `.github/workflows/ci.yml` for lint, type-check, unit tests, contract tests (FR-002)
  - **Acceptance**: PR validation blocks merge on test failures
  - **Constitutional**: Principle III (Test-First Development) - CI enforces TDD

- [x] **T003** [P] Create config loader service at `backend/src/core/config_loader.py` to parse `config/hardware.yaml` and `config/limits.yaml` with Pydantic validation (FR-003, FR-004)
  - **Acceptance**: Loads at startup, validates against HardwareConfig and SafetyLimits schemas
  - **Dependencies**: Requires T012 (HardwareConfig model) and T013 (SafetyLimits model)

- [x] **T004** [P] Implement structured JSON logging with rotation at `backend/src/core/logger.py` (max 100MB per file, 10 file retention) (FR-005)
  - **Acceptance**: Logs include timestamps (microsecond precision), service name, severity, context
  - **Constitutional**: Principle X (Observability) - Structured logging mandatory

- [x] **T005** [P] Create Prometheus metrics endpoint at `backend/src/api/metrics.py` exposing `/metrics` (FR-006)
  - **Acceptance**: Prometheus-compatible format, includes message bus latency, safety events, driver health
  - **Constitutional**: Principle X (Observability) - Metrics exposure recommended

- [x] **T006** [P] Configure uv package manager with `pyproject.toml` and committed lock file `uv.lock` for reproducible builds (FR-007)
  - **Acceptance**: `uv sync` installs exact versions, ARM64-compatible via piwheels
  - **Constitutional**: Principle II (Package Isolation) - uv lock files mandatory

- [x] **T007** [P] Create authentication models and service at `backend/src/auth/` with single operator password-based login, JWT session tokens (FR-007a, FR-007b, FR-007c, FR-007d)
  - **Acceptance**: Default admin account created on setup, password change required on first login, JWT tokens secure control endpoints
  - **Dependencies**: Requires T003 (config loader)

---

## Phase 1: Core Abstractions & Process Layout (FR-008 to FR-013)

### Contract Tests (TDD Phase - MUST COMPLETE BEFORE IMPLEMENTATION)

- [x] **T008** [P] Contract test for message bus publish/subscribe at `backend/tests/contract/test_message_bus.py`
  - **Test**: Publish event, verify subscriber receives within <10ms (FR-008)
  - **Must Fail**: No message bus implementation exists yet
  - **Constitutional**: Principle III (Test-First Development)

- [x] **T009** [P] Contract test for message persistence at `backend/tests/contract/test_message_persistence.py`
  - **Test**: Publish critical message, simulate service crash, verify delivery on recovery (FR-008a, FR-008b, FR-008c)
  - **Must Fail**: No persistence implementation exists yet

- [x] **T010** [P] Contract test for driver registry at `backend/tests/contract/test_driver_registry.py`
  - **Test**: Load drivers from hardware.yaml, verify only declared modules initialized (FR-009)
  - **Must Fail**: No driver registry exists yet

- [x] **T011** [P] Contract test for simulation mode at `backend/tests/contract/test_simulation_mode.py`
  - **Test**: Set SIM_MODE=1, verify mock drivers loaded instead of real hardware (FR-011)
  - **Must Fail**: No simulation mode implementation exists yet

- [x] **T011.5** [P] Contract test for health check endpoints at `backend/tests/contract/test_health_endpoints.py`
  - **Test**: GET /health, verify all subsystems report status (NFR-012)
  - **Must Fail**: No health check endpoints exist yet
  - **Constitutional**: Principle X (Observability) - Health checks mandatory

### Data Models

- [x] **T012** [P] Create HardwareConfig Pydantic model at `backend/src/models/hardware_config.py`
  - **Fields**: gps_type, gps_ntrip_enabled, imu_type, tof_sensors, env_sensor, power_monitor, motor_controller, blade_controller, camera_enabled
  - **Validation**: GPS type mutually exclusive, NTRIP requires ZED-F9P
  - **Source**: data-model.md section 1

- [x] **T013** [P] Create SafetyLimits Pydantic model at `backend/src/models/safety_limits.py`
  - **Fields**: estop_latency_ms, tilt_threshold_degrees, tilt_cutoff_latency_ms, battery_low_voltage, battery_critical_voltage, motor_current_max_amps, watchdog_timeout_ms, geofence_buffer_meters, high_temperature_celsius, tof_obstacle_distance_meters
  - **Validation**: estop_latency_ms ≤ 100, tilt_cutoff_latency_ms ≤ 200 (constitutional)
  - **Source**: data-model.md section 2

- [x] **T014** [P] Create MessageBusEvent Pydantic model at `backend/src/models/message_bus_event.py`
  - **Fields**: topic, timestamp_us, payload, source_service, message_id, persistence_tier
  - **Validation**: Topic follows hierarchical pattern, critical topics validated
  - **Source**: data-model.md section 3

- [x] **T015** [P] Create DriverInstance Pydantic model at `backend/src/models/driver_instance.py`
  - **Fields**: driver_id, driver_class, hardware_resource, simulation_mode, lifecycle_state, health_status, last_health_check_ts, error_message
  - **State Transitions**: uninitialized → initializing → ready → running → stopped/failed
  - **Source**: data-model.md section 4

- [x] **T016** [P] Create RobotState Pydantic model at `backend/src/models/robot_state.py`
  - **Fields**: position (lat/lon/accuracy), heading, velocity, angular_velocity, orientation (roll/pitch/yaw), navigation_mode, active_interlocks, battery state, sensor readings
  - **Source**: data-model.md section 5
  - **Dependencies**: Requires T017 (SafetyInterlock model)

- [x] **T017** [P] Create SafetyInterlock Pydantic model at `backend/src/models/safety_interlock.py`
  - **Fields**: interlock_id, type (emergency_stop, tilt_detected, low_battery, geofence_violation, obstacle_detected, watchdog_timeout), severity, triggered_at_ts, cleared_at_ts, requires_operator_ack
  - **Source**: data-model.md section 6

### Core Implementation (ONLY after contract tests failing)

- [x] **T018** Implement asyncio message bus at `backend/src/core/message_bus.py` with pub/sub, <10ms p99 latency (FR-008)
  - **Acceptance**: T008 contract test passes, latency <10ms measured
  - **Dependencies**: Requires T014 (MessageBusEvent model)
  - **Research**: research.md section 1 (asyncio pub/sub decision)

- [x] **T019** Implement two-tier message persistence at `backend/src/core/message_persistence.py` using SQLite WAL for critical messages (FR-008a, FR-008b, FR-008c)
  - **Acceptance**: T009 contract test passes, critical messages survive service restart
  - **Dependencies**: Requires T018 (message bus core)
  - **Research**: research.md section 1 (persistence strategy)

- [x] **T020** Implement driver registry at `backend/src/core/driver_registry.py` with plugin-based loading from hardware.yaml (FR-009)
  - **Acceptance**: T010 contract test passes, only declared drivers loaded
  - **Dependencies**: Requires T012 (HardwareConfig), T015 (DriverInstance)
  - **Research**: research.md section 2 (driver registry pattern)

- [x] **T021** Implement HardwareDriver ABC at `backend/src/drivers/base.py` with lifecycle methods (init, start, stop, health_check)
  - **Acceptance**: Defines async interface for all drivers
  - **Dependencies**: Requires T015 (DriverInstance model)
  - **Constitutional**: Principle VII (Modular Architecture) - Clean driver interfaces

- [x] **T021.5** [P] Document safety contract API at `contracts/safety-contract.md` with interface requirements (FR-012)
  - **Acceptance**: Specifies emergency stop interface, interlock validation interface, watchdog heartbeat protocol
  - **Dependencies**: None (documentation)
  - **Constitutional**: Principle VI (Safety-First) - Safety contracts must be explicit

- [x] **T022** Implement simulation mode support at `backend/src/core/simulation.py` for SIM_MODE=1 environment variable (FR-011)
  - **Acceptance**: T011 contract test passes, mock drivers loaded when SIM_MODE=1
  - **Dependencies**: Requires T020 (driver registry), T021 (HardwareDriver ABC)
  - **Research**: research.md section 2 (simulation support)

- [x] **T023** Implement canonical robot state service at `backend/src/core/robot_state_manager.py` aggregating subsystem inputs (FR-010)
  - **Acceptance**: State updated via message bus events, exposed via API
  - **Dependencies**: Requires T016 (RobotState model), T018 (message bus)

- [x] **T024** Implement REST + WebSocket APIs at `backend/src/api/status.py` exposing robot state (FR-013)
  - **Acceptance**: GET /status returns current state, WebSocket streams updates at 5Hz
  - **Dependencies**: Requires T023 (robot state manager)
  - **Constitutional**: Principle X (Observability) - Real-time telemetry 5Hz

---

## Phase 2: Safety & Motor Control (FR-014 to FR-020c)

### Contract Tests (TDD Phase)

- [x] **T025** [P] Contract test for E-stop GPIO at `backend/tests/contract/test_estop_gpio.py`
  - **Test**: Trigger GPIO interrupt, verify motors stop within 100ms (FR-014)
  - **Must Fail**: No E-stop handler exists yet
  - **Constitutional**: Principle VI (Safety-First) - E-stop <100ms mandatory

- [x] **T026** [P] Contract test for watchdog timeout at `backend/tests/contract/test_watchdog.py`
  - **Test**: Stop heartbeat, verify emergency stop after timeout (FR-015)
  - **Must Fail**: No watchdog implementation exists yet
  - **Constitutional**: Principle VI (Safety-First) - Watchdog enforcement mandatory

- [x] **T027** [P] Contract test for default OFF state at `backend/tests/contract/test_motor_default_state.py`
  - **Test**: System startup, verify motors OFF without authorization (FR-016)
  - **Must Fail**: No motor controller exists yet

- [x] **T028** [P] Contract test for safety interlocks at `backend/tests/contract/test_safety_interlocks.py`
  - **Test**: Attempt motor operation with active interlock, verify rejection (FR-017)
  - **Must Fail**: No interlock validation exists yet

- [x] **T029** [P] Contract test for manual teleop at `backend/tests/contract/test_manual_teleop.py`
  - **Test**: POST /motors/drive with throttle/turn, verify PWM calculation (FR-018)
  - **Must Fail**: No teleop endpoint exists yet

### Core Implementation

- [x] **T030** Implement E-stop GPIO handler at `backend/src/safety/estop_handler.py` using lgpio with asyncio integration (FR-014)
  - **Acceptance**: T025 contract test passes, <100ms latency validated
  - **Dependencies**: Requires T018 (message bus for emergency events)
  - **Research**: research.md section 3 (lgpio edge detection)
  - **Constitutional**: Principle VI (Safety-First) - <100ms non-negotiable

- [x] **T031** Implement software watchdog at `backend/src/safety/watchdog.py` with asyncio task-based monitoring (FR-015)
  - **Acceptance**: T026 contract test passes, configurable timeout from SafetyLimits
  - **Dependencies**: Requires T013 (SafetyLimits model), T030 (E-stop handler)
  - **Research**: research.md section 4 (asyncio watchdog)
  - **Constitutional**: Principle VI (Safety-First) - Watchdog mandatory

- [x] **T032** Implement RoboHAT RP2040 drive motor controller driver at `backend/src/drivers/motor/robohat_rp2040.py` via UART (FR-019)
  - **Acceptance**: Sends PWM commands via pyserial to Cytron MDDRC10 bridge, receives acknowledgments
  - **Dependencies**: Requires T021 (HardwareDriver ABC)
  - **Research**: research.md section 3 (UART motor control)
  - **Constitutional**: Principle V (Hardware Compliance) - RoboHAT primary controller for drive

- [x] **T032a** Implement IBT-4 blade controller at `backend/src/drivers/blade/ibt4_gpio.py` using GPIO 24 (IN1) and GPIO 25 (IN2) with safety interlocks (FR-019)
  - **Acceptance**: Toggles blade on/off and direction safely using Pi GPIO; respects E-stop, tilt, and lockouts; latency within limits
  - **Dependencies**: Requires T021 (HardwareDriver ABC), T033 (interlock validator)
  - **Research**: hardware-overview.md; lgpio vs python-periphery tradeoffs
  - **Constitutional**: Principle VI (Safety-First) - Blade lockouts enforced; Principle V (Hardware Compliance)

- [x] **T033** Implement safety interlock validator at `backend/src/safety/interlock_validator.py` (FR-017)
  - **Acceptance**: T028 contract test passes, blocks motor commands when interlocks active
  - **Dependencies**: Requires T017 (SafetyInterlock model), T023 (robot state)
  - **Constitutional**: Principle VI (Safety-First) - Interlocks block unsafe operations

- [x] **T034** Implement motor authorization service at `backend/src/safety/motor_authorization.py` with OFF default (FR-016)
  - **Acceptance**: T027 contract test passes, requires explicit operator authorization
  - **Dependencies**: Requires T033 (interlock validator)
  - **Constitutional**: Principle VI (Safety-First) - OFF default state mandatory

- [x] **T035** Implement manual teleop API at `backend/src/api/motors.py` with POST /motors/drive endpoint (FR-018)
  - **Acceptance**: T029 contract test passes, throttle/turn validation (-1.0 to 1.0)
  - **Dependencies**: Requires T032 (motor controller), T034 (motor authorization)

- [x] **T036** Implement E-stop recovery workflow at `backend/src/api/safety.py` with operator confirmation (FR-020, FR-020a, FR-020b, FR-020c)
  - **Acceptance**: Web UI button or CLI command with --force flag clears E-stop
  - **Dependencies**: Requires T030 (E-stop handler)

### Operator Interface Tasks

- [x] **T037** [P] Create CLI safety commands at `backend/src/cli/safety_commands.py` for E-stop recovery and diagnostics (FR-020b)
  - **Acceptance**: Commands like `lawnberry safety clear-estop --force`, `lawnberry safety status`
  - **Dependencies**: Requires T036 (E-stop recovery)

---

## Phase 3: Sensors & Extended Safety (FR-021 to FR-027)


### Contract Tests (TDD Phase)

- [x] **T038** [P] Contract test for ToF sensors at `backend/tests/contract/test_tof_sensors.py`
  - **Test**: Read left/right ToF distance, verify <0.2m triggers emergency stop (FR-021), test timeout/retry behavior (NFR-008)
  - **Must Fail**: No ToF drivers exist yet

- [x] **T039** [P] Contract test for IMU tilt detection at `backend/tests/contract/test_imu_tilt.py`
  - **Test**: Inject tilt >30°, verify blade stop within 200ms (FR-022), test timeout/retry on communication failure (NFR-008)
  - **Must Fail**: No IMU driver exists yet
  - **Constitutional**: Principle VI (Safety-First) - Tilt cutoff <200ms mandatory

- [x] **T040** [P] Contract test for BME280 environmental sensor at `backend/tests/contract/test_bme280.py`
  - **Test**: Read temperature, humidity, pressure (FR-023), test I2C timeout handling (NFR-008)
  - **Must Fail**: No BME280 driver exists yet

- [x] **T041** [P] Contract test for INA3221 power monitor at `backend/tests/contract/test_ina3221.py`
  - **Test**: Read battery/solar voltage, current from channels 1/3 (FR-024), test I2C timeout/retry (NFR-008)
  - **Must Fail**: No INA3221 driver exists yet

- [x] **T042** [P] Contract test for sensor fusion at `backend/tests/contract/test_sensor_fusion.py`
  - **Test**: Feed GPS + IMU + odometry, verify fused position output (FR-025)
  - **Must Fail**: No sensor fusion exists yet

### Data Models

- [x] **T043** [P] Create NavigationWaypoint Pydantic model at `backend/src/models/navigation_waypoint.py`
  - **Fields**: waypoint_id, latitude, longitude, target_speed_mps, arrival_threshold_m, reached, reached_at_ts
  - **Source**: data-model.md section 7

- [x] **T044** [P] Create SensorReading Pydantic model at `backend/src/models/sensor_reading.py`
  - **Fields**: sensor_id, timestamp_us, value, unit, quality_indicator
  - **Source**: data-model.md section 12

### Driver Implementations (Parallel - independent hardware)

- [x] **T045** [P] Implement VL53L0X ToF driver at `backend/src/drivers/sensors/vl53l0x_driver.py` for left/right sensors via I2C (FR-021)
  - **Acceptance**: T038 contract test passes, emergency stop at <0.2m
  - **Dependencies**: Requires T021 (HardwareDriver ABC)
  - **Constitutional**: Principle VI (Safety-First) - Obstacle detection for emergency stop

- [x] **T046** [P] Implement BNO085 IMU driver at `backend/src/drivers/sensors/bno085_driver.py` via UART with tilt detection (FR-022)
  - **Acceptance**: T039 contract test passes, blade stop <200ms on tilt >30°
  - **Dependencies**: Requires T021 (HardwareDriver ABC)
  - **Research**: research.md section 5 (IMU integration)
  - **Constitutional**: Principle VI (Safety-First) - Tilt cutoff <200ms non-negotiable

- [x] **T047** [P] Implement BME280 environmental driver at `backend/src/drivers/sensors/bme280_driver.py` via I2C (FR-023)
  - **Acceptance**: T040 contract test passes, temperature/humidity/pressure readable
  - **Dependencies**: Requires T021 (HardwareDriver ABC)

- [x] **T048** [P] Implement INA3221 power monitor driver at `backend/src/drivers/sensors/ina3221_driver.py` via I2C with channel assignments (FR-024)
  - **Acceptance**: T041 contract test passes, channels 1 (battery) / 3 (solar) correct
  - **Dependencies**: Requires T021 (HardwareDriver ABC)
  - **Constitutional**: Principle V (Hardware Compliance) - Fixed channel assignments

### Sensor Fusion Implementation

- [x] **T049** Implement Extended Kalman Filter at `backend/src/fusion/ekf.py` for GPS + IMU + odometry fusion (FR-025)
  - **Acceptance**: T042 contract test passes, position accuracy <1m within geofence
  - **Dependencies**: Requires T044 (SensorReading model), T045-T048 (sensor drivers)
  - **Research**: research.md section 5 (EKF algorithm)

- [x] **T050** Implement sensor health monitoring at `backend/src/fusion/sensor_health.py` with quality metrics (FR-025)
  - **Acceptance**: GPS DOP, IMU calibration, ToF confidence tracked
  - **Dependencies**: Requires T049 (EKF fusion)

- [x] **T051** Implement safety interlock triggers at `backend/src/safety/safety_triggers.py` for tilt, impact, low battery, high temp (FR-027)
  - **Acceptance**: Tilt >30°, ToF <0.2m, battery <10V, temp >80°C trigger interlocks
  - **Dependencies**: Requires T033 (interlock validator), T045-T048 (sensors)
  - **Constitutional**: Principle VI (Safety-First) - Multiple safety layers

### CLI Tools

- [x] **T052** [P] Create CLI sensor diagnostics at `backend/src/cli/sensor_commands.py` with live sensor testing (FR-026)
  - **Acceptance**: `lawnberry sensors test --live` displays real-time sensor table (ASCII format: columns for sensor_id, value, unit, health status; 1Hz refresh)
  - **Dependencies**: Requires T045-T048 (sensor drivers)
  - **Constitutional**: Principle X (Observability) - CLI diagnostics mandatory

- [x] **T052.5** [P] Create power budget validation test at `backend/tests/integration/test_power_budget.py` (NFR-016)
  - **Acceptance**: Measure power consumption across operational modes, validate ≤30W during mowing, document peak/average consumption
  - **Dependencies**: Requires T048 (INA3221 driver)
  - **Constitutional**: Principle V (Hardware Compliance) - 30W solar + 30Ah battery design constraint

---

## Phase 4: Navigation Core (FR-028 to FR-034)

### Contract Tests (TDD Phase)

 - [x] **T053** [P] Contract test for GPS integration at `backend/tests/contract/test_gps.py`
  - **Test**: Read GPS position, verify accuracy <5m (FR-028, FR-033)
  - **Must Fail**: No GPS driver exists yet

 - [x] **T054** [P] Contract test for geofence enforcement at `backend/tests/contract/test_geofence.py`
  - **Test**: Position outside boundary, verify immediate stop (FR-030)
  - **Must Fail**: No geofence enforcer exists yet
  - **Constitutional**: Principle VIII (Navigation) - Zero-tolerance geofence mandatory

 - [x] **T055** [P] Contract test for waypoint navigation at `backend/tests/contract/test_waypoint_navigation.py`
  - **Test**: Navigate to waypoint, verify arrival detection (FR-031)
  - **Must Fail**: No waypoint controller exists yet

 - [x] **T056** [P] Contract test for navigation mode manager at `backend/tests/contract/test_navigation_modes.py`
  - **Test**: Mode transitions MANUAL ↔ AUTONOMOUS ↔ EMERGENCY_STOP (FR-032)
  - **Must Fail**: No mode manager exists yet

### Data Models

 - [x] **T057** [P] Create Geofence Pydantic model at `backend/src/models/geofence.py`
  - **Fields**: geofence_id, boundary (array of lat/lon vertices), buffer_distance_m, violation_count
  - **Source**: data-model.md section 8

### Driver & Core Implementations

- [x] **T058** [P] Implement GPS driver at `backend/src/drivers/sensors/gps_driver.py` supporting ZED-F9P (USB) and Neo-8M (UART) (FR-028)
  - **Acceptance**: T053 contract test passes, position updates at 1Hz
  - **Dependencies**: Requires T021 (HardwareDriver ABC), T012 (HardwareConfig)
  - **Constitutional**: Principle V (Hardware Compliance) - ZED-F9P or Neo-8M mutually exclusive

- [x] **T059** Implement odometry calculator at `backend/src/nav/odometry.py` from encoder feedback or motor commands (FR-029)
  - **Acceptance**: Dead-reckoning between GPS updates, integrates with EKF
  - **Dependencies**: Requires T032 (motor controller), T049 (EKF fusion)

 - [x] **T060** Implement geofence enforcer at `backend/src/nav/geofence_enforcer.py` with ray casting algorithm (FR-030)
  - **Acceptance**: T054 contract test passes, zero-tolerance policy enforced
  - **Dependencies**: Requires T057 (Geofence model), T023 (robot state)
  - **Research**: research.md section 6 (ray casting + 3-zone buffer)
  - **Constitutional**: Principle VIII (Navigation) - Zero geofence incursions non-negotiable

 - [x] **T061** Implement waypoint controller at `backend/src/nav/waypoint_controller.py` with sequential execution (FR-031)
  - **Acceptance**: T055 contract test passes, navigates to each waypoint in order
  - **Dependencies**: Requires T043 (NavigationWaypoint model), T059 (odometry)

 - [x] **T062** Implement navigation mode manager at `backend/src/nav/mode_manager.py` (FR-032)
  - **Acceptance**: T056 contract test passes, MANUAL / AUTONOMOUS / EMERGENCY_STOP / CALIBRATION / IDLE modes
  - **Dependencies**: Requires T061 (waypoint controller), T060 (geofence enforcer)
  - **Constitutional**: Principle VIII (Navigation) - GPS degradation → MANUAL mandatory

- [x] **T063** Implement GPS degradation handler at `backend/src/nav/gps_degradation.py` reverting to MANUAL mode (FR-033)
  - **Acceptance**: GPS accuracy >5m or signal lost >10s triggers MANUAL mode
  - **Dependencies**: Requires T058 (GPS driver), T062 (mode manager)
  - **Constitutional**: Principle VIII (Navigation) - Graceful degradation mandatory

- [x] **T064** Implement navigation state API at `backend/src/api/navigation.py` exposing current mode, position, waypoint, geofence status (FR-034)
  - **Acceptance**: GET /nav/status returns complete navigation state
  - **Dependencies**: Requires T062 (mode manager), T060 (geofence enforcer)

---

## Phase 6: Scheduling & Autonomy (FR-035 to FR-041)

### Contract Tests (TDD Phase)

 - [x] **T065** [P] Contract test for job scheduling at `backend/tests/contract/test_scheduler.py`
  - **Test**: Create cron-based job, verify scheduled execution (FR-035)
  - **Must Fail**: No scheduler exists yet

- [x] **T066** [P] Contract test for weather postponement at `backend/tests/contract/test_weather_postponement.py`
  - **Test**: Rain detected, verify job postponed (FR-036)
  - **Must Fail**: No weather service exists yet

- [x] **T067** [P] Contract test for coverage pattern generation at `backend/tests/contract/test_coverage_pattern.py`
  - **Test**: Generate parallel-line pattern with configurable width/overlap (FR-037)
  - **Must Fail**: No pattern generator exists yet

- [x] **T068** [P] Contract test for solar charge management at `backend/tests/contract/test_solar_charge.py`
  - **Test**: Battery <20%, verify return to solar waypoint (FR-038)
  - **Must Fail**: No charge manager exists yet

### Data Models

 - [x] **T069** [P] Create ScheduledJob Pydantic model at `backend/src/models/scheduled_job.py`
  - **Fields**: job_id, name, cron_expression, zone_assignments, weather_check_enabled, retry_policy, state (IDLE/SCHEDULED/RUNNING/PAUSED/COMPLETED/FAILED), next_run_ts, last_run_ts
  - **Source**: data-model.md section 10

 - [x] **T070** [P] Create CoveragePattern Pydantic model at `backend/src/models/coverage_pattern.py`
  - **Fields**: pattern_id, zone_id, lines (array of waypoint pairs), cutting_width_m, overlap_m, coverage_percentage, estimated_duration_s
  - **Source**: data-model.md section 9

### Core Implementations

- [x] **T071** Implement calendar scheduler at `backend/src/scheduler/job_scheduler.py` with cron-like syntax (FR-035)
  - **Acceptance**: T065 contract test passes, jobs execute at scheduled times
  - **Dependencies**: Requires T069 (ScheduledJob model)

- [x] **T072** Implement OpenWeatherMap API client at `backend/src/scheduler/weather_api.py` with 6-hour cache (FR-036, FR-036a)
  - **Acceptance**: Free tier 1000 calls/day, forecast cached 6h
  - **Dependencies**: None (external API)
  - **Research**: research.md section 7 (OpenWeatherMap integration)

- [x] **T073** Implement weather sensor fallback at `backend/src/scheduler/weather_sensor_fallback.py` using BME280 (FR-036b)
  - **Acceptance**: High humidity (>85%) or low pressure (<1000 hPa) indicates unsuitable weather
  - **Dependencies**: Requires T047 (BME280 driver), T072 (weather API)
  - **Research**: research.md section 7 (sensor fallback logic)

- [x] **T074** Implement weather suitability evaluator at `backend/src/scheduler/weather_service.py` combining API + sensors (FR-036, FR-036c)
  - **Acceptance**: T066 contract test passes, postpones jobs during adverse weather
  - **Dependencies**: Requires T072 (weather API), T073 (sensor fallback)

- [x] **T075** Implement parallel-line coverage pattern generator at `backend/src/scheduler/coverage_generator.py` (FR-037)
  - **Acceptance**: T067 contract test passes, <10cm overlap configurable
  - **Dependencies**: Requires T070 (CoveragePattern model), T057 (Geofence model)

- [x] **T076** Implement solar charge monitor at `backend/src/scheduler/charge_monitor.py` with return-to-solar behavior (FR-038)
  - **Acceptance**: T068 contract test passes, battery <20% triggers return
  - **Dependencies**: Requires T048 (INA3221 driver), T061 (waypoint controller)

- [x] **T077** Implement job state machine at `backend/src/scheduler/job_state_machine.py` (FR-039)
  - **Acceptance**: IDLE → SCHEDULED → RUNNING → PAUSED → COMPLETED / FAILED transitions
  - **Dependencies**: Requires T069 (ScheduledJob model)

- [x] **T078** Implement pre-job safety validation at `backend/src/scheduler/safety_validator.py` (FR-040)
  - **Acceptance**: Verifies E-stop cleared, interlocks inactive, GPS available before job start
  - **Dependencies**: Requires T033 (interlock validator), T063 (GPS degradation handler)

- [x] **T079** Implement return-to-home behavior at `backend/src/scheduler/return_to_home.py` (FR-041)
  - **Acceptance**: Job completion or abort navigates to home waypoint
  - **Dependencies**: Requires T061 (waypoint controller)

---

## Phase 7: Reliability, Testing & Polish (FR-042 to FR-047)

### Contract Tests (TDD Phase)

- [x] **T080** [P] Contract test for fault injection at `backend/tests/contract/test_fault_injection.py`
  - **Test**: Inject sensor timeout, verify graceful degradation (FR-042)
  - **Must Fail**: No fault injector exists yet

- [x] **T081** [P] Contract test for 8-hour soak at `backend/tests/contract/test_8hour_soak.py`
  - **Test**: Run continuously 8h, verify zero unsafe events, <5% memory growth (FR-043)
  - **Must Fail**: No soak test framework exists yet
  - **Note**: Quick 5-minute version for CI, full 8h for production

- [x] **T082** [P] Contract test for log bundle generation at `backend/tests/contract/test_log_bundle.py`
  - **Test**: Generate tar.gz with logs, state snapshot, telemetry (FR-044)
  - **Must Fail**: No log bundle generator exists yet

- [x] **T082.5** [P] Integration test for service recovery at `backend/tests/integration/test_service_recovery.py` (NFR-007)
  - **Test**: Crash message bus service, verify subscribers reconnect; crash driver service, verify registry restarts it; validate no data loss
  - **Must Fail**: No recovery mechanisms exist yet
  - **Constitutional**: Principle IV (Hardware Coordination) - Resource ownership survives crashes

### Data Models

 - [x] **T083** [P] Create LogBundle Pydantic model at `backend/src/models/log_bundle.py`
  - **Fields**: bundle_id, created_at_ts, included_files (backend.log, safety.log, sensors.log, state_snapshot.json, telemetry.jsonl), size_bytes, trigger_reason
  - **Source**: data-model.md section 12

### Core Implementations

- [x] **T084** Implement fault injection framework at `backend/src/testing/fault_injector.py` with pytest fixtures (FR-042)
  - **Acceptance**: T080 contract test passes, environment variable control (FAULT_INJECT=sensor_timeout,gps_loss)
  - **Dependencies**: Requires T020 (driver registry)
  - **Research**: research.md section 9 (pytest fixtures + injector middleware)
  - **Constitutional**: Principle III (Test-First) - Testing frameworks for reliability

- [x] **T085** Implement 8-hour soak test at `backend/tests/soak/test_8hour_operation.py` with automated pass/fail (FR-043)
  - **Acceptance**: T081 contract test passes, zero unsafe events, memory stable, <10ms p99 latency
  - **Dependencies**: Requires T022 (simulation mode), T084 (fault injection)
  - **Research**: research.md section 10 (soak testing methodology)
  - **Constitutional**: Principle VI (Safety-First) - 8+ hour operation validated

- [x] **T086** Implement log bundle generator at `backend/src/tools/log_bundle_generator.py` (FR-044)
  - **Acceptance**: T082 contract test passes, tar.gz includes logs + state + telemetry
  - **Dependencies**: Requires T083 (LogBundle model), T004 (structured logging)
  - **Constitutional**: Principle X (Observability) - Incident analysis support

- [x] **T087** [P] Implement dashboard endpoints at `backend/src/api/dashboard.py` exposing battery, coverage, safety, uptime metrics (FR-045)
  - **Acceptance**: GET /dashboard/metrics returns key performance indicators
  - **Dependencies**: Requires T048 (power monitor), T075 (coverage generator), T051 (safety triggers)
  - **Constitutional**: Principle X (Observability) - Dashboard visualizations recommended

### Documentation Tasks (Parallel)

- [x] **T088** [P] Create operational procedures at `docs/OPERATIONS.md` covering recovery, calibration, troubleshooting (FR-046)
  - **Acceptance**: Documented: E-stop recovery, IMU calibration, GPS setup, geofence definition
  - **Dependencies**: None (documentation)
  - **Constitutional**: Principle X (Observability) - Operational docs mandatory

- [x] **T089** [P] Update setup guide at `docs/installation-setup-guide.md` with Phase 0-7 instructions
  - **Acceptance**: Step-by-step from fresh Pi to operational system
  - **Dependencies**: Requires T001 (setup script)

- [x] **T090** [P] Create hardware integration guide at `docs/hardware-integration.md` for sensor wiring, E-stop button, RoboHAT connections
  - **Acceptance**: Pin assignments, I2C addresses, UART config documented
  - **Dependencies**: None (documentation)
  - **Constitutional**: Principle V (Hardware Compliance) - Hardware config documented

### Final Validation

 - [x] **T091** Execute complete quickstart validation at `specs/002-complete-engineering-plan/quickstart.md` (all 7 phases)
  - **Acceptance**: All 7 phase validations pass (Phase 0-6 + Phase 7), measure and validate startup time <30s cold boot to operational (NFR-004)
  - **Dependencies**: Requires ALL previous tasks complete
  - **Constitutional**: Principle III (Test-First) - Full system validation mandatory

 - [x] **T092** Verify acceptance criteria: E-stop <100ms, tilt cutoff <200ms, UI telemetry ≤1s, zero geofence incursions (FR-047)
  - **Acceptance**: All constitutional requirements validated
  - **Dependencies**: Requires T091 (quickstart validation)
  - **Constitutional**: ALL PRINCIPLES - Final constitutional compliance gate

 - [x] **T093** [P] Update AGENT_JOURNAL.md at `.specify/memory/AGENT_JOURNAL.md` documenting completion, decisions, handoff notes
  - **Acceptance**: Session summary, validation results, constitutional compliance verified
  - **Dependencies**: Requires T092 (acceptance criteria)
  - **Constitutional**: Development Workflow - Agent journal mandatory

---

## Dependencies

### Critical Path (No Parallelization)
```
Setup (T001-T007) 
  → Models Phase 1 (T012-T017) 
  → Message Bus (T018-T019) 
  → Driver Registry (T020-T022) 
  → Robot State (T023-T024)
  → E-stop Handler (T030) 
  → Watchdog (T031) 
  → Motor Controller (T032-T036)
  → Sensor Drivers (T045-T048) 
  → Sensor Fusion (T049-T051)
  → GPS + Geofence (T058, T060, T062-T064)
  → Scheduler (T071, T074, T077-T079)
  → Testing (T084-T086, T091-T092)
```

### Parallel Execution Groups

**Group 1: Setup (Phase 0)** - Can run in parallel:
```bash
Task T001: "Create setup.sh with idempotent installation"
Task T002: "Create CI workflow .github/workflows/ci.yml"
Task T004: "Implement JSON logging backend/src/core/logger.py"
Task T005: "Create Prometheus metrics backend/src/api/metrics.py"
Task T006: "Configure uv with pyproject.toml and uv.lock"
Task T007: "Create auth service backend/src/auth/"
```

**Group 2: Data Models (Phase 1)** - Can run in parallel:
```bash
Task T012: "HardwareConfig model backend/src/models/hardware_config.py"
Task T013: "SafetyLimits model backend/src/models/safety_limits.py"
Task T014: "MessageBusEvent model backend/src/models/message_bus_event.py"
Task T015: "DriverInstance model backend/src/models/driver_instance.py"
Task T017: "SafetyInterlock model backend/src/models/safety_interlock.py"
Task T043: "NavigationWaypoint model backend/src/models/navigation_waypoint.py"
Task T044: "SensorReading model backend/src/models/sensor_reading.py"
Task T057: "Geofence model backend/src/models/geofence.py"
Task T069: "ScheduledJob model backend/src/models/scheduled_job.py"
Task T070: "CoveragePattern model backend/src/models/coverage_pattern.py"
Task T083: "LogBundle model backend/src/models/log_bundle.py"
```

**Group 3: Contract Tests (Phase 1)** - Can run in parallel:
```bash
Task T008: "Message bus contract test backend/tests/contract/test_message_bus.py"
Task T009: "Message persistence test backend/tests/contract/test_message_persistence.py"
Task T010: "Driver registry test backend/tests/contract/test_driver_registry.py"
Task T011: "Simulation mode test backend/tests/contract/test_simulation_mode.py"
```

**Group 4: Safety Contract Tests (Phase 2)** - Can run in parallel:
```bash
Task T025: "E-stop GPIO test backend/tests/contract/test_estop_gpio.py"
Task T026: "Watchdog test backend/tests/contract/test_watchdog.py"
Task T027: "Motor default state test backend/tests/contract/test_motor_default_state.py"
Task T028: "Safety interlocks test backend/tests/contract/test_safety_interlocks.py"
Task T029: "Manual teleop test backend/tests/contract/test_manual_teleop.py"
```

**Group 5: Sensor Drivers (Phase 3)** - Can run in parallel (independent hardware):
```bash
Task T045: "VL53L0X ToF driver backend/src/drivers/sensors/vl53l0x_driver.py"
Task T046: "BNO085 IMU driver backend/src/drivers/sensors/bno085_driver.py"
Task T047: "BME280 environmental driver backend/src/drivers/sensors/bme280_driver.py"
Task T048: "INA3221 power monitor driver backend/src/drivers/sensors/ina3221_driver.py"
```

**Group 6: Navigation Contract Tests (Phase 4)** - Can run in parallel:
```bash
Task T053: "GPS contract test backend/tests/contract/test_gps.py"
Task T054: "Geofence contract test backend/tests/contract/test_geofence.py"
Task T055: "Waypoint navigation test backend/tests/contract/test_waypoint_navigation.py"
Task T056: "Navigation modes test backend/tests/contract/test_navigation_modes.py"
```

**Group 7: Scheduling Contract Tests (Phase 6)** - Can run in parallel:
```bash
Task T065: "Job scheduling test backend/tests/contract/test_scheduler.py"
Task T066: "Weather postponement test backend/tests/contract/test_weather_postponement.py"
Task T067: "Coverage pattern test backend/tests/contract/test_coverage_pattern.py"
Task T068: "Solar charge test backend/tests/contract/test_solar_charge.py"
```

**Group 8: Reliability Contract Tests (Phase 7)** - Can run in parallel:
```bash
Task T080: "Fault injection test backend/tests/contract/test_fault_injection.py"
Task T081: "8-hour soak test backend/tests/contract/test_8hour_soak.py"
Task T082: "Log bundle test backend/tests/contract/test_log_bundle.py"
```

**Group 9: Documentation (Phase 7)** - Can run in parallel:
```bash
Task T088: "Create docs/OPERATIONS.md"
Task T089: "Update docs/installation-setup-guide.md"
Task T090: "Create docs/hardware-integration.md"
```

---

## Validation Checklist

✅ **All contracts have corresponding tests** - 28 contract tests across 7 phases  
✅ **All entities have model tasks** - 12 Pydantic models (T012-T017, T043-T044, T057, T069-T070, T083)  
✅ **All tests come before implementation** - TDD ordering enforced (contract tests → models → implementation)  
✅ **Parallel tasks truly independent** - 42 tasks marked [P], different files, no dependencies  
✅ **Each task specifies exact file path** - All 93 tasks have absolute paths  
✅ **No task modifies same file as another [P] task** - Verified: all [P] tasks touch different files  
✅ **Constitutional compliance verified** - Safety-critical tasks flagged, all principles satisfied

---

## Execution Strategy

**Total Tasks**: 93 tasks
- **Phase 0 (Setup)**: T001-T007 (7 tasks, 6 parallelizable)
- **Phase 1 (Core)**: T008-T024 (17 tasks, 11 parallelizable)
- **Phase 2 (Safety)**: T025-T037 (13 tasks, 5 parallelizable)
- **Phase 3 (Sensors)**: T038-T052 (15 tasks, 7 parallelizable)
- **Phase 4 (Navigation)**: T053-T064 (12 tasks, 5 parallelizable)
- **Phase 6 (Scheduling)**: T065-T079 (15 tasks, 5 parallelizable)
- **Phase 7 (Reliability)**: T080-T093 (14 tasks, 6 parallelizable)

**Parallelizable**: 42 tasks marked [P] (45%)  
**Critical Path**: 51 tasks (sequential dependencies)  
**Estimated Effort**: 6-8 weeks solo, 3-4 weeks with 2 developers (leveraging parallelization)

**Constitutional Gates**:
- **Phase 2 Gate**: E-stop <100ms, watchdog enforced, OFF default validated before proceeding
- **Phase 3 Gate**: Tilt cutoff <200ms, sensor fusion operational before navigation
- **Phase 4 Gate**: Zero-tolerance geofence validated before autonomous scheduling
- **Final Gate (T092)**: ALL acceptance criteria verified before feature completion

**Next Step**: Begin with Group 1 (Setup tasks T001-T007), then proceed through phases in order, executing parallel groups simultaneously where possible.
