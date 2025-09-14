#!/usr/bin/env bash
# LawnBerryPi – Auto Rebuild & Deploy Watcher
# Monitors the source tree for relevant changes and performs the smallest safe action:
# - Web UI changes: rebuild dist and fast-sync dist to /opt
# - Python/src/config changes: fast deploy code to /opt and restart services
# - Service unit changes: reinstall/replace units (not append) and restart
# - Requirements changes: ensure runtime venv deps installed at /opt
#
# Design constraints from project instructions:
# - ALWAYS use bounded timeouts (timeout ...)
# - Do not run services directly from the source tree; sync to /opt first
# - Use canonical installer/deploy scripts already present in repo
# - Keep runs non-interactive and safe for systemd

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="/opt/lawnberry"
LOG_DIR="/var/log/lawnberry"
LOG_FILE="$LOG_DIR/auto_redeploy.log"

# Ensure log dir
mkdir -p "$LOG_DIR"
touch "$LOG_FILE" 2>/dev/null || true

say()  { echo "[auto-redeploy] $*" | tee -a "$LOG_FILE"; }
warn() { echo "[auto-redeploy] WARN: $*" | tee -a "$LOG_FILE" >&2; }
err()  { echo "[auto-redeploy] ERROR: $*" | tee -a "$LOG_FILE" >&2; }

# Verify inotifywait availability early
if ! command -v inotifywait >/dev/null 2>&1; then
  err "inotifywait (inotify-tools) is required. Install via: sudo apt-get install -y inotify-tools"
  exit 1
fi

# Debounce window (seconds) to compact bursts of events
DEBOUNCE_SECONDS=${DEBOUNCE_SECONDS:-2}
# Global cap for each deploy update (seconds)
FAST_DEPLOY_MAX_SECONDS=${FAST_DEPLOY_MAX_SECONDS:-70}
# Service restart per-service timeout is in install_lawnberry.sh via FAST_DEPLOY_SERVICE_TIMEOUT
export FAST_DEPLOY_SERVICE_TIMEOUT=${FAST_DEPLOY_SERVICE_TIMEOUT:-10}

cd "$PROJECT_ROOT"

# Helper wrappers with timeouts and safe defaults
do_ui_build_and_sync() {
  say "UI: starting conditional build"
  # Rebuild dist only if changed; script already enforces timeouts
  if ! timeout 620s bash "$PROJECT_ROOT/scripts/auto_rebuild_web_ui.sh" >>"$LOG_FILE" 2>&1; then
    warn "UI: auto rebuild failed or timed out; skipping dist sync this round"
    return 1
  fi

  # Fast deploy only the dist (minimal by default)
  say "UI: syncing dist to $INSTALL_DIR (minimal)"
  FAST_DEPLOY_DIST_MODE=minimal FAST_DEPLOY_MAX_SECONDS=$FAST_DEPLOY_MAX_SECONDS \
    timeout 120s bash "$PROJECT_ROOT/scripts/lawnberry-deploy.sh" >>"$LOG_FILE" 2>&1 || warn "UI: deploy update encountered issues"
}

do_ui_full_dist_sync() {
  say "UI: package/lock changed – full dist sync"
  if ! timeout 620s bash "$PROJECT_ROOT/scripts/auto_rebuild_web_ui.sh" >>"$LOG_FILE" 2>&1; then
    warn "UI: auto rebuild failed or timed out; skipping full dist sync"
    return 1
  fi
  FAST_DEPLOY_DIST_MODE=full FAST_DEPLOY_MAX_SECONDS=$FAST_DEPLOY_MAX_SECONDS \
    timeout 160s bash "$PROJECT_ROOT/scripts/lawnberry-deploy.sh" >>"$LOG_FILE" 2>&1 || warn "UI: full dist deploy had issues"
}

do_fast_deploy_code() {
  say "Code/config changed – running fast deploy"
  FAST_DEPLOY_DIST_MODE=skip FAST_DEPLOY_MAX_SECONDS=$FAST_DEPLOY_MAX_SECONDS \
    timeout 160s bash "$PROJECT_ROOT/scripts/lawnberry-deploy.sh" >>"$LOG_FILE" 2>&1 || warn "Deploy update encountered issues"
}

do_services_replace() {
  say "Service unit changed – reinstalling and replacing"
  # Force overwrite/replace semantics via --services-only (script handles stop/replace/start + daemon-reload)
  timeout 120s bash "$PROJECT_ROOT/scripts/install_lawnberry.sh" --services-only >>"$LOG_FILE" 2>&1 || err "Service reinstall failed"
}

do_requirements_update() {
  say "Requirements changed – ensuring runtime venv dependencies at $INSTALL_DIR"
  # Fast path: copy new requirement files to /opt and let deploy script ensure venv deps
  FAST_DEPLOY_DIST_MODE=skip FAST_DEPLOY_MAX_SECONDS=$FAST_DEPLOY_MAX_SECONDS \
    timeout 200s bash "$PROJECT_ROOT/scripts/lawnberry-deploy.sh" >>"$LOG_FILE" 2>&1 || warn "Deploy update (requirements) had issues"
}

# Prepare watch set
declare -a PATHS_TO_WATCH
declare -a CANDIDATES=(
  "$PROJECT_ROOT/src"
  "$PROJECT_ROOT/config"
  "$PROJECT_ROOT/scripts"
  "$PROJECT_ROOT/requirements.txt"
  "$PROJECT_ROOT/requirements-optional.txt"
  "$PROJECT_ROOT/requirements-coral.txt"
  "$PROJECT_ROOT/pyproject.toml"
  "$PROJECT_ROOT/web-ui/src"
  "$PROJECT_ROOT/web-ui/public"
  "$PROJECT_ROOT/web-ui/package.json"
  "$PROJECT_ROOT/web-ui/package-lock.json"
  "$PROJECT_ROOT/web-ui/pnpm-lock.yaml"
  "$PROJECT_ROOT/web-ui/yarn.lock"
  "$PROJECT_ROOT/web-ui/vite.config.ts"
  "$PROJECT_ROOT/web-ui/vite.config.js"
)
for p in "${CANDIDATES[@]}"; do
  [[ -e "$p" ]] && PATHS_TO_WATCH+=("$p")
done
if [[ ${#PATHS_TO_WATCH[@]} -eq 0 ]]; then
  err "No watchable paths found; exiting"
  exit 1
fi

say "Starting watcher using inotifywait (debounce=${DEBOUNCE_SECONDS}s)"

# State to coalesce events
last_event_ts=0
pending_ui=false
pending_ui_full=false
pending_deploy=false
pending_services=false
pending_requirements=false

classify_and_mark() {
  local f="$1"
  # Normalize path
  case "$f" in
    *"/web-ui/package.json"|*"/web-ui/package-lock.json"|*"/web-ui/pnpm-lock.yaml"|*"/web-ui/yarn.lock")
      pending_ui_full=true
      ;;
    *"/web-ui/src/"*|*"/web-ui/public/"*|*"/web-ui/vite.config."*)
      pending_ui=true
      ;;
    *".service")
      # Any service unit in repo
      pending_services=true
      ;;
    *"requirements.txt"|*"requirements-optional.txt"|*"requirements-coral.txt"|*"pyproject.toml")
      pending_requirements=true
      ;;
    *"/src/"*|*"/config/"*)
      pending_deploy=true
      ;;
    *)
      # ignore
      ;;
  esac
}

run_pending_actions() {
  # Priority order: services replace (units), requirements, UI full, UI minimal, code deploy
  if [[ "$pending_services" == true ]]; then
    do_services_replace || true
  fi
  if [[ "$pending_requirements" == true ]]; then
    do_requirements_update || true
  fi
  if [[ "$pending_ui_full" == true ]]; then
    do_ui_full_dist_sync || true
  elif [[ "$pending_ui" == true ]]; then
    do_ui_build_and_sync || true
  fi
  if [[ "$pending_deploy" == true ]]; then
    do_fast_deploy_code || true
  fi
  # reset flags
  pending_ui=false
  pending_ui_full=false
  pending_deploy=false
  pending_services=false
  pending_requirements=false
}

# Trap SIGTERM for clean shutdown under systemd
shutdown=false
trap 'shutdown=true; say "Shutting down watcher"; exit 0' SIGINT SIGTERM

# Run initial quick sync if /opt exists but out of date may be desired (optional)
if [[ -d "$INSTALL_DIR" ]]; then
  say "Initial fast deploy check to ensure sync"
  FAST_DEPLOY_MAX_SECONDS=$FAST_DEPLOY_MAX_SECONDS FAST_DEPLOY_DIST_MODE=minimal \
    timeout 160s bash "$PROJECT_ROOT/scripts/lawnberry-deploy.sh" >>"$LOG_FILE" 2>&1 || true
fi

# Start the inotify monitor
inotifywait -m -r \
  -e modify,create,delete,move \
  --format '%w%f' \
  "${PATHS_TO_WATCH[@]}" 2>>"$LOG_FILE" | while read -r changed;
do
  # Update classification flags
  classify_and_mark "$changed"

  now=$(date +%s)
  # Debounce: only act if no new events arrive for DEBOUNCE_SECONDS
  if (( now - last_event_ts < DEBOUNCE_SECONDS )); then
    last_event_ts=$now
    continue
  fi
  last_event_ts=$now

  # Small debounce delay
  sleep "$DEBOUNCE_SECONDS"

  run_pending_actions

  $shutdown && break
done

exit 0
