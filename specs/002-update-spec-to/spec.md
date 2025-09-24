# Feature Specification: WebUI Page & Hardware Alignment Update

**Feature Branch**: `002-update-spec-to`  
**Created**: 2025-09-24  
**Status**: Draft  
**Input**: User description: "Update spec to explicitly list the seven WebUI pages and their goals, require matching REST/WS contracts, and align hardware section with updated hardware.yaml."

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

## User Scenarios & Testing *(mandatory)*

### Primary User Story
Operations staff managing the LawnBerry mower need a single specification that documents every required WebUI page, the data each view must surface, and the matching service contracts and hardware expectations so that development teams can implement and validate the experience without ambiguity. The scope here extends the LawnBerry Pi v2 master specification by explicitly pulling forward the authoritative WebUI, REST/WebSocket, and hardware guidance defined for the overall mower platform.

### Acceptance Scenarios
1. **Given** the specification is reviewed, **When** stakeholders check the WebUI section, **Then** all seven mandated pages (`Dashboard`, `Map Setup`, `Manual Control`, `Mow Planning`, `AI Training`, `Settings`, `Docs Hub`) are called out with their high-level goals.
2. **Given** the specification, **When** backend and QA teams look up service expectations, **Then** the document references REST and WebSocket contracts that must line up with each page's data needs, including the 5–10 Hz telemetry cadence (with downshift capability for diagnostics) documented in the LawnBerry Pi v2 platform plan.
3. **Given** the specification, **When** hardware leads compare platform requirements, **Then** the listed devices, buses, and prioritization rules match the authoritative hardware manifest for the project.

### Edge Cases
- What happens when optional hardware (e.g., alternative GPS or AI accelerator) is unavailable? The spec must describe expected fallbacks while staying faithful to the hardware manifest.
- How does the system handle simulated mode requirements? The spec should confirm simulation coverage for each WebUI view and contract.
- How are conflicting hardware accessories (e.g., Hailo hat with RoboHAT) communicated? The spec must carry over explicit conflict notes from the hardware manifest.

## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: Specification MUST describe the `Dashboard` page goal as delivering live mower state, safety status, and headline KPIs at a glance.
- **FR-002**: Specification MUST describe the `Map Setup` page goal as defining yard boundaries, mowing zones, and exclusion regions, including how changes surface through matching REST and WebSocket updates.
- **FR-003**: Specification MUST describe the `Manual Control` page goal as enabling direct drive and blade actions with safety indicators and observable feedback from real-time streams.
- **FR-004**: Specification MUST describe the `Mow Planning` page goal as managing schedules, job queues, and progress tracking with related data feeds.
- **FR-005**: Specification MUST describe the `AI Training` page goal as reviewing captured imagery, labeling data, and exporting datasets, along with the contracts supporting uploads and approvals.
- **FR-006**: Specification MUST describe the `Settings` page goal as configuring mower preferences, hardware selections, networking, and simulation toggles while calling out required persistence contracts.
- **FR-007**: Specification MUST describe the `Docs Hub` page goal as bundling on-device documentation, troubleshooting, and compliance references consistent with branding requirements.
- **FR-008**: Specification MUST require that each WebUI page references the REST endpoints and WebSocket topics that supply its data, including telemetry broadcasting at a 5 Hz default interval (scalable to 10 Hz under normal operations and degradable to 1 Hz during diagnostics or low-power modes).
- **FR-009**: Specification MUST align hardware details (platform, sensors, controllers, power monitoring, acceleration hierarchy) with the authoritative hardware manifest, including preferred vs. alternative components and any operational constraints or conflicts.
- **FR-010**: Specification MUST restate that simulated operation covers sensors, navigation, power, and AI pipelines so that every listed page and contract can be validated without physical hardware.
- **FR-011**: Specification MUST highlight monitoring expectations for safety-critical data (e.g., INA3221 channel map, emergency stop signals) to ensure UI pages and contracts expose alerts when thresholds are exceeded.
- **FR-012**: Specification MUST require a single shared operator credential protecting all WebUI pages, with authentication gating manual control actions.
- **FR-013**: Specification MUST ensure the AI Training page exports datasets in both COCO JSON and YOLO TXT formats for downstream pipelines.
- **FR-014**: Specification MUST surface mandated retro 1980s branding cues, including use of the LawnBerry Pi logo, icon set, and robot pin assets, across Dashboard, Manual Control, and Docs Hub experiences consistent with the v2 platform story.
- **FR-015**: Specification MUST reiterate that hardware alignment includes immutable INA3221 channel assignments, exclusive GPS mode selection (ZED-F9P USB with NTRIP vs. Neo-8M UART), and motor controller preferences (RoboHAT→Cytron MDDRC10 with L298N fallback) so the WebUI accurately reflects underlying configuration choices.
- **FR-016**: Specification MUST capture the WebUI route mapping (`/dashboard`, `/map-setup`, `/manual`, `/mow-plan`, `/ai-train`, `/settings`, `/docs`) alongside the corresponding REST endpoints (e.g., `/api/telemetry/snapshot`, `/api/map/zones`, `/api/manual/command`, `/api/mow/jobs`, `/api/ai/datasets`, `/api/settings/profile`, `/api/docs/index`) and WebSocket topics (`telemetry/updates`, `map/updates`, `manual/feedback`, `mow/jobs/{jobId}/events`, `ai/training/progress`, `settings/cadence`).

### Key Entities *(include if feature involves data)*
- **WebUI Page Contract**: Describes each of the seven mandated pages, the primary objective of the view, and the data/command flows it depends on via REST or WebSocket channels.
- **Hardware Baseline**: Captures required vs. optional hardware components (Raspberry Pi models, GPS modules, sensors, power monitoring, drive systems, AI accelerators) and their constraints so the specification remains synchronized with the hardware manifest.
- **Telemetry Exchange**: Summarizes the snapshot data, event notifications, and job updates that the system must publish to satisfy the dashboard, planning, and safety monitoring experiences.

## Clarifications

### Session 2025-09-24
- Q: What update frequency should the telemetry WebSocket deliver to the Dashboard? → A: 1 Hz adjustable
- Q: Which authentication model should the WebUI use for access control? → A: Option A (single shared operator credential)
- Q: Which dataset export formats must the AI Training page support? → A: Option C (COCO and YOLO)

### Session 2025-09-24B
- Q: How should the telemetry cadence align with the LawnBerry Pi v2 platform plan? → A: Operate at 5 Hz by default (expandable to 10 Hz) with the ability to step down to 1 Hz for diagnostics or when conserving power.
- Q: Does the WebUI need to reference retro branding assets documented in the v2 master plan? → A: Yes, the specification must call out usage of `LawnBerryPi_logo.png`, `LawnBerryPi_icon2.png`, and the robot pin marker across relevant surfaces.
- Q: What hardware alignment points from the platform specification must this document echo? → A: Exclusive GPS selection (F9P USB + NTRIP vs. Neo-8M UART), motor controller priority (RoboHAT→Cytron MDDRC10 with L298N fallback), INA3221 channel immutability, and AI acceleration hierarchy (Coral USB in isolated `venv-coral` → Hailo HAT → CPU TFLite).

---

## Review & Acceptance Checklist
*GATE: Automated checks run during main() execution*

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
*Updated by main() during processing*

- [x] User description parsed
- [x] Key concepts extracted
- [x] Ambiguities marked
- [x] User scenarios defined
- [x] Requirements generated
- [x] Entities identified
- [x] Review checklist passed

---
