# Phase 0 Research — WebUI Page & Hardware Alignment Update

## Decision: Telemetry Cadence Strategy
- **Rationale**: A 5 Hz default stream with a 10 Hz performance ceiling keeps dashboard widgets lively while respecting Pi 5/4B CPU and network headroom. Operators can downshift to 1 Hz during diagnostics, remote support, or power-constrained scenarios without rewriting contracts.
- **Alternatives Considered**: 1 Hz-only delivery lacked situational awareness during active mowing. Always-on 10 Hz updates overran bandwidth in weed-heavy test runs and interfered with Picamera2/GStreamer capture pipelines.

## Decision: Authentication Model
- **Rationale**: Retaining a single shared operator credential keeps the on-device workflow simple during field ops and aligns with constitution guidance against expanding auth surface without formal approval.
- **Alternatives Considered**: Per-user RBAC (adds account lifecycle complexity) and API token gating (creates parallel credential stores). Both were deferred to avoid new compliance and UX overhead.

## Decision: Dataset Export Formats
- **Rationale**: COCO JSON + YOLO TXT cover the downstream labeling and training stacks already used in LawnBerry pipelines. Exporting both formats in one job prevents duplicate storage and QA passes.
- **Alternatives Considered**: Pascal VOC XML was deemed legacy for our tooling; custom CSV/Parquet would require bespoke importers and confuse model retraining scripts.

## Decision: REST + WebSocket Coverage Map
- **Rationale**: Standardizing on `/api/<domain>` REST endpoints (snapshot, zones, manual command, jobs, datasets, settings, docs) and namespaced WebSocket topics (`telemetry/updates`, `map/updates`, `manual/feedback`, `mow/jobs/{jobId}/events`, `ai/training/progress`, `settings/cadence`) keeps parity with mower-core and lets each page cite concrete contracts.
- **Alternatives Considered**: GraphQL was out-of-scope; MQTT topics were rejected because the constitution prioritizes REST/WebSocket for operational comms and we already maintain WebSocket infrastructure for mower telemetry.

## Decision: Hardware Alignment Source
- **Rationale**: `spec/hardware.yaml` remains the authoritative manifest. Every spec update must mirror its preferred/alternate components, INA3221 channel locks, and acceleration conflicts.
- **Alternatives Considered**: Pulling from older Google Docs or README snippets would risk drift and violate the Documentation-as-Contract principle.

## Decision: Motor & Power Hierarchy
- **Rationale**: Retaining the RoboHAT→Cytron MDDRC10 preference (with L298N fallback) and honoring INA3221 channel immutability ensures UI power widgets and safety alarms match the electrical stack described in `spec/hardware.yaml`.
- **Alternatives Considered**: Promoting the L298N to a co-equal option would require new current calibration notes and contradict the conflict warnings already encoded in the manifest.

## Decision: GPS & Localization Selection
- **Rationale**: Mirroring the v2 plan’s rule that operators must choose either ZED-F9P (USB + NTRIP) or Neo-8M (UART) keeps the WebUI settings page honest about mutually exclusive GPS pipelines and network prerequisites.
- **Alternatives Considered**: Allowing simultaneous configuration confused field testers and led to undefined coordinate sources during failover drills.

## Decision: Branding Assets
- **Rationale**: Highlighting `LawnBerryPi_logo.png`, `LawnBerryPi_icon2.png`, and the LawnBerry robot pin ensures the retro 1980s motif appears consistently across Dashboard, Manual Control, and Docs Hub, matching the platform story from 001-build-lawnberry-pi.
- **Alternatives Considered**: Leaving branding implicit caused inconsistent iconography in earlier prototypes and broke the narrative alignment marketing requested.
