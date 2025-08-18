#!/usr/bin/env bash
# Wrapper to run the hardware sensor service for a short validation window
# Usage: ./scripts/run_sensor_service.sh [seconds]
# Defaults to 12 seconds when no argument provided.

set -eo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC_DIR="$ROOT_DIR/src"
VENV_DIR="$ROOT_DIR/venv_test_mqtt"
TIMEOUT_SECONDS="${1:-12}"

if [ ! -d "$VENV_DIR" ]; then
  echo "Virtualenv $VENV_DIR not found. Create it with: python3 -m venv $VENV_DIR && $VENV_DIR/bin/python -m pip install --upgrade pip paho-mqtt"
  exit 1
fi

export PYTHONPATH="$SRC_DIR"
exec "$VENV_DIR/bin/python3" - <<PYCODE
import asyncio, sys
from hardware.sensor_service import main

async def run_once():
    task = asyncio.create_task(main())
    try:
        await asyncio.sleep($TIMEOUT_SECONDS)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

asyncio.run(run_once())
PYCODE
