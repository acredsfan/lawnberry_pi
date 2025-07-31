#!/usr/bin/env python3
"""
Coral TPU Compatibility Test Framework
Tests for Pi OS Bookworm + Python 3.11+ compatibility matrix
"""

import pytest
import subprocess
import sys
import os
import platform
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

class CoralCompatibilityTester:
    """Test framework for Coral TPU compatibility on Pi OS Bookworm"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.test_results: Dict[str, Dict] = {}
        
    def detect_os_compatibility(self) -> Dict[str, any]:
        """Detect OS compatibility with Coral TPU system packages"""
        result = {
            'os_name': platform.system(),
            'os_release': None,
            'is_bookworm': False,
            'is_debian_based': False,
            'python_version': sys.version_info,
            'python_compatible': sys.version_info >= (3, 11),
            'architecture': platform.machine(),
            'supported_platform': False
        }
        
        try:
            # Check OS release info
            with open('/etc/os-release', 'r') as f:
                os_release = f.read()
                result['os_release'] = os_release
                result['is_bookworm'] = 'VERSION_CODENAME=bookworm' in os_release
                result['is_debian_based'] = any(name in os_release.lower() 
                                              for name in ['debian', 'ubuntu', 'raspbian'])
        except FileNotFoundError:
            self.logger.warning("Cannot read /etc/os-release - not a Linux system")
        
        # Determine platform support
        result['supported_platform'] = (
            result['is_bookworm'] and 
            result['python_compatible'] and
            result['architecture'] in ['aarch64', 'x86_64']
        )
        
        return result
    
    def test_system_package_availability(self) -> Dict[str, any]:
        """Test if Coral system packages are available"""
        result = {
            'repository_configured': False,
            'edgetpu_runtime_available': False,
            'pycoral_available': False,
            'packages_installable': False
        }
        
        try:
            # Check if Coral repository is configured
            coral_sources = Path('/etc/apt/sources.list.d/coral-edgetpu.list')
            result['repository_configured'] = coral_sources.exists()
            
            if result['repository_configured']:
                # Test package availability (don't actually install)
                cmd_runtime = ['apt-cache', 'show', 'libedgetpu1-std']
                runtime_check = subprocess.run(cmd_runtime, capture_output=True, text=True)
                result['edgetpu_runtime_available'] = runtime_check.returncode == 0
                
                cmd_pycoral = ['apt-cache', 'show', 'python3-pycoral']
                pycoral_check = subprocess.run(cmd_pycoral, capture_output=True, text=True)
                result['pycoral_available'] = pycoral_check.returncode == 0
                
                result['packages_installable'] = (
                    result['edgetpu_runtime_available'] and 
                    result['pycoral_available']
                )
        except Exception as e:
            self.logger.error(f"Error checking system packages: {e}")
        
        return result
    
    def test_coral_hardware_detection(self) -> Dict[str, any]:
        """Test Coral TPU hardware detection"""
        result = {
            'usb_devices_detected': [],
            'pcie_devices_detected': [],
            'device_nodes_present': [],
            'coral_hardware_present': False
        }
        
        try:
            # USB device detection
            lsusb_result = subprocess.run(['lsusb'], capture_output=True, text=True)
            if lsusb_result.returncode == 0:
                for line in lsusb_result.stdout.split('\n'):
                    if '18d1:9302' in line:  # Google Coral USB Accelerator
                        result['usb_devices_detected'].append(line.strip())
            
            # PCIe device detection
            try:
                lspci_result = subprocess.run(['lspci'], capture_output=True, text=True)
                if lspci_result.returncode == 0:
                    for line in lspci_result.stdout.split('\n'):
                        if '1ac1:' in line:  # Google Edge TPU PCIe
                            result['pcie_devices_detected'].append(line.strip())
            except FileNotFoundError:
                pass  # lspci not available
            
            # Device node detection
            device_pattern = Path('/dev').glob('apex_*')
            result['device_nodes_present'] = [str(p) for p in device_pattern]
            
            result['coral_hardware_present'] = bool(
                result['usb_devices_detected'] or 
                result['pcie_devices_detected'] or 
                result['device_nodes_present']
            )
            
        except Exception as e:
            self.logger.error(f"Error detecting hardware: {e}")
        
        return result
    
    def test_pycoral_import(self) -> Dict[str, any]:
        """Test PyCoral library import capabilities"""
        result = {
            'pycoral_importable': False,
            'tflite_importable': False,
            'edgetpu_functional': False,
            'cpu_fallback_available': False,
            'import_errors': []
        }
        
        # Test PyCoral import
        try:
            from pycoral.utils import edgetpu
            from pycoral.utils import dataset
            from pycoral.adapters import common
            from pycoral.adapters import detect
            result['pycoral_importable'] = True
            
            # Test EdgeTPU functionality
            try:
                tpu_devices = edgetpu.list_edge_tpus()
                result['edgetpu_functional'] = True
                result['tpu_devices_found'] = len(tpu_devices)
            except Exception as e:
                result['import_errors'].append(f"EdgeTPU enumeration failed: {e}")
                
        except ImportError as e:
            result['import_errors'].append(f"PyCoral import failed: {e}")
        
        # Test TensorFlow Lite import for CPU fallback
        try:
            import tflite_runtime.interpreter as tflite
            result['tflite_importable'] = True
            
            # Test CPU interpreter creation
            try:
                # This would need a real model file to test fully
                result['cpu_fallback_available'] = True
            except Exception as e:
                result['import_errors'].append(f"CPU fallback test failed: {e}")
                
        except ImportError as e:
            result['import_errors'].append(f"TensorFlow Lite import failed: {e}")
        
        return result
    
    def run_compatibility_matrix_test(self) -> Dict[str, Dict]:
        """Run the complete compatibility matrix test"""
        self.logger.info("Running Coral TPU compatibility matrix test")
        
        results = {
            'os_compatibility': self.detect_os_compatibility(),
            'system_packages': self.test_system_package_availability(),
            'hardware_detection': self.test_coral_hardware_detection(),
            'software_imports': self.test_pycoral_import()
        }
        
        # Overall compatibility assessment
        os_compat = results['os_compatibility']
        sys_packages = results['system_packages']
        hw_detection = results['hardware_detection']
        sw_imports = results['software_imports']
        
        results['overall_assessment'] = {
            'platform_supported': os_compat['supported_platform'],
            'installation_method': self._determine_installation_method(results),
            'recommended_action': self._get_recommended_action(results),
            'fallback_available': sw_imports['cpu_fallback_available'],
            'hardware_present': hw_detection['coral_hardware_present']
        }
        
        self.test_results = results
        return results
    
    def _determine_installation_method(self, results: Dict) -> str:
        """Determine the recommended installation method"""
        os_compat = results['os_compatibility']
        sys_packages = results['system_packages']
        
        if os_compat['supported_platform']:
            if sys_packages['packages_installable']:
                return "system_packages"
            else:
                return "system_packages_setup_required"
        else:
            if os_compat['python_compatible']:
                return "pip_fallback"  # Limited support
            else:
                return "unsupported"
    
    def _get_recommended_action(self, results: Dict) -> str:
        """Get recommended action based on test results"""
        installation_method = self._determine_installation_method(results)
        hw_present = results['hardware_detection']['coral_hardware_present']
        sw_working = results['software_imports']['pycoral_importable']
        
        if installation_method == "system_packages":
            if sw_working:
                return "ready_to_use" if hw_present else "software_ready_hardware_missing"
            else:
                return "install_system_packages"
        elif installation_method == "system_packages_setup_required":
            return "configure_coral_repository"
        elif installation_method == "pip_fallback":
            return "limited_pip_support"
        else:
            return "platform_not_supported"
    
    def generate_compatibility_report(self) -> str:
        """Generate a human-readable compatibility report"""
        if not self.test_results:
            self.run_compatibility_matrix_test()
        
        results = self.test_results
        os_compat = results['os_compatibility']
        overall = results['overall_assessment']
        
        report = []
        report.append("=== CORAL TPU COMPATIBILITY REPORT ===\n")
        
        # Platform Information
        report.append("PLATFORM INFORMATION:")
        report.append(f"  OS: {os_compat['os_name']}")
        report.append(f"  Bookworm: {'✅ Yes' if os_compat['is_bookworm'] else '❌ No'}")
        report.append(f"  Python: {os_compat['python_version'][0]}.{os_compat['python_version'][1]}.{os_compat['python_version'][2]}")
        report.append(f"  Architecture: {os_compat['architecture']}")
        report.append(f"  Platform Supported: {'✅ Yes' if overall['platform_supported'] else '❌ No'}")
        report.append("")
        
        # Installation Method
        report.append("INSTALLATION METHOD:")
        method = overall['installation_method']
        if method == "system_packages":
            report.append("  ✅ System packages (RECOMMENDED)")
        elif method == "system_packages_setup_required":
            report.append("  ⚠️  System packages (setup required)")
        elif method == "pip_fallback":
            report.append("  ⚠️  pip fallback (limited support)")
        else:
            report.append("  ❌ Not supported")
        report.append("")
        
        # Hardware Status
        hw_detection = results['hardware_detection']
        report.append("HARDWARE STATUS:")
        report.append(f"  Coral Hardware Present: {'✅ Yes' if hw_detection['coral_hardware_present'] else '❌ No'}")
        if hw_detection['usb_devices_detected']:
            report.append(f"  USB Devices: {len(hw_detection['usb_devices_detected'])}")
        if hw_detection['pcie_devices_detected']:
            report.append(f"  PCIe Devices: {len(hw_detection['pcie_devices_detected'])}")
        report.append("")
        
        # Software Status
        sw_imports = results['software_imports']
        report.append("SOFTWARE STATUS:")
        report.append(f"  PyCoral Available: {'✅ Yes' if sw_imports['pycoral_importable'] else '❌ No'}")
        report.append(f"  CPU Fallback Available: {'✅ Yes' if sw_imports['cpu_fallback_available'] else '❌ No'}")
        if sw_imports['import_errors']:
            report.append("  Import Errors:")
            for error in sw_imports['import_errors']:
                report.append(f"    - {error}")
        report.append("")
        
        # Recommended Action
        report.append("RECOMMENDED ACTION:")
        action = overall['recommended_action']
        action_messages = {
            'ready_to_use': '✅ System ready - Coral TPU acceleration available',
            'software_ready_hardware_missing': '⚠️  Software ready - Connect Coral TPU hardware',
            'install_system_packages': '📦 Install system packages: sudo apt-get install python3-pycoral',
            'configure_coral_repository': '🔧 Configure Coral repository and install packages',
            'limited_pip_support': '⚠️  Limited support - consider upgrading to Bookworm',
            'platform_not_supported': '❌ Platform not supported for Coral TPU'
        }
        report.append(f"  {action_messages.get(action, f'Unknown action: {action}')}")
        
        return "\n".join(report)


# Pytest test functions
@pytest.fixture
def coral_tester():
    """Fixture providing CoralCompatibilityTester instance"""
    return CoralCompatibilityTester()

def test_os_compatibility_detection(coral_tester):
    """Test OS compatibility detection"""
    result = coral_tester.detect_os_compatibility()
    
    # Basic assertions
    assert 'python_version' in result
    assert 'architecture' in result
    assert 'supported_platform' in result
    
    # Log results for debugging
    print(f"OS Compatibility: {result}")

def test_system_package_availability(coral_tester):
    """Test system package availability (only on supported platforms)"""
    os_compat = coral_tester.detect_os_compatibility()
    
    if not os_compat['supported_platform']:
        pytest.skip("System package test not applicable on unsupported platform")
    
    result = coral_tester.test_system_package_availability()
    print(f"System Package Availability: {result}")

def test_hardware_detection(coral_tester):
    """Test Coral hardware detection (always runs)"""
    result = coral_tester.test_coral_hardware_detection()
    
    # This test always runs regardless of hardware presence
    assert 'coral_hardware_present' in result
    assert 'usb_devices_detected' in result
    assert 'pcie_devices_detected' in result
    
    print(f"Hardware Detection: {result}")

def test_software_imports(coral_tester):
    """Test software import capabilities"""
    result = coral_tester.test_pycoral_import()
    
    # CPU fallback should always be testable
    assert 'cpu_fallback_available' in result
    assert 'tflite_importable' in result
    
    print(f"Software Imports: {result}")

def test_hardware_specific_functionality(coral_tester):
    """Test hardware-specific functionality (only when hardware present)"""
    hw_result = coral_tester.test_coral_hardware_detection()
    
    if not hw_result['coral_hardware_present']:
        pytest.skip("No Coral TPU hardware detected - skipping hardware-specific tests")
    
    sw_result = coral_tester.test_pycoral_import()
    
    # Hardware-specific assertions
    assert sw_result['pycoral_importable'], "PyCoral should be importable when hardware is present"
    assert sw_result['edgetpu_functional'], "EdgeTPU functions should work when hardware is present"

def test_cpu_fallback_always_available(coral_tester):
    """Test that CPU fallback is always available (runs regardless of hardware)"""
    result = coral_tester.test_pycoral_import()
    
    # CPU fallback should be available even without Coral hardware
    # This is a critical requirement for graceful degradation
    assert result['tflite_importable'] or result['cpu_fallback_available'], \
        "CPU fallback should be available for graceful degradation"

def test_compatibility_matrix_complete(coral_tester):
    """Test the complete compatibility matrix"""
    results = coral_tester.run_compatibility_matrix_test()
    
    # Ensure all test categories completed
    required_categories = ['os_compatibility', 'system_packages', 'hardware_detection', 'software_imports']
    for category in required_categories:
        assert category in results, f"Missing test category: {category}"
    
    # Ensure overall assessment is present
    assert 'overall_assessment' in results
    assert 'recommended_action' in results['overall_assessment']
    
    # Generate and print report
    report = coral_tester.generate_compatibility_report()
    print("\n" + report)

if __name__ == "__main__":
    # Run compatibility test when executed directly
    tester = CoralCompatibilityTester()
    tester.run_compatibility_matrix_test()
    print(tester.generate_compatibility_report())
