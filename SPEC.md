# LawnBerry Remote-Access Stability Spec

## §G — Goal

Remote UI at `lawnberry.link-smart-home.com` stays reachable and functional
across WiFi roaming events and cloudflared restarts. No manual intervention needed.

---

## §C — Constraints

- Hardware: Raspberry Pi 5, wlan1 = external antenna (primary), wlan0 = internal (fallback)
- WiFi: 5 GHz mesh "Link_IoT"; gateway varies by AP (192.168.4.1 / 192.168.50.1 / 192.168.86.1)
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
| I.wdog | WiFi watchdog | `/opt/wifi-watchdog`, config `/etc/wifi-watchdog/watchdog.yml` |

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
| T8 | . | Verify Vite `ws:true` proxy survives Cloudflare's HTTP upgrade path; add integration smoke-test | V8, I.cf |
| T9 | . | Add wifi-watchdog unit test: assert disabled tier is skipped, not stalling | V4 |
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
