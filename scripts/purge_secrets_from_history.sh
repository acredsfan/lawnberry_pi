#!/usr/bin/env bash
# Purge previously committed secrets from git history
# This is destructive and requires a force-push. Ensure you have backups.

set -euo pipefail

if ! command -v git >/dev/null 2>&1; then
  echo "git not found" >&2
  exit 1
fi

TARGET_FILES=(
  ".env"
  "config/secrets.json"
  "config/maps_settings.json"
)

echo "This will rewrite history and remove the following paths from ALL commits:"
printf '  - %s\n' "${TARGET_FILES[@]}"

echo "\nPress Ctrl+C to abort, or Enter to continue..."
read -r _

# Prefer git filter-repo if available
if command -v git-filter-repo >/dev/null 2>&1; then
  cmd=(git filter-repo)
else
  # Try python module
  if python3 -c 'import git_filter_repo' 2>/dev/null; then
    cmd=(python3 -m git_filter_repo)
  else
    echo "git filter-repo is not installed. Falling back to git filter-branch (slow, deprecated)." >&2
    git filter-branch --force --index-filter \
      'git rm --cached --ignore-unmatch .env config/secrets.json config/maps_settings.json' \
      --prune-empty --tag-name-filter cat -- --all
    echo "\nNow force-push all branches and tags:"
    echo "  git push --force --all"
    echo "  git push --force --tags"
    exit 0
  fi
fi

"${cmd[@]}" --path .env --path config/secrets.json --path config/maps_settings.json --invert-paths || {
  echo "filter-repo failed" >&2
  exit 1
}

echo "\nHistory rewritten. Force-push to remote to complete the purge:"
echo "  git push --force --all"
echo "  git push --force --tags"
