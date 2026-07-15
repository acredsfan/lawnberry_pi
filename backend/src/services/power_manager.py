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
import os
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

def _solar_coordinates(dt_utc: datetime) -> tuple[float, float, float]:
    """Return mean longitude, ecliptic longitude, and obliquity in radians."""
    jd = (
        dt_utc.toordinal()
        + 1721425.5
        + (dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0) / 24.0
    )
    n = jd - 2451545.0
    mean_longitude = math.radians((280.46 + 0.9856474 * n) % 360)
    mean_anomaly = math.radians((357.528 + 0.9856003 * n) % 360)
    ecliptic_longitude = (
        mean_longitude
        + math.radians(1.915) * math.sin(mean_anomaly)
        + math.radians(0.02) * math.sin(2 * mean_anomaly)
    )
    obliquity = math.radians(23.439 - 0.0000004 * n)
    return mean_longitude, ecliptic_longitude, obliquity


def _equation_of_time_from_coordinates(
    mean_longitude: float,
    ecliptic_longitude: float,
    obliquity: float,
) -> float:
    """Return equation of time in minutes, normalized across angle wrap."""
    right_ascension = math.atan2(
        math.cos(obliquity) * math.sin(ecliptic_longitude),
        math.cos(ecliptic_longitude),
    )
    equation_angle = mean_longitude - 0.0057183 - right_ascension
    equation_angle = (equation_angle + math.pi) % (2 * math.pi) - math.pi
    return 4 * math.degrees(equation_angle)


def _equation_of_time_minutes(dt_utc: datetime) -> float:
    """Return the solar equation of time in physically bounded minutes."""
    return _equation_of_time_from_coordinates(*_solar_coordinates(dt_utc))


def _solar_elevation(lat_deg: float, lon_deg: float, dt_utc: datetime) -> float:
    """Return approximate solar elevation in degrees for *dt_utc* at *lat/lon*.

    Uses a compact NOAA-derived algorithm accurate to ±0.5° for |lat| < 66°.
    """
    lat = math.radians(lat_deg)
    mean_longitude, ecliptic_longitude, obliquity = _solar_coordinates(dt_utc)
    sin_dec = math.sin(obliquity) * math.sin(ecliptic_longitude)
    cos_dec = math.cos(math.asin(sin_dec))
    # Equation of time (minutes) — simplified
    eot_minutes = _equation_of_time_from_coordinates(
        mean_longitude,
        ecliptic_longitude,
        obliquity,
    )
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
        try:
            inference_deadline = float(
                os.getenv("AI_CAMERA_INFERENCE_TIMEOUT_SECONDS", "3.0")
            )
        except (TypeError, ValueError):
            inference_deadline = 3.0
        # Capture scheduling and IPC need a small margin beyond the owner-side
        # inference deadline, while mission admission must remain bounded.
        self._mission_ai_wake_timeout_seconds = max(
            0.5,
            min(inference_deadline + 1.0, 11.0),
        )

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
        await self._reenable_ai_if_disabled(force=True)
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
        # Mission execution and fresh operator/inference frame demand are
        # capture leases. Idle power saving begins only after both are absent.
        camera_activity_age = self._camera_activity_age_seconds()
        camera_demand_active = (
            camera_activity_age is not None
            and camera_activity_age <= CAMERA_IDLE_TIMEOUT_S
        ) or (
            camera_activity_age is None and self._camera_has_recent_demand()
        )
        if mission_active or camera_demand_active:
            await self._ensure_camera_running()
            self._camera_idle_since = None
        elif camera_activity_age is not None:
            # The activity age already includes the entire idle timeout. Do not
            # add a second timeout after its lease expires.
            if camera_activity_age >= CAMERA_IDLE_TIMEOUT_S:
                await self._pause_camera()
        else:
            # Start idle countdown
            if self._camera_idle_since is None:
                self._camera_idle_since = now
            elif now - self._camera_idle_since >= CAMERA_IDLE_TIMEOUT_S:
                await self._pause_camera()

        # -- AI inference --
        ai_needed = mission_active or camera_demand_active or moving or not dark
        if ai_needed:
            # Mission execution reasserts the canonical owner gate every tick,
            # so a camera-service restart cannot silently lose AI readiness.
            await self._reenable_ai_if_disabled(force=mission_active)
        else:
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

    def _camera_has_recent_demand(self) -> bool:
        try:
            from .camera_runtime import camera_service

            checker = getattr(camera_service, "has_recent_activity", None)
            return bool(callable(checker) and checker(CAMERA_IDLE_TIMEOUT_S))
        except Exception:
            return False

    def _camera_activity_age_seconds(self) -> float | None:
        try:
            from .camera_runtime import camera_service

            getter = getattr(camera_service, "activity_age_seconds", None)
            if not callable(getter):
                return None
            age = getter()
            return max(0.0, float(age)) if age is not None else None
        except Exception:
            return None

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

    async def _refresh_camera_status(self) -> bool:
        """Refresh remote owner truth; embedded SIM state is already canonical."""
        from .camera_runtime import camera_service

        status_getter = getattr(camera_service, "get_camera_status", None)
        if not callable(status_getter):
            return True
        try:
            outcome = status_getter()
            if asyncio.iscoroutine(outcome):
                await outcome
            return True
        except Exception:
            logger.exception("PowerManager: failed to refresh camera owner status")
            return False

    async def _pause_camera(self) -> bool:
        try:
            from .camera_runtime import camera_service

            if not await self._refresh_camera_status():
                return False
            if camera_service.stream.is_active:
                await camera_service.stop_streaming()
                logger.info("PowerManager: camera capture paused (idle)")
            self._camera_paused_by_pm = True
            return True
        except Exception:
            logger.exception("PowerManager: failed to pause camera")
            return False

    async def _resume_camera_if_paused(self) -> None:
        if not self._camera_paused_by_pm:
            return
        await self._ensure_camera_running()

    async def _ensure_camera_running(self) -> bool:
        """Idempotently restore capture for a mission or active viewer."""
        try:
            from .camera_runtime import camera_service

            if not await self._refresh_camera_status():
                return False
            if camera_service.stream.is_active:
                self._camera_paused_by_pm = False
                self._camera_idle_since = None
                return True
            started = await camera_service.start_streaming()
            if not started and not camera_service.stream.is_active:
                logger.error("PowerManager: camera owner rejected capture restart")
                return False
            self._camera_paused_by_pm = False
            self._camera_idle_since = None
            logger.info("PowerManager: camera capture resumed")
            return True
        except Exception:
            logger.exception("PowerManager: failed to resume camera")
            return False

    # ------------------------------------------------------------------
    # AI inference
    # ------------------------------------------------------------------

    async def _soft_disable_ai(self) -> None:
        # Track the desired low-power state even if one owner is temporarily
        # unreachable, then retry both acknowledgements on every dark-idle tick.
        self._ai_soft_disabled = True
        if await self._set_ai_enabled(False):
            logger.info("PowerManager: AI inference soft-disabled (idle+dark)")

    async def _reenable_ai_if_disabled(self, *, force: bool = False) -> bool:
        if not self._ai_soft_disabled and not force:
            return True
        if await self._set_ai_enabled(True):
            self._ai_soft_disabled = False
            logger.info("PowerManager: AI inference re-enabled")
            return True
        return False

    async def _set_ai_enabled(self, enabled: bool) -> bool:
        """Apply the power gate to both API state and the live camera owner."""
        local_updated = False
        owner_updated = False
        service = None
        try:
            from .ai_service import get_ai_service

            service = get_ai_service()
            service.set_enabled(enabled)
            local_updated = not enabled or bool(
                getattr(getattr(service, "ai_processing", None), "system_enabled", True)
            )
        except Exception:
            logger.debug("PowerManager: local AI gate update failed", exc_info=True)
        try:
            from .camera_runtime import camera_service

            setter = getattr(camera_service, "set_ai_enabled", None)
            if callable(setter):
                outcome = setter(enabled)
                if asyncio.iscoroutine(outcome):
                    await outcome
                owner_updated = True
                if enabled:
                    status_fresh = await self._refresh_camera_status()
                    owner_state_setter = getattr(service, "set_external_owner_state", None)
                    if status_fresh and callable(owner_state_setter):
                        owner_state_setter(
                            sim_mode=bool(getattr(camera_service, "sim_mode", True)),
                            hardware_available=bool(
                                getattr(camera_service, "hardware_available", False)
                            ),
                            ai_runtime_ready=bool(
                                getattr(camera_service, "ai_runtime_ready", False)
                            ),
                            model_sha256=getattr(camera_service, "ai_model_sha256", None),
                            error=getattr(camera_service, "ai_runtime_error", None),
                        )
                    owner_updated = bool(
                        status_fresh
                        and getattr(camera_service, "ai_runtime_ready", True)
                        and not getattr(camera_service, "hardware_fallback_active", False)
                        and (
                            getattr(camera_service, "requested_sim_mode", True)
                            or getattr(camera_service, "hardware_available", True)
                        )
                    )
                    status_getter = getattr(service, "get_ai_status", None)
                    if owner_updated and callable(status_getter):
                        ai_status = status_getter()
                        if asyncio.iscoroutine(ai_status):
                            ai_status = await ai_status
                        if isinstance(ai_status, dict):
                            local_updated = local_updated and bool(
                                ai_status.get("system_enabled", False)
                            )
                            owner_updated = owner_updated and bool(
                                ai_status.get("model_ready", False)
                            )
        except Exception:
            logger.debug("PowerManager: camera-owner AI gate update failed", exc_info=True)
        # Hardware inference is owned by the camera process, while the local
        # AIService owns API truth. A transition is complete only when both
        # owners acknowledge it; otherwise keep retrying on subsequent ticks.
        return local_updated and owner_updated

    # ------------------------------------------------------------------
    # Public: external trigger to wake GPS immediately
    # (called by mission executor at mission start)
    # ------------------------------------------------------------------

    async def wake_for_viewer(self) -> bool:
        """Wake capture and issue one immediate AI-owner enable attempt.

        Unlike mission admission this does not wait for a fresh inference result;
        the Control response stays responsive while the existing retry loop
        continues until the exact-frame detector proves readiness.
        """
        try:
            from .camera_runtime import camera_service

            recorder = getattr(camera_service, "record_activity", None)
            if callable(recorder):
                recorder()
        except Exception:
            logger.debug("PowerManager: failed to record viewer demand", exc_info=True)
        camera_ready = await self._ensure_camera_running()
        if camera_ready:
            await self._reenable_ai_if_disabled(force=True)
        return camera_ready

    async def wake_for_mission(self) -> None:
        """Synchronously establish camera and AI readiness for mission start."""
        await self._resume_gps_if_suspended()
        camera_ready = await self._ensure_camera_running()
        ai_ready = False
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._mission_ai_wake_timeout_seconds
        while camera_ready:
            ai_ready = await self._reenable_ai_if_disabled(force=True)
            if ai_ready or loop.time() >= deadline:
                break
            await asyncio.sleep(min(0.1, max(0.0, deadline - loop.time())))
        if not camera_ready or not ai_ready:
            raise RuntimeError(
                "Mission power wake failed: "
                f"camera_ready={camera_ready} ai_owner_acknowledged={ai_ready}"
            )
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
