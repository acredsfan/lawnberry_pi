# LawnBerry Pi v2 Systemd Services Installation Script
# This script installs and enables the LawnBerry Pi systemd services
# Run as root: sudo bash install_services.sh

#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="/etc/systemd/system"

echo "Installing LawnBerry Pi v2 systemd services..."

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)" 
   exit 1
fi

# Copy service files
echo "Copying service files to $SYSTEMD_DIR..."
cp "$SCRIPT_DIR/lawnberry-database.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/lawnberry-backend.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/lawnberry-sensors.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/lawnberry-health.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/lawnberry-frontend.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/lawnberry-camera.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/lawnberry-remote-access.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/lawnberry-acme-renew.service" "$SYSTEMD_DIR/"
cp "$SCRIPT_DIR/lawnberry-acme-renew.timer" "$SYSTEMD_DIR/"

# Set correct permissions
chmod 644 "$SYSTEMD_DIR/lawnberry-"*.service
chmod 644 "$SYSTEMD_DIR/lawnberry-"*.timer
chown root:root "$SYSTEMD_DIR/lawnberry-"*.service
chown root:root "$SYSTEMD_DIR/lawnberry-"*.timer

# Reload systemd daemon
echo "Reloading systemd daemon..."
systemctl daemon-reload

# Enable services (but don't start yet)
echo "Enabling LawnBerry Pi services..."
systemctl enable lawnberry-database.service
systemctl enable lawnberry-backend.service
systemctl enable lawnberry-sensors.service
systemctl enable lawnberry-health.service
systemctl enable lawnberry-frontend.service
systemctl enable lawnberry-camera.service
systemctl enable lawnberry-remote-access.service
systemctl enable lawnberry-acme-renew.service
systemctl enable lawnberry-acme-renew.timer

echo ""
echo "LawnBerry Pi v2 services installed and enabled!"
echo ""
echo "To start all services:"
echo "  sudo systemctl start lawnberry-database"
echo "  sudo systemctl start lawnberry-backend"
echo "  sudo systemctl start lawnberry-sensors"
echo "  sudo systemctl start lawnberry-health"
echo "  sudo systemctl start lawnberry-frontend"
echo "  sudo systemctl start lawnberry-camera"
echo "  sudo systemctl start lawnberry-remote-access"
echo "  sudo systemctl start lawnberry-acme-renew.timer"
echo ""
echo "To check service status:"
echo "  sudo systemctl status lawnberry-backend"
echo "  sudo systemctl status lawnberry-camera"
echo "  sudo systemctl status lawnberry-remote-access"
echo ""
echo "To view logs:"
echo "  sudo journalctl -u lawnberry-backend -f"
echo "  sudo journalctl -u lawnberry-frontend -f"
echo "  sudo journalctl -u lawnberry-camera -f"
echo "  sudo journalctl -u lawnberry-remote-access -f"
echo ""
echo "Services will automatically start on boot."