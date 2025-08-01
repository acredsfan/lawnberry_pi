#!/bin/bash

# Fix Shell Script Permissions
# Makes all .sh files in the scripts directory executable

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Fixing shell script permissions..."

# Make all .sh files executable
find "$PROJECT_ROOT/scripts" -name "*.sh" -type f -exec chmod +x {} \;

echo "✅ All shell scripts in scripts/ directory are now executable"

# Show current permissions
echo
echo "Current permissions:"
ls -la "$PROJECT_ROOT/scripts/"*.sh
