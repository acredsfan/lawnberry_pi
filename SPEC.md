# LawnBerry Remote-Access Stability Spec

## §G — Goal

Remote UI at `lawnberry.link-smart-home.com` stays reachable and functional
across WiFi roaming events and cloudflared restarts. No manual intervention needed.

---

## §C — Constraints

- Hardware: Raspberry Pi 5, `wlan1` = external antenna (sole production client), `wlan0` = internal (disabled)
- WiFi: dual-band eero mesh "Butters Read-Link"; gateway may vary by AP/network
- Cloudflare tunnel token fixed in systemd unit; tunnel ID `cc06f475-a8e0-4418-a40d-1e3445d6cf8f`
- Frontend served by Vite dev server on :3000 (proxies `/api/*` incl. WebSocket to :8081)
- Backend FastAPI/uvicorn on :8081
- No hardware available in agent sessions (`SIM_MODE=1` for tests)
- Must not break local-network access or existing backend behaviour

---

## §I — External Surfaces

| ID | Surface | Details |
|----|---------|---------|
| I.cf | Cloudflare tunnel | `lawnberry.link-smart-home.com` → `http://localhost:3000` |
| I.ssh | SSH tunnels | `lawnberry-ssh` + `mower-ssh` → `tcp/ssh://localhost:22` |
| I.fe | Frontend | Vite dev server :3000, proxies `/api` to :8081 with `ws:true` |
| I.api | Backend REST | FastAPI :8081 `/api/v2/*` |
| I.ws | Backend WebSocket | `ws[s]://<origin>/api/v2/ws/telemetry` + `/api/v2/ws/control` |
| I.wdog | WiFi recovery | tracked `scripts/wlan1_usb_recovery.py`, `lawnberry-wifi-recovery.service`; legacy `/opt/wifi-watchdog` disabled |
| I.ops | Pi runtime | systemd units, install scripts, build SHA, service health |
| I.perception | Perception | camera frame-ID results, typed detections, semantic route costs |
| I.power | Energy | battery/SOC truth, mission reserve, return/dock decisions |

---

## §V — Invariants

| ID | Invariant |
|----|-----------|
| V1 | `cloudflared.service` must have `Restart=always` and NO `WatchdogSec` — cloudflared 2026.3.0 does not reliably send sd_notify heartbeats; WatchdogSec kills it every 120 s |
| V2 | `wifi-watchdog.service` must have `Type=simple` — `Type=notify` causes systemd to SIGTERM the process every ~90 s when sd_notify READY is never sent |
| V3 | WiFi watchdog ping list must contain NO hardcoded gateway IPs — gateway varies per AP; must be auto-detected from `ip route show dev wlan1` at runtime |
| V4 | WiFi watchdog escalation must skip disabled tiers rather than stalling — stalling means `cycle_interface`, `reset_usb_device`, and `reboot` are never reachable |
| V5 | WebSocket client `maxReconnectAttempts` must be -1 (unlimited) — a finite cap means the UI permanently breaks after N cloudflared restarts without a page reload |
| V6 | WebSocket reconnect backoff must cap at ≤ 30 s — prevents multi-minute gaps after a burst of drops |
| V7 | `ping -W` argument must be ≥ 1 — `int(800/1000) = 0` disables the timeout, causing each probe to hang until subprocess timeout |
| V8 | cloudflared tunnel must expose BOTH `:3000` (frontend) for HTTP AND have WebSocket upgrade support — Vite proxy handles WS upgrade from `/api/v2/ws/*` to :8081 only when `ws:true` is set in vite.config.ts |
| V9 | Software watchdog timeout enforcement must be armed only while a hazardous actuator source is active — idle backend/event-loop stalls must not latch `watchdog_timeout`, but armed drive/blade control must still E-stop on missed heartbeats |
| V10 | ToF XSHUT pair initialization must release both shutdown GPIOs high on any failure, and live hardware mode must not report ToF `online` unless each VL53L0X driver has an initialized running backend |
| V11 | Heading bootstrap tests and runtime must respect the configured travel budget — bootstrap may only continue past the budget when the test explicitly raises the budget; runtime must abort if heading is not acquired before the budget expires |
| V12 | Dynamic obstacle-clearance code must preserve legacy threshold-only limits objects exactly; the stopping-distance model is active only when the full obstacle model fields are present |
| V13 | Emergency stop triggering must be idempotent when the latch is already active and the blade is already inactive — repeated E-stop calls must keep the safety latch active without reporting a delivery failure |
| V14 | Battery safety evaluation must use the live UI safety-limit object and a configured battery-voltage source; when Victron is the preferred battery source, missing Victron voltage must not fall back to low-side INA3221 bus voltage |
| V15 | Health endpoint helper functions must remain callable without a FastAPI `Request` object; runtime request context may refine evaluation, but direct fallback calls must still use the module health service |
| V16 | Hardware config management must fail closed when legacy `config/hardware.local.yaml` exists outside `migrate-legacy`, and any `migrate-legacy` failure after backups begin must restore the original `hardware.yaml`/`hardware.local.yaml` state |
| V17 | Transient manual-drive safety lockouts must stop motion without clearing the unlocked manual-control session, and zero-vector stop commands must remain dispatchable while non-zero motion is locked out |
| V18 | Raw VL53L0X readings outside the positive in-range interval (`<=0` or `>=8190` mm) must be represented as `None`/`no_target` before telemetry, safety, obstacle, or manual-drive gating consumes them |
| V19 | Zero-vector drive commands must cancel existing drive leases without scheduling a new delayed auto-stop; only motion-active drive commands may arm a future lease-expiry stop |
| V20 | Manual-drive near-field obstacle gating must use the operator-configured `tof_obstacle_distance_meters` cutoff; autonomous stopping-distance clearance fields must not silently override the manual UI cutoff |
| V21 | Zero-vector manual stop commands must bypass telemetry and obstacle interlocks, and idle live safety must not latch `obstacle_detected` from the autonomous clearance model when no hazardous actuator is active |
| V22 | The WebUI motor-connected/queued banner must reconcile from the authoritative RoboHAT status poll, not only from drive command responses |
| V23 | Blade-capable manual/autonomous mission and scheduler entry must require current physical qualification evidence bound to commit SHA, sanitized hardware config hash, limits hash, runtime identity, and RoboHAT firmware; missing, stale, mismatched, failed, interrupted, simulation, or dirty-tree evidence fails closed with explicit reason codes |
| V24 | Blade-off diagnostic missions must be explicit, must reject any `blade_on=true` waypoint, and must not bypass zero-stop or emergency-stop access; active blade commands remain blocked unless qualification evidence is current |
| V25 | JWT signing must use PyJWT 2.13-compatible HS256 encode/decode with an explicit algorithm allow-list and the persistent secrets-manager `JWT_SECRET`; missing or empty canonical secrets must fail closed instead of generating a process-local secret |
| V26 | Repository-root `openapi.json` is the canonical API snapshot and must match deterministic `SIM_MODE=1 LAWNBERRY_SKIP_HW_INIT=1` generation on every reviewed revision |
| V27 | Missing user-owned `config/hardware.yaml` must remain a `critical` health blocker unless a test installs an explicit deterministic simulation fixture; tests must not make missing production hardware config appear healthy |
| V28 | The synthetic straight-drive fixture, replay library, and replay CLI must use one canonical heading/coordinate convention and reproduce exact navigation state without relaxing the `1e-07` parity contract |
| V29 | Qualification evidence ingestion must validate server-observed clean hardware context, exact bindings, unique required passed stages, and cleanup evidence; client-supplied flags alone must never authorize hazardous operation |
| V30 | Qualification record and artifact identifiers used as filenames must be schema-constrained to path-safe values; client input must not escape evidence storage directories |
| V31 | Performance tests must time the system operation under test and exclude mock/test-fixture construction from the measured budget |
| V32 | Boundary-point verification motion must use the canonical blade-off diagnostic mission and motor-authorization path, target only a validated stand-off point inside the authoritative operating area, require explicit physical blade-disable acknowledgement before motion, and command zero drive plus blade off on every terminal path |
| V33 | A boundary point may be confirmed only after the verification mission reaches its stand-off target, motion is stopped, and a fresh unique-sample stationary RTK average records antenna and body-center coordinates plus target residual; persisted session and mission state must reconcile safely after process restart and drive the UI state |
| V34 | GPS freshness must be derived from immutable sample identity and acquisition time: cached fallback readings must preserve the prior sample ID and timestamp, must never report zero age or refresh the canonical last-fix time, and a stale serial owner must close and reopen the device to recover live acquisition |
| V35 | Manual ToF cutoff, autonomous front-sensor stopping clearance, safe-boundary additional inset, mower footprint, and localization accuracy are distinct safety quantities; front-sensor range must not add the center-to-sensor offset again, autonomous clearance must remain speed-dependent, and the safe-boundary inset must not duplicate footprint containment |
| V36 | Safe-boundary generation without client-supplied coordinates must resolve the same authoritative persisted boundary zone shown by the Maps UI; it must not depend on one historical hardcoded zone ID |
| V37 | The backend's single GPS owner must continue acquiring samples without status/UI demand; an explicitly configured USB GPS must retain or promptly reacquire its reader through NMEA gaps, stale lock contention or read exceptions must force bounded recovery, and status must expose acquisition/recovery state without taking a read |
| V38 | Localization and navigation must read and write one canonical heading-alignment record; reusable evidence must have a finite heading, an allowlisted source, a nonfuture timestamp, and the actual current BNO085 reset generation issued only after a successful sensor reset/reopen; cached quaternion values must never refresh receipt freshness, autonomous use requires a genuinely new SHTP game-rotation report, an in-process IMU reinitialization must invalidate alignment immediately, and stale evidence must never be rebound or re-saved under the new generation; startup may promote a newer authoritative legacy snap without refreshing its acquisition timestamp, but must never let a stale/reset artifact override a newer record |
| V39 | Boundary verification mutations and status reconciliation must share one serialized admission boundary so one operator action creates at most one leg and polling cannot interrupt an in-flight admission; physical safety acknowledgements must be freshly entered for each session, and the UI may report travel only after asynchronous mission admission survives heading alignment; verification must reuse valid canonical evidence or enter an explicitly acknowledged blade-off bootstrap that requires unique non-cached GPS frames acquired after bootstrap start plus fresh live IMU reports, carries an explicit bootstrap command tag through `MotorCommandGateway`, stays inside a direction-independent footprint/uncertainty/antenna-offset/travel envelope with lease-and-braking reserve, stages heading evidence until minimum travel and a gateway-confirmed controller stop both succeed, fails closed if stop is unconfirmed, and exposes terminal errors after the active target clears |
| V40 | Position-derived GPS course-over-ground must accumulate displacement from a stable unique live-sample baseline until the configured motion threshold is reached; duplicate polls and sub-threshold low-speed frames must not consume that baseline, a qualified displacement or an explicit localization reset may advance it, and the blade-off bootstrap's COG speed floor must admit the reference mower's measured crawl while displacement, unique-frame, and straightness gates continue to reject stationary drift |
| V41 | The documented `JobsService` compatibility execution path for mower jobs must dispatch through the canonical `MissionService` and retain the linked mission identity; `last_run` may advance only after `MissionService` accepts the start, while `COMPLETED`, `completed_at`, 100% progress, and success text may be recorded only after that same mission reaches `COMPLETED`; blocked, rejected, failed, aborted, cancelled, or unsupported execution must remain an explicit non-success and must never advance through synthetic timed steps |
| V42 | The standalone camera-stream service must remain the sole live camera-device owner and expose frames over shared IPC; automatic camera AI processing in that owner must invoke an injected inference service with the exact frame bytes and frame ID, sample at a bounded cadence within the single latest-frame consumer, run CPU inference work off the event loop, and enforce a bounded frame-delivery wait with at most one tracked inference still in flight so no stale backlog or concurrent worker accumulation occurs; `processed_for_ai=true` is permitted only after a timely successful result whose annotations derive from that result, while disabled, skipped, unavailable, failed, timed-out, late, or frame-mismatched inference must remain truthfully unprocessed with no hardcoded or dummy detections; live hardware-init fallback and missing IPC topology metadata must report a fail-closed simulated/non-hardware state through the real client and API; camera AI results remain informational only unless a separate safety/navigation contract explicitly promotes them |
| V43 | Return-to-base must be a canonical blade-off mission through `MissionService`, `MissionExecutor`, and `MotorCommandGateway`; no safe route must fail closed, and success requires terminal arrival plus dock/charge confirmation |
| V44 | Blade intent belongs to traversed path legs, not destination arrival; `TRANSIT`, `TURN`, `WAIT`, and `DOCK` legs are blade-off, ambiguous legacy input defaults blade-off, and blade-on is allowed only on validated `MOW` legs |
| V45 | Live mission admission must consume one canonical snapshot containing qualification, runtime/controller, fresh RTK pose, heading, operating area/path, obstacle, weather, mission conflict, and energy reserve state; missing wiring or evaluation errors fail closed |
| V46 | GPS degradation must be one mission-owned state machine with fresh-sample loss detection, bounded hold/dead-reckoning policy, gateway-enforced caps, hysteretic recovery, alerts, and terminal stop/return behavior |
| V47 | ToF hardware must have one continuous timestamped acquisition owner; safety and telemetry consume immutable samples, and readiness must enforce per-sensor freshness plus bounded timeout/failure rate without competing I2C reads |
| V48 | Operator UI may report start/pause/resume/cancel/unlock success only after authoritative server acceptance and reconciled state; HTTP errors, unsupported methods, stale data, and local-only mutations remain explicit non-success |
| V49 | Coverage planning must erode free space by footprint, uncertainty, and configured clearance; every mow row and blade-off connector must stay inside that same geometry, and preview/admission must use identical margins and declared capabilities |
| V50 | Obstacle response must stop first, classify transient/persistent evidence, bound wait, update a local cost map, and safely replan or escalate; AI may alter semantic cost but cannot bypass geometric, ToF, or gateway safety |
| V51 | Production perception must use a real configured detector runtime with typed frame-ID/timestamped results, model provenance, latency/freshness, truthful unavailable state, and no fabricated datasets/training/export; UI and route costs consume only current validated results |
| V52 | One battery-state/energy service must own source provenance, freshness, SOC, reserve, history, and mission forecasts; mission start and runtime preserve return reserve, low energy initiates canonical return before hard stop, and INA3221 channel mapping matches verified hardware spec |
| V53 | Scheduled job occurrences must be durable and idempotent; multi-zone jobs own ordered child missions and blade-off inter-zone transit, terminal truth aggregates from those missions, and failed admission cannot create retrying orphan missions |
| V54 | Runtime/UI truth must expose deployed build SHA and sample age/source; missing numeric telemetry stays unknown, inert services cannot report healthy work, and unsupported features are hidden or explicitly unavailable |
| V55 | Critical autonomy, GPS-loss, power, perception, and operator-control flows must have non-placeholder blocking tests; OpenAPI operation IDs stay unique, generated schema stays current, and repository lint is clean |
| V56 | Response sanitization must preserve intentional signed-token fields on authentication exchange routes while continuing to redact unrelated secrets; issued tokens must work for unlock and refresh |
| V57 | Cloudflare Access bootstrap must verify an RS256 assertion against a pinned team issuer, application audience, expiry, and rotating JWKS before deriving identity; the UI exchanges that identity once before showing local login, and authentication-endpoint 401 responses must never recurse through token refresh or consume local-password lockout budget |
| V58 | The single camera owner must remain active for a mission or fresh operator frame/stream demand, power management must not pause an active Control-page viewer, and camera URLs/logs must never carry a manual-control session credential |
| V59 | Camera IPC cancellation must retire the affected connection before another command can reuse it, the owner socket must not be world-accessible, and a healthy MJPEG viewer must not be churned by a timer |
| V60 | Camera idle timeout is one total deadline from the last viewer demand, and every mission-active power tick must idempotently restore capture even after an external stop, owner restart, or camera fault |
| V61 | Cloudflare authentication must bound unknown-key refresh and session growth, preserve signed identity across restart, load runtime verifier settings before use, and share one reactive refresh coordinator; production login lockout keys must not be spoofable through proxy headers |
| V62 | The camera owner detector deadline must accommodate the validated Raspberry Pi inference path while remaining bounded, and model readiness must not be reported as operational unless automatic inference can publish a fresh result within that contract |
| V63 | AI soft-disable transitions must be symmetric: whenever the dark, stationary, mission-inactive disable predicate clears through daylight, motion, viewer demand, or a mission, the camera owner must re-enable inference |
| V64 | A hardware-requested camera that cannot open real hardware must remain fail-closed for perception; synthetic fallback frames must never be published or ingested as fresh live-world detections |
| V65 | When MJPEG recovers after snapshot fallback, the UI must stop snapshot polling, revoke the fallback object URL, and prevent an in-flight fallback response from restoring redundant camera demand |
| V66 | The canonical mission-start path must wake camera capture and owner-side AI before autonomous motion authorization rather than waiting for a periodic power-management tick |
| V67 | In hardware mode, AI re-enable succeeds only after the camera owner acknowledges it; a local metadata update must not hide an IPC failure, and later ticks or mission startup must retry |
| V68 | Camera-feed lifecycle completion must be generation-bound so an in-flight start or recovery cannot recreate MJPEG or snapshot timers after the Control view stops or unmounts |
| V69 | Production v1 and v2 login must validate only the credential actually supplied; no known default such as admin/admin may be substituted for the configured operator secret, advertised by the UI, or preserved by compatibility routes |
| V70 | Logout and concurrent-session eviction must revoke the signed session ID until its JWT expires, including across process restart, so token restoration cannot resurrect a terminated session |
| V71 | A Cloudflare-authenticated LawnBerry session and token must not outlive the verified Access assertion, and refresh must reverify a matching signed Cloudflare principal rather than extending upstream authorization locally |
| V72 | Hardware-mode WebSockets must require authenticated proof even when the TCP peer is loopback; proofless loopback access is limited to explicit simulation/test paths, and browser transport must not depend on credentials in logged URLs |
| V73 | Global rate-limit state must be isolated by client and effective route policy so the bounded Cloudflare bootstrap bucket cannot consume or shrink the normal page-load API budget |
| V74 | Scheduled job dispatch must fail before claiming an occurrence when canonical MissionService ownership is not wired; dependency misconfiguration must not be converted into a durable skipped mowing occurrence |
| V75 | A manual motor-control session derived from a verified bearer or Cloudflare assertion must expire at the earliest of the configured manual-session timeout and the upstream token expiry; identity expiry must immediately end actuator authorization |
| V76 | The persisted JobsService scheduler must start only after PowerManager is running and must stop before live safety, power, sensor, camera, or motor dependencies are torn down; a boot or shutdown ordering race must never consume or launch a mowing occurrence without its canonical safety dependencies |
| V77 | PowerManager daylight classification must use a wrap-normalized solar equation of time derived from right ascension; the equation must remain within physical bounds, a summer afternoon at the mower locale must not be classified as dark, and local night must remain below the civil-twilight threshold |
| V78 | Production request quotas and login lockouts must distinguish real clients across the local frontend proxy without trusting arbitrary browser forwarding headers: the frontend may accept a validated Cloudflare or reverse-proxy client IP only from a loopback peer, must replace any inbound canonical header, and the backend may trust that canonical hop only from a loopback TCP peer |
| V79 | Manual-control grants derived from a bearer token or Cloudflare assertion must remain bound to the canonical authentication session and become unusable when that session ends, while password/TOTP grants keep their independent timeout; authentication termination may succeed only after fsync-backed atomic revocation persistence whose high-water covers every same-SID token issued before termination even when restart restored an older sibling first, and an unreadable, corrupt, or unwritable registry must deny token-backed authorization across restart |
| V80 | Frontend token-refresh scheduling must never synchronously recurse into the active single-flight refresh promise; short-lived or non-advancing Cloudflare-capped expiries must settle one refresh, schedule bounded future work, and never create a self-wait or immediate request loop |
| V81 | A successful snapshot fallback image load must remain classified as snapshot delivery and keep its object URL and polling lease alive; only a successful primary MJPEG load may clear fallback state and claim stream recovery |
| V82 | Mission lifecycle admission must be serialized across the single mower: concurrent start/resume/pause/abort/delete transitions must recheck canonical state inside one lock, no two missions may own motion simultaneously, and concurrent starts for one mission may create exactly one tracked navigation task |
| V83 | Tracked on-device systemd units must execute from the canonical `/home/pi/lawnberry` deployment tree; installing a tracked unit must not redirect the frontend to an absent legacy `/apps/lawnberry-pi` path |
| V84 | Platform health must not equate an online IMU transport with usable heading: the latest calibration state must flow from the canonical sensor owner, and an online `uncalibrated` IMU must degrade the health rollup while autonomy remains fail-closed |
| V85 | Every persisted mission-definition mutation must share the mower-wide lifecycle lock with admission and control transitions: create, update, return-home creation, single/bulk delete, start, resume, pause, and abort may not interleave after safety/blade validation, and no navigation task may outlive its canonical mission record |
| V86 | Navigation-task terminalization must acquire the mower-wide lifecycle lock, confirm that the completed task is still the mission's exact owned task, and win over stale pause/resume work after awaited hardware or power operations; a terminal mission may never be overwritten as paused or restarted from a stale transition |
| V87 | Canonical and persisted mission status must report exactly 100 percent for `COMPLETED` while retaining the last valid zero-based waypoint index; persistence normalization must not reinterpret that index as an incomplete ratio |
| V88 | Asynchronous lifecycle tests must await an explicit state, event, or owned task rather than a hard-coded count of `sleep(0)` scheduler turns, so adding a legitimate lock or delivery task cannot create timing-dependent false failures |
| V89 | Blade qualification has two fail-closed levels: a current schema-v2 prerequisite record may authorize one local, authenticated, session/context-bound `supervised_blade_enabled` test permit only through `MotorCommandGateway` under explicitly approved speed, duration, and lease limits; ordinary blade commands, missions, and schedules require current artifact-backed supervised-stage evidence plus a confirmed permit cleanup receipt, while schema-v1, simulation, restart, expiry, reuse, concurrent ownership, context drift, safety faults, or unconfirmed commands revoke the permit and retain or command neutral drive plus blade off; advisory camera/AI evidence cannot replace or block independent safety gates |
| V90 | Production WiFi uses only external `wlan1` with `wlan1-primary`; recovery must distinguish missing USB, missing interface, association/IP failure, and upstream reachability, then use bounded cooldowns to touch only USB adapter `2357:0138`, its configured physical port/driver, and that NetworkManager profile; it must never reboot the Pi, restart NetworkManager globally, reset unrelated USB devices/ports, promote `wlan0`, or treat an upstream probe failure alone as radio loss |
| V91 | While NetworkManager reports `wlan1` in a transitional device state (`40 <= GENERAL.STATE < 100` or `GENERAL.STATE == 110`), recovery must wait and must not issue a competing profile activation; it may activate `wlan1-primary` only after NetworkManager reports a disconnected or failed state, so recovery cannot cancel or race an in-flight association, secret exchange, or deactivation |
| V92 | Selecting Maps boundary edit must retain the saved geometry as one stable editable draft; cancelling verification must remove its terminal error presentation, and changing or deleting a boundary must reject an active verification while removing its derived safe geometry, verification session, and cached authorization state |
| V93 | Maps must clearly separate the imported parcel helper from the saved mowing boundary: deleting the saved boundary preserves the helper, and selected map-point controls may remove one draft vertex only while at least three points remain |

---

## §T — Tasks

| id | status | description | cites |
|----|--------|-------------|-------|
| T1 | ✓ done | `Type=notify` → `Type=simple` in wifi-watchdog.service | V2 |
| T2 | ✓ done | Fix ping gateway: auto-detect via `get_default_gateway()` in connectivity.py | V3 |
| T3 | ✓ done | Fix escalation skip-disabled bug in escalation.py | V4 |
| T4 | ✓ done | Fix `ping -W 0` → `max(1, …)` in connectivity.py | V7 |
| T5 | ✓ done | Add `Restart=always` to cloudflared.service | V1 |
| T6 | ✓ done | Remove `WatchdogSec=120s` from cloudflared.service | V1 |
| T7 | ✓ done | Set `maxReconnectAttempts = -1` and cap backoff at 30 s in websocket.ts | V5, V6 |
| T8 | ✓ done | Verify Vite `ws:true` proxy survives Cloudflare's HTTP upgrade path; add integration smoke-test | V8, I.cf |
| T9 | ✓ done | Add wifi-watchdog unit test: assert disabled tier is skipped, not stalling | V4 |
| T10 | ✓ done | Commit and push all service-file + watchdog source changes made today | V1–V4, V7 |
| T11 | ✓ done | Make safety watchdog motion-armed and add regression tests for idle vs armed timeout behavior | V9 |
| T12 | ✓ done | Fix VL53L0X XSHUT cleanup, propagate ToF timing config, and fail ToF health closed when no backend attaches | V10 |
| T13 | ✓ done | Allow repeated emergency triggers after blade-off confirmation and cover the idempotent latch path in command-gateway tests | V13 |
| T14 | ✓ done | Hot-reload runtime safety limits from `/settings/safety` and block INA battery-voltage fallback when Victron is configured as preferred | V14 |
| T15 | ✓ done | Keep manual-control unlock state during transient obstacle lockouts and allow zero-vector stop dispatch under lockout | V17 |
| T16 | ✓ done | Filter invalid zero/no-target ToF readings before driver cache, sensor interface, obstacle detection, live safety, and manual-drive gating | V18 |
| T17 | ✓ done | Make zero-vector stops lease-cancel-only and permit frontend zero stops through active lockout state | V17, V19 |
| T18 | ✓ done | Split operator ToF cutoff from autonomous obstacle clearance and use the operator cutoff for manual-drive gating | V20 |
| T19 | ✓ done | Let zero manual stops skip backend interlocks and stop idle live safety from latching autonomous obstacle clearance | V21 |
| T20 | ✓ done | Clear stale queued/disconnected UI state from `/api/v2/hardware/robohat` serial status refreshes | V22 |
| T21 | ✓ done | Add fail-closed autonomy qualification evidence model, API, runner, mission/scheduler/blade gates, blade-off diagnostic path, and readiness UI remediation | V23, V24 |
| T22 | x | Merge PyJWT 2.13 dependency/CI changes and add focused round-trip, expiration, signature, algorithm, and missing-secret tests | V25 |
| T23 | x | Generate and commit canonical `openapi.json`; verify deterministic snapshot parity | V26, I.api |
| T24 | x | Align health endpoint tests with the fail-closed missing-hardware-config contract | V27, I.api |
| T25 | x | Fix synthetic navigation replay parity at the canonical heading/coordinate source | V28 |
| T26 | x | Reject fabricated or context-mismatched passing qualification evidence and require valid cleanup/stage structure | V23, V29, I.api |
| T27 | x | Constrain qualification record/artifact identifiers and test traversal rejection | V30, I.api |
| T28 | x | Remove `AsyncMock` construction and synthetic header behavior from the WebSocket connection benchmark window | V31, I.ws |
| T29 | x | Make GPS status freshness truthful and recover live acquisition by reopening a stale owner handle | V34, I.api |
| T30 | x | Recalibrate autonomous front-sensor clearance and safe-boundary inset semantics without weakening footprint containment | V35 |
| T31 | x | Replace direct boundary waypoint motion with a restart-safe blade-off diagnostic workflow, stationary RTK evidence, and status-driven UI | V32, V33, I.api |
| T32 | x | Resolve coordinate-free safe-boundary generation from the current persisted boundary zone | V36, I.api |
| T33 | x | Keep GPS acquisition continuously active, bound configured-USB reacquisition, and expose owner suspend/lock/open recovery diagnostics | V34, V37, I.api |
| T34 | x | Unify heading-alignment ownership and make boundary bootstrap/admission plus asynchronous UI failure state truthful | V11, V24, V32, V33, V38, V39, I.api |
| T35 | x | Preserve low-speed GPS displacement across unique frames so the bounded boundary-verification bootstrap can acquire COG before exhausting its travel reserve | V39, V40 |
| T36 | x | Route documented `JobsService` compatibility execution through `MissionService`, retain linked mission identity, project terminal truth, and add accepted-start, terminal-state, unsupported, and non-success regression coverage | V41, I.api |
| T37 | x | Wire exact-frame inference into the standalone camera owner, keep live FastAPI access on shared IPC, and enforce bounded sampling/single-flight delivery, off-event-loop CPU work, truthful annotations and owner topology, no dummy detections, informational-only isolation, and regression coverage | V42, I.api |
| T38 | x | Build canonical fail-closed return-home and blade-safe typed path legs | V43, V44, I.api |
| T39 | x | Build footprint-safe coverage, connectors, capabilities, obstacle cost map, and bounded replan | V49, V50, I.api |
| T40 | x | Build canonical admission snapshot and GPS degradation state machine | V45, V46, I.api, I.ws |
| T41 | x | Build single-owner timestamped ToF acquisition and failure-rate readiness | V47, I.api, I.ws |
| T42 | x | Make mission/manual operator mutations server-authoritative and fail-closed | V48, I.api, I.fe |
| T43 | x | Build durable idempotent multi-zone job occurrences and truthful planning controls | V48, V53, I.api, I.fe |
| T44 | x | Build canonical battery/SOC/energy reserve, return policy, history, and hardware mapping | V43, V45, V52, I.api, I.power |
| T45 | x | Build real detector runtime, typed perception stream, semantic costs, and truthful AI console | V50, V51, I.api, I.ws, I.fe, I.perception |
| T46 | x | Make telemetry, planning, readiness, power, connection, and build UI truthful | V48, V54, I.fe, I.api, I.ws |
| T47 | x | Remove green-but-inert services and unsupported API/ops success paths | V54, I.ops, I.api |
| T48 | x | Replace critical placeholder tests, run frontend tests in CI, fix OpenAPI IDs, and clean lint | V55, V56, I.api, I.fe, I.ops |
| T49 | x | Update OpenAPI, hardware/runtime docs, structure overview, and qualification handoff | V43–V56, I.api, I.ops |
| T50 | x | Repair verified Cloudflare bootstrap and auth retry/lockout behavior, preserve active camera-view demand, harden camera IPC/power recovery, deploy the canonical camera units, provision/validate a real local detector manifest plus ONNX artifact, keep live IMU health truth fail-closed, and serialize mission definition/lifecycle mutations | V42, V51, V57–V88, I.api, I.fe, I.perception, I.power |
| T51 | x | Build schema-v2 two-phase blade qualification, a bounded one-test supervised permit, canonical gateway/lifecycle revocation, staged UI/API/runbook truth, and regression coverage | V23, V24, V26, V29, V44–V48, V53, V55, V74, V76, V82, V85, V89, I.api, I.fe, I.ws, I.ops |
| T52 | x | Replace the legacy reboot-capable WiFi watchdog with tracked, USB-aware `wlan1` recovery; recover `2357:0138`, make `wlan1-primary` authoritative, disable `wlan0`, and prove bounded non-destructive recovery | V90, V91, I.wdog, I.ops |
| T53 | x | Repair Maps boundary editing, cancellation cleanup, and source-boundary lifecycle cleanup | V92, I.api, I.fe |
| T54 | x | Separate Maps parcel-helper and saved-boundary deletion, and restore selected-point deletion controls | V93, I.fe |

---

## §B — Bug Log

| id | date | cause | fix |
|----|------|-------|-----|
| B1 | 2026-05-12 | `Type=notify` in wifi-watchdog.service; Python never sends sd_notify READY → systemd SIGTERM loop every ~90 s | V2, T1 |
| B2 | 2026-05-12 | Hardcoded gateway `192.168.50.1` always unreachable → watchdog permanently LOST, never fires recovery | V3, T2 |
| B3 | 2026-05-12 | Escalation `maybe_escalate` returned None on disabled tier without advancing index → `cycle_interface`/`reboot` unreachable | V4, T3 |
| B4 | 2026-05-12 | `int(800/1000) = 0` passed to `ping -W` → per-host probe had no timeout | V7, T4 |
| B5 | 2026-05-12 | cloudflared process stayed alive after losing all QUIC connections; `Restart=on-failure` never triggered | V1, T5 |
| B6 | 2026-05-12 | `WatchdogSec=120s` added to cloudflared.service; cloudflared 2026.3.0 stops sending watchdog pings after startup → SIGABRT every 2 min | V1, T6 |
| B7 | 2026-05-12 | `maxReconnectAttempts=5`; after burst of cloudflared crashes the WS client gives up permanently → UI broken until hard-reload | V5, T7 |
| B8 | 2026-06-18 | Backend safety watchdog was armed continuously, so an idle event-loop stall from camera/telemetry work latched `watchdog_timeout` even with no hazardous actuator active | V9, T11 |
| B9 | 2026-06-22 | VL53L0X pair-address failure could leave GPIO22 XSHUT low while ToF health still reported online with no attached backend | V10, T12 |
| B10 | 2026-06-23 | Existing bootstrap sensor-manager test simulated ~2 m travel while the new bounded bootstrap default allows 0.6 m, hiding whether the runtime guard actually aborts over-budget heading acquisition | V11 |
| B11 | 2026-06-23 | Dynamic obstacle-clearance defaults were applied to test/minimal limits objects that only defined `tof_obstacle_distance_meters`, changing legacy threshold semantics | V12 |
| B12 | 2026-06-24 | Re-triggering E-stop after the blade was already inactive could be reported as a delivery failure even though the safety latch remained active | V13, T13 |
| B13 | 2026-06-25 | Live critical-battery safety could trip on 0.17 V low-side INA3221 fallback while `/settings/safety` updates did not replace the runtime safety-limit object until restart | V14, T14 |
| B14 | 2026-06-25 | Health route handlers required FastAPI `Request` objects after runtime-context injection, breaking direct unit-call coverage for the same endpoint behavior | V15 |
| B15 | 2026-06-30 | Hardware config `ensure`/`validate` could hide a legacy `hardware.local.yaml`, and `migrate-legacy` did not restore originals if a post-backup write or final validation failed | V16 |
| B16 | 2026-07-09 | Frontend treated transient `OBSTACLE_DETECTED` manual-drive lockouts as a full manual-control lock, clearing the session and forcing the operator to re-enter the password after every obstacle block | V17, T15 |
| B17 | 2026-07-09 | Raw VL53L0X zero/no-target glitches were cached and published as valid `0 mm` readings, causing false `OBSTACLE_DETECTED` manual-drive lockouts when the path was clear | V18, T16 |
| B18 | 2026-07-09 | Zero-vector manual stops scheduled a delayed backend drive-lease stop, so the pre-turn stop could fire about 500 ms into a preset turn and make 45/90 degree buttons barely move the mower | V19, T17 |
| B19 | 2026-07-09 | Manual-drive gating reused the autonomous stopping-distance clearance floor, so an operator-set 1 inch ToF cutoff still blocked clear-path readings around 0.5 m | V20, T18 |
| B20 | 2026-07-09 | Backend zero stops still ran manual safety interlocks, and idle live safety could latch `obstacle_detected` from the autonomous clearance model before any hazardous actuator was active | V21, T19 |
| B21 | 2026-07-09 | The WebUI queued/disconnected banner could remain stale because `motorConnected` was updated from drive command responses but not from the RoboHAT status poll | V22, T20 |
| B22 | 2026-07-10 | Qualification evidence POST trusted client-supplied `sim_mode`, dirty-tree, binding, and stage status fields, so a fabricated passing record could authorize hazardous operation | V29, T26 |
| B23 | 2026-07-10 | Qualification API routes changed the generated schema without regenerating repository-root `openapi.json`, so the committed API contract drifted | V26, T23 |
| B24 | 2026-07-10 | Health contract regression test asserted a nonexistent top-level hardware `detail` instead of the stable configuration entry in `drivers.checks` | V27, T24 |
| B25 | 2026-07-10 | Startup validated persistent `JWT_SECRET`, but `JWTManager` ignored it and generated a process-local signing key, causing restart drift and bypassing missing-secret validation | V25, T22 |
| B26 | 2026-07-10 | Missing-secret regression test inherited the session fixture's `JWT_SECRET`, so it tested the configured path instead of the absent-secret path | V25, T22 |
| B27 | 2026-07-10 | Removing secrets-manager auto-generation also removed the module import still used by API-key generation, which changed-file Ruff caught as an undefined name | V25, T22 |
| B28 | 2026-07-10 | Editing shared test fixtures brought stale unused and unsorted imports into incremental Ruff scope | V25, V27, T22, T24 |
| B29 | 2026-07-10 | Qualification record and artifact IDs were interpolated into filesystem paths without schema constraints, allowing path separators in client input | V30, T27 |
| B30 | 2026-07-10 | Health contract patched only the config path, so prior tests could leave cached hardware/config-loader objects that bypassed the intended missing-config branch | V27, T24 |
| B31 | 2026-07-10 | WebSocket scalability benchmark started timing before `AsyncMock` creation and used async mock headers unlike Starlette's synchronous mapping, making Pi load appear as connection latency | V31, T28 |
| B32 | 2026-07-10 | Pre-commit scanner treated local `configured_secret` variable assignments as credential literals and blocked the verified commit | V25, T22 |
| B33 | 2026-07-10 | Synthetic navigation fixture generation and replay implicitly loaded ignored host `config/hardware.yaml`, baking the Pi's antenna offset into the golden output while clean CI used neutral defaults | V28, T25 |
| B34 | 2026-07-10 | Optional-dependency fallback prepended the entire compatibility-stub directory after an earlier missing import, allowing the JWT stub to shadow installed PyJWT 2.13 in clean CI | V25, T22 |
| B35 | 2026-07-10 | Synthetic fixture generation loaded the host's persisted IMU alignment and appended to an existing golden JSONL, so regeneration was neither host-independent nor idempotent | V28, T25 |
| B36 | 2026-07-10 | The GPS driver could return one cached fix forever without recycling a silent serial handle, while the status endpoint hardcoded `last_read_age_s=0.0` and made an old sample look live | V34, T29 |
| B37 | 2026-07-10 | Autonomous obstacle clearance added the mower-center-to-front-sensor offset to a distance already measured from that front sensor and imposed a 0.55 m floor at every speed | V35, T30 |
| B38 | 2026-07-10 | Safe-boundary generation defaulted to a 0.75 m inset and operating-area validation then applied the mower footprint and accuracy allowances again, duplicating containment clearance | V35, T30 |
| B39 | 2026-07-10 | Boundary verification sent direct navigation waypoints at the recorded boundary, bypassing diagnostic mission preflight and cleanup while targeting a location the mower center cannot safely occupy | V32, V33, T31 |
| B40 | 2026-07-10 | Coordinate-free safe-boundary generation looked up only the legacy ID `confirmed_mowing_boundary`, while the current Maps UI persisted a valid boundary under a generated ID and the API returned 422 | V36, T32 |
| B41 | 2026-07-10 | PowerManager intentionally suspended GPS after its dark-and-idle check while its mission wake hook was unused and motion detection read obsolete GPS/IMU fields, creating a stale-fix preflight deadlock; driver probe/lock recovery and status also lacked enough evidence to distinguish suspension from serial failure | V34, V37, T33 |
| B42 | 2026-07-13 | Localization wrote a fresh GPS COG snap to legacy `imu_alignment.json` while navigation admission read stale `calibration.json`; after admission, the headingless bootstrap used an untagged normal mission command that the swept-motion gateway rejected, ignored the first rejection, and had equal default minimum/maximum travel; repeated Adafruit IMU/GPS cache values could be mislabeled as fresh, an in-process BNO reset could inherit alignment, heading evidence was persisted before minimum travel or confirmed stop, the cleanup stop bypassed the gateway, concurrent next-point clicks could create duplicate legs, unlocked polling could interrupt an in-flight admission, checklist acknowledgements survived into later sessions, and the UI already reported point travel while clearing the only visible error pointer | V38, V39, T34 |
| B43 | 2026-07-14 | Position-derived COG advanced its comparison baseline on every unique GPS frame even when each low-speed step was below the 0.15 m derivation threshold, and its 0.10 m/s speed floor exceeded the reference mower's observed roughly 0.08 m/s crawl; valid displacement therefore never became a heading sample and the boundary bootstrap exhausted its bounded travel reserve | V40, T35 |
| B44 | 2026-07-14 | A legacy `JobsService` compatibility executor retained a parallel ten-step timer that could report completion and success without a linked mower mission; the first replacement also started the scheduler before admission dependencies were injected and left accepted dispatch recording behind blocking WebSocket delivery | V41, T36 |
| B45 | 2026-07-14 | `CameraStreamService` marked frames AI-processed and emitted hardcoded simulation grass while real inference existed only on separate on-demand endpoints; the first attempted bridge injected a different in-process FastAPI singleton instead of the deployed standalone camera owner, `PowerManager` plus overrideable systemd mode settings could still create or control that competing owner, and hardware-init fallback was lost at the IPC boundary so simulated frames appeared to come from live hardware | V42, T37 |
| B46 | 2026-07-15 | `return_home` selected `RETURN_HOME` while execution advanced only `AUTO`; failed A* fell back to direct travel and no dock result was consumed | V43, T38 |
| B47 | 2026-07-15 | Planner copied one blade flag to all waypoints and executor applied destination intent before travel, allowing blade-on staging/connectors | V44, T38 |
| B48 | 2026-07-15 | Coverage concatenated disjoint intervals through unsafe space and preview used zero margin while admission used 0.25 m | V49, T39 |
| B49 | 2026-07-15 | ToF obstacles had dummy coordinates and caused repeated command rejection/abort without wait, map, or replan | V50, T39 |
| B50 | 2026-07-15 | Readiness omitted canonical mission facts and unexpected preflight wiring errors continued live admission | V45, T40 |
| B51 | 2026-07-15 | GPS-loss settings persisted UI policy while canonical mission/gateway execution used no degradation state machine | V46, T40 |
| B52 | 2026-07-15 | Fast safety read serialized two ToF measurements behind shared I2C contention inside a shorter aggregate timeout | V47, T41 |
| B53 | 2026-07-15 | Mission pause/resume swallowed API failure and caller always displayed success | V48, T42 |
| B54 | 2026-07-15 | Manual-control UI locally unlocked on unsupported/error responses without a server-issued hardware session | V48, T42 |
| B55 | 2026-07-15 | Quick Mow persisted `pending`; planning start/pause/resume changed browser state without canonical job/mission action | V48, V53, T43 |
| B56 | 2026-07-15 | Multi-zone scheduler ran only `zones[0]`; failed start left persisted idle missions and retried same occurrence every 30 s | V53, T43 |
| B57 | 2026-07-15 | Charge monitor was test-only, SOC algorithms disagreed, mission admission had no return reserve, and tracked INA channel mapping contradicted runtime | V52, T44 |
| B58 | 2026-07-15 | AI used one red-color heuristic, results lacked canonical perception consumers, and UI/API advertised fabricated training/export data | V50, V51, T45 |
| B59 | 2026-07-15 | UI converted missing power to zero, showed fabricated weather/history/patterns, and lacked live build/freshness truth | V48, V54, T46 |
| B60 | 2026-07-15 | Enabled sensor systemd unit only slept forever while backend owned sensors, producing green-but-inert service health | V54, T47 |
| B61 | 2026-07-15 | Critical autonomous/GPS/UI tests were skipped placeholders, frontend CI skipped tests, OpenAPI IDs collided, and full Ruff had 136 errors | V55, T48 |
| B62 | 2026-07-15 | Global response sanitization replaced login and refresh tokens with redaction markers, breaking authenticated manual unlock and token refresh | V56, T48 |
| B63 | 2026-07-15 | The Cloudflare login branch called a method absent from the production auth service, trusted unsigned claims, and was never attempted by the router; recursive refresh on auth-route 401 responses then amplified one failure into a 429 lockout | V57, T50 |
| B64 | 2026-07-15 | The tracked single-owner camera unit was not installed/enabled on the Pi, and PowerManager ignored fresh Control-page frame demand, so it could stop capture while an operator was actively viewing it | V42, V58, T50 |
| B65 | 2026-07-15 | The real detector runtime was deployed without its ignored runtime manifest or ONNX artifact, leaving the shared camera pipeline truthful but unable to perform object detection | V51, T50 |
| B66 | 2026-07-15 | The first official YOLOv5n ONNX candidate contained FP16 tensors that Raspberry Pi OS OpenCV 4.6 could not load, proving that file presence and output-shape assumptions were insufficient deployment checks | V51, T50 |
| B67 | 2026-07-15 | A cancelled shared camera IPC request left its late response on the socket for the next command, while the UI deliberately cancelled healthy MJPEG streams every four seconds and the owner socket allowed any local user to stop capture or disable AI | V59, T50 |
| B68 | 2026-07-15 | PowerManager added a second full idle countdown after the viewer-demand lease expired and only resumed capture it had paused itself, delaying power savings while allowing an externally stopped or restarted camera to remain off throughout an active mission | V60, T50 |
| B69 | 2026-07-15 | Cloudflare unknown-key assertions could force unbounded JWKS fetches, proxy-spoofable client addresses weakened login lockout, custom-password failures used a permanent duplicate counter, exchanges leaked sessions, restart restoration erased signed identity, direct startup froze verifier settings before dotenv load, and Axios refresh mutated storage without the reactive auth store | V61, T50 |
| B70 | 2026-07-15 | The installed YOLOv5n model loaded successfully but exceeded the camera owner's 0.5-second deadline on the Raspberry Pi, so every valid automatic inference result could be discarded while status still reported the model ready | V62, T50 |
| B71 | 2026-07-15 | Dark-idle power saving disabled AI, but only an active mission re-enabled it; daylight, manual motion, and an active Control viewer could therefore leave inference silently disabled | V63, T50 |
| B72 | 2026-07-15 | A hardware camera initialization failure silently changed the owner to simulation and allowed synthetic frames to become fresh perception results, making fallback imagery look like live-world evidence to route and obstacle consumers | V64, T50 |
| B73 | 2026-07-15 | After MJPEG recovered from snapshot fallback, the Control UI left its two-second snapshot poller and fallback blob active, creating redundant IPC load and camera demand indefinitely | V65, T50 |
| B74 | 2026-07-15 | Mission startup never called the existing camera and AI wake hook, so autonomous motion could begin while perception remained power-paused until the next ten-second polling tick | V66, T50 |
| B75 | 2026-07-15 | Hardware-mode AI re-enable treated a local metadata update as success even when camera-owner IPC failed, cleared the retry flag, and could leave the real inference owner disabled through later missions | V67, T50 |
| B76 | 2026-07-15 | A delayed camera start or recovery could finish after the Control view unmounted and recreate MJPEG or snapshot timers, keeping camera demand alive without a viewer | V68, T50 |
| B77 | 2026-07-15 | Both mounted login APIs replaced the known admin/admin input with the real configured operator credential, granting a production operator JWT to callers who did not know that credential while the UI and tests advertised the bypass | V69, T50 |
| B78 | 2026-07-15 | Logout and session-limit eviction deleted server memory but token verification restored any still-signed missing session ID, allowing terminated tokens to become active again | V70, T50 |
| B79 | 2026-07-15 | Cloudflare exchange discarded the verified assertion expiry, issued a renewable eight-hour local token, and refreshed it without rechecking Access, allowing LawnBerry authorization to outlive upstream policy | V71, T50 |
| B80 | 2026-07-15 | Production WebSocket authorization trusted any loopback peer without proof while the frontend proxy made every browser appear loopback and its client stripped the token query, exposing operator telemetry/control authorization | V72, T50 |
| B81 | 2026-07-15 | The Cloudflare bootstrap rate override reused the client's global token bucket, shrinking the normal API burst immediately after login and recreating 429 failures during page initialization | V73, T50 |
| B82 | 2026-07-15 | Scheduled dispatch converted a missing MissionService dependency into a normal skipped occurrence after entering persistence-backed admission, allowing a startup wiring defect to silently consume a mowing run | V74, T50 |
| B83 | 2026-07-15 | Bearer-authenticated manual unlock ignored the verified JWT expiry, and the shared expiry helper selected the token expiry instead of the earlier local timeout, allowing motor authorization to outlive one of its trust boundaries | V75, T50 |
| B84 | 2026-07-15 | Lifespan started the persisted job scheduler before PowerManager existed and stopped it only after safety/power teardown, allowing due mowing occurrences to race boot or shutdown without their canonical camera/AI wake dependency | V76, T50 |
| B85 | 2026-07-15 | Solar equation-of-time math subtracted ecliptic longitude and added right ascension without wrap normalization, producing an impossible roughly 465-minute correction and classifying summer afternoon as dark | V77, T50 |
| B86 | 2026-07-15 | Disabling Uvicorn proxy headers and stripping all forwarded identity made every Cloudflare/frontend request appear as `127.0.0.1`, so one external client could consume the shared login and API quota for every operator | V78, T50 |
| B87 | 2026-07-15 | Bearer/Cloudflare manual grants retained independent in-memory authority after their parent JWT session was logged out, revocation writes swallowed filesystem failures before reporting successful termination, and restoring an older same-SID token first narrowed logout revocation below a refreshed sibling's expiry, allowing actuator authorization or signed sessions to survive a supposedly completed logout | V79, T50 |
| B88 | 2026-07-15 | A refresh response with five minutes or less remaining called timer setup, which immediately awaited the already-active single-flight refresh promise and deadlocked itself; a non-advancing upstream expiry could also trigger an immediate loop | V80, T50 |
| B89 | 2026-07-15 | CameraPanel emitted the same load event for MJPEG and snapshot images, and the handler treated a fallback blob load as primary-stream recovery, revoking its own URL and stopping its poller | V81, T50 |
| B90 | 2026-07-15 | Mission admission checked the task map before multi-second readiness and camera/AI awaits without a lifecycle lock, so concurrent starts could both launch navigation while the second overwrote the only tracked task | V82, T50 |
| B91 | 2026-07-15 | The tracked frontend systemd unit still targeted a nonexistent `/apps/lawnberry-pi/frontend` tree even though the installed mower service executed from `/home/pi/lawnberry/frontend`, so reinstalling tracked units would have broken the UI | V83, T50 |
| B92 | 2026-07-15 | Sensor health treated the IMU interface's `online` transport status as fully healthy even when the canonical BNO085 reading was `uncalibrated`, contradicting navigation's fail-closed heading decision and misleading operators | V84, T50 |
| B93 | 2026-07-15 | Mission update and bulk deletion bypassed the lifecycle lock, so either could run while start awaited camera/AI admission: mutation could enable a blade after diagnostic validation, and deletion could remove the mission record while leaving its navigation task alive | V85, T50 |
| B94 | 2026-07-15 | Navigation's task-done callback published terminal state outside the lifecycle lock while pause held that lock across an awaited stop; task completion could therefore set `COMPLETED`, then pause could overwrite it with `PAUSED`, discard the task, and allow the completed mission to run again | V86, T50 |
| B95 | 2026-07-15 | Mission completion set progress to 100 percent immediately before `_persist_mission_status` recomputed it from the last zero-based waypoint index, so canonical and stored completed status could fall below 100 percent (including 0 percent for a one-waypoint mission) | V87, T50 |
| B96 | 2026-07-15 | A mission WebSocket regression assumed failure terminalization and delivery always completed in exactly three `sleep(0)` turns; serializing terminalization behind the lifecycle lock legitimately added a scheduling step and made the test fail despite correct eventual FAILED delivery | V88, T50 |
| B97 | 2026-07-15 | Energy-return and restart-recovery tests either closed the callback's terminalization coroutine or forged persisted RUNNING state before the live cancellation callback finished, so they tested scheduler timing rather than the intended terminal and crash-recovery contracts | V88, T50 |
| B98 | 2026-07-16 | Full blade qualification omitted `supervised_blade_enabled`; adding it directly would deadlock the only canonical blade path behind the same full-qualification gate | V89, T51 |
| B99 | 2026-07-16 | Legacy `/opt/wifi-watchdog` conflated probe/radio failures, watched absent `wlan1`, and retained USB-reset/reboot authority; its reboot coincided with `2357:0138` failing enumeration on USB3, leaving only weak internal `wlan0` online under stale backup identity | V90, T52 |
| B100 | 2026-07-16 | Recovery collapsed NetworkManager's activating states into disconnected and issued a second `connection up`; the competing activation canceled or raced the in-flight association and temporarily produced a false missing-secret failure even though the system profile retained its PSK | V91, T52 |
| B101 | 2026-07-23 | Boundary edit mode discarded the saved draft, cancellation retained failed-point UI state, and boundary mutations left derived safe geometry/session/cache state available | V92, T53 |
| B102 | 2026-07-23 | The new serialized boundary-mutation callback imported `Callable` from `typing`, violating the project's Python 3.11 lint rule | V92, T53 |
| B103 | 2026-07-23 | Maps labelled the parcel-helper and saved-boundary delete paths too similarly, while vertex handles could move but not remove a selected point | V93, T54 |
