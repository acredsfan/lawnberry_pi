from __future__ import annotations

"""Emergency stop handler (T030).

Immediate, thread-safe revocation of motor authorization. Hardware GPIO
integration will be added later; this provides core behavior for tests.
"""

from typing import Optional
from .motor_authorization import MotorAuthorization


class EstopHandler:
    def __init__(self, auth: MotorAuthorization) -> None:
        self._auth = auth
        self._last_reason: Optional[str] = None

    def trigger_estop(self, reason: str = "unknown") -> None:
        self._last_reason = reason
        # Immediate disable
        self._auth.revoke()

    @property
    def last_reason(self) -> Optional[str]:
        return self._last_reason
