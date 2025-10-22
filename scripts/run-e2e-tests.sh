#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

pushd "$FRONTEND_DIR" >/dev/null

if [ ! -d "node_modules" ]; then
  npm ci
fi

npm run build
npx playwright install --with-deps chromium
npx playwright test "$@"

popd >/dev/null
