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
import math
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
    activity    TEXT    NOT NULL DEFAULT 'idle'
);
CREATE INDEX IF NOT EXISTS idx_power_history_ts ON power_history(ts);
"""

# Prune records older than this many days to keep the DB from growing unbounded
_PRUNE_DAYS = 7


def _estimate_soc(battery_voltage: float | None) -> float | None:
    """Very rough LiFePO4 SoC estimate from resting voltage.

    LiFePO4 12 V (4S) approximate voltage → SoC mapping:
      14.6 V → 100%  (fully charged / absorption)
      13.3 V →  90%
      13.2 V →  70%
      13.1 V →  40%
      12.8 V →  20%
      12.0 V →   0%  (cut-off)

    The flat discharge curve makes this imprecise; treat as a rough indicator.
    """
    if battery_voltage is None:
        return None
    v = float(battery_voltage)
    if v >= 14.4:
        return 100.0
    if v >= 13.3:
        return 90.0 + (v - 13.3) / (14.4 - 13.3) * 10.0
    if v >= 13.2:
        return 70.0 + (v - 13.2) / (13.3 - 13.2) * 20.0
    if v >= 13.1:
        return 40.0 + (v - 13.1) / (13.2 - 13.1) * 30.0
    if v >= 12.8:
        return 20.0 + (v - 12.8) / (13.1 - 12.8) * 20.0
    if v >= 12.0:
        return max(0.0, (v - 12.0) / (12.8 - 12.0) * 20.0)
    return 0.0


class PowerHistoryService:
    """Logs power samples to SQLite and provides query helpers."""

    def __init__(self, persistence) -> None:
        self._persistence = persistence  # PersistenceLayer instance
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
        from .navigation_service import NavigationService
        from ..models.navigation_state import NavigationMode
        from ..core.state_manager import get_sensor_manager

        sm = get_sensor_manager()
        if sm is None:
            return

        power = None
        try:
            power = await sm.power.read_power()
        except Exception:
            pass

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

        # Detect charging: solar power > minimal threshold and battery current
        # positive (from Victron perspective, positive I = charging)
        if power is not None:
            solar_w = getattr(power, "solar_power", None)
            batt_a = getattr(power, "battery_current", None)
            if solar_w is not None and solar_w > 5.0 and activity == ACTIVITY_IDLE:
                if batt_a is None or batt_a >= 0:
                    activity = ACTIVITY_CHARGING

        batt_v = getattr(power, "battery_voltage", None) if power else None
        batt_a = getattr(power, "battery_current", None) if power else None
        solar_w = getattr(power, "solar_power", None) if power else None
        load_w = getattr(power, "load_power", None) if power else None

        # Derive load_w from load current × voltage if not directly available
        if load_w is None and power is not None:
            lc = getattr(power, "load_current", None)
            if lc is not None and batt_v is not None:
                load_w = round(float(lc) * float(batt_v), 2)

        batt_w: float | None = None
        if batt_v is not None and batt_a is not None:
            batt_w = round(float(batt_v) * float(batt_a), 2)

        soc_pct = _estimate_soc(batt_v)

        now = datetime.now(UTC)
        ts = now.timestamp()
        iso_ts = now.isoformat()

        self._write_sample(
            ts=ts,
            iso_ts=iso_ts,
            batt_v=batt_v,
            batt_a=batt_a,
            batt_w=batt_w,
            solar_w=solar_w,
            load_w=load_w,
            soc_pct=soc_pct,
            activity=activity,
        )

    def _write_sample(self, **kwargs) -> None:
        try:
            with self._persistence.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO power_history
                        (ts, iso_ts, batt_v, batt_a, batt_w, solar_w, load_w, soc_pct, activity)
                    VALUES (:ts, :iso_ts, :batt_v, :batt_a, :batt_w, :solar_w, :load_w, :soc_pct, :activity)
                    """,
                    kwargs,
                )
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
                AVG(soc_pct), activity
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
                    (bucket_ts, batt_v, batt_a, batt_w, solar_w, load_w, soc_pct, activity) = row
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
                    SELECT ts, iso_ts, batt_v, batt_a, batt_w, solar_w, load_w, soc_pct, activity
                    FROM power_history
                    WHERE ts >= ?
                    ORDER BY ts ASC
                    LIMIT ?
                    """,
                    (since_ts, limit),
                )
                rows = []
                for row in cursor.fetchall():
                    (ts, iso_ts, batt_v, batt_a, batt_w, solar_w, load_w, soc_pct, activity) = row
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


def init_power_history_service(persistence) -> PowerHistoryService:
    global _instance
    _instance = PowerHistoryService(persistence)
    return _instance
