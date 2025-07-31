#!/bin/bash
set -e

# LawnBerry Monitoring Setup Script
# Sets up comprehensive monitoring and alerting for deployed systems

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
INSTALL_DIR="/opt/lawnberry"
LOG_DIR="/var/log/lawnberry"
DATA_DIR="/var/lib/lawnberry"
MONITORING_DIR="/opt/lawnberry/monitoring"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging
LOG_FILE="/tmp/lawnberry_monitoring_setup.log"
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
    echo "                LAWNBERRY MONITORING SETUP"
    echo "=================================================================="
}

check_requirements() {
    log_info "Checking monitoring setup requirements..."
    
    # Check if running as root
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
    
    # Check system tools
    local required_tools=("systemctl" "crontab" "curl" "python3")
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            log_error "Required tool not found: $tool"
            exit 1
        fi
    done
    
    # Check LawnBerry installation
    if [[ ! -d "$INSTALL_DIR" ]]; then
        log_error "LawnBerry not installed at $INSTALL_DIR"
        exit 1
    fi
    
    log_success "Requirements check completed"
}

setup_monitoring_directories() {
    log_info "Setting up monitoring directories..."
    
    # Create monitoring directories
    mkdir -p "$MONITORING_DIR"/{scripts,config,data,logs}
    mkdir -p "$LOG_DIR/monitoring"
    mkdir -p "$DATA_DIR/monitoring"
    
    # Set permissions
    chown -R lawnberry:lawnberry "$MONITORING_DIR"
    chown -R lawnberry:lawnberry "$LOG_DIR/monitoring"
    chown -R lawnberry:lawnberry "$DATA_DIR/monitoring"
    
    chmod 755 "$MONITORING_DIR"
    chmod 755 "$MONITORING_DIR"/{scripts,config,data,logs}
    
    log_success "Monitoring directories created"
}

create_health_check_script() {
    log_info "Creating system health check script..."
    
    cat > "$MONITORING_DIR/scripts/health_check.sh" << 'EOF'
#!/bin/bash
# LawnBerry System Health Check Script

INSTALL_DIR="/opt/lawnberry"
LOG_FILE="/var/log/lawnberry/monitoring/health_check.log"
STATUS_FILE="/var/lib/lawnberry/monitoring/health_status.json"
ALERT_FILE="/var/lib/lawnberry/monitoring/alerts.json"

# Health check configuration
MAX_CPU_PERCENT=80
MAX_MEMORY_PERCENT=85
MIN_DISK_FREE_GB=2
MAX_TEMP_C=75
SERVICE_TIMEOUT=30

# Initialize
mkdir -p "$(dirname "$LOG_FILE")"
mkdir -p "$(dirname "$STATUS_FILE")"
exec 1> >(tee -a "$LOG_FILE")
exec 2> >(tee -a "$LOG_FILE" >&2)

log_with_timestamp() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Function to send alert
send_alert() {
    local severity="$1"
    local component="$2"
    local message="$3"
    local timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    
    # Create alert record
    local alert_record=$(cat << EOJ
{
    "timestamp": "$timestamp",
    "severity": "$severity",
    "component": "$component",
    "message": "$message",
    "hostname": "$(hostname)",
    "system_id": "$(cat /etc/machine-id 2>/dev/null || echo unknown)"
}
EOJ
)
    
    # Append to alerts file
    if [[ -f "$ALERT_FILE" ]]; then
        # Read existing alerts and add new one
        python3 -c "
import json
import sys

try:
    with open('$ALERT_FILE', 'r') as f:
        alerts = json.load(f)
except:
    alerts = []

alerts.append($alert_record)

# Keep only last 100 alerts
alerts = alerts[-100:]

with open('$ALERT_FILE', 'w') as f:
    json.dump(alerts, f, indent=2)
"
    else
        echo "[$alert_record]" > "$ALERT_FILE"
    fi
    
    # Log alert
    log_with_timestamp "ALERT [$severity] $component: $message"
    
    # Send to system log
    logger -t lawnberry-monitor "[$severity] $component: $message"
}

# Check system services
check_services() {
    local services=("lawnberry-system" "lawnberry-hardware" "lawnberry-safety" "lawnberry-web-api" "lawnberry-communication")
    local failed_services=()
    
    for service in "${services[@]}"; do
        if ! systemctl is-active --quiet "$service"; then
            failed_services+=("$service")
            send_alert "CRITICAL" "service" "Service $service is not running"
        fi
    done
    
    if [[ ${#failed_services[@]} -eq 0 ]]; then
        log_with_timestamp "All services are running"
        return 0
    else
        log_with_timestamp "Failed services: ${failed_services[*]}"
        return 1
    fi
}

# Check system resources
check_resources() {
    local issues=0
    
    # CPU usage
    local cpu_usage=$(python3 -c "import psutil; print(f'{psutil.cpu_percent(interval=1):.1f}')")
    if (( $(echo "$cpu_usage > $MAX_CPU_PERCENT" | bc -l) )); then
        send_alert "WARNING" "cpu" "High CPU usage: ${cpu_usage}%"
        issues=$((issues + 1))
    fi
    
    # Memory usage
    local memory_info=$(python3 -c "import psutil; m=psutil.virtual_memory(); print(f'{m.percent:.1f} {m.available/1024/1024/1024:.1f}')")
    local memory_percent=$(echo "$memory_info" | cut -d' ' -f1)
    local memory_available_gb=$(echo "$memory_info" | cut -d' ' -f2)
    
    if (( $(echo "$memory_percent > $MAX_MEMORY_PERCENT" | bc -l) )); then
        send_alert "WARNING" "memory" "High memory usage: ${memory_percent}%"
        issues=$((issues + 1))
    fi
    
    # Disk space
    local disk_free_gb=$(df / | tail -1 | awk '{printf "%.1f\n", $4/1024/1024}')
    if (( $(echo "$disk_free_gb < $MIN_DISK_FREE_GB" | bc -l) )); then
        send_alert "CRITICAL" "disk" "Low disk space: ${disk_free_gb}GB free"
        issues=$((issues + 1))
    fi
    
    # System temperature (if available)
    if [[ -f /sys/class/thermal/thermal_zone0/temp ]]; then
        local temp_c=$(( $(cat /sys/class/thermal/thermal_zone0/temp) / 1000 ))
        if [[ $temp_c -gt $MAX_TEMP_C ]]; then
            send_alert "WARNING" "temperature" "High system temperature: ${temp_c}°C"
            issues=$((issues + 1))
        fi
    fi
    
    log_with_timestamp "Resource check: CPU ${cpu_usage}%, Memory ${memory_percent}%, Disk ${disk_free_gb}GB free"
    return $issues
}

# Check network connectivity
check_connectivity() {
    local issues=0
    
    # Check web API
    if ! curl -f -s --connect-timeout 5 http://localhost:8000/health > /dev/null; then
        send_alert "CRITICAL" "web_api" "Web API health check failed"
        issues=$((issues + 1))
    fi
    
    # Check internet connectivity
    if ! curl -f -s --connect-timeout 10 https://api.openweathermap.org > /dev/null; then
        send_alert "WARNING" "internet" "Internet connectivity check failed"
        issues=$((issues + 1))
    fi
    
    log_with_timestamp "Connectivity check completed with $issues issues"
    return $issues
}

# Check log files for errors
check_logs() {
    local issues=0
    local log_files=(
        "/var/log/lawnberry/system.log"
        "/var/log/lawnberry/hardware.log"
        "/var/log/lawnberry/safety.log"
    )
    
    # Check for recent critical errors (last 5 minutes)
    local since_time=$(date -d '5 minutes ago' '+%Y-%m-%d %H:%M:%S')
    
    for log_file in "${log_files[@]}"; do
        if [[ -f "$log_file" ]]; then
            local error_count=$(awk -v since="$since_time" '$0 >= since && /ERROR|CRITICAL/' "$log_file" | wc -l)
            if [[ $error_count -gt 0 ]]; then
                send_alert "WARNING" "logs" "Found $error_count recent errors in $(basename "$log_file")"
                issues=$((issues + 1))
            fi
        fi
    done
    
    log_with_timestamp "Log check completed with $issues issues"
    return $issues
}

# Generate health status report
generate_status_report() {
    local overall_status="healthy"
    local timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    
    # Get system metrics
    local system_info=$(python3 -c "
import psutil
import json
import socket

cpu_percent = psutil.cpu_percent(interval=1)
memory = psutil.virtual_memory()
disk = psutil.disk_usage('/')
boot_time = psutil.boot_time()

# Get load average
try:
    load_avg = psutil.getloadavg()
except:
    load_avg = [0, 0, 0]

# Get network stats
network = psutil.net_io_counters()

# Get temperature if available
temp = None
try:
    with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
        temp = int(f.read().strip()) / 1000
except:
    pass

status = {
    'cpu_percent': round(cpu_percent, 1),
    'memory_percent': round(memory.percent, 1),
    'memory_available_gb': round(memory.available / 1024**3, 1),
    'disk_free_gb': round(disk.free / 1024**3, 1),
    'disk_percent': round((disk.used / disk.total) * 100, 1),
    'load_average': [round(x, 2) for x in load_avg],
    'network_bytes_sent': network.bytes_sent,
    'network_bytes_recv': network.bytes_recv,
    'uptime_hours': round(($(date +%s) - boot_time) / 3600, 1),
    'hostname': socket.gethostname()
}

if temp is not None:
    status['temperature_c'] = round(temp, 1)

print(json.dumps(status, indent=2))
")
    
    # Check if any critical issues exist
    if [[ -f "$ALERT_FILE" ]]; then
        local recent_critical=$(python3 -c "
import json
from datetime import datetime, timedelta

try:
    with open('$ALERT_FILE', 'r') as f:
        alerts = json.load(f)
    
    now = datetime.utcnow()
    recent_threshold = now - timedelta(minutes=15)
    
    critical_count = 0
    for alert in alerts:
        alert_time = datetime.fromisoformat(alert['timestamp'].replace('Z', '+00:00'))
        if alert_time > recent_threshold and alert['severity'] == 'CRITICAL':
            critical_count += 1
    
    print(critical_count)
except:
    print(0)
")
        
        if [[ $recent_critical -gt 0 ]]; then
            overall_status="critical"
        fi
    fi
    
    # Create status report
    cat > "$STATUS_FILE" << EOJ
{
    "timestamp": "$timestamp",
    "overall_status": "$overall_status",
    "system_metrics": $system_info,
    "services_status": {
        "lawnberry-system": "$(systemctl is-active lawnberry-system 2>/dev/null || echo inactive)",
        "lawnberry-hardware": "$(systemctl is-active lawnberry-hardware 2>/dev/null || echo inactive)",
        "lawnberry-safety": "$(systemctl is-active lawnberry-safety 2>/dev/null || echo inactive)",
        "lawnberry-web-api": "$(systemctl is-active lawnberry-web-api 2>/dev/null || echo inactive)",
        "lawnberry-communication": "$(systemctl is-active lawnberry-communication 2>/dev/null || echo inactive)"
    },
    "last_health_check": "$timestamp"
}
EOJ
    
    log_with_timestamp "Health status report generated: $overall_status"
}

# Main health check function
main() {
    log_with_timestamp "Starting system health check..."
    
    local total_issues=0
    
    # Run all health checks
    check_services || total_issues=$((total_issues + 1))
    check_resources || total_issues=$((total_issues + $?))
    check_connectivity || total_issues=$((total_issues + $?))
    check_logs || total_issues=$((total_issues + $?))
    
    # Generate status report
    generate_status_report
    
    if [[ $total_issues -eq 0 ]]; then
        log_with_timestamp "Health check completed successfully - no issues found"
    else
        log_with_timestamp "Health check completed with $total_issues issues"
    fi
    
    # Cleanup old log entries (keep last 1000 lines)
    if [[ -f "$LOG_FILE" ]]; then
        tail -n 1000 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
    fi
}

# Install required Python packages if not available
if ! python3 -c "import psutil" 2>/dev/null; then
    echo "Installing required Python packages..."
    pip3 install psutil bc-python 2>/dev/null || {
        echo "Warning: Could not install psutil. Some metrics may not be available."
    }
fi

# Run main function
main "$@"
EOF

    chmod +x "$MONITORING_DIR/scripts/health_check.sh"
    chown lawnberry:lawnberry "$MONITORING_DIR/scripts/health_check.sh"
    
    log_success "Health check script created"
}

create_monitoring_service() {
    log_info "Creating monitoring systemd service..."
    
    cat > /etc/systemd/system/lawnberry-monitor.service << EOF
[Unit]
Description=LawnBerry System Monitor
After=multi-user.target
Wants=lawnberry-system.service

[Service]
Type=simple
User=lawnberry
Group=lawnberry
WorkingDirectory=/opt/lawnberry
ExecStart=/opt/lawnberry/monitoring/scripts/health_check.sh
Restart=always
RestartSec=300
StandardOutput=journal
StandardError=journal

# Resource limits
MemoryMax=100M
CPUQuota=10%

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable lawnberry-monitor.service
    
    log_success "Monitoring service created and enabled"
}

setup_cron_jobs() {
    log_info "Setting up monitoring cron jobs..."
    
    # Create cron job for regular health checks
    cat > /etc/cron.d/lawnberry-monitoring << EOF
# LawnBerry Monitoring Cron Jobs
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Health check every 5 minutes
*/5 * * * * lawnberry /opt/lawnberry/monitoring/scripts/health_check.sh >/dev/null 2>&1

# Cleanup old logs daily at 2 AM
0 2 * * * root /opt/lawnberry/monitoring/scripts/cleanup_logs.sh >/dev/null 2>&1

# System backup weekly on Sunday at 3 AM
0 3 * * 0 root /opt/lawnberry/scripts/create_backup.sh >/dev/null 2>&1
EOF

    log_success "Cron jobs setup completed"
}

create_log_cleanup_script() {
    log_info "Creating log cleanup script..."
    
    cat > "$MONITORING_DIR/scripts/cleanup_logs.sh" << 'EOF'
#!/bin/bash
# LawnBerry Log Cleanup Script

LOG_DIR="/var/log/lawnberry"
DATA_DIR="/var/lib/lawnberry"
MONITORING_DIR="/opt/lawnberry/monitoring"

# Cleanup parameters
KEEP_DAYS=30
KEEP_COMPRESSED_DAYS=90

log_cleanup() {
    echo "[$(date)] Starting log cleanup..."
    
    # Rotate and compress logs older than KEEP_DAYS
    find "$LOG_DIR" -name "*.log" -type f -mtime +$KEEP_DAYS -exec gzip {} \;
    
    # Remove compressed logs older than KEEP_COMPRESSED_DAYS
    find "$LOG_DIR" -name "*.log.gz" -type f -mtime +$KEEP_COMPRESSED_DAYS -delete
    
    # Cleanup monitoring data
    find "$DATA_DIR/monitoring" -name "*.json" -type f -mtime +$KEEP_DAYS -delete
    
    # Cleanup temporary files
    find /tmp -name "lawnberry_*" -type f -mtime +7 -delete
    
    echo "[$(date)] Log cleanup completed"
}

# Run cleanup
log_cleanup
EOF

    chmod +x "$MONITORING_DIR/scripts/cleanup_logs.sh"
    chown lawnberry:lawnberry "$MONITORING_DIR/scripts/cleanup_logs.sh"
    
    log_success "Log cleanup script created"
}

create_monitoring_dashboard() {
    log_info "Creating monitoring dashboard..."
    
    cat > "$MONITORING_DIR/scripts/show_dashboard.py" << 'EOF'
#!/usr/bin/env python3
"""
LawnBerry Monitoring Dashboard - Simple console dashboard
"""

import json
import time
import os
from pathlib import Path
from datetime import datetime

def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')

def load_status():
    status_file = Path("/var/lib/lawnberry/monitoring/health_status.json")
    if status_file.exists():
        try:
            with open(status_file, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def load_alerts():
    alerts_file = Path("/var/lib/lawnberry/monitoring/alerts.json")
    if alerts_file.exists():
        try:
            with open(alerts_file, 'r') as f:
                alerts = json.load(f)
                # Return last 10 alerts
                return alerts[-10:]
        except:
            return []
    return []

def format_status_indicator(status):
    if status == "active":
        return "🟢 RUNNING"
    elif status == "inactive":
        return "🔴 STOPPED"
    else:
        return "🟡 UNKNOWN"

def print_dashboard(status_data, alerts):
    print("=" * 80)
    print("                    LAWNBERRY SYSTEM DASHBOARD")
    print("=" * 80)
    
    if not status_data:
        print("⚠️  No status data available")
        return
    
    # System overview
    overall = status_data.get('overall_status', 'unknown')
    last_check = status_data.get('last_health_check', 'unknown')
    
    status_color = "🟢" if overall == "healthy" else "🔴" if overall == "critical" else "🟡"
    
    print(f"Overall Status: {status_color} {overall.upper()}")
    print(f"Last Check: {last_check}")
    print()
    
    # System metrics
    metrics = status_data.get('system_metrics', {})
    if metrics:
        print("SYSTEM METRICS")
        print("-" * 40)
        print(f"CPU Usage:      {metrics.get('cpu_percent', 'N/A')}%")
        print(f"Memory Usage:   {metrics.get('memory_percent', 'N/A')}% ({metrics.get('memory_available_gb', 'N/A')}GB available)")
        print(f"Disk Usage:     {metrics.get('disk_percent', 'N/A')}% ({metrics.get('disk_free_gb', 'N/A')}GB free)")
        print(f"Load Average:   {', '.join(map(str, metrics.get('load_average', ['N/A'])))}")
        print(f"Uptime:         {metrics.get('uptime_hours', 'N/A')} hours")
        if 'temperature_c' in metrics:
            print(f"Temperature:    {metrics['temperature_c']}°C")
        print()
    
    # Services status
    services = status_data.get('services_status', {})
    if services:
        print("SERVICES STATUS")
        print("-" * 40)
        for service, status in services.items():
            service_name = service.replace('lawnberry-', '').replace('-', ' ').title()
            print(f"{service_name:15} {format_status_indicator(status)}")
        print()
    
    # Recent alerts
    if alerts:
        print("RECENT ALERTS")
        print("-" * 40)
        for alert in alerts:
            timestamp = alert.get('timestamp', 'Unknown')
            severity = alert.get('severity', 'INFO')
            component = alert.get('component', 'system')
            message = alert.get('message', 'No message')
            
            severity_icon = "🔴" if severity == "CRITICAL" else "🟡" if severity == "WARNING" else "🔵"
            
            # Format timestamp
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                time_str = dt.strftime('%H:%M:%S')
            except:
                time_str = timestamp[:8] if len(timestamp) > 8 else timestamp
            
            print(f"{severity_icon} {time_str} [{component}] {message}")
        print()
    else:
        print("RECENT ALERTS")
        print("-" * 40)
        print("🟢 No recent alerts")
        print()
    
    print("=" * 80)
    print("Press Ctrl+C to exit | Auto-refresh every 30 seconds")

def main():
    try:
        while True:
            clear_screen()
            
            status_data = load_status()
            alerts = load_alerts()
            
            print_dashboard(status_data, alerts)
            
            time.sleep(30)
            
    except KeyboardInterrupt:
        print("\nDashboard closed.")

if __name__ == "__main__":
    main()
EOF

    chmod +x "$MONITORING_DIR/scripts/show_dashboard.py"
    chown lawnberry:lawnberry "$MONITORING_DIR/scripts/show_dashboard.py"
    
    # Create convenient alias
    cat > "$MONITORING_DIR/scripts/dashboard.sh" << 'EOF'
#!/bin/bash
python3 /opt/lawnberry/monitoring/scripts/show_dashboard.py "$@"
EOF

    chmod +x "$MONITORING_DIR/scripts/dashboard.sh"
    chown lawnberry:lawnberry "$MONITORING_DIR/scripts/dashboard.sh"
    
    log_success "Monitoring dashboard created"
}

create_backup_script() {
    log_info "Creating automated backup script..."
    
    cat > "$INSTALL_DIR/scripts/create_backup.sh" << 'EOF'
#!/bin/bash
# LawnBerry Automated Backup Script

BACKUP_DIR="/var/backups/lawnberry"
INSTALL_DIR="/opt/lawnberry"
DATA_DIR="/var/lib/lawnberry"
LOG_DIR="/var/log/lawnberry"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Backup configuration
KEEP_BACKUPS=10
COMPRESS=true

log_backup() {
    echo "[$(date)] $1" | tee -a "$LOG_DIR/backup.log"
}

create_backup() {
    local backup_name="lawnberry_backup_$TIMESTAMP"
    local backup_path="$BACKUP_DIR/$backup_name"
    
    log_backup "Starting backup: $backup_name"
    
    # Create backup directory
    mkdir -p "$backup_path"
    
    # Backup configuration
    log_backup "Backing up configuration..."
    cp -r "$INSTALL_DIR/config" "$backup_path/"
    
    # Backup user data
    log_backup "Backing up user data..."
    cp -r "$DATA_DIR" "$backup_path/data"
    
    # Backup recent logs (last 7 days)
    log_backup "Backing up recent logs..."
    mkdir -p "$backup_path/logs"
    find "$LOG_DIR" -name "*.log" -mtime -7 -exec cp {} "$backup_path/logs/" \;
    
    # Create backup manifest
    cat > "$backup_path/BACKUP_INFO.json" << EOJ
{
    "backup_name": "$backup_name",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "hostname": "$(hostname)",
    "system_id": "$(cat /etc/machine-id 2>/dev/null || echo unknown)",
    "lawnberry_version": "$(cat $INSTALL_DIR/VERSION 2>/dev/null || echo unknown)",
    "backup_type": "automatic",
    "components": ["config", "data", "logs"]
}
EOJ
    
    # Compress backup if enabled
    if [[ "$COMPRESS" == "true" ]]; then
        log_backup "Compressing backup..."
        cd "$BACKUP_DIR"
        tar -czf "${backup_name}.tar.gz" "$backup_name"
        rm -rf "$backup_path"
        backup_path="${backup_path}.tar.gz"
    fi
    
    # Cleanup old backups
    log_backup "Cleaning up old backups..."
    cd "$BACKUP_DIR"
    ls -t lawnberry_backup_* 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | xargs rm -rf
    
    log_backup "Backup completed: $(basename "$backup_path")"
    
    # Return backup path for external use
    echo "$backup_path"
}

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Run backup
create_backup
EOF

    chmod +x "$INSTALL_DIR/scripts/create_backup.sh"
    chown lawnberry:lawnberry "$INSTALL_DIR/scripts/create_backup.sh"
    
    log_success "Backup script created"
}

start_monitoring_services() {
    log_info "Starting monitoring services..."
    
    # Start and enable monitoring service
    systemctl start lawnberry-monitor.service
    
    # Run initial health check
    sudo -u lawnberry "$MONITORING_DIR/scripts/health_check.sh"
    
    log_success "Monitoring services started"
}

create_monitoring_config() {
    log_info "Creating monitoring configuration..."
    
    cat > "$MONITORING_DIR/config/monitoring.yaml" << 'EOF'
# LawnBerry Monitoring Configuration

monitoring:
  enabled: true
  check_interval: 300  # 5 minutes
  
  # Health check thresholds
  thresholds:
    cpu_max_percent: 80
    memory_max_percent: 85
    disk_min_free_gb: 2
    temperature_max_c: 75
    service_timeout_seconds: 30
  
  # Alert configuration
  alerts:
    enabled: true
    max_stored_alerts: 100
    notification_methods:
      - system_log
      - file
    
    # Alert severity levels
    severity_levels:
      - INFO
      - WARNING
      - CRITICAL
  
  # Log management
  logs:
    retention_days: 30
    compressed_retention_days: 90
    max_log_size_mb: 100
  
  # Backup configuration
  backup:
    enabled: true
    schedule: "0 3 * * 0"  # Weekly on Sunday at 3 AM
    retention_count: 10
    compress: true
  
  # Dashboard settings
  dashboard:
    refresh_interval: 30
    show_metrics: true
    show_alerts: true
    max_displayed_alerts: 10

# Remote monitoring (optional)
remote_monitoring:
  enabled: false
  endpoint: ""
  api_key: ""
  send_interval: 900  # 15 minutes
EOF

    chown lawnberry:lawnberry "$MONITORING_DIR/config/monitoring.yaml"
    
    log_success "Monitoring configuration created"
}

print_completion_summary() {
    log_success "Monitoring setup completed successfully!"
    echo
    echo "=================================================================="
    echo "                    MONITORING SETUP SUMMARY"
    echo "=================================================================="
    echo "Monitoring Directory: $MONITORING_DIR"
    echo "Health Check Script:  $MONITORING_DIR/scripts/health_check.sh"
    echo "Dashboard Script:     $MONITORING_DIR/scripts/dashboard.sh"
    echo "Backup Script:        $INSTALL_DIR/scripts/create_backup.sh"
    echo
    echo "Services:"
    echo "  - lawnberry-monitor.service (health monitoring)"
    echo "  - Cron jobs for regular checks and cleanup"
    echo
    echo "Commands:"
    echo "  View dashboard:       sudo -u lawnberry $MONITORING_DIR/scripts/dashboard.sh"
    echo "  Run health check:     sudo -u lawnberry $MONITORING_DIR/scripts/health_check.sh"
    echo "  Create backup:        sudo $INSTALL_DIR/scripts/create_backup.sh"
    echo "  Check service status: systemctl status lawnberry-monitor"
    echo
    echo "Log Files:"
    echo "  Health checks:        /var/log/lawnberry/monitoring/health_check.log"
    echo "  System status:        /var/lib/lawnberry/monitoring/health_status.json"
    echo "  Alerts:              /var/lib/lawnberry/monitoring/alerts.json"
    echo "=================================================================="
}

main() {
    print_header
    
    check_requirements
    setup_monitoring_directories
    create_health_check_script
    create_monitoring_service
    setup_cron_jobs
    create_log_cleanup_script
    create_monitoring_dashboard
    create_backup_script
    create_monitoring_config
    start_monitoring_services
    
    print_completion_summary
}

# Run main function
main "$@"
