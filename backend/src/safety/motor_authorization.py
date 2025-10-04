from __future__ import annotations

"""Motor authorization service (T034).

Default OFF until explicitly authorized. E-stop and interlocks will revoke.
"""

import threading


class MotorAuthorization:
    def __init__(self) -> None:
        self._enabled = False
        self._lock = threading.Lock()

    def authorize(self) -> None:
        with self._lock:
            self._enabled = True

    def revoke(self) -> None:
        with self._lock:
            self._enabled = False

    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled
