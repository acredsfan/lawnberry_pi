"""
Data Service entrypoint
-----------------------
Long-running asyncio service that initializes the DataManager, subscribes to
MQTT topics if needed, and performs periodic maintenance. Designed to be
executed as a module via `python -m src.data_management.data_service`.
"""

import asyncio
import logging
import signal
from contextlib import asynccontextmanager

from .data_manager import DataManager


logger = logging.getLogger("lawnberry.data_service")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


@asynccontextmanager
async def _lifecycle(dm: DataManager):
    started = await dm.initialize()
    if not started:
        raise RuntimeError("DataManager failed to initialize")
    try:
        yield
    finally:
        await dm.shutdown()


async def _run(dm: DataManager, stop_event: asyncio.Event) -> None:
    """Main loop for periodic tasks/health checks."""
    logger.info("Data service started")
    # Example: periodic compaction/flush/metrics; keep loop light.
    while not stop_event.is_set():
        try:
            await dm.tick()
        except AttributeError:
            # tick() optional; sleep instead
            await asyncio.sleep(5)
        except Exception as e:  # noqa: BLE001
            logger.exception("Data service loop error: %s", e)
            await asyncio.sleep(2)
        else:
            # If tick present and fast, avoid busy loop
            await asyncio.sleep(1)
    logger.info("Data service stopping")


async def _main_async() -> int:
    _setup_logging()
    stop_event = asyncio.Event()

    # Handle SIGTERM/SIGINT for graceful shutdown
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Signal handlers not available on some platforms
            pass

    dm = DataManager()
    async with _lifecycle(dm):
        await _run(dm, stop_event)
    return 0


def main() -> int:
    return asyncio.run(_main_async())


if __name__ == "__main__":
    raise SystemExit(main())
