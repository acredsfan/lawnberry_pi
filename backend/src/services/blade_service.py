"""
Blade service for IBT-4 control.

Provides a simple async wrapper around IBT4BladeDriver with a process-wide
singleton accessor. Safe in SIM mode; hardware access is lazy and guarded.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from ..drivers.blade.ibt4_gpio import IBT4BladeDriver

logger = logging.getLogger(__name__)


class BladeService:
    def __init__(self) -> None:
        self._driver = IBT4BladeDriver({})
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> bool:
        async with self._lock:
            if self._initialized:
                return True
            try:
                await self._driver.initialize()
                await self._driver.start()
                self._initialized = True
                return True
            except Exception as e:
                logger.warning("BladeService init failed: %s", e)
                return False

    async def set_active(self, active: bool) -> bool:
        if not self._initialized:
            await self.initialize()
        try:
            return await self._driver.set_active(bool(active))
        except Exception as e:
            logger.error("BladeService set_active failed: %s", e)
            return False

    async def emergency_stop(self) -> None:
        try:
            await self._driver.set_estop(True)
        except Exception:
            pass
        try:
            await self._driver.set_active(False)
        except Exception:
            pass


_blade_service: Optional[BladeService] = None


def get_blade_service() -> BladeService:
    global _blade_service
    if _blade_service is None:
        _blade_service = BladeService()
    return _blade_service
