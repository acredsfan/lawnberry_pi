# LawnBerry Pi — Claude Code Instructions

> **Start here, then read `AGENTS.md`** for full project orientation, safety-critical hardware rules,
> coding conventions, documentation drift policy, and secrets handling.
> This file adds Claude Code-specific guidance that goes beyond AGENTS.md.

---

## Tools

### Code Search — semble

Use **semble MCP tools** for all code search before falling back to `grep` or `find`:
- `mcp__semble__search` — find where a symbol, function, or pattern is defined/used
- `mcp__semble__find_related` — discover related code after an initial hit

Use the **Explore subagent** for open-ended multi-file investigations (file patterns, cross-file
references, architecture surveys). Use `mcp__semble__search` for targeted lookups.

### Pi System Control — pi-control

The `pi-control` MCP server gives direct access to the Raspberry Pi OS. Prefer these over
spawning subagents for simple runtime checks. **Tier 3 is enabled** (full system access).

**Shell & processes**
| Tool | When to use |
|------|------------|
| `mcp__pi-control__Shell` | Run any shell command on the Pi (replaces `Bash` for live system state) |
| `mcp__pi-control__ListProcesses` | See running processes and their PIDs |
| `mcp__pi-control__KillProcess` | Send signal to a process by PID |

**Services (systemd)**
| Tool | When to use |
|------|------------|
| `mcp__pi-control__ServiceList` | List all systemd units and their active/enabled state |
| `mcp__pi-control__ServiceHealthReport` | Health summary for LawnBerry systemd units |
| `mcp__pi-control__ServiceStart` | Start a systemd service |
| `mcp__pi-control__ServiceStop` | Stop a systemd service |
| `mcp__pi-control__JournalSearch` | Query journald logs (replaces `journalctl` grep) |

**Network & ports**
| Tool | When to use |
|------|------------|
| `mcp__pi-control__PortCheck` | Confirm a port is listening (e.g. backend on 8081) |
| `mcp__pi-control__NetConnections` | Active network connections |
| `mcp__pi-control__Ping` | Reachability check |
| `mcp__pi-control__NetworkFailoverStatus` | LTE/WiFi failover state |

**Hardware & mower runtime**
| Tool | When to use |
|------|------------|
| `mcp__pi-control__GetSystemInfo` | CPU, memory, disk, temperature |
| `mcp__pi-control__HardwareProbe` | Detect attached hardware devices |
| `mcp__pi-control__MowerRuntimeSnapshot` | Live mower service state (GPS, IMU, mission) |

**Git & file ops**
| Tool | When to use |
|------|------------|
| `mcp__pi-control__GitProjectState` | Branch, status, recent commits for `/home/pi/lawnberry` |
| `mcp__pi-control__FileList` | Directory listing |
| `mcp__pi-control__FileRead` | Read a file by path |
| `mcp__pi-control__FileSearch` | Find files by name pattern |

**Screen & UI** (use sparingly — prefer Shell for automation)
| Tool | When to use |
|------|------------|
| `mcp__pi-control__Snapshot` | Screenshot of the Pi display |
| `mcp__pi-control__ObserveScreen` | Watch for display changes |
| `mcp__pi-control__OCR` | Extract text from a screenshot region |

---

## Environment

| Item | Value |
|------|-------|
| Hardware | Raspberry Pi 5, aarch64, Linux |
| Python | 3.11+ |
| Package manager | `uv` (lock file: `uv.lock`) |
| Backend framework | FastAPI + Uvicorn, port **8081** |
| Frontend framework | Vue 3 + Vite + TypeScript, port **3000** |
| Test framework | pytest 8 + pytest-asyncio (auto mode) |

**`SIM_MODE=1` is mandatory** for every test, script, and server run in an agent session.
Hardware is never available. Leaving `SIM_MODE` unset defaults to hardware mode (`os.getenv("SIM_MODE", "0")`).

---

## Running Tests

```bash
# Backend — unit tests (safest default)
SIM_MODE=1 pytest tests/unit -q --tb=short

# Backend — integration tests (skips placeholder stubs by default)
SIM_MODE=1 pytest tests/integration -q --tb=short

# Backend — contract tests
SIM_MODE=1 pytest tests/contract -q --tb=short

# Run all with placeholder stubs included
SIM_MODE=1 RUN_PLACEHOLDER_INTEGRATION=1 RUN_PLACEHOLDER_CONTRACT=1 pytest tests/ -q --tb=short

# Navigation-specific (referenced by plan steps)
SIM_MODE=1 pytest tests/integration/test_navigation_replay.py tests/integration/test_replay_navigation_script.py tests/integration/test_compare_run.py tests/unit/test_legacy_nav_flag.py -v

# Frontend
cd frontend && npm test               # Vitest unit tests
cd frontend && npm run type-check     # TypeScript check
cd frontend && npm run build          # Build validation
```

### Known Pre-Existing Failures to Ignore

These are **not regressions** — do not spend time fixing them:

| File | Reason |
|------|--------|
| `tests/unit/test_sensor_cli_format.py` | `typer` version mismatch (`module 'typer' has no attribute 'command'`) — collection error |
| `tests/unit/test_nav_coverage_patterns.py` | Shapely 2.x `__slots__` issue with `Polygon.origin_lat` — xfail |
| `tests/unit/test_nav_geofence_validator.py` | Same Shapely issue — xfail |
| `tests/unit/test_dead_reckoning.py` | Reset behavior divergence — xfail |
| `tests/unit/test_global_rate_limiter.py` | conftest env-override ordering — xfail |
| `tests/unit/test_navigation_service.py` (2) | Singleton state isolation — xfail |
| `tests/unit/test_consistency_guard.py` (2) | Hardcoded CI paths — xfail |
| `tests/unit/test_rest_api_control.py` | Telemetry interlock ordering — xfail |
| `tests/unit/test_robohat_service_usb_control.py` | CI-only serial branch — xfail |
| `tests/unit/test_hardware_selftest.py` | Requires `RUN_HW_TESTS=1` — skipif |

The `test_sensor_cli_format.py` collection error interrupts the entire run when collecting `tests/unit/`.
Work around it by targeting specific test files or directories instead of `tests/unit/` as a whole.

---

## Environment Variable Quick Reference

| Variable | Values | Effect |
|----------|--------|--------|
| `SIM_MODE` | `0` / `1` | **1 = simulation** (no hardware I/O). Must be 1 in all agent sessions. |
| `LAWN_LEGACY_NAV` | `0` / `1` | 1 = use pre-Phase-2 `_update_navigation_state_impl` path (§13 rollback) |
| `USE_LEGACY_NAVIGATION` | `0` / `1` | 1 = disable `LocalizationService` delegation (Phase 2 guard) |
| `LAWN_BERRY_OPERATOR_CREDENTIAL` | string | Operator password for auth tests |
| `DB_PATH` | path / `:memory:` | SQLite path; tests use `:memory:` |
| `LOG_LEVEL` | `WARNING` etc. | Tests set `WARNING` via conftest |
| `LAWNBERRY_CAPTURE_PATH` | file path | Enables telemetry capture to JSONL |
| `RUN_PLACEHOLDER_INTEGRATION` | `1` | Include placeholder integration stubs |
| `RUN_PLACEHOLDER_CONTRACT` | `1` | Include placeholder contract stubs |
| `RUN_HW_TESTS` | `1` | Enable hardware self-test suite |
| `AI_INFERENCE_ENABLED` | `0` / `1` | Enable ML inference |

---

## Git Workflow

### Pre-Commit Hooks (never bypass with `--no-verify`)

Three checks run on every commit:
1. **Gitignore guard** — blocks logs, secrets, DB files, runtime data, files >2 MB
2. **Secret scanner** — rejects Google/AWS/GitHub/Slack tokens and generic credential assignments (e.g. bare string literals assigned to `password` or `api_key` variables)
3. **TODO format** — new TODOs must match `TODO(vX): <description> - Issue #<number>`

The scanner **excludes** Python type annotations (`my_token: Optional[str] = None`) and files ending in `.example`. Plan documents in `docs/superpowers/plans/` are gitignored and will never be staged.

### Committing

- **Never commit local-only files.** Gitignored paths that must stay untracked:
  - `docs/superpowers/plans/` — local agent implementation plan documents
  - `config/secrets.json`, `data/`, `logs/`, `.env` variants, `*.db`, `*.sqlite*`
  - Everything in `.gitignore`
- Always stage files **explicitly by name** — never `git add .` or `git add -A`
- Run `git status` before committing to confirm only intended files are staged

### Syncing After Task Completion

When a task or plan step is verified complete (tests pass, behavior confirmed):
1. `git add <specific files>`
2. `git commit -m "..."` (with `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`)
3. `git push origin main`
4. Confirm: `git status` shows clean working tree, branch up to date with origin

---

## Plan Execution Protocol

When executing a multi-step implementation plan from `docs/superpowers/plans/`:

1. **Read the plan file** at the start of the session before writing any code.
2. **TDD order**: write failing tests first, confirm they fail, implement, confirm they pass.
3. **Commit and push at each task boundary** — do not batch multiple tasks into one commit.
4. **Gate on tests**: do not proceed to the next task if the current task's tests fail.
5. **After the final task**: run the full test suite (excluding known pre-existing failures) to confirm no regressions, then push.
6. **Provide a handoff prompt** when the plan is part of a sequence. The prompt must be self-contained: working directory, branch/tag state, what was completed, what the next plan file is, and all constraints the next agent needs. Hand it to the user verbatim so they can paste it into a new session.

---

## Architecture Quick Reference

### Key Files

| Path | Purpose |
|------|---------|
| `backend/src/main.py` | FastAPI app entrypoint; lifespan wires all services into `RuntimeContext` |
| `backend/src/core/runtime.py` | `RuntimeContext` dataclass (config, nav, mission, safety, gateway, localization) |
| `backend/src/core/state_manager.py` | `AppState` singleton; sensor manager, safety state, debug overrides |
| `backend/src/services/navigation_service.py` | Core navigation (1910 lines); active refactor target |
| `backend/src/services/robohat_service.py` | RoboHAT RP2040 bridge |
| `backend/src/nav/geoutils.py` | Lat/lon math utilities |
| `backend/src/nav/localization_helpers.py` | Pure heading/GPS/offset math (Phase 2+) |
| `scripts/replay_navigation.py` | Offline navigation replay + `--compare` mode |
| `tests/fixtures/navigation/synthetic_straight_drive.jsonl` | Golden navigation fixture |
| `data/imu_alignment.json` | Persisted IMU session heading alignment |
| `docs/rollback-bisect.md` | Operator runbook: rollback, bisect, compare-run |

### Active Refactor Flags

| Flag | Meaning |
|------|---------|
| `LAWN_LEGACY_NAV=1` | Use pre-Phase-2 localization path in `NavigationService._update_navigation_state_impl` |
| `USE_LEGACY_NAVIGATION=1` | Disable `LocalizationService` delegation (Phase 2 facade guard) |
| `phase-1-complete` (git tag) | Known-good pre-Phase-2 baseline for `git bisect` |

### Services Layer (backend/src/services/)

`navigation_service` · `localization_service` · `mission_service` · `robohat_service` ·
`sensor_manager` · `telemetry_service` · `telemetry_hub` · `auth_service` ·
`blade_service` · `camera_stream_service` · `maps_service` · `weather_service` ·
`traction_control_service` · `jobs_service` · `power_service` · `ai_service` ·
`settings_service` · `ntrip_client` · `websocket_hub`

### Test Layout

```
tests/
  unit/          64 files — no hardware, fast, safest default
  integration/   35 files — cross-component, persistence, API interactions
  contract/      45 files — API contract compliance
  hil/            1 file  — hardware-in-loop (requires RUN_HW_TESTS=1)
  fixtures/
    navigation/  JSONL replay fixtures + build script
```

### Ports

| Service | Port |
|---------|------|
| Backend API | 8081 |
| Frontend dev / deployed | 3000 |
| Playwright E2E preview | 4173 |
| Backend WebSocket | `ws://127.0.0.1:8081/api/v2/ws/telemetry` |

---

## Development Server Commands

```bash
# Backend (simulation)
SIM_MODE=1 python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081

# Frontend
cd frontend && npm ci && npm run dev -- --host 0.0.0.0 --port 3000

# Lint
python -m ruff check backend/src tests

# Replay navigation (compare legacy vs refactored)
SIM_MODE=1 python scripts/replay_navigation.py tests/fixtures/navigation/synthetic_straight_drive.jsonl --compare --verbose
```
