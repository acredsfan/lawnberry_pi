#!/usr/bin/env bash
# Quick preflight: scan shell scripts for potentially long-running commands missing explicit timeouts.
# This is a heuristic guardrail; it intentionally errs on the side of caution.
# Usage: timeout 8s bash scripts/check_timeouts.sh || true
set -euo pipefail

# Directories to scan
ROOT_DIR=$(cd "$(dirname "$0")"/.. && pwd)
SCAN_DIRS=("$ROOT_DIR/scripts")

# Patterns considered risky if not wrapped in `timeout` or already guarded by systemd-run TimeoutStopSec
RISKY_CMDS=(
  "python \\|python3"
  "pytest"
  "pip \\|pip3"
  "npm \\|pnpm \\|yarn"
  "rsync"
  "curl \\|wget"
  "git \\|ssh"
  "i2cdetect \\|v4l2-ctl \\|ffmpeg"
)

EXIT=0

echo "Scanning for commands without timeouts..."

for dir in "${SCAN_DIRS[@]}"; do
  while IFS= read -r -d '' file; do
    rel="${file#"$ROOT_DIR"/}"
    # Skip this checker and logs
    [[ "$rel" == "scripts/check_timeouts.sh" ]] && continue

    # Grep risky lines
  while IFS= read -r line; do
      # Skip comments and empty lines
      [[ "$line" =~ ^[[:space:]]*# ]] && continue
      [[ -z "${line//[[:space:]]/}" ]] && continue

      for pat in "${RISKY_CMDS[@]}"; do
        if echo "$line" | grep -Eiq "${pat}"; then
          # Check if timeout or systemd-run TimeoutStopSec guard is nearby
          if ! echo "$line" | grep -Eiq "timeout[[:space:]]+[0-9]+[sm]?|systemd-run"; then
            printf "WARN: %s: %s\n" "$rel" "$line"
            EXIT=1
          fi
        fi
      done
    done < <(grep -nE "$(IFS='|'; echo "${RISKY_CMDS[*]}")" "$file" || true)

  done < <(find "$dir" -type f -name "*.sh" -print0)
done

echo "Scan complete."
if [[ $EXIT -ne 0 ]]; then
  echo "One or more risky commands without explicit timeout found."
fi

exit 0
