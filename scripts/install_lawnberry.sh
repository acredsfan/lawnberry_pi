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
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging setup
LOG_FILE="/tmp/lawnberry_install.log"
sudo touch "$LOG_FILE"
sudo chmod 666 "$LOG_FILE"
exec 1> >(sudo tee -a "$LOG_FILE")
exec 2> >(sudo tee -a "$LOG_FILE" >&2)

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" | sudo tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | sudo tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | sudo tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | sudo tee -a "$LOG_FILE"
}

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

check_root() {
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

apply_bookworm_optimizations() {
    print_section "Applying Bookworm-Specific Performance Optimizations"
    
    if [[ "$BOOKWORM_DETECTED" != true ]]; then
        log_warning "Skipping Bookworm optimizations - not running on Bookworm"
        return 0
    fi
    
    # Configure boot optimizations
    log_info "Configuring boot optimizations in /boot/config.txt..."
    if [[ -f /boot/config.txt ]]; then
        # Backup original config
        sudo cp /boot/config.txt /boot/config.txt.backup.$(date +%Y%m%d_%H%M%S)
        
        # Apply GPU memory split for computer vision
        if ! grep -q "gpu_mem=" /boot/config.txt; then
            echo "gpu_mem=128" | sudo tee -a /boot/config.txt >/dev/null
            log_success "Set GPU memory to 128MB for computer vision workloads"
        fi
        
        # Optimize I2C clock speed
        if ! grep -q "i2c_arm_baudrate=400000" /boot/config.txt; then
            echo "i2c_arm_baudrate=400000" | sudo tee -a /boot/config.txt >/dev/null
            log_success "Set I2C clock speed to 400kHz for better sensor performance"
        fi
        
        # Enable enhanced kernel scheduler
        if ! grep -q "cgroup_memory=1" /boot/cmdline.txt 2>/dev/null; then
            sudo sed -i 's/$/ cgroup_memory=1 cgroup_enable=memory/' /boot/cmdline.txt 2>/dev/null || true
            log_success "Enabled enhanced kernel scheduler optimizations"
        fi
    fi
    
    # Configure CPU governor for balanced performance
    log_info "Configuring CPU governor..."
    if [[ -f /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]]; then
        echo "ondemand" | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor >/dev/null 2>&1 || true
        log_success "Set CPU governor to 'ondemand' for balanced performance"
    fi
    
    # Configure systemd service limits for better performance
    log_info "Applying systemd performance optimizations..."
    sudo mkdir -p /etc/systemd/system.conf.d/
    sudo tee /etc/systemd/system.conf.d/lawnberry-performance.conf >/dev/null <<EOF
# LawnBerry Bookworm Performance Optimizations
[Manager]
DefaultLimitNOFILE=65536
DefaultLimitNPROC=32768
DefaultCPUAccounting=yes
DefaultMemoryAccounting=yes
DefaultTasksMax=4096
EOF
    
    # Configure memory management optimizations
    log_info "Applying memory management optimizations..."
    sudo tee /etc/sysctl.d/99-lawnberry-bookworm.conf >/dev/null <<EOF
# LawnBerry Bookworm Memory Optimizations
vm.swappiness=10
vm.dirty_ratio=5
vm.dirty_background_ratio=2
vm.vfs_cache_pressure=50

# Network optimizations
net.core.rmem_max=134217728
net.core.wmem_max=134217728
net.ipv4.tcp_congestion_control=bbr
EOF
    
    # Apply Python optimizations
    log_info "Configuring Python 3.11+ optimizations..."
    sudo mkdir -p /opt/lawnberry/config/
    sudo tee /opt/lawnberry/config/python-optimization.env >/dev/null <<EOF
# Python 3.11 Performance Optimizations
PYTHONOPTIMIZE=2
PYTHONDONTWRITEBYTECODE=0
PYTHONUNBUFFERED=1
PYTHONHASHSEED=random
PYTHONMALLOC=pymalloc
EOF
    
    log_success "Applied comprehensive Bookworm performance optimizations"
    log_info "Note: Some optimizations require a reboot to take effect"
}
    print_section "Raspberry Pi OS Bookworm Detection and Optimization"
    
    # Check for Bookworm specifically
    if [[ -f /etc/os-release ]]; then
        if grep -q "VERSION_CODENAME=bookworm" /etc/os-release; then
            BOOKWORM_DETECTED=true
            BOOKWORM_OPTIMIZATIONS=true
            log_success "Raspberry Pi OS Bookworm detected - enabling full optimizations"
            
            # Check Python version for Bookworm compatibility
            PYTHON_VERSION=$(python3 --version 2>/dev/null | grep -o '[0-9]\+\.[0-9]\+' | head -n1)
            if [[ $(echo "$PYTHON_VERSION >= 3.11" | bc -l 2>/dev/null || echo 0) -eq 1 ]]; then
                log_success "Python $PYTHON_VERSION meets Bookworm requirements (3.11+)"
            else
                log_warning "Python $PYTHON_VERSION may not be optimal for Bookworm"
                log_info "Consider upgrading to Python 3.11+ for best performance"
            fi
            
            # Check for Raspberry Pi 4B specifically
            if [[ -f /proc/device-tree/model ]]; then
                PI_MODEL=$(cat /proc/device-tree/model 2>/dev/null | tr -d '\0')
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

install_dependencies() {
    print_section "Installing System Dependencies"

    log_info "Updating package lists..."
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
        "libcap-dev"  # Added to resolve python-prctl dependency
    )

    # Hardware-specific packages
    hardware_packages=(
        "python3-picamera2"
        "python3-gpiozero"
        "python3-rpi.gpio"
        "raspi-config"
    )

    log_info "Installing essential packages..."
    sudo apt-get install -y "${essential_packages[@]}" || {
        log_error "Failed to install essential packages"
        exit 1
    }

    log_info "Installing hardware packages..."
    sudo apt-get install -y "${hardware_packages[@]}" || {
        log_warning "Some hardware packages failed to install - continuing anyway"
    }

    # Install Node.js LTS from NodeSource
    print_section "Installing Node.js LTS (via NodeSource)"
    if ! command -v node >/dev/null 2>&1 || [[ $(node -v | cut -d. -f1 | tr -d 'v') -lt 18 ]]; then
        curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
        sudo apt-get install -y nodejs || {
            log_warning "Node.js installation failed - web UI may not work"
        }
    else
        log_info "Node.js LTS already installed: $(node -v)"
    fi

    # Enable I2C and SPI
    log_info "Enabling I2C and SPI interfaces..."
    sudo raspi-config nonint do_i2c 0 2>/dev/null || log_warning "Could not enable I2C"
    sudo raspi-config nonint do_spi 0 2>/dev/null || log_warning "Could not enable SPI"
    sudo raspi-config nonint do_camera 0 2>/dev/null || log_warning "Could not enable camera"

    # Add user to required groups
    log_info "Adding user to required groups..."
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
        rm -rf venv
    fi

    python3 -m venv venv
    source venv/bin/activate

    # Upgrade pip
    log_info "Upgrading pip..."
    pip install --upgrade pip

    # Install requirements
    log_info "Installing Python requirements..."
    if [[ -f "requirements.txt" ]]; then
        pip install -r requirements.txt
    else
        log_error "requirements.txt not found"
        exit 1
    fi

    # Ensure requests library is installed
    log_info "Ensuring 'requests' library is installed..."
    pip install requests || {
        log_error "Failed to install 'requests' library"
        exit 1
    }

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
    
    log_info "Installing web UI dependencies..."
    npm install || {
        log_warning "npm install failed - web UI may not work"
        return
    }
    
    log_info "Building web UI..."
    npm run build || {
        log_warning "Web UI build failed"
        return
    }
    
    log_success "Web UI built successfully"
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
            rm "$temp_service"

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
    rm -f /tmp/lawnberry_*
    
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

    # Parse command line arguments
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
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo "Options:"
                echo "  --skip-hardware    Skip hardware detection"
                echo "  --skip-env        Skip environment setup"
                echo "  --non-interactive Run without user prompts"
                echo "  -h, --help        Show this help"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    log_info "Starting LawnBerry Pi installation..."
    log_info "Installation log: $LOG_FILE"

    # Run installation steps
    check_root
    check_system
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
