# LawnBerry Pi — Codebase Audit Report
**Date:** 2026-05-06  
**Scope:** Full codebase; 20 recent commits (Phase 8/9 frontend decomposition, navigation fixes, telemetry)

---

## Bugs Fixed in This Session

### Critical

**1. `uptime_seconds` was Unix epoch, not process uptime**  
`backend/src/services/telemetry_service.py:358`  
`time.time()` (~1.7 billion) was being returned as uptime. The dashboard was dividing this by 3600 and displaying millions of hours.  
**Fix:** Added module-level `_service_start_time = time.time()` and changed the field to `time.time() - _service_start_time`.

**2. Runtime artifacts (`data/lawnberry.db-shm`, `data/lawnberry.db-wal`, `openapi.json`) were tracked in git**  
`data/lawnberry.db-shm` — SQLite WAL shared-memory sidecar (binary, changes on every connection)  
`data/lawnberry.db-wal` — already gitignored but still tracked  
`openapi.json` — 151 KB generated file that diverges silently from the running API  
**Fix:** `git rm --cached` all three; added `data/lawnberry.db-shm` and `openapi.json` patterns to `.gitignore`.

### Important

**3. Deprecated `asyncio.get_event_loop()` inside running async context**  
`backend/src/services/mission_service.py:556, 569, 582`  
`backend/src/services/navigation_service.py:746`  
In Python 3.10+, calling `get_event_loop()` inside an already-running loop emits `DeprecationWarning` and may fail. The `if loop.is_running():` guard was also always-True inside async tasks.  
**Fix:** Replaced all four occurrences with direct `asyncio.ensure_future(...)` calls (the loop is always running in these code paths).

**4. Duplicate `PoseQuality` enum**  
`backend/src/services/localization_service.py:36` (duplicate, now removed)  
`backend/src/fusion/pose2d.py:13` (canonical)  
Two non-interoperable `PoseQuality` enums with identical string values existed in parallel. Type checkers would flag cross-service comparisons.  
**Fix:** Removed the `PoseQuality(StrEnum)` class from `localization_service.py` and added `from ..fusion.pose2d import PoseQuality` import. The `__all__` re-export is preserved so callers importing `PoseQuality` from `localization_service` continue to work.

---

## Bugs Not Fixed (Require More Work)

### Critical

**5. `LAWN_LEGACY_NAV=1` rollback flag is a no-op**  
`backend/src/services/navigation_service.py:1115–1127`  
`_update_navigation_state_legacy` delegates unconditionally to `_update_navigation_state_impl`. Setting `LAWN_LEGACY_NAV=1` logs "legacy path active" but does **not** engage a different code path. Operators following `docs/rollback-bisect.md` in a production incident will believe they have a stable fallback when they do not.  
**Action needed:** Either copy the pre-Phase-2 localization snapshot into `_update_navigation_state_legacy`, or formally deprecate the flag and update the runbook.  
**Partial fix applied:** Added a warning notice to `docs/rollback-bisect.md` explaining the flag is currently a no-op and that `git checkout phase-1-complete` is the true rollback path.

**6. Traction control RPM estimation is meaningless**  
`backend/src/services/navigation_service.py:528–533`  
Both `left_rpm` and `right_rpm` are set to `robohat.status.encoder_position * 0.5` — the same cumulative single-axis counter scaled by a magic number. Left/right slip detection does not function.  
**Action needed:** Requires firmware support to report per-wheel tick counts or RPM. Not fixable in software alone.

### Important

**7. `ObstacleDetector.is_path_clear()` is dead code**  
`backend/src/services/navigation_service.py:91–98`  
The method is defined but never called. Obstacle avoidance operates only through the `obstacle_avoidance_active` flag.  
**Action needed:** Delete or integrate properly.

**8. `bind_app_state` misleading first line in `websocket_hub.py`**  
`backend/src/services/websocket_hub.py:34`  
`self._app_state = self.app_state` — the parameter `state` is unused on this line. The intent (use `AppState` singleton as backing store, read attrs from FastAPI `app.state` to populate it) is correct but confusing.  
**Action needed:** Add a clarifying comment.

**9. Dual `_zones_store` dictionaries never synchronized**  
`backend/src/api/rest.py:106` and `backend/src/api/rest_v1.py:92`  
Zones POSTed to `/api/v1/map/zones` land in `rest_v1._zones_store`; zones read by `NavigationService._load_boundaries_from_zones()` come from `rest._zones_store`. With the `MapRepository` path these are bypassed, but the fallback path silently loses zones.  
**Action needed:** Consolidate to a single store or always require the `MapRepository` path.

### Minor

**10. `jobs_service._execute_job` is a fake simulation loop**  
`backend/src/services/jobs_service.py:261`  
Scheduled jobs produce fake 10-step progress and mark themselves complete without running any mission logic.

**11. `camera_stream_service._process_frame_for_ai` is a placeholder**  
`backend/src/services/camera_stream_service.py:837`  
Returns dummy AI annotations in sim mode.

**12. `PlanningView.vue` uses hardcoded mock jobs data**  
`frontend/src/views/PlanningView.vue:443–479`  
The `jobs` ref is never populated from the API; it uses static 2024 dummy entries.

**13. Google auth `POST /api/v1/auth/unlock` returns 501**  
`backend/src/api/routers/auth.py:768`  
The frontend's offline-mode fallback grants access silently when the backend returns 501. Depending on deployment context this may be a security concern.

---

## Cleanup Performed in This Session

### Files Removed from Git

| File | Reason |
|------|--------|
| `data/lawnberry.db-shm` | Binary runtime artifact (SQLite WAL shared memory) |
| `data/lawnberry.db-wal` | Binary runtime artifact (SQLite WAL) |
| `openapi.json` | Generated file; regenerate with `scripts/generate_openapi.py` |
| `docs/session-handoff-2026-04-23.md` | Agent session handoff, not product documentation |
| `docs/session-handoff-2026-05-01.md` | Agent session handoff |
| `docs/architecture-review-2026-04-22.md` | One-off agent audit document |
| `docs/bug-report-2026-04-22.md` | One-off agent bug report |
| `docs/hallucination-audit.md` | One-off agent audit |
| `CODE_REVIEW_REPORT.md` | Previous code review artifact |
| `IMPLEMENTATION_SUMMARY.md` | Implementation notes, not product docs |
| `=2.0.4` | Zero-byte file created by a mistyped shell command |
| `frontend/src/composables/useWebSocket.ts` | Orphaned socket.io composable; no callers in the codebase |
| `frontend/src/components/ToastHost.vue` | Replaced by superior `components/ui/ToastHost.vue` |

### Code Changes

| Change | File | Details |
|--------|------|---------|
| Remove `socket.io-client` dependency | `frontend/package.json` | Was only referenced by the deleted orphaned composable |
| Activate better ToastHost | `frontend/src/App.vue` | Now imports from `components/ui/ToastHost.vue` (has `aria-live`, better accessibility) |
| Add missing gitignore patterns | `.gitignore` | Added `data/lawnberry.db-shm` and `openapi.json` |
| Removed duplicate `.db-wal` entry | `.gitignore` | Consolidated with the two new entries above |

### Documentation Updated

| File | Change |
|------|--------|
| `docs/rollback-bisect.md` | Added warning that `LAWN_LEGACY_NAV=1` is currently a no-op; directs operators to `git checkout phase-1-complete` as the true rollback path |

---

## Remaining Cleanup Candidates (Not Yet Done)

These are safe but require manual judgment:

### Scripts to Consolidate
`scripts/backup.sh` vs `scripts/backup_system.sh` — different implementations, one more complete. Consider keeping only `backup_system.sh` or renaming clearly.  
`scripts/restore.sh` vs `scripts/restore_system.sh` — same situation.

### One-Off Diagnostic Scripts
`scripts/test_latency.py`, `scripts/test_websocket_load.py`, `scripts/test_motor_diagnostics.sh`, `scripts/test_performance_degradation.py` — not harmful but not part of the standard test suite. Consider moving to `scripts/diagnostics/`.

### Stale Architecture References
`README.md:64` — hardcoded IP `192.168.50.215:3000` should be replaced with a generic placeholder.  
`backend/src/services/navigation_service.py:45` — stale migration comment `## Path planning moved to…`; PathPlanner is the live implementation now.

### Dead Code
`NavigationService._update_navigation_state_legacy()` — dead stub once the LAWN_LEGACY_NAV issue is resolved.  
`ObstacleDetector.is_path_clear()` — dead method; either integrate or delete.  
`DeadReckoningSystem` in `navigation_service.py` vs `_DeadReckoningState` in `localization_service.py` — parallel implementations; the NavigationService one is only used when `LocalizationService` is disabled.

---

## Architecture Notes

**`RuntimeContext` uses `Any` types** — intentional to avoid circular imports, but means type-checkers can't verify service access at router call sites. Acceptable for now.

**Circular lazy import pattern** — `navigation_service.py` and `mission_service.py` do `from ..main import app` inside function bodies to reach `command_gateway`. This is an intentional workaround that falls back gracefully but silently when called before lifespan completes.

**Tests do not cover extracted `MissionControls` / `MissionStatusPanel` components in isolation** — `MissionPlannerView.spec.ts` covers them indirectly. The four new composables (`useBoundaryGeometry`, `useMowerTelemetry`, `useMissionDiagnostics`, `useMissionMapSettings`) do have spec files.
