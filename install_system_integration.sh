#!/bin/bash
set -e

# Lawnberry System Integration Installation Script
# Installs systemd services and sets up system integration

echo "Installing Lawnberry System Integration..."

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo "This script should not be run as root. Please run as the lawnberry user."
   exit 1
fi

# Configuration
INSTALL_DIR="/opt/lawnberry"
SERVICE_DIR="/etc/systemd/system"
LOG_DIR="/var/log/lawnberry"
DATA_DIR="/var/lib/lawnberry"
USER="lawnberry"
GROUP="lawnberry"

echo "Creating directories..."
sudo mkdir -p $LOG_DIR
sudo mkdir -p $DATA_DIR
sudo mkdir -p $DATA_DIR/config_backups
sudo mkdir -p $DATA_DIR/health_metrics

# Set permissions
sudo chown -R $USER:$GROUP $LOG_DIR
sudo chown -R $USER:$GROUP $DATA_DIR
sudo chmod 755 $LOG_DIR
sudo chmod 755 $DATA_DIR

echo "Installing systemd service files..."

# Copy service files to systemd directory
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

for service in "${services[@]}"; do
    if [ -f "$service" ]; then
        service_name=$(basename "$service")
        echo "Installing $service_name..."
        sudo cp "$service" "$SERVICE_DIR/"
        sudo chmod 644 "$SERVICE_DIR/$service_name"
    else
        echo "Warning: Service file $service not found"
    fi
done

echo "Reloading systemd daemon..."
sudo systemctl daemon-reload

echo "Enabling core services..."
# Enable essential services
core_services=(
    "lawnberry-system"
    "lawnberry-communication"  
    "lawnberry-data"
    "lawnberry-hardware"
    "lawnberry-safety"
)

for service in "${core_services[@]}"; do
    echo "Enabling $service..."
    sudo systemctl enable "$service.service"
done

echo "Creating logrotate configuration..."
sudo tee /etc/logrotate.d/lawnberry > /dev/null <<EOF
/var/log/lawnberry/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 $USER $GROUP
    postrotate
        systemctl reload lawnberry-* 2>/dev/null || true
    endscript
}
EOF

echo "Setting up system limits..."
# Create systemd user service limits
sudo tee /etc/systemd/system/user@.service.d/lawnberry.conf > /dev/null <<EOF
[Service]
# Increase limits for Lawnberry services
LimitNOFILE=65536
LimitNPROC=32768
EOF

echo "Creating system health check script..."
sudo tee /usr/local/bin/lawnberry-health-check > /dev/null <<'EOF'
#!/bin/bash
# Simple health check script for Lawnberry system

services=(
    "lawnberry-system"
    "lawnberry-communication"
    "lawnberry-data" 
    "lawnberry-hardware"
    "lawnberry-safety"
)

echo "Lawnberry System Health Check - $(date)"
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
echo "CPU: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)%"
echo "Memory: $(free | grep Mem | awk '{printf("%.1f%%\n", $3/$2 * 100.0)}')"
echo "Disk: $(df / | tail -1 | awk '{print $5}')"

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

sudo chmod +x /usr/local/bin/lawnberry-health-check

echo "Creating system control script..."
sudo tee /usr/local/bin/lawnberry-system > /dev/null <<'EOF'
#!/bin/bash
# Lawnberry system control script

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
        echo "Starting Lawnberry system..."
        systemctl start lawnberry-system.service
        ;;
    stop)
        echo "Stopping Lawnberry system..."
        for service in "${SERVICES[@]}"; do
            systemctl stop "$service.service" 2>/dev/null || true
        done
        ;;
    restart)
        echo "Restarting Lawnberry system..."
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
        echo "Enabling Lawnberry system..."
        for service in "${SERVICES[@]}"; do
            systemctl enable "$service.service" 2>/dev/null || true
        done
        ;;
    disable)
        echo "Disabling Lawnberry system..."
        for service in "${SERVICES[@]}"; do
            systemctl disable "$service.service" 2>/dev/null || true
        done
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs [service]|enable|disable}"
        echo ""
        echo "Available services for logs:"
        for service in "${SERVICES[@]}"; do
            echo "  ${service#lawnberry-}"
        done
        exit 1
        ;;
esac
EOF

sudo chmod +x /usr/local/bin/lawnberry-system

echo ""
echo "System Integration Installation Complete!"
echo ""
echo "Available commands:"
echo "  lawnberry-system start    - Start the system"
echo "  lawnberry-system stop     - Stop the system"
echo "  lawnberry-system status   - Check system health"
echo "  lawnberry-system logs     - View system logs"
echo "  lawnberry-health-check    - Quick health check"
echo ""
echo "To start the system now:"
echo "  sudo lawnberry-system start"
echo ""
echo "To enable auto-start on boot:"
echo "  sudo lawnberry-system enable"
