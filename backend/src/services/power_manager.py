"""Intelligent Power Manager for LawnBerry Pi.

Manages three non-positioning subsystems to reduce idle power consumption while
keeping GPS continuously available for safety and operator readiness:

1. Camera idle pause — stops the camera capture loop when no mission is active
   and no AI inference has been requested recently.  Restarts automatically when
   a mission begins or inference is requested.

2. Victron BLE poll rate — slows the Victron BLE background refresh from 10 s
   (day) to 60 s (night) so BLE doesn't stay active overnight.

3. AI inference — soft-disables inference when the mower is fully idle; re-
   enables when a mission starts.

Solar "dark" detection uses a simple solar-elevation formula (no external API).
The mower's approximate position (used only for sun-angle) comes from the last
known GPS reading or falls back to a reasonable default.

All decisions are made locally in a lightweight polling loop; the loop period is
short (POLL_INTERVAL_S) so transitions feel instantaneous to the user.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .power_history_service import PowerHistoryService

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Tuning constants
# ------------------------------------------------------------------
POLL_INTERVAL_S: float = 10.0           # main loop period
SOLAR_ELEVATION_THRESHOLD = -6.0        # civil twilight (degrees)
MOTION_SPEED_THRESHOLD_MS = 0.05        # m/s below which we consider "stopped"
CAMERA_IDLE_TIMEOUT_S: float = 30.0     # camera off delay after going idle
VICTRON_RATE_DAY_S: float = 10.0        # BLE refresh interval during day
VICTRON_RATE_NIGHT_S: float = 60.0      # BLE refresh interval at night


# ------------------------------------------------------------------
# Solar elevation helper (no external dependencies)
# ------------------------------------------------------------------

def _solar_elevation(lat_deg: float, lon_deg: float, dt_utc: datetime) -> float:
    """Return approximate solar elevation in degrees for *dt_utc* at *lat/lon*.

    Uses a compact NOAA-derived algorithm accurate to ±0.5° for |lat| < 66°.
    """
    lat = math.radians(lat_deg)
    # Julian day number
    jd = (
        dt_utc.toordinal()
        + 1721425.5
        + (dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0) / 24.0
    )
    n = jd - 2451545.0                  # days since J2000.0
    L = math.radians((280.46 + 0.9856474 * n) % 360)    # mean longitude
    g = math.radians((357.528 + 0.9856003 * n) % 360)   # mean anomaly
    lam = L + math.radians(1.915) * math.sin(g) + math.radians(0.02) * math.sin(2 * g)
    eps = math.radians(23.439 - 0.0000004 * n)          # obliquity
    sin_dec = math.sin(eps) * math.sin(lam)
    cos_dec = math.cos(math.asin(sin_dec))
    # Equation of time (minutes) — simplified
    eot_minutes = 4 * math.degrees(L - 0.0057183 - lam + math.atan2(
        math.cos(eps) * math.sin(lam), math.cos(lam)
    ))
    solar_noon_h = 12.0 - lon_deg / 15.0 - eot_minutes / 60.0
    hour = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0
    hour_angle = math.radians(15.0 * (hour - solar_noon_h))
    sin_elev = math.sin(lat) * sin_dec + math.cos(lat) * cos_dec * math.cos(hour_angle)
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_elev))))


def _is_dark(lat: float, lon: float) -> bool:
    """Return True when solar elevation is below civil-twilight threshold."""
    try:
        elev = _solar_elevation(lat, lon, datetime.now(UTC))
        return elev < SOLAR_ELEVATION_THRESHOLD
    except Exception:
        return False  # fail open (assume day) to avoid spurious suspensions


# ------------------------------------------------------------------
# PowerManager
# ------------------------------------------------------------------

class PowerManager:
    """Background service managing GPS, camera, AI, and Victron power modes."""

    def __init__(self, power_history_service: PowerHistoryService | None = None) -> None:
        self._history = power_history_service
        self._running = False
        self._task: asyncio.Task | None = None
        self._sensor_manager = None  # lazily resolved from websocket_hub

        # State tracking
        self._gps_suspended = False
        self._last_gps_suspend_ts: float = 0.0
        self._last_gps_resume_ts: float = 0.0
        self._camera_paused_by_pm = False
        self._camera_idle_since: float | None = None
        self._ai_soft_disabled = False
        self._is_day = True

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="power_manager")
        logger.info("PowerManager started")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # Resume everything before shutdown
        await self._resume_gps_if_suspended()
        await self._resume_camera_if_paused()
        await self._reenable_ai_if_disabled()
        logger.info("PowerManager stopped")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("PowerManager: error in tick")
            await asyncio.sleep(POLL_INTERVAL_S)

    async def _tick(self) -> None:
        import time as _time

        # -- Gather state --
        lat, lon = self._get_position()
        dark = _is_dark(lat, lon)
        mission_active = self._is_mission_active()
        moving = self._is_moving()
        now = _time.monotonic()

        # Update power history cadence
        self._is_day = not dark
        if self._history is not None:
            self._history.set_is_day(self._is_day)

        # GPS is a safety/readiness input, not an idle power-saving target.
        # Keeping it live avoids a deadlock where mission preflight requires a
        # fresh fix but the old power policy waited for a mission to resume GPS.
        await self._resume_gps_if_suspended()

        # -- Victron BLE rate --
        await self._set_victron_rate(dark)

        # -- Camera management --
        if mission_active:
            # Always ensure camera is running during a mission
            if self._camera_paused_by_pm:
                await self._resume_camera_if_paused()
            self._camera_idle_since = None
        else:
            # Start idle countdown
            if self._camera_idle_since is None:
                self._camera_idle_since = now
            elif now - self._camera_idle_since >= CAMERA_IDLE_TIMEOUT_S and not self._camera_paused_by_pm:
                await self._pause_camera()

        # -- AI inference --
        if mission_active:
            await self._reenable_ai_if_disabled()
        elif dark and not moving and not mission_active:
            await self._soft_disable_ai()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _get_sensor_manager(self):
        """Return the live SensorManager (from websocket hub or cached)."""
        if self._sensor_manager is not None:
            return self._sensor_manager
        try:
            from .websocket_hub import websocket_hub
            sm = getattr(websocket_hub, "_sensor_manager", None)
            if sm is not None:
                self._sensor_manager = sm
                return sm
        except Exception:
            pass
        return None

    def _get_position(self) -> tuple[float, float]:
        """Return (lat, lon) from last GPS fix, or default (US central)."""
        try:
            sm = self._get_sensor_manager()
            if sm is not None and sm.gps.last_reading is not None:
                r = sm.gps.last_reading
                if r.latitude is not None and r.longitude is not None:
                    return float(r.latitude), float(r.longitude)
        except Exception:
            pass
        # Default: US geographic center (lat 39.5, lon -98.35)
        return 39.5, -98.35

    def _is_mission_active(self) -> bool:
        try:
            from ..models.navigation_state import NavigationMode
            from .navigation_service import NavigationService
            nav = NavigationService.get_instance()
            mode = nav.navigation_state.navigation_mode
            return mode in (NavigationMode.AUTO, NavigationMode.RETURN_HOME, NavigationMode.PAUSED)
        except Exception:
            return False

    def _is_moving(self) -> bool:
        """Return True if IMU/GPS indicates the mower is moving."""
        try:
            sm = self._get_sensor_manager()
            if sm is None:
                return False
            # Check last GPS reading speed
            gps = sm.gps.last_reading
            gps_speed = getattr(gps, "speed", getattr(gps, "speed_ms", None))
            if gps is not None and gps_speed is not None:
                if abs(float(gps_speed)) > MOTION_SPEED_THRESHOLD_MS:
                    return True
            # Check IMU angular velocity (any axis > threshold → rotating = moving)
            imu = sm.imu.last_reading if hasattr(sm, "imu") else None
            if imu is not None:
                for attr in (
                    "gyro_x",
                    "gyro_y",
                    "gyro_z",
                    "angular_velocity_x",
                    "angular_velocity_y",
                    "angular_velocity_z",
                ):
                    val = getattr(imu, attr, None)
                    if val is not None and abs(float(val)) > 0.05:  # rad/s threshold
                        return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # GPS control
    # ------------------------------------------------------------------

    async def _suspend_gps(self) -> None:
        """Compatibility no-op: GPS must remain continuously available."""
        await self._resume_gps_if_suspended()
        logger.warning("PowerManager: GPS suspend request ignored; continuous fix required")

    async def _resume_gps_if_suspended(self) -> None:
        try:
            sm = self._get_sensor_manager()
            if sm is None or not hasattr(sm, "gps"):
                return
            driver = getattr(sm.gps, "_driver", None)
            driver_suspended = bool(getattr(driver, "is_suspended", False))
            if (
                driver is not None
                and hasattr(driver, "resume")
                and (self._gps_suspended or driver_suspended)
            ):
                driver.resume()
                self._gps_suspended = False
                logger.info("PowerManager: GPS resumed")
        except Exception:
            logger.exception("PowerManager: failed to resume GPS")

    # ------------------------------------------------------------------
    # Victron BLE rate
    # ------------------------------------------------------------------

    async def _set_victron_rate(self, dark: bool) -> None:
        try:
            sm = self._get_sensor_manager()
            if sm is None or not hasattr(sm, "power"):
                return
            driver = getattr(sm.power, "_victron_driver", None)
            if driver is None:
                return
            target = VICTRON_RATE_NIGHT_S if dark else VICTRON_RATE_DAY_S
            if hasattr(driver, "set_refresh_interval"):
                driver.set_refresh_interval(target)
        except Exception:
            pass  # Non-critical; log only on unexpected errors

    # ------------------------------------------------------------------
    # Camera control
    # ------------------------------------------------------------------

    async def _pause_camera(self) -> None:
        try:
            from .camera_runtime import camera_service

            if camera_service.stream.is_active:
                await camera_service.stop_streaming()
                self._camera_paused_by_pm = True
                logger.info("PowerManager: camera capture paused (idle)")
        except Exception:
            logger.exception("PowerManager: failed to pause camera")

    async def _resume_camera_if_paused(self) -> None:
        if not self._camera_paused_by_pm:
            return
        try:
            from .camera_runtime import camera_service

            if not camera_service.stream.is_active:
                await camera_service.start_streaming()
                self._camera_paused_by_pm = False
                self._camera_idle_since = None
                logger.info("PowerManager: camera capture resumed")
        except Exception:
            logger.exception("PowerManager: failed to resume camera")

    # ------------------------------------------------------------------
    # AI inference
    # ------------------------------------------------------------------

    async def _soft_disable_ai(self) -> None:
        if self._ai_soft_disabled:
            return
        try:
            from .ai_service import get_ai_service
            svc = get_ai_service()
            if hasattr(svc, "set_enabled"):
                svc.set_enabled(False)
                self._ai_soft_disabled = True
                logger.info("PowerManager: AI inference soft-disabled (idle+dark)")
        except Exception:
            pass

    async def _reenable_ai_if_disabled(self) -> None:
        if not self._ai_soft_disabled:
            return
        try:
            from .ai_service import get_ai_service
            svc = get_ai_service()
            if hasattr(svc, "set_enabled"):
                svc.set_enabled(True)
                self._ai_soft_disabled = False
                logger.info("PowerManager: AI inference re-enabled")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public: external trigger to wake GPS immediately
    # (called by mission executor at mission start)
    # ------------------------------------------------------------------

    async def wake_for_mission(self) -> None:
        """Immediately resume all suspended subsystems for mission start."""
        await self._resume_gps_if_suspended()
        await self._resume_camera_if_paused()
        await self._reenable_ai_if_disabled()
        self._camera_idle_since = None
        logger.info("PowerManager: woken for mission start")


# Module-level singleton — populated by main.py
_instance: PowerManager | None = None


def get_power_manager() -> PowerManager | None:
    return _instance


def init_power_manager(power_history_service=None) -> PowerManager:
    global _instance
    _instance = PowerManager(power_history_service)
    return _instance
