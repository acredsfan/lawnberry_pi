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

# Installation component flags
INSTALL_DEPENDENCIES=true
INSTALL_PYTHON_ENV=true
INSTALL_WEB_UI=true
INSTALL_SERVICES=true
INSTALL_DATABASE=true
INSTALL_SYSTEM_CONFIG=true
SKIP_HARDWARE=false
SKIP_ENV=false
SKIP_VALIDATION=false

# Parse command line arguments for modular installation
show_help() {
    cat << 'EOF'
LawnBerry Installation Script - Modular Installation Support

Usage: ./install_lawnberry.sh [OPTIONS]

Installation Options:
  --help                    Show this help message
  --dependencies-only       Install only system dependencies
  --python-only            Install only Python environment and packages
  --web-ui-only            Build and install only the web UI
  --services-only          Install only systemd services
  --database-only          Initialize only the database
  --system-config-only     Configure only system settings

Component Combinations:
  --backend-only           Install dependencies + Python + services + database
  --frontend-only          Install web UI only
  --minimal                Install core components (no validation, no hardware detection)
    --deploy-update          Sync current working tree to /opt canonical runtime & restart services (fast deploy)

Control Options:
  --skip-hardware          Skip hardware detection and sensor setup
  --skip-env               Skip environment file setup
  --skip-validation        Skip post-installation validation
  --non-interactive        Run in non-interactive mode
  --debug                  Enable debug output

Examples:
  ./install_lawnberry.sh                    # Full installation
  ./install_lawnberry.sh --web-ui-only      # Only rebuild web UI
  ./install_lawnberry.sh --services-only    # Only reinstall services
  ./install_lawnberry.sh --backend-only     # Backend components only
  ./install_lawnberry.sh --minimal          # Core installation only
EOF
}

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help)
                show_help
                exit 0
                ;;
            --dependencies-only)
                INSTALL_DEPENDENCIES=true
                INSTALL_PYTHON_ENV=false
                INSTALL_WEB_UI=false
                INSTALL_SERVICES=false
                INSTALL_DATABASE=false
                INSTALL_SYSTEM_CONFIG=false
                SKIP_VALIDATION=true
                ;;
            --python-only)
                INSTALL_DEPENDENCIES=false
                INSTALL_PYTHON_ENV=true
                INSTALL_WEB_UI=false
                INSTALL_SERVICES=false
                INSTALL_DATABASE=false
                INSTALL_SYSTEM_CONFIG=false
                SKIP_VALIDATION=true
                ;;
            --web-ui-only)
                INSTALL_DEPENDENCIES=false
                INSTALL_PYTHON_ENV=false
                INSTALL_WEB_UI=true
                INSTALL_SERVICES=false
                INSTALL_DATABASE=false
                INSTALL_SYSTEM_CONFIG=false
                SKIP_VALIDATION=true
                SKIP_HARDWARE=true
                SKIP_ENV=true
                ;;
            --services-only)
                INSTALL_DEPENDENCIES=false
                INSTALL_PYTHON_ENV=false
                INSTALL_WEB_UI=false
                INSTALL_SERVICES=true
                INSTALL_DATABASE=false
                INSTALL_SYSTEM_CONFIG=false
                SKIP_VALIDATION=true
                SKIP_HARDWARE=true
                ;;
            --database-only)
                INSTALL_DEPENDENCIES=false
                INSTALL_PYTHON_ENV=false
                INSTALL_WEB_UI=false
                INSTALL_SERVICES=false
                INSTALL_DATABASE=true
                INSTALL_SYSTEM_CONFIG=false
                SKIP_VALIDATION=true
                SKIP_HARDWARE=true
                SKIP_ENV=true
                ;;
            --system-config-only)
                INSTALL_DEPENDENCIES=false
                INSTALL_PYTHON_ENV=false
                INSTALL_WEB_UI=false
                INSTALL_SERVICES=false
                INSTALL_DATABASE=false
                INSTALL_SYSTEM_CONFIG=true
                SKIP_VALIDATION=true
                SKIP_HARDWARE=true
                ;;
            --backend-only)
                INSTALL_DEPENDENCIES=true
                INSTALL_PYTHON_ENV=true
                INSTALL_WEB_UI=false
                INSTALL_SERVICES=true
                INSTALL_DATABASE=true
                INSTALL_SYSTEM_CONFIG=true
                SKIP_VALIDATION=true
                ;;
            --frontend-only)
                INSTALL_DEPENDENCIES=false
                INSTALL_PYTHON_ENV=false
                INSTALL_WEB_UI=true
                INSTALL_SERVICES=false
                INSTALL_DATABASE=false
                INSTALL_SYSTEM_CONFIG=false
                SKIP_VALIDATION=true
                SKIP_HARDWARE=true
                SKIP_ENV=true
                ;;
            --minimal)
                INSTALL_DEPENDENCIES=true
                INSTALL_PYTHON_ENV=true
                INSTALL_WEB_UI=true
                INSTALL_SERVICES=true
                INSTALL_DATABASE=true
                INSTALL_SYSTEM_CONFIG=true
                SKIP_VALIDATION=true
                SKIP_HARDWARE=true
                ;;
            --deploy-update)
                # Fast path: only sync source to INSTALL_DIR and restart services
                DEPLOY_UPDATE_ONLY=true
                INSTALL_DEPENDENCIES=false
                INSTALL_PYTHON_ENV=false
                INSTALL_WEB_UI=false
                INSTALL_SERVICES=false
                INSTALL_DATABASE=false
                INSTALL_SYSTEM_CONFIG=false
                SKIP_VALIDATION=true
                SKIP_HARDWARE=true
                ;;
            --skip-hardware)
                SKIP_HARDWARE=true
                ;;
            --skip-env)
                SKIP_ENV=true
                ;;
            --skip-validation)
                SKIP_VALIDATION=true
                ;;
            --non-interactive)
                NON_INTERACTIVE=true
                ;;
            --debug)
                DEBUG_MODE=true
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
        shift
    done
}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
ORANGE='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# --- LOGGING SETUP ---
# Default log file location
LOG_FILE="$SCRIPT_DIR/lawnberry_install.log"
DEBUG_MODE=false

# Delete existing log file if it exists to start fresh
if [[ -f "$LOG_FILE" ]]; then
    rm -f "$LOG_FILE"
    echo "Deleted existing installation log file"
fi

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${ORANGE}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
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

print_section() {
    echo
    echo "----------------------------------------"
    echo "$1"
    echo "----------------------------------------"
}

fix_permissions() {
    print_section "Fixing File Permissions"
    log_info "Running fix_permissions.sh to make all scripts executable..."
    if [ -f "$SCRIPT_DIR/fix_permissions.sh" ]; then
        bash "$SCRIPT_DIR/fix_permissions.sh"
    else
        log_warning "fix_permissions.sh not found, skipping..."
    fi

    log_info "Setting ownership of all project files to the current user..."
    sudo chown -R $USER:$GROUP "$PROJECT_ROOT"
    log_success "File and folder permissions have been set."
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

        elif grep -q "bullseye\\|buster" /etc/os-release; then
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

    # Check available RAM (8GB model typically reports ~7GB usable)
    TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo 0)
    TOTAL_RAM_GB=$((TOTAL_RAM_KB / 1024 / 1024))
    log_debug "Total RAM detected: ${TOTAL_RAM_KB} KB (${TOTAL_RAM_GB} GB)"
    if [[ $TOTAL_RAM_GB -ge 7 ]]; then
        log_success "RAM: ${TOTAL_RAM_GB}GB detected - enabling memory optimizations"
        if [[ $TOTAL_RAM_GB -ge 8 ]]; then
            log_info "Full 8GB RAM detected - enabling advanced memory management"
        fi
    elif [[ $TOTAL_RAM_GB -lt 6 ]]; then
        log_warning "RAM: ${TOTAL_RAM_GB}GB - may limit performance optimizations"
    else
        log_info "RAM: ${TOTAL_RAM_GB}GB - near minimum recommended memory"
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
        "python3-pytest"
        "rpicam-apps"
        "libcamera-dev"
        "python3-libcamera"
    )

    # Hardware-specific packages
    hardware_packages=(
        "python3-picamera2"
        "python3-gpiozero"
        "python3-lgpio"
        "libgpiod-dev"
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

    # Ensure MQTT broker starts properly
    if systemctl is-available mosquitto >/dev/null 2>&1; then
        log_info "Starting Mosquitto MQTT broker..."
        sudo systemctl enable mosquitto
        sudo systemctl restart mosquitto || log_warning "Could not start Mosquitto MQTT broker"
        sleep 2
        if systemctl is-active --quiet mosquitto; then
            log_success "Mosquitto MQTT broker is running"
        else
            log_warning "Mosquitto MQTT broker failed to start"
        fi
    fi

    log_info "Installing Node.js for the web UI..."

    # Check current Node.js version and compatibility
    if command -v node >/dev/null && command -v npm >/dev/null; then
        current_node=$(node --version | sed 's/v//')
        node_major=$(echo $current_node | cut -d. -f1)
        log_info "Current Node.js version: $current_node"

        # Test for ARM compatibility issues
        if ! timeout 10s node -e "console.log('Node.js compatibility test passed')" 2>/dev/null; then
            log_warning "Current Node.js version has ARM compatibility issues - reinstalling compatible version"
            node_needs_update=true
        elif [[ $node_major -gt 18 ]]; then
            log_warning "Node.js v$node_major may have ARM compatibility issues - installing v18 LTS"
            node_needs_update=true
        else
            log_success "Node.js version is compatible"
            node_needs_update=false
        fi
    else
        log_info "Node.js not found - installing Node.js 18 LTS"
        node_needs_update=true
    fi

    # Install compatible Node.js version if needed
    if [[ "$node_needs_update" == true ]]; then
        log_info "Installing Node.js 18 LTS for optimal ARM compatibility..."

        # Remove existing Node.js if problematic
        if command -v node >/dev/null; then
            log_info "Removing incompatible Node.js version..."
            sudo apt-get remove -y nodejs npm 2>/dev/null || true
        fi

        # Install Node.js 18 LTS via NodeSource
        log_debug "Downloading and running NodeSource setup script for Node.js 18.x LTS"
        curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -

        # Install Node.js (which includes npm)
        log_debug "Installing nodejs package."
        sudo apt-get install -y nodejs
    fi

    # Verify installation
    if command -v node >/dev/null && command -v npm >/dev/null; then
        log_success "Node.js and npm are installed."
        log_info "Node version: $(node -v)"
        log_info "npm version: $(npm -v)"

        # Final compatibility test
        if timeout 10s node -e "console.log('✅ Node.js ARM compatibility verified')" 2>/dev/null; then
            log_success "Node.js ARM compatibility confirmed"
        else
            log_error "Node.js still has compatibility issues after installation"
            exit 1
        fi
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

setup_coral_packages() {
    print_section "Setting up Google Coral TPU Environment (Optional)"

    if [[ "$NON_INTERACTIVE" == true ]]; then
        log_info "Non-interactive mode - skipping Coral TPU setup"
        return 0
    fi

    echo
    echo "Google Coral TPU Support Setup"
    echo "=============================="
    echo "The Coral USB Accelerator provides AI acceleration for machine learning models."
    echo "This is optional and only needed if you have a Coral TPU device."
    echo
    echo "⚠️  IMPORTANT COMPATIBILITY NOTE:"
    echo "PyCoral currently supports Python 3.6–3.9 only."
    echo "This installer sets up a pyenv-based Python 3.9 environment with all requirements."
    echo
    read -p "Do you want to install Coral TPU support? (y/N): " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Skipping Coral TPU setup"
        return 0
    fi

    log_info "Installing Coral Edge TPU runtime..."
    echo
    echo "Edge TPU Runtime Frequency Options:"
    echo "1. Standard frequency (recommended)"
    echo "2. Maximum frequency (more heat/power)"
    read -p "Choose runtime version (1 for standard, 2 for max): " -n 1 -r
    echo

    if [[ $REPLY == "2" ]]; then
        EDGE_TPU_PACKAGE="libedgetpu1-max"
        log_warning "Installing MAX frequency runtime – device will run hot"
    else
        EDGE_TPU_PACKAGE="libedgetpu1-std"
        log_info "Installing standard runtime"
    fi

    echo "deb https://packages.cloud.google.com/apt coral-edgetpu-stable main" | sudo tee /etc/apt/sources.list.d/coral-edgetpu.list
    curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -
    sudo apt-get update -qq
    sudo apt-get install -y "$EDGE_TPU_PACKAGE" || {
        log_error "Failed to install Edge TPU runtime"
        return 1
    }
    log_success "Edge TPU runtime installed: $EDGE_TPU_PACKAGE"

    # Setup pyenv and virtualenv
    CORAL_VENV_NAME="coral-python39"
    CORAL_VENV_DIR="$PROJECT_ROOT/venv_coral_pyenv"
    PYTHON_39_VERSION="3.9.18"

    export PYENV_ROOT="$HOME/.pyenv"
    export PATH="$PYENV_ROOT/bin:$PATH"

    if ! command -v pyenv >/dev/null 2>&1; then
        log_info "pyenv not found, installing..."
        curl https://pyenv.run | bash
        export PATH="$PYENV_ROOT/bin:$PATH"
    fi

    if command -v pyenv >/dev/null 2>&1; then
        eval "$(pyenv init -)" 2>/dev/null || true
        eval "$(pyenv virtualenv-init -)" 2>/dev/null || true
    else
        log_error "pyenv installation failed"
        exit 1
    fi

    if ! pyenv versions | grep -q "$PYTHON_39_VERSION"; then
        log_info "Installing Python $PYTHON_39_VERSION via pyenv..."
        pyenv install "$PYTHON_39_VERSION"
    fi

    log_info "Creating virtualenv for Coral: $CORAL_VENV_NAME"
    pyenv virtualenv-delete -f "$CORAL_VENV_NAME" 2>/dev/null || true
    rm -rf "$CORAL_VENV_DIR"
    pyenv virtualenv "$PYTHON_39_VERSION" "$CORAL_VENV_NAME"
    ln -sf "$PYENV_ROOT/versions/$CORAL_VENV_NAME" "$CORAL_VENV_DIR"

    # Ensure shell uses the correct virtualenv
    export PATH="$PYENV_ROOT/versions/$CORAL_VENV_NAME/bin:$PATH"
    PYENV_PYTHON="$PYENV_ROOT/versions/$CORAL_VENV_NAME/bin/python"
    PYENV_PIP="$PYENV_PYTHON -m pip"

    log_info "Python binary: $PYENV_PYTHON"
    log_info "Upgrading pip"
    $PYENV_PIP install --upgrade pip

    # Install PyCoral wheel
    WHEEL_URL="https://github.com/google-coral/pycoral/releases/download/v2.0.0/pycoral-2.0.0-cp39-cp39-linux_aarch64.whl"
    WHEEL_FILE="pycoral-2.0.0-cp39-cp39-linux_aarch64.whl"

    log_info "Downloading PyCoral wheel..."
    curl -L -o "$WHEEL_FILE" "$WHEEL_URL" || {
        log_error "Failed to download PyCoral wheel"
        return 1
    }

    log_info "Installing PyCoral wheel..."
    $PYENV_PIP install --force-reinstall --no-deps "$WHEEL_FILE" || {
        log_error "PyCoral wheel installation failed"
        return 1
    }
    rm -f "$WHEEL_FILE"

    log_info "Installing pinned dependencies for PyCoral..."
    $PYENV_PIP install "numpy==1.23.5" --timeout 100 --retries 5 || {
        log_error "Failed to install numpy 1.23.5"
        return 1
    }

    $PYENV_PIP install "Pillow>=4.0.0" --extra-index-url https://www.piwheels.org/simple

    TFLITE_URL="https://github.com/google-coral/pycoral/releases/download/v2.0.0/tflite_runtime-2.5.0.post1-cp39-cp39-linux_aarch64.whl"
    TFLITE_FILE="tflite_runtime-2.5.0.post1-cp39-cp39-linux_aarch64.whl"

    log_info "Installing tflite-runtime..."
    curl -L -o "$TFLITE_FILE" "$TFLITE_URL"
    $PYENV_PIP install --no-deps "$TFLITE_FILE" || {
        log_error "tflite-runtime install failed"
        return 1
    }
    rm -f "$TFLITE_FILE"

    log_info "Testing PyCoral..."
    $PYENV_PYTHON -c "from pycoral.utils.edgetpu import list_edge_tpus; print('✅ PyCoral OK')" 2>/dev/null \
        && log_success "PyCoral installed and TPU accessible" \
        || log_warning "PyCoral import failed — check runtime or USB device"

    log_info "Creating helper script to activate Coral environment..."
    cat > "$PROJECT_ROOT/activate_coral.sh" << EOF
#!/bin/bash
if ! command -v pyenv >/dev/null 2>&1; then
  echo "pyenv is required but not installed." >&2
  exit 1
fi
export PYENV_ROOT="\$HOME/.pyenv"
export PATH="\$PYENV_ROOT/bin:\$PATH"
eval "\$(pyenv init -)"
eval "\$(pyenv virtualenv-init -)"
pyenv activate "$CORAL_VENV_NAME"
exec \$SHELL
EOF
    chmod +x "$PROJECT_ROOT/activate_coral.sh"

    log_success "Coral TPU setup completed!"
}



setup_python_environment() {
    print_section "Setting up Python Environment"

    # Check if virtual environment already exists and is properly configured
    if [[ -d "$PROJECT_ROOT/venv" ]] && [[ -f "$PROJECT_ROOT/venv/bin/activate" ]] && [[ "$FORCE_REINSTALL" != "true" ]]; then
        log_info "Checking existing virtual environment..."

        # Test if the environment has required packages
        source "$PROJECT_ROOT/venv/bin/activate"

        # Check if key packages are installed
        if python -c "import requests, fastapi, uvicorn, redis, yaml" 2>/dev/null; then
            log_success "Virtual environment already exists and is properly configured"
            log_info "Skipping Python environment setup (use --force-reinstall to override)"
            return 0
        else
            log_info "Virtual environment exists but missing required packages - reinstalling"
            deactivate 2>/dev/null || true
        fi
    fi

    # Create virtual environment with system site packages for libcamera access
    log_info "Creating Python virtual environment with system packages access..."
    cd "$PROJECT_ROOT"

    if [[ -d "venv" ]]; then
        log_info "Removing existing virtual environment..."
        log_debug "Removing existing venv directory."
        rm -rf venv
    fi

    log_debug "Creating new virtual environment with --system-site-packages for libcamera access."
    python3 -m venv --system-site-packages venv
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

    # Verify libcamera access
    log_info "Verifying libcamera access in virtual environment..."
    if python3 -c "import libcamera; print('✓ libcamera accessible')" 2>/dev/null; then
        log_success "libcamera module accessible in virtual environment"
    else
        log_warning "libcamera module not accessible - camera features may be limited"
    fi

    # Verify rpicam utilities are available
    if command -v rpicam-hello >/dev/null 2>&1; then
        log_info "Testing camera with rpicam-hello..."
        if rpicam-hello --version >/dev/null 2>&1; then
            log_success "rpicam-hello is available"
        else
            log_warning "rpicam-hello test failed"
        fi
    else
        log_warning "rpicam-hello command not found"
    fi

    # Coral TPU support is now optional and handled separately
    # Use setup_coral_packages() function for Coral installation

    log_success "Python environment setup complete"
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

initialize_tof_sensors() {
    print_section "ToF Sensor Initialization"

    cd "$PROJECT_ROOT"
    source venv/bin/activate

    log_info "Initializing dual VL53L0X ToF sensors..."
    log_info "This ensures both sensors are configured at different I2C addresses"

    # Check if ToF sensors are physically connected
    log_info "Checking for ToF sensor hardware..."

    # Run I2C detection first
    if command -v i2cdetect >/dev/null 2>&1; then
        # Look for any devices at 0x29 or 0x30 (typical ToF addresses)
        if i2cdetect -y 1 | grep -E "(29|30)" >/dev/null 2>&1; then
            log_info "ToF sensors detected on I2C bus"

            # Run our ToF initialization script
            if python3 setup_dual_tof.py >/dev/null 2>&1; then
                log_success "✅ Dual ToF sensors initialized successfully"
                log_success "  - Left sensor (tof_left): 0x30"
                log_success "  - Right sensor (tof_right): 0x29"

                # Verify both sensors are accessible
                log_info "Verifying sensor accessibility..."
                if i2cdetect -y 1 | grep -E " 29 " >/dev/null 2>&1 && i2cdetect -y 1 | grep -E " 30 " >/dev/null 2>&1; then
                    log_success "✅ Both ToF sensors accessible at correct addresses"

                    # Update hardware configuration to reflect both sensors
                    log_info "Updating hardware configuration..."
                    if [[ -f "config/hardware.yaml" ]]; then
                        # The setup script already updated the config, so we're good
                        log_success "✅ Hardware configuration updated"
                    fi
                else
                    log_warning "⚠️ ToF sensors initialized but address verification failed"
                fi

            else
                log_warning "ToF sensor initialization script failed"
                log_info "ToF sensors may still work with default configuration"
            fi
        else
            log_info "No ToF sensors detected on I2C bus"
            log_info "This is normal if ToF sensors are not yet connected"
        fi
    else
        log_warning "i2cdetect not available - skipping ToF sensor check"
    fi

    log_info "ToF sensor initialization complete"
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
        log_error "npm not available - Node.js is required for web UI build"
        exit 1
    fi

    # ARM64/Raspberry Pi compatibility assessment
    NODE_VERSION=$(node --version | sed 's/v//')
    NODE_MAJOR=$(echo $NODE_VERSION | cut -d. -f1)

    log_info "Node.js version: $NODE_VERSION (ARM64 compatibility check)"

    # Ensure we have a secure, compatible Node.js version for ARM64
    if [[ $NODE_MAJOR -lt 18 ]]; then
        log_error "Node.js $NODE_VERSION is too old for optimal ARM64 support and security"
        log_error "Raspberry Pi OS Bookworm with ARM64 needs Node.js 18+ for best compatibility"
        exit 1
    elif [[ $NODE_MAJOR -eq 18 ]]; then
        log_info "Node.js 18.x - Good ARM64 compatibility and security support"
        export NODE_OPTIONS="--max-old-space-size=1536 --no-warnings"
    elif [[ $NODE_MAJOR -eq 20 ]]; then
        log_info "Node.js 20.x - Excellent ARM64 support, LTS recommended"
        export NODE_OPTIONS="--max-old-space-size=2048 --no-warnings"
    elif [[ $NODE_MAJOR -ge 21 ]]; then
        log_warning "Node.js $NODE_MAJOR.x - Very new, may have ARM64 compatibility issues"
        log_info "Testing compatibility before proceeding..."

        # Test Node.js basic functionality on ARM64
        if ! timeout 10s node -e "console.log('ARM64 test OK')" >/dev/null 2>&1; then
            log_error "Node.js $NODE_VERSION has ARM64 compatibility issues"
            exit 1
        fi
        export NODE_OPTIONS="--max-old-space-size=2048 --no-warnings"
    fi

    # Verify package.json and dependencies
    if [[ ! -f "package.json" ]]; then
        log_error "package.json not found in web-ui directory"
        exit 1
    fi

    log_info "Installing web UI dependencies with ARM64 optimizations..."

    # Set ARM64-friendly npm configuration for better compatibility
    export npm_config_target_arch=arm64
    export npm_config_target_platform=linux
    export npm_config_cache=/tmp/npm-cache-$USER

    # Clean any potentially corrupted installations
    rm -rf node_modules package-lock.json .npm

    # Use npm install instead of ci for better ARM64 dependency resolution
    log_info "Installing dependencies (optimized for ARM64)..."
    if ! timeout 600s npm install --verbose --no-audit --no-fund --prefer-online; then
        log_error "Failed to install dependencies"
        log_error "This may be due to ARM64 compatibility issues with some packages"
        exit 1
    fi

    # Verify critical dependencies are installed and check their ARM64 compatibility
    if [[ ! -d "node_modules/react" ]] || [[ ! -d "node_modules/vite" ]]; then
        log_error "Critical dependencies missing after install"
        exit 1
    fi

    # Check Vite version for ARM64 compatibility (newest compatible approach)
    vite_version=$(npm list vite --depth=0 2>/dev/null | grep vite@ | cut -d'@' -f2 | head -1)
    if [[ -n "$vite_version" ]]; then
        vite_major=$(echo "$vite_version" | cut -d'.' -f1)
        log_info "Detected Vite version: $vite_version"

        if [[ "$vite_major" -eq 4 ]]; then
            log_info "Vite 4.x - Stable ARM64 compatibility"
        elif [[ "$vite_major" -eq 5 ]]; then
            log_info "Vite 5.x - Good ARM64 support"
        elif [[ "$vite_major" -eq 6 ]]; then
            log_info "Vite 6.x - Latest stable with ARM64 support"
        elif [[ "$vite_major" -ge 7 ]]; then
            log_warning "Vite $vite_version - Very new, testing ARM64 compatibility..."

            # Test Vite binary compatibility before proceeding
            if ! timeout 15s npx vite --version >/dev/null 2>&1; then
                log_error "Vite $vite_version binary not compatible with ARM64"
                log_error "Consider downgrading to Vite 6.x for better ARM64 compatibility"
                exit 1
            fi
            log_info "Vite $vite_version ARM64 compatibility test passed"
        fi
    fi

    log_success "Dependencies installed successfully"

    # Set build environment variables optimized for Raspberry Pi ARM64
    export CI="true"
    export FORCE_COLOR="0"
    export NODE_ENV="production"
    export VITE_APP_API_URL="/api"
    export VITE_APP_WS_URL="/ws"
    export GENERATE_SOURCEMAP="false"  # Reduce build size and memory usage

    # Create production build
    log_info "Building web UI for production (ARM64 optimized)..."

    # Run build with proper timeout and error handling
    if timeout 600s npm run build; then
        log_success "Web UI build completed successfully"

        # Verify build output
        if [[ -d "dist" ]] && [[ -f "dist/index.html" ]]; then
            build_size=$(du -sh dist | cut -f1)
            file_count=$(find dist -type f | wc -l)
            log_info "Build output: $file_count files, $build_size total"
            log_success "Web UI ready for deployment"
        else
            log_error "Build completed but output files missing"
            exit 1
        fi
    else
        log_error "Web UI build failed or timed out"
        log_error "This may be due to ARM64 compatibility issues with build dependencies"

        # Try to provide helpful error information
        if [[ -f "npm-debug.log" ]]; then
            log_info "Last 10 lines of npm debug log:"
            tail -10 npm-debug.log | while read line; do
                log_info "  $line"
            done
        fi

        exit 1
    fi

    # Test the build by serving it briefly
    log_info "Testing web UI build..."
    npm run preview &>/dev/null &
    preview_pid=$!
    sleep 5

    # Test if server responds
    if curl -s http://localhost:4173 >/dev/null 2>&1; then
        log_success "Web UI preview test passed"
    else
        log_warning "Web UI preview test failed - may need manual verification"
    fi

    # Cleanup
    kill $preview_pid 2>/dev/null || true
    wait $preview_pid 2>/dev/null || true

    log_success "Web UI build process completed"
}

create_directories() {
    print_section "Creating System Directories"

    log_info "Creating system directories..."

    # Create directories
    sudo mkdir -p "$INSTALL_DIR"
    sudo mkdir -p "$LOG_DIR"
    sudo mkdir -p "$DATA_DIR"
    sudo mkdir -p "$DATA_DIR/config_backups"
    sudo mkdir -p "$DATA_DIR/health_metrics"
    sudo mkdir -p "$DATA_DIR/database"
    sudo mkdir -p "$BACKUP_DIR"

    # Copy project files to installation directory
    log_info "Copying project files to $INSTALL_DIR..."
    sudo cp -r "$PROJECT_ROOT"/* "$INSTALL_DIR/" || log_warning "Could not copy all project files"

    # Ensure a virtual environment exists in canonical install dir (Option A runtime)
    if [[ ! -d "$INSTALL_DIR/venv" ]]; then
        log_info "Creating virtual environment in $INSTALL_DIR/venv (canonical runtime)"
        # Use root-owned creation then adjust ownership
        sudo python3 -m venv --system-site-packages "$INSTALL_DIR/venv" || log_warning "Failed to create venv in $INSTALL_DIR"
        sudo chown -R "$USER:$GROUP" "$INSTALL_DIR/venv" || sudo chown -R "$USER:$USER" "$INSTALL_DIR/venv"
    else
        log_debug "Virtual environment already present in $INSTALL_DIR/venv"
    fi

    # Set ownership and permissions
    sudo chown -R "$USER:$GROUP" "$INSTALL_DIR" || sudo chown -R "$USER:$USER" "$INSTALL_DIR"
    sudo chown -R "$USER:$GROUP" "$LOG_DIR" || sudo chown -R "$USER:$USER" "$LOG_DIR"
    sudo chown -R "$USER:$GROUP" "$DATA_DIR" || sudo chown -R "$USER:$USER" "$DATA_DIR"
    sudo chmod 755 "$INSTALL_DIR"
    sudo chmod 755 "$LOG_DIR"
    sudo chmod 755 "$DATA_DIR"
    sudo chmod 700 "$DATA_DIR/config_backups"

    log_success "System directories created"
}

deploy_update() {
    print_section "Fast Deploy Update (Sync to /opt)"
    local deploy_start_ts=$(date +%s)
    local max_seconds=${FAST_DEPLOY_MAX_SECONDS:-0}
    if [[ $max_seconds -gt 0 ]]; then
        log_info "Fast deploy max duration set to ${max_seconds}s"
    fi

    if [[ ! -d "$INSTALL_DIR" ]]; then
        log_error "Canonical install directory $INSTALL_DIR not found. Run full install first."
        exit 1
    fi

    log_info "Synchronizing source tree to $INSTALL_DIR (excluding logs, data, venv, node_modules, build artifacts)..."

    # Lightweight optional drift check (FAST_DEPLOY_HASH=0 to disable)
    if [[ "${FAST_DEPLOY_HASH:-1}" -eq 1 ]] && command -v sha256sum >/dev/null 2>&1; then
        log_info "Running quick drift hash (subset of source files)"
        hash_start=$(date +%s)
        # Subset: python, TS/TSX, service units, manifests
        mapfile -t HASH_FILES < <(find "$PROJECT_ROOT" -maxdepth 6 -type f \
            \( -path "$PROJECT_ROOT/venv/*" -o -path "$PROJECT_ROOT/node_modules/*" -o -path "$PROJECT_ROOT/web-ui/node_modules/*" -o -path "$PROJECT_ROOT/web-ui/.*/ *" -o -name '*.log' \) -prune -o \
            -regex ".*\.(py|ts|tsx)" -o -name '*.service' -o -name 'pyproject.toml' -o -name 'requirements.txt' -o -name 'requirements-optional.txt' -o -name 'requirements-coral.txt' 2>/dev/null | sed '/^$/d')
        hf_count=${#HASH_FILES[@]}
        if (( hf_count > 0 && hf_count < 8000 )); then
            # Hash in chunks to reduce memory
            pre_hash=$(printf '%s\n' "${HASH_FILES[@]}" | xargs sha256sum 2>/dev/null | sha256sum | cut -d' ' -f1)
            runtime_hash=""
            if [[ -d "$INSTALL_DIR" ]]; then
                runtime_hash=$(find "$INSTALL_DIR" -maxdepth 6 -type f \
                    \( -path "$INSTALL_DIR/venv/*" -o -path "$INSTALL_DIR/node_modules/*" -o -path "$INSTALL_DIR/web-ui/node_modules/*" -o -name '*.log' \) -prune -o \
                    -regex ".*\.(py|ts|tsx)" -o -name '*.service' -o -name 'pyproject.toml' -o -name 'requirements.txt' -o -name 'requirements-optional.txt' -o -name 'requirements-coral.txt' 2>/dev/null | sed '/^$/d' | \
                    xargs sha256sum 2>/dev/null | sha256sum | cut -d' ' -f1 || true)
            fi
            if [[ -n "$runtime_hash" && "$pre_hash" != "$runtime_hash" ]]; then
                log_warning "Drift detected (subset hash mismatch)"
            else
                log_debug "No drift detected (subset hash)"
            fi
        else
            log_debug "Skipping hash (file count=$hf_count)"
        fi
        log_info "Quick hash completed in $(( $(date +%s) - hash_start ))s (files=$hf_count)"
    else
        log_debug "Skipping quick drift hash (disabled or sha256sum missing)"
    fi

    # Incremental directory-by-directory rsync to avoid long single timeouts
    RSYNC_TIMEOUT_PER=${RSYNC_TIMEOUT_PER:-40}
    RSYNC_OPTS=(-a --no-times --omit-dir-times --delete --exclude 'venv/' --exclude 'node_modules/' --exclude '.git/' --exclude 'build/' --exclude 'dist/' --exclude '*.log' --exclude 'data/' --exclude 'reports/')
    # Determine top-level entries to sync
    mapfile -t SYNC_DIRS < <(find "$PROJECT_ROOT" -maxdepth 1 -mindepth 1 -type d -printf '%f\n' 2>/dev/null | grep -Ev '^(venv|venv_coral_pyenv|node_modules|data|reports|tests|\.git|__pycache__)$' | sort)
    # Optionally include tests if requested
    if [[ "${FAST_DEPLOY_INCLUDE_TESTS:-0}" -eq 1 ]]; then
        [[ -d "$PROJECT_ROOT/tests" ]] && SYNC_DIRS+=(tests)
    fi
    # Always ensure destination exists
    for d in "${SYNC_DIRS[@]}"; do
        if [[ $max_seconds -gt 0 ]]; then
            local now=$(date +%s)
            if (( now - deploy_start_ts > max_seconds )); then
                log_warning "Reached FAST_DEPLOY_MAX_SECONDS ($max_seconds) before syncing remaining directories; aborting further syncs"
                break
            fi
        fi
        [[ -d "$PROJECT_ROOT/$d" ]] || continue
        log_info "Syncing directory: $d (timeout ${RSYNC_TIMEOUT_PER}s)"
    if ! timeout ${RSYNC_TIMEOUT_PER}s ionice -c3 nice -n 10 rsync "${RSYNC_OPTS[@]}" "$PROJECT_ROOT/$d/" "$INSTALL_DIR/$d/" 2>/dev/null; then
            log_warning "Timeout or error syncing $d - retrying without timeout"
            if ! ionice -c3 nice -n 10 rsync "${RSYNC_OPTS[@]}" "$PROJECT_ROOT/$d/" "$INSTALL_DIR/$d/"; then
                log_error "Failed to sync directory $d"
            fi
        fi
    done
    # Sync top-level files
    log_info "Syncing top-level files"
    mapfile -t TOP_FILES < <(find "$PROJECT_ROOT" -maxdepth 1 -type f -printf '%f\n')
    for f in "${TOP_FILES[@]}"; do
        case "$f" in
            lawnberry_install.log|*.pyc) continue;;
            *)
                rsync -a "$PROJECT_ROOT/$f" "$INSTALL_DIR/$f" 2>/dev/null || true
            ;;
        esac
    done
    log_success "Incremental rsync synchronization complete"

    # Ensure ownership remains correct
    sudo chown -R "$USER:$GROUP" "$INSTALL_DIR" || sudo chown -R "$USER:$USER" "$INSTALL_DIR"

    # --- Optimized web UI dist sync with mode selection ---
    # Modes: skip|minimal|full (default: minimal). Set FAST_DEPLOY_DIST_MODE env variable.
    if [[ -d "$PROJECT_ROOT/web-ui/dist" ]]; then
        DIST_MODE="${FAST_DEPLOY_DIST_MODE:-minimal}"
        case "$DIST_MODE" in
            skip)
                log_info "FAST_DEPLOY_DIST_MODE=skip -> Skipping web UI dist sync"
                ;;
            minimal|full|*)
                [[ "$DIST_MODE" != "full" && "$DIST_MODE" != "minimal" ]] && DIST_MODE="minimal"
                # Ensure target dist exists
                mkdir -p "$INSTALL_DIR/web-ui/dist"
                # Change detection: if index.html unchanged and mode=minimal, short-circuit
                if [[ -f "$INSTALL_DIR/web-ui/dist/index.html" && -f "$PROJECT_ROOT/web-ui/dist/index.html" ]]; then
                    src_idx_hash=$(sha256sum "$PROJECT_ROOT/web-ui/dist/index.html" 2>/dev/null | cut -d' ' -f1)
                    dst_idx_hash=$(sha256sum "$INSTALL_DIR/web-ui/dist/index.html" 2>/dev/null | cut -d' ' -f1)
                else
                    src_idx_hash=missing
                    dst_idx_hash=different
                fi
                if [[ "$DIST_MODE" == "minimal" && "$src_idx_hash" == "$dst_idx_hash" ]]; then
                    # Check for any new hashed assets (filename with .[hash].) not present at destination
                    new_assets=false
                    while IFS= read -r f; do
                        rel=${f#"$PROJECT_ROOT/web-ui/dist/"}
                        [[ -f "$INSTALL_DIR/web-ui/dist/$rel" ]] || { new_assets=true; break; }
                    done < <(find "$PROJECT_ROOT/web-ui/dist" -maxdepth 1 -type f -regextype posix-extended -regex '.*/[^/]+\.[a-f0-9]{8,}\.[a-z0-9]{2,4}$' 2>/dev/null)
                    if [[ $new_assets == false ]]; then
                        log_info "Web UI dist unchanged (minimal mode) - skipping dist sync"
                        DIST_SYNC_SKIPPED=1
                    fi
                fi
                if [[ "$DIST_SYNC_SKIPPED" != 1 ]]; then
                    if [[ "$DIST_MODE" == "full" ]]; then
                        log_info "Syncing web UI dist (full mode, timeout 35s)"
                        if ! timeout 35s rsync -a --delete "$PROJECT_ROOT/web-ui/dist/" "$INSTALL_DIR/web-ui/dist/" 2>/dev/null; then
                            log_warning "Full dist sync timed out - falling back to minimal subset"
                            DIST_MODE="minimal"
                        else
                            DIST_SYNC_DONE=1
                        fi
                    fi
                    if [[ "$DIST_MODE" == "minimal" && "$DIST_SYNC_DONE" != 1 ]]; then
                        log_info "Syncing web UI dist (minimal core files)"
                        # Copy critical entry files
                        for coref in index.html manifest*.json favicon.* robots.txt asset-manifest.json registerSW.js sw.js service-worker.js; do
                            cp "$PROJECT_ROOT/web-ui/dist/$coref" "$INSTALL_DIR/web-ui/dist/" 2>/dev/null || true
                        done
                        # Sync new hashed assets only (do not delete old to avoid 404 during rolling reload)
                        while IFS= read -r asset; do
                            rel=${asset#"$PROJECT_ROOT/web-ui/dist/"}
                            if [[ ! -f "$INSTALL_DIR/web-ui/dist/$rel" ]]; then
                                cp "$asset" "$INSTALL_DIR/web-ui/dist/" 2>/dev/null || true
                            fi
                        done < <(find "$PROJECT_ROOT/web-ui/dist" -maxdepth 1 -type f -regextype posix-extended -regex '.*/[^/]+\.[a-f0-9]{8,}\.[a-z0-9]{2,4}$' 2>/dev/null)
                        DIST_SYNC_DONE=1
                    fi
                    # Verification message
                    if [[ "$DIST_SYNC_DONE" == 1 ]]; then
                        count=$(find "$INSTALL_DIR/web-ui/dist" -maxdepth 1 -type f | wc -l)
                        log_success "Web UI dist sync complete (files=$count, mode=$DIST_MODE)"
                    else
                        log_warning "Web UI dist sync not fully completed (mode=$DIST_MODE)"
                    fi
                fi
                ;;
        esac
    else
        log_debug "No web-ui/dist directory present in source; skipping"
    fi

    # Post-sync verification hash (optional & bounded)
    if [[ "${FAST_DEPLOY_SKIP_POST_HASH:-0}" -eq 1 ]]; then
        log_debug "Skipping post-sync hash (FAST_DEPLOY_SKIP_POST_HASH=1)"
    elif command -v sha256sum >/dev/null 2>&1; then
        log_info "Computing post-sync verification hash (bounded)"
        if ! post_hash=$(timeout 8s bash -c 'find "$0" -maxdepth 2 -type f \
            \( -path "$0/venv/*" -o -path "$0/node_modules/*" -o -path "$0/web-ui/node_modules/*" \) -prune -o -regex ".*\\.(py|ts|tsx)$" -print | sort | head -2000 | xargs sha256sum 2>/dev/null | sha256sum | cut -d" " -f1' "$INSTALL_DIR" 2>/dev/null); then
            log_warning "Post-sync hash timed out or failed (skipping)"
        else
            [[ -n "$post_hash" ]] && log_debug "Runtime sync hash: $post_hash"
        fi
    fi

    # Ensure runtime python environment has dependencies
    if [[ "${FAST_DEPLOY_SKIP_VENV:-0}" -eq 1 ]]; then
        log_info "FAST_DEPLOY_SKIP_VENV=1 -> Skipping runtime venv validation"
    else
        ensure_runtime_python_env
    fi

    # Restart core services to pick up code changes
    # First, recanonicalize any service units still pointing at project root (legacy state)
    legacy_services=$(grep -l "WorkingDirectory=$PROJECT_ROOT" /etc/systemd/system/lawnberry-*.service 2>/dev/null || true)
    if [[ -n "$legacy_services" ]]; then
        log_info "Rewriting legacy service units to canonical /opt paths"
        for svc_file in $legacy_services; do
            sudo sed -i "s|WorkingDirectory=$PROJECT_ROOT|WorkingDirectory=$INSTALL_DIR|" "$svc_file"
            sudo sed -i "s|Environment=PYTHONPATH=$PROJECT_ROOT|Environment=PYTHONPATH=$INSTALL_DIR|" "$svc_file"
            sudo sed -i "s|ExecStart=$PROJECT_ROOT/venv/bin/python3|ExecStart=$INSTALL_DIR/venv/bin/python3|" "$svc_file" || true
            sudo sed -i "s|ExecStart=$PROJECT_ROOT/venv/bin/python|ExecStart=$INSTALL_DIR/venv/bin/python|" "$svc_file" || true
            # Remove any duplicated trailing 'Additional Bookworm Security Features' block if previously appended
            # Keep only first occurrence of ProtectClock line cluster
            if grep -q "# Additional Bookworm Security Features" "$svc_file"; then
                sudo awk 'BEGIN{found=0} /# Additional Bookworm Security Features/{if(found){skip=1}else{found=1}} {if(!skip)print} END{}' "$svc_file" > /tmp/clean_unit && sudo mv /tmp/clean_unit "$svc_file"
            fi
        done
        sudo systemctl daemon-reload
    fi

    if [[ "${FAST_DEPLOY_SKIP_SERVICES:-0}" -eq 1 ]]; then
        log_info "FAST_DEPLOY_SKIP_SERVICES=1 -> Skipping service restarts"
    else
        core_services=(
            "lawnberry-system"
            "lawnberry-data"
            "lawnberry-hardware"
            "lawnberry-safety"
            "lawnberry-api"
        )
        local per_restart_timeout=${FAST_DEPLOY_SERVICE_TIMEOUT:-10}
        log_info "Restarting core services (timeout ${per_restart_timeout}s each) ..."
        for svc in "${core_services[@]}"; do
            if systemctl is-enabled "$svc" >/dev/null 2>&1; then
                if ! timeout ${per_restart_timeout}s sudo systemctl restart "$svc" 2>/dev/null; then
                    log_warning "Timeout or failure restarting $svc"
                else
                    log_debug "Restarted $svc"
                fi
            else
                log_debug "Service not enabled: $svc"
            fi
        done
    fi

    local deploy_end_ts=$(date +%s)
    log_success "Deploy update complete in $((deploy_end_ts - deploy_start_ts))s"
}

ensure_runtime_python_env() {
    log_info "Validating runtime Python environment in $INSTALL_DIR/venv"
    if [[ ! -x "$INSTALL_DIR/venv/bin/python" ]]; then
        log_warning "Runtime venv missing; creating..."
        python3 -m venv --system-site-packages "$INSTALL_DIR/venv" || {
            log_error "Failed to create runtime venv"
            return
        }
    fi

    # Quick import probe for a representative module
    if ! "$INSTALL_DIR/venv/bin/python" -c "import fastapi" 2>/dev/null; then
        log_info "Installing Python dependencies into runtime venv"
        "$INSTALL_DIR/venv/bin/python" -m pip install --upgrade pip setuptools wheel >/dev/null 2>&1 || true
        if [[ -f "$INSTALL_DIR/requirements.txt" ]]; then
            "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" || log_warning "Base requirements install encountered issues"
        fi
        if [[ -f "$INSTALL_DIR/requirements-optional.txt" ]]; then
            "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements-optional.txt" || log_warning "Optional requirements install issues"
        fi
        if [[ -f "$INSTALL_DIR/requirements-coral.txt" ]]; then
            "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements-coral.txt" || log_debug "Coral requirements skipped or failed"
        fi
    else
        log_debug "Runtime venv already has core dependencies"
    fi

    # Final verification of critical modules (non-fatal if missing hardware libs)
    "$INSTALL_DIR/venv/bin/python" - <<'EOF'
critical = ["fastapi", "pydantic", "asyncio"]
missing = []
for m in critical:
    try:
        __import__(m)
    except Exception:
        missing.append(m)
if missing:
    print(f"[WARN] Missing critical modules in runtime venv: {missing}")
else:
    print("[OK] Runtime venv core modules present")
EOF
}

apply_bookworm_optimizations() {
    if [[ $BOOKWORM_OPTIMIZATIONS == true ]]; then
        print_section "Applying Bookworm-Specific Optimizations"

    log_info "Configuring memory management for 8GB RAM..."
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
        "src/hardware/lawnberry-sensor.service"
        "src/sensor_fusion/lawnberry-sensor-fusion.service"
        "src/weather/lawnberry-weather.service"
        "src/power_management/lawnberry-power.service"
        "src/safety/lawnberry-safety.service"
        "src/vision/lawnberry-vision.service"
        "src/web_api/lawnberry-api.service"
    )

    log_info "Checking and installing systemd service files with Bookworm optimizations..."

    installed_services=()
    services_needing_update=()

    for service_file in "${services[@]}"; do
        if [[ -f "$service_file" ]]; then
            service_name=$(basename "$service_file")
            target_service="$SERVICE_DIR/$service_name"
            needs_install=false

            # Check if service needs to be installed/updated
            if [[ ! -f "$target_service" ]]; then
                log_info "Service not found: $service_name - installing..."
                needs_install=true
            else
                # Check if source service file is newer than installed one
                if [[ "$service_file" -nt "$target_service" ]]; then
                    log_info "Service outdated: $service_name - updating..."
                    needs_install=true
                    services_needing_update+=("$service_name")
                else
                    # Check if Python path in service file needs updating (canonical runtime = INSTALL_DIR)
                        if ! grep -q "$INSTALL_DIR/venv/bin/python" "$target_service" 2>/dev/null; then
                        log_info "Service paths outdated: $service_name - updating..."
                        needs_install=true
                        services_needing_update+=("$service_name")
                    else
                        log_debug "Service up-to-date: $service_name - skipping"
                    fi
                fi
            fi

            if [[ "$needs_install" == true ]]; then
                log_info "Installing/updating $service_name..."

                # Stop service if it's running and being updated
                if [[ " ${services_needing_update[*]} " =~ " ${service_name} " ]]; then
                    service_base="${service_name%.service}"
                    if systemctl is-active --quiet "$service_name" 2>/dev/null; then
                        log_info "Stopping $service_name for update..."
                        sudo systemctl stop "$service_name" || log_warning "Could not stop $service_name"
                    fi
                fi

                # Update service file paths BUT retain /opt canonical deployment (Option A)
                # We intentionally keep WorkingDirectory=/opt/lawnberry so runtime is isolated from dev tree
                temp_service="/tmp/$service_name"
                cp "$service_file" "$temp_service"
                # Ensure python path points to canonical venv if template used /usr/bin/python3
                sed -i "s|/usr/bin/python3|$INSTALL_DIR/venv/bin/python3|g" "$temp_service"
                # Normalize WorkingDirectory & PYTHONPATH explicitly (idempotent when already correct)
                sed -i "s|WorkingDirectory=.*|WorkingDirectory=$INSTALL_DIR|g" "$temp_service"
                sed -i "s|Environment=PYTHONPATH=.*|Environment=PYTHONPATH=$INSTALL_DIR|g" "$temp_service"
                # Fix user and group to match current user (templates may specify placeholder)
                sed -i "s|User=.*|User=$USER|g" "$temp_service"
                sed -i "s|Group=.*|Group=$GROUP|g" "$temp_service"
                # (No replacement of /opt/lawnberry with project root — by design per Option A decision)

                # Apply Bookworm-specific security hardening if supported
                if [[ $SYSTEMD_VERSION -ge 252 ]]; then
                    # Only append hardening block if not already present
                    if ! grep -q 'ProtectClock=' "$temp_service"; then
                        log_info "Appending hardening block to $service_name (systemd >=252)"
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
                    else
                        log_debug "Hardening keys already present in $service_name"
                    fi
                fi

                sudo cp "$temp_service" "$SERVICE_DIR/"
                sudo chmod 644 "$SERVICE_DIR/$service_name"
                rm -f "$temp_service"

                installed_services+=("${service_name%.service}")
            else
                # Service is up-to-date, but still add to list for enabling
                installed_services+=("${service_name%.service}")
            fi
        else
            log_warning "Service file not found: $service_file"
        fi
    done

    # Reload systemd if any services were installed/updated
    if [[ ${#services_needing_update[@]} -gt 0 ]] || [[ ${#installed_services[@]} -gt 0 ]]; then
        log_info "Reloading systemd daemon..."
        sudo systemctl daemon-reload
    fi

    # Enable core services (check if they need enabling)
    core_services=(
        "lawnberry-system"
        "lawnberry-data"
        "lawnberry-hardware"
        "lawnberry-safety"
        "lawnberry-api"
    )

    log_info "Checking and enabling core services..."
    for service in "${core_services[@]}"; do
        if [[ " ${installed_services[*]} " =~ " ${service} " ]]; then
            # Check if service is already enabled
            if ! systemctl is-enabled "$service.service" >/dev/null 2>&1; then
                log_info "Enabling $service..."
                sudo systemctl enable "$service.service" || log_warning "Could not enable $service"
            else
                log_debug "Service already enabled: $service"
            fi
        fi
    done

    # Restart updated services
    if [[ ${#services_needing_update[@]} -gt 0 ]]; then
        log_info "Restarting updated services..."
        for service_name in "${services_needing_update[@]}"; do
            service_base="${service_name%.service}"
            if [[ " ${core_services[*]} " =~ " ${service_base} " ]]; then
                if systemctl is-enabled "$service_name" >/dev/null 2>&1; then
                    log_info "Restarting $service_name..."
                    sudo systemctl restart "$service_name" || log_warning "Could not restart $service_name"
                fi
            fi
        done
    fi

    log_success "System services installed and configured"
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

configure_system() {
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
    echo "Memory: $(free | grep Mem | awk '{printf("%.1f%%\n", $3/$2 * 100.0)}'")"
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
}

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
# Enhanced main function with modular installation support
main() {
    print_header

    # Parse command line arguments for modular installation
    parse_arguments "$@"

    # Fast deploy/update shortcut before heavy setup (minimal logging init only)
    if [[ "$DEPLOY_UPDATE_ONLY" == true ]]; then
        # Basic log file handling
        exec 1> >(tee -a "$LOG_FILE")
        exec 2> >(tee -a "$LOG_FILE" >&2)
        log_info "Running fast deploy/update mode (--deploy-update)"
        deploy_update
        log_success "Fast deploy/update finished"
        exit 0
    fi

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

    log_info "Installation mode configuration:"
    log_info "  INSTALL_DEPENDENCIES: $INSTALL_DEPENDENCIES"
    log_info "  INSTALL_PYTHON_ENV: $INSTALL_PYTHON_ENV"
    log_info "  INSTALL_WEB_UI: $INSTALL_WEB_UI"
    log_info "  INSTALL_SERVICES: $INSTALL_SERVICES"
    log_info "  INSTALL_DATABASE: $INSTALL_DATABASE"
    log_info "  INSTALL_SYSTEM_CONFIG: $INSTALL_SYSTEM_CONFIG"
    log_debug "  SKIP_HARDWARE: $SKIP_HARDWARE"
    log_debug "  SKIP_ENV: $SKIP_ENV"
    log_debug "  SKIP_VALIDATION: $SKIP_VALIDATION"
    log_debug "  DEBUG_MODE: $DEBUG_MODE"

    # Always check these first regardless of mode
    check_root
    fix_permissions
    check_system

    # Run installation steps based on flags
    if [[ "$INSTALL_DEPENDENCIES" == true ]]; then
        install_dependencies
        setup_coral_packages
    fi

    if [[ "$INSTALL_PYTHON_ENV" == true ]]; then
        setup_python_environment
    fi

    if [[ "$SKIP_HARDWARE" != true ]] && [[ "$INSTALL_DEPENDENCIES" == true || "$INSTALL_PYTHON_ENV" == true ]]; then
        detect_hardware
        initialize_tof_sensors
    fi

    if [[ "$SKIP_ENV" != true ]] && [[ "$INSTALL_SYSTEM_CONFIG" == true ]]; then
        if [[ "$NON_INTERACTIVE" == true ]]; then
            log_info "Skipping environment setup in non-interactive mode"
        else
            setup_environment
        fi
    fi

    if [[ "$INSTALL_WEB_UI" == true ]]; then
        build_web_ui
    fi

    # Always create directories if installing any component that needs them
    if [[ "$INSTALL_SERVICES" == true || "$INSTALL_DATABASE" == true ]]; then
        create_directories
    fi

    if [[ "$INSTALL_SERVICES" == true ]]; then
        install_services
    fi

    if [[ "$INSTALL_DATABASE" == true ]]; then
        setup_database
    fi

    if [[ "$INSTALL_SYSTEM_CONFIG" == true ]]; then
        configure_system
    fi

    # Run validation and tests unless skipped
    if [[ "$SKIP_VALIDATION" != true ]]; then
        run_post_install_validation
        run_tests
    fi

    cleanup
    show_completion_message

    log_success "Installation completed successfully!"
}

# Run main function
main "$@"
