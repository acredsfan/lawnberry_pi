"""Timezone detection utilities for defaulting UI settings.

Primary strategy: prefer the mower's current GPS fix when available,
falling back to the Raspberry Pi's configured system timezone.
- Debian/Ubuntu: /etc/timezone contains the IANA zone name (e.g., "America/New_York").
- Generic: /etc/localtime is a symlink to "/usr/share/zoneinfo/<Region>/<City>".

We also allow dependency-free unit testing by passing an alternate base_path
or GPS lookup so tests can simulate environments without hardware.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional, Tuple

from timezonefinder import TimezoneFinder


@dataclass
class TimezoneInfo:
    timezone: str
    source: str  # 'system' | 'gps' | 'default'


logger = logging.getLogger(__name__)

_TZ_FINDER = TimezoneFinder(in_memory=True)
_CACHE_TTL = timedelta(minutes=30)
_COORD_CACHE_TTL = timedelta(minutes=5)

_timezone_cache: Optional[tuple[datetime, TimezoneInfo]] = None
_coordinate_cache: Optional[tuple[datetime, Tuple[float, float]]] = None


def _read_text_file(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return None


def _detect_os_timezone(base_path: str) -> TimezoneInfo:
    etc_path = os.path.join(base_path, "etc")

    # 1) Debian/Ubuntu style
    tzfile = os.path.join(etc_path, "timezone")
    tz = _read_text_file(tzfile)
    if tz and "/" in tz and not tz.endswith("/"):
        return TimezoneInfo(timezone=tz, source="system")

    # 2) Symlink under /etc/localtime -> /usr/share/zoneinfo/Region/City
    localtime_path = os.path.join(etc_path, "localtime")
    try:
        if os.path.islink(localtime_path):
            target = os.readlink(localtime_path)
            if not target.startswith("/"):
                target = os.path.normpath(os.path.join(etc_path, target))
            marker = "/zoneinfo/"
            idx = target.find(marker)
            if idx != -1:
                tzname = target[idx + len(marker) :]
                if tzname and "/" in tzname:
                    return TimezoneInfo(timezone=tzname, source="system")
    except Exception:
        logger.debug("Failed to resolve /etc/localtime symlink", exc_info=True)

    return TimezoneInfo(timezone="UTC", source="default")


def _timezone_from_coordinates(lat: float, lon: float) -> Optional[str]:
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None

    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
        return None

    tz_name = _TZ_FINDER.timezone_at(lat=lat_f, lng=lon_f)
    if not tz_name:
        tz_name = _TZ_FINDER.closest_timezone_at(lat=lat_f, lng=lon_f)
    return tz_name


def _run_coro_sync(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            # If run_until_complete failed or exited early, ensure the created
            # coroutine is cleaned up to avoid "coroutine was never awaited" warnings.
            with suppress(Exception):
                if hasattr(coro, "close"):
                    coro.close()
    finally:
        # Gracefully shut down async generators; protect against races where the
        # loop may already be closed by ensuring the coroutine is also closed
        # if run_until_complete cannot execute.
        with suppress(Exception):
            shutdown_coro = loop.shutdown_asyncgens()
            try:
                loop.run_until_complete(shutdown_coro)
            finally:
                with suppress(Exception):
                    if hasattr(shutdown_coro, "close"):
                        shutdown_coro.close()
        asyncio.set_event_loop(None)
        with suppress(Exception):
            loop.close()


def _default_gps_lookup(timeout: float = 2.5) -> Optional[Tuple[float, float]]:
    global _coordinate_cache

    if os.environ.get("LAWN_BERRY_DISABLE_GPS_TZ", "").lower() in {"1", "true", "yes"}:
        return None

    now = datetime.now()
    if _coordinate_cache and (now - _coordinate_cache[0]) < _COORD_CACHE_TTL:
        return _coordinate_cache[1]

    async def _read() -> Optional[Tuple[float, float]]:
        from .sensor_manager import SensorManager  # type: ignore

        manager = SensorManager()
        try:
            init_ok = await asyncio.wait_for(manager.initialize(), timeout=timeout)
            if not init_ok:
                return None
            reading = await asyncio.wait_for(manager.gps.read_gps(), timeout=timeout)
            if reading and reading.latitude is not None and reading.longitude is not None:
                lat = float(reading.latitude)
                lon = float(reading.longitude)
                if abs(lat) > 1e-6 or abs(lon) > 1e-6:
                    return lat, lon
            return None
        finally:
            with suppress(Exception):
                await asyncio.wait_for(manager.shutdown(), timeout=1.0)

    try:
        coords = _run_coro_sync(_read())
    except asyncio.TimeoutError:
        logger.debug("GPS timezone lookup timed out")
        return None
    except Exception as exc:
        logger.debug("GPS timezone lookup failed: %s", exc, exc_info=True)
        return None

    if coords:
        _coordinate_cache = (now, coords)
    return coords


def _detect_timezone_from_gps(
    gps_lookup: Optional[Callable[[], Optional[Tuple[float, float]]]]
) -> Optional[TimezoneInfo]:
    lookup = gps_lookup or _default_gps_lookup
    if lookup is None:
        return None

    try:
        coords = lookup()
    except Exception as exc:
        logger.debug("GPS timezone callable failed: %s", exc, exc_info=True)
        return None

    if not coords:
        return None

    tz_name = _timezone_from_coordinates(*coords)
    if tz_name:
        return TimezoneInfo(timezone=tz_name, source="gps")
    return None


def detect_system_timezone(
    base_path: str = "/",
    gps_lookup: Optional[Callable[[], Optional[Tuple[float, float]]]] = None,
    cache: bool = True,
) -> TimezoneInfo:
    global _timezone_cache

    use_cache = cache and base_path == "/"
    now = datetime.now()

    if use_cache and _timezone_cache and (now - _timezone_cache[0]) < _CACHE_TTL:
        return _timezone_cache[1]

    gps_info = _detect_timezone_from_gps(gps_lookup)
    if gps_info is not None:
        info = gps_info
    else:
        info = _detect_os_timezone(base_path)

    if use_cache:
        _timezone_cache = (now, info)
    return info
