# LawnBerry Pi v2.0.0 - Release Notes (2025-09-27)

This release replaces version 1 with a unified v2 backend and frontend, contract-tested APIs, and on-device readiness for Raspberry Pi (ARM64, Bookworm).

## Maintenance (2025-10-22)

- Hardened backend authentication by switching to a direct bcrypt-based password manager that safely handles operator credentials longer than 72 bytes.
- Secrets manager now self-generates a persistent `JWT_SECRET` when missing, avoiding startup failures on fresh installs.

## Enhancements (2025-10-25)

- Manual control camera feed now streams via `/api/v2/camera/stream.mjpeg` with automatic snapshot fallback, reducing perceived latency on the WebUI.
- Drive commands carry the operator speed slider as `max_speed_limit`, ensuring forward throttle reaches the RoboHAT controller while preserving safety clamps.
- Motor safety logging correctly reports safety violations instead of raising attribute errors, improving diagnostics when commands are rejected.
- Camera API endpoints now include dedicated rate-limit allowances and the WebUI identifies itself via `X-Client-Id`, eliminating `429 Too Many Requests` errors during streaming fallback.
- WebUI detects unavailable MJPEG streams, switches to snapshot mode automatically, and suppresses repetitive console errors for smoother diagnostics.
- MJPEG snapshot fallback now auto-retries the primary stream after short cooldowns, so camera feeds recover without manual refreshes.
- Joystick drive commands are coalesced and dispatched at a higher cadence, cutting manual control input lag while staying within rate limits.

## Fixes (2025-10-26)

- RoboHAT USB watchdog now detects firmware timeouts and reasserts `rc=disable`, ensuring manual joystick drive commands continue to reach the motor controller after idle periods.
- Added backend unit coverage for RoboHAT USB control keep-alive logic to prevent regressions in manual movement.
- RoboHAT PWM handshake now waits for explicit firmware acknowledgement before issuing keep-alives or drive commands, eliminating `[USB] Invalid command: pwm` spam and restoring manual joystick responsiveness.

## Fixes (2025-10-27)

- Manual drive endpoints retry RoboHAT USB takeover with adaptive timeouts and surface firmware errors in responses, eliminating silent command drops when RC passthrough lingers.
- Control WebUI now highlights motor-controller health, blocks dispatch when the USB link is offline, and raises toasts when the controller disconnects or recovers.
- Camera JPEG encoder respects explicit colour-space hints from PiCamera2 frames, preventing the magenta tint seen in MJPEG streams after the migration to RGB888 capture.
- Added regression tests for RoboHAT USB acquisition retries, manual unlock TOTP window tolerance, and camera colour encoding to prevent future regressions.

## Fixes (2026-03-15)

- Navigation waypoint completion now requires a fresh, non-dead-reckoned GPS fix, preventing missions from advancing on stale or synthetic position estimates.
- Mission pause and abort flows now retry stop delivery and escalate to emergency stop when motion cannot be halted cleanly.
- RoboHAT emergency stop now fails closed when USB control cannot be re-acquired instead of pretending a neutral PWM command succeeded.
- Mission metadata and lifecycle state now persist in SQLite, and startup recovery restores missions conservatively by recovering prior running state as paused instead of auto-resuming motion.

## Enhancements (2026-03-16)

- Control WebUI now classifies lockout severity and shows clearer remediation-oriented messaging for emergency-stop, low-battery, and generic safety lockouts.
- Manual control camera status now distinguishes live streaming from snapshot fallback so operators can see when MJPEG recovery is still in progress.
- Mission Planner now surfaces recovered-paused mission detail and waypoint progress from the backend status contract instead of showing only a bare paused/running string.
- Frontend mission/control stores now use tighter status typing and regression coverage around control lockouts, camera fallback, and recovered mission visibility.
- Manual control camera fallback now tolerates both flat backend camera status payloads and raw frame responses, reducing drift between the frontend fallback path and the current FastAPI camera endpoints.
- Added focused Playwright coverage for blocked manual-control lockouts, deterministic snapshot fallback, and recovered-paused mission visibility.

## Fixes (2026-03-19)

- FastAPI camera snapshot and MJPEG endpoints now emit raw JPEG bytes instead of leaking Base64 frame strings with an `image/jpeg` content type, restoring both live camera streaming and snapshot fallback on `/control`.
- The deployed frontend server now skips HTTP compression for `/api/v2/camera/frame` and `/api/v2/camera/stream.mjpeg`, preventing multipart MJPEG responses from being buffered into a black or stalled camera pane.
- RoboHAT status handling now marks the controller ready as soon as the firmware acknowledges `rc=disable`, clears stale `usb_control_unavailable` warnings on real takeover, and accepts the firmware's Python-dict `[STATUS]` payloads during diagnostics.
- RoboHAT port probing now waits for CircuitPython startup after the USB CDC port opens, treats legacy `[RC] ...` heartbeats as valid firmware activity, and recognizes older `[USB] Timeout → back to RC` messages so enumerated RP2040 boards are no longer misclassified as missing or unresponsive.
- HTTPS fallback now regenerates self-signed certificates with SAN entries for the configured hostnames plus detected LAN IPv4 addresses, fixing modern-browser hostname mismatch failures when the frontend is reached by Pi IP.
- Let's Encrypt setup now skips IP literals in `ALT_DOMAINS` instead of passing them to certbot, preventing LAN-IP configuration drift from breaking certificate issuance for the real hostname.
- The canonical `/api/v2/settings` payload now prefers the unit system stored by `/api/v2/settings/system`, so choosing imperial units in the Settings UI no longer snaps back to metric after refresh or app startup.
- Documented that Cloudflare Access on the public hostname blocks HTTP-01 unless the ACME challenge path is bypassed or DNS-01 is used.
- Added focused backend regression coverage for camera byte delivery and RoboHAT USB-control readiness parsing.

## Fixes (2026-03-21)

- FastAPI startup now syncs the loaded hardware configuration into the shared singleton app state before telemetry initialization, so hardware-backed telemetry no longer falls back to `neo8m_uart` when the mower is actually configured for a ZED-F9P over USB.
- WebSocket/sensor diagnostics now share the same sensor-manager and NTRIP state used by the live telemetry path, restoring accurate `/api/v2/sensors/gps/status` and RTK diagnostics after startup.
- Added focused regression coverage for telemetry hardware-config selection and WebSocket hub app-state synchronization to prevent future GPS/RTK drift regressions.

## Highlights

- Hardware telemetry behind SIM_MODE (T102, T110)
  - `SIM_MODE=1` is the pure simulation path used for CI/dev safety
  - `SIM_MODE=0` on the Pi initializes sensors lazily via SensorManager and publishes hardware-backed telemetry over WebSocket
  - Leaving `SIM_MODE` unset currently behaves like hardware mode because startup checks `os.getenv("SIM_MODE", "0")`
  - Hardware mode still uses graceful fallback when individual devices fail

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
