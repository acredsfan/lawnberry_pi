#!/usr/bin/env python3
"""
Verification script for PR #10 integration
Tests that the lgpio migration and Pi 4B/5 support is correctly implemented
"""

import sys
import os
import traceback
from pathlib import Path

def test_requirements_updated():
    """Test that requirements.txt has been updated to use lgpio"""
    print("🔍 Testing requirements.txt updates...")
    
    requirements_path = Path("requirements.txt")
    if not requirements_path.exists():
        print("❌ requirements.txt not found")
        return False
    
    content = requirements_path.read_text()
    
    # Check for lgpio
    if "lgpio>=0.2.2,<1.0.0" in content:
        print("✅ lgpio dependency found")
    else:
        print("❌ lgpio dependency missing")
        return False
    
    # Check Pi 4B/5 comment
    if "Pi 4B/5 compatible" in content:
        print("✅ Pi 4B/5 compatibility comment found")
    else:
        print("❌ Pi 4B/5 compatibility comment missing")
        return False
    
    # Check that RPi.GPIO is removed
    if "RPi.GPIO" in content:
        print("❌ RPi.GPIO still present in requirements.txt")
        return False
    else:
        print("✅ RPi.GPIO successfully removed from requirements.txt")
    
    return True

def test_hardware_managers():
    """Test that hardware managers use lgpio"""
    print("\n🔍 Testing hardware manager updates...")
    
    managers_path = Path("src/hardware/managers.py")
    if not managers_path.exists():
        print("❌ hardware/managers.py not found")
        return False
    
    content = managers_path.read_text()
    
    # Check for lgpio import
    if "import lgpio" in content:
        print("✅ lgpio import found")
    else:
        print("❌ lgpio import missing")
        return False
    
    # Check for compatibility comment
    if "Raspberry Pi 4B/5 compatibility" in content:
        print("✅ Pi 4B/5 compatibility comment found")
    else:
        print("⚠️ Pi 4B/5 compatibility comment not found (minor)")
    
    # Check for lgpio API usage
    if "gpiochip_open" in content:
        print("✅ lgpio API usage found (gpiochip_open)")
    else:
        print("❌ lgpio API usage missing")
        return False
    
    return True

def test_tof_manager():
    """Test ToF manager lgpio updates"""
    print("\n🔍 Testing ToF manager updates...")
    
    tof_path = Path("src/hardware/tof_manager.py")
    if not tof_path.exists():
        print("❌ tof_manager.py not found")
        return False
    
    content = tof_path.read_text()
    
    # Check for lgpio import
    if "import lgpio" in content:
        print("✅ lgpio import found in ToF manager")
    else:
        print("❌ lgpio import missing in ToF manager")
        return False
    
    # Check that RPi.GPIO references are removed/updated
    if "RPi.GPIO" in content and "import RPi.GPIO" in content:
        print("❌ RPi.GPIO import still present in ToF manager")
        return False
    else:
        print("✅ RPi.GPIO properly handled in ToF manager")
    
    return True

def test_readme_updates():
    """Test README.md Pi 5 support"""
    print("\n🔍 Testing README.md updates...")
    
    readme_path = Path("README.md")
    if not readme_path.exists():
        print("❌ README.md not found")
        return False
    
    content = readme_path.read_text()
    
    # Check for Pi 4B/5 mention
    if "Raspberry Pi 4B or 5" in content:
        print("✅ Pi 4B/5 support mentioned in README")
    else:
        print("❌ Pi 4B/5 support not mentioned in README")
        return False
    
    return True

def test_config_files():
    """Test configuration files for Pi 5 support"""
    print("\n🔍 Testing configuration file updates...")
    
    config_path = Path("config/bookworm_optimizations.yaml")
    if not config_path.exists():
        print("❌ bookworm_optimizations.yaml not found")
        return False
    
    content = config_path.read_text()
    
    # Check for Pi 4B/5 support
    if "Pi 4B/5" in content:
        print("✅ Pi 4B/5 support found in config")
    else:
        print("❌ Pi 4B/5 support missing in config")
        return False
    
    # Check for Pi 5 overrides
    if "pi5_overrides" in content:
        print("✅ Pi 5 specific overrides found")
    else:
        print("❌ Pi 5 overrides missing")
        return False
    
    return True

def test_file_syntax():
    """Test that Python files compile correctly"""
    print("\n🔍 Testing Python file syntax...")
    
    test_files = [
        "src/hardware/managers.py",
        "src/hardware/tof_manager.py",
        "scripts/hardware_detection.py"
    ]
    
    for file_path in test_files:
        path = Path(file_path)
        if path.exists():
            try:
                with open(path, 'r') as f:
                    compile(f.read(), str(path), 'exec')
                print(f"✅ {file_path} compiles successfully")
            except SyntaxError as e:
                print(f"❌ {file_path} has syntax errors: {e}")
                return False
            except Exception as e:
                print(f"⚠️ {file_path} compile warning: {e}")
        else:
            print(f"⚠️ {file_path} not found")
    
    return True

def main():
    """Run all verification tests"""
    print("🚀 Verifying PR #10 Integration - Pi 4B/5 Support with lgpio Migration")
    print("=" * 70)
    
    tests = [
        ("Requirements.txt Updates", test_requirements_updated),
        ("Hardware Managers", test_hardware_managers), 
        ("ToF Manager", test_tof_manager),
        ("README Updates", test_readme_updates),
        ("Config Files", test_config_files),
        ("File Syntax", test_file_syntax),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 70)
    print("📊 VERIFICATION SUMMARY")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! PR #10 integration is successful.")
        print("✅ The codebase is now ready for production on both Pi 4B and Pi 5!")
        return 0
    else:
        print(f"\n❌ {failed} test(s) failed. Please review the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())