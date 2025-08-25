"""Board utilities for Raspberry Pi model detection and board-aware defaults.

This module centralizes small helpers to detect Pi model variants and choose
safe default pins that avoid known conflicts (e.g., UART4 on Pi 5 mapping to
BCM12/13 means BCM12 should not be used for ToF interrupts on Pi 5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def get_pi_model() -> str:
    """Return the Raspberry Pi model string from device-tree (empty if unknown)."""
    try:
        p = Path("/proc/device-tree/model")
        if p.exists():
            return p.read_text(errors="ignore").replace("\x00", "").strip()
    except Exception:
        pass
    return ""


def is_pi_5() -> bool:
    m = get_pi_model()
    return "Raspberry Pi 5" in m


def is_pi_4() -> bool:
    m = get_pi_model()
    return "Raspberry Pi 4" in m


def default_tof_right_interrupt_pin() -> int:
    """Choose a default interrupt pin for the right ToF sensor.

    On Pi 5, avoid BCM12 because it is used for UART4 TXD by default; choose BCM8.
    On older boards (e.g., Pi 4B), keep BCM12 as the historical default.
    """
    return 8 if is_pi_5() else 12


def maybe_override_tof_right_interrupt(configured: Optional[int]) -> int:
    """Return the effective ToF right interrupt pin.

    If running on a Pi 5 and the configured pin is None or 12 (legacy default),
    return 8 to avoid contention with UART4. Otherwise, return the configured pin
    if provided, or the board default.
    """
    if is_pi_5():
        if configured is None or configured == 12:
            return 8
    # not Pi 5, or configured is already non-conflicting
    return configured if configured is not None else (12 if is_pi_4() else 12)
