# LawnBerry Pi — Claude Code Instructions

## Environment

- Raspberry Pi 5, Python 3.11, running Linux (aarch64)
- All test and script runs must be prefixed with `SIM_MODE=1` — hardware is never available in a dev/agent session
- Use `uv run pytest` or plain `pytest` (both work); use `SIM_MODE=1 pytest ...`
- Pre-commit hooks run on every commit: gitignore guard, secret scanner, TODO format check — do not use `--no-verify`

## Running Tests

```bash
# Standard test run (skip the pre-existing broken collector)
SIM_MODE=1 pytest tests/unit tests/integration -q --tb=short

# The file below has a pre-existing typer version error unrelated to this project's work.
# It is safe to ignore it by running specific test directories or files directly.
# tests/unit/test_sensor_cli_format.py
```

## Git Workflow

### Committing

- **Never commit local-only files.** The following paths are gitignored and must stay that way:
  - `docs/superpowers/plans/` — local implementation plan documents used to guide agents
  - Any file listed in `.gitignore`
- Before committing, run `git status` and verify no gitignored or unintended files are staged.
- Stage files explicitly by name (never `git add .` or `git add -A`).

### Syncing After Task Completion

- When a task or plan step is verified as complete (tests passing, behavior confirmed), **immediately commit the relevant files and push to `origin/main`**.
- After pushing, confirm with `git status` that the working tree is clean and branch is up to date with origin.

## Plan Execution

When executing a multi-step implementation plan (e.g., from `docs/superpowers/plans/`):

1. Read the plan file at the start of the session.
2. Execute tasks in order, running the required tests at the end of each task before proceeding.
3. Commit and push at each task boundary (per the Git Workflow rules above).
4. **When a plan references a follow-on plan or the work is part of a larger sequence, provide the user with the exact prompt to hand to the next agent in a new session.** The prompt must be self-contained: include the working directory, branch state, what was completed, what comes next, and any constraints the next agent needs.

## Architecture Notes

- `backend/src/services/navigation_service.py` — core navigation; currently being refactored across multiple phases
- `LAWN_LEGACY_NAV=1` — selects the pre-Phase-2 localization path inside `NavigationService` (§13 rollback flag)
- `USE_LEGACY_NAVIGATION=1` — disables `LocalizationService` delegation (Phase 2 guard)
- `phase-1-complete` git tag — known-good baseline for bisecting Phase 2 regressions
- `scripts/replay_navigation.py --compare` — runs both legacy and refactored paths against a JSONL fixture and reports per-step divergence
- `docs/rollback-bisect.md` — operator runbook for rollback, bisect, and compare-run procedures
