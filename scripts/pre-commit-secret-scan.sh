#!/usr/bin/env bash
# Simple secret scanner to prevent committing sensitive tokens
# Scans staged changes for common secret patterns

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get list of staged files (added/modified)
FILES=$(git diff --cached --name-only --diff-filter=ACM)
if [[ -z "$FILES" ]]; then
  exit 0
fi

# Build combined grep pattern (extended regex)
# - Google API key: AIza...
# - AWS Access Key ID: AKIA...
# - GitHub token: ghp_...
# - Slack token: xox...
# - Private key headers
# - Generic key/password/token assignments
PATTERN='(AIza[0-9A-Za-z\-_]{35}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36,}|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|(^|[^A-Za-z])(api[_-]?key|secret|password|token)\s*[:=]\s*[^\s,;]+)'

FOUND=0

while IFS= read -r file; do
  # Skip example and dist files
  if [[ "$file" =~ \.example$ ]] || [[ "$file" =~ (^|/)dist/ ]]; then
    continue
  fi
  if git show :"$file" | grep -E -n "$PATTERN" >/tmp/secret-scan.out 2>/dev/null; then
    echo -e "${RED}❌ Potential secret detected in staged file:${NC} $file"
    cat /tmp/secret-scan.out | sed -E 's/(AIza[0-9A-Za-z\-_]{35}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{10})/***REDACTED***/g' | sed 's/^/  > /'
    FOUND=1
  fi
  rm -f /tmp/secret-scan.out || true
done <<< "$FILES"

if [[ $FOUND -ne 0 ]]; then
  echo -e "\n${YELLOW}Fix or unstage the offending changes, then commit again.${NC}"
  echo -e "${YELLOW}If this is a false positive, you can bypass with --no-verify (not recommended).${NC}"
  exit 1
fi

exit 0
