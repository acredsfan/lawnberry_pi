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

# Allow overriding the root to watch via WATCH_ROOT; default to script location
PROJECT_ROOT="${WATCH_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# If we're running under systemd with WATCH_ROOT pointing at the source tree (read-only via ProtectHome),
# use the canonical runtime /opt/lawnberry for executing deploy scripts to avoid write attempts in /home.
EXEC_ROOT="/opt/lawnberry"
if [[ ! -d "$EXEC_ROOT/scripts" ]]; then
  # Fallback to PROJECT_ROOT if runtime missing (developer session)
  EXEC_ROOT="$PROJECT_ROOT"
fi
INSTALL_DIR="/opt/lawnberry"
LOG_DIR="/var/log/lawnberry"
LOG_FILE="$LOG_DIR/auto_redeploy.log"

# Ensure log dir
mkdir -p "$LOG_DIR"
touch "$LOG_FILE" 2>/dev/null || true

# Timestamped logging helpers (ISO8601 with seconds)
_ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }
say()  { echo "[$(_ts)] [auto-redeploy] $*" | tee -a "$LOG_FILE"; }
warn() { echo "[$(_ts)] [auto-redeploy] WARN: $*" | tee -a "$LOG_FILE" >&2; }
err()  { echo "[$(_ts)] [auto-redeploy] ERROR: $*" | tee -a "$LOG_FILE" >&2; }

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
  say "UI: DETECTED change -> INIT build & minimal dist deploy"
  # Rebuild dist only if changed; script already enforces timeouts
  if ! timeout 620s bash "$PROJECT_ROOT/scripts/auto_rebuild_web_ui.sh" >>"$LOG_FILE" 2>&1; then
    err "UI: BUILD FAILED (auto_rebuild_web_ui.sh)"
    return 1
  fi

  # Fast deploy only the dist (minimal by default)
  say "UI: DEPLOY START (dist minimal) -> $INSTALL_DIR"
  if FAST_DEPLOY_DIST_MODE=minimal FAST_DEPLOY_MAX_SECONDS=$FAST_DEPLOY_MAX_SECONDS \
    timeout 120s bash "$EXEC_ROOT/scripts/lawnberry-deploy.sh" >>"$LOG_FILE" 2>&1; then
    say "UI: DEPLOY SUCCESS (dist minimal)"
    return 0
  else
    err "UI: DEPLOY FAILED (dist minimal)"
    return 1
  fi
}

do_ui_full_dist_sync() {
  say "UI: DETECTED pkg/lock change -> INIT build & FULL dist deploy"
  if ! timeout 620s bash "$PROJECT_ROOT/scripts/auto_rebuild_web_ui.sh" >>"$LOG_FILE" 2>&1; then
    err "UI: BUILD FAILED (full dist)"
    return 1
  fi
  say "UI: DEPLOY START (dist full) -> $INSTALL_DIR"
  if FAST_DEPLOY_DIST_MODE=full FAST_DEPLOY_MAX_SECONDS=$FAST_DEPLOY_MAX_SECONDS \
    timeout 160s bash "$EXEC_ROOT/scripts/lawnberry-deploy.sh" >>"$LOG_FILE" 2>&1; then
    say "UI: DEPLOY SUCCESS (dist full)"
    return 0
  else
    err "UI: DEPLOY FAILED (dist full)"
    return 1
  fi
}

do_fast_deploy_code() {
  say "CODE: DETECTED src/config change -> INIT fast deploy"
  local cmd=(timeout 160s bash "$EXEC_ROOT/scripts/lawnberry-deploy.sh")
  # Prevent a non-critical rm failure inside install script (read-only log dir) from aborting entire deploy
  set +e
  FAST_DEPLOY_DIST_MODE=skip FAST_DEPLOY_MAX_SECONDS=$FAST_DEPLOY_MAX_SECONDS "${cmd[@]}" >>"$LOG_FILE" 2>&1
  local ec=$?
  set -e
  if [[ $ec -eq 0 ]]; then
    say "CODE: DEPLOY SUCCESS"
    return 0
  else
    err "CODE: DEPLOY FAILED (exit=$ec)"
    # On first failure of a cycle, surface tail of install log if available
    if [[ -f "$PROJECT_ROOT/scripts/lawnberry_install.log" ]]; then
      err "Last 15 lines of install log (source tree):"
      tail -n 15 "$PROJECT_ROOT/scripts/lawnberry_install.log" 2>/dev/null | sed 's/^/[auto-redeploy] LOG: /' | tee -a "$LOG_FILE" >&2 || true
    fi
    if [[ -f "/opt/lawnberry/scripts/lawnberry_install.log" ]]; then
      err "Last 15 lines of runtime install log (/opt):"
      tail -n 15 /opt/lawnberry/scripts/lawnberry_install.log 2>/dev/null | sed 's/^/[auto-redeploy] RUNTIME: /' | tee -a "$LOG_FILE" >&2 || true
    fi
    # Emit environment diagnostics (non-fatal)
    say "Diag: FAST_DEPLOY_MAX_SECONDS=$FAST_DEPLOY_MAX_SECONDS DIST_MODE=${FAST_DEPLOY_DIST_MODE:-skip} HASH=${FAST_DEPLOY_HASH:-1}"
    return 1
  fi
}

do_services_replace() {
  say "SERVICE: DETECTED *.service change -> INIT reinstall & replace"
  # Force overwrite/replace semantics via --services-only (script handles stop/replace/start + daemon-reload)
  if timeout 120s bash "$EXEC_ROOT/scripts/install_lawnberry.sh" --services-only >>"$LOG_FILE" 2>&1; then
    say "SERVICE: REINSTALL SUCCESS"
    return 0
  else
    err "SERVICE: REINSTALL FAILED"
    return 1
  fi
}

do_requirements_update() {
  say "REQS: DETECTED requirements/pyproject change -> INIT venv update deploy"
  # Fast path: copy new requirement files to /opt and let deploy script ensure venv deps
  if FAST_DEPLOY_DIST_MODE=skip FAST_DEPLOY_MAX_SECONDS=$FAST_DEPLOY_MAX_SECONDS \
    timeout 200s bash "$EXEC_ROOT/scripts/lawnberry-deploy.sh" >>"$LOG_FILE" 2>&1; then
    say "REQS: DEPLOY SUCCESS (venv deps ensured)"
    return 0
  else
    err "REQS: DEPLOY FAILED (venv deps)"
    return 1
  fi
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
say "Heartbeat interval: ${HEARTBEAT_INTERVAL:-300}s"

# Heartbeat: emit a liveness log line periodically so operators know watcher hasn't stalled
HEARTBEAT_INTERVAL=${HEARTBEAT_INTERVAL:-300}
(
  while true; do
    sleep "$HEARTBEAT_INTERVAL" || exit 0
    # Only emit heartbeat if log file still writable (avoid noise if rotated read-only)
    if [[ -w "$LOG_FILE" ]]; then
      say "HEARTBEAT: watcher alive (pid=$$)"
    else
      echo "[$(_ts)] [auto-redeploy] WARN: HEARTBEAT skipped (log not writable)" >&2 || true
    fi
  done
) &
heartbeat_pid=$!

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
      say "DETECT: UI pkg/lock changed -> $f"
      pending_ui_full=true
      ;;
    *"/web-ui/src/"*|*"/web-ui/public/"*|*"/web-ui/vite.config."*)
      say "DETECT: UI source/assets changed -> $f"
      pending_ui=true
      ;;
    *".service")
      say "DETECT: service unit changed -> $f"
      pending_services=true
      ;;
    *"requirements.txt"|*"requirements-optional.txt"|*"requirements-coral.txt"|*"pyproject.toml")
      say "DETECT: requirements/pyproject changed -> $f"
      pending_requirements=true
      ;;
    *"/src/"*|*"/config/"*)
      say "DETECT: code/config changed -> $f"
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
    if do_services_replace; then
      say "SERVICE: ACTION COMPLETE -> SUCCESS"
    else
      err "SERVICE: ACTION COMPLETE -> FAILURE"
    fi
  fi
  if [[ "$pending_requirements" == true ]]; then
    if do_requirements_update; then
      say "REQS: ACTION COMPLETE -> SUCCESS"
    else
      err "REQS: ACTION COMPLETE -> FAILURE"
    fi
  fi
  if [[ "$pending_ui_full" == true ]]; then
    if do_ui_full_dist_sync; then
      say "UI: ACTION COMPLETE (full) -> SUCCESS"
    else
      err "UI: ACTION COMPLETE (full) -> FAILURE"
    fi
  elif [[ "$pending_ui" == true ]]; then
    if do_ui_build_and_sync; then
      say "UI: ACTION COMPLETE (minimal) -> SUCCESS"
    else
      err "UI: ACTION COMPLETE (minimal) -> FAILURE"
    fi
  fi
  if [[ "$pending_deploy" == true ]]; then
    if do_fast_deploy_code; then
      say "CODE: ACTION COMPLETE -> SUCCESS"
    else
      err "CODE: ACTION COMPLETE -> FAILURE"
    fi
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
trap 'shutdown=true; say "Shutting down watcher"; kill "$heartbeat_pid" 2>/dev/null || true; exit 0' SIGINT SIGTERM

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
