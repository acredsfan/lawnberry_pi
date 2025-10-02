# WebSocket Topics – LawnBerry Pi v2

| Channel | Direction | Payload Schema | Purpose |
|---------|-----------|----------------|---------|
| `wss://<host>/api/v2/ws/telemetry` | server → client | `HardwareTelemetryStream` array (see OpenAPI schema) | Streams live telemetry frames at 5 Hz (configurable). Includes latency header `x-latency-ms`. |
| `wss://<host>/api/v2/ws/control` | bidirectional | `ControlCommandResponse` (server) / `DriveCommandRequest \| BladeCommandRequest \| {"type":"emergency"}` (client) | Mirrors manual control acknowledgements and state transitions. |
| `wss://<host>/api/v2/ws/settings` | server → client | `{ "profile_version": string, "updated_at": string }` | Pushes configuration updates triggered elsewhere to keep Settings UI in sync. |
| `wss://<host>/api/v2/ws/notifications` | server → client | `{ "severity": "info"|"warning"|"critical", "message": string, "timestamp": string }` | Broadcasts safety lockouts, telemetry faults, and documentation drift alerts. |

## Event Semantics
- All channels require JWT authentication; connections without valid tokens are rejected with 4401.
- Telemetry streams include `sequence_id` monotonic integer and `component_id` enumerations aligning with REST contract.
- Control channel enforces `session_id` correlation ID; server echoes `result` with matching `session_id`.
- Settings channel emits after successful `PUT /settings` or when SIM_MODE toggles.
- Notifications channel is backed by audit log tailing; messages are persisted for retrieval via `/audit/logs` (existing API).

## Latency Targets
- Telemetry messages must arrive ≤250 ms after hardware capture on Raspberry Pi 5.
- Control acknowledgements must be round-tripped ≤200 ms on Raspberry Pi 5.
- WebSocket reconnect strategy uses exponential backoff capped at 5 seconds; UI shows banner after >10 seconds disconnect.
