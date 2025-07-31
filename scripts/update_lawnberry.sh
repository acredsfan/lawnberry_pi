#!/bin/bash
set -e

# LawnBerry Pi Update Script
# Updates the system while preserving configurations and user data

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="/var/log/lawnberry"
DATA_DIR="/var/lib/lawnberry"
BACKUP_DIR="/var/backups/lawnberry"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging setup
LOG_FILE="/tmp/lawnberry_update.log"
exec 1> >(tee -a "$LOG_FILE")
exec 2> >(tee -a "$LOG_FILE" >&2)

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

print_header() {
    echo
    echo "=================================================================="
    echo "                   LAWNBERRY PI UPDATER"
    echo "=================================================================="
    echo
}

print_section() {
    echo
    echo "----------------------------------------"
    echo "$1"
    echo "----------------------------------------"
}

check_git_status() {
    print_section "Checking Git Status"
    
    cd "$PROJECT_ROOT"
    
    if [[ ! -d ".git" ]]; then
        log_error "Not a git repository. Updates require git."
        log_info "To enable updates, clone the repository with git:"
        log_info "  git clone <repository-url> /path/to/new/location"
        exit 1
    fi
    
    # Check for uncommitted changes
    if ! git diff --quiet; then
        log_warning "Uncommitted changes detected in working directory"
        if [[ "$FORCE_UPDATE" != true ]]; then
            read -p "Continue with update? Changes may be lost. (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                log_info "Update cancelled"
                exit 0
            fi
        fi
    fi
    
    # Check current branch
    current_branch=$(git branch --show-current)
    log_info "Current branch: $current_branch"
    
    # Check remote status
    log_info "Fetching latest changes..."
    git fetch origin || {
        log_error "Failed to fetch from remote repository"
        exit 1
    }
    
    # Check if updates are available
    local_commit=$(git rev-parse HEAD)
    remote_commit=$(git rev-parse origin/$current_branch)
    
    if [[ "$local_commit" == "$remote_commit" ]]; then
        log_info "Already up to date"
        if [[ "$FORCE_UPDATE" != true ]]; then
            read -p "Force update anyway? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                log_info "Update cancelled"
                exit 0
            fi
        fi
    else
        log_info "Updates available"
        log_info "Local:  $local_commit"
        log_info "Remote: $remote_commit"
    fi
    
    log_success "Git status check complete"
}

backup_system() {
    print_section "Creating System Backup"
    
    timestamp=$(date +%Y%m%d_%H%M%S)
    backup_name="lawnberry_pre_update_$timestamp"
    backup_path="$BACKUP_DIR/$backup_name"
    
    log_info "Creating backup: $backup_name"
    
    # Create backup directory
    sudo mkdir -p "$BACKUP_DIR"
    sudo mkdir -p "$backup_path"
    
    # Backup critical files and directories
    backup_items=(
        ".env"
        "config/"
        "venv/"
    )
    
    # Backup user data
    if [[ -d "$DATA_DIR" ]]; then
        sudo cp -r "$DATA_DIR" "$backup_path/data" || true
    fi
    
    # Backup project files
    cd "$PROJECT_ROOT"
    for item in "${backup_items[@]}"; do
        if [[ -e "$item" ]]; then
            log_info "Backing up: $item"
            sudo cp -r "$item" "$backup_path/" || true
        fi
    done
    
    # Backup service files
    sudo mkdir -p "$backup_path/services"
    sudo cp /etc/systemd/system/lawnberry-*.service "$backup_path/services/" 2>/dev/null || true
    
    # Create backup info file
    sudo tee "$backup_path/backup_info.txt" > /dev/null <<EOF
LawnBerry Pi System Backup
Created: $(date)
Git Commit: $(git rev-parse HEAD)
Git Branch: $(git branch --show-current)
Python Version: $(python3 --version)
System: $(uname -a)
EOF
    
    # Set ownership
    sudo chown -R "$USER:$USER" "$backup_path" 2>/dev/null || true
    
    echo "$backup_path" > /tmp/lawnberry_backup_path
    log_success "Backup created: $backup_path"
}

stop_services() {
    print_section "Stopping Services"
    
    log_info "Stopping LawnBerry services..."
    
    # Use system control script if available
    if command -v lawnberry-system >/dev/null 2>&1; then
        lawnberry-system stop
    else
        # Manual service stop
        services=(
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
        
        for service in "${services[@]}"; do
            if systemctl is-active --quiet "$service.service" 2>/dev/null; then
                log_info "Stopping $service..."
                sudo systemctl stop "$service.service" || true
            fi
        done
    fi
    
    log_success "Services stopped"
}

update_code() {
    print_section "Updating Source Code"
    
    cd "$PROJECT_ROOT"
    
    log_info "Stashing local changes..."
    git stash push -m "Pre-update stash $(date)" || true
    
    log_info "Pulling latest changes..."
    current_branch=$(git branch --show-current)
    git pull origin "$current_branch" || {
        log_error "Failed to pull updates from remote repository"
        exit 1
    }
    
    # Get commit info
    new_commit=$(git rev-parse HEAD)
    log_info "Updated to commit: $new_commit"
    
    # Show changelog if available
    if [[ -f "CHANGELOG.md" ]]; then
        log_info "Recent changes:"
        head -20 CHANGELOG.md
    fi
    
    log_success "Source code updated"
}

run_coral_migration() {
    print_section "Checking Coral Package Migration"
    
    local migration_script="$SCRIPT_DIR/migrate_coral_packages.py"
    
    if [[ ! -f "$migration_script" ]]; then
        log_warning "Coral migration script not found, skipping migration check"
        return 0
    fi
    
    log_info "Checking if Coral package migration is needed..."
    
    # Check if migration is needed (detection only)
    local migration_check
    if migration_check=$(python3 "$migration_script" --detect-only 2>/dev/null); then
        local migration_needed
        migration_needed=$(echo "$migration_check" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('migration_needed', False))" 2>/dev/null || echo "false")
        
        if [[ "$migration_needed" == "True" ]]; then
            log_info "Coral package migration needed - migrating from pip to system packages"
            log_info "This will:"
            log_info "  - Remove pip-installed pycoral and tflite-runtime packages"
            log_info "  - Install system packages: python3-pycoral, python3-tflite-runtime"
            log_info "  - Create backup for rollback capability"
            
            # Ask for user confirmation unless forced
            if [[ "$FORCE_UPDATE" != true ]]; then
                echo
                read -p "Proceed with Coral package migration? (Y/n): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Nn]$ ]]; then
                    log_warning "Coral migration skipped by user request"
                    log_warning "Note: You can run migration later with: python3 $migration_script"
                    return 0
                fi
            fi
            
            # Run migration
            log_info "Running Coral package migration..."
            if python3 "$migration_script" --verbose; then
                log_success "Coral package migration completed successfully"
            else
                log_error "Coral package migration failed"
                log_error "Check logs at /var/log/lawnberry/coral_migration.log"
                log_info "You can attempt rollback with: python3 $migration_script --rollback <migration_id>"
                
                # Ask if user wants to continue despite migration failure
                if [[ "$FORCE_UPDATE" != true ]]; then
                    echo
                    read -p "Continue update despite migration failure? (y/N): " -n 1 -r
                    echo
                    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                        log_error "Update cancelled due to migration failure"
                        exit 1
                    fi
                fi
                
                log_warning "Continuing update despite migration failure"
            fi
        else
            log_info "No Coral package migration needed"
        fi
    else
        log_warning "Could not check migration status, continuing with update"
    fi
}

update_dependencies() {
    print_section "Updating Dependencies"
    
    cd "$PROJECT_ROOT"
    
    # Update system packages
    log_info "Updating system packages..."
    sudo apt-get update -qq
    sudo apt-get upgrade -y -qq
    
    # Update Python virtual environment
    log_info "Updating Python environment..."
    
    if [[ -d "venv" ]]; then
        source venv/bin/activate
        
        # Upgrade pip
        pip install --upgrade pip
        
        # Run Coral package migration if needed
        run_coral_migration
        
        # Update requirements
        if [[ -f "requirements.txt" ]]; then
            log_info "Installing/updating Python packages..."
            pip install -r requirements.txt --upgrade
        fi
        
        log_success "Python dependencies updated"
    else
        log_warning "Virtual environment not found - creating new one"
        python3 -m venv venv
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
        log_success "New virtual environment created"
    fi
}

update_configuration() {
    print_section "Updating Configuration"
    
    cd "$PROJECT_ROOT"
    
    # Check for new configuration files
    if [[ -f "config/.example" ]]; then
        log_info "New configuration examples found"
        # Handle configuration migration if needed
    fi
    
    # Update environment variables if needed
    if [[ -f ".env.example" && -f ".env" ]]; then
        log_info "Checking environment variables..."
        
        # Check for new required variables
        new_vars=$(comm -23 <(grep "^[A-Z]" .env.example | cut -d'=' -f1 | sort) <(grep "^[A-Z]" .env | cut -d'=' -f1 | sort) || true)
        
        if [[ -n "$new_vars" ]]; then
            log_warning "New environment variables detected:"
            echo "$new_vars"
            
            if [[ "$INTERACTIVE" == true ]]; then
                read -p "Run environment setup to add new variables? (y/N): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    source venv/bin/activate
                    python3 scripts/setup_environment.py
                fi
            fi
        fi
    fi
    
    # Run hardware detection if requested
    if [[ "$RUN_HARDWARE_DETECTION" == true ]]; then
        log_info "Running hardware detection..."
        source venv/bin/activate
        python3 scripts/hardware_detection.py || log_warning "Hardware detection failed"
    fi
    
    log_success "Configuration updated"
}

update_services() {
    print_section "Updating System Services"
    
    cd "$PROJECT_ROOT"
    
    # Update service files
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
    
    log_info "Updating systemd service files..."
    
    updated_services=()
    for service_file in "${services[@]}"; do
        if [[ -f "$service_file" ]]; then
            service_name=$(basename "$service_file")
            log_info "Updating $service_name..."
            
            # Update service file paths to use current virtual environment
            temp_service="/tmp/$service_name"
            sed "s|/usr/bin/python3|$PROJECT_ROOT/venv/bin/python3|g" "$service_file" > "$temp_service"
            sed -i "s|WorkingDirectory=.*|WorkingDirectory=$PROJECT_ROOT|g" "$temp_service"
            
            sudo cp "$temp_service" "/etc/systemd/system/"
            sudo chmod 644 "/etc/systemd/system/$service_name"
            rm "$temp_service"
            
            updated_services+=("${service_name%.service}")
        fi
    done
    
    if [[ ${#updated_services[@]} -gt 0 ]]; then
        # Reload systemd
        log_info "Reloading systemd daemon..."
        sudo systemctl daemon-reload
        log_success "Service files updated"
    fi
}

run_tests() {
    print_section "Running Update Tests"
    
    cd "$PROJECT_ROOT"
    source venv/bin/activate
    
    log_info "Testing updated system..."
    
    # Test Python imports
    if python3 -c "import sys; sys.path.insert(0, 'src'); import weather.weather_service" 2>/dev/null; then
        log_success "Python imports: OK"
    else
        log_warning "Python imports: Some modules failed"
    fi
    
    # Test configuration loading
    if [[ -f ".env" ]]; then
        log_success "Environment file: Present"
    else
        log_warning "Environment file: Missing"
    fi
    
    # Test hardware if available
    if [[ -f "scripts/hardware_detection.py" ]]; then
        python3 scripts/hardware_detection.py >/dev/null 2>&1 && \
            log_success "Hardware detection: Working" || \
            log_warning "Hardware detection: Issues detected"
    fi
    
    log_info "Update tests completed"
}

start_services() {
    print_section "Starting Services"
    
    log_info "Starting LawnBerry services..."
    
    # Use system control script if available
    if command -v lawnberry-system >/dev/null 2>&1; then
        lawnberry-system start
        sleep 3
        lawnberry-system status
    else
        log_warning "System control script not found - manual service start required"
    fi
    
    log_success "Services started"
}

cleanup() {
    print_section "Update Cleanup"
    
    cd "$PROJECT_ROOT"
    
    # Clean up temporary files
    log_info "Cleaning up temporary files..."
    rm -f /tmp/lawnberry_*
    
    # Clean up build artifacts
    find . -name "*.pyc" -delete 2>/dev/null || true
    find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    
    log_info "Cleanup complete"
}

show_completion() {
    print_section "Update Complete!"
    
    cd "$PROJECT_ROOT"
    
    echo
    log_success "LawnBerry Pi update completed successfully!"
    echo
    echo "Update Summary:"
    echo "  - Updated to commit: $(git rev-parse --short HEAD)"
    echo "  - Current branch: $(git branch --show-current)"
    echo "  - Update log: $LOG_FILE"
    
    if [[ -f "/tmp/lawnberry_backup_path" ]]; then
        backup_path=$(cat /tmp/lawnberry_backup_path)
        echo "  - Backup location: $backup_path"
        rm -f /tmp/lawnberry_backup_path
    fi
    
    echo
    echo "System Status:"
    if command -v lawnberry-health-check >/dev/null 2>&1; then
        lawnberry-health-check
    else
        log_info "Run system health check manually if needed"
    fi
    
    echo
    echo "If you encounter issues:"
    echo "1. Check logs: lawnberry-system logs"
    echo "2. Check service status: lawnberry-system status"
    echo "3. Restore from backup if needed"
    echo
}

rollback() {
    log_error "Update failed - attempting rollback..."
    
    if [[ -f "/tmp/lawnberry_backup_path" ]]; then
        backup_path=$(cat /tmp/lawnberry_backup_path)
        log_info "Rolling back from backup: $backup_path"
        
        cd "$PROJECT_ROOT"
        
        # Restore git state
        git reset --hard HEAD~1 2>/dev/null || true
        
        # Restore virtual environment
        if [[ -d "$backup_path/venv" ]]; then
            rm -rf venv
            cp -r "$backup_path/venv" .
        fi
        
        # Restore configuration
        if [[ -f "$backup_path/.env" ]]; then
            cp "$backup_path/.env" .
        fi
        
        # Restore services
        if [[ -d "$backup_path/services" ]]; then
            sudo cp "$backup_path/services"/* /etc/systemd/system/ 2>/dev/null || true
            sudo systemctl daemon-reload
        fi
        
        log_success "Rollback completed"
    else
        log_error "No backup found for rollback"
    fi
}

# Main update process
main() {
    print_header
    
    # Parse command line arguments
    FORCE_UPDATE=false
    INTERACTIVE=true
    RUN_HARDWARE_DETECTION=false
    SKIP_BACKUP=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --force)
                FORCE_UPDATE=true
                shift
                ;;
            --non-interactive)
                INTERACTIVE=false
                shift
                ;;
            --hardware-detection)
                RUN_HARDWARE_DETECTION=true
                shift
                ;;
            --skip-backup)
                SKIP_BACKUP=true
                shift
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo "Options:"
                echo "  --force               Force update even if up to date"
                echo "  --non-interactive     Run without user prompts"
                echo "  --hardware-detection  Run hardware detection after update"
                echo "  --skip-backup         Skip creating backup (not recommended)"
                echo "  -h, --help           Show this help"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    log_info "Starting LawnBerry Pi update..."
    log_info "Update log: $LOG_FILE"
    
    # Set trap for cleanup on failure
    trap rollback ERR
    
    # Run update steps
    check_git_status
    
    if [[ "$SKIP_BACKUP" != true ]]; then
        backup_system
    fi
    
    stop_services
    update_code
    update_dependencies
    update_configuration
    update_services
    run_tests
    start_services
    cleanup
    show_completion
    
    # Remove error trap
    trap - ERR
    
    log_success "Update completed successfully!"
}

# Run main function
main "$@"
