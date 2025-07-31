#!/usr/bin/env python3
"""
Test script for Coral package migration functionality
Validates migration logic without requiring actual Coral hardware
"""

import os
import sys
import tempfile
import shutil
import subprocess
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the scripts directory to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    from migrate_coral_packages import CoralPackageMigrator, MigrationState
except ImportError as e:
    print(f"Error importing migration script: {e}")
    sys.exit(1)


class MockCoralMigrationTest:
    """Test class for Coral migration functionality"""
    
    def __init__(self):
        self.test_results = []
        self.temp_dir = None
    
    def setup_test_environment(self):
        """Setup temporary test environment"""
        self.temp_dir = tempfile.mkdtemp(prefix="coral_migration_test_")
        print(f"Test environment: {self.temp_dir}")
        
        # Create mock backup directory structure
        backup_dir = Path(self.temp_dir) / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        return True
    
    def cleanup_test_environment(self):
        """Clean up test environment"""
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)
            print(f"Cleaned up test environment: {self.temp_dir}")
    
    def test_migration_detection(self):
        """Test migration detection logic"""
        print("\n--- Testing Migration Detection ---")
        
        try:
            # Create migrator in dry-run mode
            migrator = CoralPackageMigrator(dry_run=True, verbose=True)
            
            # Override backup directory for testing
            migrator.backup_dir = Path(self.temp_dir) / "test_backup"
            migrator.backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Test detection
            migration_needed, detection_info = migrator.detect_migration_needed()
            
            print(f"Migration needed: {migration_needed}")
            print(f"Detection info: {json.dumps(detection_info, indent=2)}")
            
            # Validate detection results
            assert isinstance(migration_needed, bool), "Migration needed should be boolean"
            assert isinstance(detection_info, dict), "Detection info should be dict"
            assert 'pip_pycoral_installed' in detection_info, "Should check pip pycoral"
            assert 'system_pycoral_installed' in detection_info, "Should check system pycoral"
            assert 'pi_os_bookworm_compatible' in detection_info, "Should check OS compatibility"
            
            self.test_results.append(("Migration Detection", True, "All detection checks passed"))
            return True
            
        except Exception as e:
            self.test_results.append(("Migration Detection", False, str(e)))
            print(f"Detection test failed: {e}")
            return False
    
    def test_migration_state_persistence(self):
        """Test migration state saving and loading"""
        print("\n--- Testing Migration State Persistence ---")
        
        try:
            # Create test migration state
            test_state = MigrationState(
                timestamp="2024-01-01T12:00:00",
                phase="test_phase",
                pip_packages_backed_up=["pycoral", "tflite-runtime"],
                virtual_env_path="/test/venv",
                system_packages_installed=["python3-pycoral"],
                config_files_backed_up=["config/hardware.yaml"],
                rollback_possible=True,
                migration_id="test_migration_123"
            )
            
            # Test saving
            state_file = Path(self.temp_dir) / "test_state.json"
            test_state.save_to_file(str(state_file))
            
            assert state_file.exists(), "State file should be created"
            
            # Test loading
            loaded_state = MigrationState.load_from_file(str(state_file))
            
            assert loaded_state.migration_id == test_state.migration_id, "Migration ID should match"
            assert loaded_state.phase == test_state.phase, "Phase should match"
            assert loaded_state.pip_packages_backed_up == test_state.pip_packages_backed_up, "Backed up packages should match"
            
            self.test_results.append(("Migration State Persistence", True, "State save/load working correctly"))
            return True
            
        except Exception as e:
            self.test_results.append(("Migration State Persistence", False, str(e)))
            print(f"State persistence test failed: {e}")
            return False
    
    def test_dry_run_migration(self):
        """Test complete migration in dry-run mode"""
        print("\n--- Testing Dry Run Migration ---")
        
        try:
            # Create migrator in dry-run mode
            migrator = CoralPackageMigrator(dry_run=True, verbose=True)
            
            # Override backup directory for testing
            migrator.backup_dir = Path(self.temp_dir) / "dry_run_backup"
            migrator.backup_dir.mkdir(parents=True, exist_ok=True)
            migrator.state_file = migrator.backup_dir / "migration_state.json"
            
            # Mock the detection to return migration needed
            with patch.object(migrator, 'detect_migration_needed') as mock_detect:
                mock_detect.return_value = (True, {
                    'pip_pycoral_installed': True,
                    'pip_tflite_coral_installed': True,
                    'system_pycoral_installed': False,
                    'pi_os_bookworm_compatible': True,
                    'virtual_env_detected': '/test/venv',
                    'migration_needed': True,
                    'migration_reason': ['test migration']
                })
                
                # Run migration
                success = migrator.run_migration()
                
                assert success, "Dry run migration should succeed"
                
                # Check that state file was created
                assert migrator.state_file.exists(), "State file should be created in dry run"
                
                # Load and validate state
                state = MigrationState.load_from_file(migrator.state_file)
                assert state.phase == "complete", "Migration should be marked complete"
            
            self.test_results.append(("Dry Run Migration", True, "Complete dry run migration successful"))
            return True
            
        except Exception as e:
            self.test_results.append(("Dry Run Migration", False, str(e)))
            print(f"Dry run migration test failed: {e}")
            return False
    
    def test_rollback_functionality(self):
        """Test rollback functionality"""
        print("\n--- Testing Rollback Functionality ---")
        
        try:
            # Create migrator
            migrator = CoralPackageMigrator(dry_run=True, verbose=True)
            
            # Setup test state for rollback
            migrator.backup_dir = Path(self.temp_dir) / "rollback_test"
            migrator.backup_dir.mkdir(parents=True, exist_ok=True)
            migrator.state_file = migrator.backup_dir / "migration_state.json"
            
            # Create test migration state
            test_state = MigrationState(
                timestamp="2024-01-01T12:00:00",
                phase="system_packages_installed",
                pip_packages_backed_up=["pycoral", "tflite-runtime"],
                virtual_env_path="/test/venv",
                system_packages_installed=["python3-pycoral"],
                config_files_backed_up=["config/hardware.yaml"],
                rollback_possible=True,
                migration_id="rollback_test_123"
            )
            
            # Save state and set in migrator
            test_state.save_to_file(migrator.state_file)
            migrator.migration_state = test_state
            
            # Create mock backup file
            pip_backup = migrator.backup_dir / "pip_requirements_backup.txt"
            with open(pip_backup, 'w') as f:
                f.write("pycoral==2.0.0\ntflite-runtime==2.13.0\n")
            
            # Test rollback
            success = migrator.rollback_migration()
            
            assert success, "Rollback should succeed in dry run mode"
            
            self.test_results.append(("Rollback Functionality", True, "Rollback logic working correctly"))
            return True
            
        except Exception as e:
            self.test_results.append(("Rollback Functionality", False, str(e)))
            print(f"Rollback test failed: {e}")
            return False
    
    def test_idempotency(self):
        """Test that migration can be run multiple times safely"""
        print("\n--- Testing Migration Idempotency ---")
        
        try:
            # Create migrator
            migrator = CoralPackageMigrator(dry_run=True, verbose=True)
            
            # Override backup directory
            migrator.backup_dir = Path(self.temp_dir) / "idempotency_test"
            migrator.backup_dir.mkdir(parents=True, exist_ok=True)
            
            # Mock detection to return no migration needed (already migrated)
            with patch.object(migrator, 'detect_migration_needed') as mock_detect:
                mock_detect.return_value = (False, {
                    'pip_pycoral_installed': False,
                    'pip_tflite_coral_installed': False,
                    'system_pycoral_installed': True,
                    'pi_os_bookworm_compatible': True,
                    'virtual_env_detected': '/test/venv',
                    'migration_needed': False,
                    'migration_reason': []
                })
                
                # Run migration multiple times
                success1 = migrator.run_migration()
                success2 = migrator.run_migration()
                
                assert success1, "First run should succeed"
                assert success2, "Second run should succeed (idempotent)"
            
            self.test_results.append(("Migration Idempotency", True, "Migration is idempotent"))
            return True
            
        except Exception as e:
            self.test_results.append(("Migration Idempotency", False, str(e)))
            print(f"Idempotency test failed: {e}")
            return False
    
    def run_all_tests(self):
        """Run all migration tests"""
        print("Starting Coral Migration Tests...")
        
        if not self.setup_test_environment():
            print("Failed to setup test environment")
            return False
        
        try:
            # Run tests
            tests = [
                self.test_migration_detection,
                self.test_migration_state_persistence,
                self.test_dry_run_migration,
                self.test_rollback_functionality,
                self.test_idempotency
            ]
            
            for test in tests:
                try:
                    test()
                except Exception as e:
                    print(f"Test {test.__name__} failed with exception: {e}")
            
            # Report results
            print("\n" + "="*60)
            print("CORAL MIGRATION TEST RESULTS")
            print("="*60)
            
            passed = 0
            failed = 0
            
            for test_name, success, message in self.test_results:
                status = "PASS" if success else "FAIL"
                print(f"{test_name:<30} [{status}] {message}")
                if success:
                    passed += 1
                else:
                    failed += 1
            
            print(f"\nTotal: {len(self.test_results)} tests, {passed} passed, {failed} failed")
            
            return failed == 0
            
        finally:
            self.cleanup_test_environment()


def main():
    """Main test entry point"""
    tester = MockCoralMigrationTest()
    success = tester.run_all_tests()
    
    if success:
        print("\nAll tests passed! ✅")
        sys.exit(0)
    else:
        print("\nSome tests failed! ❌")
        sys.exit(1)


if __name__ == '__main__':
    main()
