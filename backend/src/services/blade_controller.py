from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..drivers.blade.ibt4_gpio import IBT4BladeDriver
from ..models.hardware_config import BladeConfig, BladeControllerType


@dataclass(frozen=True)
class BladeResult:
    ok: bool
    reason_code: str | None = None
    commanded_active: bool | None = None
    acknowledged_active: bool | None = None


@dataclass(frozen=True)
class BladeHealth:
    backend: str
    online: bool
    initialized: bool
    commanded_active: bool
    acknowledged_active: bool | None
    allow_autonomous: bool
    pins: dict[str, int] | None = None
    reason_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "online": self.online,
            "initialized": self.initialized,
            "commanded_active": self.commanded_active,
            "acknowledged_active": self.acknowledged_active,
            "allow_autonomous": self.allow_autonomous,
            "pins": self.pins,
            "reason_code": self.reason_code,
        }


class BladeController(Protocol):
    async def initialize(self) -> bool: ...
    async def set_active(self, active: bool, *, reason: str) -> BladeResult: ...
    async def emergency_stop(self, *, reason: str) -> BladeResult: ...
    async def health(self) -> BladeHealth: ...


class IBT4BladeController:
    def __init__(self, config: BladeConfig):
        self._config = config
        pins = {"in1": config.pins.in1, "in2": config.pins.in2}
        self._driver = IBT4BladeDriver({"pins": pins})
        self._initialized = False
        self._commanded_active = False
        self._acknowledged_active: bool | None = False
        self._reason_code: str | None = None

    async def initialize(self) -> bool:
        if self._initialized:
            return True
        try:
            await self._driver.initialize()
            await self._driver.start()
            await self._driver.set_active(False)
        except Exception:
            self._initialized = False
            self._reason_code = "BLADE_CONTROLLER_OFFLINE"
            self._acknowledged_active = None
            return False
        self._initialized = True
        self._reason_code = None
        self._commanded_active = False
        self._acknowledged_active = False
        return True

    async def set_active(self, active: bool, *, reason: str) -> BladeResult:
        if not self._initialized and not await self.initialize():
            return BladeResult(
                ok=False,
                reason_code="BLADE_CONTROLLER_OFFLINE",
                commanded_active=bool(active),
                acknowledged_active=self._acknowledged_active,
            )
        self._commanded_active = bool(active)
        ok = await self._driver.set_active(bool(active))
        self._acknowledged_active = bool(active) if ok else False if active else None
        self._reason_code = None if ok else "BLADE_STOP_UNCONFIRMED" if not active else "BLADE_ACK_TIMEOUT"
        return BladeResult(
            ok=ok,
            reason_code=None if ok else self._reason_code,
            commanded_active=self._commanded_active,
            acknowledged_active=self._acknowledged_active,
        )

    async def emergency_stop(self, *, reason: str) -> BladeResult:
        self._commanded_active = False
        try:
            await self._driver.set_estop(True)
            ok = await self._driver.set_active(False)
        except Exception:
            ok = False
        self._acknowledged_active = False if ok else None
        self._reason_code = None if ok else "BLADE_STOP_UNCONFIRMED"
        return BladeResult(
            ok=ok,
            reason_code=None if ok else self._reason_code,
            commanded_active=False,
            acknowledged_active=self._acknowledged_active,
        )

    async def health(self) -> BladeHealth:
        hc = await self._driver.health_check()
        return BladeHealth(
            backend=BladeControllerType.IBT_4.value,
            online=self._initialized and self._reason_code is None,
            initialized=self._initialized,
            commanded_active=self._commanded_active,
            acknowledged_active=self._acknowledged_active,
            allow_autonomous=bool(self._config.allow_autonomous),
            pins={"in1": self._config.pins.in1, "in2": self._config.pins.in2},
            reason_code=self._reason_code or hc.get("offline_reason"),
        )


class RoboHATBladeController:
    def __init__(self, config: BladeConfig, robohat: Any):
        self._config = config
        self._robohat = robohat
        self._commanded_active = False
        self._acknowledged_active: bool | None = False
        self._reason_code: str | None = None

    async def initialize(self) -> bool:
        if self._robohat is None:
            self._reason_code = "BLADE_CONTROLLER_OFFLINE"
            return False
        return True

    async def set_active(self, active: bool, *, reason: str) -> BladeResult:
        if self._robohat is None:
            return BladeResult(False, "BLADE_CONTROLLER_OFFLINE", bool(active), None)
        self._commanded_active = bool(active)
        send = getattr(self._robohat, "send_blade_command", None)
        ok = bool(await send(bool(active), ack_timeout=self._config.command_ack_timeout_seconds))
        self._acknowledged_active = bool(active) if ok else False if active else None
        self._reason_code = None if ok else "BLADE_STOP_UNCONFIRMED" if not active else "BLADE_ACK_TIMEOUT"
        return BladeResult(
            ok=ok,
            reason_code=None if ok else self._reason_code,
            commanded_active=self._commanded_active,
            acknowledged_active=self._acknowledged_active,
        )

    async def emergency_stop(self, *, reason: str) -> BladeResult:
        result = await self.set_active(False, reason=reason)
        if not result.ok:
            self._reason_code = "BLADE_STOP_UNCONFIRMED"
        return result

    async def health(self) -> BladeHealth:
        status = getattr(self._robohat, "status", None)
        connected = bool(getattr(status, "serial_connected", False))
        return BladeHealth(
            backend=BladeControllerType.ROBOHAT_RP2040.value,
            online=connected and self._reason_code is None,
            initialized=self._robohat is not None,
            commanded_active=self._commanded_active,
            acknowledged_active=self._acknowledged_active,
            allow_autonomous=bool(self._config.allow_autonomous),
            reason_code=None if connected else "BLADE_CONTROLLER_OFFLINE",
        )


def build_blade_controller(config: BladeConfig, robohat: Any = None) -> BladeController:
    controller = config.controller
    if controller == BladeControllerType.ROBOHAT_RP2040:
        return RoboHATBladeController(config, robohat)
    return IBT4BladeController(config)
