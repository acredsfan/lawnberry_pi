# Contract Test Plan

## REST Endpoints

| Endpoint | Required Tests | Notes |
|----------|----------------|-------|
| `GET /telemetry/stream` | Smoke retrieval with healthy data, pagination cursor coverage, 503 when telemetry daemon offline | Validate schema matches `HardwareTelemetryStream` definition and latency summary keys. |
| `POST /telemetry/ping` | Valid component latency measurement, invalid component id (422), high latency alert path | Use SIM_MODE to inject latency >250 ms and verify failure.
| `GET /hardware/robohat` | Firmware metadata present, watchdog stale heartbeat triggers warning, 503 unreachable controller | Requires serial bridge stub for CI.
| `GET/PUT /map/configuration` | Round-trip persistence of markers/polygons, validation rejection for overlapping zones, provider switch to OSM fallback | Ensure saved payload updates SQLite and triggers WebSocket sync.
| `POST /control/drive` | Accepted command with telemetry echo, blocked due to lockout, rejected for invalid payload | Assert audit log entry creation.
| `POST /control/blade` | Engage/disengage flows, lockout enforcement, dual command debouncing | Must confirm driver acknowledgement (IBT-4 GPIO path), not RoboHAT.
| `POST /control/emergency` | Emergency stop accepted, repeated call idempotency | Confirm safety interlock resets control UI.
| `GET/PUT /settings` | Fetch default profile, update cadence with version bump, conflict when outdated version submitted | Validate branding checksum recompute.
| `GET /docs/bundle` | Returns offline-available docs list, checksum mismatch triggers warning header | Use fixture docs.
| `POST /verification-artifacts` | Accepts telemetry log metadata, rejects when linked requirements empty, enforces known requirement IDs | Links FR-001…FR-016.

## WebSocket Channels

- `ws://.../telemetry`: streaming cadence test, latency measurement, component health transitions.
- `ws://.../control`: command echo path, safety lockout broadcast, session correlation failure case.
- `ws://.../settings`: update broadcast after settings PUT, stale connection recovery.
- `ws://.../notifications`: critical error broadcast, offline doc drift alert, reconnect handling.

## Test Harness Expectations
- Tests created under `tests/contract/` and `tests/integration/` MUST start failing (pending implementation) until backend/frontend satisfy contracts.
- Provide fixtures for SIM_MODE and hardware mocks; real hardware validation handled by quickstart steps.
- Performance guardrail measured via `scripts/test_performance_degradation.py` invoked in CI with thresholds from constitution.
