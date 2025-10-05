# Feature Specification: Run on real hardware (no SIM)

**Feature Branch**: `003-add-finish-all`  
**Created**: 2025-10-05  
**Status**: Draft  
**Input**: User description: "Add/finish all hardware code so this program can be run outside of SIM mode. This includes roboHAT/MDDRC10 drive motor control, IBT-4 Blade control, BNO085 IMU, 2x VL53L0X ToF sensors, BME280, RTK-9FP, Pi Camera v2, hall sensors via roboHAT, INA3221, and Google Coral USB accelerator on Raspberry Pi 5. Ensure frequent grounding to avoid hallucinations. Ready for Web UI and CLI operation."

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

### Section Requirements
- **Mandatory sections**: Must be completed for every feature
- **Optional sections**: Include only when relevant to the feature
- When a section doesn't apply, remove it entirely (don't leave as "N/A")

### For AI Generation
When creating this spec from a user prompt:
1. **Mark all ambiguities**: Use [NEEDS CLARIFICATION: specific question] for any assumption you'd need to make
2. **Don't guess**: If the prompt doesn't specify something (e.g., "login system" without auth method), mark it
3. **Think like a tester**: Every vague requirement should fail the "testable and unambiguous" checklist item
4. **Common underspecified areas**:
   - User types and permissions
   - Data retention/deletion policies  
   - Performance targets and scale
   - Error handling behaviors
   - Integration requirements
   - Security/compliance needs

---

## User Scenarios & Testing *(mandatory)*

### Primary User Story
As an operator using a Raspberry Pi 5–powered LawnBerry mower, I want to run the system with real hardware (not simulation) so that I can drive, mow, and monitor the mower via the Web UI and CLI with reliable, safety‑enforced behavior.

### Acceptance Scenarios
1. **Given** the mower is powered on with all listed hardware connected, **When** I start the backend and frontend and open the Web UI, **Then** I can enable motors, drive forward/backward/turn, and see live camera and key telemetry (GPS, IMU tilt, ToF distances, battery/solar power).
2. **Given** the blade is off, **When** I enable the blade in the UI with safety conditions satisfied (no excessive tilt, adequate voltage), **Then** the blade engages and can be stopped from the UI or by emergency stop.
3. **Given** the mower is driving, **When** a tilt exceeds 30 degrees or an obstacle is detected within 0.18 m by any ToF, **Then** the system immediately (≤200 ms) stops the blade and commands motor stop.
4. **Given** the system is in real (non‑SIM) mode, **When** the Google Coral accelerator is connected, **Then** AI processing status reports Coral as the active accelerator; when absent, **Then** system continues without blocking mower operation.
5. **Given** hall sensors are connected to RoboHAT, **When** the mower moves 1 m forward on level ground, **Then** encoder feedback reflects expected tick counts and the UI shows motion updates.

### Edge Cases
- Loss of any single sensor (e.g., one ToF or IMU) must degrade gracefully and preserve safe operation (blade inhibited if tilt unknown).
- GPS not fixed (no RTK) must not block manual driving but should show reduced accuracy.
- Low battery voltage threshold must inhibit blade and alert the operator.
- Serial or I2C bus busy conditions must not freeze control loops; commands must still time out to stop motors.
- Camera unavailable should not block the rest of the system; the UI shows a camera error but control remains available.

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: The system MUST operate outside simulation mode by default when running on deployed hardware (Raspberry Pi 5).
- **FR-002**: The operator MUST be able to drive the mower (differential drive) via Web UI and CLI with latency suitable for manual control.
- **FR-003**: The blade motor MUST be controllable (enable/disable) via Web UI and CLI, subject to safety interlocks.
- **FR-004**: The system MUST read live telemetry from: IMU (tilt/yaw), ToF distance sensors (two units, left/right), environmental (temperature, humidity, pressure), GPS (u‑blox RTK‑capable), power (battery and solar via INA3221), hall sensors (wheel encoders), and camera.
- **FR-005**: Safety MUST cut blade power within 200 ms when tilt exceeds 30° roll or pitch, on obstacle within 0.18 m, or on emergency stop activation.
- **FR-006**: The system MUST gracefully degrade when any sensor is unavailable (missing, unplugged, driver error) and MUST log the condition visibly in the UI.
- **FR-007**: The system MUST allow operation when the Google Coral accelerator is absent and MUST automatically use it when present.
- **FR-008**: The operator MUST be able to see real‑time camera stream and essential telemetry values in the Web UI.
- **FR-009**: The CLI MUST support commands to start/stop motors, engage/disengage blade, perform emergency stop, and query health/telemetry.
- **FR-010**: The system MUST provide a health status endpoint that reflects connectivity to RoboHAT/MDDRC10, IMU, ToF x2, BME280, GPS (RTK‑9FP), INA3221, camera, Coral.
- **FR-011**: Hall sensor feedback (encoders) MUST update while driving and be exposed for UI display and navigation.
- **FR-012**: Configuration MUST allow selecting real hardware vs. simulation explicitly and per‑component overrides.
- **FR-013**: Logs MUST record hardware faults, safety interlocks, and operator actions for later review.
- **FR-014**: The mower MUST fail safe: on hardware or software fault, motors and blade are stopped.
- **FR-015**: The system MUST present clear operator messages to avoid misinterpretation, with frequent explicit grounding (e.g., "No IMU data; blade disabled").

*Examples of unclear details to confirm:*
- **FR-016**: System MUST define exact low‑voltage thresholds and hysteresis for blade inhibit [NEEDS CLARIFICATION: exact voltage/current thresholds requested?].
- **FR-017**: System MUST define required GPS fix quality to allow autonomous features [NEEDS CLARIFICATION: is manual only sufficient for this scope?].
- **FR-018**: System MUST define acceptable command latency targets for drive and blade control [NEEDS CLARIFICATION: target ms?].

### Key Entities *(include if feature involves data)*
- **Operator session**: User interaction context via Web UI/CLI.
- **Hardware telemetry**: Structured data for GPS, IMU, ToF (left/right), environment, power, encoders, camera status.
- **Safety interlocks**: Emergency stop state, tilt cutoff, obstacle inhibit, low‑voltage inhibit.

---

## Review & Acceptance Checklist
*GATE: Automated checks run during main() execution*

### Content Quality
- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

### Requirement Completeness
- [ ] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous  
- [x] Success criteria are measurable
- [x] Scope is clearly bounded to run outside SIM mode with listed hardware
- [x] Dependencies and assumptions identified

---

## Execution Status
*Updated by main() during processing*

- [x] User description parsed
- [x] Key concepts extracted
- [x] Ambiguities marked
- [x] User scenarios defined
- [x] Requirements generated
- [x] Entities identified
- [ ] Review checklist passed

---
