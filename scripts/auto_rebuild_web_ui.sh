#!/usr/bin/env bash
# Automated conditional Web UI rebuild helper
# Triggers a Vite production build ONLY if source files are newer than dist output.
# Safe to run as a systemd ExecStartPre (fast no-op when unchanged).
#
# Timeouts are enforced so a stuck npm process will not block service startup forever.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_UI_DIR="$PROJECT_ROOT/web-ui"
DIST_DIR="$WEB_UI_DIR/dist"
INDEX_FILE="$DIST_DIR/index.html"
STAMP_FILE="$DIST_DIR/.build_timestamp"
LOG_PREFIX="[auto-rebuild-ui]"

MAX_BUILD_SECONDS=${MAX_BUILD_SECONDS:-600}
NPM_BIN="$(command -v npm || true)"
SKIP_AUTO_REBUILD=${SKIP_AUTO_REBUILD:-0}

log() { echo "${LOG_PREFIX} $*"; }
warn() { echo "${LOG_PREFIX} WARN: $*" >&2; }
err() { echo "${LOG_PREFIX} ERROR: $*" >&2; }

# Allow callers to skip rebuild explicitly (for faster restarts)
if [[ "$SKIP_AUTO_REBUILD" == "1" ]]; then
  log "SKIP_AUTO_REBUILD=1 set – skipping UI rebuild check"
  exit 0
fi

# Quick pre-flight checks
if [[ -z "$NPM_BIN" ]]; then
  warn "npm not found – skipping UI rebuild check"
  exit 0
fi

if [[ ! -d "$WEB_UI_DIR" ]]; then
  warn "web-ui directory missing – skipping"
  exit 0
fi

# If dist missing entirely, force rebuild
NEED_BUILD=false
if [[ ! -f "$INDEX_FILE" ]]; then
  log "dist/index.html missing – build required"
  NEED_BUILD=true
fi

# Determine newest source modification time (src, public, package.json, vite.config.*)
if [[ "$NEED_BUILD" = false ]]; then
  NEWEST_SRC_EPOCH=$(find "$WEB_UI_DIR" \( -path "*/node_modules" -prune -false \) -o \
    -path "*/dist" -prune -false -o \
    -type f \( -path "*/src/*" -o -path "*/public/*" -o -name "package.json" -o -name "vite.config.*" \) -printf '%T@\n' 2>/dev/null | sort -nr | head -1 | cut -d'.' -f1 || echo 0)
  BUILD_EPOCH=0
  if [[ -f "$STAMP_FILE" ]]; then
    BUILD_EPOCH=$(cat "$STAMP_FILE" 2>/dev/null || echo 0)
  else
    # Fallback to index.html mtime
    BUILD_EPOCH=$(stat -c '%Y' "$INDEX_FILE" 2>/dev/null || echo 0)
  fi
  if (( NEWEST_SRC_EPOCH > BUILD_EPOCH )); then
    log "Source changes detected (src newer than last build)"
    NEED_BUILD=true
  else
    log "No source changes detected – skipping rebuild"
  fi
fi

if [[ "$NEED_BUILD" = false ]]; then
  exit 0
fi

# Ensure dependencies present (install only if node_modules absent)
if [[ ! -d "$WEB_UI_DIR/node_modules" ]]; then
  log "node_modules missing – installing dependencies"
  ( cd "$WEB_UI_DIR" && timeout ${MAX_BUILD_SECONDS}s npm install --no-audit --no-fund ) || {
    err "npm install failed or timed out"; exit 1; }
fi

log "Running production build (timeout: ${MAX_BUILD_SECONDS}s)"
if ( cd "$WEB_UI_DIR" && timeout ${MAX_BUILD_SECONDS}s npm run build --silent ); then
  date +%s > "$STAMP_FILE" || true
  log "Build complete"
else
  err "Build failed or timed out"
  exit 1
fi

exit 0
