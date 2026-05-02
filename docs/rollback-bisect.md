# Rollback and Bisect Strategy

This document describes how to handle a field regression that surfaces during
the Phase 2 navigation refactor.  It implements §13 of
`docs/major-architecture-and-code-improvement-plan.md`.

## Phase milestone tags

| Tag | What it marks |
|-----|---------------|
| `phase-1-complete` | RuntimeContext (§1), MotorCommandGateway (§4), replay harness (§8) all merged and green. Safe baseline for bisecting any Phase 2 regression. |
| `phase-2-localization-extracted` | LocalizationService extracted from NavigationService; legacy path still runnable. Add this tag when the Phase 2 extraction PR merges. |
| `phase-2-parity-proven` | Replay parity confirmed on at least one real yard-run fixture with zero divergence. Safe to delete the legacy path. Add this tag when parity is signed off. |

## Switching to the legacy navigation path

If a field regression surfaces after the Phase 2 extraction lands, switch
the production mower to the pre-extraction implementation without reverting
any commits:

```bash
# On the Raspberry Pi, in the lawnberry directory:
export LAWN_LEGACY_NAV=1
sudo systemctl restart lawnberry-backend
```

To make the flag persist across reboots, add it to the systemd unit's
`[Service]` block:

```ini
[Service]
Environment="LAWN_LEGACY_NAV=1"
```

Then reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart lawnberry-backend
```

To switch back to the refactored path:

```bash
# Remove the env var from the unit file, then:
sudo systemctl daemon-reload
sudo systemctl restart lawnberry-backend
```

## Verifying which path is active

The backend logs the active path at INFO level during the first
`update_navigation_state` call.  Look for:

```
INFO  navigation_service  legacy localization path active (LAWN_LEGACY_NAV=1)
```

or its absence (refactored path is active).

## Bisecting a regression

If the flag switch above restores correct behavior, use `git bisect` to
identify the offending commit:

```bash
git bisect start
git bisect bad HEAD           # current HEAD has the regression
git bisect good phase-1-complete  # known-good baseline

# git bisect will check out commits for you.  At each step, test the mower
# (or run the replay harness) and tell bisect the result:
SIM_MODE=1 python scripts/replay_navigation.py \
  tests/fixtures/navigation/synthetic_straight_drive.jsonl

git bisect good   # if the step is OK
git bisect bad    # if the step has the regression

# When bisect finishes, it names the first bad commit.
git bisect reset
```

## Running a compare-run to identify divergence

Before filing a bug or reverting a commit, run compare-mode on a fixture
captured from the regressing yard run:

```bash
SIM_MODE=1 python scripts/replay_navigation.py <captured-run.jsonl> \
  --compare --report-json /tmp/divergence.json --verbose
```

`divergence.json` will list every step where legacy and refactored outputs
differ, with per-field deltas.  Attach this file to the bug report.

## Behavioral parity boundaries

| Domain | Legacy and refactored must agree | Intentional change permitted |
|--------|----------------------------------|------------------------------|
| Dead-reckoning position | must agree, until encoder odometry lands (§3) | No |
| GPS-fused position | must agree | No |
| Heading (IMU + GPS COG snap) | must agree | No |
| Waypoint index advancement | must agree | No |
| Velocity estimate | must agree | Slight change acceptable when encoder odometry replaces hardcoded 0.1 m step (§3 — document with justification in the extraction PR) |
| Motor command values | must agree (gateway enforces this independently) | No |
| Navigation mode transitions (IDLE→NAVIGATING→etc.) | must agree | Only if a bug in the legacy path is being fixed — document the intentional change |

When a compare-run shows divergence in a field marked "must agree", it is a
bug, not a feature.  Fix the refactored path before merging.

When a divergence is intentional (e.g., encoder odometry replaces
hardcoded step), add a row to this table with the justification and the PR
number, and regenerate the golden fixture before merging.
