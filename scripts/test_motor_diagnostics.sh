#!/bin/bash
# Motor Control Diagnostic Test Script
# Tests the new progressive stiffness detection and heading validation endpoints
#
# Usage:
#   ./scripts/test_motor_diagnostics.sh [test|stiffness|heading]
#   test    - Run all diagnostics (default)
#   stiffness - Progressive turn stiffness test
#   heading - GPS vs IMU heading validation

set -e

API_BASE="http://localhost:8000/api/v2"
SESSION_ID=$(python3 -c "import uuid; print(str(uuid.uuid4()))")

echo "🔍 LawnBerry Motor Control Diagnostics"
echo "======================================="
echo "Session ID: $SESSION_ID"
echo ""

# Function to test progressive stiffness
test_stiffness() {
    local direction="${1:-left}"
    echo "📊 Progressive Stiffness Test (Turn $direction)"
    echo "-------------------------------------------"
    echo "This test slowly increases turn effort until the motor gets stuck."
    echo "Watch the heading_delta value - when it drops below 0.3°, motor is stuck."
    echo ""
    
    local iteration=1
    local test_active=true
    
    while [ "$test_active" = "true" ]; do
        echo "Iteration $iteration:"
        response=$(curl -s -X POST "$API_BASE/control/diagnose/stiffness" \
            -H "Content-Type: application/json" \
            -d "{
                \"session_id\": \"$SESSION_ID\",
                \"direction\": \"$direction\",
                \"initial_effort\": 0.1,
                \"step\": 0.05,
                \"max_effort\": 1.0
            }")
        
        echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
        echo ""
        
        # Check if test is still active
        test_active=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('test_active', False))" 2>/dev/null || echo "false")
        
        if [ "$test_active" = "True" ] || [ "$test_active" = "true" ]; then
            echo "Waiting 2 seconds before next iteration..."
            sleep 2
        else
            echo "✅ Test Complete"
            break
        fi
        
        iteration=$((iteration + 1))
        if [ $iteration -gt 20 ]; then
            echo "⚠️  Stopping after 20 iterations"
            break
        fi
    done
    echo ""
}

# Function to test heading validation
test_heading() {
    echo "🧭 Heading Validation Test"
    echo "-------------------------------"
    echo "This test drives forward while comparing GPS Course-Over-Ground vs IMU yaw."
    echo "It detects: heading agreement, 180° inversion, or conflicts."
    echo ""
    
    echo "Starting heading validation..."
    response=$(curl -s -X POST "$API_BASE/control/diagnose/heading-validation" \
        -H "Content-Type: application/json" \
        -d "{
            \"session_id\": \"$SESSION_ID\",
            \"distance_m\": 5.0,
            \"samples\": 10
        }")
    
    echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
    echo ""
    
    # Extract recommendation
    recommendation=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('recommendation', 'N/A'))" 2>/dev/null)
    echo "📋 Recommendation: $recommendation"
    echo ""
}

# Main test selection
test_type="${1:-test}"

case "$test_type" in
    stiffness)
        direction="${2:-left}"
        test_stiffness "$direction"
        ;;
    heading)
        test_heading
        ;;
    test)
        echo "Running full diagnostic suite..."
        echo ""
        test_stiffness "left"
        echo ""
        echo "---"
        echo ""
        test_stiffness "right"
        echo ""
        echo "---"
        echo ""
        test_heading
        ;;
    *)
        echo "Unknown test type: $test_type"
        echo "Usage: $0 [test|stiffness|heading]"
        exit 1
        ;;
esac

echo "✅ Diagnostics Complete"
