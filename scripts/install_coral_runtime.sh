#!/bin/bash
# Coral Edge TPU Runtime Installation Script for Pi OS Bookworm
# Handles libedgetpu runtime installation according to official Google documentation
# Can be run standalone or integrated with main installer

set -e

# Command line argument parsing
ALLOW_ROOT=false
DRY_RUN=false
NON_INTERACTIVE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --allow-root)
            ALLOW_ROOT=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --non-interactive)
            NON_INTERACTIVE=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --allow-root      Allow running as root (for CI/Docker environments)"
            echo "  --dry-run         Perform dry run without making changes"
            echo "  --non-interactive Use default options without prompts"
            echo "  --help, -h        Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/tmp/coral_runtime_install.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Global variables
BOOKWORM_DETECTED=false
RUNTIME_INSTALLED=false
PERFORMANCE_MODE=""
HARDWARE_PRESENT=false
REPOSITORY_CONFIGURED=false

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

print_header() {
    echo
    echo "=================================================================="
    echo "           CORAL EDGE TPU RUNTIME INSTALLER"
    echo "        For Raspberry Pi OS Bookworm + Python 3.11+"
    echo "=================================================================="
    echo
    log_info "Installation log: $LOG_FILE"
    echo
}

print_section() {
    echo
    echo "----------------------------------------"
    echo "$1"
    echo "----------------------------------------"
}

# OS and platform detection
detect_platform() {
    print_section "Platform Detection"
    
    log_info "Detecting operating system and architecture..."
    
    # Check if running on Linux
    if [[ "$OSTYPE" != "linux-gnu"* ]]; then
        log_error "This script requires a Linux system"
        log_error "Please refer to https://coral.ai/docs/accelerator/get-started/ for other platforms"
        exit 1
    fi
    
    # Check for Debian-based system
    if ! command -v apt-get &> /dev/null; then
        log_error "This script requires a Debian-based system with apt-get"
        log_error "For other Linux distributions, please refer to:"
        log_error "https://coral.ai/docs/accelerator/get-started/#requirements"
        exit 1
    fi
    
    # Check for Pi OS Bookworm (recommended)
    if [[ -f /etc/os-release ]]; then
        if grep -q "VERSION_CODENAME=bookworm" /etc/os-release; then
            log_success "Pi OS Bookworm detected - full runtime support"
            BOOKWORM_DETECTED=true
        elif grep -q "VERSION_CODENAME=bullseye" /etc/os-release; then
            log_warning "Pi OS Bullseye detected - limited support"
            log_warning "Consider upgrading to Bookworm for better compatibility"
            BOOKWORM_DETECTED=false
        else
            log_warning "Non-Raspberry Pi OS detected"
            log_info "Attempting installation with generic Debian method"
            BOOKWORM_DETECTED=false
        fi
    else
        log_warning "Cannot detect OS version - proceeding with generic installation"
        BOOKWORM_DETECTED=false
    fi
    
    # Check architecture
    ARCH=$(uname -m)
    case $ARCH in
        aarch64)
            log_success "Architecture: ${ARCH} (64-bit ARM) - fully supported"
            ;;
        x86_64)
            log_success "Architecture: ${ARCH} (64-bit x86) - fully supported"
            ;;
        armv7l)
            log_warning "Architecture: ${ARCH} (32-bit ARM) - limited support"
            log_warning "Consider using 64-bit Pi OS for better performance"
            ;;
        *)
            log_error "Architecture: ${ARCH} - not supported"
            log_error "Supported architectures: aarch64, x86_64, armv7l"
            exit 1
            ;;
    esac
    
    # Check Python version
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
            log_success "Python ${PYTHON_VERSION} - compatible with system packages"
        else
            log_warning "Python ${PYTHON_VERSION} - Python 3.11+ recommended for Bookworm"
        fi
    else
        log_error "Python 3 not found - required for runtime verification"
        exit 1
    fi
}

# Hardware detection
detect_coral_hardware() {
    print_section "Coral Hardware Detection"
    
    HARDWARE_PRESENT=false
    
    # Check for USB Accelerator
    log_info "Scanning for Coral USB Accelerator..."
    if lsusb | grep -q "18d1:9302"; then
        log_success "Coral USB Accelerator detected (Vendor: 18d1, Product: 9302)"
        HARDWARE_PRESENT=true
    elif lsusb | grep -q "1a6e:089a"; then
        log_success "Coral USB Accelerator (older model) detected"
        HARDWARE_PRESENT=true
    else
        log_info "No Coral USB Accelerator currently connected"
    fi
    
    # Check for M.2 Accelerator (PCIe)
    log_info "Scanning for Coral M.2 Accelerator..."
    if lspci 2>/dev/null | grep -i "coral\|edgetpu\|google" &> /dev/null; then
        log_success "Coral M.2 Accelerator detected"
        HARDWARE_PRESENT=true
    else
        log_info "No Coral M.2 Accelerator detected"
    fi
    
    # Check for Dev Board
    log_info "Checking for Coral Dev Board..."
    if [[ -d /sys/devices/platform/edgetpu ]]; then
        log_success "Coral Dev Board detected"
        HARDWARE_PRESENT=true
    else
        log_info "Not running on Coral Dev Board"
    fi
    
    if [[ "$HARDWARE_PRESENT" == true ]]; then
        log_success "Coral hardware detected - runtime installation recommended"
    else
        log_info "No Coral hardware currently detected"
        log_info "Runtime can still be installed for future hardware addition"
    fi
}

# Repository configuration
configure_coral_repository() {
    print_section "Configuring Google Coral Repository"
    
    # Check if repository is already configured
    if [[ -f /etc/apt/sources.list.d/coral-edgetpu.list ]]; then
        log_info "Coral repository already configured"
        REPOSITORY_CONFIGURED=true
        return 0
    fi
    
    log_info "Adding Google Coral repository to system sources..."
    
    # Add Google's GPG key
    log_info "Adding Google's GPG key..."
    if ! curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add - 2>/dev/null; then
        log_error "Failed to add Google's GPG key"
        log_error "Please check your internet connection and try again"
        return 1
    fi
    
    # Add repository
    log_info "Adding Coral Edge TPU repository..."
    echo "deb https://packages.cloud.google.com/apt coral-edgetpu-stable main" | sudo tee /etc/apt/sources.list.d/coral-edgetpu.list >/dev/null
    
    # Update package lists
    log_info "Updating package lists..."
    if sudo apt-get update -qq; then
        log_success "Repository configured successfully"
        REPOSITORY_CONFIGURED=true
    else
        log_error "Failed to update package lists"
        log_error "Repository configuration may have failed"
        return 1
    fi
}

# Performance mode selection
select_performance_mode() {
    print_section "Performance Mode Selection"
    
    echo "The Edge TPU runtime supports two operating frequencies:"
    echo
    echo "1. STANDARD frequency (recommended)"
    echo "   - Balanced performance and thermal management"
    echo "   - Suitable for most applications"
    echo "   - Lower power consumption"
    echo
    echo "2. MAXIMUM frequency (advanced users)"
    echo "   - Higher performance but increased heat generation"
    echo "   - Requires adequate cooling"
    echo "   - May throttle without proper heat dissipation"
    echo
    
    # Default to standard mode in non-interactive environments
    if [[ ! -t 0 || "$NON_INTERACTIVE" == true ]]; then
        log_info "Non-interactive mode detected - using STANDARD frequency"
        PERFORMANCE_MODE="standard"
        return 0
    fi
    
    while true; do
        read -p "Select performance mode (1=standard, 2=maximum) [1]: " choice
        case $choice in
            1|"")
                PERFORMANCE_MODE="standard"
                log_info "Selected: STANDARD frequency mode"
                break
                ;;
            2)
                PERFORMANCE_MODE="maximum"
                log_warning "Selected: MAXIMUM frequency mode"
                log_warning "Ensure adequate cooling to prevent thermal throttling"
                break
                ;;
            *)
                echo "Please enter 1 or 2"
                ;;
        esac
    done
}

# Runtime installation
install_runtime() {
    print_section "Installing Edge TPU Runtime"
    
    if [[ "$REPOSITORY_CONFIGURED" != true ]]; then
        log_error "Repository not configured - cannot install runtime"
        return 1
    fi
    
    # Determine package name based on performance mode
    local package_name
    if [[ "$PERFORMANCE_MODE" == "maximum" ]]; then
        package_name="libedgetpu1-max"
    else
        package_name="libedgetpu1-std"
    fi
    
    log_info "Installing $package_name..."
    
    # Dry run mode
    if [[ "$DRY_RUN" == true ]]; then
        log_info "[DRY RUN] Would install package: $package_name"
        RUNTIME_INSTALLED=true
        return 0
    fi
    
    # Check if already installed
    if dpkg -l | grep -q "^ii.*$package_name"; then
        log_info "Runtime package $package_name is already installed"
        
        # Check for conflicting package
        local other_package
        if [[ "$PERFORMANCE_MODE" == "maximum" ]]; then
            other_package="libedgetpu1-std"
        else
            other_package="libedgetpu1-max"
        fi
        
        if dpkg -l | grep -q "^ii.*$other_package"; then
            log_warning "Conflicting package $other_package detected"
            log_info "Removing conflicting package..."
            sudo apt-get remove -y "$other_package"
        fi
        
        RUNTIME_INSTALLED=true
        return 0
    fi
    
    # Install the runtime package  
    if sudo apt-get install -y "$package_name"; then
        log_success "Edge TPU runtime installed successfully"
        RUNTIME_INSTALLED=true
    else
        log_error "Failed to install Edge TPU runtime"
        log_error "This may be due to:"
        log_error "  - Network connectivity issues"
        log_error "  - Repository synchronization problems"
        log_error "  - Platform compatibility issues"
        return 1
    fi
}

# Installation verification
verify_installation() {
    print_section "Verifying Runtime Installation"
    
    # Check if runtime package is installed
    local expected_package
    if [[ "$PERFORMANCE_MODE" == "maximum" ]]; then
        expected_package="libedgetpu1-max"
    else
        expected_package="libedgetpu1-std"
    fi
    
    if ! dpkg -l | grep -q "^ii.*$expected_package"; then
        log_error "Runtime package $expected_package not found"
        return 1
    fi
    
    log_success "Runtime package $expected_package is installed"
    
    # Check if runtime library is accessible
    if ldconfig -p | grep -q "libedgetpu.so"; then
        log_success "Edge TPU runtime library is accessible"
    else
        log_warning "Edge TPU runtime library not found in system paths"
        log_info "You may need to restart your session or reboot"
    fi
    
    # Test with Python (if hardware is present)
    if [[ "$HARDWARE_PRESENT" == true ]]; then
        log_info "Testing runtime with Python..."
        
        # Create temporary test script
        local test_script=$(mktemp)
        cat > "$test_script" << 'EOF'
try:
    # Try to import and test the runtime
    import platform
    print(f"Python {platform.python_version()} on {platform.system()} {platform.machine()}")
    
    # Test basic tflite functionality
    try:
        import tflite_runtime.interpreter as tflite
        print("✓ TensorFlow Lite runtime available")
    except ImportError:
        print("✗ TensorFlow Lite runtime not available")
        exit(1)
    
    # Test Edge TPU functionality (requires pycoral)
    try:
        from pycoral.utils import edgetpu
        devices = edgetpu.list_edge_tpus()
        if devices:
            print(f"✓ Edge TPU devices detected: {len(devices)}")
            for i, device in enumerate(devices):
                print(f"  Device {i}: {device}")
        else:
            print("! No Edge TPU devices currently available")
            print("  (This is normal if hardware was just connected)")
    except ImportError:
        print("! PyCoral not available - install with: sudo apt-get install python3-pycoral")
    except Exception as e:
        print(f"! Edge TPU detection error: {e}")
    
    print("Runtime verification completed")
    
except Exception as e:
    print(f"Verification failed: {e}")
    exit(1)
EOF
        
        if python3 "$test_script"; then
            log_success "Python runtime verification passed"
        else
            log_warning "Python runtime verification had issues"
            log_info "This may be normal if PyCoral packages are not yet installed"
        fi
        
        rm -f "$test_script"
    else
        log_info "Skipping hardware-specific tests (no Coral hardware detected)"
        log_info "Connect Coral hardware and re-run verification to test device detection"
    fi
}

# Post-installation setup
post_installation_setup() {
    print_section "Post-Installation Setup"
    
    # Add user to plugdev group (for USB device access)
    local current_user=$(whoami)
    if groups "$current_user" | grep -q "plugdev"; then
        log_info "User $current_user already in plugdev group"
    else
        log_info "Adding user $current_user to plugdev group for USB device access..."
        sudo usermod -a -G plugdev "$current_user"
        log_success "User added to plugdev group"
        log_warning "You may need to log out and back in for group changes to take effect"
    fi
    
    # Create udev rules for Coral devices (if not present)
    local udev_rules="/etc/udev/rules.d/99-edgetpu-accelerator.rules"
    if [[ ! -f "$udev_rules" ]]; then
        log_info "Creating udev rules for Coral devices..."
        sudo tee "$udev_rules" > /dev/null << 'EOF'
# Google Coral Edge TPU USB Accelerator
SUBSYSTEM=="usb", ATTRS{idVendor}=="1a6e", ATTRS{idProduct}=="089a", TAG+="uaccess"
SUBSYSTEM=="usb", ATTRS{idVendor}=="18d1", ATTRS{idProduct}=="9302", TAG+="uaccess"
EOF
        sudo udevadm control --reload-rules
        sudo udevadm trigger
        log_success "Udev rules created and activated"
    else
        log_info "Udev rules already exist"
    fi
    
    # Provide next steps
    echo
    log_info "Runtime installation completed successfully!"
    echo
    echo "Next steps:"
    echo "1. Install PyCoral packages: sudo apt-get install python3-pycoral"
    echo "2. Connect your Coral device (if not already connected)"
    echo "3. Test with: python3 -c \"from pycoral.utils import edgetpu; print(edgetpu.list_edge_tpus())\""
    echo
    if [[ "$HARDWARE_PRESENT" != true ]]; then
        echo "Note: No Coral hardware was detected during installation."
        echo "The runtime is ready and will automatically detect devices when connected."
    fi
}

# Cleanup on exit
cleanup() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        log_error "Installation failed with exit code $exit_code"
        echo
        echo "Troubleshooting steps:"
        echo "1. Check internet connectivity"
        echo "2. Ensure system is up to date: sudo apt-get update && sudo apt-get upgrade"
        echo "3. Check installation log: $LOG_FILE"
        echo "4. Refer to official documentation: https://coral.ai/docs/accelerator/get-started/"
    fi
    
    # Clean up temporary files
    [[ -f /tmp/coral_test_*.py ]] && rm -f /tmp/coral_test_*.py
}

trap cleanup EXIT

# Main installation function
main() {
    print_header
    
    # Check if running as root
    if [[ $EUID -eq 0 && "$ALLOW_ROOT" != true ]]; then
        log_error "This script should not be run directly as root"
        log_info "It will request sudo permissions when needed"
        log_info "Use --allow-root flag for CI/Docker environments"
        exit 1
    fi
    
    if [[ $EUID -eq 0 && "$ALLOW_ROOT" == true ]]; then
        log_warning "Running as root with --allow-root flag"
        log_warning "This should only be used in CI/Docker environments"
    fi
    
    # Perform installation steps
    detect_platform
    detect_coral_hardware
    configure_coral_repository
    select_performance_mode
    install_runtime
    verify_installation
    post_installation_setup
    
    log_success "Coral Edge TPU runtime installation completed successfully!"
    
    # Log final status
    echo
    echo "Installation Summary:"
    echo "- Platform: $(uname -m) $(grep PRETTY_NAME /etc/os-release 2>/dev/null | cut -d'"' -f2 || echo "Unknown")"
    echo "- Runtime: $([[ "$PERFORMANCE_MODE" == "maximum" ]] && echo "libedgetpu1-max" || echo "libedgetpu1-std")"
    echo "- Hardware: $([[ "$HARDWARE_PRESENT" == true ]] && echo "Detected" || echo "Not currently detected")"
    echo "- Log file: $LOG_FILE"
    echo
}

# Support for being called from other scripts
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    # Running as standalone script
    main "$@"
else
    # Being sourced by another script
    log_info "Coral runtime installer loaded as library"
fi
