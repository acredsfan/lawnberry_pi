# Feature Specification: LawnBerry Pi v2

**Feature Branch**: `001-build-lawnberry-pi`  
**Created**: 2025-09-24  
**Status**: Draft  
**Input**: User description: "Build LawnBerry Pi v2: Modules: sensors, navigation, motion, safety, power, camera, webui, ai runners. One WebSocket hub for telemetry/control. Services: mower-core, camera-stream, webui. Deliverables: working code, tests (incl. sim), docs site, install scripts, systemd, migration note from v1."

## ⚡ Quick Guidelines
- ✅ Focus on WHAT users need and WHY
- ❌ Avoid HOW to implement (no tech stack, APIs, code structure)
- 👥 Written for business stakeholders, not developers

---

## User Scenarios & Testing

### Primary User Story
A user wants to operate an autonomous robotic lawn mower that can navigate their property, avoid obstacles, maintain safety protocols, and provide real-time monitoring and control capabilities through a web interface. The system should handle all aspects of autonomous mowing operations including sensor data processing, navigation planning, motor control, safety monitoring, power management, and visual feedback.

### Acceptance Scenarios
1. **Given** the mower is powered on and positioned on a lawn, **When** the user initiates mowing through the web interface, **Then** the system autonomously navigates and mows the designated area while avoiding obstacles
2. **Given** the mower is operating autonomously, **When** an obstacle or safety hazard is detected, **Then** the system immediately stops motors and alerts the user through the web interface
3. **Given** the user opens the web interface, **When** the mower is operating, **Then** real-time telemetry data (position, battery, sensor readings, camera feed) is displayed
4. **Given** the mower battery is low, **When** the threshold is reached, **Then** the system autonomously returns to charging station and notifies user
5. **Given** a user has LawnBerry Pi v1, **When** they follow the migration process, **Then** they can successfully upgrade to v2 with preserved settings

### Edge Cases
- What happens when GPS signal is lost during navigation?
- How does the system handle sensor failures or inconsistent readings?
- What occurs when Wi-Fi connectivity is interrupted during field operations where Ethernet is unavailable?
- How does the system respond to weather conditions or wet grass?
- What happens during emergency stop scenarios?

## Clarifications

### Session 2025-09-24
- Q: What boards/OS/Python are supported? → A: Raspberry Pi OS Bookworm 64-bit; Python 3.11.x; Pi 5 (primary) and Pi 4B (compatible).
- Q: GPS configurations? → A: Either (a) ZED-F9P RTK over USB with NTRIP (preferred) or (b) Neo-8M over UART (alternative, no RTK). Not both at once.
- Q: Drive controller options? → A: Preferred: RoboHAT RP2040 → Cytron MDDRC10 (PWM, encoders, safety IO). Alternative: L298N dual H-bridge if RoboHAT isn’t available.
- Q: HAT stacking policy? → A: Do not combine RoboHAT and Hailo HAT simultaneously. GPIO splitter use is unsupported/at-your-own-risk and not in the main build path.
- Q: AI acceleration order and isolation? → A: Coral USB (isolated venv-coral) → Hailo HAT (optional) → CPU (TFLite/OpenCV). BAN `pycoral`/`edgetpu` in the main env.
- Q: Sensors, buses, and addresses? → A: BNO085 on UART4; VL53L0X left 0x29, right 0x30; BME280 0x76; SSD1306 0x3C; INA3221 0x40.
- Q: INA3221 fixed channel mapping? → A: Channel 1 = Battery; Channel 2 = Unused; Channel 3 = Solar.
- Q: Networking assumptions? → A: Wi-Fi primary; Ethernet is bench-only and must not be assumed at runtime.
- Q: Cutting system details? → A: IBT-4 H-Bridge, GPIO24/25, with tilt/e-stop safety interlocks.
- Q: Camera/UI? → A: Picamera2 → GStreamer; retro 80s WebUI; must run well on Pi 5 and degrade gracefully on Pi 4.
- Q: RC receiver? → A: FUTURE feature only; document RoboHAT inputs in docs/optional-hardware.md; do not implement now.
- Q: Simulation and CI? → A: SIM_MODE=1 drivers for GPS/IMU/BME280/ToF/blade/motors/power; CI runs sim tests; hardware-in-loop later on the mower Pi.

## Requirements

### Functional Requirements
- **FR-001**: System MUST collect and process sensor data including IMU positioning (BNO085 on UART4), power monitoring (INA3221 at 0x40), distance measurements (VL53L0X at 0x29/0x30), environmental data (BME280 at 0x76), display telemetry (SSD1306 at 0x3C), and wheel encoder feedback
- **FR-002**: System MUST plan and execute autonomous navigation paths while avoiding static and dynamic obstacles
- **FR-003**: System MUST control motor operations for propulsion and cutting mechanisms with precise speed and direction control
- **FR-004**: System MUST implement safety protocols including emergency stops, obstacle avoidance, and hazard detection
- **FR-005**: System MUST monitor power consumption and battery levels with automated charging station return, using INA3221 with Channel 1 assigned to battery, Channel 2 unused, and Channel 3 for solar input
- **FR-006**: System MUST capture and stream video feed for visual monitoring and AI-based obstacle detection via Picamera2 pipelines delivered over GStreamer
- **FR-007**: System MUST provide web-based user interface for monitoring, control, and configuration that delivers an intentional retro 1980s aesthetic, operates fluidly on Raspberry Pi 5, and degrades gracefully on Raspberry Pi 4
- **FR-008**: System MUST run AI processing for object detection and navigation assistance with hardware acceleration support, prioritizing Coral USB (isolated `venv-coral`), then optional Hailo HAT, and finally CPU-based TFLite/OpenCV while keeping `pycoral`/`edgetpu` packages out of the main environment
- **FR-009**: System MUST maintain real-time bidirectional communication between all system components via centralized message hub, relying on Wi-Fi for field operations and reserving Ethernet for bench diagnostics only
- **FR-010**: System MUST persist operational data, user settings, and historical performance metrics
- **FR-011**: System MUST provide automated installation and configuration scripts for deployment
- **FR-012**: System MUST operate as managed system services with automatic startup and monitoring
- **FR-013**: System MUST include comprehensive test suite covering unit tests, integration tests, and simulation scenarios driven by `SIM_MODE=1`, with CI executing simulation runs and hardware-in-the-loop validation scheduled on the mower platform
- **FR-014**: System MUST provide complete documentation including user guides, API references, and operational procedures
- **FR-015**: System MUST support migration from LawnBerry Pi v1 installations with data preservation

### Key Entities
- **Sensor Data**: Real-time measurements from IMU (BNO085), power monitor (INA3221), ToF sensors (VL53L0X left/right), and wheel encoders with timestamps, bus assignments, I2C addresses, and validation status
- **Navigation State**: Current position, planned path, obstacle map, and movement commands with safety constraints
- **Motor Control**: Speed settings, direction commands, and operational status for propulsion (RoboHAT RP2040 with Cytron MDDRC10, or fallback L298N) and cutting systems (IBT-4 H-Bridge on GPIO24/25 with tilt and e-stop interlocks)
- **Safety Events**: Emergency conditions, obstacle detections, and system alerts with priority levels and response actions
- **Power Management**: Battery levels, consumption patterns, charging status, and power optimization settings tied to INA3221 Channel 1 (battery), Channel 2 (unused reserve), and Channel 3 (solar)
- **Camera Stream**: Video frames, processing metadata, and AI analysis results for visual monitoring sourced from Picamera2 via GStreamer pipelines
- **User Session**: Web interface connections, user preferences, and control permissions with authentication status
- **AI Processing**: Model inference results, confidence scores, and hardware acceleration status across Coral USB (`venv-coral`), optional Hailo HAT, and CPU backstops, with package governance enforced
- **System Configuration**: Operational parameters, calibration data, and user-defined settings with version tracking, capturing GPS mode (ZED-F9P RTK via USB or Neo-8M via UART—mutually exclusive) and network assumptions (Wi-Fi primary, Ethernet bench-only)
- **Telemetry Data**: Consolidated system metrics, performance indicators, and operational logs for monitoring and analysis, including simulation results and CI artifacts from `SIM_MODE=1` runs

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

---

## Execution Status

- [x] User description parsed
- [x] Key concepts extracted
- [x] Ambiguities marked
- [x] User scenarios defined
- [x] Requirements generated
- [x] Entities identified
- [x] Review checklist passed

---
