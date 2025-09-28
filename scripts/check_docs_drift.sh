#!/usr/bin/env bash
set -euo pipefail

# Docs drift detection: fail if code changes have no corresponding docs/spec/journal updates.
# Intended for CI, but runnable locally.
#
# Logic:
# - Determine diff range (BASE..HEAD). In PRs, use merge-base with base branch.
# - code_changed: files in backend/, frontend/src/, systemd/, scripts/, pyproject.toml, backend/src/
#                 excluding tests/** and this script itself and CI files.
# - docs_changed: files in docs/**, spec/**, README.md, .specify/memory/AGENT_JOURNAL.md
# If code_changed is true and docs_changed is false -> exit 1 with a helpful message.

BASE_REF=${BASE_REF:-"origin/${GITHUB_BASE_REF:-main}"}
HEAD_REF=${HEAD_REF:-"HEAD"}

# Ensure git history depth is sufficient
git fetch --no-tags --depth=0 origin || true

# Compute range; fallback to BASE_REF..HEAD_REF
MERGE_BASE=$(git merge-base "$BASE_REF" "$HEAD_REF" 2>/dev/null || true)
if [[ -n "${MERGE_BASE}" ]]; then
  RANGE="$MERGE_BASE..$HEAD_REF"
else
  RANGE="$BASE_REF..$HEAD_REF"
fi

CHANGED_FILES=$(git diff --name-only $RANGE | tr '\n' '\n')

# No changes (shouldn't happen in CI) => succeed
if [[ -z "$CHANGED_FILES" ]]; then
  echo "No changed files detected in range $RANGE."
  exit 0
fi

echo "Changed files in $RANGE:" >&2
echo "$CHANGED_FILES" >&2

# Define code vs docs patterns
CODE_REGEX='^(backend/|frontend/src/|systemd/|scripts/|pyproject\.toml)'
# Accept both singular spec/ (repo-local) and plural specs/ (external or future mirror)
DOCS_REGEX='^(docs/|spec/|specs/|README\.md|\.specify/memory/AGENT_JOURNAL\.md)'

# Exclusions (do not count as code for drift): tests/, .github/
EXCLUDE_CODE_REGEX='^(tests/|\.github/|scripts/check_docs_drift\.sh)'

code_changed=false
docs_changed=false

while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  if [[ "$file" =~ $DOCS_REGEX ]]; then
    docs_changed=true
  fi
  if [[ "$file" =~ $CODE_REGEX && ! "$file" =~ $EXCLUDE_CODE_REGEX ]]; then
    code_changed=true
  fi
done <<< "$CHANGED_FILES"

echo "code_changed=$code_changed, docs_changed=$docs_changed" >&2

if [[ "$code_changed" == true && "$docs_changed" == false ]]; then
  echo "Docs drift detected: code changed without corresponding docs/spec/journal updates." >&2
  echo "Please update one of: docs/**, spec/**, README.md, .specify/memory/AGENT_JOURNAL.md" >&2
  exit 1
fi

exit 0
