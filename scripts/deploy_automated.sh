#!/bin/bash
set -e

# LawnBerry Automated Deployment Script
# Complete zero-touch deployment with monitoring and remote update capabilities

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOYMENT_LOG="/tmp/lawnberry_automated_deployment_$(date +%Y%m%d_%H%M%S).log"
DEPLOYMENT_PACKAGE=""
DEPLOYMENT_MODE="production"
SKIP_VALIDATION=false
ENABLE_MONITORING=true
ENABLE_REMOTE_UPDATES=true
FORCE_DEPLOYMENT=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging setup
exec 1> >(tee -a "$DEPLOYMENT_LOG")
exec 2> >(tee -a "$DEPLOYMENT_LOG" >&2)

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
    echo "                LAWNBERRY AUTOMATED DEPLOYMENT"
    echo "=================================================================="
    echo "Deployment Mode: $DEPLOYMENT_MODE"
    echo "Package: $DEPLOYMENT_PACKAGE"
    echo "Log File: $DEPLOYMENT_LOG"
    echo "=================================================================="
}

show_usage() {
    cat << EOF
Usage: $0 [OPTIONS] PACKAGE_FILE

LawnBerry Automated Deployment Script

OPTIONS:
    -m, --mode MODE           Deployment mode: production, development, testing (default: production)
    -s, --skip-validation     Skip pre-deployment validation
    --no-monitoring          Disable monitoring setup
    --no-remote-updates      Disable remote update system
    -f, --force              Force deployment even if validation fails
    -h, --help               Show this help message

PACKAGE_FILE:
    Path to LawnBerry deployment package (.tar.gz)

EXAMPLES:
    $0 lawnberry-1.0.0.tar.gz
    $0 --mode development --skip-validation lawnberry-dev.tar.gz
    $0 --force --no-monitoring lawnberry-1.0.0.tar.gz

EOF
}

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -m|--mode)
                DEPLOYMENT_MODE="$2"
                shift 2
                ;;
            -s|--skip-validation)
                SKIP_VALIDATION=true
                shift
                ;;
            --no-monitoring)
                ENABLE_MONITORING=false
                shift
                ;;
            --no-remote-updates)
                ENABLE_REMOTE_UPDATES=false
                shift
                ;;
            -f|--force)
                FORCE_DEPLOYMENT=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            -*)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
            *)
                if [[ -z "$DEPLOYMENT_PACKAGE" ]]; then
                    DEPLOYMENT_PACKAGE="$1"
                else
                    log_error "Multiple package files specified"
                    exit 1
                fi
                shift
                ;;
        esac
    done

    if [[ -z "$DEPLOYMENT_PACKAGE" ]]; then
        log_error "No deployment package specified"
        show_usage
        exit 1
    fi

    if [[ ! -f "$DEPLOYMENT_PACKAGE" ]]; then
        log_error "Deployment package not found: $DEPLOYMENT_PACKAGE"
        exit 1
    fi

    # Validate deployment mode
    case $DEPLOYMENT_MODE in
        production|development|testing)
            ;;
        *)
            log_error "Invalid deployment mode: $DEPLOYMENT_MODE"
            log_info "Valid modes: production, development, testing"
            exit 1
            ;;
    esac
}

check_deployment_prerequisites() {
    log_info "Checking deployment prerequisites..."

    # Check if running as root
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi

    # Check system requirements
    local requirements_met=true

    # Check OS version
    if ! grep -q "bookworm" /etc/os-release; then
        log_error "Raspberry Pi OS Bookworm required"
        requirements_met=false
    fi

    # Check hardware
    if ! grep -Eq "Raspberry Pi 4|Raspberry Pi 5" /proc/cpuinfo; then
        log_warning "Raspberry Pi 4B or 5 recommended for optimal performance"
    fi

    # Check available memory
    local memory_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    local memory_gb=$((memory_kb / 1024 / 1024))
    if [[ $memory_gb -lt 4 ]]; then
        log_error "Minimum 4GB RAM required, found ${memory_gb}GB"
        requirements_met=false
    fi

    # Check available disk space
    local available_space_kb=$(df / | tail -1 | awk '{print $4}')
    local available_space_gb=$((available_space_kb / 1024 / 1024))
    if [[ $available_space_gb -lt 8 ]]; then
        log_error "Minimum 8GB free disk space required, found ${available_space_gb}GB"
        requirements_met=false
    fi

    # Check required tools
    local required_tools=("systemctl" "python3" "pip3" "git" "curl" "tar" "gzip")
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            log_error "Required tool not found: $tool"
            requirements_met=false
        fi
    done

    if [[ "$requirements_met" != true ]]; then
        log_error "Prerequisites not met"
        if [[ "$FORCE_DEPLOYMENT" != true ]]; then
            exit 1
        else
            log_warning "Continuing with force deployment despite failed prerequisites"
        fi
    fi

    log_success "Prerequisites check completed"
}

verify_deployment_package() {
    log_info "Verifying deployment package..."

    local package_path="$DEPLOYMENT_PACKAGE"
    local package_name=$(basename "$package_path" .tar.gz)

    # Check package file integrity
    if [[ ! -f "$package_path" ]]; then
        log_error "Package file not found: $package_path"
        exit 1
    fi

    # Check if checksum file exists
    local checksum_file="${package_path}.sha256"
    if [[ -f "$checksum_file" ]]; then
        log_info "Verifying package checksum..."
        if sha256sum -c "$checksum_file"; then
            log_success "Package checksum verified"
        else
            log_error "Package checksum verification failed"
            if [[ "$FORCE_DEPLOYMENT" != true ]]; then
                exit 1
            fi
        fi
    else
        log_warning "No checksum file found, skipping integrity check"
    fi

    # Extract and verify package contents
    local temp_dir="/tmp/lawnberry_deploy_verify"
    rm -rf "$temp_dir"
    mkdir -p "$temp_dir"

    log_info "Extracting package for verification..."
    tar -xzf "$package_path" -C "$temp_dir"

    local extracted_dir="$temp_dir/$package_name"
    if [[ ! -d "$extracted_dir" ]]; then
        # Try to find the extracted directory
        extracted_dir=$(find "$temp_dir" -maxdepth 1 -type d -name "lawnberry*" | head -1)
        if [[ ! -d "$extracted_dir" ]]; then
            log_error "Could not find extracted package directory"
            exit 1
        fi
    fi

    # Verify required files
    local required_files=(
        "install.sh"
        "src/system_integration/system_manager.py"
        "config/system.yaml"
        "PACKAGE_INFO.json"
    )

    local verification_failed=false
    for file in "${required_files[@]}"; do
        if [[ ! -f "$extracted_dir/$file" ]]; then
            log_error "Required file missing from package: $file"
            verification_failed=true
        fi
    done

    if [[ "$verification_failed" == true ]]; then
        log_error "Package verification failed"
        rm -rf "$temp_dir"
        if [[ "$FORCE_DEPLOYMENT" != true ]]; then
            exit 1
        fi
    fi

    # Store extracted directory for deployment
    export EXTRACTED_PACKAGE_DIR="$extracted_dir"

    log_success "Package verification completed"
}

create_deployment_backup() {
    log_info "Creating pre-deployment backup..."

    local backup_dir="/var/backups/lawnberry"
    local backup_name="pre_deployment_$(date +%Y%m%d_%H%M%S)"
    local backup_path="$backup_dir/$backup_name"

    mkdir -p "$backup_dir"
    mkdir -p "$backup_path"

    # Backup existing installation if it exists
    if [[ -d "/opt/lawnberry" ]]; then
        log_info "Backing up existing installation..."
        cp -r /opt/lawnberry "$backup_path/"

        # Backup user data
        if [[ -d "/var/lib/lawnberry" ]]; then
            cp -r /var/lib/lawnberry "$backup_path/data"
        fi

        # Backup recent logs
        if [[ -d "/var/log/lawnberry" ]]; then
            mkdir -p "$backup_path/logs"
            find /var/log/lawnberry -name "*.log" -mtime -7 -exec cp {} "$backup_path/logs/" \; 2>/dev/null || true
        fi
    fi

    # Create backup manifest
    cat > "$backup_path/BACKUP_INFO.json" << EOF
{
    "backup_name": "$backup_name",
    "backup_type": "pre_deployment",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "hostname": "$(hostname)",
    "system_id": "$(cat /etc/machine-id 2>/dev/null || echo unknown)",
    "deployment_package": "$(basename "$DEPLOYMENT_PACKAGE")",
    "deployment_mode": "$DEPLOYMENT_MODE"
}
EOF

    # Compress backup
    cd "$backup_dir"
    tar -czf "${backup_name}.tar.gz" "$backup_name"
    rm -rf "$backup_path"

    export DEPLOYMENT_BACKUP="${backup_dir}/${backup_name}.tar.gz"

    log_success "Backup created: $DEPLOYMENT_BACKUP"
}

run_pre_deployment_validation() {
    if [[ "$SKIP_VALIDATION" == true ]]; then
        log_info "Skipping pre-deployment validation (--skip-validation specified)"
        return 0
    fi

    log_info "Running pre-deployment validation..."

    # Check if validation script exists
    local validation_script="$EXTRACTED_PACKAGE_DIR/scripts/validate_deployment.py"
    if [[ ! -f "$validation_script" ]]; then
        log_warning "Deployment validation script not found, skipping validation"
        return 0
    fi

    # Run validation
    local validation_output="/tmp/pre_deployment_validation.json"
    if python3 "$validation_script" --output "$validation_output" --categories installation configuration; then
        log_success "Pre-deployment validation passed"
        return 0
    else
        log_error "Pre-deployment validation failed"

        if [[ -f "$validation_output" ]]; then
            log_info "Validation results:"
            python3 -c "
import json
with open('$validation_output', 'r') as f:
    data = json.load(f)
    summary = data['summary']
    print(f'  Tests: {summary[\"total_tests\"]}')
    print(f'  Passed: {summary[\"passed\"]}')
    print(f'  Failed: {summary[\"failed\"]}')
    print(f'  Warnings: {summary[\"warnings\"]}')
"
        fi

        if [[ "$FORCE_DEPLOYMENT" == true ]]; then
            log_warning "Continuing with deployment despite validation failures (--force specified)"
            return 0
        else
            log_error "Use --force to continue despite validation failures"
            exit 1
        fi
    fi
}

deploy_package() {
    log_info "Deploying LawnBerry package..."

    # Change to extracted package directory
    cd "$EXTRACTED_PACKAGE_DIR"

    # Set deployment mode environment variable
    export LAWNBERRY_DEPLOYMENT_MODE="$DEPLOYMENT_MODE"
    export LAWNBERRY_AUTOMATED_DEPLOYMENT=true

    # Run installation script
    log_info "Running installation script..."
    if ./install.sh; then
        log_success "Package installation completed"
    else
        log_error "Package installation failed"

        # Attempt rollback
        log_info "Attempting automatic rollback..."
        rollback_deployment
        exit 1
    fi
}

setup_additional_features() {
    log_info "Setting up additional deployment features..."

    # Setup monitoring if enabled
    if [[ "$ENABLE_MONITORING" == true ]]; then
        log_info "Setting up monitoring system..."
        if [[ -f "/opt/lawnberry/scripts/setup_monitoring.sh" ]]; then
            bash /opt/lawnberry/scripts/setup_monitoring.sh
            log_success "Monitoring system setup completed"
        else
            log_warning "Monitoring setup script not found"
        fi
    fi

    # Setup remote updates if enabled
    if [[ "$ENABLE_REMOTE_UPDATES" == true ]]; then
        log_info "Configuring remote update system..."

        # Enable remote updates in configuration
        local config_file="/opt/lawnberry/config/deployment.yaml"
        if [[ -f "$config_file" ]]; then
            # Update configuration to enable remote updates
            python3 -c "
import yaml
try:
    with open('$config_file', 'r') as f:
        config = yaml.safe_load(f)

    if 'deployment' not in config:
        config['deployment'] = {}

    config['deployment']['remote_updates'] = {
        'enabled': True,
        'check_interval': 3600,
        'auto_approve_security': True,
        'auto_approve_config': True
    }

    with open('$config_file', 'w') as f:
        yaml.dump(config, f, default_flow_style=False)

    print('Remote updates configuration updated')
except Exception as e:
    print(f'Failed to update configuration: {e}')
"
            log_success "Remote update system configured"
        else
            log_warning "Deployment configuration file not found"
        fi
    fi
}

run_post_deployment_validation() {
    log_info "Running post-deployment validation..."

    # Wait for services to start
    log_info "Waiting for services to initialize..."
    sleep 30

    # Run comprehensive validation
    local validation_script="/opt/lawnberry/scripts/validate_deployment.py"
    local validation_output="/tmp/post_deployment_validation.json"

    if [[ -f "$validation_script" ]]; then
        if python3 "$validation_script" --output "$validation_output"; then
            log_success "Post-deployment validation passed"

            # Display validation summary
            python3 -c "
import json
with open('$validation_output', 'r') as f:
    data = json.load(f)
    summary = data['summary']
    print(f'Validation Summary:')
    print(f'  Total Tests: {summary[\"total_tests\"]}')
    print(f'  Passed: {summary[\"passed\"]}')
    print(f'  Failed: {summary[\"failed\"]}')
    print(f'  Warnings: {summary[\"warnings\"]}')
    print(f'  Success: {summary[\"success\"]}')
"
            return 0
        else
            log_error "Post-deployment validation failed"

            # Show failed tests
            python3 -c "
import json
with open('$validation_output', 'r') as f:
    data = json.load(f)

print('Failed Tests:')
for test in data['tests']:
    if test['status'] == 'FAIL':
        print(f'  - {test[\"description\"]}: {test[\"message\"]}')
"

            log_error "Deployment validation failed, consider rollback"
            return 1
        fi
    else
        log_warning "Post-deployment validation script not available"
        return 0
    fi
}

rollback_deployment() {
    log_warning "Initiating deployment rollback..."

    if [[ -z "$DEPLOYMENT_BACKUP" ]] || [[ ! -f "$DEPLOYMENT_BACKUP" ]]; then
        log_error "No deployment backup available for rollback"
        return 1
    fi

    # Stop services
    log_info "Stopping LawnBerry services..."
    systemctl stop lawnberry-system.service || true
    systemctl stop lawnberry-hardware.service || true
    systemctl stop lawnberry-safety.service || true
    systemctl stop lawnberry-web-api.service || true
    systemctl stop lawnberry-communication.service || true
    systemctl stop lawnberry-monitor.service || true

    # Remove current installation
    log_info "Removing current installation..."
    rm -rf /opt/lawnberry
    rm -rf /var/lib/lawnberry

    # Restore from backup
    log_info "Restoring from backup..."
    local restore_dir="/tmp/lawnberry_rollback"
    rm -rf "$restore_dir"
    mkdir -p "$restore_dir"

    tar -xzf "$DEPLOYMENT_BACKUP" -C "$restore_dir"
    local backup_name=$(basename "$DEPLOYMENT_BACKUP" .tar.gz)

    if [[ -d "$restore_dir/$backup_name/lawnberry" ]]; then
        mv "$restore_dir/$backup_name/lawnberry" /opt/lawnberry
    fi

    if [[ -d "$restore_dir/$backup_name/data" ]]; then
        mv "$restore_dir/$backup_name/data" /var/lib/lawnberry
    fi

    # Restore permissions
    chown -R lawnberry:lawnberry /opt/lawnberry || true
    chown -R lawnberry:lawnberry /var/lib/lawnberry || true

    # Restart services
    log_info "Restarting services..."
    systemctl daemon-reload
    systemctl start lawnberry-system.service || true

    # Cleanup
    rm -rf "$restore_dir"

    log_success "Rollback completed"
}

generate_deployment_report() {
    log_info "Generating deployment report..."

    local report_file="/var/log/lawnberry/deployment_report_$(date +%Y%m%d_%H%M%S).json"
    mkdir -p "$(dirname "$report_file")"

    # Collect deployment information
    local deployment_info=$(cat << EOF
{
    "deployment_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "deployment_mode": "$DEPLOYMENT_MODE",
    "package_file": "$(basename "$DEPLOYMENT_PACKAGE")",
    "hostname": "$(hostname)",
    "system_id": "$(cat /etc/machine-id 2>/dev/null || echo unknown)",
    "deployment_log": "$DEPLOYMENT_LOG",
    "backup_file": "$DEPLOYMENT_BACKUP",
    "monitoring_enabled": $ENABLE_MONITORING,
    "remote_updates_enabled": $ENABLE_REMOTE_UPDATES,
    "validation_skipped": $SKIP_VALIDATION,
    "force_deployment": $FORCE_DEPLOYMENT
}
EOF
)

    echo "$deployment_info" > "$report_file"

    export DEPLOYMENT_REPORT="$report_file"

    log_success "Deployment report created: $report_file"
}

cleanup_deployment() {
    log_info "Cleaning up deployment artifacts..."

    # Remove temporary files
    rm -rf /tmp/lawnberry_deploy_*
    rm -rf /tmp/lawnberry_package_*

    # Keep deployment log for reference
    cp "$DEPLOYMENT_LOG" "/var/log/lawnberry/deployment_$(date +%Y%m%d_%H%M%S).log" 2>/dev/null || true

    log_success "Cleanup completed"
}

print_deployment_summary() {
    echo
    echo "=================================================================="
    echo "                    DEPLOYMENT SUMMARY"
    echo "=================================================================="
    echo "Status: SUCCESS"
    echo "Mode: $DEPLOYMENT_MODE"
    echo "Package: $(basename "$DEPLOYMENT_PACKAGE")"
    echo "Backup: $DEPLOYMENT_BACKUP"
    echo "Report: $DEPLOYMENT_REPORT"
    echo "Log: $DEPLOYMENT_LOG"
    echo
    echo "Services Status:"
    systemctl is-active lawnberry-system.service && echo "  ✓ System Service: Running" || echo "  ✗ System Service: Not Running"
    systemctl is-active lawnberry-hardware.service && echo "  ✓ Hardware Service: Running" || echo "  ✗ Hardware Service: Not Running"
    systemctl is-active lawnberry-safety.service && echo "  ✓ Safety Service: Running" || echo "  ✗ Safety Service: Not Running"
    systemctl is-active lawnberry-web-api.service && echo "  ✓ Web API Service: Running" || echo "  ✗ Web API Service: Not Running"

    if [[ "$ENABLE_MONITORING" == true ]]; then
        systemctl is-active lawnberry-monitor.service && echo "  ✓ Monitor Service: Running" || echo "  ✗ Monitor Service: Not Running"
    fi

    echo
    echo "Next Steps:"
    echo "  1. Access web interface: http://$(hostname -I | awk '{print $1}'):8000"
    echo "  2. Complete system configuration"
    echo "  3. Run hardware tests"

    if [[ "$ENABLE_MONITORING" == true ]]; then
        echo "  4. View monitoring dashboard: sudo -u lawnberry /opt/lawnberry/monitoring/scripts/dashboard.sh"
    fi

    echo "=================================================================="
}

main() {
    print_header

    # Parse command line arguments
    parse_arguments "$@"

    # Pre-deployment phase
    check_deployment_prerequisites
    verify_deployment_package
    create_deployment_backup
    run_pre_deployment_validation

    # Deployment phase
    deploy_package
    setup_additional_features

    # Post-deployment phase
    if ! run_post_deployment_validation; then
        log_error "Post-deployment validation failed"

        if [[ "$FORCE_DEPLOYMENT" != true ]]; then
            read -p "Do you want to rollback? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                rollback_deployment
                exit 1
            fi
        fi
    fi

    # Finalization
    generate_deployment_report
    cleanup_deployment
    print_deployment_summary

    log_success "Automated deployment completed successfully!"
}

# Trap signals to cleanup on exit
trap cleanup_deployment EXIT

# Run main function
main "$@"
