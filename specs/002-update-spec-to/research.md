# Phase 0 Research — WebUI Page & Hardware Alignment Update

## Decision: Telemetry Cadence Strategy
- **Rationale**: A 1 Hz default stream with operator-controlled throttling balances dashboard freshness with Pi network and CPU overhead. The cadence aligns with current mower safety monitoring requirements while letting operators increase frequency temporarily for diagnostics.
- **Alternatives Considered**: 2–5 Hz streaming was rejected because it inflates bandwidth and can starve Picamera2/GStreamer pipelines. Sub-1 Hz polling would delay safety alerts and KPI visibility.

## Decision: Authentication Model
- **Rationale**: Retaining a single shared operator credential keeps the on-device workflow simple during field ops and aligns with constitution guidance against expanding auth surface without formal approval.
- **Alternatives Considered**: Per-user RBAC (adds account lifecycle complexity) and API token gating (creates parallel credential stores). Both were deferred to avoid new compliance and UX overhead.

## Decision: Dataset Export Formats
- **Rationale**: COCO JSON + YOLO TXT cover the downstream labeling and training stacks already used in LawnBerry pipelines. Exporting both formats in one job prevents duplicate storage and QA passes.
- **Alternatives Considered**: Pascal VOC XML was deemed legacy for our tooling; custom CSV/Parquet would require bespoke importers and confuse model retraining scripts.

## Decision: REST + WebSocket Coverage Map
- **Rationale**: Standardizing on `/api/<domain>` REST endpoints for CRUD actions and `/ws/<topic>` channels for live telemetry keeps parity with existing services (e.g., mower-core) and makes spec references actionable.
- **Alternatives Considered**: GraphQL was out-of-scope; MQTT topics were rejected because constitution prioritizes REST/WebSocket for operational comms.

## Decision: Hardware Alignment Source
- **Rationale**: `spec/hardware.yaml` remains the authoritative manifest. Every spec update must mirror its preferred/alternate components, INA3221 channel locks, and acceleration conflicts.
- **Alternatives Considered**: Pulling from older Google Docs or README snippets would risk drift and violate the Documentation-as-Contract principle.
