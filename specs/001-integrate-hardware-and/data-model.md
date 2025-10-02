# Data Model – LawnBerry Pi v2 Hardware Integration & UI Completion

## Overview
This feature extends existing persistence and runtime telemetry structures. It does not introduce a new database technology, but it formalizes entities to ensure telemetry verification, UI flows, and documentation artifacts remain consistent.

## Entities

### HardwareTelemetryStream
- **Purpose**: Real-time snapshot of hardware sensor values and derived status flags.
- **Source**: RoboHAT RP2040 serial bridge, I2C/USB peripherals, telemetry aggregation service.
- **Attributes**:
  - `timestamp` (UTC ISO8601, primary ordering key)
  - `component_id` (enum: imu, gps, power, tof_left, tof_right, blade_motor, drive_left, drive_right, coral, hailo, cpu)
  - `value` (variant payload: numeric, object depending on component)
  - `status` (enum: healthy, warning, fault)
  - `latency_ms` (float)
  - `metadata` (JSON: includes INA3221 channel, GPS fix type, IMU quaternion, etc.)
- **Relationships**:
  - Linked to `VerificationArtifact` entries for evidence capture.
  - Referenced by `ControlSession` to display actuator response.

### MapConfiguration
- **Purpose**: Persisted geospatial definition for mowing area, exclusion zones, and special markers.
- **Storage**: SQLite `map_zones` table and `system_config` JSON.
- **Attributes**:
  - `zone_id` (UUID, primary key)
  - `zone_type` (enum: boundary, exclusion, home, am_sun, pm_sun)
  - `geometry` (GeoJSON polygon or point, WGS84)
  - `priority` (int)
  - `color` (hex string for UI rendering)
  - `last_modified` (UTC timestamp)
- **Relationships**:
  - Referenced by control planner and job scheduling modules.
  - Surfaces in Docs Hub as part of configuration export.

### ControlSession
- **Purpose**: Auditable record of manual control interactions and resulting states.
- **Storage**: SQLite `audit_logs` (existing) with `details_json` extension.
- **Attributes**:
  - `session_id` (UUID)
  - `operator_id` (string; single shared credential with MFA)
  - `command` (enum: drive, blade, emergency_stop, mode_toggle)
  - `command_payload` (JSON: PWM targets, reason codes)
  - `result` (enum: accepted, rejected, blocked)
  - `status_reason` (string; e.g., "SAFETY_LOCKOUT")
  - `telemetry_snapshot_id` (FK -> `HardwareTelemetryStream`)
  - `created_at` (UTC timestamp)
- **Relationships**:
  - References telemetry for verification artifacts.
  - Linked to settings changes when commands adjust configuration.

### SettingsProfile
- **Purpose**: Aggregated configuration state for hardware, network, telemetry, simulation, AI acceleration, and branding compliance.
- **Storage**: Combination of `/config/*.json` and SQLite `system_config`.
- **Attributes**:
  - `profile_version` (semver string)
  - `hardware` (JSON: calibration values, channel mapping overrides)
  - `network` (JSON: wifi, hotspot, remote access)
  - `telemetry` (JSON: cadence_hz, latency_targets)
  - `simulation_mode` (bool)
  - `ai_acceleration` (enum: coral, hailo, cpu)
  - `branding_checksum` (SHA256 of required assets)
  - `updated_at` (UTC timestamp)
- **Relationships**:
  - UI Settings page reads/writes this entity.
  - Changes generate `VerificationArtifact` entries and `audit_logs` rows.

### DocumentationBundle
- **Purpose**: Collection of synchronized documentation artifacts for operators.
- **Storage**: Markdown/HTML in `docs/` with metadata tracked in SQLite or JSON manifest.
- **Attributes**:
  - `doc_id` (string; e.g., "hardware-overview")
  - `title`
  - `version` (semver)
  - `last_updated`
  - `checksum`
  - `offline_available` (bool)
- **Relationships**:
  - Exposed via Docs Hub UI.
  - Referenced in verification artifacts to confirm documentation completion.

### VerificationArtifact
- **Purpose**: Evidence package showing telemetry validation, UI walkthroughs, and documentation completion.
- **Storage**: Files (logs, screenshots, JSON summaries) with metadata recorded in SQLite `audit_logs` or dedicated table.
- **Attributes**:
  - `artifact_id` (UUID)
  - `type` (enum: telemetry_log, ui_screencast, doc_diff, performance_report)
  - `location` (path or URL)
  - `created_by` (operator id / automation)
  - `created_at`
  - `summary` (string)
  - `linked_requirements` (array of FR ids)
- **Relationships**:
  - Connects to `HardwareTelemetryStream`, `ControlSession`, `DocumentationBundle` as evidence.

## State & Lifecycle Notes
- Telemetry snapshots stream continuously; every run generates automated validations and can be archived if flagged.
- Map configuration edits trigger new versions stored in SQLite and mirrored to configuration JSON for Docs Hub export.
- Control sessions close automatically after command completion or timeouts, leaving an immutable audit record.
- Settings profile updates bump `profile_version` (semantic) and recompute branding checksum to enforce asset presence.
- Documentation bundle refresh occurs at release checkpoints; docs must reference the same asset set used in UI.
- Verification artifacts gathered during integration become release attachments and must pass CI upload checks.

## Data Volume & Scale
- Telemetry: 5–10 Hz streaming capped by retention policy (default 7 days). SQLite housekeeping job prunes old entries.
- Map zones: tens of polygons per property; negligible impact.
- Control sessions & verification artifacts: low volume, but critical for audit.
- Documentation bundles: handful of Markdown/HTML files with associated assets (<10 MB total).
```}