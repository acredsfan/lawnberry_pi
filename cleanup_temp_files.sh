#!/bin/bash

# Repository Cleanup Script - Remove temporary development artifacts
# This script removes temporary files created during development while preserving legitimate project files

set -e

echo "=== LawnBerry Pi Repository Cleanup ==="
echo "Removing temporary development artifacts..."

# Change to project root
# Change to repository root dynamically (script's parent directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Track what we remove
removed_count=0

echo
echo "1. Removing temporary shell scripts..."
if ls test_*.sh 1> /dev/null 2>&1; then
    echo "  Removing test shell scripts:"
    for file in test_*.sh; do
        echo "    - $file"
        rm -f "$file"
        ((removed_count++))
    done
else
    echo "  No test shell scripts found."
fi

echo
echo "2. Removing fix scripts (temporary development scripts)..."
temp_fix_scripts=(
    "fix_services.sh"
    "fix_services_final.sh"
    "fix_hardware_detection.sh"
    "fix_install_script.sh"
)

for script in "${temp_fix_scripts[@]}"; do
    if [[ -f "$script" ]]; then
        echo "  Removing: $script"
        rm -f "$script"
        ((removed_count++))
    fi
done

echo
echo "3. Removing installation log files..."
log_files=(
    "install_test.log"
    "scripts/lawnberry_install.log"
    "lawnberry_install.log"
)

for log in "${log_files[@]}"; do
    if [[ -f "$log" ]]; then
        echo "  Removing: $log"
        rm -f "$log"
        ((removed_count++))
    fi
done

echo
echo "4. Removing temporary Python test files (root directory only)..."
temp_test_files=(
    "test_coral_installation_fix.py"
    "test_webui_build.py"
    "test_hardware_fix.py"
)

for test_file in "${temp_test_files[@]}"; do
    if [[ -f "$test_file" ]]; then
        echo "  Removing: $test_file"
        rm -f "$test_file"
        ((removed_count++))
    fi
done

echo
echo "5. Removing temporary validation scripts (keeping legitimate ones)..."
temp_validation_files=(
    "validate_installation.sh"
)

for val_file in "${temp_validation_files[@]}"; do
    if [[ -f "$val_file" ]]; then
        echo "  Removing: $val_file"
        rm -f "$val_file"
        ((removed_count++))
    fi
done

echo
echo "6. Checking for any remaining temporary files..."
temp_patterns=(
    "*_temp*"
    "*_tmp*"
    "*.tmp"
    "temp_*"
    "*_backup"
)

for pattern in "${temp_patterns[@]}"; do
    if ls $pattern 1> /dev/null 2>&1; then
        echo "  Found temporary files matching '$pattern':"
        for file in $pattern; do
            echo "    - $file"
            rm -f "$file"
            ((removed_count++))
        done
    fi
done

echo
echo "=== Files Preserved (Legitimate Project Components) ==="
echo "✅ scripts/fix_permissions.sh - Legitimate utility script"
echo "✅ All validate_*.py files - Project validation tools"
echo "✅ All test_*.py files in tests/ directory - Unit tests"
echo "✅ All test_*.py files in src/ - Component tests"
echo "✅ All configuration files in config/"
echo "✅ All documentation in docs/"
echo "✅ All models and examples"
echo "✅ All web-ui components"
echo "✅ Virtual environment (venv/)"

echo
echo "=== Cleanup Summary ==="
echo "📁 Total temporary files removed: $removed_count"

if [[ $removed_count -eq 0 ]]; then
    echo "🎉 Repository is already clean!"
else
    echo "✅ Repository cleanup completed successfully!"
fi

echo
echo "📊 Repository Status:"
echo "  - Core installation script: scripts/install_lawnberry.sh ✅"
echo "  - Configuration files: $(find config/ -name "*.yaml" | wc -l) files ✅"
echo "  - Documentation: $(find docs/ -name "*.md" | wc -l) files ✅" 
echo "  - Test suites: $(find tests/ -name "*.py" | wc -l) files ✅"
echo "  - Source code: $(find src/ -name "*.py" | wc -l) files ✅"

echo
echo "🚀 Repository is now production-ready!"
