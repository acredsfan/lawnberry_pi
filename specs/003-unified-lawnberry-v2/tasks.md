# Tasks: LawnBerry Pi v2 Unified System

**Input**: Design documents from `/home/pi/lawnberry/specs/003-unified-lawnberry-v2/`
**Prerequisites**: plan.md (required), research.md, data-model.md, contracts/, quickstart.md

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Each task must end with passing tests + updated docs
- Include exact file paths in descriptions
- Constitutional compliance required for all tasks

## Phase 3.1: Foundation & Constitutional Compliance

### T001 [X] Validate current v2 scaffold against unified requirements
Review and update existing project structure for unified specification:
- Verify `pyproject.toml` ARM64 guards and constitutional package restrictions
- Update `src/lawnberry/` modules for unified sensor/AI/WebUI integration
- Validate `.pre-commit-config.yaml` and CI configuration
- Update `/docs/architecture.md` with unified system overview
- Tests: Enhance `tests/test_project_structure.py` for unified requirements

### T002 [X] Enhance WebSocket hub for unified telemetry requirements
Extend existing WebSocket hub implementation:
- Update `src/lawnberry/core/websocket_hub.py` for autonomous system integration
- Add sensor data streaming, navigation updates, safety alerts
- Implement configurable cadence (1-10Hz) with constitutional compliance
- Tests: Extend WebSocket hub tests for sensor data integration
- Docs: Update WebSocket hub documentation with unified requirements

### T003 [X] Complete data model implementations for unified system
Finish implementing remaining dataclasses from unified data-model.md:
- Add `SensorReading`, `NavigationState`, `MotorCommand`, `SafetySystem`
- Add `PowerSystem`, `AIAccelerator`, `VisionProcessing`
- Add `SystemConfiguration`, `OperationalData`
- Extend existing WebUI dataclasses for autonomous system integration
- Tests: Comprehensive validation of all data models

## Phase 3.2: AI Acceleration & Vision (Constitutional Compliance)

### T004 [P] CPU TFLite runner + synthetic testing; constitutional compliance
Enhance existing CPU fallback implementation:
- Verify `src/lawnberry/runners/cpu_tflite_runner.py` constitutional compliance
- Add object detection models for navigation assistance
- Extend synthetic testing with lawn mower scenarios
- Update performance benchmarks for unified system requirements
- Tests: Integration with navigation and safety systems

### T005 [P] Hailo runner with constitutional isolation; graceful degradation
Implement optional mid-tier acceleration per constitutional requirements:
- `src/lawnberry/runners/hailo_runner.py` with device detection
- Constitutional compliance: no concurrent RoboHAT usage
- `scripts/setup_env_hailo.sh` for SDK installation
- Graceful fallback when hardware unavailable
- Tests: Hardware detection and fallback scenarios
- Docs: `/docs/ai-acceleration/hailo.md` with constitutional constraints

### T006 [P] Coral USB isolation: constitutional venv-coral compliance
Implement top-tier acceleration with strict constitutional isolation:
- `scripts/setup_coral_venv.sh` creating isolated environment
- `src/lawnberry/runners/coral_runner.py` with subprocess communication
- Constitutional ban on pycoral/edgetpu in main environment
- `systemd/coral-runner.service.template` for service isolation
- Tests: `tests/integration/test_coral_isolation.py` validates separation
- Docs: `/docs/ai-acceleration/coral-tpu.md` with SDK warnings

## Phase 3.3: Core Sensor & Hardware Systems

### T007 [P] IMU integration: BNO085 on UART4 constitutional compliance
Implement IMU positioning per hardware.yaml requirements:
- `src/lawnberry/sensors/bno085_driver.py` for UART4 @ 3Mbaud
- Integration with NavigationState for heading/orientation
- Sensor fusion with GPS and encoder data
- `tests/integration/test_imu_integration.py` with simulation support
- Docs: `/docs/sensors/imu-bno085.md` with calibration procedures

### T008 [P] Power monitoring: INA3221 constitutional channel compliance
Implement power system per constitutional channel assignments:
- `src/lawnberry/sensors/ina3221_driver.py` for I2C 0x40
- Constitutional channels: 1=Battery, 2=Unused, 3=Solar
- Integration with PowerSystem entity and safety protocols
- Battery management and charging return logic
- Tests: `tests/integration/test_power_system.py` with channel validation
- Docs: `/docs/sensors/power-monitoring.md` with constitutional requirements

### T009 [P] ToF sensors: VL53L0X dual sensor setup
Implement distance sensing per hardware.yaml specifications:
- `src/lawnberry/sensors/vl53l0x_driver.py` for I2C 0x29/0x30
- GPIO shutdown control (pins 22/23) and interrupt handling (6/12)
- Integration with obstacle detection and safety systems
- Address conflict resolution and dual sensor management
- Tests: `tests/integration/test_tof_sensors.py` with simulation
- Docs: `/docs/sensors/tof-vl53l0x.md` with setup procedures
 - Orientation: Document that “left” = front-left and “right” = front-right (headlight positions)

### T010 [P] Environmental sensors: BME280 + SSD1306 display
Implement environmental monitoring and display:
- `src/lawnberry/sensors/bme280_driver.py` for I2C 0x76
- `src/lawnberry/display/ssd1306_driver.py` for I2C 0x3C
- Weather data integration and display management
- Tests: Environmental sensor simulation and display testing
- Docs: Sensor documentation with I2C address validation

## Phase 3.4: Navigation & GPS Systems

### T011 [P] GPS integration: constitutional dual-mode support
Implement GPS per constitutional requirements (mutually exclusive):
- `src/lawnberry/navigation/gps_manager.py` with mode selection
- ZED-F9P USB with NTRIP corrections (preferred)
- Neo-8M UART fallback (alternative, no RTK)
- Constitutional compliance: exclusive mode operation
- Tests: `tests/integration/test_gps_modes.py` with mode validation
- Docs: `/docs/navigation/gps-configuration.md` with mode selection

### T012 [P] Navigation system: path planning and obstacle avoidance
Implement autonomous navigation capabilities:
- `src/lawnberry/navigation/path_planner.py` with boundary respect
- `src/lawnberry/navigation/obstacle_detector.py` using ToF and vision
- Integration with SafetySystem for emergency responses
- Map-based navigation with zone definitions
- Tests: Navigation simulation with obstacle scenarios
- Docs: `/docs/navigation/autonomous-operation.md`
 - Add solar-aware idle behavior: choose Home, AM Sun, or PM Sun positions

## Phase 3.5: Motor Control & Safety Systems

### T013 [P] Motor control: constitutional drive system support
Implement motor control per constitutional hierarchy:
- `src/lawnberry/control/motor_controller.py` with driver abstraction
- RoboHAT RP2040 → Cytron MDDRC10 (preferred)
- L298N dual H-bridge (alternative fallback)
- Encoder feedback integration and safety interlocks
- Tests: Motor control simulation and safety validation
- Docs: `/docs/control/motor-systems.md` with controller options
 - Commands MUST be sent via serial to RP2040 `robohat_files/code.py`; avoid firmware edits unless hall-effect support missing

### T014 [P] Blade control: IBT-4 H-Bridge with safety interlocks
Implement cutting system per constitutional requirements:
- `src/lawnberry/control/blade_controller.py` for GPIO 24/25
- IBT-4 H-Bridge control with safety interlocks
- Tilt detection and emergency stop integration
- Blade safety protocols and audit logging
- Tests: Blade control safety scenarios
- Docs: `/docs/control/blade-safety.md` with interlock procedures

### T015 [P] Safety system: comprehensive hazard detection
Implement safety monitoring and emergency response:
- `src/lawnberry/safety/safety_monitor.py` with multi-source detection
- Emergency stop, tilt detection, obstacle proximity
- Integration with all motor systems for immediate shutdown
- Safety alert routing to WebUI and logging
- Tests: `tests/integration/test_safety_system.py` with hazard scenarios
- Docs: `/docs/safety/hazard-detection.md`

## Phase 3.6: Camera & Vision Pipeline

### T016 [P] Camera service: constitutional exclusive ownership
Implement camera system per constitutional requirements:
- `src/lawnberry/services/camera_service.py` with exclusive device access
- Picamera2 → GStreamer pipeline implementation
- IPC-based frame distribution (no direct camera sharing)
- `systemd/camera-stream.service` for service ownership
- Tests: Camera service isolation and IPC distribution
- Docs: `/docs/vision/camera-architecture.md` with ownership model

### T017 [P] Vision processing: AI-accelerated object detection
Implement vision processing with constitutional acceleration:
- `src/lawnberry/vision/object_detector.py` using AI runners
- Integration with constitutional acceleration hierarchy
- Obstacle detection for navigation safety
- Training data capture for AI improvement
- Tests: Vision processing with synthetic frames
- Docs: `/docs/vision/object-detection.md`

## Phase 3.7: WebUI Implementation & REST API

### T018 [P] Enhanced REST API: unified system endpoints
Extend existing REST API for autonomous system integration:
- Add navigation endpoints: `/api/navigation/status`, `/api/navigation/path`
- Add sensor endpoints: `/api/sensors/readings`, `/api/sensors/health`
- Add safety endpoints: `/api/safety/status`, `/api/safety/alerts`
- Add power endpoints: `/api/power/status`, `/api/power/history`
- Update existing endpoints for autonomous system data
 - Add Map provider & boundary endpoints; add Home/AM/PM sun locations endpoints
 - Add RC status endpoint including hall sensor fields
- Tests: Comprehensive API contract validation
- Docs: Complete API documentation with autonomous features

### T019 [P] WebUI page enhancements: autonomous system integration
Enhance existing seven WebUI pages for autonomous operation:
- Dashboard: Add autonomous status, navigation state, sensor health
- Map Setup: Add autonomous boundary definition and zone management
	- Polygon drawing with Google Maps (preferred) and OpenStreetMap fallback
	- Marker: Use LawnBerryPi_Pin.png for mower position icon
- Manual Control: Add safety overrides and autonomous system controls
- Mow Planning: Add autonomous job scheduling and progress tracking
- AI Training: Add object detection model management
- Settings: Add autonomous system configuration options
- Docs Hub: Add autonomous operation documentation
- Tests: WebUI integration testing with autonomous features

### T020 [P] WebSocket integration: autonomous system telemetry
Extend WebSocket hub for autonomous system real-time updates:
- Add navigation telemetry streams
- Add sensor data broadcasts with constitutional cadence
- Add safety alert immediate notifications
- Add job progress and completion updates
 - Add map locations and boundary update topics; add rc/status topic with hall sensors
- Integration with existing WebSocket infrastructure
- Tests: Real-time data streaming validation
- Docs: WebSocket topic documentation for autonomous features

## Phase 3.8: System Integration & Services

### T021 [P] Service orchestration: systemd integration
Implement system service management:
- `systemd/mower-core.service` for main autonomous system
- `systemd/sensor-monitor.service` for sensor data collection
- `systemd/navigation.service` for path planning and execution
- `systemd/safety-monitor.service` for hazard detection
- Service dependencies and startup ordering
- Tests: Service integration and dependency validation
- Docs: `/docs/deployment/service-management.md`

### T022 [P] Configuration management: unified system configuration
Implement configuration system for autonomous operation:
- `src/lawnberry/config/config_manager.py` with validation
- Hardware detection and configuration validation
- User preference management and persistence
- Simulation mode configuration (SIM_MODE=1)
- Constitutional compliance validation
- Tests: Configuration validation and simulation support
- Docs: `/docs/configuration/system-setup.md`

### T023 [P] Data persistence: operational data and analytics
Implement data management for autonomous system:
- `src/lawnberry/data/data_manager.py` for operational data
- Sensor data archiving and analytics
- Navigation performance tracking
- Safety event logging and analysis
- User action audit trails
- Tests: Data persistence and retrieval validation
- Docs: `/docs/data/data-management.md`

## Phase 3.9: Installation & Migration

### T024 [P] Installation scripts: unified system deployment
Create comprehensive installation and setup:
- `scripts/install_lawnberry_v2.sh` for complete system setup
- Hardware detection and validation
- Service installation and configuration
- Constitutional compliance verification
- Dependency management and virtual environment setup
- Tests: Installation script validation in clean environment
- Docs: `/docs/installation/complete-setup.md`

### T025 [P] Migration system: v1 to v2 upgrade path
Implement migration from LawnBerry Pi v1:
- `scripts/migrate_v1_to_v2.sh` for data preservation
- Configuration migration and validation
- Service migration and testing
- Rollback procedures for failed migrations
- User data and preference preservation
- Tests: Migration validation with v1 data
- Docs: `/docs/migration/v1-to-v2-guide.md`

## Phase 3.10: Testing & Documentation

### T026 [P] Comprehensive test suite: unified system validation
Implement complete testing framework:
- Unit tests for all components with mock hardware
- Integration tests with SIM_MODE=1 simulation
- Contract tests for API and WebSocket validation
- Performance tests for constitutional compliance
- Safety tests for hazard scenarios
- Tests: Meta-testing to ensure coverage completeness
- Docs: `/docs/testing/test-framework.md`

### T027 [P] Simulation framework: SIM_MODE=1 complete coverage
Implement comprehensive simulation support:
- `src/lawnberry/simulation/` with mock hardware drivers
- Sensor simulation with realistic data patterns
- Navigation simulation with virtual environments
- Safety scenario simulation for testing
- AI processing simulation with synthetic data
- Tests: Simulation framework validation
- Docs: `/docs/simulation/sim-mode-guide.md`

### T028 [P] Documentation site: comprehensive user guides
Create complete documentation system:
- User guides for operation and maintenance
- Developer guides for system extension
- Troubleshooting guides for common issues
- API documentation with examples
- Constitutional compliance guides
- Installation and migration procedures
- Tests: Documentation completeness validation
- Docs: Complete documentation site structure

## Phase 3.11: Validation & Deployment

### T029 [P] Constitutional compliance audit: complete system validation
Comprehensive constitutional compliance verification:
- Platform exclusivity validation (Raspberry Pi OS Bookworm)
- AI acceleration hierarchy compliance
- Hardware specification alignment with hardware.yaml
- Package isolation verification (pycoral ban)
- Documentation-as-contract validation
- Test-driven development compliance
- Tests: Constitutional compliance test suite
- Docs: Compliance audit report

### T030 [P] Performance optimization: Pi 5/Pi 4B compatibility
System performance tuning for constitutional platforms:
- Pi 5 optimal performance configuration
- Pi 4B graceful degradation strategies
- Memory usage optimization
- CPU utilization balancing
- WebUI responsiveness tuning
- Tests: Performance benchmarking on both platforms
- Docs: Performance optimization guide

### T031 [P] Field testing preparation: hardware-in-the-loop validation
Prepare system for real hardware testing:
- Hardware-in-the-loop test procedures
- Field testing safety protocols
- Performance validation procedures
- Issue tracking and resolution workflows
- Hardware compatibility verification
- Tests: Hardware testing automation where possible
- Docs: Field testing guide and safety procedures

---

## Task Dependencies & Execution Order

### Critical Path Dependencies
- T001 → T002 → T003 (Foundation must complete before system integration)
- T004,T005,T006 can run in parallel (AI runners independent)
- T007,T008,T009,T010 can run in parallel (sensors independent)
- T011,T012 → T013,T014,T015 (navigation before motor control)
- T016,T017 can run in parallel (vision components)
- T018,T019,T020 depend on core systems (T007-T017)
- T021,T022,T023 depend on all core systems
- T024,T025 depend on complete implementation
- T026,T027,T028 can run in parallel with implementation
- T029,T030,T031 final validation and optimization

### Parallel Execution Opportunities
```
Phase 3.2: T004 || T005 || T006 (AI runners)
Phase 3.3: T007 || T008 || T009 || T010 (sensors)
Phase 3.4: T011 || T012 (navigation components)
Phase 3.5: T013 || T014 || T015 (control systems)
Phase 3.6: T016 || T017 (vision pipeline)
Phase 3.7: T018 || T019 || T020 (WebUI components)
Phase 3.8: T021 || T022 || T023 (system integration)
Phase 3.9: T024 || T025 (deployment)
Phase 3.10: T026 || T027 || T028 (validation)
Phase 3.11: T029 || T030 || T031 (final validation)
```

## Constitutional Compliance Notes
- All tasks must maintain ARM64/Raspberry Pi OS Bookworm exclusivity
- AI acceleration must follow constitutional hierarchy with proper isolation
- Hardware specifications must align exactly with hardware.yaml
- Package restrictions must be enforced (pycoral/edgetpu banned from main env)
- Documentation must be updated with every functional change
- Test-driven development approach required for all implementations
- Simulation mode (SIM_MODE=1) must provide complete coverage for CI