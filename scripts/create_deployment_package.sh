#!/bin/bash
set -e

# Enhanced Deployment Package Creation Script
# Creates comprehensive deployment packages with all optimizations and validations

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PACKAGE_DIR="$PROJECT_ROOT/deployment_packages"
TEMP_DIR="/tmp/lawnberry_package_build"
VERSION_FILE="$PROJECT_ROOT/VERSION"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging
LOG_FILE="/tmp/lawnberry_package_build.log"
exec 1> >(tee -a "$LOG_FILE")
exec 2> >(tee -a "$LOG_FILE" >&2)

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
    echo "=================================================================="
    echo "                LAWNBERRY DEPLOYMENT PACKAGE BUILDER"
    echo "=================================================================="
}

check_prerequisites() {
    log_info "Checking build prerequisites..."

    # Check required tools
    local required_tools=("git" "tar" "gzip" "python3" "pip3" "nodejs" "npm")
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            log_error "Required tool not found: $tool"
            exit 1
        fi
    done

    # Check Python dependencies
    if ! python3 -m pip list | grep -q "PyYAML"; then
        log_error "PyYAML not installed. Run: pip3 install PyYAML"
        exit 1
    fi

    log_success "All prerequisites satisfied"
}

get_version() {
    if [[ -f "$VERSION_FILE" ]]; then
        cat "$VERSION_FILE"
    elif git rev-parse --git-dir &> /dev/null; then
        git describe --tags --always --dirty
    else
        echo "1.0.0-$(date +%Y%m%d_%H%M%S)"
    fi
}

create_package_structure() {
    local version="$1"
    local package_name="lawnberry-${version}"
    local package_path="$TEMP_DIR/$package_name"

    log_info "Creating package structure for version $version..."

    # Clean and create temporary directory
    rm -rf "$TEMP_DIR"
    mkdir -p "$TEMP_DIR"
    mkdir -p "$package_path"

    # Copy core application files
    cp -r "$PROJECT_ROOT/src" "$package_path/"
    cp -r "$PROJECT_ROOT/config" "$package_path/"
    cp -r "$PROJECT_ROOT/scripts" "$package_path/"
    cp -r "$PROJECT_ROOT/docs" "$package_path/"
    cp -r "$PROJECT_ROOT/examples" "$package_path/"
    cp -r "$PROJECT_ROOT/models" "$package_path/"
    cp -r "$PROJECT_ROOT/robohat_files" "$package_path/"

    # Copy configuration files
    cp "$PROJECT_ROOT/requirements.txt" "$package_path/"
    cp "$PROJECT_ROOT/pyproject.toml" "$package_path/"
    cp "$PROJECT_ROOT/pytest.ini" "$package_path/"
    cp "$PROJECT_ROOT/.env.example" "$package_path/"

    # Copy documentation
    cp "$PROJECT_ROOT/README.md" "$package_path/"
    cp "$PROJECT_ROOT/plan.md" "$package_path/"

    # Build web UI
    log_info "Building web UI..."
    cd "$PROJECT_ROOT/web-ui"
    npm install
    npm run build
    mkdir -p "$package_path/web-ui/dist"
    cp -r dist/* "$package_path/web-ui/dist/"
    cp package.json "$package_path/web-ui/"
    cp index.html "$package_path/web-ui/"
    cp nginx.conf "$package_path/web-ui/"

    cd "$PROJECT_ROOT"

    # Create deployment metadata
    create_deployment_metadata "$package_path" "$version"

    # Create installation package
    create_installation_package "$package_path" "$version"

    echo "$package_path"
}

create_deployment_metadata() {
    local package_path="$1"
    local version="$2"

    log_info "Creating deployment metadata..."

    # Create package metadata
    cat > "$package_path/PACKAGE_INFO.json" << EOF
{
    "name": "lawnberry",
    "version": "$version",
    "build_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "build_host": "$(hostname)",
    "git_commit": "$(git rev-parse HEAD 2>/dev/null || echo 'unknown')",
    "git_branch": "$(git branch --show-current 2>/dev/null || echo 'unknown')",
    "package_type": "full",
    "target_os": "raspberry_pi_os_bookworm",
    "minimum_hardware": "raspberry_pi_4b",
    "dependencies": {
        "python": ">=3.11",
        "nodejs": ">=16.0.0",
        "systemd": ">=250"
    },
    "services": [
        "lawnberry-system",
        "lawnberry-hardware",
        "lawnberry-safety",
        "lawnberry-web-api",
        "lawnberry-communication"
    ],
    "configuration_profiles": [
        "default",
        "development",
        "production",
        "field_test"
    ]
}
EOF

    # Create installation checklist
    cat > "$package_path/INSTALLATION_CHECKLIST.md" << EOF
# LawnBerry Installation Checklist

## Pre-Installation Verification
- [ ] Raspberry Pi 4B or 5 with minimum 4GB RAM
- [ ] Raspberry Pi OS Bookworm (fresh installation recommended)
- [ ] SD card with minimum 32GB capacity
- [ ] Internet connection for package downloads
- [ ] All hardware components connected
- [ ] Power supply adequate (minimum 3A)

## Hardware Detection Required
- [ ] GPIO pins 15, 16, 31, 32, 18, 22 available
- [ ] I2C devices: ToF sensors (0x29/0x30), BME280 (0x76), INA3221 (0x40), OLED (0x3c)
- [ ] UART: GPS (/dev/ttyACM0), BNO085 IMU (/dev/ttyAMA4)
- [ ] USB: RoboHAT (/dev/ttyACM1)
- [ ] Camera module (/dev/video0)

## Post-Installation Verification
- [ ] All systemd services start successfully
- [ ] Web interface accessible on port 8000
- [ ] Hardware detection reports all components
- [ ] Safety systems respond correctly
- [ ] GPS achieves fix within 5 minutes
- [ ] Camera produces clear 1920x1080 video

## Configuration Validation
- [ ] Environment variables properly set
- [ ] API keys configured (OpenWeather, Google Maps)
- [ ] Network connectivity established
- [ ] Time synchronization working
- [ ] Log rotation configured

## Performance Validation
- [ ] System startup completes within 2 minutes
- [ ] Memory usage under 2GB during normal operation
- [ ] CPU usage under 50% during mowing
- [ ] All sensors report within expected ranges
- [ ] Web interface responsive (<2s page loads)
EOF

    # Create backup procedures
    cat > "$package_path/BACKUP_PROCEDURES.md" << EOF
# LawnBerry Backup and Recovery Procedures

## Automatic Backup Components
- Configuration files (/opt/lawnberry/config/)
- User data (/var/lib/lawnberry/)
- System logs (last 7 days)
- Database snapshots
- SSL certificates and keys

## Manual Backup Creation
\`\`\`bash
sudo /opt/lawnberry/scripts/create_backup.sh
\`\`\`

## Recovery Procedures

### Configuration Recovery
\`\`\`bash
sudo /opt/lawnberry/scripts/restore_config.sh /path/to/backup
\`\`\`

### Full System Recovery
\`\`\`bash
sudo /opt/lawnberry/scripts/restore_system.sh /path/to/backup
\`\`\`

### Emergency Recovery Mode
If system fails to start:
1. Boot to single-user mode
2. Mount filesystems
3. Run: \`/opt/lawnberry/scripts/emergency_recovery.sh\`

## Rollback Procedures

### Automatic Rollback
System automatically rolls back if:
- Health checks fail for 5 minutes
- Critical services crash repeatedly
- Safety system failures detected

### Manual Rollback
\`\`\`bash
sudo /opt/lawnberry/scripts/rollback_deployment.sh
\`\`\`
EOF

    log_success "Deployment metadata created"
}

create_installation_package() {
    local package_path="$1"
    local version="$2"

    log_info "Creating comprehensive installation package..."

    # Create enhanced installation script
    cat > "$package_path/install.sh" << 'EOF'
#!/bin/bash
set -e

# LawnBerry Enhanced Installation Script with Full Automation
PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/lawnberry"
LOG_FILE="/tmp/lawnberry_install_$(date +%Y%m%d_%H%M%S).log"

# Import installation functions
source "$PACKAGE_DIR/scripts/install_lawnberry.sh"

# Main installation with enhanced error handling
main() {
    print_header

    # Pre-installation checks
    check_prerequisites
    detect_hardware
    validate_system_requirements

    # User confirmation
    confirm_installation

    # Create system backup point
    create_pre_install_backup

    # Install with progress tracking
    install_with_progress

    # Post-installation validation
    validate_installation

    # Setup monitoring and alerts
    setup_monitoring

    log_success "Installation completed successfully!"
    log_info "Access web interface at: http://$(hostname -I | awk '{print $1}'):8000"
    log_info "Check system status: sudo systemctl status lawnberry-system"
}

check_prerequisites() {
    log_info "Performing comprehensive prerequisite checks..."

    # Check OS version
    if ! grep -q "bookworm" /etc/os-release; then
        log_error "Raspberry Pi OS Bookworm required"
        exit 1
    fi

    # Check hardware
    if ! grep -q "Raspberry Pi 4" /proc/cpuinfo && ! grep -q "Raspberry Pi 5" /proc/cpuinfo; then
        log_warning "Raspberry Pi 4B or 5 recommended for optimal performance"
    fi

    # Check memory
    memory_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    memory_gb=$((memory_kb / 1024 / 1024))
    if [[ $memory_gb -lt 4 ]]; then
        log_error "Minimum 4GB RAM required"
        exit 1
    fi

    # Check disk space
    available_space=$(df / | tail -1 | awk '{print $4}')
    if [[ $available_space -lt 8000000 ]]; then # 8GB in KB
        log_error "Minimum 8GB free disk space required"
        exit 1
    fi

    log_success "All prerequisites satisfied"
}

install_with_progress() {
    local steps=("system_setup" "dependencies" "services" "configuration" "web_ui" "validation")
    local total_steps=${#steps[@]}
    local current_step=0

    for step in "${steps[@]}"; do
        current_step=$((current_step + 1))
        log_info "Step $current_step/$total_steps: $step"

        case $step in
            "system_setup")
                setup_system_users_and_directories
                ;;
            "dependencies")
                install_dependencies
                ;;
            "services")
                install_system_services
                ;;
            "configuration")
                setup_default_configuration
                ;;
            "web_ui")
                setup_web_interface
                ;;
            "validation")
                run_post_install_validation
                ;;
        esac

        log_success "Step $current_step/$total_steps completed"
    done
}

validate_installation() {
    log_info "Running comprehensive installation validation..."

    # Service validation
    local services=("lawnberry-system" "lawnberry-hardware" "lawnberry-safety" "lawnberry-web-api")
    for service in "${services[@]}"; do
        if systemctl is-active --quiet "$service"; then
            log_success "Service $service is running"
        else
            log_error "Service $service failed to start"
            systemctl status "$service" || true
            exit 1
        fi
    done

    # Hardware validation
    python3 "$INSTALL_DIR/scripts/hardware_detection.py" --validate || {
        log_error "Hardware validation failed"
        exit 1
    }

    # Web interface validation
    if curl -f -s http://localhost:8000/health > /dev/null; then
        log_success "Web interface is accessible"
    else
        log_error "Web interface validation failed"
        exit 1
    fi

    log_success "Installation validation completed"
}

setup_monitoring() {
    log_info "Setting up monitoring and alerting..."

    # Create monitoring configuration
    systemctl enable lawnberry-monitor.service
    systemctl start lawnberry-monitor.service

    # Setup log rotation
    cp "$PACKAGE_DIR/config/logrotate.conf" /etc/logrotate.d/lawnberry

    # Setup health check cron job
    echo "*/5 * * * * /opt/lawnberry/scripts/health_check.sh" | crontab -

    log_success "Monitoring setup completed"
}

main "$@"
EOF

    chmod +x "$package_path/install.sh"

    # Create uninstall script
    cat > "$package_path/uninstall.sh" << 'EOF'
#!/bin/bash
# LawnBerry Complete Uninstallation Script

set -e

LOG_FILE="/tmp/lawnberry_uninstall_$(date +%Y%m%d_%H%M%S).log"
BACKUP_DIR="/var/backups/lawnberry_uninstall_$(date +%Y%m%d_%H%M%S)"

log_info() {
    echo "[INFO] $1" | tee -a "$LOG_FILE"
}

main() {
    echo "LawnBerry Complete Uninstallation"
    echo "================================="

    read -p "This will completely remove LawnBerry. Continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi

    # Create backup before uninstall
    create_uninstall_backup

    # Stop and disable services
    stop_services

    # Remove installation
    remove_installation

    # Cleanup system
    cleanup_system

    log_info "Uninstallation completed"
    log_info "Backup created at: $BACKUP_DIR"
}

create_uninstall_backup() {
    log_info "Creating backup before uninstall..."
    mkdir -p "$BACKUP_DIR"

    if [[ -d "/opt/lawnberry" ]]; then
        cp -r /opt/lawnberry "$BACKUP_DIR/"
    fi

    if [[ -d "/var/lib/lawnberry" ]]; then
        cp -r /var/lib/lawnberry "$BACKUP_DIR/"
    fi

    log_info "Backup created at $BACKUP_DIR"
}

stop_services() {
    log_info "Stopping LawnBerry services..."

    local services=(
        "lawnberry-system"
        "lawnberry-hardware"
        "lawnberry-safety"
        "lawnberry-web-api"
        "lawnberry-communication"
        "lawnberry-monitor"
    )

    for service in "${services[@]}"; do
        if systemctl is-active --quiet "$service"; then
            systemctl stop "$service"
            log_info "Stopped $service"
        fi

        if systemctl is-enabled --quiet "$service"; then
            systemctl disable "$service"
            log_info "Disabled $service"
        fi

        if [[ -f "/etc/systemd/system/$service.service" ]]; then
            rm "/etc/systemd/system/$service.service"
            log_info "Removed $service.service"
        fi
    done

    systemctl daemon-reload
}

remove_installation() {
    log_info "Removing LawnBerry installation..."

    # Remove installation directory
    if [[ -d "/opt/lawnberry" ]]; then
        rm -rf /opt/lawnberry
        log_info "Removed /opt/lawnberry"
    fi

    # Remove data directory
    if [[ -d "/var/lib/lawnberry" ]]; then
        rm -rf /var/lib/lawnberry
        log_info "Removed /var/lib/lawnberry"
    fi

    # Remove log directory
    if [[ -d "/var/log/lawnberry" ]]; then
        rm -rf /var/log/lawnberry
        log_info "Removed /var/log/lawnberry"
    fi
}

cleanup_system() {
    log_info "Cleaning up system configuration..."

    # Remove user and group
    if id "lawnberry" &>/dev/null; then
        userdel lawnberry
        log_info "Removed lawnberry user"
    fi

    if getent group lawnberry &>/dev/null; then
        groupdel lawnberry
        log_info "Removed lawnberry group"
    fi

    # Remove cron jobs
    crontab -r 2>/dev/null || true

    # Remove logrotate configuration
    if [[ -f "/etc/logrotate.d/lawnberry" ]]; then
        rm /etc/logrotate.d/lawnberry
        log_info "Removed logrotate configuration"
    fi
}

main "$@"
EOF

    chmod +x "$package_path/uninstall.sh"

    log_success "Installation package created"
}

validate_package() {
    local package_path="$1"

    log_info "Validating deployment package..."

    # Check required files
    local required_files=(
        "src/system_integration/system_manager.py"
        "src/hardware/__init__.py"
        "src/safety/__init__.py"
        "config/system.yaml"
        "install.sh"
        "uninstall.sh"
        "PACKAGE_INFO.json"
    )

    for file in "${required_files[@]}"; do
        if [[ ! -f "$package_path/$file" ]]; then
            log_error "Required file missing: $file"
            exit 1
        fi
    done

    # Validate Python syntax
    find "$package_path/src" -name "*.py" -exec python3 -m py_compile {} \; || {
        log_error "Python syntax validation failed"
        exit 1
    }

    # Validate configuration files
    python3 -c "
import yaml
import sys
import os

config_dir = '$package_path/config'
for config_file in os.listdir(config_dir):
    if config_file.endswith('.yaml'):
        try:
            with open(os.path.join(config_dir, config_file)) as f:
                yaml.safe_load(f)
            print(f'Valid: {config_file}')
        except Exception as e:
            print(f'Invalid {config_file}: {e}')
            sys.exit(1)
" || {
        log_error "Configuration validation failed"
        exit 1
    }

    log_success "Package validation completed"
}

create_package_archive() {
    local package_path="$1"
    local version="$2"
    local package_name="lawnberry-${version}"

    log_info "Creating package archive..."

    mkdir -p "$PACKAGE_DIR"
    cd "$TEMP_DIR"

    # Create compressed archive
    tar -czf "$PACKAGE_DIR/${package_name}.tar.gz" "$package_name"

    # Create checksums
    cd "$PACKAGE_DIR"
    sha256sum "${package_name}.tar.gz" > "${package_name}.sha256"
    md5sum "${package_name}.tar.gz" > "${package_name}.md5"

    # Package information
    local archive_size=$(stat -c%s "${package_name}.tar.gz")
    local archive_checksum=$(sha256sum "${package_name}.tar.gz" | cut -d' ' -f1)

    log_success "Package archive created: ${package_name}.tar.gz"
    log_info "Archive size: $(numfmt --to=iec $archive_size)"
    log_info "SHA256: $archive_checksum"

    # Create package manifest
    cat > "${package_name}.manifest.json" << EOF
{
    "package_name": "$package_name",
    "version": "$version",
    "archive_file": "${package_name}.tar.gz",
    "archive_size": $archive_size,
    "checksum_sha256": "$archive_checksum",
    "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "created_by": "$(whoami)@$(hostname)",
    "installation_command": "tar -xzf ${package_name}.tar.gz && cd $package_name && sudo ./install.sh",
    "validation_command": "sha256sum -c ${package_name}.sha256"
}
EOF

    log_success "Package manifest created"
}

cleanup() {
    log_info "Cleaning up temporary files..."
    rm -rf "$TEMP_DIR"
    log_success "Cleanup completed"
}

main() {
    print_header

    check_prerequisites

    local version=$(get_version)
    log_info "Building deployment package for version: $version"

    local package_path
    package_path=$(create_package_structure "$version")

    validate_package "$package_path"

    create_package_archive "$package_path" "$version"

    cleanup

    log_success "Deployment package creation completed!"
    log_info "Package location: $PACKAGE_DIR/lawnberry-${version}.tar.gz"
    log_info "Install with: tar -xzf lawnberry-${version}.tar.gz && cd lawnberry-${version} && sudo ./install.sh"
}

# Run main function if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
