#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y curl python3-venv python3-dev libatlas-base-dev \
  gstreamer1.0-tools gstreamer1.0-libcamera gstreamer1.0-plugins-{base,good,bad} \
  libcap2-bin pkg-config build-essential

# Install uv without touching system pip (PEP 668-safe)
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# Sync project env
uv sync --dev
