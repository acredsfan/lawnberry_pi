#!/usr/bin/env bash
# LawnBerry Pi - Automated Backup Script
# Creates a timestamped backup archive containing configuration, database, and system state.
#
# Features:
# - Consistent SQLite backup using sqlite3 .backup (if available)
# - Includes config/, data/ JSON, and lawnberry.db
# - Generates MANIFEST.json with file sizes and SHA256 checksums
# - Produces a compressed .tar.gz and companion .sha256 file
# - Applies simple retention policy (BACKUP_RETENTION_DAYS, default 14)
# - Safe permissions on output artifacts (owner-only)

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

BACKUP_ROOT_DIR=${BACKUP_ROOT_DIR:-"$REPO_ROOT/backups"}
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-14}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
WORK_DIR="$BACKUP_ROOT_DIR/.work-$TIMESTAMP"
SNAPSHOT_DIR="$WORK_DIR/snapshot"
ARCHIVE_NAME="lawnberry-backup-$TIMESTAMP.tar.gz"
ARCHIVE_PATH="$BACKUP_ROOT_DIR/$ARCHIVE_NAME"
SHA_PATH="$ARCHIVE_PATH.sha256"

DB_PATH="./data/lawnberry.db"

log() { echo "[$(date -Is)] $*"; }
fail() { echo "[$(date -Is)] ERROR: $*" >&2; exit 1; }

ensure_dirs() {
  mkdir -p "$BACKUP_ROOT_DIR" || fail "Cannot create backup root dir: $BACKUP_ROOT_DIR"
  mkdir -p "$SNAPSHOT_DIR" || fail "Cannot create snapshot dir: $SNAPSHOT_DIR"
}

permissions_safe() {
  # Ensure owner-only on backup artifacts and temp files
  umask 0077
}

collect_meta() {
  log "Collecting metadata"
  mkdir -p "$SNAPSHOT_DIR/meta"
  (
    cd "$REPO_ROOT"
    {
      echo "repo_path=$REPO_ROOT"
      command -v git >/dev/null 2>&1 && git rev-parse HEAD 2>/dev/null | sed 's/^/git_commit=/'
      uname -a | sed 's/^/uname=/'
      echo "timestamp=$TIMESTAMP"
    } >"$SNAPSHOT_DIR/meta/system.txt"
  )
  # Dump systemd service states (best-effort)
  if command -v systemctl >/dev/null 2>&1; then
    for svc in lawnberry-backend.service lawnberry-sensors.service lawnberry-camera.service lawnberry-remote-access.service lawnberry-database.service lawnberry-health.service lawnberry-frontend.service; do
      systemctl status "$svc" --no-pager --full || true
    done >"$SNAPSHOT_DIR/meta/systemd-status.txt" 2>&1 || true
  fi
}

backup_sqlite() {
  local src_db="$1"
  local dst_db="$2"
  if [ -f "$src_db" ]; then
    if command -v sqlite3 >/dev/null 2>&1; then
      log "Creating consistent SQLite backup"
      sqlite3 "$src_db" ".backup '$dst_db'"
    else
      log "sqlite3 not found; falling back to file copy"
      cp -a "$src_db" "$dst_db"
      sync
    fi
  else
    log "Database not found at $src_db (skipping)"
  fi
}

copy_tree() {
  local src="$1" dst="$2";
  if [ -d "$src" ]; then
    mkdir -p "$dst"
    rsync -a --delete --exclude 'logs/' "$src/" "$dst/"
  fi
}

create_snapshot() {
  log "Creating snapshot layout"
  mkdir -p "$SNAPSHOT_DIR/config" "$SNAPSHOT_DIR/data" "$SNAPSHOT_DIR/db"

  # Config files (JSON/YAML)
  copy_tree "$REPO_ROOT/config" "$SNAPSHOT_DIR/config"

  # Data JSON/state
  if [ -d "$REPO_ROOT/data" ]; then
    rsync -a --include '*/' --include '*.json' --exclude '*' "$REPO_ROOT/data/" "$SNAPSHOT_DIR/data/" || true
  fi

  # SQLite database snapshot
  backup_sqlite "$DB_PATH" "$SNAPSHOT_DIR/db/lawnberry.db"

  # Include .env if present (contains tokens; protect with 0600)
  if [ -f "$REPO_ROOT/.env" ]; then
    install -m 0600 "$REPO_ROOT/.env" "$SNAPSHOT_DIR/.env"
  fi
}

make_manifest() {
  log "Generating MANIFEST.json and checksums"
  local manifest="$WORK_DIR/MANIFEST.json"
  local tmpfile="$WORK_DIR/.manifest.tmp"
  : > "$tmpfile"
  echo '{' >>"$tmpfile"
  echo '  "timestamp": '"$TIMESTAMP"',' >>"$tmpfile"
  echo '  "files": {' >>"$tmpfile"
  # List files and compute sha256
  local first=1
  while IFS= read -r -d '' f; do
    local rel=${f#"$SNAPSHOT_DIR/"}
    local size
    size=$(stat -c%s "$f")
    local sha
    sha=$(sha256sum "$f" | awk '{print $1}')
    if [ $first -eq 0 ]; then echo ',' >>"$tmpfile"; fi
    first=0
    printf '    "%s": {"size": %s, "sha256": "%s"}' "$rel" "$size" "$sha" >>"$tmpfile"
  done < <(find "$SNAPSHOT_DIR" -type f -print0 | sort -z)
  echo '' >>"$tmpfile"
  echo '  }' >>"$tmpfile"
  echo '}' >>"$tmpfile"
  mv "$tmpfile" "$manifest"
}

create_archive() {
  log "Creating archive $ARCHIVE_PATH"
  (
    cd "$WORK_DIR"
    tar -czf "$ARCHIVE_PATH" MANIFEST.json snapshot
  )
  sha256sum "$ARCHIVE_PATH" | awk '{print $1"  '"$ARCHIVE_NAME"'"}' >"$SHA_PATH"
  chmod 600 "$ARCHIVE_PATH" "$SHA_PATH"
}

enforce_retention() {
  log "Applying retention: $RETENTION_DAYS days"
  find "$BACKUP_ROOT_DIR" -maxdepth 1 -type f -name 'lawnberry-backup-*.tar.gz' -mtime +"$RETENTION_DAYS" -print -exec rm -f {} + || true
  find "$BACKUP_ROOT_DIR" -maxdepth 1 -type f -name 'lawnberry-backup-*.tar.gz.sha256' -mtime +"$RETENTION_DAYS" -print -exec rm -f {} + || true
}

cleanup() {
  rm -rf "$WORK_DIR" || true
}

main() {
  permissions_safe
  ensure_dirs
  collect_meta
  create_snapshot
  make_manifest
  create_archive
  enforce_retention
  cleanup
  log "Backup complete: $ARCHIVE_PATH"
  log "Checksum: $(cut -d' ' -f1 "$SHA_PATH")"
}

main "$@"
