# Data Model — WebUI Page & Hardware Alignment Update

## WebUIPage
- **Description**: Canonical record describing one of the seven mandated WebUI experiences.
- **Identifiers**: `slug` (`dashboard`, `map-setup`, `manual-control`, `mow-planning`, `ai-training`, `settings`, `docs-hub`).
- **Fields**:
  - `display_name` (string, required)
  - `primary_goal` (string, required)
  - `rest_dependencies` (array of `RestContract.id`, ≥1, required)
  - `ws_topics` (array of `WebSocketTopic.id`, optional for Docs Hub)
  - `telemetry_requirements` (object; cadence, alert thresholds)
  - `simulation_support` (boolean, must be `true` per constitution)
- **Relationships**:
  - References one or more `TelemetryStream` definitions.
  - References zero or more `DatasetExportJob` capabilities (only AI Training).
  - Relies on one `OperatorCredential` for gated interactions (Manual Control, Settings).
- **Validation Rules**:
  - Every page must list at least one REST contract, even if it is documentation only.
  - Pages requiring live state (`dashboard`, `manual-control`, `mow-planning`) must include ≥1 WebSocket topic with `<1.5s` latency expectation.

## TelemetryStream
- **Description**: Streamed data published over WebSocket for real-time UI updates.
- **Identifiers**: `topic` (e.g., `telemetry/updates`, `map/updates`).
- **Fields**:
  - `cadence_hz` (float, default `1.0`, adjustable range `0.2–5.0`)
  - `payload_schema` (JSON Schema reference)
  - `source_service` (string, e.g., `mower-core`, `navigation`, `safety`)
  - `critical` (boolean; true triggers alert surfaces if stream stalls >3s)
- **Relationships**:
  - Bound to one or more `WebUIPage` consumers.
  - May mirror a `RestContract` payload for historical fetch fallback.
- **Validation Rules**:
  - Streams flagged as `critical` must include heartbeat fields `last_update` and `uptime_seconds`.
  - Telemetry topics must offer simulation publishers for CI/CD validation.

## RestContract
- **Description**: REST endpoint supporting a WebUI action or data retrieval.
- **Identifiers**: `id` (URI path + method, e.g., `GET /api/dashboard/state`).
- **Fields**:
  - `method` (`GET`, `POST`, `PUT`, `PATCH`)
  - `path` (string)
  - `request_schema` (JSON Schema or `null` when N/A)
  - `response_schema` (JSON Schema, required)
  - `auth_required` (boolean; true for all but Docs Hub)
  - `roles_allowed` (array; currently `["operator"]`)
  - `cache_ttl_seconds` (integer, optional; dashboard state defaults to 2)
- **Relationships**:
  - Consumed by one or more `WebUIPage` instances.
  - May expose backing data for `TelemetryStream` fallbacks.
- **Validation Rules**:
  - Manual Control endpoints must reject unauthenticated calls and log audit entries.
  - Map mutation endpoints require optimistic concurrency tokens to prevent overwriting concurrent edits.

## WebSocketTopic
- **Description**: Async channel streaming state changes tied to one or more pages.
- **Identifiers**: `name` (e.g., `telemetry/updates`, `manual/feedback`).
- **Fields**:
  - `message_schema` (JSON Schema reference, required)
  - `heartbeat_interval_sec` (integer, default `1`)
  - `supports_backfill` (boolean; dashboard and mow progress must be `true`)
- **Relationships**:
  - Linked to `TelemetryStream` when the topic is stateful; can exist independently for acknowledgement channels.
  - Referenced by `WebUIPage.ws_topics`.
- **Validation Rules**:
  - Topics carrying safety-critical data must include `safety_state` payload attributes.
  - Topics must broadcast a `settings` frame when cadence is updated at runtime.

## DatasetExportJob
- **Description**: Represents a request to package labeled imagery and annotations for download.
- **Identifiers**: `job_id` (UUID).
- **Fields**:
  - `requested_formats` (set ⊆ {`coco-json`, `yolo-txt`}, required, size ≥1)
  - `status` (`queued`, `running`, `complete`, `failed`)
  - `image_count` (integer, required)
  - `submitted_by` (`OperatorCredential.id`, required)
  - `submitted_at`, `completed_at` (timestamps)
  - `artifact_urls` (map keyed by format; populated on completion)
- **Relationships**:
  - Created via `RestContract POST /api/ai/datasets/export`.
  - Progress updates streamed over `WebSocketTopic ai/training/progress`.
- **Validation Rules**:
  - Must include both COCO + YOLO when requested; fail the job if either export fails.
  - Simulation mode must stub export completion within 5 seconds for test pipelines.

## HardwareProfile
- **Description**: Snapshot describing preferred and alternate hardware for the mower platform.
- **Identifiers**: `component` (e.g., `gps`, `imu`, `ai_acceleration`).
- **Fields**:
  - `preferred` (object; matches `spec/hardware.yaml` details)
  - `alternatives` (array of alternative hardware entries)
  - `conflicts` (array of strings; e.g., "Hailo HAT cannot stack with RoboHAT")
  - `required_buses` (array; e.g., `I2C`, `UART4`, `USB`)
- **Relationships**:
  - Referenced by spec hardware section and `WebUIPage` notes for configuration steps.
  - Provides context for `TelemetryStream` fields (e.g., INA3221 mapping to dashboard alerts).
- **Validation Rules**:
  - INA3221 must always map channel 1 → battery, 2 → unused, 3 → solar.
  - Coral USB accelerator flagged as `preferred` for AI acceleration tier.

## OperatorCredential
- **Description**: Authentication artifact guarding WebUI access.
- **Identifiers**: `id` (currently `operator-shared`).
- **Fields**:
  - `username` (string, required)
  - `password_hash` (string, stored securely outside spec scope)
  - `permissions` (set; includes `view`, `control`, `export`)
  - `last_rotated_at` (timestamp)
- **Relationships**:
  - Required by `RestContract` entries where `auth_required = true`.
  - Drives gating logic for `WebUIPage` manual control and settings sections.
- **Validation Rules**:
  - Manual control commands must verify the credential before queueing drive/blade actions.
  - Dataset exports must log the credential ID for traceability.