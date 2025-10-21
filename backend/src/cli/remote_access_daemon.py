"""Remote access management daemon.

Maintains Cloudflare/ngrok tunnels by watching the shared configuration file
and updating the remote access service accordingly. The daemon persists tunnel
status so the FastAPI backend can present accurate information via the
settings and status endpoints.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from contextlib import suppress

from backend.src.services.remote_access_service import (
    RemoteAccessError,
    RemoteAccessService,
)


logging.basicConfig(level=logging.INFO, format="[remote-access] %(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _config_digest(cfg) -> str:
    try:
        payload = cfg.model_dump(mode="json")
    except AttributeError:
        # Should not occur, but defensive fallback
        payload = dict(cfg)
    return json.dumps(payload, sort_keys=True)


async def _polling_loop(service: RemoteAccessService, stop_event: asyncio.Event, poll_seconds: int) -> None:
    while not stop_event.is_set():
        try:
            cfg = RemoteAccessService.load_config_from_disk(service.config_path)
            digest = _config_digest(cfg)
            if digest != service.config_digest:
                logger.info("Remote access configuration changed; applying")
                await service.apply_configuration(cfg, persist=False)
            else:
                await service.check_health()
        except RemoteAccessError as exc:
            service.record_error(f"Remote access configuration error: {exc}", exc)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Unexpected remote access daemon error: %s", exc)
            service.record_error("Remote access daemon runtime error", exc)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except asyncio.TimeoutError:
            continue


async def main() -> int:
    poll_seconds = int(os.getenv("REMOTE_ACCESS_POLL_SECONDS", "10"))
    logger.info("Remote access daemon starting (poll interval: %ss)", poll_seconds)

    service = RemoteAccessService()
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()

    def _request_shutdown() -> None:
        if not stop_event.is_set():
            logger.info("Shutdown requested")
            stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, _request_shutdown)

    # Apply existing configuration once at startup
    try:
        await service.apply_configuration(service.get_config(), persist=False)
    except RemoteAccessError as exc:
        service.record_error(f"Initial remote access configuration invalid: {exc}", exc)

    await _polling_loop(service, stop_event, poll_seconds)

    logger.info("Remote access daemon stopping")
    with suppress(Exception):
        await service.disable()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(asyncio.run(main()))
