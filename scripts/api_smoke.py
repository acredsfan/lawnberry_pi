#!/usr/bin/env python3
"""
API Smoke Test (non-interactive)

Runs a minimal health check and status fetch against the FastAPI app in-process
using TestClient, with guardrails to avoid startup hangs (Redis/MQTT timeouts
are already enforced in app startup). Intended to be executed with a timeout.

Usage:
    timeout 20s venv/bin/python scripts/api_smoke.py
"""

import os
import sys
import json

# Ensure imports resolve when run from repo root
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src_path = os.path.join(repo_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from fastapi.testclient import TestClient


def main() -> int:
    # Provide environment hints (optional) to avoid slow DNS lookups if misconfigured
    os.environ.setdefault('REDIS_HOST', 'localhost')
    os.environ.setdefault('MQTT_BROKER_HOST', 'localhost')

    # Lazy import after sys.path adjustment
    from web_api.main import create_app

    app = create_app()
    with TestClient(app) as client:
        try:
            r = client.get('/health', timeout=5)
            print('[health]', r.status_code, r.json())
        except Exception as e:
            print('[health] ERROR', str(e))
            return 2

        try:
            r2 = client.get('/api/v1/status', timeout=8)
            print('[status]', r2.status_code)
            # Print a compact preview
            txt = r2.text
            if len(txt) > 400:
                txt = txt[:400] + '…'
            print(txt)
        except Exception as e:
            print('[status] ERROR', str(e))
            return 3

    return 0


if __name__ == '__main__':
    sys.exit(main())
