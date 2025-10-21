#!/bin/bash
#
# Pre-commit hook to enforce TODO policy
# Install: cp scripts/pre-commit-todo-check.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
#

echo "Checking TODO format compliance..."

# Get list of staged files
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(py|ts|vue|js)$' | grep -v node_modules | grep -v .venv || true)

if [ -z "$STAGED_FILES" ]; then
  echo "✅ No source files staged for commit"
  exit 0
fi

# Check each staged file for TODO markers
INVALID_TODOS=""
for FILE in $STAGED_FILES; do
  if [ -f "$FILE" ]; then
    # Search for TODO/FIXME/XXX/HACK in staged file
    TODOS=$(grep -n "TODO\|FIXME\|XXX\|HACK" "$FILE" 2>/dev/null || true)
    
    if [ ! -z "$TODOS" ]; then
      # Check if TODOs follow proper format: TODO(vX): ... - Issue #N
      INVALID=$(echo "$TODOS" | grep -E "TODO|FIXME|XXX|HACK" | grep -v -E "TODO\(v[0-9]+\):.*Issue #[0-9]+" || true)
      
      if [ ! -z "$INVALID" ]; then
        INVALID_TODOS="$INVALID_TODOS\n$FILE:\n$INVALID\n"
      fi
    fi
  fi
done

if [ ! -z "$INVALID_TODOS" ]; then
  echo "❌ Commit rejected: Found improperly formatted TODOs"
  echo ""
  echo -e "$INVALID_TODOS"
  echo ""
  echo "All TODOs must follow this format:"
  echo "  // TODO(v3): <description> - Issue #<number>"
  echo "  # TODO(v3): <description> - Issue #<number>"
  echo ""
  echo "Please:"
  echo "  1. Create a GitHub issue for the TODO"
  echo "  2. Update the TODO format to reference the issue"
  echo "  3. Stage the changes and commit again"
  echo ""
  echo "To bypass this check (not recommended), use: git commit --no-verify"
  exit 1
fi

echo "✅ All TODOs are properly formatted"
exit 0
