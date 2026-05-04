#!/usr/bin/env python3
"""Generate the LawnBerry OpenAPI schema without starting the HTTP server.

Usage:
    # Write to stdout
    uv run python scripts/generate_openapi.py

    # Write to file
    uv run python scripts/generate_openapi.py openapi.json

The script sets SIM_MODE=1 and LAWNBERRY_SKIP_HW_INIT=1 so hardware drivers
are not initialised. It imports the FastAPI app, calls app.openapi(), and
serialises to JSON with stable key ordering.

Exit codes:
    0  — success
    1  — import or schema generation failed
"""
from __future__ import annotations

import json
import os
import sys

# Disable hardware init before importing the app
os.environ.setdefault("SIM_MODE", "1")
os.environ.setdefault("LAWNBERRY_SKIP_HW_INIT", "1")

try:
    from backend.src.main import app  # noqa: E402
except Exception as exc:
    print(f"ERROR: Failed to import backend app: {exc}", file=sys.stderr)
    sys.exit(1)

try:
    schema = app.openapi()
except Exception as exc:
    print(f"ERROR: app.openapi() failed: {exc}", file=sys.stderr)
    sys.exit(1)

output = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False)

if len(sys.argv) >= 2:
    dest = sys.argv[1]
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(output)
        fh.write("\n")
    print(f"OpenAPI schema written to {dest}", file=sys.stderr)
else:
    print(output)
