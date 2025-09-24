#!/usr/bin/env bash
set -euo pipefail
uv sync --extra hailo
echo "LBY_ACCEL=hailo" | sudo tee -a /etc/environment >/dev/null
