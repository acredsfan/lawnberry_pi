#!/usr/bin/env python3
"""
cleanup_test_fixtures.py — purge test-fixture rows from the production DB.

Background
----------
The LawnBerry test suite previously wrote to the production database
(data/lawnberry.db) instead of an in-memory database.  This left 30+
mission rows in the prod DB, causing MissionService.recover_persisted_missions()
to resurrect deleted missions every time the backend started.

What this script does
---------------------
- Deletes ALL rows from ``missions``.
- Deletes ALL rows from ``mission_execution_state``.
- For ``planning_jobs``: disables any enabled rows (sets enabled=0) rather
  than deleting them, because they may represent real user-created schedules.
  A note is printed so the operator can re-enable them manually if needed.

Usage
-----
  # See what would be removed (no changes made):
  python scripts/cleanup_test_fixtures.py --dry-run

  # Interactive confirmation:
  python scripts/cleanup_test_fixtures.py

  # Non-interactive (CI / scripted):
  python scripts/cleanup_test_fixtures.py --yes

  # Target a different database:
  python scripts/cleanup_test_fixtures.py --db /path/to/other.db --yes

Exit codes
----------
  0 — success (or nothing to do)
  1 — error (DB not found, SQL failure, user declined)
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def _db_default() -> Path:
    """Resolve the default DB path relative to this script's parent directory."""
    return Path(__file__).resolve().parent.parent / "data" / "lawnberry.db"


def _fetch_counts(conn: sqlite3.Connection) -> dict[str, int]:
    cur = conn.cursor()
    counts: dict[str, int] = {}

    cur.execute("SELECT COUNT(*) FROM missions")
    counts["missions"] = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM mission_execution_state")
    counts["mission_execution_state"] = cur.fetchone()[0]

    cur.execute("SELECT id, name FROM planning_jobs WHERE enabled=1")
    rows = cur.fetchall()
    counts["planning_jobs_enabled"] = len(rows)
    counts["_planning_jobs_rows"] = rows  # type: ignore[assignment]

    return counts


def _print_dry_run(counts: dict) -> None:
    rows = counts["_planning_jobs_rows"]
    print("Dry run — no changes will be made.")
    print(f"  missions:                 {counts['missions']} rows")
    print(f"  mission_execution_state:  {counts['mission_execution_state']} rows")
    if rows:
        summary = ", ".join(f"id={r[0]}, name={r[1]}" for r in rows)
        print(f"  planning_jobs (disable):  {counts['planning_jobs_enabled']} row(s) ({summary})")
    else:
        print(f"  planning_jobs (disable):  0 rows (none enabled)")
    print()
    print("Run without --dry-run to apply.")


def _apply(conn: sqlite3.Connection, counts: dict) -> None:
    cur = conn.cursor()

    cur.execute("DELETE FROM missions")
    deleted_missions = cur.rowcount
    print(f"Deleted {deleted_missions} rows from missions.")

    cur.execute("DELETE FROM mission_execution_state")
    deleted_mes = cur.rowcount
    print(f"Deleted {deleted_mes} rows from mission_execution_state.")

    enabled_rows = counts["_planning_jobs_rows"]
    if enabled_rows:
        cur.execute("UPDATE planning_jobs SET enabled=0 WHERE enabled=1")
        disabled = cur.rowcount
        ids = ", ".join(r[0] for r in enabled_rows)
        print(
            f"Disabled {disabled} planning_jobs row(s) (id={ids}).\n"
            "  NOTE: These may be real user schedules. Re-enable them via the\n"
            "  Planning UI or: UPDATE planning_jobs SET enabled=1 WHERE id IN (...)"
        )
    else:
        print("No enabled planning_jobs rows found — nothing to disable.")

    conn.commit()
    print("Done.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Purge test-fixture rows from the LawnBerry production database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=_db_default(),
        help="Path to the SQLite database (default: data/lawnberry.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted/disabled without making any changes.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt and apply immediately.",
    )
    args = parser.parse_args(argv)

    db_path: Path = args.db

    if not db_path.exists():
        print(f"ERROR: database not found at {db_path}", file=sys.stderr)
        return 1

    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.Error as exc:
        print(f"ERROR: could not open database: {exc}", file=sys.stderr)
        return 1

    try:
        counts = _fetch_counts(conn)
    except sqlite3.Error as exc:
        print(f"ERROR: could not query database: {exc}", file=sys.stderr)
        conn.close()
        return 1

    if args.dry_run:
        _print_dry_run(counts)
        conn.close()
        return 0

    # Show summary before asking / applying
    rows = counts["_planning_jobs_rows"]
    print("Will perform the following actions:")
    print(f"  Delete {counts['missions']} row(s) from missions.")
    print(f"  Delete {counts['mission_execution_state']} row(s) from mission_execution_state.")
    if rows:
        ids = ", ".join(r[0] for r in rows)
        print(f"  Disable {counts['planning_jobs_enabled']} planning_jobs row(s) (id={ids}).")
    else:
        print("  No enabled planning_jobs rows to disable.")
    print()

    if not args.yes:
        try:
            answer = input("Proceed? [y/N] ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.")
            conn.close()
            return 1
        if answer not in ("y", "yes"):
            print("Aborted.")
            conn.close()
            return 1

    try:
        _apply(conn, counts)
    except sqlite3.Error as exc:
        print(f"ERROR: database operation failed: {exc}", file=sys.stderr)
        conn.close()
        return 1

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
