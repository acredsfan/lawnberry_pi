#!/usr/bin/env bash
# pre-commit-gitignore-guard.sh
#
# Detects staged files that should never be committed (logs, runtime data,
# secrets, large files, compiled artefacts, etc.). For any violation it:
#   1. Adds the specific path to .gitignore (if not already covered)
#   2. Unstages the file
#   3. Prints a clear warning
# If any violations are found the commit is aborted so the developer can review.
#
# Install via:  scripts/install-hooks.sh
# Bypass (emergency only):  git commit --no-verify

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
GITIGNORE="$REPO_ROOT/.gitignore"
LARGE_FILE_THRESHOLD_KB=2048   # 2 MB

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# Pattern categories  (label : extended-grep pattern)
# ---------------------------------------------------------------------------
declare -A PATTERN_LABEL=(
  [log]="Log file"
  [env]="Environment / secrets file"
  [secret]="Private key or certificate"
  [runtime_data]="Runtime data file"
  [compiled]="Compiled Python artefact"
  [temp]="Temporary file"
  [backup]="Backup file"
  [db]="Database file"
  [node]="Node.js dependency directory"
  [venv]="Python virtual environment"
)

# Each entry is a bash extended-regex matched against the staged file path.
declare -A PATTERNS=(
  [log]='(^|/)([^/]+\.log|[^/]+\.log\.[0-9]+)$'
  [env]='(^|/)\.env(\.[^/]+)?$'
  [secret]='(^|/)(.*\.(key|pem|p12|pfx|cer|crt)|secrets\.json|id_rsa|id_ed25519|id_ecdsa)$'
  [runtime_data]='(^|/)data/[^/]+\.(json|csv|db|sqlite|sqlite3)$'
  [compiled]='(^|/)(__pycache__|[^/]+\.(pyc|pyo|pyd))(/|$)'
  [temp]='(^|/)[^/]+\.(tmp|temp|bak|swp|swo)$'
  [backup]='(^|/)(backups/|[^/]+\.backup$)'
  [db]='(^|/)[^/]+\.(db|sqlite|sqlite3)$'
  [node]='(^|/)node_modules/'
  [venv]='(^|/)(\.venv|venv|env|ENV|\.virtualenv|venv-coral)/'
)

# ---------------------------------------------------------------------------
# Specific well-known files that should always be blocked (full path from root)
# ---------------------------------------------------------------------------
BLOCKED_EXACT=(
  "backend.log"
  "frontend.log"
  "backend/backend.log"
  "frontend/frontend.log"
  "console_output.md"
  "test_movement.py"
  "test_satellite_setting.html"
  "test_error_handling.html"
  "config/secrets.json"
  "config/maps_settings.json"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

is_already_ignored() {
  local file="$1"
  # Use git check-ignore to see if a rule already covers this path.
  git check-ignore -q "$file" 2>/dev/null
}

add_to_gitignore() {
  local entry="$1"
  local reason="$2"

  # Don't add duplicate entries.
  if grep -qxF "$entry" "$GITIGNORE" 2>/dev/null; then
    return
  fi

  echo "" >> "$GITIGNORE"
  echo "# Auto-added by pre-commit-gitignore-guard: $reason" >> "$GITIGNORE"
  echo "$entry" >> "$GITIGNORE"
  echo -e "  ${GREEN}→ Added '${entry}' to .gitignore${NC}"
}

unstage_file() {
  git restore --staged "$1" 2>/dev/null || git reset HEAD "$1" 2>/dev/null || true
}

file_size_kb() {
  local file="$1"
  # Size of the staged blob, not the working-tree file.
  local sha
  sha=$(git ls-files --cached -s -- "$file" 2>/dev/null | awk '{print $2}')
  if [[ -n "$sha" ]]; then
    git cat-file -s "$sha" 2>/dev/null | awk '{printf "%d", $1/1024}'
  else
    echo 0
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# Staged files (Added, Copied, Modified) — skip Deleted files.
mapfile -t STAGED < <(git diff --cached --name-only --diff-filter=ACM 2>/dev/null || true)

if [[ ${#STAGED[@]} -eq 0 ]]; then
  exit 0
fi

VIOLATIONS=0

for file in "${STAGED[@]}"; do
  violated=0
  violation_label=""
  gitignore_entry=""

  # --- Exact-match blocklist ---
  for blocked in "${BLOCKED_EXACT[@]}"; do
    if [[ "$file" == "$blocked" ]]; then
      violated=1
      violation_label="Blocked file"
      gitignore_entry="$file"
      break
    fi
  done

  # --- Pattern matching ---
  if [[ $violated -eq 0 ]]; then
    for key in "${!PATTERNS[@]}"; do
      if echo "$file" | grep -Eq "${PATTERNS[$key]}"; then
        violated=1
        violation_label="${PATTERN_LABEL[$key]}"
        # Use the specific file path as the gitignore entry so only
        # this exact file is blocked (more surgical than a broad pattern
        # that might be already present).
        gitignore_entry="$file"
        break
      fi
    done
  fi

  # --- Large file check ---
  if [[ $violated -eq 0 ]]; then
    size_kb=$(file_size_kb "$file")
    if [[ "$size_kb" -ge "$LARGE_FILE_THRESHOLD_KB" ]]; then
      violated=1
      violation_label="Large file (${size_kb} KB ≥ ${LARGE_FILE_THRESHOLD_KB} KB threshold)"
      gitignore_entry="$file"
    fi
  fi

  if [[ $violated -eq 1 ]]; then
    echo -e "${RED}✗ ${violation_label}:${NC} ${file}"
    add_to_gitignore "$gitignore_entry" "$violation_label"
    unstage_file "$file"
    VIOLATIONS=$((VIOLATIONS + 1))
  fi
done

if [[ $VIOLATIONS -gt 0 ]]; then
  echo ""
  echo -e "${YELLOW}⚠  ${VIOLATIONS} file(s) were unstaged and added to .gitignore.${NC}"
  echo -e "${YELLOW}   Stage the updated .gitignore and retry your commit:${NC}"
  echo -e "${CYAN}     git add .gitignore && git commit${NC}"
  echo ""
  echo -e "${YELLOW}   To override (not recommended): git commit --no-verify${NC}"
  exit 1
fi

exit 0
