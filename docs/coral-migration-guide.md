# Coral Package Migration Guide

## Overview

The Coral Package Migration system automatically updates existing LawnBerry installations from pip-based Coral packages to system package management on Pi OS Bookworm systems. This migration ensures compatibility with Python 3.11+ and follows Google's recommended installation methods.

## Migration Process

### Automatic Migration During Updates

The migration runs automatically during system updates via `scripts/update_lawnberry.sh`. The process:

1. **Detection Phase**: Checks if migration is needed by detecting:
   - Pip-installed `pycoral` or `tflite-runtime` packages
   - Pi OS Bookworm compatibility 
   - Current system package status

2. **User Confirmation**: Prompts user before proceeding (unless `FORCE_UPDATE=true`)

3. **Backup Phase**: Creates comprehensive backup including:
   - Current pip package list (`pip freeze`)
   - Virtual environment configuration
   - Relevant config files
   - Migration state for rollback

4. **Cleanup Phase**: Safely removes pip-installed Coral packages:
   - `pycoral`
   - `tflite-runtime`

5. **Installation Phase**: Installs system packages:
   - `python3-pycoral` (primary package)
   - `python3-tflite-runtime` (if available)

6. **Verification Phase**: Tests the new installation:
   - Import tests for Coral packages
   - Hardware detection validation
   - Functionality verification

## Manual Migration

### Run Migration Manually

```bash
# Check if migration is needed
python3 scripts/migrate_coral_packages.py --detect-only

# Run migration with verbose output
python3 scripts/migrate_coral_packages.py --verbose

# Dry run (show what would be done)
python3 scripts/migrate_coral_packages.py --dry-run --verbose
```

### Rollback Migration

If migration fails or causes issues:

```bash
# List available migrations for rollback
ls /var/backups/lawnberry/coral_migration/

# Rollback specific migration
python3 scripts/migrate_coral_packages.py --rollback coral_migration_1234567890

# Dry run rollback
python3 scripts/migrate_coral_packages.py --rollback coral_migration_1234567890 --dry-run
```

## Migration Scenarios

### Scenario 1: Standard Migration
- **System**: Pi OS Bookworm with Python 3.11+
- **Current**: pip-installed pycoral packages
- **Action**: Migrate to system packages
- **Result**: Improved compatibility and performance

### Scenario 2: Mixed Package State  
- **System**: Pi OS Bookworm
- **Current**: Some pip packages, some system packages
- **Action**: Clean up pip packages, ensure system packages
- **Result**: Consistent system package installation

### Scenario 3: No Hardware Present
- **System**: Pi OS Bookworm without Coral TPU
- **Current**: pip-installed packages
- **Action**: Migrate to system packages for future hardware
- **Result**: Ready for Coral TPU when hardware is added

### Scenario 4: Migration Failure
- **System**: Any compatible system
- **Current**: Migration fails partway through
- **Action**: Automatic rollback to previous state
- **Result**: System restored to pre-migration state

## Safety Features

### Backup and Rollback
- Complete backup before any changes
- Rollback capability if migration fails
- Preservation of user data and configurations
- Multiple rollback points if needed

### Idempotency
- Safe to run multiple times
- Detects already-migrated systems
- No-op if migration not needed
- Consistent results across runs

### Error Handling
- Graceful handling of partial failures
- Clear error messages and recovery instructions
- Automatic rollback on critical failures
- Continue-or-abort prompts for non-critical issues

## Troubleshooting

### Migration Detection Issues
```bash
# Check current package state
dpkg -l | grep pycoral
pip list | grep -E "(pycoral|tflite)"

# Check OS compatibility
lsb_release -a
python3 --version
```

### Migration Failures
```bash
# Check migration logs
tail -f /var/log/lawnberry/coral_migration.log

# Check system package availability
apt-cache search python3-pycoral
apt-get update && apt-cache search python3-pycoral
```

### Post-Migration Verification
```bash
# Test Coral imports
python3 -c "import pycoral.utils.edgetpu; print('PyCoral OK')"
python3 -c "import tflite_runtime.interpreter; print('TFLite OK')"

# Run hardware detection
python3 scripts/hardware_detection.py
```

## Integration with Update Process

The migration is fully integrated with the update system:

1. **Update Script**: `scripts/update_lawnberry.sh` calls migration automatically
2. **Timing**: Runs after code update, before dependency installation
3. **User Control**: Respects `FORCE_UPDATE` flag for unattended updates
4. **Logging**: Integrated with update logging system
5. **Error Handling**: Migration failures can optionally abort updates

## Configuration

### Environment Variables
- `FORCE_UPDATE=true`: Skip user prompts during migration
- `LAWNBERRY_MIGRATION_SKIP=true`: Skip migration entirely (not recommended)

### Migration Settings
Migration behavior is controlled by:
- Pi OS version detection
- Python version compatibility  
- Current package installation state
- Hardware presence (optional)

## Backup Locations

Backups are stored in `/var/backups/lawnberry/coral_migration/` with:
- Unique migration ID timestamps
- Complete pip requirements backup
- Configuration file backups
- Migration state files for rollback
- Automatic cleanup after successful migration (optional)

## Best Practices

1. **Before Migration**:
   - Ensure system is updated (`sudo apt-get update`)
   - Stop LawnBerry services if running
   - Have console/SSH access in case of issues

2. **During Migration**:
   - Monitor output for any warnings
   - Don't interrupt the process
   - Note the migration ID for potential rollback

3. **After Migration**:
   - Test Coral functionality if hardware present
   - Verify application startup
   - Clean up old backups after confirming stability

## Support and Recovery

If you encounter issues:

1. **Check logs**: `/var/log/lawnberry/coral_migration.log`
2. **Attempt rollback**: Use the migration ID from logs
3. **Manual cleanup**: Remove pip packages and install system packages manually
4. **Contact support**: Provide migration logs and system information

The migration system is designed to be safe and reversible, ensuring your LawnBerry installation remains functional throughout the process.
