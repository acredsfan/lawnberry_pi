from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models.hardware_config import BladeControllerType, HardwareConfig, IMUType
from .platform_profile import PlatformKind, PlatformProfile


@dataclass(frozen=True)
class PinConflict:
    gpio: int
    roles: tuple[str, ...]
    reason_code: str = "HARDWARE_PIN_CONFLICT"


@dataclass(frozen=True)
class PinAllocationReport:
    platform: str
    model: str
    allocations: dict[int, tuple[str, ...]]
    conflicts: tuple[PinConflict, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.conflicts

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "model": self.model,
            "ok": self.ok,
            "allocations": {str(pin): list(roles) for pin, roles in self.allocations.items()},
            "conflicts": [
                {"gpio": conflict.gpio, "roles": list(conflict.roles), "reason_code": conflict.reason_code}
                for conflict in self.conflicts
            ],
        }


def _add(allocation: dict[int, list[str]], gpio: int | None, role: str) -> None:
    if gpio is None:
        return
    allocation.setdefault(int(gpio), []).append(role)


def build_pin_allocation_report(
    hardware: HardwareConfig,
    platform: PlatformProfile,
) -> PinAllocationReport:
    allocation: dict[int, list[str]] = {}

    if hardware.imu_type == IMUType.BNO085_UART and platform.imu_uart_pins is not None:
        tx_gpio, rx_gpio = platform.imu_uart_pins
        _add(allocation, tx_gpio, f"{platform.kind.value}:BNO085 UART4 TX")
        _add(allocation, rx_gpio, f"{platform.kind.value}:BNO085 UART4 RX")

    tof = hardware.tof_config
    if tof is not None:
        _add(allocation, tof.left_shutdown_gpio, "ToF left XSHUT")
        _add(allocation, tof.right_shutdown_gpio, "ToF right XSHUT")
        left_irq = getattr(tof, "left_interrupt_gpio", None)
        right_irq = getattr(tof, "right_interrupt_gpio", None)
        _add(allocation, left_irq, "ToF left IRQ")
        _add(allocation, right_irq, "ToF right IRQ")

    controller = hardware.blade.controller or hardware.blade_controller
    if controller == BladeControllerType.IBT_4:
        _add(allocation, hardware.blade.pins.in1, "IBT-4 blade IN1")
        _add(allocation, hardware.blade.pins.in2, "IBT-4 blade IN2")

    conflicts = tuple(
        PinConflict(gpio=pin, roles=tuple(roles))
        for pin, roles in sorted(allocation.items())
        if len(set(roles)) > 1
    )
    return PinAllocationReport(
        platform=platform.kind.value,
        model=platform.model,
        allocations={pin: tuple(roles) for pin, roles in sorted(allocation.items())},
        conflicts=conflicts,
    )


def default_blade_pins_for_platform(kind: PlatformKind) -> tuple[int, int] | None:
    if kind is PlatformKind.RPI5:
        return (24, 25)
    if kind is PlatformKind.RPI4B:
        return (26, 27)
    return None

