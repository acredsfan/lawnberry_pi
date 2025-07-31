#!/bin/bash
# Coral TPU System Package Installation Script for Pi OS Bookworm
# Official Google-recommended installation method for Debian-based systems

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo
    echo "=================================================================="
    echo "              CORAL TPU SYSTEM PACKAGE INSTALLER"
    echo "       For Raspberry Pi OS Bookworm + Python 3.11+"
    echo "=================================================================="
    echo
}

check_platform_compatibility() {
    log_info "Checking platform compatibility..."
    
    # Check if running on Linux
    if [[ "$OSTYPE" != "linux-gnu"* ]]; then
        log_error "This script requires a Linux system"
        exit 1
    fi
    
    # Check for Debian-based system
    if ! command -v apt-get &> /dev/null; then
        log_error "This script requires a Debian-based system with apt-get"
        exit 1
    fi
    
    # Check for Pi OS Bookworm (recommended)
    if [[ -f /etc/os-release ]]; then
        if grep -q "VERSION_CODENAME=bookworm" /etc/os-release; then
            log_success "Pi OS Bookworm detected - full system package support"
            BOOKWORM_DETECTED=true
        else
            log_warning "Non-Bookworm system detected - compatibility may be limited"
            BOOKWORM_DETECTED=false
        fi
    else
        log_warning "Cannot detect OS version"
        BOOKWORM_DETECTED=false
    fi
    
    # Check Python version
    PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    if python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)"; then
        log_success "Python ${PYTHON_VERSION} detected - compatible with system packages"
    else
        log_warning "Python ${PYTHON_VERSION} detected - Python 3.11+ recommended"
    fi
    
    # Check architecture
    ARCH=$(uname -m)
    case $ARCH in
        aarch64|x86_64)
            log_success "Architecture ${ARCH} - fully supported"
            ;;
        armv7l)
            log_warning "Architecture ${ARCH} - limited support"
            ;;
        *)
            log_warning "Architecture ${ARCH} - compatibility unknown"
            ;;
    esac
}

configure_coral_repository() {
    log_info "Configuring Google Coral repository..."
    
    # Check if repository is already configured
    if [[ -f /etc/apt/sources.list.d/coral-edgetpu.list ]]; then
        log_info "Coral repository already configured"
        return 0
    fi
    
    # Add Google's Coral repository
    echo "deb https://packages.cloud.google.com/apt coral-edgetpu-stable main" | sudo tee /etc/apt/sources.list.d/coral-edgetpu.list
    
    # Add Google's signing key
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -
    
    # Update package lists
    log_info "Updating package lists..."
    sudo apt-get update
    
    log_success "Coral repository configured successfully"
}

detect_existing_coral_packages() {
    log_info "Checking for existing Coral packages..."
    
    # Check for pip-installed packages that might conflict
    CONFLICTING_PACKAGES=()
    
    if python3 -c "import pycoral" 2>/dev/null; then
        # Check if it's pip-installed
        if pip3 show pycoral >/dev/null 2>&1; then
            CONFLICTING_PACKAGES+=("pycoral")
        fi
    fi
    
    if python3 -c "import tflite_runtime" 2>/dev/null; then
        if pip3 show tflite-runtime >/dev/null 2>&1; then
            CONFLICTING_PACKAGES+=("tflite-runtime")
        fi
    fi
    
    if [[ ${#CONFLICTING_PACKAGES[@]} -gt 0 ]]; then
        log_warning "Found pip-installed packages that may conflict with system packages:"
        for pkg in "${CONFLICTING_PACKAGES[@]}"; do
            echo "  - $pkg"
        done
        
        echo
        read -p "Remove conflicting pip packages? [y/N]: " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            for pkg in "${CONFLICTING_PACKAGES[@]}"; do
                log_info "Removing pip package: $pkg"
                pip3 uninstall -y "$pkg" || true
            done
            log_success "Conflicting packages removed"
        else
            log_warning "Conflicting packages may cause issues - consider removing manually"
        fi
    else
        log_success "No conflicting pip packages found"
    fi
}

install_edge_tpu_runtime() {
    log_info "Installing Edge TPU runtime..."
    
    # Check if already installed
    if dpkg -l | grep -q "libedgetpu1"; then
        log_info "Edge TPU runtime already installed"
        return 0
    fi
    
    # Ask user about frequency setting
    echo
    echo "Edge TPU Runtime Frequency Options:"
    echo "  Standard (recommended): Lower power consumption, cooler operation"
    echo "  Maximum: Higher performance, increased power consumption and heat"
    echo
    read -p "Install maximum frequency runtime? [y/N]: " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log_info "Installing maximum frequency runtime..."
        sudo apt-get install -y libedgetpu1-max
        log_warning "WARNING: Device will run hot at maximum frequency!"
    else
        log_info "Installing standard frequency runtime..."
        sudo apt-get install -y libedgetpu1-std
        log_success "Standard frequency runtime installed"
    fi
}

install_pycoral_library() {
    log_info "Installing PyCoral library..."
    
    # Check if already installed
    if dpkg -l | grep -q "python3-pycoral"; then
        log_info "PyCoral library already installed"
        return 0
    fi
    
    sudo apt-get install -y python3-pycoral
    log_success "PyCoral library installed"
}

verify_installation() {
    log_info "Verifying installation..."
    
    # Test PyCoral import
    if python3 -c "from pycoral.utils import edgetpu; print('PyCoral import successful')" 2>/dev/null; then
        log_success "PyCoral library working correctly"
        
        # Test hardware enumeration
        TPU_COUNT=$(python3 -c "from pycoral.utils import edgetpu; print(len(edgetpu.list_edge_tpus()))" 2>/dev/null || echo "0")
        if [[ $TPU_COUNT -gt 0 ]]; then
            log_success "Found $TPU_COUNT Coral TPU device(s)"
        else
            log_info "No Coral TPU hardware detected (software installation successful)"
            log_info "Connect Coral TPU hardware for acceleration"
        fi
    else
        log_error "PyCoral import failed - installation may have issues"
        return 1
    fi
    
    # Test CPU fallback
    if python3 -c "import tflite_runtime.interpreter; print('CPU fallback available')" 2>/dev/null; then
        log_success "CPU fallback available for graceful degradation"
    else
        log_warning "CPU fallback may not be available"
    fi
}

provide_usage_guidance() {
    echo
    echo "=================================================================="
    echo "                    INSTALLATION COMPLETE"
    echo "=================================================================="
    echo
    echo "Next Steps:"
    echo "1. Connect your Coral TPU device (if not already connected)"
    echo "2. Test your installation:"
    echo "   python3 scripts/verify_coral_installation.py"
    echo
    echo "3. Run the LawnBerryPi compatibility test:"
    echo "   python3 -m pytest tests/integration/test_coral_compatibility.py -v"
    echo
    echo "Usage in Python code:"
    echo "try:"
    echo "    from pycoral.utils import edgetpu"
    echo "    tpu_devices = edgetpu.list_edge_tpus()"
    echo "    if tpu_devices:"
    echo "        print('Coral TPU acceleration available')"
    echo "    else:"
    echo "        print('Using CPU fallback')"
    echo "except ImportError:"
    echo "    print('Coral packages not available')"
    echo
    echo "For more information:"
    echo "- Documentation: docs/coral-tpu-compatibility-analysis.md"
    echo "- Official Coral docs: https://coral.ai/docs/accelerator/get-started/"
    echo
}

main() {
    print_header
    
    # Platform compatibility check
    check_platform_compatibility
    
    if [[ "$BOOKWORM_DETECTED" != true ]]; then
        echo
        read -p "Non-Bookworm system detected. Continue anyway? [y/N]: " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Installation cancelled. Consider upgrading to Pi OS Bookworm for full support."
            exit 0
        fi
    fi
    
    # Installation steps
    configure_coral_repository
    detect_existing_coral_packages
    install_edge_tpu_runtime
    install_pycoral_library
    
    # Verification
    if verify_installation; then
        provide_usage_guidance
        log_success "Coral TPU system package installation completed successfully!"
    else
        log_error "Installation verification failed. Check logs for issues."
        exit 1
    fi
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    log_error "Do not run this script as root. It will use sudo when needed."
    exit 1
fi

# Run main function
main "$@"
