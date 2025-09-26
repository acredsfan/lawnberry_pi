#!/usr/bin/env bash
set -euo pipefail

# LawnBerry Pi v2 restore script
# Usage: restore.sh --archive FILE [--target DIR]
# Defaults:
#   TARGET: /home/pi/lawnberry/data

ARCHIVE=""
TARGET="/home/pi/lawnberry/data"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --archive)
      ARCHIVE="$2"; shift 2;;
    --target)
      TARGET="$2"; shift 2;;
    -h|--help)
      echo "Usage: $0 --archive FILE [--target DIR]"; exit 0;;
    *)
      echo "Unknown option: $1" >&2; exit 2;;
  esac
done

if [[ -z "$ARCHIVE" ]]; then
  echo "--archive is required" >&2
  exit 2
fi

if [[ ! -f "$ARCHIVE" ]]; then
  echo "Archive not found: $ARCHIVE" >&2
  exit 1
fi

mkdir -p "$TARGET"

# Extract with ownership and permissions preserved
tar -xzf "$ARCHIVE" -C "$TARGET"

echo "Restored to $TARGET"
