# LawnBerry Scripts

Utility scripts for the LawnBerry Pi robot mower project. Most scripts are
standalone Python or shell; run them from the repository root unless noted.

All Python scripts require `SIM_MODE=1` when the backend is not running
against real hardware.

---

## cleanup_test_fixtures.py

Purges test-fixture rows that leaked into the production database
(`data/lawnberry.db`) when the test suite wrote to the prod DB instead of
an in-memory database.

**What it does**

| Table | Action |
|-------|--------|
| `missions` | DELETE all rows |
| `mission_execution_state` | DELETE all rows |
| `planning_jobs` (enabled=1) | SET enabled=0 (disabled, not deleted — may be real user schedules) |

**Usage**

```bash
# Dry run — show what would change, make no modifications
python scripts/cleanup_test_fixtures.py --dry-run

# Interactive confirmation
python scripts/cleanup_test_fixtures.py

# Non-interactive (CI / scripted)
python scripts/cleanup_test_fixtures.py --yes

# Target a different database file
python scripts/cleanup_test_fixtures.py --db /path/to/other.db --yes
```

**Example output (dry run)**

```
Dry run — no changes will be made.
  missions:                 32 rows
  mission_execution_state:  32 rows
  planning_jobs (disable):   1 row(s) (id=job-test-001, name=Test Schedule)

Run without --dry-run to apply.
```

**Example output (--yes)**

```
Will perform the following actions:
  Delete 32 row(s) from missions.
  Delete 32 row(s) from mission_execution_state.
  No enabled planning_jobs rows to disable.

Deleted 32 rows from missions.
Deleted 32 rows from mission_execution_state.
No enabled planning_jobs rows found — nothing to disable.
Done.
```

**Re-enabling schedules after cleanup**

If planning jobs were disabled, re-enable them via the Planning UI or directly:

```sql
UPDATE planning_jobs SET enabled=1 WHERE id IN ('your-job-id');
```

---

## diagnose_gps_rtk.py

Diagnoses GPS RTK fix quality, NTRIP connection, and satellite counts.

## generate_docs_bundle.py

Generates a documentation bundle (HTML/PDF) from the project docs.

## generate_openapi.py

Exports the FastAPI OpenAPI schema to a JSON file.

## hil_probe.py

Hardware-in-loop probe: verifies hardware peripherals are accessible
(requires `RUN_HW_TESTS=1` and real hardware).

## init_database.py

Initialises the SQLite database schema from scratch. Run once on first
deployment or after wiping `data/lawnberry.db`.

## replay_navigation.py

Offline navigation replay from a JSONL telemetry file. Supports
`--compare` mode to diff legacy vs refactored navigation paths.

```bash
SIM_MODE=1 python scripts/replay_navigation.py \
  tests/fixtures/navigation/synthetic_straight_drive.jsonl \
  --compare --verbose
```

## rtk_diagnostics_watch.py

Continuous RTK diagnostics watcher (streaming output).

## test_latency.py

Measures API round-trip latency for the backend endpoints.

## test_performance_degradation.py

Stress-tests the backend for performance degradation under load.

## test_websocket_load.py

Load-tests the WebSocket telemetry endpoint.

## validate_acceptance.py / validate_quickstart.py / validate_safety_config.py

Acceptance and safety validation scripts for pre-deployment checks.

## Shell scripts

| Script | Purpose |
|--------|---------|
| `backup.sh` / `backup_system.sh` | Create a system backup |
| `restore.sh` / `restore_system.sh` | Restore from backup |
| `harden_system.sh` | Apply OS hardening settings |
| `install-hooks.sh` | Install pre-commit hooks |
| `rebuild_frontend_and_restart_backend.sh` | Full rebuild and restart |
| `renew_certificates.sh` | Renew TLS certificates |
| `run-e2e-tests.sh` | Run Playwright end-to-end tests |
| `setup.sh` | Initial project setup |
| `setup_https.sh` / `setup_lets_encrypt.sh` | Configure HTTPS |
