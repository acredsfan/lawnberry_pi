"""Fault injection utilities (FR-042).

Enables lightweight, environment-driven fault simulations for tests:
    - FAULT_INJECT env var as comma-separated values
        * gps_loss: mark GPS as degraded/fault
        * sensor_timeout: mark all sensors as degraded (timeout warnings)
        * imu_fault: mark IMU as fault
        * power_sag: mark power as warning

Intentionally minimal to avoid heavy runtime overhead. This module has no
side effects unless FAULT_INJECT is present.
"""

import os

_cached: tuple[str, set[str]] | None = None


def _parse() -> set[str]:
    global _cached
    raw = os.environ.get("FAULT_INJECT", "").strip()
    if _cached and _cached[0] == raw:
        return _cached[1]
    faults: set[str] = set()
    if raw:
        for part in raw.split(","):
            part = part.strip().lower()
            if part:
                faults.add(part)
    _cached = (raw, faults)
    return faults


def enabled(name: str) -> bool:
    return name.lower() in _parse()


def any_enabled(*names: str) -> bool:
    faults = _parse()
    return any(n.lower() in faults for n in names)
