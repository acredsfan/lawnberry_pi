# LawnBerry Pi Developer Toolkit

This is the maintainer-first re-entry document for LawnBerry Pi. If you are coming back to the project after time away, start here before diving into feature work, hardware changes, or debugging.

## What this project is

LawnBerry Pi is an autonomous lawn mower platform built around a Raspberry Pi, a FastAPI backend, and a Vue 3 frontend. It combines:

- hardware control for drive motors, blade motor, GPS, IMU, ToF sensors, power monitoring, and camera streaming
- a web UI for manual control, telemetry, mission planning, maps, settings, and diagnostics
- operational tooling for TLS, backups, remote access, logging, validation, and deployment on Raspberry Pi OS Bookworm

In practical terms, the project has three personalities:

1. **Robotics control system** for the mower and attached hardware
2. **Web application** for operators and developers
3. **Pi appliance** with systemd-managed services, configuration, and diagnostics

## Current project status

The codebase is substantial and already covers the major product surfaces:

- FastAPI backend with domain routers and real-time telemetry
- Vue 3 + Pinia frontend with authenticated views and Playwright/Vitest coverage
- recent operator-clarity hardening in the frontend for mission recovery detail, control lockout severity, and camera fallback visibility
- nginx/TLS fallback now regenerates SAN-aware self-signed certificates for LAN/IP access, though a trusted browser experience still requires Let's Encrypt or local trust installation
- when using `scripts/setup_lets_encrypt.sh`, keep `ALT_DOMAINS` limited to hostnames; LAN/private IPs belong only on the self-signed fallback path, not in ACME requests
- Cloudflare Access in front of the public hostname will block HTTP-01 unless `/.well-known/acme-challenge/*` is explicitly bypassed; otherwise use DNS-01 with a Cloudflare API token
- `/api/v2/settings` now treats the unit system saved through `/api/v2/settings/system` as authoritative, preventing Settings UI unit preferences from being reset by stale legacy profile data on reload
- `/api/v2/control/emergency` now latches control lockout via shared safety state until `/api/v2/control/emergency_clear` explicitly confirms reset, so post-E-stop commands stay fail-closed beyond transient TTL windows
- documented hardware baseline in `spec/hardware.yaml`
- safety, health, telemetry, settings, and mapping subsystems
- Raspberry Pi operational support: systemd units, HTTPS/TLS automation, backups, diagnostics, validation scripts

The project is **not in a greenfield state**. You are returning to a live codebase that already has working paths, but it also has a few mismatches between documentation, runtime defaults, and partially implemented subsystems. Those are listed later under [Immediate focus](#immediate-focus).

## Read these first

Use this order if you need to get mentally back in the saddle quickly:

1. `README.md` — project overview and quick-start entry point
2. `docs/OPERATIONS.md` — runtime ports, service behavior, key API endpoints, systemd notes
3. `docs/TESTING.md` — local backend/frontend/hardware test workflows
4. `docs/hardware-integration.md` — actual wiring, buses, UART/I2C expectations, RTK notes
5. `spec/hardware.yaml` — canonical supported hardware baseline
6. `docs/code_structure_overview.md` — subsystem and callable-interface orientation
7. `docs/RELEASE_NOTES.md` — recent regression-sensitive work and active engineering themes
8. `docs/hallucination-audit.md` — documented cleanup list for stale or unsupported hardware mentions
9. `CONTRIBUTING.md` — coding standards, TODO policy, PR expectations
10. `.github/copilot-instructions.md` — local agent/documentation rules, especially around architecture docs
11. `docs/copilot-customizations-guide.md` — prompt, skill, agent, chat-mode, and hook reference for this repo's Copilot workflows

## Mental model of the system

The shortest useful mental model is:

- **backend** owns hardware, safety, state, APIs, and telemetry
- **frontend** owns operator workflows, control surfaces, maps, diagnostics, and auth-aware UX
- **config/** and `.env` shape runtime behavior
- **scripts/** and `systemd/` are how the appliance is validated and operated on-device
- **docs/** contains both strong source-of-truth material and some drift that still needs cleanup

### Backend runtime map

Main entrypoint:

- `backend/src/main.py`

Important backend layers:

- `backend/src/api/` — FastAPI routers and REST/WebSocket surfaces
- `backend/src/services/` — domain services such as RoboHAT, sensor aggregation, mission, maps, weather, telemetry, remote access, ACME, camera, AI
- `backend/src/nav/` — path planning, coverage, geofence, GPS degradation helpers
- `backend/src/safety/` — startup validation, safety monitor, E-stop/interlock handling, motor authorization
- `backend/src/core/` — config loading, state management, message bus, observability, persistence
- `backend/src/drivers/` — hardware-facing adapters for motors, blade, GPS, ToF, IMU, power, and similar devices
- `backend/src/models/` — Pydantic/domain models
- `backend/src/cli/` — command-line utilities for operations and diagnostics

Things `backend/src/main.py` makes clear today:

- `.env` is loaded early from the project root when present
- config is loaded at startup via `ConfigLoader`
- the app wires many routers under `/api/v2`
- hardware initialization is guarded to stay simulation-safe
- `SIM_MODE=0` is the key switch for real hardware behavior
- safety validation and telemetry loop startup happen in application lifespan

### Frontend runtime map

Frontend entrypoint:

- `frontend/src/main.ts`

Important frontend layers:

- `frontend/src/views/` — top-level screens like Dashboard, Control, Maps, Planning, Mission Planner, Telemetry, RTK Diagnostics, AI, Settings, Docs Hub, Login
- `frontend/src/stores/` — Pinia stores for auth, control, map, mission, system, preferences, toast, and user settings
- `frontend/src/services/` — API client, auth helpers, WebSocket client
- `frontend/src/composables/` — reusable stateful logic like API access, offline maps, and WebSocket handling
- `frontend/src/components/` — reusable UI and domain widgets
- `frontend/src/router/index.ts` — route definitions and auth guard
- `frontend/tests/` — Playwright E2E coverage

Important behavior to remember:

- routes are mostly auth-protected in `frontend/src/router/index.ts`
- the app exposes an E2E test harness via `__APP_TEST_HOOKS__` in `frontend/src/main.ts`
- the frontend supports multiple API/WebSocket connection shapes through service and proxy logic

## Repository structure

This is the useful developer view of the repo, rather than the raw directory listing:

- `backend/` — Python application code and backend packaging
- `frontend/` — Vue 3 app, tests, Vite config, production Node server
- `config/` — YAML and JSON config for hardware, limits, logging, maps, remote access, secrets examples
- `docs/` — operations, setup, hardware, release notes, safety/privacy, architecture reference
- `scripts/` — validation, backup/restore, HTTPS/TLS, RTK and load diagnostics, helper automation
- `systemd/` — service and timer units for deployment on-device
- `tests/` — backend unit/integration/contract coverage
- `spec/` — canonical feature and hardware specifications
- `branding/` — UI/asset branding
- `data/`, `logs/`, `verification_artifacts/` — runtime and validation outputs
- `robohat-rp2040-code/` — firmware-side code/assets for the controller side of the system

## Current runtime and port reality

This is the current startup and runtime contract after the port cleanup pass.

### Canonical ports

- **Backend API**: `8081`
- **Frontend local dev and deployed UI**: `3000`
- **Playwright preview / E2E preview server**: `4173`

### Where those values come from

- `systemd/lawnberry-backend.service` runs Uvicorn on **`8081`**
- `systemd/lawnberry-frontend.service` runs the frontend on **`3000`**
- `frontend/server.mjs` proxies backend traffic to **`http://127.0.0.1:8081`**
- `frontend/vite.config.ts` runs Vite on **`3000`** and now proxies `/api` to **`8081`**
- `frontend/playwright.config.ts` intentionally uses preview port **`4173`**

### Practical interpretation

- Use `8081` when starting or debugging the backend locally.
- Use `3000` when running the frontend in normal local development or deployed mode.
- Use `4173` only when working with preview-based Playwright/E2E runs.
- If you find older port references, treat them as stale and verify them against the current runtime contract before using them.
- On the mower, treat Wi-Fi failover as part of the runtime contract too: `wlan1` is the normal primary client link,
  while `wlan0` must stay NetworkManager-managed so it can scan and take over via the on-device failover dispatcher if
  the primary radio drops.
- Manual drive is now part of the same runtime contract: the UI should only enable the joystick when RoboHAT is actually
  controller-ready, and live hardware drive commands fail closed when fresh telemetry, usable position awareness, or ToF
  obstacle clearance is not available.
- Mission autonomy is now part of that runtime contract too: navigation obstacle gating should use the shared
  `config/limits.yaml` ToF threshold rather than a separate hardcoded distance, and missions must fail with explicit detail
  if waypoint traversal cannot begin safely after the bounded verification window.
- RoboHAT command delivery is part of the same contract: treat a serial write as insufficient proof of motion. The backend
  should only consider a drive command accepted once the RP2040 firmware acknowledges the PWM command; asynchronous firmware
  rejections must propagate back into mission/control failure handling.

## Local developer workflows

### Backend

Primary references:

- `pyproject.toml`
- `docs/TESTING.md`
- `CONTRIBUTING.md`

Useful backend workflow:

1. Create/activate a Python 3.11 environment
2. Install the package and test dependencies
3. Run backend tests in simulation mode first
4. Only move to hardware mode when you actually need it and the Pi is correctly configured

Important points:

- hardware libraries are optional and imported lazily where possible
- `SIM_MODE=1` is the recommended pure-simulation path for local development and CI
- `SIM_MODE=0` enables real hardware initialization on the Pi
- leaving `SIM_MODE` unset currently behaves like hardware mode because startup checks `os.getenv("SIM_MODE", "0")`
- `.env` is used for runtime secrets such as NTRIP configuration and TLS-related settings

For the full mode model, read `docs/simulation-vs-hardware-modes.md`.

### Frontend

Primary reference:

- `frontend/package.json`

Key scripts currently defined:

- `npm run dev`
- `npm run build`
- `npm run preview`
- `npm run start`
- `npm run lint`
- `npm run format`
- `npm run type-check`
- `npm test`
- `npm run test:ui`
- `npm run test:e2e`

### Testing

The project already has multiple test layers:

- backend unit/integration/contract tests under `tests/`
- frontend unit/integration tests via Vitest
- frontend E2E tests via Playwright
- specialized validation scripts under `scripts/`

Read before running anything significant:

- `docs/TESTING.md`
- `docs/OPERATIONS.md`
- `frontend/playwright.config.ts`

## Hardware and simulation model

The codebase is intentionally split between **simulation-safe development** and **real hardware operation**.

### Canonical hardware baseline

Use `spec/hardware.yaml` as the source of truth for supported baseline hardware. As of the current repo state, the baseline includes:

- Raspberry Pi 5 / Pi 4B support target
- ZED-F9P preferred GPS with NEO-8M alternative
- dual VL53L0X ToF sensors
- BME280 environmental sensor
- SSD1306 OLED
- BNO085 IMU
- RoboHAT RP2040 → Cytron MDDRC10 preferred drive control
- L298N fallback drive control
- IBT-4 blade driver
- Pi Camera v2
- Coral USB accelerator, optional Hailo with caveats
- INA3221 and optional Victron BLE-backed power monitoring

Treat `spec/hardware.yaml` as the final word on what is actually in baseline. If another doc mentions LiDAR,
secondary USB cameras, RC receivers, cellular hardware, or other exotic add-ons, assume that content is stale unless
the spec has been updated too.

### Real-hardware gotchas

- `SIM_MODE=0` is required for real hardware behavior
- `SIM_MODE=1` is the only pure simulation path; unset `SIM_MODE` currently still attempts hardware init
- I2C/UART/GPIO expectations are documented in `docs/hardware-integration.md`
- some startup behavior is intentionally best-effort so CI and dev environments do not explode theatrically
- camera ownership is centralized; do not casually create new components that re-open the camera device directly

## Subsystem maturity snapshot

This is the practical “how real is this?” map for returning maintainers. These labels are based on the current code and test
coverage, not on roadmap intent.

| Subsystem | Current maturity | What is real today | Main gaps / cautions |
| --- | --- | --- | --- |
| RoboHAT USB control bridge | **Stable enough for active maintenance** | `backend/src/services/robohat_service.py` now speaks the RP2040 text protocol, probes serial ports with a CircuitPython startup-settle window, maintains USB control, accepts the firmware's Python-dict status payloads, marks the controller ready as soon as the firmware acknowledges `rc=disable`, and waits for explicit PWM acknowledgement before reporting drive-command success. Focused regression coverage lives in `tests/unit/test_robohat_service_usb_control.py`. | Still hardware-sensitive by nature; treat serial timing, older-vs-newer firmware dialect differences, RC takeover, delayed/absent PWM acknowledgements, and emergency-stop behavior as regression-sensitive. |
| Camera streaming | **Beta / partial but real** | `backend/src/services/camera_stream_service.py` supports PiCamera2/OpenCV selection, simulation fallback, IPC streaming, client backpressure handling, and the FastAPI camera endpoints now return raw JPEG bytes for both snapshot and MJPEG paths. The deployed frontend server also skips compression for camera endpoints so multipart MJPEG delivery is not buffered into oblivion. | The streaming path is real, but camera ownership assumptions are still strict and per-frame AI hooks are intentionally conservative. |
| Navigation | **Partial implementation with recent safety hardening** | `backend/src/services/navigation_service.py` has path planning hooks, waypoint driving, return-home behavior, weather gating, and contract coverage such as `tests/contract/test_waypoint_navigation.py`. At each mission start a GPS COG heading bootstrap drives briefly forward (~75% throttle, up to 3 s) to derive a `session_heading_alignment` that maps the BNO085's arbitrary boot yaw to compass north; adjusted heading is `(-raw_yaw + imu_yaw_offset_degrees + session_heading_alignment) % 360`. Waypoint completion now requires a fresh, non-dead-reckoned GPS fix instead of advancing on stale synthetic position data, and live mission traversal now reuses the shared ToF clearance threshold from `config/limits.yaml` instead of a separate 1 m autonomy-only block. | Obstacle handling is still simplistic, dead reckoning still uses placeholder distance estimates rather than field-grade odometry feedback, and waypoint traversal still needs more real-world validation around heading quality and obstacle interpretation. |
| Mission orchestration | **Beta / persistence-backed and conservative by design** | `backend/src/services/mission_service.py` now validates mission payloads, enforces lifecycle transitions, persists mission metadata and lifecycle state in SQLite, recovers missions on startup, and has service/API coverage in `tests/test_mission_api.py`, `tests/unit/test_mission_service.py`, `tests/unit/test_mission_persistence.py`, and `tests/unit/test_navigation_service.py`. Pause/abort flows now retry stop delivery and escalate to emergency stop if motion cannot be halted cleanly, and missions now fail with explicit detail if autonomy cannot begin waypoint traversal after the bounded verification window. | Recovery is intentionally conservative: running missions come back paused, no active task is recreated automatically, and resume UX / live field reconciliation still need more operator-facing polish. |
| Motor service abstraction | **Legacy / partial abstraction** | `backend/src/services/motor_service.py` models safety checks, controller selection, timeout behavior, and emergency-stop flow. | The concrete controller implementations are still placeholder-heavy; the more credible live control path today is the RoboHAT bridge rather than this abstraction layer. |
| AI service | **Experimental but real** | `backend/src/services/ai_service.py` now loads a local JSON model definition, runs CPU inference on uploaded images or the latest camera frame, tracks recent results/performance, and is covered by `tests/test_ai_api.py` and `tests/unit/test_ai_service.py`. | This is a conservative first-pass inference pipeline, not production-grade perception; it is CPU-only, model quality is only as good as the configured rules/artifact, and accelerator-specific runtimes remain future work. |

Practical rule of thumb:

- build confidently on the RoboHAT USB-control and camera-streaming paths, but keep tests close
- treat navigation as usable but not fully hardened
- treat mission orchestration as persistence-backed but still conservative and not yet field-proven
- treat AI as experimentally real: safe to extend carefully, unsafe to oversell
- do not assume `MotorService` is the dominant runtime path without checking the current startup wiring first

## Important files by task

### If you are debugging startup or runtime wiring

- `backend/src/main.py`
- `backend/src/core/config_loader.py`
- `config/hardware.yaml`
- `config/limits.yaml`
- `.env`
- `docs/OPERATIONS.md`

### If you are debugging safety behavior

- `backend/src/safety/`
- `backend/src/services/motor_service.py`
- `backend/src/services/blade_service.py`
- `backend/src/services/robohat_service.py`
- `docs/constitution.md`
- `docs/hardware-integration.md`

### If you are debugging telemetry, sensors, or GPS/RTK

- `backend/src/services/sensor_manager.py`
- `backend/src/services/telemetry_hub.py`
- `backend/src/services/websocket_hub.py`
- `backend/src/services/ntrip_client.py`
- `docs/gps-ntrip-setup.md`
- `scripts/diagnose_gps_rtk.py`
- `scripts/rtk_diagnostics_watch.py`

### If you are working on manual control or the operator UI

- `frontend/src/views/ControlView.vue`
- `frontend/src/stores/control.ts`
- `frontend/src/services/api.ts`
- `frontend/src/services/websocket.ts`
- `backend/src/api/`
- `docs/RELEASE_NOTES.md`

### If you are working on maps and planning

- `frontend/src/views/MapsView.vue`
- `frontend/src/views/PlanningView.vue`
- `frontend/src/views/MissionPlannerView.vue`
- `frontend/src/stores/map.ts`
- `frontend/src/stores/mission.ts`
- `backend/src/services/maps_service.py`
- `backend/src/services/navigation_service.py`
- `backend/src/services/mission_service.py`
- `backend/src/nav/`

## Immediate focus

The biggest runtime-contract and doc-cleanup passes have landed. Treat the items below as the current
maintenance guardrails plus the remaining high-value gaps before broad new feature work.

### 1. Keep the runtime contract honest

**Why it matters:** the main port/startup drift has been cleaned up, but this is the sort of issue that quietly comes back if docs,
systemd units, Vite config, and scripts drift apart again.

**Evidence:**

- `README.md`
- `docs/OPERATIONS.md`
- `docs/TESTING.md`
- `frontend/vite.config.ts`
- `frontend/server.mjs`

**What to do now:**

- treat `8081` / `3000` / `4173` as the current contract unless you deliberately change it everywhere
- verify docs and scripts whenever startup behavior changes
- keep `backend/src/main.py` and service units as the primary runtime truth

### 2. Keep hardware scope grounded in the spec

**Why it matters:** the hardware docs are much closer to reality now, but this repo has a history of speculative hardware prose
getting ahead of the actual supported baseline.

**Evidence:**

- `docs/hallucination-audit.md`
- `docs/hardware-overview.md`
- `docs/installation-setup-guide.md`
- `docs/hardware-feature-matrix.md`

**What to do now:**

- treat `spec/hardware.yaml` as the source of truth before editing prose docs
- clearly separate supported fallbacks from future experiments
- keep unsupported hardware mentions explicitly labeled as non-baseline

### 3. Keep simulation and hardware workflows explicit

**Why it matters:** the mode model is documented much more clearly now, but developers can still accidentally assume that
“backend starts” means “hardware path is validated.” It very much does not.

**Evidence:**

- `backend/src/main.py`
- `docs/TESTING.md`
- `docs/RELEASE_NOTES.md`
- `docs/hardware-integration.md`

**What to do now:**

- keep `SIM_MODE=1` as the default recommendation for laptops and CI
- document on-device validation as a separate maintainer workflow, not “just run the app”
- check `.env`, serial devices, and I2C/UART expectations before declaring hardware regressions

### 4. Protect regression-sensitive manual control and camera paths

**Why it matters:** recent release notes show a lot of work in RoboHAT USB handshake behavior, camera stream fallback, joystick responsiveness,
and emergency-stop fail-closed behavior. Those paths are much healthier now, but they are still some of the easiest places to reintroduce field regressions.

**Evidence:**

- `docs/RELEASE_NOTES.md`
- `backend/src/services/robohat_service.py`
- `backend/src/services/camera_stream_service.py`
- frontend control/camera views and services

**What to do first:**

- treat manual control, USB takeover, MJPEG/snapshot fallback, and command-rate behavior as high-regression zones
- review related tests before refactoring
- expand targeted regression tests rather than relying on happy-path smoke testing

### 5. Clarify partially implemented subsystem status

**Why it matters:** some services exist as scaffolds or partial implementations; returning maintainers need to know which surfaces are production-grade and which are still aspirational.

**Evidence:**

- `backend/src/services/ai_service.py`
- `backend/src/services/navigation_service.py`
- `backend/src/services/mission_service.py`
- `backend/src/services/motor_service.py`

**What to do first:**

- keep the maturity labels in this handbook updated as code changes land
- avoid building new features on top of placeholder behavior without first tightening the contract
- use matching tests as part of the definition of “stable enough,” not just the existence of a service file
- remember the current practical status: navigation is safer than it was before the March 2026 hardening pass, mission recovery is real but intentionally conservative, and AI is still experimental rather than field-proven

### 6. Keep tightening frontend typing and deep-path tests

**Why it matters:** the frontend test posture is decent, but complex stateful flows still benefit from stronger typing, better recovery/fault surfacing,
and more targeted coverage around operator-critical transitions.

**Evidence:**

- `frontend/package.json`
- `frontend/playwright.config.ts`
- `frontend/src/stores/`
- `frontend/src/composables/`
- `docs/RELEASE_NOTES.md` next-steps note on TS tightening

**What to do first:**

- prioritize control/auth/map/mission flows that combine API, WebSocket, and local state
- reduce `any` usage where practical
- keep Playwright mock-backed scenarios aligned with real API behavior
- make mission recovery, lockout/fault reasons, and camera fallback behavior more obvious to operators before treating the UI as “done enough”
- current March 2026 kickoff work already surfaces recovered-paused mission detail plus richer control lockout/camera fallback status in the UI; next tighten E2E coverage and field validation rather than redoing the same UX pass
- the follow-on March 2026 slice also aligned the manual-control camera fallback code with the real backend camera contract and added focused Playwright coverage for safety lockouts, snapshot fallback, and recovered mission visibility
- the follow-on control-contract cleanup also restored real `/api/v2/control/start|pause|resume|stop|return-home|status` behavior for operator views, replacing placeholder/manual-drift paths in the UI with backend-backed navigation actions

## Practical re-entry checklist

If you are getting back into the codebase after a break, this is the shortest sane path:

1. Read `docs/RELEASE_NOTES.md`
2. Read `docs/OPERATIONS.md`
3. Read `docs/TESTING.md`
4. Check `frontend/vite.config.ts` and `frontend/server.mjs` before assuming port defaults
5. Check `spec/hardware.yaml` before trusting setup or overview docs about hardware
6. Run tests in simulation-safe mode before touching hardware
7. Pick one immediate-focus item and close the drift before starting new feature work

## Working conventions worth remembering

- Python target is 3.11
- frontend is Vue 3 + TypeScript + Pinia + Vite
- TODOs must follow the issue-linked format described in `CONTRIBUTING.md`
- when structural code changes affect callable interfaces, `docs/code_structure_overview.md` must be updated
- avoid introducing unsupported hardware assumptions without updating the spec and related docs

## Recommended next cleanup sequence

The previous three-pass recommendation (manual-control/camera hardening, then mission/navigation contracts, then AI surface work)
has effectively rolled forward. The navigation and mission-recovery parts landed meaningful work in March 2026, so the next
high-value sequence should focus on what remains instead of restating already-completed hardening as future work.

1. **AI model-quality pass**
	- keep the backend AI contract stable while improving the configured model artifact or inference rules
	- validate against real captured frames, not just synthetic or happy-path samples
	- treat accelerator-specific runtimes as optional follow-on work unless they improve reliability as well as speed

2. **Field validation and operator-feedback pass**
	- validate navigation, pause/abort, emergency-stop, and mission-recovery behavior on real hardware instead of assuming SIM success proves field readiness
	- capture where waypoint progress, obstacle response, or stop behavior still feel optimistic under real GPS/controller conditions
	- fold findings back into targeted backend hardening rather than broad speculative refactors

3. **Frontend operator clarity and regression-tightening pass**
	- make mission recovery, control lockouts, controller disconnects, and camera fallback states easier to understand from the UI
	- reduce `any` usage in high-traffic composables and stores where typing helps prevent state drift
	- add or tighten focused E2E coverage for mission pause/resume, camera fallback, and other operator-visible failure paths
	- note: the initial March 2026 slice landed typed mission/control store metadata plus clearer mission recovery, lockout, and camera-fallback UI messaging; keep building from that instead of restarting discovery
	- note: focused Playwright coverage now exists for blocked manual-control lockouts, forced snapshot fallback, and recovered-paused mission visibility; remaining work should prioritize broader recovery/controller-disconnect coverage and real-hardware confirmation

That keeps the next work focused on field credibility and operator clarity rather than reopening already-completed runtime-contract cleanup.

## Next 2 weeks: practical maintainer plan

The previous two-week plan largely landed in the March 2026 hardening pass. Use the next two weeks for field-trustworthiness work,
AI quality improvement, and operator-facing clarity instead of replaying the already-completed mission persistence / stop-path work.

### Week 1 — field validation and operator feedback

1. **Run a hardware-backed validation slice**
	- validate waypoint completion, pause/resume, abort, and emergency-stop behavior on the mower instead of only in simulation
	- explicitly compare live behavior against the March 2026 expectations: fresh GPS gating, conservative mission recovery, and fail-closed stop behavior
	- output: a short findings list tied to concrete files, logs, and tests

2. **Audit operator-visible failure reporting**
	- verify that control lockouts, controller disconnects, mission recovery state, and camera fallback behavior are obvious from the UI
	- note any places where the backend has the right state but the frontend does not surface it clearly enough
	- output: a prioritized UI/documentation gap list, not just a bug pile

3. **Fix only the highest-confidence field issues**
	- prioritize deterministic safety or operator-clarity gaps over speculative cleanup
	- prefer targeted hardening and targeted tests to broad subsystem rewrites
	- output: a small, credible set of improvements that are actually field-informed

4. **Re-run focused validation after each change**
	- run the smallest meaningful backend/frontend slice after fixes land
	- update maintainer docs immediately if field behavior or subsystem limitations changed materially
	- output: a known-good validation set for the field-informed week-1 work

### Week 2 — AI quality and frontend polish

1. **Improve AI quality behind the existing contract**
	- swap or extend the baseline CPU model artifact or inference rules without reopening the API contract
	- evaluate against a small real-image set that is representative of current mower use, not just synthetic examples
	- output: better baseline detections with the same backend surface area

2. **Tighten frontend operator-critical flows**
	- reduce `any` usage in `frontend/src/composables/` and the highest-traffic stores where better typing reduces state ambiguity
	- add or tighten coverage for mission recovery visibility, camera fallback, and control-path regressions
	- output: a smaller but safer operator UI surface

3. **Sync docs with what the field pass actually taught us**
	- update `docs/developer-toolkit.md`, `docs/RELEASE_NOTES.md`, and operator-facing docs if the field behavior or practical limitations changed
	- record limitations honestly so the next maintainer does not rebuild on wishful thinking
	- output: docs that reflect observed reality, not just design intent

### Suggested daily cadence

- **Day 1–2:** hardware-backed validation slice + findings log
- **Day 3–4:** highest-confidence safety / operator-clarity fixes
- **Day 5:** focused regression validation and doc sync
- **Day 6–7:** AI model-quality iteration behind the existing contract
- **Day 8:** frontend typing / recovery-visibility / camera-fallback tightening
- **Day 9:** targeted E2E or contract regression additions
- **Day 10:** cleanup, docs sync, backlog reshape based on field evidence

### Definition of success for this two-week pass

At the end of the two weeks, you should be able to say all of the following with a straight face:

- the field-validation pass found the next real problems instead of re-solving already-landed March 2026 work
- navigation, mission stop behavior, and recovery semantics feel at least as trustworthy on hardware as they do in simulation
- AI is still conservative, but the baseline results are better without reopening the backend contract
- operator-facing fault and recovery states are easier to interpret in the UI and docs
- maintainer docs still match the implementation and the currently believed limitations

## Deep references

Use these when you need detail instead of orientation:

- `docs/OPERATIONS.md`
- `docs/TESTING.md`
- `docs/hardware-integration.md`
- `docs/hardware-overview.md`
- `docs/gps-ntrip-setup.md`
- `docs/RELEASE_NOTES.md`
- `docs/code_structure_overview.md`
- `docs/copilot-customizations-guide.md`
- `docs/constitution.md`
- `docs/privacy.md`
- `CONTRIBUTING.md`

## Bottom line

LawnBerry Pi already has a serious amount of infrastructure in place. The fastest way to regain leverage is not to add features immediately, but to restore shared reality:

- one clear story for ports and startup
- one clear story for supported hardware
- one clear story for simulation vs real hardware
- one clear understanding of which subsystems are stable and which are still scaffolding

Once those are cleaned up, the project becomes much easier to extend safely.

## High-level next steps

After the two-week plan above, the strategic next wave should be:

1. **Field-trustworthy autonomy**
	- reduce the gap between simulated success and hardware-confirmed behavior
	- improve sensor fusion, motion verification, and obstacle response quality

2. **Persistent operator workflows**
	- make missions, calibration state, and operational context survive restarts in a safe and inspectable way
	- improve recoverability over cleverness

3. **Better onboard perception without contract churn**
	- continue improving AI quality behind the now-stable backend surface
	- add accelerators later only if they improve reliability rather than just complexity

4. **Frontend/operator clarity**
	- reflect real backend lifecycle, fault, and AI status cleanly in the UI
	- reduce ambiguity for the person driving or debugging the mower

5. **Hardware-safe validation discipline**
	- keep building targeted regression coverage around the most safety-sensitive flows
	- favor repeatable SIM-safe validation before touching live hardware
