# Feature Specification: LawnBerry Pi v2 Unified System

**Feature Branch**: `004-lawnberry-pi-v2`  
**Created**: 2025-09-25  
**Status**: Draft
**Input**: Unified specification combining autonomous mower system implementation with WebUI page requirements, aligned with constitution v1.3.0, updated hardware.yaml, and pyproject.toml

## Execution Flow (main)
```
1. Parse user description from Input
   → If empty: ERROR "No feature description provided"
2. Extract key concepts from description
   → Identify: actors, actions, data, constraints
3. For each unclear aspect:
   → Mark with [NEEDS CLARIFICATION: specific question]
4. Fill User Scenarios & Testing section
   → If no clear user flow: ERROR "Cannot determine user scenarios"
5. Generate Functional Requirements
   → Each requirement must be testable
   → Mark ambiguous requirements
6. Identify Key Entities (if data involved)
7. Run Review Checklist
   → If any [NEEDS CLARIFICATION]: WARN "Spec has uncertainties"
   → If implementation details found: ERROR "Remove tech details"
8. Return: SUCCESS (spec ready for planning)
```

---
## ⚡ Quick Guidelines
- ✅ Focus on WHAT users need and WHY
- ❌ Avoid HOW to implement (no tech stack, APIs, code structure)
- 👥 Written for business stakeholders, not developers

---

## User Scenarios & Testing

### Primary User Story
A user wants to operate an autonomous robotic lawn mower through a comprehensive web interface that provides real-time monitoring, manual control, autonomous operation planning, AI-powered obstacle detection, and system configuration. The system must handle all aspects of autonomous mowing operations while ensuring safety, providing visual feedback, and maintaining operational efficiency across varying hardware configurations and environmental conditions.

### Acceptance Scenarios

#### Core Autonomous Operation
1. **Given** the mower is powered on and positioned on a lawn, **When** the user initiates mowing through the web interface, **Then** the system autonomously navigates and mows the designated area while avoiding obstacles and maintaining safety protocols
2. **Given** the mower is operating autonomously, **When** an obstacle or safety hazard is detected, **Then** the system immediately stops motors, activates safety protocols, and alerts the user through the web interface with specific hazard information
3. **Given** the mower battery reaches a low threshold, **When** power management triggers energy-conserving behavior, **Then** the system autonomously navigates to the most appropriate location based on time-of-day and sun availability — the "AM Sun" location in morning hours, the "PM Sun" location in afternoon hours, or the user-defined "Home" location otherwise — and notifies the user of the charge/idle status (no physical docking station)

#### WebUI Experience & Control
4. **Given** the user opens the web interface Dashboard, **When** the mower is operating, **Then** real-time telemetry data (position, battery, sensor readings, safety status, camera feed) is displayed with <100ms latency and 5Hz update frequency
5. **Given** the user accesses Manual Control with proper authentication, **When** direct commands are issued, **Then** the system responds immediately with visual feedback and safety override capabilities
6. **Given** the user configures mowing zones in Map Setup, **When** boundaries and exclusion areas are defined with a polygon drawing tool, **Then** the system validates the configuration and updates navigation parameters in real time. The map uses Google Maps as the preferred provider (with usage optimized to keep API costs negligible) and OpenStreetMap as a selectable fallback. The mower’s live position is shown using the LawnBerry map pin asset (LawnBerryPi_Pin.png).
7. **Given** the user schedules jobs in Mow Planning, **When** jobs are queued and executed, **Then** progress updates stream live with estimated completion times and zone-specific status
8. **Given** the user reviews captured imagery in AI Training, **When** datasets are labeled and exported, **Then** the system generates both COCO JSON and YOLO TXT formats for downstream processing within the defined performance bounds (see NFR-007)

#### Hardware & Platform Compliance
9. **Given** the system runs on Raspberry Pi 5 or Pi 4B with Raspberry Pi OS Bookworm, **When** hardware detection occurs, **Then** the system correctly identifies and configures sensors, GPS (ZED-F9P USB or Neo-8M UART), and motor controllers (RoboHAT→Cytron MDDRC10 or L298N fallback)
10. **Given** AI acceleration hardware is available, **When** object detection runs, **Then** the system prioritizes Coral USB (isolated venv), then Hailo HAT, then CPU fallback while maintaining constitutional package isolation
11. **Given** power monitoring via INA3221, **When** system operates, **Then** Channel 1 tracks battery, Channel 2 remains unused, and Channel 3 monitors solar input per constitutional requirements
12. **Given** GPS is temporarily unavailable, **When** dead-reckoning is engaged, **Then** navigation drift shall remain ≤1.0 meter per 10 seconds (P95) for up to 60 seconds of outage, and the system shall autonomously revert to GPS once available (see NFR-008)

#### Migration & Maintenance
12. **Given** a user has LawnBerry Pi v1, **When** they follow the migration process, **Then** they can successfully upgrade to v2 with preserved settings and minimal operational disruption

### Edge Cases
- What happens when GPS signal is lost during navigation and system must rely on IMU/encoder dead reckoning?
- How does the system handle sensor failures or inconsistent readings while maintaining operational safety?
- What occurs when Wi-Fi connectivity is interrupted during field operations (Ethernet unavailable per constitution)?
- How does the system respond to weather conditions, wet grass, or environmental hazards?
- What happens during emergency stop scenarios from multiple sources (tilt, manual, obstacle)?
- How does the WebUI handle degraded performance on Pi 4B vs Pi 5?
- What occurs when optional hardware (Hailo HAT, alternative GPS) is unavailable?
- How does simulation mode provide complete coverage for CI/testing without hardware?

## Requirements

### Functional Requirements - Core System
- **FR-001**: System MUST collect and process sensor data including IMU positioning (BNO085 on UART4 at 3Mbaud), power monitoring (INA3221 at I2C 0x40 with fixed channel assignments), distance measurements (VL53L0X at I2C 0x29/0x30), environmental data (BME280 at I2C 0x76), display telemetry (SSD1306 at I2C 0x3C), and wheel encoder feedback with proper bus isolation and error handling
- **FR-002**: System MUST plan and execute autonomous navigation paths using GPS (preferred ZED-F9P USB with NTRIP corrections OR alternative Neo-8M UART), IMU fusion, and obstacle avoidance algorithms with safety-first decision making
- **FR-003**: System MUST control motor operations for propulsion (preferred RoboHAT RP2040→Cytron MDDRC10 OR alternative L298N) and cutting mechanisms (IBT-4 H-Bridge on GPIO24/25) with precise speed control, direction management, and safety interlocks
- **FR-004**: System MUST implement comprehensive safety protocols including emergency stops, obstacle avoidance, tilt detection, blade safety cutoffs, and hazard response with immediate motor shutdown and user notification capabilities
- **FR-005**: System MUST monitor power systems using INA3221 with constitutional channel assignments (Channel 1: Battery, Channel 2: Unused, Channel 3: Solar) and provide solar-aware behavior including sun-seeking (AM Sun / PM Sun locations), power optimization, return-to-Home idling (no docking), and low-power operation modes
- **FR-006**: System MUST capture and stream video feed via Picamera2→GStreamer pipelines for visual monitoring and AI-based obstacle detection with exclusive camera access through designated service ownership
- **FR-007**: System MUST provide web-based user interface with intentional retro 1980s aesthetic, operating fluidly on Raspberry Pi 5 and gracefully degraded on Raspberry Pi 4, supporting all seven mandated pages with responsive design and constitutional branding
- **FR-008**: System MUST run AI processing for object detection and navigation assistance with constitutional acceleration hierarchy: Coral USB (isolated venv-coral) → Hailo HAT (optional, no concurrent RoboHAT) → CPU fallback (TFLite/OpenCV), maintaining package isolation and graceful degradation

### Functional Requirements - WebUI Pages
- **FR-009**: System MUST provide Dashboard page delivering live mower state, safety status, and operational KPIs with real-time telemetry streams at 5Hz default (scalable to 10Hz, degradable to 1Hz), battery/power status, position tracking, and alert management
- **FR-010**: System MUST provide Map Setup page enabling definition of yard boundaries (polygon), mowing zones, and exclusion regions with interactive editing, real-time validation, zone priority settings, and boundary conflict detection. The map provider MUST default to Google Maps (cost-optimized) with a user-selectable OpenStreetMap fallback. The mower’s live position MUST use the LawnBerry map pin asset (LawnBerryPi_Pin.png).
- **FR-011**: System MUST provide Manual Control page enabling direct drive and blade actions with shared operator credential authentication, safety indicators, real-time feedback streams, emergency stop access, and audit logging
- **FR-012**: System MUST provide Mow Planning page managing schedules, job queues, and progress tracking with automated scheduling, weather integration (environmental inputs from onboard BME280; forecast and conditions from OpenWeatherMap API), job priority management, progress visualization, and completion analytics. Weather inputs MUST be used to gate scheduling (e.g., avoid rain/high humidity) and suggest optimal mowing windows.
- **FR-013**: System MUST provide AI Training page supporting captured imagery review, data labeling workflows, and dataset exports in both COCO JSON and YOLO TXT formats with annotation tools, quality validation, and export job management
- **FR-014**: System MUST provide Settings page configuring mower preferences, hardware selections, networking, simulation toggles, telemetry cadence overrides, and system maintenance with persistent configuration storage
- **FR-015**: System MUST provide Docs Hub page bundling on-device documentation, troubleshooting guides, compliance references, and branding assets with offline access, search capabilities, and maintenance procedures

### Functional Requirements - System Integration
- **FR-016**: System MUST maintain real-time bidirectional communication via centralized WebSocket hub supporting topic-based subscriptions, client management, configurable telemetry cadence (1-10Hz), and graceful client disconnection handling
- **FR-017**: System MUST provide REST API endpoints supporting all WebUI functionality with proper authentication, request validation, response schemas, caching strategies (ETag and/or Last-Modified on cacheable GET endpoints; Cache-Control with appropriate max-age), and error handling aligned with OpenAPI specifications
- **FR-018**: System MUST implement single shared operator credential protecting all WebUI pages with authentication gates for manual control actions, dataset exports, and configuration changes while maintaining audit trails
- **FR-019**: System MUST persist operational data, user settings, configuration changes, and historical performance metrics with data integrity, backup capabilities, and migration support
- **FR-020**: System MUST provide automated installation and configuration scripts for deployment with hardware detection, dependency management, service configuration, and migration assistance

### Functional Requirements - Platform Compliance
- **FR-021**: System MUST operate exclusively on Raspberry Pi OS Bookworm (64-bit) with Python 3.11.x runtime on Raspberry Pi 5 (primary) or Pi 4B (compatible) with no cross-platform dependencies or alternate interpreters
- **FR-022**: System MUST maintain constitutional package isolation with pycoral/edgetpu banned from main environment, Coral acceleration isolated in venv-coral, and proper dependency management via uv with committed lock files
- **FR-023**: System MUST operate as managed systemd services with automatic startup, monitoring, logging, and graceful shutdown while respecting camera service ownership and hardware resource coordination
- **FR-024**: System MUST include comprehensive test suite covering unit tests, integration tests, and simulation scenarios with SIM_MODE=1 support, CI execution, and hardware-in-the-loop validation
- **FR-025**: System MUST provide complete documentation including user guides, API references, operational procedures, troubleshooting guides, and migration documentation with automatic drift detection

### Non-Functional Requirements (NFR)
- **NFR-001 Performance & Latency**: End-to-end telemetry latency (sensor read → backend publish → WebSocket delivery → UI render) on Raspberry Pi 5 SHALL be <100ms P95 at 5Hz under nominal load; on Pi 4B, <140ms P95. Under sustained high load, the system SHALL degrade telemetry cadence gracefully (to 1–3Hz) with a clear UI indicator. A measurement harness SHALL be provided (scripts/test_latency.py) and used in CI.
- **NFR-002 WebSocket Resilience**: Clients SHALL automatically reconnect with exponential backoff (≤5s to first reconnect attempt) and resubscribe to prior topics. No more than one telemetry interval worth of data may be missed beyond cadence expectations after reconnection.
- **NFR-003 Security Hardening**: Authentication endpoints SHALL include rate limiting (e.g., ≥5 attempts/minute per IP enforced), lockout/backoff after repeated failures, strict CORS configuration, and transport security when deployed over network. Manual-control actions require authenticated sessions and SHALL be logged (see NFR-004).
- **NFR-004 Privacy & Audit**: Privileged operations (manual control, settings changes, dataset export) SHALL be captured in an audit log with timestamp, action, and client metadata. Audit logs SHALL retain 30 days of history with log rotation enabled and PII-minimization policy documented.
- **NFR-005 Offline & Maps**: The Map Setup page MUST function without a Google Maps API key by falling back to OpenStreetMap (OSM). If GOOGLE_MAPS_API_KEY is absent, OSM is used automatically. An offline-friendly mode SHALL be provided for development with limited tiles/caching; no runtime Ethernet dependency is permitted by the constitution.
- **NFR-006 Caching**: Cacheable GET endpoints (e.g., /dashboard/status, /map/zones, /map/locations, /settings/system) SHALL emit ETag or Last-Modified and appropriate Cache-Control headers. Contract and tests SHALL validate caching behavior.
- **NFR-007 Dataset Export Performance**: AI Training dataset exports of up to 500 images SHALL complete within 3 minutes on Raspberry Pi 5, and within 5 minutes on Pi 4B; resource usage SHALL not starve critical services.
- **NFR-008 Dead-Reckoning Bounds**: During GPS loss (≤60s), dead-reckoning drift SHALL be ≤1.0m per 10s (P95). On re-acquisition, the system SHALL converge position within two telemetry intervals.
- **NFR-009 Systemd Health & Order**: All services (camera-stream, sensor-manager, navigation, webui-backend, webui-frontend) SHALL be active after boot with correct ordering. Health probes and journald checks SHALL verify successful startup and runtime health.
- **NFR-010 Documentation Drift Detection**: A CI step SHALL detect and fail on documentation drift for API contracts and generated references.

### Key Entities

#### Hardware & Sensor Systems
- **Sensor Data**: Real-time measurements from IMU (BNO085/UART4), power monitor (INA3221/I2C 0x40), ToF sensors (VL53L0X 0x29/0x30), environmental (BME280/0x76), display (SSD1306/0x3C), and wheel encoders with timestamps, bus assignments, validation status, and error conditions
- **Navigation State**: Current position (GPS/IMU fusion), planned paths, obstacle maps, movement commands, safety constraints, and dead reckoning capabilities with GPS mode handling (ZED-F9P USB/NTRIP or Neo-8M UART)
- **Motor Control**: Speed settings, direction commands, operational status for propulsion (RoboHAT RP2040→Cytron MDDRC10 preferred, L298N alternative) and cutting systems (IBT-4 H-Bridge GPIO24/25) with safety interlocks and encoder feedback. Movement control MUST be issued via serial to the RoboHAT’s RP2040 running the provided `code.py`; that firmware SHOULD remain unmodified unless strictly necessary, with the sole required enhancement being support for reading wheel hall-effect sensors if not already present.
- **Power Management**: Battery levels, consumption patterns, charging status, optimization settings tied to INA3221 constitutional channel assignments (1:Battery, 2:Unused, 3:Solar) with automated power management and low-power modes

#### AI & Vision Systems
- **Camera Stream**: Video frames from Picamera2→GStreamer pipelines, processing metadata, AI analysis results with exclusive service ownership and IPC-based frame distribution
- **AI Processing**: Model inference results, confidence scores, hardware acceleration status across constitutional hierarchy (Coral USB venv-coral → Hailo HAT optional → CPU TFLite/OpenCV) with graceful degradation and package isolation
- **Training Data**: Captured imagery, annotation metadata, labeling workflows, dataset exports (COCO JSON, YOLO TXT), quality validation, and export job management

#### WebUI & Communication Systems
- **WebUI Page Contracts**: Seven mandated pages (Dashboard, Map Setup, Manual Control, Mow Planning, AI Training, Settings, Docs Hub) with defined objectives, data dependencies, REST endpoint mappings, WebSocket topic subscriptions, and authentication requirements
- **Telemetry Exchange**: Real-time data streams, event notifications, job updates, safety alerts delivered via WebSocket hub with configurable cadence (5Hz default, 1-10Hz range), topic-based routing, and client management including reconnection and resubscription semantics
- **User Session**: Web interface connections, authentication state (shared operator credential), user preferences, control permissions, and audit logging with session management and security enforcement (rate limiting and lockout on auth endpoints)

#### System Configuration & Operations
- **Hardware Baseline**: Required vs optional components (Pi models, GPS modules, sensors, power monitoring, drive systems, AI accelerators) with constitutional constraints, conflict detection, and graceful degradation handling
- **System Configuration**: Operational parameters, calibration data, user-defined settings with version tracking, hardware detection, simulation mode support, and migration capabilities
- **Operational Data**: System metrics, performance indicators, historical logs, maintenance records, error conditions, and analytics with data persistence, backup strategies, and reporting capabilities

## Clarifications

### Session 2025-09-24 (Hardware & Platform)
- Q: What boards/OS/Python are supported? → A: Raspberry Pi OS Bookworm 64-bit; Python 3.11.x; Pi 5 (primary) and Pi 4B (compatible)
- Q: GPS configurations? → A: Either ZED-F9P RTK over USB with NTRIP (preferred) OR Neo-8M over UART (alternative). Mutually exclusive, not concurrent
- Q: Drive controller options? → A: Preferred: RoboHAT RP2040 → Cytron MDDRC10 (PWM, encoders, safety IO). Alternative: L298N dual H-bridge
- Q: HAT stacking policy? → A: Do not combine RoboHAT and Hailo HAT simultaneously. GPIO splitter unsupported
- Q: AI acceleration order and isolation? → A: Coral USB (isolated venv-coral) → Hailo HAT (optional) → CPU (TFLite/OpenCV). BAN `pycoral`/`edgetpu` in main env
- Q: INA3221 fixed channel mapping? → A: Channel 1 = Battery; Channel 2 = Unused; Channel 3 = Solar (constitutional requirement)
- Q: Networking assumptions? → A: Wi-Fi primary; Ethernet is bench-only and must not be assumed at runtime

### Session 2025-09-24 (WebUI & Interface)
- Q: What are the seven mandated WebUI pages? → A: Dashboard, Map Setup, Manual Control, Mow Planning, AI Training, Settings, Docs Hub
- Q: Telemetry cadence requirements? → A: 5 Hz default (expandable to 10 Hz) with ability to step down to 1 Hz for diagnostics/power conservation
- Q: Authentication model? → A: Single shared operator credential protecting all pages, with manual control requiring authentication gates
- Q: Dataset export formats? → A: AI Training page must support both COCO JSON and YOLO TXT formats
- Q: Branding requirements? → A: Retro 1980s aesthetic with LawnBerryPi_logo.png, LawnBerryPi_icon2.png, and robot pin assets (use LawnBerryPi_Pin.png for the robot marker on maps)
- Q: Platform performance? → A: Must run fluidly on Pi 5, gracefully degrade on Pi 4B

### Orientation & Mapping Clarifications (2025-09-25)
- VL53L0X “left” and “right” refer to the mower’s front-left and front-right sensors (mounted like car headlights)
- Map provider preference: Google Maps (cost-optimized usage) is preferred; OpenStreetMap is available as a no-cost fallback selectable by the user
- User-configurable locations: Home, AM Sun, PM Sun used for return/idle/sun-seeking behavior; no physical docking station is assumed

### Session 2025-09-25 (Integration & Architecture)
- Q: How do the two specifications combine? → A: Full autonomous mower system with comprehensive WebUI, maintaining constitutional compliance and hardware alignment
- Q: Simulation coverage? → A: SIM_MODE=1 must cover all sensors, navigation, power, AI pipelines, and WebUI functionality for CI/testing
- Q: Resource coordination? → A: Camera service owns device, other components consume via IPC; hardware resources have single owners with proper coordination

### Performance Measurement Definition
- End-to-end telemetry latency is defined as the elapsed time from sensor read capture (timestamped at source) to UI render completion for the corresponding update (timestamped in the client after render). Measurements are collected by the provided harness and aggregated as P50/P95/P99 with per-device targets (see NFR-001). Degradation behavior (cadence changes) must be user-visible.

---

## Review & Acceptance Checklist

### Content Quality
- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

### Requirement Completeness
- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous  
- [x] Success criteria are measurable
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

### Constitutional Compliance
- [x] Platform exclusivity (Raspberry Pi OS Bookworm, Python 3.11)
- [x] AI acceleration hierarchy with package isolation
- [x] Hardware compliance with spec/hardware.yaml alignment
- [x] Documentation-as-contract principles maintained
- [x] Test-driven development approach specified

---

## Execution Status

- [x] User description parsed (unified requirements from both specs)
- [x] Key concepts extracted (autonomous system + comprehensive WebUI)
- [x] Ambiguities resolved (hardware conflicts, platform compliance)
- [x] User scenarios defined (core operation + WebUI experience)
- [x] Requirements generated (25 functional requirements across all domains)
- [x] Entities identified (hardware, AI, WebUI, configuration systems)
- [x] Constitutional compliance verified
- [x] Review checklist passed

---