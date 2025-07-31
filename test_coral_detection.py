#!/usr/bin/env python3
"""
Test script for Coral TPU detection logic
"""
import sys
import os
sys.path.insert(0, 'scripts')

def test_coral_detection():
    """Test the Coral TPU detection functionality"""
    try:
        from hardware_detection import EnhancedHardwareDetector
        
        print("✅ Successfully imported EnhancedHardwareDetector")
        
        detector = EnhancedHardwareDetector()
        
        # Test individual detection methods
        print("\n🔍 Testing OS compatibility check...")
        os_compatible, os_details = detector._check_pi_os_bookworm_compatibility()
        print(f"OS Compatible: {os_compatible}")
        print(f"OS Details: {os_details}")
        
        print("\n🔍 Testing hardware detection...")
        hardware_present, hardware_details = detector._detect_coral_hardware()
        print(f"Hardware Present: {hardware_present}")
        print(f"Hardware Details: {hardware_details}")
        
        print("\n🔍 Testing software status...")
        software_status, software_details = detector._check_coral_software_status()
        print(f"Software Status: {software_status}")
        print(f"Software Details: {software_details}")
        
        print("\n✅ All Coral detection methods working correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Error testing Coral detection: {e}")
        return False

if __name__ == "__main__":
    success = test_coral_detection()
    sys.exit(0 if success else 1)
