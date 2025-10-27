#!/usr/bin/env bash
# LawnBerry Pi - Restore Script
# Restores configuration and database from a backup archive produced by backup_system.sh

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

ARCHIVE_PATH="${1:-}"
DRY_RUN=${DRY_RUN:-0}
SKIP_SYSTEMCTL=${SKIP_SYSTEMCTL:-0}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
WORK_DIR="$REPO_ROOT/backups/.restore-$TIMESTAMP"
PRE_BACKUP_DIR="$REPO_ROOT/backups/restore-pre-$TIMESTAMP"

DB_DST="./data/lawnberry.db"

log() { echo "[$(date -Is)] $*"; }
fail() { echo "[$(date -Is)] ERROR: $*" >&2; exit 1; }
run() { if [ "$DRY_RUN" = "1" ]; then echo "+ $*"; else "$@"; fi }

usage() {
  cat <<EOF
Usage: $(basename "$0") <backup-archive.tar.gz>

Environment variables:
  DRY_RUN=1         Print actions without executing
  SKIP_SYSTEMCTL=1  Do not stop/start systemd services
EOF
}

verify_inputs() {
  if [ -z "$ARCHIVE_PATH" ]; then usage; fail "Archive path is required"; fi
  [ -f "$ARCHIVE_PATH" ] || fail "Archive not found: $ARCHIVE_PATH"
}

verify_checksum() {
  local sha_file="$ARCHIVE_PATH.sha256"
  if [ -f "$sha_file" ]; then
    log "Verifying checksum"
    local expected actual
    expected=$(awk '{print $1}' "$sha_file")
    actual=$(sha256sum "$ARCHIVE_PATH" | awk '{print $1}')
    if [ "$expected" != "$actual" ]; then
      fail "Checksum mismatch: expected $expected, got $actual"
    fi
  else
    log "No .sha256 file found; skipping checksum verification"
  fi
}

extract_archive() {
  mkdir -p "$WORK_DIR"
  log "Extracting archive to $WORK_DIR"
  tar -xzf "$ARCHIVE_PATH" -C "$WORK_DIR"
  [ -d "$WORK_DIR/snapshot" ] || fail "Invalid archive (snapshot/ missing)"
}

stop_services() {
  if [ "$SKIP_SYSTEMCTL" = "1" ]; then
    log "Skipping systemd service stop"
    return
  fi
  if command -v systemctl >/dev/null 2>&1; then
    log "Stopping services"
    run sudo systemctl stop lawnberry-backend.service || true
    run sudo systemctl stop lawnberry-sensors.service || true
    run sudo systemctl stop lawnberry-camera.service || true
    run sudo systemctl stop lawnberry-remote-access.service || true
    run sudo systemctl stop lawnberry-database.service || true
    run sudo systemctl stop lawnberry-health.service || true
    run sudo systemctl stop lawnberry-frontend.service || true
  fi
}

start_services() {
  if [ "$SKIP_SYSTEMCTL" = "1" ]; then
    log "Skipping systemd service start"
    return
  fi
  if command -v systemctl >/dev/null 2>&1; then
    log "Starting services"
    run sudo systemctl start lawnberry-database.service || true
    run sudo systemctl start lawnberry-backend.service || true
    run sudo systemctl start lawnberry-sensors.service || true
    run sudo systemctl start lawnberry-camera.service || true
    run sudo systemctl start lawnberry-remote-access.service || true
    run sudo systemctl start lawnberry-health.service || true
    run sudo systemctl start lawnberry-frontend.service || true
  fi
}

pre_backup_current() {
  log "Backing up current state to $PRE_BACKUP_DIR"
  mkdir -p "$PRE_BACKUP_DIR/config" "$PRE_BACKUP_DIR/data" "$PRE_BACKUP_DIR/db"
  [ -d "$REPO_ROOT/config" ] && run rsync -a "$REPO_ROOT/config/" "$PRE_BACKUP_DIR/config/"
  [ -d "$REPO_ROOT/data" ] && run rsync -a "$REPO_ROOT/data/" "$PRE_BACKUP_DIR/data/"
  [ -f "$DB_DST" ] && run install -m 0600 "$DB_DST" "$PRE_BACKUP_DIR/db/lawnberry.db"
}

restore_files() {
  local snap="$WORK_DIR/snapshot"
  log "Restoring configuration files"
  if [ -d "$snap/config" ]; then
    run rsync -a "$snap/config/" "$REPO_ROOT/config/"
  fi
  log "Restoring data JSON (non-destructive)"
  if [ -d "$snap/data" ]; then
    run rsync -a "$snap/data/" "$REPO_ROOT/data/"
  fi
  log "Restoring environment file (if present)"
  if [ -f "$snap/.env" ]; then
    run install -m 0600 "$snap/.env" "$REPO_ROOT/.env"
  fi
  log "Restoring SQLite database"
  if [ -f "$snap/db/lawnberry.db" ]; then
    mkdir -p "$(dirname "$DB_DST")"
    run install -m 0600 "$snap/db/lawnberry.db" "$DB_DST"
  else
    log "No database in snapshot; skipping"
  fi
}

cleanup() {
  rm -rf "$WORK_DIR" || true
}

main() {
  verify_inputs
  verify_checksum
  extract_archive
  stop_services
  pre_backup_current
  restore_files
  start_services
  cleanup
  log "Restore complete from $(basename "$ARCHIVE_PATH")"
}

main "$@"
