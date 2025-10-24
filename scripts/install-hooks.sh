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

# Run TODO check if available
if [ -f "$REPO_ROOT/scripts/pre-commit-todo-check.sh" ]; then
  "$REPO_ROOT/scripts/pre-commit-todo-check.sh"
fi

# Run secret scan if available
if [ -f "$REPO_ROOT/scripts/pre-commit-secret-scan.sh" ]; then
  "$REPO_ROOT/scripts/pre-commit-secret-scan.sh"
fi

exit 0
HOOK

chmod +x "$COMPOSITE_HOOK"
echo "✅ Installed composite pre-commit hook (TODO check + secret scan)"

echo ""
echo "Pre-commit hooks installed successfully!"
echo ""
echo "The following checks will run before each commit:"
echo "  - TODO format compliance (TODO(vX): ... - Issue #N)"
echo "  - Secret scanning for common tokens (API keys, private keys, etc.)"
echo ""
echo "To bypass checks (not recommended): git commit --no-verify"
