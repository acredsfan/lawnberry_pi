# LawnBerry Pi v2 - Production Cutover & Rollback Plan

This document outlines the complete cutover plan for transitioning from LawnBerry Pi v1 to v2, validation procedures, and rollback strategies.

## Table of Contents

1. [Overview](#overview)
2. [Pre-Cutover Checklist](#pre-cutover-checklist)
3. [Cutover Procedure](#cutover-procedure)
4. [Validation Steps](#validation-steps)
5. [Rollback Plan](#rollback-plan)
6. [Post-Cutover Tasks](#post-cutover-tasks)
7. [Troubleshooting](#troubleshooting)

## Overview

### Cutover Strategy

**Type**: Blue-Green Deployment with In-Place Migration Option
**Downtime**: Minimal (< 5 minutes for critical functions)
**Rollback Time**: < 10 minutes if needed
**Data Migration**: Automated with validation

### Migration Phases

1. **Preparation Phase**: System backup and preparation
2. **Migration Phase**: Data migration and service transition
3. **Validation Phase**: Comprehensive system testing
4. **Cutover Phase**: Switch to production v2 system
5. **Stabilization Phase**: Monitor and optimize

### Success Criteria

- [ ] All core services operational (API, frontend, sensors)
- [ ] Data successfully migrated with integrity validation
- [ ] Authentication system functional
- [ ] Remote access working (if configured)
- [ ] Camera and telemetry systems operational
- [ ] Emergency stop and safety systems verified
- [ ] Performance metrics within acceptable ranges

## Pre-Cutover Checklist

### System Preparation

#### 1. Backup Current System
```bash
# Create comprehensive v1 backup
sudo systemctl stop lawnberry-v1
sudo mkdir -p /backup/lawnberry-v1-$(date +%Y%m%d)
sudo cp -r /home/pi/lawnberry-v1 /backup/lawnberry-v1-$(date +%Y%m%d)/
sudo cp -r /var/lib/lawnberry-v1 /backup/lawnberry-v1-$(date +%Y%m%d)/
sudo cp -r /etc/lawnberry-v1 /backup/lawnberry-v1-$(date +%Y%m%d)/

# Backup database with integrity check
sudo sqlite3 /var/lib/lawnberry-v1/main.db ".backup /backup/lawnberry-v1-$(date +%Y%m%d)/main.db"
sudo sqlite3 /backup/lawnberry-v1-$(date +%Y%m%d)/main.db "PRAGMA integrity_check;"
```

#### 2. Verify v2 Installation
```bash
# Check v2 system health
cd /home/pi/lawnberry/lawnberry-rebuild
lawnberry-pi system check --comprehensive

# Verify all services are installed
sudo systemctl list-unit-files | grep lawnberry

# Test v2 services without starting production
SIM_MODE=1 sudo systemctl start lawnberry-database
SIM_MODE=1 sudo systemctl start lawnberry-backend
SIM_MODE=1 sudo systemctl start lawnberry-frontend
```

#### 3. Hardware Verification
```bash
# Test all hardware components
lawnberry-pi hardware test --all --verbose

# Verify sensor connectivity
lawnberry-pi sensors test --connectivity --calibration

# Test camera system
lawnberry-pi camera test --capture --streaming

# Verify GPS functionality
lawnberry-pi gps test --signal-acquisition --accuracy
```

#### 4. Network and Security
```bash
# Test network connectivity
lawnberry-pi network test --external --internal --dns

# Verify authentication system
lawnberry-pi auth test --all-levels --verbose

# Test remote access (if configured)
lawnberry-pi remote-access test --all-methods
```

### Data Migration Preparation

#### 1. Analyze v1 Data
```bash
# Analyze v1 database structure
lawnberry-pi migrate analyze --source-db /var/lib/lawnberry-v1/main.db

# Check data integrity
lawnberry-pi migrate validate --source-db /var/lib/lawnberry-v1/main.db

# Generate migration report
lawnberry-pi migrate plan --source-db /var/lib/lawnberry-v1/main.db --report
```

#### 2. Test Migration (Dry Run)
```bash
# Perform dry-run migration
lawnberry-pi migrate test-run \
    --source-db /var/lib/lawnberry-v1/main.db \
    --target-db /tmp/test-migration.db \
    --validate-only

# Verify test migration results
lawnberry-pi migrate verify --db /tmp/test-migration.db --comprehensive
```

### Environmental Preparation

#### 1. System Resources
```bash
# Check system resources
free -h
df -h
lscpu
vcgencmd measure_temp

# Optimize system performance
sudo systemctl stop lawnberry-v1
sudo systemctl stop unnecessary-services
echo performance | sudo tee /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
```

#### 2. Maintenance Window
- [ ] Schedule maintenance window (recommend off-season or overnight)
- [ ] Notify users of planned downtime
- [ ] Ensure physical access to Pi during cutover
- [ ] Have emergency contact information ready

## Cutover Procedure

### Phase 1: Final Preparation (5 minutes)

```bash
# Stop v1 services
sudo systemctl stop lawnberry-v1-*
sudo systemctl disable lawnberry-v1-*

# Final v1 backup
sudo sqlite3 /var/lib/lawnberry-v1/main.db ".backup /backup/final-v1-backup-$(date +%Y%m%d-%H%M).db"

# Verify v1 services stopped
sudo systemctl status lawnberry-v1-backend lawnberry-v1-frontend
```

### Phase 2: Data Migration (10-15 minutes)

```bash
# Initialize v2 database
lawnberry-pi database init --clean

# Migrate v1 data to v2
lawnberry-pi migrate execute \
    --source-db /var/lib/lawnberry-v1/main.db \
    --target-db /var/lib/lawnberry/main.db \
    --validate \
    --progress

# Verify migration integrity
lawnberry-pi migrate verify \
    --source-db /var/lib/lawnberry-v1/main.db \
    --target-db /var/lib/lawnberry/main.db \
    --comprehensive
```

### Phase 3: Service Startup (5 minutes)

```bash
# Start v2 core services in order
sudo systemctl start lawnberry-database
sleep 5
sudo systemctl start lawnberry-backend
sleep 10
sudo systemctl start lawnberry-sensors
sleep 5
sudo systemctl start lawnberry-camera
sleep 5
sudo systemctl start lawnberry-frontend

# Start optional services
sudo systemctl start lawnberry-remote-access  # if configured
sudo systemctl start lawnberry-acme-renew.timer  # if configured

# Enable services for auto-start
sudo systemctl enable lawnberry-database lawnberry-backend lawnberry-sensors lawnberry-camera lawnberry-frontend
```

### Phase 4: Immediate Validation (10 minutes)

```bash
# Check service status
sudo systemctl status lawnberry-database lawnberry-backend lawnberry-frontend lawnberry-sensors lawnberry-camera

# Test API endpoints
curl -f http://localhost:8081/api/v1/status
curl -f http://localhost:8081/api/v2/status
curl -f http://localhost:8081/health/readiness

# Test frontend accessibility
curl -f http://localhost:3000/

# Test authentication
lawnberry-pi auth test --quick

# Test hardware connectivity
lawnberry-pi hardware test --critical --quick
```

## Validation Steps

### Functional Validation

#### 1. Core System Functions
```bash
# Test API functionality
lawnberry-pi test api --all-endpoints --auth

# Test WebSocket connectivity
lawnberry-pi test websocket --telemetry --subscriptions

# Test database operations
lawnberry-pi test database --crud --integrity

# Test configuration management
lawnberry-pi test config --load --save --validate
```

#### 2. Hardware Integration
```bash
# Test sensor readings
lawnberry-pi test sensors --all --real-data --duration 60

# Test GPS functionality
lawnberry-pi test gps --acquisition --accuracy --dead-reckoning

# Test camera system
lawnberry-pi test camera --capture --streaming --clients 3

# Test motor control (if safe)
lawnberry-pi test motors --safety-checks --low-speed --duration 10
```

#### 3. User Interface Validation
```bash
# Test frontend functionality (automated)
cd /home/pi/lawnberry/lawnberry-rebuild/frontend
npm run test:e2e

# Manual UI testing checklist:
# - [ ] Dashboard loads and shows live data
# - [ ] Maps view displays correctly
# - [ ] Manual control interface responds
# - [ ] Settings pages load and save
# - [ ] Authentication works correctly
```

### Performance Validation

#### 1. System Performance
```bash
# Monitor system resources during operation
lawnberry-pi monitor system --duration 300 --interval 5

# Test telemetry performance
lawnberry-pi test telemetry --frequency 5hz --duration 120 --clients 5

# Memory usage validation
lawnberry-pi test memory --stress-test --duration 300

# Network performance
lawnberry-pi test network --bandwidth --latency --reliability
```

#### 2. Database Performance
```bash
# Test database performance
lawnberry-pi test database --performance --large-dataset

# Monitor database growth
lawnberry-pi monitor database --size --queries --duration 300

# Validate backup/restore performance
lawnberry-pi test backup --full-cycle --verify
```

### Security Validation

#### 1. Authentication System
```bash
# Test all authentication levels
lawnberry-pi test auth --password --totp --google --tunnel

# Test session management
lawnberry-pi test sessions --concurrent --timeout --security

# Test rate limiting
lawnberry-pi test security --rate-limits --brute-force-protection
```

#### 2. Network Security
```bash
# Test remote access security
lawnberry-pi test remote-access --security --encryption

# Validate certificate management
lawnberry-pi test certificates --validation --renewal

# Test firewall rules
lawnberry-pi test network --security --ports --access
```

### Data Integrity Validation

#### 1. Migration Verification
```bash
# Compare v1 and v2 data
lawnberry-pi migrate compare \
    --v1-db /var/lib/lawnberry-v1/main.db \
    --v2-db /var/lib/lawnberry/main.db \
    --detailed-report

# Validate zone data migration
lawnberry-pi test zones --migration-integrity --boundaries

# Validate job history migration
lawnberry-pi test jobs --history --migration-accuracy
```

#### 2. Ongoing Data Integrity
```bash
# Test data consistency
lawnberry-pi test data-integrity --comprehensive

# Validate telemetry data flow
lawnberry-pi test telemetry --data-flow --storage --retrieval

# Test configuration persistence
lawnberry-pi test config --persistence --consistency
```

## Rollback Plan

### Rollback Decision Criteria

Initiate rollback if any of the following occur within 2 hours of cutover:

- [ ] Critical service failure (API, database, or safety systems)
- [ ] Authentication system failure preventing access
- [ ] Hardware integration failure affecting safety
- [ ] Data corruption or significant data loss
- [ ] Performance degradation > 50% from baseline
- [ ] Multiple component failures indicating systemic issues

### Quick Rollback Procedure (< 10 minutes)

#### Step 1: Stop v2 Services
```bash
# Stop all v2 services immediately
sudo systemctl stop lawnberry-*
sudo systemctl disable lawnberry-*
```

#### Step 2: Restore v1 System
```bash
# Restore v1 from backup if needed
sudo cp -r /backup/lawnberry-v1-$(date +%Y%m%d)/* /home/pi/lawnberry-v1/
sudo cp /backup/final-v1-backup-$(date +%Y%m%d-%H%M).db /var/lib/lawnberry-v1/main.db

# Start v1 services
sudo systemctl start lawnberry-v1-database
sudo systemctl start lawnberry-v1-backend
sudo systemctl start lawnberry-v1-frontend
sudo systemctl enable lawnberry-v1-*
```

#### Step 3: Validate v1 Restoration
```bash
# Test v1 system functionality
curl -f http://localhost:8080/api/status  # v1 endpoint
curl -f http://localhost:3001/  # v1 frontend

# Verify hardware connectivity
# (Use v1 diagnostics tools)

# Test core functions
# (Use v1 testing procedures)
```

### Complete Rollback Procedure (30-60 minutes)

If quick rollback isn't sufficient or data integrity is compromised:

#### 1. Full System Restore
```bash
# Stop all services
sudo systemctl stop lawnberry-*

# Restore complete v1 system
sudo rm -rf /home/pi/lawnberry-v1
sudo rm -rf /var/lib/lawnberry-v1
sudo rm -rf /etc/lawnberry-v1

sudo cp -r /backup/lawnberry-v1-$(date +%Y%m%d)/lawnberry-v1 /home/pi/
sudo cp -r /backup/lawnberry-v1-$(date +%Y%m%d)/var/lib/lawnberry-v1 /var/lib/
sudo cp -r /backup/lawnberry-v1-$(date +%Y%m%d)/etc/lawnberry-v1 /etc/

# Restore systemd services
sudo cp /backup/lawnberry-v1-$(date +%Y%m%d)/systemd/* /etc/systemd/system/
sudo systemctl daemon-reload
```

#### 2. Hardware Reconfiguration
```bash
# Revert hardware configurations if changed
# (Restore GPIO configurations, I2C settings, camera settings)

# Test hardware with v1 system
# Recalibrate sensors if necessary
```

#### 3. Network and Security Restoration
```bash
# Restore v1 network configurations
# Revert any firewall or routing changes
# Restore certificates and authentication settings
```

### Post-Rollback Actions

#### 1. Incident Analysis
```bash
# Collect v2 failure logs
sudo journalctl -u lawnberry-* --since "1 hour ago" > /var/log/v2-failure-logs.txt

# Generate failure report
lawnberry-pi diagnose --failure-analysis --comprehensive > /var/log/v2-failure-report.txt

# Document rollback reasons and timeline
```

#### 2. Communication
- [ ] Notify stakeholders of rollback
- [ ] Document lessons learned
- [ ] Plan remediation actions
- [ ] Schedule retry timeline

## Post-Cutover Tasks

### Immediate Tasks (First 24 hours)

#### 1. Monitoring Setup
```bash
# Enable comprehensive monitoring
lawnberry-pi monitor enable --all-metrics --alerts

# Set up log monitoring
lawnberry-pi logs monitor --error-threshold 10 --alert-email admin@domain.com

# Monitor system resources
lawnberry-pi monitor resources --memory --cpu --disk --network
```

#### 2. Performance Baseline
```bash
# Establish performance baselines
lawnberry-pi benchmark --comprehensive --save-baseline

# Monitor for performance regressions
lawnberry-pi monitor performance --compare-baseline --duration 24h
```

#### 3. User Acceptance
- [ ] User training on new interface
- [ ] Collect user feedback
- [ ] Address immediate usability issues
- [ ] Update documentation based on feedback

### Short-term Tasks (First Week)

#### 1. Optimization
```bash
# Optimize based on real usage patterns
lawnberry-pi optimize --auto-tune --based-on-usage

# Fine-tune cache settings
lawnberry-pi config cache --optimize-sizes --based-on-patterns

# Adjust telemetry frequencies
lawnberry-pi config telemetry --optimize-frequency --reduce-bandwidth
```

#### 2. Security Hardening
```bash
# Complete security configuration
lawnberry-pi security harden --comprehensive

# Update default passwords
lawnberry-pi auth update-defaults --force-change

# Enable additional security features
lawnberry-pi security enable --advanced-features
```

### Long-term Tasks (First Month)

#### 1. Feature Enablement
- [ ] Enable advanced AI features
- [ ] Configure automated scheduling
- [ ] Set up remote monitoring
- [ ] Enable predictive maintenance

#### 2. System Maintenance
```bash
# Set up automated backups
lawnberry-pi backup schedule --daily --retention 30

# Configure automatic updates
lawnberry-pi update schedule --security-only --maintenance-window

# Set up health monitoring
lawnberry-pi health monitor --predictive --alerts
```

#### 3. Documentation Updates
- [ ] Update operational procedures
- [ ] Create troubleshooting guides
- [ ] Document configuration changes
- [ ] Update emergency procedures

## Troubleshooting

### Common Cutover Issues

#### 1. Service Startup Failures
```bash
# Check service dependencies
sudo systemctl list-dependencies lawnberry-backend

# View detailed service logs
sudo journalctl -u lawnberry-backend -f

# Test service configuration
lawnberry-pi config validate --service backend
```

#### 2. Database Migration Issues
```bash
# Check migration logs
cat /var/log/lawnberry/migration.log

# Validate database integrity
lawnberry-pi database check --integrity --repair

# Re-run specific migration steps
lawnberry-pi migrate retry --step zones --validate
```

#### 3. Hardware Integration Issues
```bash
# Test hardware step by step
lawnberry-pi hardware test --component-by-component

# Check hardware permissions
ls -la /dev/ttyACM* /dev/video* /dev/i2c*

# Verify GPIO configurations
lawnberry-pi gpio test --all-pins --verbose
```

### Emergency Procedures

#### 1. Complete System Recovery
```bash
# If system becomes completely unresponsive
sudo systemctl stop lawnberry-*
sudo systemctl start lawnberry-emergency-mode

# This provides basic safety functions only
# Allows manual control for emergency situations
```

#### 2. Emergency Contact Procedures
1. **Hardware Issues**: Stop all motor functions immediately
2. **Safety Concerns**: Activate emergency stop procedures
3. **Data Loss**: Begin immediate backup recovery
4. **Security Breach**: Isolate system from network

### Success Metrics

Monitor these metrics post-cutover:

- **System Uptime**: > 99.5%
- **API Response Time**: < 200ms average
- **Telemetry Frequency**: 5Hz sustained
- **Memory Usage**: < 80% under normal load
- **Error Rate**: < 1% of all operations
- **User Satisfaction**: > 90% positive feedback

### Conclusion

This cutover plan provides a comprehensive approach to migrating from LawnBerry Pi v1 to v2 with minimal risk and quick recovery options. Regular validation and monitoring ensure system stability and performance after the transition.

For additional support during cutover, maintain emergency contact information and ensure physical access to the Pi system throughout the process.