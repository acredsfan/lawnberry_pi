# Research Notes – LawnBerry Pi v2 Hardware Integration & UI Completion

## Objectives
- Confirm live telemetry pipelines for every component in `spec/hardware.yaml`, including RoboHAT RP2040 firmware (`robohat-rp2040-code/code.py`) and INA3221 channel mapping.
- Restore and harden UI pages (Dashboard, Map Setup, Control, Settings) while enforcing LawnBerry branding assets and retro aesthetic.
- Establish verification and documentation updates necessary for final release sign-off on Raspberry Pi 5 with Raspberry Pi 4B graceful degradation.

## Findings & Decisions

### Telemetry verification workflow
- **Decision**: Use the existing FastAPI telemetry endpoints and WebSocket hub to stream data at 5 Hz (configurable 1–10 Hz) and log snapshot comparisons against hardware ranges. Embed automated validation via pytest in `tests/contract/test_telemetry.py` and add telemetry smoke scripts for field validation.
- **Rationale**: Reuses hardened backend infrastructure while enabling deterministic test runs (SIM_MODE) and live hardware capture. Aligns with constitutional requirements for reproducible validation.
- **Alternatives considered**: Adding a separate telemetry aggregation microservice (rejected due to platform constraints); relying solely on manual dashboard observation (rejected—insufficient for CI evidence).

### RoboHAT firmware handshake
- **Decision**: Expose a `GET /api/v2/hardware/robohat` endpoint backed by serial bridge health checks and embed firmware version metadata emitted by `code.py`. Control commands go through the existing IPC channel, with watchdog metrics logged.
- **Rationale**: Ensures firmware version drift is detected and provides auditable status for safety-critical functions.
- **Alternatives considered**: Extending MQTT topic coverage for RoboHAT telemetry (deferred—may be explored later once MQTT broker hardening completes).

### Map Setup provider strategy
- **Decision**: Keep Google Maps as primary provider with adaptive tile throttling and enforce OSM fallback when quota limits approach. Store polygons and markers in SQLite (`map_zones`, `system_config`) with schema migration guardrails.
- **Rationale**: Meets requirement for Google Maps defaults while guaranteeing offline-ready fallback per documentation. SQLite already supports zone persistence.
- **Alternatives considered**: Moving to Mapbox (rejected—would violate current branding assets and increase dependency footprint).

### Control page resiliency
- **Decision**: Wrap manual control commands in REST calls (`POST /api/v2/control/drive`, `POST /api/v2/control/blade`, `POST /api/v2/control/emergency`) plus mirrored WebSocket responses to reflect actuator state. Add debounce and lock-out indicators when safety conditions trigger.
- **Rationale**: Maintains compatibility with automated tests and provides immediate operator feedback.
- **Alternatives considered**: Direct WebSocket-only control (rejected to preserve audit logging guarantee) and bypassing RoboHAT for debugging (rejected—breaks constitutional hardware coordination).

### Settings page architecture
- **Decision**: Compose Settings from backend configuration manager (`backend/src/core/config.py`) endpoints, splitting panels into Hardware, Network, Telemetry, Simulation, AI Acceleration, Branding Compliance. Persist via atomic updates and surface validation errors inline.
- **Rationale**: Respects existing JSON/SQLite configuration stack and prevents inconsistent state, while allowing UI reusability.
- **Alternatives considered**: Creating a new settings microservice (rejected—overhead, duplicates persistence logic).

### Documentation updates
- **Decision**: Regenerate hardware overview, feature matrix, wiring diagrams, and operations guides to reference verified telemetry checks, RoboHAT firmware, and UI flows. Host docs in Docs Hub with offline cache.
- **Rationale**: Required for release readiness and constitutional documentation drift prevention.
- **Alternatives considered**: Linking to external wiki (rejected—violates offline-access requirement).

### Performance guardrail
- **Decision**: Enforce ≤250 ms dashboard telemetry latency on Raspberry Pi 5 and ≤350 ms on Raspberry Pi 4B via automated perf test script (`scripts/test_performance_degradation.py`) and frontend frame timing instrumentation.
- **Rationale**: Aligns with clarified requirement and ensures both hardware tiers remain compliant.
- **Alternatives considered**: Raising threshold to 500 ms (rejected—operator feedback would appear sluggish and contradict clarified expectation).

## Outstanding Risks & Mitigations
- **Google Maps API key availability**: Mitigate by detecting missing key, guiding operator to fallback automatically, and documenting requirements.
- **Hardware unavailability during CI**: Maintain SIM_MODE test coverage; require manual sign-off checklist for physical verification and attach logs/screenshots as verification artifacts.
- **Coral/Hailo optional acceleration**: Ensure isolation by gating UI toggles behind detection and verifying CPU fallback path remains functional.

## Research Completion Checklist
- [x] Telemetry verification approach defined
- [x] RoboHAT handshake strategy documented
- [x] Map provider decision confirmed
- [x] Control and Settings UX behavior clarified
- [x] Documentation update scope defined
- [x] Performance guardrail captured
```}