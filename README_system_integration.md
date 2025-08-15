# Lawnberry System Integration

The system integration layer provides master orchestration and coordination for all Lawnberry subsystems using native systemd services with comprehensive health monitoring and automatic recovery.

## Overview

The system integration layer consists of:

- **System Manager**: Master orchestration service coordinating all subsystems
- **Service Orchestrator**: Manages individual services with dependency handling
- **Configuration Manager**: Centralized configuration with hot reloading and validation
- **Health Monitor**: Comprehensive system health monitoring with automatic recovery
- **State Machine**: System state management with persistence and safe transitions

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    System Manager                           │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐│
│  │ Service         │ │ Health          │ │ State           ││
│  │ Orchestrator    │ │ Monitor         │ │ Machine         ││
│  └─────────────────┘ └─────────────────┘ └─────────────────┘│
│  ┌─────────────────────────────────────────────────────────┐│
│  │            Configuration Manager                        ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼────┐    ┌─────────▼──────┐    ┌──────▼─────┐
│Communication│    │ Hardware       │    │ Safety     │
│   Service   │    │  Interface     │    │ Monitor    │
└────────────┘    └────────────────┘    └────────────┘
        │                   │                   │
┌───────▼────┐    ┌─────────▼──────┐    ┌──────▼─────┐
│ Data Mgmt  │    │ Sensor Fusion  │    │ Vision     │
│  Service   │    │    Engine      │    │ System     │
└────────────┘    └────────────────┘    └────────────┘
        │                   │                   │
┌───────▼────┐    ┌─────────▼──────┐    ┌──────▼─────┐
│ Weather    │    │ Power Mgmt     │    │ Web API    │
│ Service    │    │   Service      │    │ Backend    │
└────────────┘    └────────────────┘    └────────────┘
```

## System States

The system operates in the following states with safe transitions:

- **INITIALIZING**: System startup and component initialization
- **STARTING**: Services being started in dependency order
- **RUNNING**: Normal operation with all services healthy
- **DEGRADED**: Some non-critical services unhealthy but system operational
- **MAINTENANCE**: Controlled maintenance mode
- **ERROR**: System error requiring intervention
- **SHUTTING_DOWN**: Graceful shutdown in progress
- **STOPPED**: System cleanly stopped
- **EMERGENCY_STOP**: Emergency shutdown due to safety conditions

## Service Dependencies

Services start in the following order with dependency management:

1. **communication** (MQTT broker and messaging)
2. **data_management** (Redis cache and database)
3. **hardware** (Hardware interface layer)
4. **sensor_fusion** (Sensor data processing)
5. **weather** (Weather service)
6. **power_management** (Power monitoring)
7. **safety** (Safety monitoring - critical)
8. **vision** (Computer vision)
9. **web_api** (Web API backend)

## Installation

Run the installation script to set up systemd services:

```bash
chmod +x install_system_integration.sh
./install_system_integration.sh
```

This installs:
- Systemd service files for all components
- Log rotation configuration
- System control scripts
- Health check utilities

## Configuration

System configuration is centralized in `config/system.yaml`:

```yaml
system:
  name: "lawnberry-mower"
  version: "1.0.0"
  log_level: "INFO"
  max_cpu_percent: 80.0
  max_memory_percent: 75.0

services:
  communication:
    critical: true
    restart_policy: "always"
    max_restarts: 5
    restart_delay: 2.0

monitoring:
  alert_thresholds:
    cpu_percent: 90.0
    memory_percent: 85.0
    temperature_celsius: 75.0
```

Environment-specific overrides can be placed in `config/overrides/production/`.

## Service Management

### System Control Commands

```bash
# Start the entire system
sudo lawnberry-system start

# Stop the entire system
sudo lawnberry-system stop

# Check system status
lawnberry-system status

# View system logs
lawnberry-system logs

# View specific service logs
lawnberry-system logs safety

# Enable auto-start on boot
sudo lawnberry-system enable
```

### Individual Service Control

```bash
# Control individual services
sudo systemctl start lawnberry-safety.service
sudo systemctl stop lawnberry-vision.service
sudo systemctl restart lawnberry-communication.service

# Check service status
systemctl status lawnberry-hardware.service

# View service logs
journalctl -f -u lawnberry-sensor-fusion.service
```

## Health Monitoring

The system provides comprehensive health monitoring:

### Service Health
- Process status and responsiveness
- CPU and memory usage per service
- Restart count and error tracking
- Circuit breaker protection

### System Resources
- CPU usage monitoring
- Memory utilization tracking
- Disk space monitoring
- Temperature monitoring (if available)

### Alerts and Recovery
- Configurable alert thresholds
- Automatic restart of failed services
- Exponential backoff for restart attempts
- Emergency shutdown on critical failures

### Health Check Script

```bash
# Quick health check
lawnberry-health-check

# Example output:
# Lawnberry System Health Check - 2024-01-15 10:30:00
# ========================================
# ✓ lawnberry-system: Running
# ✓ lawnberry-communication: Running
# ✓ lawnberry-safety: Running
# ✗ lawnberry-vision: Not running
# 
# System Resources:
# CPU: 25.3%
# Memory: 45.2%
# Disk: 68%
# 
# Overall Status: DEGRADED ⚠
```

## Configuration Management

### Hot Reloading
Configuration changes can be applied without service restart:

```python
from src.system_integration.config_manager import ConfigManager

config_manager = ConfigManager()
await config_manager.load_all_configs()

# Register for change notifications
config_manager.register_change_callback('system.yaml', on_config_change)

# Enable hot reloading
await config_manager.start_hot_reload('system.yaml')
```

### Backup and Restore
Configuration changes are automatically backed up:

```bash
# View available backups
ls /var/lib/lawnberry/config_backups/

# Restore from backup (programmatically)
await config_manager.restore_config('system.yaml', '20240115_103000')
```

## State Persistence

System state is persisted across reboots in `/var/lib/lawnberry/system_state.json`:

```json
{
  "current_state": "running",
  "previous_state": "starting", 
  "timestamp": "2024-01-15T10:30:00",
  "state_data": {},
  "recent_history": [...]
}
```

## Security Features

### Service Isolation
Each service runs with:
- Dedicated user/group permissions
- Restricted filesystem access
- System call filtering
- Resource limits

### Audit Logging
All system operations are logged with:
- Structured JSON formatting
- Correlation IDs for tracking
- Security event logging
- Log rotation and retention

## Performance Monitoring

### Resource Usage
- Real-time CPU, memory, and disk monitoring
- Per-service resource tracking
- Historical metrics storage
- Performance trend analysis

### Optimization
- Dynamic CPU scaling based on load
- Memory cleanup procedures
- Connection pooling
- Efficient logging and metrics collection

## Failure Recovery

### Automatic Recovery
- Service restart with exponential backoff
- Circuit breaker pattern for failing services
- Graceful degradation for non-critical services
- Emergency stop procedures for safety

### Manual Recovery
```bash
# Force restart all services
sudo lawnberry-system restart

# Reset a specific service
sudo systemctl reset-failed lawnberry-vision.service
sudo systemctl start lawnberry-vision.service

# Emergency stop
sudo systemctl stop lawnberry-system.service
```

## Testing

Run the comprehensive test suite:

```bash
python test_system_integration.py
```

Tests cover:
- Configuration loading and validation
- Service orchestration and dependencies
- Health monitoring functionality
- State machine transitions
- Failure recovery procedures
- System persistence

## Troubleshooting

### Common Issues

**Service fails to start:**
```bash
# Check service status
systemctl status lawnberry-service.service

# View detailed logs
journalctl -u lawnberry-service.service --since "1 hour ago"

# Check dependencies
systemctl list-dependencies lawnberry-service.service
```

**High resource usage:**
```bash
# Check system resources
lawnberry-health-check

# View per-service usage
systemctl status lawnberry-*.service
```

**Configuration errors:**
```bash
# Validate configuration
python -c "
from src.system_integration.config_manager import ConfigManager
import asyncio
async def test():
    cm = ConfigManager()
    await cm.load_all_configs()
    print('Configuration valid')
asyncio.run(test())
"
```

### Log Locations
- System logs: `/var/log/lawnberry/system.log`
- Service logs: `journalctl -u lawnberry-service.service`
- Health metrics: `/var/lib/lawnberry/health_metrics.json`
- State persistence: `/var/lib/lawnberry/system_state.json`

## Development

### Adding New Services

1. Create service configuration in `config/system.yaml`
2. Add systemd service file
3. Update service orchestrator dependencies
4. Add health monitoring
5. Test integration

### Configuration Schema

Configuration files should follow the established patterns:
- YAML format with validation
- Environment-specific overrides
- Hot reloading support
- Backup/restore capability

## Integration Points

The system integration layer coordinates with:
- **MQTT Communication**: Service discovery and messaging
- **Redis Cache**: State sharing and performance data
- **Web API**: System status and control endpoints
- **Safety System**: Emergency stop coordination
- **Hardware Interface**: Resource sharing and coordination

This provides a robust, production-ready orchestration system for the autonomous mower with comprehensive monitoring, automatic recovery, and safe operation.

## OLED Command Monitor (Optional)

- Default hardware: SSD1306 128x32 at I2C `0x3C`.
- The system mirrors RoboHAT-bound serial commands on the OLED in real-time, if present.
- Environment overrides:
  - `OLED_HEIGHT=32` (default `32`), `OLED_WIDTH=128` (default `128`)
  - `OLED_ADDR=0x3C` (I2C address)
  - `OLED_DRIVER=ssd1306` (or `sh1106` if that module is installed)
  - `OLED_DISABLE=1` to disable display rendering at runtime (file logging still enabled)
  - `OLED_LOG_PATH=data/robohat_commands.log` rolling log file (default path)

Quick test:

```bash
source venv/bin/activate
export PYTHONPATH=$PWD
OLED_HEIGHT=32 timeout 25s python3 tests/hardware/robohat_oled_monitor_test.py
```
