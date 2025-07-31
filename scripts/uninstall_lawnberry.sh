#!/bin/bash
set -e

# LawnBerry Pi Uninstall Script
# Safely removes LawnBerry Pi system while preserving user data

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
INSTALL_DIR="/opt/lawnberry"
SERVICE_DIR="/etc/systemd/system"
LOG_DIR="/var/log/lawnberry"
DATA_DIR="/var/lib/lawnberry"
BACKUP_DIR="/var/backups/lawnberry"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
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
    echo "                 LAWNBERRY PI UNINSTALLER"
    echo "=================================================================="
    echo
}

confirm_uninstall() {
    echo "This will remove the LawnBerry Pi system from your device."
    echo "The following will be removed:"
    echo "  - System services"
    echo "  - System control scripts"
    echo "  - Log rotation configuration"
    echo "  - Python virtual environment"
    echo
    echo "The following will be PRESERVED:"
    echo "  - Configuration files in $DATA_DIR"
    echo "  - Log files in $LOG_DIR"
    echo "  - Project source code"
    echo "  - Environment variables (.env)"
    echo
    read -p "Are you sure you want to continue? (type 'yes' to confirm): " confirm
    
    if [[ "$confirm" != "yes" ]]; then
        log_info "Uninstall cancelled"
        exit 0
    fi
}

stop_services() {
    log_info "Stopping LawnBerry services..."
    
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
        
        if systemctl is-enabled --quiet "$service.service" 2>/dev/null; then
            log_info "Disabling $service..."
            sudo systemctl disable "$service.service" || true
        fi
    done
    
    log_success "Services stopped and disabled"
}

remove_services() {
    log_info "Removing system service files..."
    
    services=(
        "lawnberry-system.service"
        "lawnberry-communication.service"
        "lawnberry-data.service"
        "lawnberry-hardware.service"
        "lawnberry-sensor-fusion.service"
        "lawnberry-weather.service"
        "lawnberry-power.service"
        "lawnberry-safety.service"
        "lawnberry-vision.service"
        "lawnberry-api.service"
    )
    
    for service in "${services[@]}"; do
        if [[ -f "$SERVICE_DIR/$service" ]]; then
            log_info "Removing $service..."
            sudo rm -f "$SERVICE_DIR/$service"
        fi
    done
    
    # Reload systemd
    log_info "Reloading systemd daemon..."
    sudo systemctl daemon-reload
    
    log_success "Service files removed"
}

remove_system_scripts() {
    log_info "Removing system control scripts..."
    
    scripts=(
        "/usr/local/bin/lawnberry-system"
        "/usr/local/bin/lawnberry-health-check"
    )
    
    for script in "${scripts[@]}"; do
        if [[ -f "$script" ]]; then
            log_info "Removing $script..."
            sudo rm -f "$script"
        fi
    done
    
    log_success "System scripts removed"
}

remove_logrotate() {
    log_info "Removing log rotation configuration..."
    
    if [[ -f "/etc/logrotate.d/lawnberry" ]]; then
        sudo rm -f "/etc/logrotate.d/lawnberry"
        log_success "Log rotation configuration removed"
    fi
}

backup_data() {
    log_info "Creating backup of user data..."
    
    timestamp=$(date +%Y%m%d_%H%M%S)
    backup_file="/tmp/lawnberry_backup_$timestamp.tar.gz"
    
    # Create backup directory if it doesn't exist
    sudo mkdir -p "$BACKUP_DIR"
    
    # Files to backup
    backup_items=()
    
    if [[ -f "$PROJECT_ROOT/.env" ]]; then
        backup_items+=("$PROJECT_ROOT/.env")
    fi
    
    if [[ -d "$DATA_DIR" ]]; then
        backup_items+=("$DATA_DIR")
    fi
    
    if [[ -f "$PROJECT_ROOT/config/hardware.yaml" ]]; then
        backup_items+=("$PROJECT_ROOT/config/hardware.yaml")
    fi
    
    if [[ ${#backup_items[@]} -gt 0 ]]; then
        sudo tar -czf "$backup_file" "${backup_items[@]}" 2>/dev/null || true
        sudo mv "$backup_file" "$BACKUP_DIR/" 2>/dev/null || true
        sudo chown "$USER:$USER" "$BACKUP_DIR/lawnberry_backup_$timestamp.tar.gz" 2>/dev/null || true
        log_success "Backup created: $BACKUP_DIR/lawnberry_backup_$timestamp.tar.gz"
    else
        log_info "No user data found to backup"
    fi
}

remove_python_env() {
    log_info "Removing Python virtual environment..."
    
    cd "$PROJECT_ROOT"
    
    if [[ -d "venv" ]]; then
        rm -rf venv
        log_success "Python virtual environment removed"
    else
        log_info "No virtual environment found"
    fi
}

clean_cache() {
    log_info "Cleaning cache and temporary files..."
    
    cd "$PROJECT_ROOT"
    
    # Remove Python cache
    find . -name "*.pyc" -delete 2>/dev/null || true
    find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    
    # Remove detection results
    rm -f hardware_detection_results.json 2>/dev/null || true
    rm -f hardware_detected.yaml 2>/dev/null || true
    
    # Remove build artifacts
    if [[ -d "web-ui/dist" ]]; then
        rm -rf web-ui/dist
    fi
    
    if [[ -d "web-ui/node_modules" ]]; then
        read -p "Remove web UI node_modules directory? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf web-ui/node_modules
            log_success "Node modules removed"
        fi
    fi
    
    log_success "Cache cleaned"
}

optional_removal() {
    echo
    log_info "Optional removal steps:"
    echo
    
    # Ask about removing logs
    if [[ -d "$LOG_DIR" ]]; then
        read -p "Remove log files in $LOG_DIR? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo rm -rf "$LOG_DIR"
            log_success "Log files removed"
        fi
    fi
    
    # Ask about removing data directory
    if [[ -d "$DATA_DIR" ]]; then
        read -p "Remove data directory $DATA_DIR? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            sudo rm -rf "$DATA_DIR"
            log_success "Data directory removed"
        fi
    fi
    
    # Ask about removing environment file
    if [[ -f "$PROJECT_ROOT/.env" ]]; then
        read -p "Remove environment file (.env)? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -f "$PROJECT_ROOT/.env"
            log_success "Environment file removed"
        fi
    fi
    
    # Ask about removing the entire project
    read -p "Remove entire project directory? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "WARNING: This will remove all source code and configuration!"
        read -p "Are you absolutely sure? (type 'DELETE' to confirm): " confirm
        if [[ "$confirm" == "DELETE" ]]; then
            cd /
            rm -rf "$PROJECT_ROOT"
            log_success "Project directory removed"
            echo "LawnBerry Pi has been completely removed from your system."
            exit 0
        else
            log_info "Project directory preserved"
        fi
    fi
}

show_completion() {
    echo
    log_success "LawnBerry Pi uninstall completed!"
    echo
    echo "What was removed:"
    echo "  ✓ System services"
    echo "  ✓ System control scripts"
    echo "  ✓ Log rotation configuration"
    echo "  ✓ Python virtual environment"
    echo "  ✓ Cache and temporary files"
    echo
    echo "What was preserved:"
    if [[ -d "$DATA_DIR" ]]; then
        echo "  • Configuration data: $DATA_DIR"
    fi
    if [[ -d "$LOG_DIR" ]]; then
        echo "  • Log files: $LOG_DIR"
    fi
    if [[ -f "$PROJECT_ROOT/.env" ]]; then
        echo "  • Environment variables: $PROJECT_ROOT/.env"
    fi
    echo "  • Project source code: $PROJECT_ROOT"
    echo
    
    if [[ -d "$BACKUP_DIR" ]]; then
        echo "Backups are available in: $BACKUP_DIR"
        echo
    fi
    
    echo "To reinstall LawnBerry Pi, run:"
    echo "  cd $PROJECT_ROOT"
    echo "  bash scripts/install_lawnberry.sh"
    echo
}

# Main uninstall process
main() {
    print_header
    
    # Parse command line arguments
    FORCE=false
    COMPLETE=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --force)
                FORCE=true
                shift
                ;;
            --complete)
                COMPLETE=true
                shift
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo "Options:"
                echo "  --force      Skip confirmation prompts"
                echo "  --complete   Remove everything including data and logs"
                echo "  -h, --help   Show this help"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    if [[ "$FORCE" != true ]]; then
        confirm_uninstall
    fi
    
    log_info "Starting LawnBerry Pi uninstall..."
    
    # Core uninstall steps
    backup_data
    stop_services
    remove_services
    remove_system_scripts
    remove_logrotate
    remove_python_env
    clean_cache
    
    # Complete removal if requested
    if [[ "$COMPLETE" == true ]]; then
        log_info "Performing complete removal..."
        sudo rm -rf "$LOG_DIR" 2>/dev/null || true
        sudo rm -rf "$DATA_DIR" 2>/dev/null || true
        rm -f "$PROJECT_ROOT/.env" 2>/dev/null || true
    else
        # Interactive optional removal
        if [[ "$FORCE" != true ]]; then
            optional_removal
        fi
    fi
    
    show_completion
    log_success "Uninstall completed successfully!"
}

# Run main function
main "$@"
