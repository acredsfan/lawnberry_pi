#!/bin/bash
#
# Install pre-commit hooks for LawnBerry Pi development
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GIT_HOOKS_DIR="$REPO_ROOT/.git/hooks"

echo "Installing LawnBerry Pi pre-commit hooks..."

# Check if .git directory exists
if [ ! -d "$REPO_ROOT/.git" ]; then
  echo "❌ Error: Not in a git repository"
  exit 1
fi

# Create hooks directory if it doesn't exist
mkdir -p "$GIT_HOOKS_DIR"

# Install composite pre-commit hook that runs multiple checks
COMPOSITE_HOOK="$GIT_HOOKS_DIR/pre-commit"
cat > "$COMPOSITE_HOOK" << 'HOOK'
#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"

# 1. Gitignore guard — blocks logs, runtime data, secrets, large files.
#    Runs first so subsequent checks don't see bad files.
if [ -f "$REPO_ROOT/scripts/pre-commit-gitignore-guard.sh" ]; then
  "$REPO_ROOT/scripts/pre-commit-gitignore-guard.sh"
fi

# 2. Secret scanner — pattern-matches staged content for tokens/credentials.
if [ -f "$REPO_ROOT/scripts/pre-commit-secret-scan.sh" ]; then
  "$REPO_ROOT/scripts/pre-commit-secret-scan.sh"
fi

# 3. TODO format check.
if [ -f "$REPO_ROOT/scripts/pre-commit-todo-check.sh" ]; then
  "$REPO_ROOT/scripts/pre-commit-todo-check.sh"
fi

exit 0
HOOK

chmod +x "$COMPOSITE_HOOK"
echo "✅ Installed composite pre-commit hook (gitignore guard + secret scan + TODO check)"

echo ""
echo "Pre-commit hooks installed successfully!"
echo ""
echo "The following checks will run before each commit:"
echo "  - Gitignore guard: blocks logs, runtime data, secrets, large files (>2 MB)"
echo "    Auto-adds violating paths to .gitignore and unstages them"
echo "  - Secret scanning: pattern-matches for API keys, tokens, private keys"
echo "  - TODO format compliance: TODO(vX): ... - Issue #N"
echo ""
echo "To bypass checks (emergency only): git commit --no-verify"
