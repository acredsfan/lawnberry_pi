#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
FRONTEND_DIR="${REPO_ROOT}/frontend"

info() { echo -e "\033[1;34m[INFO]\033[0m $*"; }
error() { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; }

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    error "Required command '$1' not found. Please install it before running this script."
    exit 1
  fi
}

require_command npm
require_command systemctl

info "Installing frontend dependencies (npm install)"
(
  cd "$FRONTEND_DIR"
  npm install --no-audit --no-fund
)

info "Building frontend (npm run build)"
(
  cd "$FRONTEND_DIR"
  npm run build
)

info "Restarting lawnberry-backend.service"
if ! sudo systemctl restart lawnberry-backend.service; then
  error "Failed to restart lawnberry-backend.service"
  exit 1
fi

if systemctl status lawnberry-frontend.service >/dev/null 2>&1; then
  info "Restarting lawnberry-frontend.service"
  if ! sudo systemctl restart lawnberry-frontend.service; then
    error "Failed to restart lawnberry-frontend.service"
    exit 1
  fi
else
  info "lawnberry-frontend.service not found; skipping frontend restart"
fi

info "All tasks completed successfully."
