"""Power History Service — logs power telemetry with activity tags to SQLite.

Records time-series power data (battery voltage/current, solar power, load power,
estimated SoC) tagged with the current mower activity (idle, mowing, manual,
charging, etc.).  Provides query helpers for the Power History API endpoint.

Sampling cadence:
  - Day (sun above civil-twilight threshold, -6°): every LOG_INTERVAL_DAY_S seconds
  - Night: every LOG_INTERVAL_NIGHT_S seconds
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Default sampling intervals (seconds)
LOG_INTERVAL_DAY_S: float = 2.0
LOG_INTERVAL_NIGHT_S: float = 30.0

# Activity tag constants
ACTIVITY_IDLE = "idle"
ACTIVITY_MOWING = "mowing"
ACTIVITY_MANUAL = "manual"
ACTIVITY_RETURNING = "returning"
ACTIVITY_PAUSED = "paused"
ACTIVITY_CHARGING = "charging"
ACTIVITY_ESTOP = "emergency_stop"
ACTIVITY_UNKNOWN = "unknown"

# Table DDL — created if absent (no migration version bump needed)
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS power_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          REAL    NOT NULL,          -- Unix epoch seconds (UTC)
    iso_ts      TEXT    NOT NULL,          -- ISO-8601 string for readability
    batt_v      REAL,                      -- battery voltage (V)
    batt_a      REAL,                      -- battery current (A, + = charging)
    batt_w      REAL,                      -- battery power (W)
    solar_w     REAL,                      -- solar power (W)
    load_w      REAL,                      -- load power (W)
    soc_pct     REAL,                      -- state of charge estimate (0–100)
    source      TEXT,                      -- canonical battery telemetry provenance
    sample_age_s REAL,                     -- age of source sample when logged
    fresh       INTEGER NOT NULL DEFAULT 0,
    activity    TEXT    NOT NULL DEFAULT 'idle'
);
CREATE INDEX IF NOT EXISTS idx_power_history_ts ON power_history(ts);
"""

# Prune records older than this many days to keep the DB from growing unbounded
_PRUNE_DAYS = 7

class PowerHistoryService:
    """Logs power samples to SQLite and provides query helpers."""

    def __init__(self, persistence, energy_service) -> None:
        self._persistence = persistence  # PersistenceLayer instance
        self._energy = energy_service
        self._running = False
        self._task: asyncio.Task | None = None
        self._is_day = True  # set by PowerManager
        self._ensure_table()

    # ------------------------------------------------------------------
    # Table lifecycle
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        try:
            with self._persistence.get_connection() as conn:
                conn.executescript(_CREATE_TABLE_SQL)
                columns = {row[1] for row in conn.execute("PRAGMA table_info(power_history)")}
                for name, declaration in (
                    ("source", "TEXT"),
                    ("sample_age_s", "REAL"),
                    ("fresh", "INTEGER NOT NULL DEFAULT 0"),
                ):
                    if name not in columns:
                        conn.execute(
                            f"ALTER TABLE power_history ADD COLUMN {name} {declaration}"
                        )
                conn.commit()
        except Exception:
            logger.exception("PowerHistoryService: failed to create power_history table")

    # ------------------------------------------------------------------
    # Background logging loop
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="power_history_log")
        logger.info("PowerHistoryService started")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("PowerHistoryService stopped")

    async def _run_loop(self) -> None:
        while self._running:
            interval = LOG_INTERVAL_DAY_S if self._is_day else LOG_INTERVAL_NIGHT_S
            await asyncio.sleep(interval)
            if not self._running:
                break
            try:
                await self._log_sample()
            except Exception:
                logger.exception("PowerHistoryService: error logging sample")

    async def _log_sample(self) -> None:
        from ..models.navigation_state import NavigationMode
        from .navigation_service import NavigationService

        state = self._energy.current_state()

        activity = ACTIVITY_IDLE
        try:
            nav = NavigationService.get_instance()
            mode = nav.navigation_state.navigation_mode
            if mode == NavigationMode.AUTO:
                # Distinguish mowing vs returning via the mission executor's active status
                try:
                    from .mission_service import get_mission_service
                    ms = get_mission_service(nav)
                    if hasattr(ms, "active_mission") and ms.active_mission is not None:
                        activity = ACTIVITY_MOWING
                    else:
                        activity = ACTIVITY_MOWING
                except Exception:
                    activity = ACTIVITY_MOWING
            elif mode == NavigationMode.MANUAL:
                activity = ACTIVITY_MANUAL
            elif mode == NavigationMode.RETURN_HOME:
                activity = ACTIVITY_RETURNING
            elif mode == NavigationMode.PAUSED:
                activity = ACTIVITY_PAUSED
            elif mode == NavigationMode.EMERGENCY_STOP:
                activity = ACTIVITY_ESTOP
            else:
                activity = ACTIVITY_IDLE
        except Exception:
            pass

        if state.charging_confirmed and activity == ACTIVITY_IDLE:
            activity = ACTIVITY_CHARGING

        now = datetime.now(UTC)
        ts = now.timestamp()
        iso_ts = now.isoformat()

        self._write_sample(
            ts=ts,
            iso_ts=iso_ts,
            batt_v=state.voltage,
            batt_a=state.battery_current,
            batt_w=state.battery_power,
            solar_w=state.solar_power,
            load_w=state.load_power,
            soc_pct=state.soc_percent,
            source=state.source,
            sample_age_s=state.sample_age_seconds,
            fresh=int(state.fresh),
            activity=activity,
        )

    def _write_sample(self, **kwargs) -> None:
        try:
            with self._persistence.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO power_history
                        (ts, iso_ts, batt_v, batt_a, batt_w, solar_w, load_w, soc_pct,
                         source, sample_age_s, fresh, activity)
                    VALUES (:ts, :iso_ts, :batt_v, :batt_a, :batt_w, :solar_w, :load_w,
                            :soc_pct, :source, :sample_age_s, :fresh, :activity)
                    """,
                    kwargs,
                )
                conn.commit()
        except Exception:
            logger.exception("PowerHistoryService: failed to write sample")

    # ------------------------------------------------------------------
    # Time-of-day control (called by PowerManager)
    # ------------------------------------------------------------------

    def set_is_day(self, is_day: bool) -> None:
        """Switch log cadence between day (2 s) and night (30 s)."""
        self._is_day = is_day

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def query_history(
        self,
        *,
        hours: float = 24.0,
        resolution_minutes: float = 1.0,
        activity_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return time-bucketed power history rows.

        Rows are averaged into buckets of *resolution_minutes* width.
        Returns newest-first order within each bucket for consistency with
        UI rendering conventions.
        """
        now_ts = datetime.now(UTC).timestamp()
        since_ts = now_ts - hours * 3600.0
        bucket_s = max(1.0, resolution_minutes * 60.0)

        activity_clause = ""
        if activity_filter:
            activity_clause = "AND activity = ?"

        # Build query with all-positional params (sqlite3 doesn't allow mixing named + positional)
        where_params: list[Any] = [since_ts]
        if activity_filter:
            where_params.append(activity_filter)
        sql = f"""
            SELECT
                CAST(ts / {bucket_s} AS INTEGER) * {bucket_s} + {bucket_s} / 2 AS bucket_ts,
                AVG(batt_v), AVG(batt_a), AVG(batt_w), AVG(solar_w), AVG(load_w),
                AVG(soc_pct), GROUP_CONCAT(DISTINCT source), MAX(sample_age_s),
                MIN(fresh), activity
            FROM power_history
            WHERE ts >= ?
            {activity_clause}
            GROUP BY CAST(ts / {bucket_s} AS INTEGER), activity
            ORDER BY bucket_ts ASC
        """
        try:
            with self._persistence.get_connection() as conn:
                cursor = conn.execute(sql, where_params)
                rows = []
                for row in cursor.fetchall():
                    (
                        bucket_ts,
                        batt_v,
                        batt_a,
                        batt_w,
                        solar_w,
                        load_w,
                        soc_pct,
                        source,
                        sample_age_s,
                        fresh,
                        activity,
                    ) = row
                    rows.append(
                        {
                            "ts": bucket_ts,
                            "iso_ts": datetime.fromtimestamp(bucket_ts, UTC).isoformat(),
                            "batt_v": round(batt_v, 3) if batt_v is not None else None,
                            "batt_a": round(batt_a, 3) if batt_a is not None else None,
                            "batt_w": round(batt_w, 2) if batt_w is not None else None,
                            "solar_w": round(solar_w, 2) if solar_w is not None else None,
                            "load_w": round(load_w, 2) if load_w is not None else None,
                            "soc_pct": round(soc_pct, 1) if soc_pct is not None else None,
                            "source": source,
                            "sample_age_s": sample_age_s,
                            "fresh": bool(fresh),
                            "activity": activity,
                        }
                    )
                return rows
        except Exception:
            logger.exception("PowerHistoryService: query_history failed")
            return []

    def query_raw(
        self,
        *,
        hours: float = 1.0,
        limit: int = 3600,
    ) -> list[dict[str, Any]]:
        """Return raw (un-bucketed) rows for the last *hours* hours."""
        now_ts = datetime.now(UTC).timestamp()
        since_ts = now_ts - hours * 3600.0
        try:
            with self._persistence.get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT ts, iso_ts, batt_v, batt_a, batt_w, solar_w, load_w, soc_pct,
                           source, sample_age_s, fresh, activity
                    FROM power_history
                    WHERE ts >= ?
                    ORDER BY ts ASC
                    LIMIT ?
                    """,
                    (since_ts, limit),
                )
                rows = []
                for row in cursor.fetchall():
                    (
                        ts,
                        iso_ts,
                        batt_v,
                        batt_a,
                        batt_w,
                        solar_w,
                        load_w,
                        soc_pct,
                        source,
                        sample_age_s,
                        fresh,
                        activity,
                    ) = row
                    rows.append(
                        {
                            "ts": ts,
                            "iso_ts": iso_ts,
                            "batt_v": batt_v,
                            "batt_a": batt_a,
                            "batt_w": batt_w,
                            "solar_w": solar_w,
                            "load_w": load_w,
                            "soc_pct": soc_pct,
                            "source": source,
                            "sample_age_s": sample_age_s,
                            "fresh": bool(fresh),
                            "activity": activity,
                        }
                    )
                return rows
        except Exception:
            logger.exception("PowerHistoryService: query_raw failed")
            return []

    def prune_old_records(self) -> int:
        """Delete records older than _PRUNE_DAYS days. Returns rows deleted."""
        cutoff = datetime.now(UTC).timestamp() - _PRUNE_DAYS * 86400.0
        try:
            with self._persistence.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM power_history WHERE ts < ?", (cutoff,)
                )
                return cursor.rowcount
        except Exception:
            logger.exception("PowerHistoryService: prune failed")
            return 0


# Module-level singleton — populated by main.py during startup
_instance: PowerHistoryService | None = None


def get_power_history_service() -> PowerHistoryService | None:
    return _instance


def init_power_history_service(persistence, energy_service) -> PowerHistoryService:
    global _instance
    _instance = PowerHistoryService(persistence, energy_service)
    return _instance
