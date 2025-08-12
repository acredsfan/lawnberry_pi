# LawnBerry Field Deployment Guide

This comprehensive guide covers the complete deployment process for LawnBerry autonomous mower systems in production environments.

## Table of Contents

1. [Pre-Deployment Preparation](#pre-deployment-preparation)
2. [Hardware Setup](#hardware-setup)
3. [Automated Installation](#automated-installation)
4. [Configuration Validation](#configuration-validation)
5. [System Testing](#system-testing)
6. [Monitoring Setup](#monitoring-setup)
7. [Remote Update Configuration](#remote-update-configuration)
8. [Troubleshooting](#troubleshooting)
9. [Support Procedures](#support-procedures)

## Pre-Deployment Preparation

### Required Equipment

**Hardware:**
- Raspberry Pi 4B or 5 (minimum 4GB RAM, 8GB recommended)
- MicroSD card (minimum 32GB, Class 10)
- Power supply (official Raspberry Pi power supply recommended)
- Network connection (Ethernet or WiFi)
- All LawnBerry hardware components (see Hardware Overview)

**Software:**
- Fresh Raspberry Pi OS Bookworm installation
- LawnBerry deployment package (.tar.gz)
- Field deployment toolkit (USB drive with utilities)

### Pre-Installation Checklist

- [ ] Hardware assembled and connected
- [ ] Raspberry Pi OS Bookworm installed and updated
- [ ] Network connectivity verified
- [ ] SSH access configured (if needed)
- [ ] All required environment variables prepared
- [ ] Deployment package verified (checksum)

## Hardware Setup

### GPIO Pin Verification

Before installation, verify all GPIO connections match the configuration:

| Component | GPIO Pin | Function |
|-----------|----------|----------|
| Motor Left Direction | 15 | Digital Output |
| Motor Right Direction | 16 | Digital Output |
| Motor Left PWM | 31 | PWM Output |
| Motor Right PWM | 32 | PWM Output |
| Safety Stop | 18 | Digital Input |
| Emergency Stop | 22 | Digital Input |

### I2C Device Verification

Verify I2C devices are detected:

```bash
sudo i2cdetect -y 1
```

Expected devices:
- `0x29`: ToF Sensor 1
- `0x30`: ToF Sensor 2
- `0x40`: INA3221 Power Monitor
- `0x76`: BME280 Environmental Sensor
- `0x3c`: SSD1306 OLED Display

### Camera Module Testing

Test camera functionality:

```bash
rpicam-hello --timeout 2000
rpicam-vid -t 5000 -o test.h264
```

## Automated Installation

### Using the Automated Deployment Script

The automated deployment script provides zero-touch installation:

```bash
# Extract deployment package
tar -xzf lawnberry-1.0.0.tar.gz
cd lawnberry-1.0.0

# Run automated deployment (production mode)
sudo ./scripts/deploy_automated.sh ../lawnberry-1.0.0.tar.gz

# Alternative: Development mode with monitoring disabled
sudo ./scripts/deploy_automated.sh --mode development --no-monitoring ../lawnberry-1.0.0.tar.gz
```

### Deployment Script Options

| Option | Description |
|--------|-------------|
| `--mode MODE` | Deployment mode: production, development, testing |
| `--skip-validation` | Skip pre-deployment validation |
| `--no-monitoring` | Disable monitoring setup |
| `--no-remote-updates` | Disable remote update system |
| `--force` | Force deployment despite validation failures |

### Manual Installation Process

If automated deployment is not suitable:

1. **Extract Package:**
   ```bash
   tar -xzf lawnberry-1.0.0.tar.gz
   cd lawnberry-1.0.0
   ```

2. **Run Installation:**
   ```bash
   sudo ./install.sh
   ```

3. **Verify Installation:**
   ```bash
   sudo systemctl status lawnberry-system
   ```

## Configuration Validation

### Automated Configuration Validation

Run comprehensive configuration validation:

```bash
# Validate all configurations
sudo python3 /opt/lawnberry/scripts/validate_deployment.py

# Validate specific categories
sudo python3 /opt/lawnberry/scripts/validate_deployment.py --categories hardware network

# Export validation results
sudo python3 /opt/lawnberry/scripts/validate_deployment.py --output validation_results.json
```

### Manual Configuration Checks

#### System Configuration

Verify system configuration in `/opt/lawnberry/config/system.yaml`:

```yaml
system:
  system_id: "lawnberry_001"
  operation_mode: "production"
  log_level: "INFO"
  data_directory: "/var/lib/lawnberry"
  config_directory: "/opt/lawnberry/config"
```

#### Hardware Configuration

Check hardware configuration in `/opt/lawnberry/config/hardware.yaml`:

```yaml
hardware:
  gpio_pins:
    motor_left_dir: 15
    motor_right_dir: 16
    motor_left_pwm: 31
    motor_right_pwm: 32
    safety_stop: 18
    emergency_stop: 22

  i2c_devices:
    tof_sensor_1: 0x29
    tof_sensor_2: 0x30
    power_monitor: 0x40
    environmental: 0x76
    display: 0x3c
```

### Environment Variables

Ensure all required environment variables are set:

```bash
# Check environment variables
sudo -u lawnberry printenv | grep -E "(OPENWEATHER|GOOGLE_MAPS|JWT)"

# Required variables:
# OPENWEATHER_API_KEY=your_openweather_api_key
# REACT_APP_GOOGLE_MAPS_API_KEY=your_google_maps_api_key
# JWT_SECRET_KEY=your_jwt_secret_key
```

## System Testing

### Service Status Verification

Check all LawnBerry services are running:

```bash
# Check individual services
sudo systemctl status lawnberry-system
sudo systemctl status lawnberry-hardware
sudo systemctl status lawnberry-safety
sudo systemctl status lawnberry-web-api
sudo systemctl status lawnberry-communication

# Check all services at once
sudo systemctl status lawnberry-* --no-pager
```

### Hardware Interface Testing

Test hardware interfaces:

```bash
# Run hardware detection
sudo python3 /opt/lawnberry/scripts/hardware_detection.py --validate

# Test specific components
sudo python3 /opt/lawnberry/examples/hardware_interface_demo.py
```

### Web Interface Testing

Verify web interface accessibility:

```bash
# Test web API health
curl -f http://localhost:8000/health

# Test web interface (replace IP with actual IP)
curl -f http://192.168.1.100:8000/
```

### Safety System Testing

**⚠️ IMPORTANT:** Always test safety systems before operational use.

```bash
# Test emergency stop
sudo python3 /opt/lawnberry/examples/safety_system_demo.py --test-emergency-stop

# Test obstacle detection
sudo python3 /opt/lawnberry/examples/safety_system_demo.py --test-obstacle-detection
```

## Monitoring Setup

### Automated Monitoring Setup

The monitoring system is automatically configured during deployment:

```bash
# View monitoring dashboard
sudo -u lawnberry /opt/lawnberry/monitoring/scripts/dashboard.sh

# Check monitoring service
sudo systemctl status lawnberry-monitor

# View health check logs
sudo tail -f /var/log/lawnberry/monitoring/health_check.log
```

### Manual Monitoring Configuration

If monitoring was not set up during deployment:

```bash
# Run monitoring setup script
sudo /opt/lawnberry/scripts/setup_monitoring.sh

# Start monitoring service
sudo systemctl start lawnberry-monitor
sudo systemctl enable lawnberry-monitor
```

### Monitoring Features

- **Real-time Health Checks:** CPU, memory, disk, temperature monitoring
- **Service Monitoring:** Automatic detection of failed services
- **Alert System:** Configurable alerts for critical issues
- **Dashboard:** Console-based system status dashboard
- **Automated Backups:** Scheduled system backups
- **Log Management:** Automatic log rotation and cleanup

## Remote Update Configuration

### Update Server Configuration

Configure remote update server in `/opt/lawnberry/config/deployment.yaml`:

```yaml
deployment:
  remote_updates:
    enabled: true
    update_server_url: "https://updates.lawnberry.com/api/v1"
    check_interval: 3600
    auto_approve_security: true
    auto_approve_config: true
    require_approval_features: true
```

### User Approval Workflow

The remote update system supports user approval for non-critical updates:

1. **Automatic Updates:** Security and configuration updates are auto-approved
2. **Manual Approval:** Feature updates require user approval via web interface
3. **Emergency Updates:** Critical security updates can bypass approval
4. **Rollback Capability:** Failed updates automatically rollback

### Update Management Commands

```bash
# Check for updates manually
sudo -u lawnberry python3 -c "
import asyncio
from src.system_integration.remote_update_manager import RemoteUpdateManager
from src.system_integration.config_manager import ConfigManager
from src.system_integration.deployment_manager import DeploymentManager
from src.system_integration.system_monitor import SystemMonitor
from src.system_integration.health_monitor import HealthMonitor

async def check_updates():
    config_manager = ConfigManager()
    deployment_manager = DeploymentManager(config_manager, None, None)
    system_monitor = SystemMonitor(config_manager)
    health_monitor = HealthMonitor()

    update_manager = RemoteUpdateManager(config_manager, deployment_manager, system_monitor, health_monitor)
    await update_manager.initialize()
    updates = await update_manager.check_for_updates(force=True)
    print(f'Found {len(updates)} updates')

asyncio.run(check_updates())
"

# View pending updates
curl -s http://localhost:8000/api/system/updates/pending | python3 -m json.tool

# Approve update (via web interface or API)
curl -X POST http://localhost:8000/api/system/updates/approve -d '{"update_id": "update_123", "approved_by": "admin"}'
```

## Troubleshooting

### Common Installation Issues

#### Insufficient Disk Space

**Problem:** Installation fails with "No space left on device"

**Solution:**
```bash
# Check disk usage
df -h

# Clean up system
sudo apt clean
sudo apt autoremove

# Expand filesystem if needed
sudo raspi-config --expand-rootfs
```

#### Service Startup Failures

**Problem:** Services fail to start after installation

**Solution:**
```bash
# Check service logs
sudo journalctl -u lawnberry-system -f

# Check service dependencies
sudo systemctl list-dependencies lawnberry-system

# Restart services manually
sudo systemctl daemon-reload
sudo systemctl restart lawnberry-system
```

#### Hardware Detection Issues

**Problem:** Hardware components not detected

**Solution:**
```bash
# Enable I2C and SPI
sudo raspi-config

# Check GPIO access
ls -la /dev/gpiomem

# Verify I2C devices
sudo i2cdetect -y 1

# Check camera
vcgencmd get_camera
```

### Performance Issues

#### High CPU Usage

**Problem:** System shows consistently high CPU usage

**Solution:**
```bash
# Check CPU usage by process
top -p $(pgrep -d',' -f lawnberry)

# Adjust service priorities
sudo systemctl edit lawnberry-system.service
# Add: [Service]
#      CPUQuota=50%

# Check for runaway processes
sudo systemctl status lawnberry-*
```

#### Memory Issues

**Problem:** System runs out of memory

**Solution:**
```bash
# Check memory usage
free -h

# Identify memory-intensive processes
sudo ps aux --sort=-%mem | grep lawnberry

# Adjust memory limits
sudo systemctl edit lawnberry-web-api.service
# Add: [Service]
#      MemoryMax=500M
```

### Network Connectivity Issues

#### Web Interface Not Accessible

**Problem:** Cannot access web interface

**Solution:**
```bash
# Check web API service
sudo systemctl status lawnberry-web-api

# Check port binding
sudo netstat -tulpn | grep :8000

# Check firewall
sudo ufw status

# Test local access
curl -v http://localhost:8000/health
```

#### External API Issues

**Problem:** Weather or GPS services not working

**Solution:**
```bash
# Test internet connectivity
ping -c 4 api.openweathermap.org

# Check API keys
sudo -u lawnberry printenv | grep API_KEY

# Test API access
curl "https://api.openweathermap.org/data/2.5/weather?q=London&appid=YOUR_API_KEY"
```

## Support Procedures

### Log Collection

For support purposes, collect system logs:

```bash
# Create support bundle
sudo /opt/lawnberry/scripts/create_support_bundle.sh

# Manual log collection
sudo tar -czf lawnberry_logs_$(date +%Y%m%d).tar.gz \
  /var/log/lawnberry/ \
  /var/lib/lawnberry/monitoring/ \
  /opt/lawnberry/config/ \
  /etc/systemd/system/lawnberry-*
```

### System Health Report

Generate comprehensive system health report:

```bash
# Generate detailed health report
sudo python3 /opt/lawnberry/scripts/validate_deployment.py \
  --output health_report.json

# Create system snapshot
sudo /opt/lawnberry/scripts/create_system_snapshot.sh
```

### Emergency Recovery

#### System Recovery Mode

If the system fails to start normally:

1. **Boot to Single User Mode:**
   - Edit boot command line
   - Add `systemd.unit=rescue.target`

2. **Run Emergency Recovery:**
   ```bash
   sudo /opt/lawnberry/scripts/emergency_recovery.sh
   ```

3. **Restore from Backup:**
   ```bash
   sudo /opt/lawnberry/scripts/restore_system.sh /path/to/backup
   ```

#### Factory Reset

Complete system reset:

```bash
# Stop all services
sudo systemctl stop lawnberry-*

# Run uninstaller
sudo /opt/lawnberry/uninstall.sh

# Clean system
sudo rm -rf /opt/lawnberry /var/lib/lawnberry /var/log/lawnberry

# Reinstall from scratch
# Follow installation procedures
```

### Remote Support Access

For remote troubleshooting:

```bash
# Enable SSH (if not already enabled)
sudo systemctl enable ssh
sudo systemctl start ssh

# Create temporary support user (remove after support session)
sudo useradd -m -s /bin/bash support
sudo usermod -aG sudo support
sudo passwd support

# Generate system report for remote analysis
sudo /opt/lawnberry/scripts/generate_support_report.sh
```

## Best Practices

### Security

- Change default passwords immediately after installation
- Use strong, unique API keys for all external services
- Regularly update system packages
- Monitor access logs for suspicious activity
- Implement network segmentation if possible

### Maintenance

- Review monitoring alerts daily
- Perform weekly system health checks
- Update software monthly (or as security updates are available)
- Clean and inspect hardware quarterly
- Create configuration backups before major changes

### Documentation

- Document any configuration changes
- Maintain installation and maintenance logs
- Record hardware serial numbers and versions
- Document local network configuration
- Keep deployment and troubleshooting notes

## Contact Information

### Technical Support

- **Email:** support@lawnberry.com
- **Phone:** 1-800-LAWNBERRY
- **Web:** https://support.lawnberry.com

### Emergency Support

- **24/7 Hotline:** 1-800-EMERGENCY
- **Critical Issues:** critical@lawnberry.com

### Community Support

- **Forum:** https://community.lawnberry.com
- **GitHub:** https://github.com/lawnberry/lawnberry
- **Documentation:** https://docs.lawnberry.com

---

**Document Version:** 1.0
**Last Updated:** $(date +%Y-%m-%d)
**Valid For:** LawnBerry v1.0.0 and later
