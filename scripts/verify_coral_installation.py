#!/usr/bin/env python3
"""
Coral TPU Installation Verification Script
Verifies Pi OS Bookworm + Python 3.11+ system package installation
"""

import sys
import subprocess
import platform
from pathlib import Path

def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def print_status(check, status, details=""):
    status_symbol = "✅" if status else "❌"
    print(f"{status_symbol} {check}")
    if details:
        print(f"   {details}")

def check_platform_compatibility():
    """Check if platform supports Coral TPU system packages"""
    print_header("PLATFORM COMPATIBILITY CHECK")
    
    # Python version check
    python_version = sys.version_info
    python_compatible = python_version >= (3, 11)
    print_status(
        f"Python Version: {python_version[0]}.{python_version[1]}.{python_version[2]}",
        python_compatible,
        "Python 3.11+ required for Pi OS Bookworm" if not python_compatible else "Compatible"
    )
    
    # Architecture check
    arch = platform.machine()
    arch_compatible = arch in ['aarch64', 'x86_64', 'armv7l']
    print_status(
        f"Architecture: {arch}",
        arch_compatible,
        "ARM64 or x86_64 recommended" if not arch_compatible else "Compatible"
    )
    
    # OS check
    try:
        with open('/etc/os-release', 'r') as f:
            os_release = f.read()
        
        is_bookworm = 'VERSION_CODENAME=bookworm' in os_release
        is_debian_based = any(name in os_release.lower() for name in ['debian', 'ubuntu', 'raspbian'])
        
        print_status(
            "Operating System",
            is_debian_based,
            "Debian-based system detected" if is_debian_based else "Non-Debian system"
        )
        
        print_status(
            "Pi OS Bookworm",
            is_bookworm,
            "Bookworm detected - system packages supported" if is_bookworm else "Non-Bookworm system - limited support"
        )
        
        return python_compatible and arch_compatible and is_debian_based and is_bookworm
        
    except FileNotFoundError:
        print_status("Operating System", False, "Cannot detect OS - not a Linux system")
        return False

def check_coral_repository():
    """Check if Coral repository is configured"""
    print_header("CORAL REPOSITORY CHECK")
    
    coral_sources = Path('/etc/apt/sources.list.d/coral-edgetpu.list')
    repo_configured = coral_sources.exists()
    
    print_status(
        "Coral Repository Configured",
        repo_configured,
        "Repository file found" if repo_configured else "Run: echo 'deb https://packages.cloud.google.com/apt coral-edgetpu-stable main' | sudo tee /etc/apt/sources.list.d/coral-edgetpu.list"
    )
    
    if repo_configured:
        try:
            # Check if packages are available
            runtime_check = subprocess.run(['apt-cache', 'show', 'libedgetpu1-std'], 
                                         capture_output=True, text=True)
            runtime_available = runtime_check.returncode == 0
            
            pycoral_check = subprocess.run(['apt-cache', 'show', 'python3-pycoral'], 
                                         capture_output=True, text=True)
            pycoral_available = pycoral_check.returncode == 0
            
            print_status(
                "Edge TPU Runtime Package",
                runtime_available,
                "libedgetpu1-std available" if runtime_available else "Package not found - update apt cache"
            )
            
            print_status(
                "PyCoral Package",
                pycoral_available,
                "python3-pycoral available" if pycoral_available else "Package not found - update apt cache"
            )
            
            return runtime_available and pycoral_available
            
        except Exception as e:
            print_status("Package Availability Check", False, f"Error: {e}")
            return False
    
    return False

def check_installed_packages():
    """Check if Coral packages are installed"""
    print_header("INSTALLED PACKAGES CHECK")
    
    try:
        # Check Edge TPU runtime
        runtime_check = subprocess.run(['dpkg', '-l', 'libedgetpu1-std'], 
                                     capture_output=True, text=True)
        runtime_max_check = subprocess.run(['dpkg', '-l', 'libedgetpu1-max'], 
                                         capture_output=True, text=True)
        
        runtime_std_installed = runtime_check.returncode == 0
        runtime_max_installed = runtime_max_check.returncode == 0
        runtime_installed = runtime_std_installed or runtime_max_installed
        
        runtime_type = "standard frequency" if runtime_std_installed else "maximum frequency" if runtime_max_installed else "not installed"
        
        print_status(
            f"Edge TPU Runtime ({runtime_type})",
            runtime_installed,
            "Install with: sudo apt-get install libedgetpu1-std" if not runtime_installed else "Installed"
        )
        
        # Check PyCoral
        pycoral_check = subprocess.run(['dpkg', '-l', 'python3-pycoral'], 
                                     capture_output=True, text=True)
        pycoral_installed = pycoral_check.returncode == 0
        
        print_status(
            "PyCoral Library",
            pycoral_installed,
            "Install with: sudo apt-get install python3-pycoral" if not pycoral_installed else "Installed"
        )
        
        return runtime_installed and pycoral_installed
        
    except Exception as e:
        print_status("Package Installation Check", False, f"Error: {e}")
        return False

def check_hardware_detection():
    """Check for Coral TPU hardware"""
    print_header("HARDWARE DETECTION")
    
    usb_devices = []
    pcie_devices = []
    device_nodes = []
    
    try:
        # USB device detection
        lsusb_result = subprocess.run(['lsusb'], capture_output=True, text=True)
        if lsusb_result.returncode == 0:
            for line in lsusb_result.stdout.split('\n'):
                if '18d1:9302' in line:  # Google Coral USB Accelerator
                    usb_devices.append(line.strip())
        
        print_status(
            "USB Coral Devices",
            len(usb_devices) > 0,
            f"Found {len(usb_devices)} USB device(s)" if usb_devices else "No USB Coral devices detected"
        )
        
        # PCIe device detection
        try:
            lspci_result = subprocess.run(['lspci'], capture_output=True, text=True)
            if lspci_result.returncode == 0:
                for line in lspci_result.stdout.split('\n'):
                    if '1ac1:' in line:  # Google Edge TPU PCIe
                        pcie_devices.append(line.strip())
        except FileNotFoundError:
            pass  # lspci not available
        
        print_status(
            "PCIe Coral Devices",
            len(pcie_devices) > 0,
            f"Found {len(pcie_devices)} PCIe device(s)" if pcie_devices else "No PCIe Coral devices detected"
        )
        
        # Device node detection
        device_pattern = Path('/dev').glob('apex_*')
        device_nodes = list(device_pattern)
        
        print_status(
            "Device Nodes",
            len(device_nodes) > 0,
            f"Found {len(device_nodes)} device node(s)" if device_nodes else "No /dev/apex_* nodes found"
        )
        
        hardware_present = bool(usb_devices or pcie_devices or device_nodes)
        
        if not hardware_present:
            print("   ℹ️  No Coral TPU hardware detected - CPU fallback will be used")
        
        return hardware_present
        
    except Exception as e:
        print_status("Hardware Detection", False, f"Error: {e}")
        return False

def check_software_functionality():
    """Check if PyCoral software works"""
    print_header("SOFTWARE FUNCTIONALITY CHECK")
    
    # Test PyCoral import
    try:
        from pycoral.utils import edgetpu
        from pycoral.utils import dataset
        from pycoral.adapters import common
        from pycoral.adapters import detect
        
        print_status("PyCoral Import", True, "All PyCoral modules imported successfully")
        
        # Test EdgeTPU enumeration
        try:
            tpu_devices = edgetpu.list_edge_tpus()
            tpu_functional = True
            device_count = len(tpu_devices)
        except Exception as e:
            tpu_functional = False
            device_count = 0
            
        print_status(
            "EdgeTPU Enumeration",
            tpu_functional,
            f"Found {device_count} TPU device(s)" if tpu_functional else f"Enumeration failed: {e}"
        )
        
        pycoral_working = True
        
    except ImportError as e:
        print_status("PyCoral Import", False, f"Import failed: {e}")
        pycoral_working = False
    
    # Test TensorFlow Lite CPU fallback
    try:
        import tflite_runtime.interpreter as tflite
        print_status("TensorFlow Lite Import", True, "CPU fallback available")
        cpu_fallback = True
    except ImportError as e:
        print_status("TensorFlow Lite Import", False, f"CPU fallback failed: {e}")
        cpu_fallback = False
    
    return pycoral_working, cpu_fallback

def provide_installation_guidance():
    """Provide installation guidance based on checks"""
    print_header("INSTALLATION GUIDANCE")
    
    platform_ok = check_platform_compatibility()
    repo_ok = check_coral_repository()
    packages_ok = check_installed_packages()
    hardware_present = check_hardware_detection()
    pycoral_working, cpu_fallback = check_software_functionality()
    
    print_header("SUMMARY AND RECOMMENDATIONS")
    
    if platform_ok and packages_ok and pycoral_working:
        if hardware_present:
            print("🎉 EXCELLENT: Full Coral TPU acceleration ready!")
            print("   • Pi OS Bookworm with Python 3.11+ ✅")
            print("   • System packages installed ✅") 
            print("   • Coral hardware detected ✅")
            print("   • Software functional ✅")
        else:
            print("✅ GOOD: Software ready, hardware missing")
            print("   • Pi OS Bookworm with Python 3.11+ ✅")
            print("   • System packages installed ✅")
            print("   • Connect Coral TPU hardware for acceleration")
            print("   • CPU fallback will be used until hardware connected")
    
    elif platform_ok and not packages_ok:
        print("📦 ACTION REQUIRED: Install Coral packages")
        print("   Run these commands:")
        if not repo_ok:
            print("   1. Configure repository:")
            print("      echo 'deb https://packages.cloud.google.com/apt coral-edgetpu-stable main' | sudo tee /etc/apt/sources.list.d/coral-edgetpu.list")
            print("      curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -")
            print("      sudo apt-get update")
        print("   2. Install packages:")
        print("      sudo apt-get install libedgetpu1-std python3-pycoral")
    
    elif not platform_ok:
        print("⚠️  PLATFORM LIMITATION:")
        print("   • Pi OS Bookworm with Python 3.11+ recommended for full support")
        print("   • Consider upgrading to Bookworm for optimal Coral TPU support")
        print("   • Current platform may have limited compatibility")
    
    else:
        print("🔧 TROUBLESHOOTING NEEDED:")
        print("   • Check installation logs for errors")
        print("   • Verify repository configuration")
        print("   • Consider reinstalling packages")
    
    if cpu_fallback:
        print("   • CPU fallback available for graceful degradation ✅")
    else:
        print("   • ⚠️  CPU fallback not available - install tflite-runtime")

def main():
    """Main verification function"""
    print("Coral TPU Installation Verification")
    print("For Pi OS Bookworm + Python 3.11+ System Package Installation")
    
    provide_installation_guidance()
    
    print_header("VERIFICATION COMPLETE")
    print("For more information, see: docs/coral-tpu-compatibility-analysis.md")

if __name__ == "__main__":
    main()
