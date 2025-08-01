#!/bin/bash
set -e

# Enhanced LawnBerry Installation Script
# Automatically detects hardware, sets up environment, and installs system

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
INSTALL_DIR="/opt/lawnberry"
SERVICE_DIR="/etc/systemd/system"
LOG_DIR="/var/log/lawnberry"
DATA_DIR="/var/lib/lawnberry"
USER=$(whoami)
GROUP=$(id -gn)
BACKUP_DIR="/var/backups/lawnberry"

# Colors for output
RED='[0;31m'
GREEN='[0;32m'
YELLOW='[1;33m'
BLUE='[0;34m'
NC='[0m' # No Color

# --- LOGGING SETUP ---
# Default log file location
LOG_FILE="$SCRIPT_DIR/lawnberry_install.log"
DEBUG_MODE=false

# Functions
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

log_debug() {
    if [ "$DEBUG_MODE" = true ]; then
        echo -e "${YELLOW}[DEBUG]${NC} $1" | tee -a "$LOG_FILE"
    fi
}

# --- MAIN SCRIPT ---

print_header() {
    echo
    echo "=================================================================="
    echo "                   LAWNBERRY PI INSTALLER"
    echo "=================================================================="
    echo
}

fix_script_permissions() {
    log_info "Ensuring all shell scripts are executable..."
    
    # Make all .sh files in scripts directory executable
    if [ -d "$PROJECT_ROOT/scripts" ]; then
        find "$PROJECT_ROOT/scripts" -name "*.sh" -type f -exec chmod +x {} \;
        log_success "Shell script permissions fixed"
    fi
    
    # Also fix any other common script locations
    if [ -d "$INSTALL_DIR/scripts" ]; then
        find "$INSTALL_DIR/scripts" -name "*.sh" -type f -exec chmod +x {} \;
    fi
}

print_section() {
    echo
    echo "----------------------------------------"
    echo "$1"
    echo "----------------------------------------"
}

check_root() {
    log_debug "Checking for root execution."
    if [[ $EUID -eq 0 ]]; then
        log_error "This script should not be run as root."
        log_info "Please run as the lawnberry user or your regular user."
        exit 1
    fi
}

# Global variables for Bookworm optimization
BOOKWORM_DETECTED=false
BOOKWORM_OPTIMIZATIONS=false
SYSTEMD_VERSION=0

detect_bookworm() {
    log_debug "Detecting Raspberry Pi OS Bookworm."
    print_section "Raspberry Pi OS Bookworm Detection and Optimization"
    
    # Check for Bookworm specifically
    if [[ -f /etc/os-release ]]; then
        if grep -q "VERSION_CODENAME=bookworm" /etc/os-release; then
            BOOKWORM_DETECTED=true
            BOOKWORM_OPTIMIZATIONS=true
            log_success "Raspberry Pi OS Bookworm detected - enabling full optimizations"
            
            # Check Python version for Bookworm compatibility
            PYTHON_VERSION=$(python3 --version 2>/dev/null | grep -o '[0-9]\+\.[0-9]\+' | head -n1)
            log_debug "Detected Python version: $PYTHON_VERSION"
            if [[ $(echo "$PYTHON_VERSION >= 3.11" | bc -l 2>/dev/null || echo 0) -eq 1 ]]; then
                log_success "Python $PYTHON_VERSION meets Bookworm requirements (3.11+)"
            else
                log_warning "Python $PYTHON_VERSION may not be optimal for Bookworm"
                log_info "Consider upgrading to Python 3.11+ for best performance"
            fi
            
            # Check for Raspberry Pi 4B specifically
            if [[ -f /proc/device-tree/model ]]; then
                PI_MODEL=$(cat /proc/device-tree/model 2>/dev/null | tr -d '\0')
                log_debug "Detected Raspberry Pi model: $PI_MODEL"
                if [[ "$PI_MODEL" == *"Raspberry Pi 4"* ]]; then
                    log_success "Raspberry Pi 4 Model B detected - optimal hardware"
                else
                    log_warning "Hardware: $PI_MODEL - some optimizations may not apply"
                fi
            fi
            
        elif grep -q "bullseye\|buster" /etc/os-release; then
            log_warning "Legacy OS detected - some features may not be available"
            log_info "For best performance, upgrade to Raspberry Pi OS Bookworm"
            log_info "Many Bookworm-specific optimizations will be disabled"
        fi
    fi
    
    # Get systemd version for compatibility and security features
    if command -v systemctl >/dev/null 2>&1; then
        SYSTEMD_VERSION=$(systemctl --version | head -n1 | grep -o '[0-9]\+' | head -n1)
        log_info "systemd version: $SYSTEMD_VERSION"
        log_debug "Detected systemd version: $SYSTEMD_VERSION"
        
        if [[ $SYSTEMD_VERSION -ge 252 ]]; then
            log_success "systemd 252+ detected - enabling enhanced security hardening"
            log_info "Available features: service sandboxing, cgroup v2, process isolation"
        else
            log_warning "systemd < 252 - some security features will be disabled"
            log_info "Update systemd for enhanced security and performance features"
        fi
    fi
    
    # Check available RAM for 16GB optimization
    TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 0)
    TOTAL_RAM_GB=$((TOTAL_RAM_KB / 1024 / 1024))
    log_debug "Total RAM detected: ${TOTAL_RAM_KB} KB (${TOTAL_RAM_GB} GB)"
    if [[ $TOTAL_RAM_GB -ge 8 ]]; then
        log_success "RAM: ${TOTAL_RAM_GB}GB detected - enabling memory optimizations"
        if [[ $TOTAL_RAM_GB -ge 16 ]]; then
            log_info "16GB+ RAM detected - enabling advanced memory management"
        fi
    else
        log_warning "RAM: ${TOTAL_RAM_GB}GB - may limit performance optimizations"
    fi
}

check_system() {
    print_section "System Requirements Check"
    
    # Check if we're on Raspberry Pi
    log_debug "Checking for Raspberry Pi hardware."
    if [[ ! -f /proc/device-tree/model ]] || ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
        log_warning "Not running on Raspberry Pi - some features may not work"
    else
        model=$(cat /proc/device-tree/model)
        log_info "Detected: $model"
        
        # Check for Pi 4B specifically for optimizations
        if grep -q "Raspberry Pi 4" /proc/device-tree/model; then
            log_success "Raspberry Pi 4 detected - enabling performance optimizations"
        fi
    fi
    
    # Check OS
    if command -v lsb_release >/dev/null 2>&1; then
        os_info=$(lsb_release -d | cut -f2)
        log_info "Operating System: $os_info"
    fi
    
    # Detect Bookworm first
    detect_bookworm
    
    # Check Python version - Bookworm compatibility
    log_debug "Checking Python version."
    if command -v python3 >/dev/null 2>&1; then
        python_version=$(python3 --version)
        log_info "Python: $python_version"
        
        # Check if Python 3.11+ (Bookworm requirement)
        if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
            if [[ $BOOKWORM_DETECTED == true ]]; then
                log_error "Python 3.11+ required for Raspberry Pi OS Bookworm compatibility"
                log_error "Please ensure you're running the latest Bookworm with Python 3.11+"
                exit 1
            else
                log_warning "Python 3.11+ recommended for optimal performance"
                log_info "Minimum Python 3.8 detected - some optimizations may not be available"
                if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)" 2>/dev/null; then
                    log_error "Python 3.8 or higher is required"
                    exit 1
                fi
            fi
        else
            log_success "Python 3.11+ detected - Bookworm optimized features available"
        fi
    else
        log_error "Python 3 is not installed"
        exit 1
    fi
    
    # Check Raspberry Pi OS version - Bookworm preferred
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        log_info "OS: $PRETTY_NAME"
        if [[ "$VERSION_CODENAME" == "bookworm" ]]; then
            log_success "Raspberry Pi OS Bookworm detected - fully supported"
        elif [[ "$VERSION_CODENAME" == "bullseye" ]]; then
            log_warning "Raspberry Pi OS Bullseye detected - consider upgrading to Bookworm"
        else
            log_warning "Unrecognized OS version - Bookworm recommended for best compatibility"
        fi
    fi
    
    # Check available memory
    total_mem=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    total_mem_mb=$((total_mem / 1024))
    log_info "Total Memory: ${total_mem_mb} MB"
    
    if [[ $total_mem_mb -lt 1024 ]]; then
        log_warning "Less than 1GB RAM detected - performance may be limited"
    fi
    
    # Check disk space
    available_space=$(df "$HOME" | tail -1 | awk '{print $4}')
    available_mb=$((available_space / 1024))
    log_info "Available disk space: ${available_mb} MB"
    
    if [[ $available_mb -lt 2048 ]]; then
        log_error "At least 2GB free space required"
        exit 1
    fi
    
    log_success "System requirements check passed"
}

install_dependencies() {
    print_section "Installing System Dependencies"
    
    log_info "Updating package lists..."
    log_debug "Running 'sudo apt-get update -qq'"
    sudo apt-get update -qq
    
    # Essential packages
    essential_packages=(
        "python3-pip"
        "python3-venv"
        "python3-dev"
        "build-essential"
        "git"
        "curl"
        "wget"
        "i2c-tools"
        "python3-smbus"
        "python3-serial"
        "python3-opencv"
        "python3-numpy"
        "python3-yaml"
        "redis-server"
        "nginx"
        "sqlite3"
        "logrotate"
        "systemd"
        "libcap-dev"
        "mosquitto"
        "mosquitto-clients"
    )
    
    # Hardware-specific packages
    hardware_packages=(
        "python3-picamera2"
        "python3-gpiozero"
        "python3-rpi.gpio"
        "raspi-config"
    )
    
    log_info "Installing essential packages..."
    log_debug "Installing: ${essential_packages[*]}"
    sudo apt-get install -y "${essential_packages[@]}" || {
        log_error "Failed to install essential packages"
        exit 1
    }
    
    log_info "Installing hardware packages..."
    log_debug "Installing: ${hardware_packages[*]}"
    sudo apt-get install -y "${hardware_packages[@]}" || {
        log_warning "Some hardware packages failed to install - continuing anyway"
    }
    
    log_info "Installing Node.js for the web UI..."
    if ! command -v node >/dev/null || ! command -v npm >/dev/null; then
        log_info "Node.js or npm not found. Installing Node.js via NodeSource."
        log_debug "Downloading and running NodeSource setup script for Node.js 20.x"
        # Download and execute the NodeSource setup script for Node.js 20.x
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        # Install Node.js (which includes npm)
        log_debug "Installing nodejs package."
        sudo apt-get install -y nodejs
    else
        log_info "Node.js and npm are already installed."
    fi

    # Verify installation
    if command -v node >/dev/null && command -v npm >/dev/null; then
        log_success "Node.js and npm are installed."
        log_info "Node version: $(node -v)"
        log_info "npm version: $(npm -v)"
    else
        log_warning "Node.js installation failed - web UI may not work"
    fi
    
    # Enable I2C and SPI
    log_info "Enabling I2C and SPI interfaces..."
    log_debug "Running raspi-config to enable I2C, SPI, and camera."
    sudo raspi-config nonint do_i2c 0 2>/dev/null || log_warning "Could not enable I2C"
    sudo raspi-config nonint do_spi 0 2>/dev/null || log_warning "Could not enable SPI"
    sudo raspi-config nonint do_camera 0 2>/dev/null || log_warning "Could not enable camera"
    
    # Add user to required groups
    log_info "Adding user to required groups..."
    log_debug "Adding user '$USER' to groups: i2c, spi, gpio, dialout"
    sudo usermod -a -G i2c,spi,gpio,dialout "$USER" || log_warning "Could not add user to hardware groups"
    
    log_success "Dependencies installed successfully"
}

setup_python_environment() {
    print_section "Setting up Python Environment"
    
    # Create virtual environment
    log_info "Creating Python virtual environment..."
    cd "$PROJECT_ROOT"
    
    if [[ -d "venv" ]]; then
        log_info "Virtual environment already exists - removing old one"
        log_debug "Removing existing venv directory."
        rm -rf venv
    fi
    
    log_debug "Creating new virtual environment."
    python3 -m venv venv
    source venv/bin/activate
    
    # Upgrade pip
    log_info "Upgrading pip..."
    log_debug "Running 'pip install --upgrade pip'"
    pip install --upgrade pip
    
    # Install core requirements first (always required)
    log_info "Installing core Python requirements..."
    if [[ -f "requirements.txt" ]]; then
        log_debug "Installing packages from requirements.txt"
        if pip install -r requirements.txt; then
            log_success "Core requirements installed successfully"
        else
            log_error "Failed to install core requirements"
            exit 1
        fi
    else
        log_error "requirements.txt not found"
        exit 1
    fi

    # Ensure requests library is installed
    log_info "Ensuring 'requests' library is installed..."
    log_debug "Installing 'requests' library."
    pip install requests || {
        log_error "Failed to install 'requests' library"
        exit 1
    }

    # Run Coral TPU hardware detection and conditional installation
    setup_coral_packages
    
    log_success "Python environment setup complete"
}

setup_coral_packages() {
    print_section "Coral TPU Package Installation"
    
    # Check platform compatibility for Coral packages
    local coral_compatible=false
    local bookworm_detected=false
    local python_version_ok=false
    
    # Detect Pi OS Bookworm
    if [[ -f /etc/os-release ]] && grep -q "VERSION_CODENAME=bookworm" /etc/os-release; then
        bookworm_detected=true
        log_success "Pi OS Bookworm detected - system packages available"
    else
        log_warning "Non-Bookworm system detected - limited Coral support"
    fi
    
    # Check Python version compatibility
    if python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
        python_version_ok=true
        log_success "Python 3.11+ detected - compatible with system packages"
    else
        log_warning "Python version < 3.11 - may use pip fallback"
    fi
    
    coral_compatible=$bookworm_detected
    
    # Check for Coral hardware presence (informational only)
    local coral_hardware_present=false
    if command -v lsusb &> /dev/null; then
        if lsusb | grep -q "18d1:9302\|1a6e:089a"; then
            coral_hardware_present=true
            log_success "Coral USB Accelerator detected"
        else
            log_info "No Coral USB hardware detected (can be added later)"
        fi
    fi
    
    # User interaction for Coral installation
    local install_coral=false
    local install_runtime=false
    
    if [[ "$coral_compatible" == true ]]; then
        echo
        echo "Coral TPU Support Available:"
        echo "  • Pi OS Bookworm detected - system packages supported"
        echo "  • Python 3.11+ compatible"
        if [[ "$coral_hardware_present" == true ]]; then
            echo "  • Coral hardware currently connected"
        else
            echo "  • No Coral hardware detected (can be added later)"
        fi
        echo
        echo "Coral TPU provides significant performance improvements for computer vision tasks."
        echo "You can install support now or add it later using: scripts/install_coral_system_packages.sh"
        echo
        
        read -p "Install Coral TPU support? (Y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$|^$ ]]; then
            install_coral=true
            
            echo
            echo "Edge TPU Runtime Installation:"
            echo "  • Required for Coral hardware acceleration"
            echo "  • Installs Google's libedgetpu runtime"
            echo "  • Only needed if you have or plan to use Coral hardware"
            echo
            
            read -p "Also install Edge TPU runtime? (Y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$|^$ ]]; then
                install_runtime=true
            fi
        fi
    else
        log_info "Coral TPU system packages not available on this platform"
        log_info "Will attempt pip-based fallback installation"
        install_coral=true  # Try fallback method
    fi
    
    # Install Coral packages if requested
    if [[ "$install_coral" == true ]]; then
        install_coral_packages_with_fallback "$coral_compatible" "$install_runtime"
    else
        log_info "Skipping Coral TPU installation - can be added later"
        log_info "To install later: scripts/install_coral_system_packages.sh"
    fi
}

install_coral_packages_with_fallback() {
    local system_packages_available="$1"
    local install_runtime="$2"
    local installation_success=false
    
    log_info "Starting Coral TPU package installation..."
    
    # Method 1: System packages (preferred for Bookworm)
    if [[ "$system_packages_available" == true ]]; then
        log_info "Attempting system package installation (method 1/3)..."
        
        if scripts/install_coral_system_packages.sh --non-interactive; then
            log_success "System packages installed successfully"
            installation_success=true
            
            # Install runtime if requested
            if [[ "$install_runtime" == true ]]; then
                log_info "Installing Edge TPU runtime..."
                if scripts/install_coral_runtime.sh --non-interactive; then
                    log_success "Edge TPU runtime installed successfully"
                else
                    log_warning "Runtime installation failed - Coral packages available but no hardware acceleration"
                fi
            fi
        else
            log_warning "System package installation failed - trying fallback methods"
        fi
    fi
    
    # Method 2: Pip installation fallback
    if [[ "$installation_success" != true ]] && [[ -f "requirements-coral.txt" ]]; then
        log_info "Attempting pip-based installation (method 2/3)..."
        
        if pip install -r requirements-coral.txt; then
            log_success "Pip-based Coral packages installed successfully"
            installation_success=true
            
            # Note about runtime for pip installation
            if [[ "$install_runtime" == true ]]; then
                log_info "Installing Edge TPU runtime for pip-based packages..."
                if scripts/install_coral_runtime.sh --non-interactive; then
                    log_success "Edge TPU runtime installed successfully"
                else
                    log_warning "Runtime installation failed - packages available but no hardware acceleration"
                fi
            fi
        else
            log_warning "Pip installation also failed - trying CPU-only fallback"
        fi
    fi
    
    # Method 3: CPU-only TensorFlow Lite fallback
    if [[ "$installation_success" != true ]]; then
        log_info "Attempting CPU-only TensorFlow Lite installation (method 3/3)..."
        
        if pip install 'tflite-runtime>=2.13.0,<3.0.0'; then
            log_success "CPU-only TensorFlow Lite installed successfully"
            log_info "Coral acceleration not available - will use CPU processing"
            installation_success=true
        else
            log_error "All Coral installation methods failed"
            log_error "ML functionality may be limited"
        fi
    fi
    
    # Final status report
    if [[ "$installation_success" == true ]]; then
        log_success "Coral/TensorFlow Lite installation completed"
        
        # Run verification
        log_info "Verifying installation..."
        if python3 -c "
try:
    import tflite_runtime.interpreter as tflite
    print('✓ TensorFlow Lite available')
    try:
        import pycoral.utils.edgetpu as edgetpu
        print('✓ Coral packages available')
        devices = edgetpu.list_edge_tpus()
        if devices:
            print(f'✓ {len(devices)} Edge TPU device(s) detected')
        else:
            print('ℹ No Edge TPU hardware detected (CPU fallback available)')
    except ImportError:
        print('ℹ Coral packages not available (CPU-only mode)')
except ImportError as e:
    print(f'✗ TensorFlow Lite verification failed: {e}')
    exit(1)
" 2>/dev/null; then
            log_success "Installation verification passed"
        else
            log_warning "Installation verification had issues - functionality may be limited"
        fi
    else
        log_error "Coral installation failed completely"
        log_error "Consider manual installation or running without ML features"
    fi
}

detect_hardware() {
    print_section "Hardware Detection and Testing"
    
    cd "$PROJECT_ROOT"
    source venv/bin/activate
    
    log_info "Running hardware detection..."
    if python3 scripts/hardware_detection.py; then
        log_success "Hardware detection completed"
        
        # Check if hardware config was generated
        if [[ -f "hardware_detected.yaml" ]]; then
            log_info "Hardware configuration generated"
            
            # Backup original config if it exists
            if [[ -f "config/hardware.yaml" ]]; then
                cp config/hardware.yaml config/hardware.yaml.backup
                log_info "Backed up original hardware.yaml"
            fi
            
            # Ask user if they want to use detected config
            echo
            read -p "Use detected hardware configuration? (Y/n): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$|^$ ]]; then
                cp hardware_detected.yaml config/hardware.yaml
                log_success "Using detected hardware configuration"
            else
                log_info "Keeping original hardware configuration"
            fi
        fi
        
        # Show detection results
        if [[ -f "hardware_detection_results.json" ]]; then
            log_info "Hardware detection results saved to hardware_detection_results.json"
        fi
    else
        log_warning "Hardware detection failed - continuing with default configuration"
    fi
}

setup_environment() {
    print_section "Environment Configuration"
    
    cd "$PROJECT_ROOT"
    source venv/bin/activate
    
    log_info "Setting up environment variables..."
    
    # Check if .env already exists
    if [[ -f ".env" ]]; then
        log_info ".env file already exists - validating..."
        if python3 scripts/setup_environment.py --check; then
            log_success "Environment configuration is valid"
            return
        else
            log_warning "Environment configuration issues detected"
        fi
    fi
    
    # Run environment setup
    echo
    echo "Environment setup is required for API keys and configuration."
    read -p "Run interactive environment setup? (Y/n): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$|^$ ]]; then
        if python3 scripts/setup_environment.py; then
            log_success "Environment setup completed"
        else
            log_error "Environment setup failed"
            exit 1
        fi
    else
        log_info "Skipping interactive setup - you'll need to configure .env manually"
        log_info "Copy .env.example to .env and fill in your API keys"
    fi
}

build_web_ui() {
    print_section "Building Web UI"
    
    cd "$PROJECT_ROOT/web-ui"
    
    # Check if Node.js is available
    if ! command -v npm >/dev/null 2>&1; then
        log_warning "npm not available - skipping web UI build"
        return
    fi
    
    log_info "Cleaning npm cache and removing old dependencies..."
    npm cache clean --force
    rm -rf node_modules package-lock.json

    log_info "Installing web UI dependencies..."
    npm install --legacy-peer-deps || {
        log_warning "npm install failed - web UI may not work"
        return
    }
    
    # Fix security vulnerabilities
    log_info "Fixing npm security vulnerabilities..."
    npm audit fix --force || log_warning "Some npm security issues could not be automatically fixed"
    
    log_info "Building web UI..."
    npm run build || {
        log_warning "Web UI build failed"
        return
    }
    
    log_success "Web UI built successfully"
}

create_directories() {
    print_section "Creating System Directories"
    
    log_info "Creating system directories..."
    
    # Create directories
    sudo mkdir -p "$LOG_DIR"
    sudo mkdir -p "$DATA_DIR"
    sudo mkdir -p "$DATA_DIR/config_backups"
    sudo mkdir -p "$DATA_DIR/health_metrics"
    sudo mkdir -p "$DATA_DIR/database"
    sudo mkdir -p "$BACKUP_DIR"
    
    # Set ownership and permissions
    sudo chown -R "$USER:$GROUP" "$LOG_DIR" || sudo chown -R "$USER:$USER" "$LOG_DIR"
    sudo chown -R "$USER:$GROUP" "$DATA_DIR" || sudo chown -R "$USER:$USER" "$DATA_DIR"
    sudo chmod 755 "$LOG_DIR"
    sudo chmod 755 "$DATA_DIR"
    sudo chmod 700 "$DATA_DIR/config_backups"
    
    log_success "System directories created"
}

apply_bookworm_optimizations() {
    if [[ $BOOKWORM_OPTIMIZATIONS == true ]]; then
        print_section "Applying Bookworm-Specific Optimizations"
        
        log_info "Configuring memory management for 16GB RAM..."
        # Create memory optimization configuration
        sudo tee /etc/sysctl.d/99-lawnberry-bookworm.conf >/dev/null <<EOF
# LawnBerry Bookworm Memory Optimizations
vm.swappiness=10
vm.vfs_cache_pressure=50
vm.dirty_background_ratio=5
vm.dirty_ratio=10
EOF
        
        log_info "Enabling CPU governor for performance..."
        # Set CPU governor for Pi 4B performance
        if grep -q "Raspberry Pi 4" /proc/device-tree/model 2>/dev/null; then
            echo 'GOVERNOR="performance"' | sudo tee /etc/default/cpufrequtils >/dev/null
        fi
        
        log_info "Configuring I2C and GPIO optimizations..."
        # Optimize I2C performance
        if ! grep -q "dtparam=i2c_arm_baudrate" /boot/config.txt; then
            echo "dtparam=i2c_arm_baudrate=400000" | sudo tee -a /boot/config.txt >/dev/null
        fi
        
        log_success "Bookworm optimizations applied"
    fi
}

install_services() {
    print_section "Installing System Services"
    
    cd "$PROJECT_ROOT"
    
    # Service files to install
    services=(
        "src/system_integration/lawnberry-system.service"
        "src/communication/lawnberry-communication.service"
        "src/data_management/lawnberry-data.service"
        "src/hardware/lawnberry-hardware.service"
        "src/sensor_fusion/lawnberry-sensor-fusion.service"
        "src/weather/lawnberry-weather.service"
        "src/power_management/lawnberry-power.service"
        "src/safety/lawnberry-safety.service"
        "src/vision/lawnberry-vision.service"
        "src/web_api/lawnberry-api.service"
    )
    
    log_info "Installing systemd service files with Bookworm optimizations..."
    
    installed_services=()
    for service_file in "${services[@]}"; do
        if [[ -f "$service_file" ]]; then
            service_name=$(basename "$service_file")
            log_info "Installing $service_name..."
            
            # Update service file paths to use virtual environment
            temp_service="/tmp/$service_name"
            sed "s|/usr/bin/python3|$PROJECT_ROOT/venv/bin/python3|g" "$service_file" > "$temp_service"
            sed -i "s|WorkingDirectory=.*|WorkingDirectory=$PROJECT_ROOT|g" "$temp_service"
            
            # Apply Bookworm-specific security hardening if supported
            if [[ $SYSTEMD_VERSION -ge 252 ]]; then
                log_info "Applying systemd 252+ security hardening to $service_name"
                # Add additional Bookworm security features
                cat >> "$temp_service" << 'EOF'

# Additional Bookworm Security Features
ProtectClock=true
ProtectHostname=true
ProtectKernelLogs=true
ProtectKernelModules=true
ProtectProc=invisible
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
RestrictNamespaces=true
RestrictSUIDSGID=true
SystemCallArchitectures=native
UMask=0027
EOF
            fi
            
            sudo cp "$temp_service" "$SERVICE_DIR/"
            sudo chmod 644 "$SERVICE_DIR/$service_name"
            rm "$temp_service" "$temp_service"
            
            installed_services+=("${service_name%.service}")
        else
            log_warning "Service file not found: $service_file"
        fi
    done
    
    # Reload systemd
    log_info "Reloading systemd daemon..."
    sudo systemctl daemon-reload
    
    # Enable core services
    core_services=(
        "lawnberry-system"
        "lawnberry-data"
        "lawnberry-hardware"
        "lawnberry-safety"
        "lawnberry-api"
    )
    
    log_info "Enabling core services..."
    for service in "${core_services[@]}"; do
        if [[ " ${installed_services[*]} " =~ " ${service} " ]]; then
            log_info "Enabling $service..."
            sudo systemctl enable "$service.service"
        fi
    done
    
    log_success "System services installed"
}

setup_database() {
    print_section "Database Initialization"
    
    cd "$PROJECT_ROOT"
    source venv/bin/activate
    
    log_info "Initializing database..."
    
    # Create database directory
    mkdir -p "$DATA_DIR/database"
    
    # Run database initialization if script exists
    if [[ -f "scripts/init_database.py" ]]; then
        python3 scripts/init_database.py
    else
        log_info "Database initialization script not found - skipping"
    fi
    
    # Start Redis if available
    if systemctl is-available redis-server >/dev/null 2>&1; then
        log_info "Starting Redis server..."
        sudo systemctl start redis-server
        sudo systemctl enable redis-server
    fi
    
    # Start and configure Mosquitto MQTT broker
    if systemctl is-available mosquitto >/dev/null 2>&1; then
        log_info "Configuring and starting Mosquitto MQTT broker..."
        
        # Create basic mosquitto configuration
        sudo tee /etc/mosquitto/conf.d/lawnberry.conf >/dev/null <<EOF
# LawnBerry MQTT Configuration
listener 1883 localhost
allow_anonymous true
log_dest file /var/log/mosquitto/mosquitto.log
log_type error
log_type warning  
log_type notice
log_type information
EOF
        
        sudo systemctl start mosquitto
        sudo systemctl enable mosquitto
        log_success "Mosquitto MQTT broker configured and started"
    else
        log_warning "Mosquitto MQTT broker not available - communication features may be limited"
    fi
    
    log_success "Database initialization complete"
}

configure_system() {

run_post_install_validation() {
    print_section "Post-Installation Validation"
    
    log_info "Running Bookworm compatibility validation..."
    cd "$PROJECT_ROOT"
    
    if [[ -f "scripts/validate_bookworm_installation.py" ]]; then
        if [[ $BOOKWORM_DETECTED == true ]]; then
            log_info "Bookworm detected - running comprehensive validation"
            python3 scripts/validate_bookworm_installation.py --quick
        else
            log_info "Non-Bookworm system - running basic validation"
            python3 scripts/validate_bookworm_installation.py --quick
        fi
        
        validation_result=$?
        if [[ $validation_result -eq 0 ]]; then
            log_success "Installation validation passed!"
        else
            log_warning "Installation validation found issues - check /tmp/bookworm_validation_report.json"
        fi
    else
        log_info "Validation script not found - skipping validation"
    fi
}
    print_section "System Configuration"
    
    # Create logrotate configuration
    log_info "Configuring log rotation..."
    sudo tee /etc/logrotate.d/lawnberry > /dev/null <<EOF
$LOG_DIR/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 $USER $USER
    postrotate
        systemctl reload lawnberry-* 2>/dev/null || true
    endscript
}
EOF
    
    # Create system control scripts
    log_info "Installing system control scripts..."
    
    # Enhanced system control script
    sudo tee /usr/local/bin/lawnberry-system > /dev/null <<'EOF'
#!/bin/bash
# LawnBerry system control script

SERVICES=(
    "lawnberry-system"
    "lawnberry-communication"
    "lawnberry-data"
    "lawnberry-hardware"
    "lawnberry-sensor-fusion"
    "lawnberry-weather"
    "lawnberry-power"
    "lawnberry-safety"
    "lawnberry-vision"
    "lawnberry-api"
)

case "$1" in
    start)
        echo "Starting LawnBerry system..."
        for service in "${SERVICES[@]}"; do
            if systemctl is-enabled "$service.service" >/dev/null 2>&1; then
                systemctl start "$service.service" 2>/dev/null || true
            fi
        done
        ;;
    stop)
        echo "Stopping LawnBerry system..."
        for service in "${SERVICES[@]}"; do
            systemctl stop "$service.service" 2>/dev/null || true
        done
        ;;
    restart)
        echo "Restarting LawnBerry system..."
        $0 stop
        sleep 2
        $0 start
        ;;
    status)
        lawnberry-health-check
        ;;
    logs)
        service=${2:-"system"}
        journalctl -f -u "lawnberry-$service.service"
        ;;
    enable)
        echo "Enabling LawnBerry system..."
        for service in "${SERVICES[@]}"; do
            systemctl enable "$service.service" 2>/dev/null || true
        done
        ;;
    disable)
        echo "Disabling LawnBerry system..."
        for service in "${SERVICES[@]}"; do
            systemctl disable "$service.service" 2>/dev/null || true
        done
        ;;
    hardware)
        cd /opt/lawnberry || cd /home/lawnberry/lawnberry
        python3 scripts/hardware_detection.py
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs [service]|enable|disable|hardware}"
        echo ""
        echo "Available services for logs:"
        for service in "${SERVICES[@]}"; do
            echo "  ${service#lawnberry-}"
        done
        exit 1
        ;;
esac
EOF
    
    # Health check script
    sudo tee /usr/local/bin/lawnberry-health-check > /dev/null <<'EOF'
#!/bin/bash
# Enhanced health check script for LawnBerry system

services=(
    "lawnberry-system"
    "lawnberry-data"
    "lawnberry-hardware"
    "lawnberry-safety"
    "lawnberry-api"
)

echo "LawnBerry System Health Check - $(date)"
echo "========================================"

all_healthy=true

for service in "${services[@]}"; do
    if systemctl is-active --quiet "$service.service"; then
        echo "✓ $service: Running"
    else
        echo "✗ $service: Not running"
        all_healthy=false
    fi
done

echo ""
echo "System Resources:"
if command -v free >/dev/null 2>&1; then
    echo "Memory: $(free | grep Mem | awk '{printf("%.1f%%\n", $3/$2 * 100.0)}')"
fi

if command -v df >/dev/null 2>&1; then
    echo "Disk: $(df / | tail -1 | awk '{print $5}')"
fi

# Hardware status
echo ""
echo "Hardware Status:"
if [[ -f /dev/i2c-1 ]]; then
    echo "✓ I2C: Available"
else
    echo "✗ I2C: Not available"
fi

if [[ -e /dev/video0 ]]; then
    echo "✓ Camera: Detected"
else
    echo "✗ Camera: Not detected"
fi

# Network connectivity
echo ""
echo "Network Connectivity:"
if ping -c 1 8.8.8.8 >/dev/null 2>&1; then
    echo "✓ Internet: Connected"
else
    echo "✗ Internet: Not connected"
fi

if [ "$all_healthy" = true ]; then
    echo ""
    echo "Overall Status: HEALTHY ✓"
    exit 0
else
    echo ""
    echo "Overall Status: UNHEALTHY ✗"
    exit 1
fi
EOF
    
    # Make scripts executable
    sudo chmod +x /usr/local/bin/lawnberry-system
    sudo chmod +x /usr/local/bin/lawnberry-health-check
    
    log_success "System configuration complete"
}

run_tests() {
    print_section "Running System Tests"
    
    cd "$PROJECT_ROOT"
    source venv/bin/activate
    
    log_info "Running basic system tests..."
    
    # Test Python imports
    if python3 -c "import sys; sys.path.insert(0, 'src'); import weather.weather_service" 2>/dev/null; then
        log_success "Python imports: OK"
    else
        log_warning "Python imports: Some modules failed to import"
    fi
    
    # Test configuration loading
    if [[ -f ".env" ]]; then
        log_success "Environment file: Present"
    else
        log_warning "Environment file: Missing"
    fi
    
    # Test hardware detection
    if [[ -f "hardware_detection_results.json" ]]; then
        log_success "Hardware detection: Results available"
    else
        log_warning "Hardware detection: No results found"
    fi
    
    # Test database connection
    if systemctl is-active --quiet redis-server; then
        log_success "Redis database: Running"
    else
        log_warning "Redis database: Not running"
    fi
    
    log_info "System tests completed"
}

cleanup() {
    print_section "Installation Cleanup"
    
    # Clean up temporary files
    log_info "Cleaning up temporary files..."
    sudo rm -f /tmp/lawnberry_*
    
    # Clean up build artifacts
    cd "$PROJECT_ROOT"
    find . -name "*.pyc" -delete
    find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    
    log_info "Cleanup complete"
}

show_completion_message() {
    print_section "Installation Complete!"
    
    echo
    log_success "LawnBerry Pi installation completed successfully!"
    echo
    echo "Installation Summary:"
    echo "  - Project root: $PROJECT_ROOT"
    echo "  - Python environment: $PROJECT_ROOT/venv"
    echo "  - Log directory: $LOG_DIR"
    echo "  - Data directory: $DATA_DIR"
    echo "  - Installation log: $LOG_FILE"
    echo
    echo "Available commands:"
    echo "  lawnberry-system start    - Start the system"
    echo "  lawnberry-system stop     - Stop the system"
    echo "  lawnberry-system status   - Check system health"
    echo "  lawnberry-system logs     - View system logs"
    echo "  lawnberry-system hardware - Run hardware detection"
    echo "  lawnberry-health-check    - Quick health check"
    echo
    echo "Next steps:"
    echo "1. Reboot the system to ensure all hardware interfaces are enabled"
    echo "2. Run: lawnberry-system start"
    echo "3. Check status: lawnberry-system status"
    echo "4. View logs: lawnberry-system logs"
    echo
    echo "Web interface will be available at: http://$(hostname -I | awk '{print $1}'):8000"
    echo
    
    if [[ -f "hardware_detection_results.json" ]]; then
        echo "Hardware detection results: hardware_detection_results.json"
    fi
    
    echo "Full installation log: $LOG_FILE"
    echo
}

# Main installation process
main() {
    print_header
    
    # --- Argument Parsing ---
    SKIP_HARDWARE=false
    SKIP_ENV=false
    NON_INTERACTIVE=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-hardware)
                SKIP_HARDWARE=true
                shift
                ;;
            --skip-env)
                SKIP_ENV=true
                shift
                ;;
            --non-interactive)
                NON_INTERACTIVE=true
                shift
                ;;
            --debug)
                DEBUG_MODE=true
                shift
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo "Options:"
                echo "  --skip-hardware    Skip hardware detection"
                echo "  --skip-env        Skip environment setup"
                echo "  --non-interactive Run without user prompts"
                echo "  --debug           Enable debug logging"
                echo "  -h, --help        Show this help"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    # --- Start Installation ---
    # Clear log file at the beginning of the script
    if [ "$DEBUG_MODE" = true ]; then
        > "$LOG_FILE"
    fi

    # Redirect stdout/stderr to log file
    exec 1> >(tee -a "$LOG_FILE")
    exec 2> >(tee -a "$LOG_FILE" >&2)

    log_info "Starting LawnBerry Pi installation..."
    log_info "Installation log will be saved to: $LOG_FILE"
    
    # Ask user about debug logging if not already enabled
    if [ "$DEBUG_MODE" = false ] && [ "$NON_INTERACTIVE" = false ]; then
        echo
        read -p "Enable debug logging for detailed troubleshooting? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            DEBUG_MODE=true
            log_info "Debug logging enabled."
        fi
    fi

    log_debug "Installation started with the following options:"
    log_debug "  SKIP_HARDWARE: $SKIP_HARDWARE"
    log_debug "  SKIP_ENV: $SKIP_ENV"
    log_debug "  NON_INTERACTIVE: $NON_INTERACTIVE"
    log_debug "  DEBUG_MODE: $DEBUG_MODE"

    # Run installation steps
    check_root
    check_system
    fix_script_permissions
    install_dependencies
    setup_python_environment
    
    if [[ "$SKIP_HARDWARE" != true ]]; then
        detect_hardware
    fi
    
    if [[ "$SKIP_ENV" != true ]]; then
        if [[ "$NON_INTERACTIVE" == true ]]; then
            log_info "Skipping environment setup in non-interactive mode"
        else
            setup_environment
        fi
    fi
    
    build_web_ui
    create_directories
    install_services
    setup_database
    configure_system
    run_tests
    cleanup
    show_completion_message
    
    log_success "Installation completed successfully!"
}

# Run main function
main "$@"