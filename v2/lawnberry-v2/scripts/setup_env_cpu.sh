#!/usr/bin/env bash
set -euo pipefail
uv sync --all-extras --dev
echo "LBY_ACCEL=cpu" | sudo tee -a /etc/environment >/dev/null
