#!/usr/bin/env python3
"""
Coral Package Migration Script
Migrates from pip-based Coral installations to system package management
Runs automatically during updates with rollback capability
"""

import os
import sys
import json
import shutil
import subprocess
import logging
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import hardware detection for Coral compatibility checks
try:
    from hardware_detection import EnhancedHardwareDetector
    HARDWARE_DETECTION_AVAILABLE = True
except ImportError:
    HARDWARE_DETECTION_AVAILABLE = False


@dataclass
class MigrationState:
    """Tracks migration state for rollback purposes"""
    timestamp: str
    phase: str
    pip_packages_backed_up: List[str]
    virtual_env_path: str
    system_packages_installed: List[str]
    config_files_backed_up: List[str]
    rollback_possible: bool
    migration_id: str
    
    def save_to_file(self, filepath: str):
        """Save migration state to JSON file"""
        with open(filepath, 'w') as f:
            json.dump(asdict(self), f, indent=2)
    
    @classmethod
    def load_from_file(cls, filepath: str) -> 'MigrationState':
        """Load migration state from JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return cls(**data)


class CoralPackageMigrator:
    """Handles migration from pip-based to system package Coral installation"""
    
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.dry_run = dry_run
        self.verbose = verbose
        self.logger = self._setup_logging()
        self.migration_id = f"coral_migration_{int(time.time())}"
        self.backup_dir = Path(f"/var/backups/lawnberry/coral_migration/{self.migration_id}")
        self.state_file = self.backup_dir / "migration_state.json"
        self.migration_state: Optional[MigrationState] = None
        
        # Ensure backup directory exists
        if not self.dry_run:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def _setup_logging(self) -> logging.Logger:
        """Setup logging for migration process"""
        logger = logging.getLogger('coral_migration')
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # File handler
        if not self.dry_run:
            log_file = Path("/var/log/lawnberry/coral_migration.log")
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
        return logger
    
    def detect_migration_needed(self) -> Tuple[bool, Dict[str, Any]]:
        """Detect if migration is needed and gather current state"""
        self.logger.info("Detecting if Coral package migration is needed...")
        
        detection_info = {
            'pip_pycoral_installed': False,
            'pip_tflite_coral_installed': False,
            'system_pycoral_installed': False,
            'pi_os_bookworm_compatible': False,
            'virtual_env_detected': None,
            'migration_needed': False,
            'migration_reason': []
        }
        
        try:
            # Check for pip-installed pycoral
            try:
                import pycoral
                detection_info['pip_pycoral_installed'] = True
                detection_info['migration_reason'].append("pip-installed pycoral detected")
                self.logger.info("Found pip-installed pycoral package")
            except ImportError:
                pass
            
            # Check for pip-installed tflite-runtime with coral extras
            pip_list_result = subprocess.run(
                [sys.executable, '-m', 'pip', 'list'], 
                capture_output=True, text=True, timeout=30
            )
            if pip_list_result.returncode == 0:
                pip_output = pip_list_result.stdout.lower()
                if 'tflite-runtime' in pip_output:
                    # Check if coral extras might be installed
                    try:
                        import tflite_runtime
                        detection_info['pip_tflite_coral_installed'] = True
                        detection_info['migration_reason'].append("pip-installed tflite-runtime detected")
                        self.logger.info("Found pip-installed tflite-runtime package")
                    except ImportError:
                        pass
            
            # Check for system-installed packages
            dpkg_result = subprocess.run(
                ['dpkg', '-l', 'python3-pycoral'], 
                capture_output=True, text=True, timeout=10
            )
            if dpkg_result.returncode == 0 and 'ii' in dpkg_result.stdout:
                detection_info['system_pycoral_installed'] = True
                self.logger.info("Found system-installed python3-pycoral package")
            
            # Check Pi OS Bookworm compatibility
            if HARDWARE_DETECTION_AVAILABLE:
                detector = EnhancedHardwareDetector()
                os_compatible, _ = detector._check_pi_os_bookworm_compatibility()
                detection_info['pi_os_bookworm_compatible'] = os_compatible
            else:
                # Fallback OS detection
                try:
                    with open('/etc/os-release', 'r') as f:
                        os_release = f.read()
                    detection_info['pi_os_bookworm_compatible'] = (
                        'bookworm' in os_release.lower() and 
                        'raspberry' in os_release.lower()
                    )
                except:
                    pass
            
            # Detect virtual environment
            if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
                detection_info['virtual_env_detected'] = sys.prefix
                self.logger.info(f"Virtual environment detected: {sys.prefix}")
            
            # Determine if migration is needed
            has_pip_coral = (detection_info['pip_pycoral_installed'] or 
                           detection_info['pip_tflite_coral_installed'])
            needs_system_packages = (detection_info['pi_os_bookworm_compatible'] and 
                                   not detection_info['system_pycoral_installed'])
            
            detection_info['migration_needed'] = has_pip_coral and needs_system_packages
            
            if detection_info['migration_needed']:
                self.logger.info("Migration needed: pip-based Coral packages detected on Bookworm-compatible system")
            else:
                self.logger.info("No migration needed")
                
        except Exception as e:
            self.logger.error(f"Detection failed: {e}")
            detection_info['error'] = str(e)
        
        return detection_info['migration_needed'], detection_info
    
    def create_backup(self, detection_info: Dict[str, Any]) -> bool:
        """Create backup of current installation state"""
        self.logger.info("Creating backup of current installation state...")
        
        if self.dry_run:
            self.logger.info("[DRY RUN] Would create backup")
            return True
        
        try:
            # Create migration state
            self.migration_state = MigrationState(
                timestamp=datetime.now().isoformat(),
                phase="backup",
                pip_packages_backed_up=[],
                virtual_env_path=detection_info.get('virtual_env_detected', ''),
                system_packages_installed=[],
                config_files_backed_up=[],
                rollback_possible=True,
                migration_id=self.migration_id
            )
            
            # Backup pip package list
            pip_freeze_result = subprocess.run(
                [sys.executable, '-m', 'pip', 'freeze'], 
                capture_output=True, text=True, timeout=30
            )
            if pip_freeze_result.returncode == 0:
                pip_requirements_file = self.backup_dir / "pip_requirements_backup.txt"
                with open(pip_requirements_file, 'w') as f:
                    f.write(pip_freeze_result.stdout)
                self.logger.info(f"Backed up pip requirements to {pip_requirements_file}")
            
            # Backup virtual environment if present
            if detection_info.get('virtual_env_detected'):
                venv_backup = self.backup_dir / "venv_backup"
                try:
                    # Only backup the pyvenv.cfg and pip list, not the entire venv
                    venv_path = Path(detection_info['virtual_env_detected'])
                    if (venv_path / 'pyvenv.cfg').exists():
                        shutil.copy2(venv_path / 'pyvenv.cfg', venv_backup / 'pyvenv.cfg')
                        venv_backup.mkdir(parents=True, exist_ok=True)
                        self.logger.info("Backed up virtual environment configuration")
                except Exception as e:
                    self.logger.warning(f"Virtual environment backup failed: {e}")
            
            # Backup relevant configuration files
            config_files = [
                Path("config/hardware.yaml"),
                Path("config/system.yaml"),
                Path("requirements-coral.txt")
            ]
            
            project_root = Path(__file__).parent.parent
            for config_file in config_files:
                source_file = project_root / config_file
                if source_file.exists():
                    backup_file = self.backup_dir / config_file.name
                    shutil.copy2(source_file, backup_file)
                    self.migration_state.config_files_backed_up.append(str(config_file))
                    self.logger.info(f"Backed up {config_file}")
            
            # Save migration state
            self.migration_state.save_to_file(self.state_file)
            self.logger.info(f"Migration state saved to {self.state_file}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Backup creation failed: {e}")
            return False
    
    def remove_pip_packages(self) -> bool:
        """Safely remove pip-installed Coral packages"""
        self.logger.info("Removing pip-installed Coral packages...")
        
        if self.dry_run:
            self.logger.info("[DRY RUN] Would remove pip packages: pycoral, tflite-runtime")
            return True
        
        try:
            packages_to_remove = []
            
            # Check which packages are actually installed
            try:
                import pycoral
                packages_to_remove.append('pycoral')
                self.migration_state.pip_packages_backed_up.append('pycoral')
            except ImportError:
                pass
            
            # Check for tflite-runtime
            pip_list_result = subprocess.run(
                [sys.executable, '-m', 'pip', 'list'], 
                capture_output=True, text=True, timeout=30
            )
            if pip_list_result.returncode == 0 and 'tflite-runtime' in pip_list_result.stdout:
                packages_to_remove.append('tflite-runtime')
                self.migration_state.pip_packages_backed_up.append('tflite-runtime')
            
            # Remove packages
            for package in packages_to_remove:
                self.logger.info(f"Removing pip package: {package}")
                result = subprocess.run(
                    [sys.executable, '-m', 'pip', 'uninstall', '-y', package],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode != 0:
                    self.logger.warning(f"Failed to remove {package}: {result.stderr}")
                    # Continue with migration despite individual package failures
                else:
                    self.logger.info(f"Successfully removed {package}")
            
            # Update migration state
            self.migration_state.phase = "pip_cleanup_complete"
            self.migration_state.save_to_file(self.state_file)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Pip package removal failed: {e}")
            return False
    
    def install_system_packages(self) -> bool:
        """Install system packages for Coral TPU"""
        self.logger.info("Installing system packages for Coral TPU...")
        
        if self.dry_run:
            self.logger.info("[DRY RUN] Would install system packages: python3-pycoral")
            return True
        
        try:
            # Update package list
            self.logger.info("Updating package list...")
            result = subprocess.run(
                ['sudo', 'apt-get', 'update'],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                self.logger.warning(f"Package list update failed: {result.stderr}")
                # Continue anyway, packages might still install
            
            # Install python3-pycoral
            self.logger.info("Installing python3-pycoral...")
            result = subprocess.run(
                ['sudo', 'apt-get', 'install', '-y', 'python3-pycoral'],
                capture_output=True, text=True, timeout=300
            )
            
            if result.returncode == 0:
                self.logger.info("Successfully installed python3-pycoral")
                self.migration_state.system_packages_installed.append('python3-pycoral')
                
                # Also try to install tflite-runtime if available
                self.logger.info("Installing python3-tflite-runtime...")
                tflite_result = subprocess.run(
                    ['sudo', 'apt-get', 'install', '-y', 'python3-tflite-runtime'],
                    capture_output=True, text=True, timeout=300
                )
                if tflite_result.returncode == 0:
                    self.logger.info("Successfully installed python3-tflite-runtime")
                    self.migration_state.system_packages_installed.append('python3-tflite-runtime')
                else:
                    self.logger.warning("python3-tflite-runtime installation failed, but continuing")
                
            else:
                self.logger.error(f"System package installation failed: {result.stderr}")
                return False
            
            # Update migration state
            self.migration_state.phase = "system_packages_installed"
            self.migration_state.save_to_file(self.state_file)
            
            return True
            
        except Exception as e:
            self.logger.error(f"System package installation failed: {e}")
            return False
    
    def verify_installation(self) -> bool:
        """Verify that the migrated installation works correctly"""
        self.logger.info("Verifying migrated installation...")
        
        if self.dry_run:
            self.logger.info("[DRY RUN] Would verify installation")
            return True
        
        try:
            # Test basic imports
            try:
                import pycoral.utils.edgetpu as edgetpu
                self.logger.info("Successfully imported pycoral.utils.edgetpu")
            except ImportError as e:
                self.logger.error(f"Failed to import pycoral: {e}")
                return False
            
            try:
                import tflite_runtime.interpreter as tflite
                self.logger.info("Successfully imported tflite_runtime.interpreter")
            except ImportError as e:
                self.logger.warning(f"tflite_runtime import failed: {e}")
                # This is not critical for the migration
            
            # Test Coral device detection if hardware detection is available
            if HARDWARE_DETECTION_AVAILABLE:
                try:
                    detector = EnhancedHardwareDetector()
                    coral_results = detector._detect_coral_tpu_enhanced()
                    if coral_results:
                        self.logger.info("Coral hardware detection working correctly")
                    else:
                        self.logger.info("Coral hardware detection completed (no hardware detected)")
                except Exception as e:
                    self.logger.warning(f"Hardware detection test failed: {e}")
            
            # Update migration state
            self.migration_state.phase = "verification_complete"
            self.migration_state.save_to_file(self.state_file)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Installation verification failed: {e}")
            return False
    
    def rollback_migration(self) -> bool:
        """Rollback migration if something went wrong"""
        self.logger.info("Rolling back migration...")
        
        if self.dry_run:
            self.logger.info("[DRY RUN] Would rollback migration")
            return True
        
        try:
            if not self.migration_state:
                if self.state_file.exists():
                    self.migration_state = MigrationState.load_from_file(self.state_file)
                else:
                    self.logger.error("No migration state found for rollback")
                    return False
            
            rollback_success = True
            
            # Remove system packages that were installed
            for package in self.migration_state.system_packages_installed:
                self.logger.info(f"Removing system package: {package}")
                result = subprocess.run(
                    ['sudo', 'apt-get', 'remove', '-y', package],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode != 0:
                    self.logger.warning(f"Failed to remove {package}: {result.stderr}")
                    rollback_success = False
            
            # Restore pip packages from backup
            pip_backup_file = self.backup_dir / "pip_requirements_backup.txt"
            if pip_backup_file.exists():
                self.logger.info("Restoring pip packages from backup...")
                result = subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', '-r', str(pip_backup_file)],
                    capture_output=True, text=True, timeout=300
                )
                if result.returncode != 0:
                    self.logger.warning(f"Pip package restoration failed: {result.stderr}")
                    rollback_success = False
            
            # Restore configuration files
            project_root = Path(__file__).parent.parent
            for config_file in self.migration_state.config_files_backed_up:
                backup_file = self.backup_dir / Path(config_file).name
                target_file = project_root / config_file
                if backup_file.exists():
                    shutil.copy2(backup_file, target_file)
                    self.logger.info(f"Restored {config_file}")
            
            if rollback_success:
                self.logger.info("Migration rollback completed successfully")
            else:
                self.logger.warning("Migration rollback completed with some errors")
            
            return rollback_success
            
        except Exception as e:
            self.logger.error(f"Rollback failed: {e}")
            return False
    
    def run_migration(self) -> bool:
        """Run the complete migration process"""
        self.logger.info(f"Starting Coral package migration (ID: {self.migration_id})...")
        
        try:
            # Phase 1: Detection
            migration_needed, detection_info = self.detect_migration_needed()
            if not migration_needed:
                self.logger.info("No migration needed, exiting")
                return True
            
            self.logger.info("Migration needed, proceeding with phases...")
            
            # Phase 2: Backup
            if not self.create_backup(detection_info):
                self.logger.error("Backup phase failed, aborting migration")
                return False
            
            # Phase 3: Cleanup
            if not self.remove_pip_packages():
                self.logger.error("Pip package cleanup failed, attempting rollback")
                self.rollback_migration()
                return False
            
            # Phase 4: Installation
            if not self.install_system_packages():
                self.logger.error("System package installation failed, attempting rollback")
                self.rollback_migration()
                return False
            
            # Phase 5: Verification
            if not self.verify_installation():
                self.logger.error("Installation verification failed, attempting rollback")
                self.rollback_migration()
                return False
            
            # Success
            self.migration_state.phase = "complete"
            self.migration_state.rollback_possible = False  # No longer needed
            self.migration_state.save_to_file(self.state_file)
            
            self.logger.info("Coral package migration completed successfully!")
            self.logger.info(f"Migration backup saved to: {self.backup_dir}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Migration failed with exception: {e}")
            if self.migration_state and self.migration_state.rollback_possible:
                self.logger.info("Attempting rollback...")
                self.rollback_migration()
            return False


def main():
    """Main entry point for migration script"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate Coral packages from pip to system packages')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be done without making changes')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--rollback', type=str, metavar='MIGRATION_ID',
                       help='Rollback a specific migration by ID')
    parser.add_argument('--detect-only', action='store_true',
                       help='Only detect if migration is needed and exit')
    
    args = parser.parse_args()
    
    # Handle rollback
    if args.rollback:
        backup_dir = Path(f"/var/backups/lawnberry/coral_migration/{args.rollback}")
        state_file = backup_dir / "migration_state.json"
        
        if not state_file.exists():
            print(f"Error: Migration state file not found: {state_file}")
            sys.exit(1)
        
        migrator = CoralPackageMigrator(dry_run=args.dry_run, verbose=args.verbose)
        migrator.migration_state = MigrationState.load_from_file(state_file)
        migrator.backup_dir = backup_dir
        migrator.state_file = state_file
        
        success = migrator.rollback_migration()
        sys.exit(0 if success else 1)
    
    # Regular migration
    migrator = CoralPackageMigrator(dry_run=args.dry_run, verbose=args.verbose)
    
    # Detection only mode
    if args.detect_only:
        migration_needed, detection_info = migrator.detect_migration_needed()
        print(json.dumps({
            'migration_needed': migration_needed,
            'detection_info': detection_info
        }, indent=2))
        sys.exit(0)
    
    # Run migration
    success = migrator.run_migration()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
