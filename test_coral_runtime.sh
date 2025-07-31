#!/bin/bash
# Test script for Coral runtime installer

# Test individual functions by sourcing the script
source scripts/install_coral_runtime.sh

# Test platform detection
echo "=== Testing Platform Detection ==="
detect_platform

echo
echo "=== Testing Hardware Detection ==="
detect_coral_hardware

echo
echo "=== Variables Set ==="
echo "BOOKWORM_DETECTED: $BOOKWORM_DETECTED"
echo "HARDWARE_PRESENT: $HARDWARE_PRESENT"
echo "ARCH: $ARCH"
echo "PYTHON_VERSION: $PYTHON_VERSION"
