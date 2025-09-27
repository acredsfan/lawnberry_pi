# LawnBerry Pi v2.0.0 - Release Notes (2025-09-27)

This release replaces version 1 with a unified v2 backend and frontend, contract-tested APIs, and on-device readiness for Raspberry Pi (ARM64, Bookworm).

## Highlights

- Hardware telemetry behind SIM_MODE (T102, T110)
  - Default simulation mode (SIM_MODE=1) keeps CI/dev safe
  - Set `SIM_MODE=0` on the Pi to lazily initialize sensors via SensorManager and publish hardware-backed telemetry over WebSocket
  - Graceful fallback to simulated data on hardware errors

- Docs Hub polish (T099)
  - Backend serves markdown/text with `ETag`, `Last-Modified`, and `Cache-Control`
  - Frontend renders markdown safely using markdown-it + DOMPurify (sanitization tests included)

- Stability & health
  - Liveness/readiness endpoints verified
  - WebSocket telemetry with cadence control and reconnection
  - Privacy guard + log rotation retained

## Validation

- Backend: pytest – PASS (contract + integration tests green)
- Frontend: vitest – PASS (UI/composables + markdown sanitization green)
- Frontend build: Type-check + Vite production build – PASS
- Lint: Warnings only (types tightening optionally tracked)

## Deployment Notes

- Systemd services under `systemd/` can be used to run backend and related services
- To enable hardware telemetry on the device:
  - Ensure the `pi` user is in required groups (e.g., `i2c`, `dialout`)
  - Export `SIM_MODE=0` in the backend service environment
- Docs Hub available via `/docs` route in the WebUI; content served from `docs/` directory

## Breaking Changes

- API endpoints are under `/api/v2/*`; WebSocket at `/api/v2/ws/telemetry`
- Configuration and persistence aligned with v2 schema (migration tests included)

## Next Steps

- Add calibrated battery percentage mapping per chemistry
- Extend SensorManager coverage and readiness checks when `SIM_MODE=0`
- Optional TS type tightening to reduce `any` usage in frontend composables
