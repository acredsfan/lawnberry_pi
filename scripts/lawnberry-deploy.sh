#!/bin/bash
# Convenience wrapper for fast deploy/update to canonical runtime
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"
exec ./scripts/install_lawnberry.sh --deploy-update "$@"
