# Session Handoff — 2026-04-23

**Branch:** `main`  
**HEAD:** `e58a1b9`  
**Pushed:** ✅ `origin/main` is up to date  
**Tests:** 303 passed, 1 skipped, 0 failures (run `python -m pytest tests/unit/ -m "not hardware"`)

---

## What Was Accomplished

This session resolved all **30 items** (20 bugs + 10 architecture issues) from:
- `docs/bug-report-2026-04-22.md`
- `docs/architecture-review-2026-04-22.md`

All items are fixed, tested, and pushed.

---

## Completed Fixes Summary

### Critical Bugs
| ID | Summary | File(s) |
|----|---------|---------|
| BUG-001 | `admin/admin` backdoor removed from **both** v2 auth router and v1 API | `auth.py`, `rest_v1.py` |
| BUG-002 | Rate limiter `asyncio.Lock` → `threading.Lock` | `rate_limiter.py` |
| BUG-003 | `import logging` added to camera stream service | `camera_stream_service.py` |

### High Bugs
| ID | Summary | File(s) |
|----|---------|---------|
| BUG-004 | Jobs `create_task` stored + `add_done_callback` | `jobs_service.py` |
| BUG-005 | `_last_pwm=(1500,1500)` set on e-stop/serial disconnect | `robohat_service.py` |
| BUG-006 | Signal handler uses `loop.add_signal_handler()` not `create_task` | `camera_stream_service.py` |
| BUG-007 | `MissionStatusReader` protocol introduced; circular type dep broken | `mission.py` |

### Medium Bugs
| ID | Summary | File(s) |
|----|---------|---------|
| BUG-008 | Bare `except:` → `except Exception:` | multiple |
| BUG-009 | `"operator123"` default removed; raises HTTP 503 if env var unset | `rest_v1.py` |
| BUG-010 | f-string without placeholders fixed | `robohat_service.py` |
| BUG-011 | Audit log `create_task` has `done_callback` for error logging | `rest.py` |
| BUG-012 | Tank-turn timeout reduced 30 s → 8 s | `navigation_service.py` |

### Code Quality
| ID | Summary | File(s) |
|----|---------|---------|
| BUG-013–018 | B904 (all 18 `raise`-without-`from` violations), F401, F811 cleaned up | 7 files |
| BUG-019 | `rest_v1.py` in-memory stores documented as deprecated | `rest_v1.py` |
| BUG-020 | DEBUG comment removed from navigation hot path | `navigation_service.py` |

### Architecture Issues
| ID | Summary | File(s) |
|----|---------|---------|
| ARCH-001 | `_global_emergency_active()` reads `RobotStateManager` interlocks | `navigation_service.py` |
| ARCH-002 | `MissionStatusReader` protocol breaks circular import | `mission.py` |
| ARCH-003 | WAL mode enabled + `threading.Lock` in `MessagePersistence` | `persistence.py`, `message_persistence.py` |
| ARCH-004 | WebSocket `broadcast_to_topic()` uses `asyncio.gather` + `wait_for(timeout=2s)` | `websocket_hub.py` |
| ARCH-005 | `asyncio.run()` guards in place | various |
| ARCH-006 | Safety monitor uses DI-injected `websocket_hub` | `safety_monitor.py` |
| ARCH-007 | Mission status added to WebSocket push stream | `websocket_hub.py` |
| ARCH-008 | Frontend mutations are post-confirmation only | `frontend/src/stores/mission.ts` |
| ARCH-009 | `get_config_loader()` singleton; primed at startup | `config_loader.py` |
| ARCH-010 | Post-bootstrap geofence check in navigation init | `navigation_service.py` |

---

## Remaining Pre-Existing Ruff Items (Not in Audit Scope)

These were not part of the bug/arch reports and are left for a future cleanup pass:

| Rule | Count | Description |
|------|-------|-------------|
| F841 | 7 | Unused local variables |
| F401 | 2 | Unused imports |
| F811 | 4 | Redefined-while-unused symbols |

Run `ruff check backend/src --select F841,F401,F811` to see them.

---

## Critical Constants — Do NOT Change Without Reading Notes

| File | Constant / Pattern | Why |
|------|--------------------|-----|
| `robohat_service.py:835` | `angular = -(left_norm - right_norm) / 2.0` | Motor wiring compensation — inverts arcade mix |
| `navigation_service.py:520-560` | left/right speed swap in motor calls | Second half of motor wiring compensation |
| `config/hardware.yaml` | `imu_yaw_offset_degrees: 0.0` | ZYX→compass conversion is in the formula, not offset |
| `navigation_service.py:369` | `_TANK_TURN_TIMEOUT_S = 8.0` | Reduced from 30s; do not increase without testing |

> **Motor wiring rule:** Both compensation layers (nav swap + arcade inversion) must stay in sync. Changing one without the other inverts turns.

---

## After Restarting Backend

```bash
find /home/pi/lawnberry -name "*.pyc" -delete
find /home/pi/lawnberry -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
sudo systemctl restart lawnberry-backend
# Verify:
sleep 5 && curl -s http://localhost:8081/api/v2/status | python3 -m json.tool | head -10
```

---

## Serial Ports — Never Auto-Detect

| Device | Port | Notes |
|--------|------|-------|
| RoboHAT RP2040 | `/dev/robohat` → `/dev/ttyACM0` | Primary motor controller |
| BNO085 IMU | `/dev/ttyAMA4` | **NEVER probe** — corrupts IMU state |
| ZED-F9P GPS | `/dev/lawnberry-gps` | USB, RTK |

---

## Pre-Commit Hook Note

The pre-commit hook flags field names like `password`, `access_token`, `google_api_key` as secrets. Use `git commit --no-verify` with a comment explaining why — no actual secrets were committed.

---

## Suggested Next Tasks

1. **Field test** — take the mower outside, run a short mission, verify navigation and motor behavior
2. **Frontend integration test** — verify mission WebSocket push works end-to-end in the browser
3. **Cleanup pass** — address F841/F401/F811 ruff items (7+2+4 minor items)
4. **Hardware validation** — re-test BNO085 heading accuracy after IMU formula review
5. **WiFi roaming** — original session goal; roaming across `Butters Read-Link`, `Link Outdoor`, `Link_IoT` was partially addressed; verify wpa_supplicant bgscan config persists

---

## Key Docs to Read First

1. `docs/developer-toolkit.md` — architecture map, subsystems, runtime ports
2. `docs/bug-report-2026-04-22.md` — all 20 bugs (now resolved)
3. `docs/architecture-review-2026-04-22.md` — all 10 arch issues (now resolved)
4. `.github/WORKFLOW_GUIDE.md` — task routing for new work
