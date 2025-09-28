from __future__ import annotations
from typing import Optional
from dataclasses import dataclass

from ..models.remote_access_config import RemoteAccessConfig, RemoteAccessProvider


@dataclass
class RemoteAccessStatus:
    provider: str
    enabled: bool
    active: bool
    url: Optional[str] = None
    message: Optional[str] = None


class RemoteAccessService:
    """Manage remote access tunnels (Cloudflare, ngrok, or custom).

    This is a scaffold. Implementation will be added in subsequent tasks.
    """

    def __init__(self) -> None:
        self._config = RemoteAccessConfig()
        self._status = RemoteAccessStatus(provider=self._config.provider, enabled=False, active=False)

    def configure(self, cfg: RemoteAccessConfig) -> None:
        self._config = cfg
        self._status.provider = cfg.provider
        self._status.enabled = cfg.enabled
        # No tunnel started in scaffold
        self._status.active = False
        self._status.url = None
        self._status.message = "configured (scaffold)"

    def get_status(self) -> RemoteAccessStatus:
        return self._status

    def enable(self) -> None:
        self._status.enabled = True
        # TODO: start tunnel based on provider
        self._status.active = False
        self._status.message = "enable requested (scaffold)"

    def disable(self) -> None:
        # TODO: stop tunnel if running
        self._status.enabled = False
        self._status.active = False
        self._status.url = None
        self._status.message = "disabled (scaffold)"


remote_access_service = RemoteAccessService()
