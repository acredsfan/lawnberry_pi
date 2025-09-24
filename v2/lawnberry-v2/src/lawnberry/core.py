from __future__ import annotations

import asyncio
import os
import signal
import sys
from typing import NoReturn


def log(msg: str) -> None:
    print(f"[lawnberry] {msg}", flush=True)

async def main() -> None:
    sim = os.getenv("SIM_MODE", "0") == "1"
    accel = os.getenv("LBY_ACCEL", "cpu")
    log(f"Booting LawnBerry core (SIM_MODE={sim}, ACCEL={accel})")
    # TODO: wire up services incrementally (sensors, websockets, camera, etc.)
    # For now: simple heartbeat loop
    try:
        while True:
            await asyncio.sleep(1.0)
            log("heartbeat")
    except asyncio.CancelledError:
        log("shutdown requested")

def _handle_sigterm(loop: asyncio.AbstractEventLoop) -> None:
    for task in asyncio.all_tasks(loop):
        task.cancel()

def run() -> NoReturn:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_sigterm, loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.run_until_complete(asyncio.sleep(0))
        loop.close()
        sys.exit(0)

if __name__ == "__main__":
    run()
