from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class PlatformKind(str, Enum):
    RPI5 = "raspberry-pi-5"
    RPI4B = "raspberry-pi-4b"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PlatformProfile:
    kind: PlatformKind
    model: str
    imu_uart_pins: tuple[int, int] | None
    supported: bool

    @property
    def requires_explicit_pin_profile(self) -> bool:
        return self.kind is PlatformKind.UNKNOWN


def detect_platform_profile(model_path: Path = Path("/proc/device-tree/model")) -> PlatformProfile:
    """Detect the Raspberry Pi profile without scattering model checks in drivers.

    ``LAWNBERRY_PLATFORM_MODEL`` is intentionally an explicit test/CI override.
    Production hardware should rely on the device-tree model supplied by
    Raspberry Pi OS.
    """

    model = os.environ.get("LAWNBERRY_PLATFORM_MODEL", "").strip()
    if not model:
        try:
            model = model_path.read_text(encoding="utf-8").replace("\x00", "").strip()
        except OSError:
            model = ""

    normalized = model.lower()
    if "raspberry pi 5" in normalized:
        return PlatformProfile(
            kind=PlatformKind.RPI5,
            model=model or "Raspberry Pi 5",
            imu_uart_pins=(12, 13),
            supported=True,
        )
    if "raspberry pi 4" in normalized:
        return PlatformProfile(
            kind=PlatformKind.RPI4B,
            model=model or "Raspberry Pi 4 Model B",
            imu_uart_pins=(24, 21),
            supported=True,
        )
    return PlatformProfile(
        kind=PlatformKind.UNKNOWN,
        model=model or "unknown",
        imu_uart_pins=None,
        supported=False,
    )

