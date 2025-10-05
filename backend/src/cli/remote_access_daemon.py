"""
Remote Access Daemon (scaffold)

Runs a lightweight loop to reflect configured remote access settings.
Does not establish tunnels in this scaffold; integration to be added later.
"""

from __future__ import annotations

import asyncio
import logging
import os

from backend.src.services.remote_access_service import remote_access_service


logging.basicConfig(level=logging.INFO, format="[remote-access] %(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def main() -> int:
    logger.info("Remote access daemon starting (scaffold)")
    # In the future, load persisted settings and start provider-specific tunnels
    # For now, run a simple health loop
    try:
        while True:
            status = remote_access_service.get_status()
            logger.debug("status: enabled=%s active=%s provider=%s url=%s", status.enabled, status.active, status.provider, status.url)
            await asyncio.sleep(10)
    except asyncio.CancelledError:  # pragma: no cover
        pass
    except Exception as e:  # pragma: no cover
        logger.exception("Remote access daemon error: %s", e)
        return 1
    finally:
        logger.info("Remote access daemon stopping")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(asyncio.run(main()))
