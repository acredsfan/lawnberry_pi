# Raspberry Pi OS Bookworm Compatibility Validation Checklist

This checklist provides comprehensive automated verification of Bookworm compatibility for the LawnBerryPi system.

## Automated Validation Commands

### Quick Validation (5-10 minutes)
```bash
# Run quick compatibility check
python3 scripts/validate_bookworm_installation.py --quick

# Run Bookworm-specific tests
python3 -m pytest tests/integration/test_bookworm_compatibility.py -v

# Run comprehensive validation suite
python3 tests/automation/bookworm_validation_suite.py
```

### Full Validation (24+ hours)
```bash
# Run complete validation including 24-hour stability test
python3 scripts/validate_bookworm_installation.py

# Run performance benchmarks
python3 -m pytest tests/performance/test_performance_benchmarks.py -v
```

## Manual Verification Steps

### 1. System Detection and Requirements ✓
- [ ] **OS Detection**: Raspberry Pi OS Bookworm detected
  ```bash
  grep "VERSION_CODENAME=bookworm" /etc/os-release
  ```
- [ ] **Python Version**: Python 3.11+ detected
  ```bash
  python3 --version  # Should show 3.11.x or higher
  ```
- [ ] **systemd Version**: systemd 252+ detected
  ```bash
  systemctl --version  # Should show 252 or higher
  ```
- [ ] **Hardware Model**: Raspberry Pi 4 Model B or Raspberry Pi 5 detected
  ```bash
  cat /proc/device-tree/model
  ```

### 2. Installation System Validation ✓
- [ ] **Installation Script**: Completes without manual intervention
  ```bash
  bash scripts/install_lawnberry.sh 2>&1 | tee install.log
  grep -c "ERROR" install.log  # Should be 0
  ```
- [ ] **Directory Structure**: All required directories created
  ```bash
  test -d /opt/lawnberry && test -d /var/log/lawnberry && test -d /var/lib/lawnberry
  ```
- [ ] **Virtual Environment**: Python virtual environment created and functional
  ```bash
  test -f /opt/lawnberry/venv/bin/python3
  /opt/lawnberry/venv/bin/python3 --version
  ```
- [ ] **Permissions**: Correct file and directory permissions
  ```bash
  ls -la /opt/lawnberry/ | grep lawnberry  # Should show lawnberry:lawnberry ownership
  ```

### 3. Software Dependencies Validation ✓
- [ ] **Python Packages**: All requirements.txt packages installed
  ```bash
  /opt/lawnberry/venv/bin/pip list --format=freeze > installed.txt
  /opt/lawnberry/venv/bin/pip check  # Should show no conflicts
  ```
- [ ] **Critical Dependencies**: Core functionality packages available
  ```bash
  /opt/lawnberry/venv/bin/python3 -c "import redis, fastapi, opencv, asyncio_mqtt"
  ```
- [ ] **Hardware Dependencies**: Raspberry Pi specific packages
  ```bash
  /opt/lawnberry/venv/bin/python3 -c "import lgpio, gpiozero, smbus2, picamera2"
  ```
- [ ] **Version Compatibility**: Bookworm-optimized versions
  ```bash
  /opt/lawnberry/venv/bin/python3 -c "import opencv as cv2; print(cv2.__version__)"  # Should be 4.8+
  ```

### 4. Hardware Interface Compatibility ✓
- [ ] **GPIO Interface**: GPIO pins accessible and functional
  ```bash
  python3 scripts/hardware_detection.py --test-gpio
  ```
- [ ] **I2C Interface**: I2C bus operational at 400kHz
  ```bash
  i2cdetect -y 1  # Should show I2C devices
  grep "i2c_arm_baudrate=400000" /boot/config.txt
  ```
- [ ] **UART Interface**: Serial interfaces configured
  ```bash
  ls -la /dev/ttyAMA* /dev/ttyACM*
  ```
- [ ] **Camera Interface**: Camera module detected
  ```bash
  rpicam-hello --list-cameras  # Should list available cameras
  ```
- [ ] **USB Interface**: USB devices properly enumerated
  ```bash
  lsusb  # Should show connected USB devices
  ```

### 5. System Integration Validation ✓
- [ ] **Service Files**: All 11 microservices configured
  ```bash
  ls -1 /opt/lawnberry/src/*/lawnberry-*.service | wc -l  # Should be >= 10
  ```
- [ ] **Service Installation**: systemd services installed and enabled
  ```bash
  systemctl list-unit-files | grep lawnberry  # Should show enabled services
  ```
- [ ] **Service Dependencies**: Proper startup order configured
  ```bash
  systemctl show lawnberry-system.service --property=After
  ```
- [ ] **Inter-service Communication**: MQTT and Redis connectivity
  ```bash
  systemctl is-active redis-server mosquitto
  ```

### 6. Service Startup and Stability ✓
- [ ] **Service Startup**: All critical services start successfully
  ```bash
  sudo systemctl start lawnberry-system.service
  systemctl is-active lawnberry-system.service  # Should show "active"
  ```
- [ ] **Service Health**: Services maintain healthy status
  ```bash
  lawnberry-health-check  # Should exit with code 0
  ```
- [ ] **Resource Usage**: Services operate within memory/CPU limits
  ```bash
  systemctl show lawnberry-system.service --property=MemoryCurrent,CPUUsageNSec
  ```
- [ ] **Error Handling**: Services recover from failures gracefully
  ```bash
  journalctl -u lawnberry-system.service --since "1 hour ago" | grep -i error
  ```

### 7. Performance Benchmarks ✓
- [ ] **Boot Time**: System boots within acceptable timeframe
  ```bash
  systemd-analyze  # Should show boot time < 60 seconds
  ```
- [ ] **Service Startup**: Services start within timeout limits
  ```bash
  systemd-analyze critical-chain lawnberry-system.service
  ```
- [ ] **I/O Performance**: File system operations meet requirements
  ```bash
  dd if=/dev/zero of=/tmp/test bs=1M count=100 oflag=sync  # Should complete < 30s
  ```
- [ ] **Memory Performance**: Memory allocation/deallocation efficient
  ```bash
  python3 -c "import time; start=time.time(); [i for i in range(100000)]; print(f'Time: {time.time()-start:.3f}s')"
  ```
- [ ] **Network Performance**: Web UI responsive
  ```bash
  curl -o /dev/null -s -w "%{time_total}\n" http://localhost:8080/  # Should be < 2s
  ```

### 8. Bookworm-Specific Optimizations ✓
- [ ] **Memory Management**: Bookworm memory optimizations applied
  ```bash
  test -f /etc/sysctl.d/99-lawnberry-bookworm.conf
  sysctl vm.swappiness  # Should show 10
  ```
- [ ] **CPU Governor**: Performance governor configured for Pi 4B
  ```bash
  cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor  # Should show "performance"
  ```
- [ ] **I2C Optimization**: I2C bus speed optimized
  ```bash
  grep "dtparam=i2c_arm_baudrate=400000" /boot/config.txt
  ```
- [ ] **Security Hardening**: systemd 252+ security features enabled
  ```bash
  grep "ProtectClock=true" /opt/lawnberry/src/system_integration/lawnberry-system.service
  ```

### 9. Security and Hardening ✓
- [ ] **Service Isolation**: Services run with minimal privileges
  ```bash
  systemctl show lawnberry-system.service --property=User,Group,NoNewPrivileges
  ```
- [ ] **Filesystem Protection**: Read-only system protection enabled
  ```bash
  systemctl show lawnberry-system.service --property=ProtectSystem,ProtectHome
  ```
- [ ] **Network Security**: Restricted network access
  ```bash
  systemctl show lawnberry-system.service --property=RestrictAddressFamilies
  ```
- [ ] **System Call Filtering**: System call restrictions applied
  ```bash
  systemctl show lawnberry-system.service --property=SystemCallFilter
  ```

### 10. Automated Testing Framework ✓
- [ ] **Test Suite**: Comprehensive test coverage available
  ```bash
  python3 -m pytest tests/ --collect-only | grep "collected"  # Should show > 50 tests
  ```
- [ ] **Integration Tests**: All integration tests pass
  ```bash
  python3 -m pytest tests/integration/ -v
  ```
- [ ] **Hardware Tests**: Hardware interface tests pass
  ```bash
  python3 -m pytest tests/hardware/ -v
  ```
- [ ] **Performance Tests**: Performance benchmarks within limits
  ```bash
  python3 -m pytest tests/performance/ -v --benchmark-only
  ```

## 24-Hour Stability Test ✓

### Automated Stability Monitoring
```bash
# Start 24-hour stability test
python3 scripts/validate_bookworm_installation.py --output /tmp/stability_report.json

# Monitor system resources during test
watch -n 300 'echo "=== $(date) ==="; systemctl is-active lawnberry-*.service; free -h; df -h'
```

### Manual Stability Verification
- [ ] **Service Uptime**: All services maintain > 99% uptime
- [ ] **Memory Stability**: Memory usage remains stable (no leaks)
- [ ] **CPU Stability**: CPU usage patterns remain consistent
- [ ] **Error Rate**: Error rate < 0.1% of total operations
- [ ] **Recovery Testing**: Services recover from simulated failures

## Validation Reports

### Generate Comprehensive Report
```bash
# Generate complete validation report
{
  echo "# LawnBerryPi Bookworm Compatibility Report"
  echo "Generated: $(date)"
  echo ""

  echo "## System Information"
  lsb_release -a
  cat /proc/device-tree/model
  python3 --version
  systemctl --version | head -1

  echo ""
  echo "## Validation Results"
  python3 scripts/validate_bookworm_installation.py --quick
  python3 tests/automation/bookworm_validation_suite.py

} > bookworm_compatibility_report.md
```

### Success Criteria
- ✅ **Installation**: Completes without errors on fresh Bookworm
- ✅ **Services**: All 11 microservices start and remain stable
- ✅ **Hardware**: All hardware interfaces operational
- ✅ **Performance**: Meets or exceeds baseline requirements
- ✅ **Stability**: 24-hour operation without critical failures
- ✅ **Testing**: Automated test suite validates ongoing compatibility

### Failure Investigation
If any validation fails:
1. **Check logs**: `journalctl -u lawnberry-system.service --since "1 hour ago"`
2. **Run diagnostics**: `lawnberry-system status`
3. **Check hardware**: `python3 scripts/hardware_detection.py`
4. **Validate environment**: `python3 -m pytest tests/integration/test_bookworm_compatibility.py -v -s`
5. **Review installation**: Check `/tmp/lawnberry_install.log`

## Continuous Compatibility Monitoring

### Daily Automated Checks
```bash
# Add to crontab for daily validation
0 2 * * * /opt/lawnberry/venv/bin/python3 /opt/lawnberry/tests/automation/bookworm_validation_suite.py
```

### System Health Monitoring
```bash
# Regular health checks
*/15 * * * * /usr/local/bin/lawnberry-health-check
```

This checklist ensures comprehensive validation of Raspberry Pi OS Bookworm compatibility with automated verification wherever possible.
