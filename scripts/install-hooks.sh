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

# Install TODO check hook
if [ -f "$SCRIPT_DIR/pre-commit-todo-check.sh" ]; then
  cp "$SCRIPT_DIR/pre-commit-todo-check.sh" "$GIT_HOOKS_DIR/pre-commit"
  chmod +x "$GIT_HOOKS_DIR/pre-commit"
  echo "✅ Installed TODO format check pre-commit hook"
else
  echo "❌ Error: pre-commit-todo-check.sh not found"
  exit 1
fi

echo ""
echo "Pre-commit hooks installed successfully!"
echo ""
echo "The following checks will run before each commit:"
echo "  - TODO format compliance (TODO(vX): ... - Issue #N)"
echo ""
echo "To bypass checks (not recommended): git commit --no-verify"
