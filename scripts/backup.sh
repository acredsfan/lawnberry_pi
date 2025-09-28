#!/usr/bin/env bash
set -euo pipefail

# LawnBerry Pi v2 backup script
# Usage: backup.sh [--src DIR] [--dest DIR] [--name NAME]
# Defaults:
#   SRC:  /home/pi/lawnberry/data
#   DEST: /home/pi/lawnberry/backups
#   NAME: lawnberry-YYYYmmdd-HHMMSS.tar.gz

SRC="/home/pi/lawnberry/data"
DEST="/home/pi/lawnberry/backups"
NAME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --src)
      SRC="$2"; shift 2;;
    --dest)
      DEST="$2"; shift 2;;
    --name)
      NAME="$2"; shift 2;;
    -h|--help)
      echo "Usage: $0 [--src DIR] [--dest DIR] [--name NAME]"; exit 0;;
    *)
      echo "Unknown option: $1" >&2; exit 2;;
  esac
done

if [[ ! -d "$SRC" ]]; then
  echo "Source directory not found: $SRC" >&2
  exit 1
fi

mkdir -p "$DEST"

timestamp=$(date +%Y%m%d-%H%M%S)
if [[ -z "$NAME" ]]; then
  NAME="lawnberry-${timestamp}.tar.gz"
fi

ARCHIVE_PATH="$DEST/$NAME"

# Create archive with ownership and permissions preserved
tar -czf "$ARCHIVE_PATH" -C "$SRC" .

echo "$ARCHIVE_PATH"
