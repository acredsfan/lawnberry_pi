# Feature Specification: LawnBerry Pi v2 — Complete Rebuild to Production Operation

**Feature Branch**: `005-complete-the-rebuild`  
**Created**: 2025-09-27  
**Status**: Draft  
**Input**: User description: "Complete the rebuild. Get all hardware and systems working outside of simulation mode, complete web UI build out including the lawnberry branding with the 80's techno theme and coloring based on LawnBerryPi_logo.png and LawnBerryPi_icon2.png, ensure all parts of the UI work: Dashboard (all mower telemetry), Map Setup (lawn boundaries, no-go zones, Home, AM Sun, PM Sun with Google Maps default + OSM fallback and LawnBerryPi_Pin.png marker), Mow Planning/scheduling, Settings, AI Training, Docs Hub. Provide full installation/setup/run user documentation for the mower program per spec.md and constitution v1.2.0, hardware.yaml, Pi OS Bookworm, Python 3.11, systemd services, SIM_MODE and real hardware operation."

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
- ❌ Avoid HOW to implement (no low-level tech stack, APIs, code structure)
- 👥 Written for business stakeholders, not developers

### Section Requirements
- Mandatory sections below are completed
- Optional sections are included only when relevant

### For AI Generation
This specification is derived from the user prompt and prior unified specification. No ambiguities that block execution remain at this time.

---

## Clarifications

### Session 2025-09-27
- Q: What’s the intended network exposure for the WebUI, REST API, and WebSocket hub? → A: C — Remote access supported out of the box (built-in secure exposure), configurable.
- Q: Authentication strength for the single shared operator credential? → A: D — Password + TOTP + backup codes.
- Q: Map provider cost control strategy? → A: C — Adaptive usage (reduced tiles/frequency) before fallback to OSM.

---

## User Scenarios & Testing (mandatory)

### Primary User Story
A homeowner operates an autonomous robotic lawn mower through a web interface that provides real-time monitoring, manual control, autonomous planning, AI-powered obstacle awareness, and system configuration. The system must run on supported LawnBerry hardware and complete mowing safely and efficiently while offering clear visual feedback and robust safeguards.

### Acceptance Scenarios
1. Given the mower is powered and on a lawn, When the user starts mowing from the web interface, Then the mower autonomously navigates and mows designated areas while honoring safety and zone constraints.
2. Given autonomous operation is in progress, When an obstacle or safety hazard is detected, Then motors stop immediately, safety protocols activate, and the user is alerted with specific hazard information.
3. Given the battery is low, When power management engages, Then the mower navigates to the most appropriate location by time-of-day (AM Sun or PM Sun) or to Home otherwise, and the user is notified of charge/idle status (no docking station assumed).
4. Given the user opens the Dashboard, When the mower is operating, Then live telemetry (position, battery, sensors, safety state, camera feed) is shown with <100ms latency at 5 Hz default cadence.
5. Given the user accesses Manual Control with authentication, When drive/blade commands are issued, Then the mower responds immediately with visual feedback and safety overrides.
6. Given the user configures Map Setup, When lawn boundaries, exclusion zones, Home, AM Sun, and PM Sun are defined via polygon editing, Then the system validates and updates navigation parameters in real time. The live mower position uses the LawnBerry map pin asset.
7. Given the user schedules jobs in Mow Planning, When jobs are queued/executed, Then live progress and zone-specific status with estimated completion times are shown.
8. Given the user manages AI Training, When imagery is reviewed and labeled, Then dataset exports are produced in COCO JSON and YOLO TXT formats.
9. Given the mower is running on supported Raspberry Pi hardware, When hardware detection runs, Then sensors, GPS, and motor controllers are correctly identified and configured according to constitution and hardware.yaml.
10. Given multiple clients are connected to the web interface, When telemetry is streamed, Then the system maintains bidirectional communication with topic subscriptions and configurable cadence without impacting control responsiveness.
11. Given Wi‑Fi connectivity is interrupted, When the mower is operating, Then safety is preserved, control degrades gracefully, and the UI indicates connectivity loss and recovery.
12. Given wet/unsafe conditions are detected, When mowing is active or scheduled, Then the mower delays or pauses operations and informs the user with clear recommendations.
13. Given the rebuild has passed all tests and reviews, When the release is approved, Then the repository mainline is cut over to this complete rebuild, replacing the original build with documented migration and rollback provisions.

### Edge Cases
- GPS signal loss during navigation (fall back to dead reckoning while maintaining safety)
- Sensor failure or inconsistent readings (degrade safely and notify)
- Wi‑Fi interruptions during field operation (no Ethernet assumption)
- Wet grass or environmental hazards (pause/delay/avoid)
- Emergency stop from multiple sources (tilt/manual/obstacle) with consistent priority
- Performance differences between Pi 5 and Pi 4B (graceful degradation)
- Optional hardware absent (Hailo HAT, alternative GPS) with graceful fallback
- Simulation mode vs real hardware (consistent behavior with SIM_MODE off)

## Requirements (mandatory)

### Functional Requirements
- FR-001: System MUST collect and process sensor data for IMU positioning, power monitoring, distance sensing, environmental readings, display telemetry, and wheel encoder feedback with bus isolation and robust error handling.
- FR-002: System MUST plan and execute autonomous paths using GPS + IMU fusion and obstacle avoidance with safety-first decisions.
- FR-003: System MUST control propulsion and cutting mechanisms with precise speed/direction control and safety interlocks.
- FR-004: System MUST implement comprehensive safety protocols including emergency stops, tilt detection, obstacle avoidance, and hazard response with immediate motor shutdown and user notification.
- FR-005: System MUST monitor power via INA3221 with constitutional channel assignments (1: Battery, 2: Unused, 3: Solar) and support sun-seeking (AM/PM Sun), return-to-Home idling, and low-power modes.
- FR-006: System MUST capture/stream camera video for monitoring and AI detection with single service ownership and safe sharing.
- FR-007: System MUST provide a web UI with LawnBerry branding and retro 1980s aesthetic, running fluidly on Pi 5 and gracefully on Pi 4B, covering seven mandated pages with responsive design.
- FR-008: System MUST run AI object detection with acceleration hierarchy (Coral USB → Hailo HAT → CPU) and maintain package isolation and graceful degradation.
- FR-009: System MUST provide a Dashboard with live state, safety status, KPIs, real-time telemetry streams (default 5 Hz, 1–10 Hz configurable), battery/power status, position tracking, and alert management.
- FR-010: System MUST provide Map Setup enabling boundaries, zones, and exclusion regions with interactive editing, validation, zone priorities, and conflict detection. Google Maps is preferred with OSM fallback; implement adaptive usage (reduced tiles/frequency) to control costs and automatically fallback to OSM upon threshold. Live position uses the LawnBerry pin asset. Google Maps usage requires a user-supplied API key.
- FR-011: System MUST provide Manual Control with authentication, safety indicators, live feedback, emergency stop access, and audit logging.
- FR-012: System MUST provide Mow Planning with schedules, job queues, live progress, completion estimates, and historical insights.
- FR-013: System MUST provide AI Training workflows, annotation tools, quality checks, and exports in both COCO JSON and YOLO TXT formats.
- FR-014: System MUST provide Settings for hardware preferences, networking, simulation toggles, telemetry cadence overrides, and maintenance; configuration persists.
- FR-015: System MUST provide a Docs Hub bundling on-device documentation, troubleshooting, compliance references, branding assets, and offline access with search.
- FR-016: System MUST maintain a centralized WebSocket hub for real-time bidirectional communication with topic-based subscriptions and client management.
- FR-017: System MUST expose REST endpoints supporting all WebUI capabilities with authentication, validation, schemaed responses, caching, and robust error handling.
- FR-018: System MUST implement a single shared operator credential protected by MFA (password + TOTP + backup codes) to gate manual control, dataset exports, and configuration changes, with audit logging.
- FR-019: System MUST persist operational data, settings, configuration changes, and historical performance with integrity, backup, and migration support.
- FR-020: System MUST provide automated install/config scripts for deployment with hardware detection, dependencies, service configuration, and migration assistance.
- FR-021: System MUST operate on supported Raspberry Pi OS and hardware with Python runtime versions aligned to constitution; no cross-platform dependencies.
- FR-022: System MUST maintain constitutional package isolation; Coral-related packages remain isolated from the main environment.
- FR-023: System MUST run as managed services with automatic startup, monitoring, logging, and graceful shutdown; respect single-owner hardware coordination.
- FR-024: System MUST include a comprehensive test suite covering unit, integration, and simulation scenarios (SIM_MODE=1) plus real hardware readiness.
- FR-025: System MUST include complete user documentation for installation, setup, operation, maintenance, and migration with drift checks.
- FR-026: System MUST execute a final cutover to replace the original build with this complete rebuild in the repository, including mainline branch cutover, versioned release tags, documented migration steps, and a verified rollback path.
- FR-027: System MUST support built-in secure remote access (configurable) for the WebUI, REST API, and WebSocket hub, aligning with the clarified network exposure.

### Key Entities
- Sensor Data: Real-time measurements with timestamps, bus assignments, validation, and error conditions.
- Navigation State: Current position (fusion), planned paths, obstacle maps, movement commands, safety constraints, and dead reckoning.
- Motor Control: Speed/direction commands and status for propulsion and cutting with interlocks and encoder feedback.
- Power Management: Battery levels, consumption, solar input, optimization settings, and sun-seeking behavior.
- Camera Stream: Video frames, metadata, and AI analysis results with exclusive ownership and shared access via IPC.
- AI Processing: Inference results, confidence scores, acceleration status per hierarchy, and isolation indicators.
- Training Data: Captured imagery, annotations, dataset exports (COCO/YOLO), and export job tracking.
- WebUI & Communication: Page contracts, REST mappings, WebSocket topics, authentication requirements, and audit logging.
- System Configuration: Hardware baseline, operational parameters, calibration data, user-defined settings, version tracking, detection, simulation, and migration.
- Operational Data: Metrics, performance indicators, logs, maintenance records, errors, analytics, backups, and reporting.

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
- [x] Ambiguities marked (none blocking)
- [x] User scenarios defined
- [x] Requirements generated
- [x] Entities identified
- [x] Review checklist passed

---
**Feature Branch**:   
