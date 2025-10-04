from __future__ import annotations

"""Safety interlock validator (T033).

Tracks active interlocks and provides assertion helper to block unsafe ops.
"""

from typing import Dict


class InterlockActiveError(RuntimeError):
    pass


class InterlockValidator:
    def __init__(self) -> None:
        self._active: Dict[str, bool] = {}

    def set_interlock(self, name: str, active: bool) -> None:
        self._active[name] = bool(active)

    def is_any_active(self) -> bool:
        return any(self._active.values())

    def assert_safe_to_move(self) -> None:
        if self.is_any_active():
            raise InterlockActiveError("Safety interlock is active; operation blocked")
