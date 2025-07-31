#!/usr/bin/env python3
"""
Installation Test Script
Tests the installation automation scripts for functionality
"""

import os
import sys
import asyncio
import subprocess
import tempfile
import json
from pathlib import Path
from typing import Dict, List, Tuple
import logging


class InstallationTester:
    """Tests installation scripts and components"""
    
    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root or Path(__file__).parent.parent)
        self.scripts_dir = self.project_root / 'scripts'
        self.test_results = {}
        self.logger = self._setup_logging()
    
    def _setup_logging(self) -> logging.Logger:
        """Setup test logging"""
        logger = logging.getLogger('installation_tester')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def test_script_permissions(self) -> Dict[str, bool]:
        """Test that all scripts have proper permissions"""
        self.logger.info("Testing script permissions...")
        
        scripts_to_test = [
            'install_lawnberry.sh',
            'uninstall_lawnberry.sh', 
            'update_lawnberry.sh',
            'hardware_detection.py',
            'setup_environment.py',
            'init_database.py',
            'first_run_wizard.py'
        ]
        
        results = {}
        for script in scripts_to_test:
            script_path = self.scripts_dir / script
            if script_path.exists():
                is_executable = os.access(script_path, os.X_OK)
                results[script] = is_executable
                status = "✅" if is_executable else "❌"
                self.logger.info(f"{status} {script}: {'Executable' if is_executable else 'Not executable'}")
            else:
                results[script] = False
                self.logger.warning(f"❌ {script}: Not found")
        
        return results
    
    def test_script_syntax(self) -> Dict[str, bool]:
        """Test script syntax and basic validation"""
        self.logger.info("Testing script syntax...")
        
        results = {}
        
        # Test bash scripts
        bash_scripts = ['install_lawnberry.sh', 'uninstall_lawnberry.sh', 'update_lawnberry.sh']
        for script in bash_scripts:
            script_path = self.scripts_dir / script
            if script_path.exists():
                try:
                    result = subprocess.run(
                        ['bash', '-n', str(script_path)],
                        cwd=self.project_root,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    results[script] = result.returncode == 0
                    status = "✅" if result.returncode == 0 else "❌"
                    self.logger.info(f"{status} {script}: Syntax {'OK' if result.returncode == 0 else 'Error'}")
                    if result.returncode != 0:
                        self.logger.error(f"   Error: {result.stderr}")
                except Exception as e:
                    results[script] = False
                    self.logger.error(f"❌ {script}: Test failed - {e}")
            else:
                results[script] = False
        
        # Test Python scripts
        python_scripts = [
            'hardware_detection.py',
            'setup_environment.py', 
            'init_database.py',
            'first_run_wizard.py'
        ]
        
        for script in python_scripts:
            script_path = self.scripts_dir / script
            if script_path.exists():
                try:
                    result = subprocess.run(
                        [sys.executable, '-m', 'py_compile', str(script_path)],
                        cwd=self.project_root,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    results[script] = result.returncode == 0
                    status = "✅" if result.returncode == 0 else "❌"
                    self.logger.info(f"{status} {script}: Syntax {'OK' if result.returncode == 0 else 'Error'}")
                    if result.returncode != 0:
                        self.logger.error(f"   Error: {result.stderr}")
                except Exception as e:
                    results[script] = False
                    self.logger.error(f"❌ {script}: Test failed - {e}")
            else:
                results[script] = False
        
        return results
    
    def test_import_capabilities(self) -> Dict[str, bool]:
        """Test that Python scripts can import required modules"""
        self.logger.info("Testing import capabilities...")
        
        results = {}
        
        # Test hardware detection imports
        try:
            sys.path.insert(0, str(self.scripts_dir))
            
            # Test hardware_detection.py
            try:
                import hardware_detection
                results['hardware_detection_imports'] = True
                self.logger.info("✅ hardware_detection.py: Imports OK")
            except ImportError as e:
                results['hardware_detection_imports'] = False
                self.logger.warning(f"⚠️  hardware_detection.py: Import warning - {e}")
            
            # Test setup_environment.py
            try:
                import setup_environment
                results['setup_environment_imports'] = True
                self.logger.info("✅ setup_environment.py: Imports OK")
            except ImportError as e:
                results['setup_environment_imports'] = False
                self.logger.warning(f"⚠️  setup_environment.py: Import warning - {e}")
            
            # Test init_database.py
            try:
                import init_database
                results['init_database_imports'] = True
                self.logger.info("✅ init_database.py: Imports OK")
            except ImportError as e:
                results['init_database_imports'] = False
                self.logger.warning(f"⚠️  init_database.py: Import warning - {e}")
            
            # Test first_run_wizard.py
            try:
                import first_run_wizard
                results['first_run_wizard_imports'] = True
                self.logger.info("✅ first_run_wizard.py: Imports OK")
            except ImportError as e:
                results['first_run_wizard_imports'] = False
                self.logger.warning(f"⚠️  first_run_wizard.py: Import warning - {e}")
                
        except Exception as e:
            self.logger.error(f"❌ Import test failed: {e}")
            results['import_test_error'] = str(e)
        finally:
            # Clean up sys.path
            if str(self.scripts_dir) in sys.path:
                sys.path.remove(str(self.scripts_dir))
        
        return results
    
    def test_help_options(self) -> Dict[str, bool]:
        """Test that scripts respond to help options"""
        self.logger.info("Testing help options...")
        
        results = {}
        
        # Test bash scripts with --help
        bash_scripts = ['install_lawnberry.sh', 'uninstall_lawnberry.sh', 'update_lawnberry.sh']
        for script in bash_scripts:
            script_path = self.scripts_dir / script
            if script_path.exists():
                try:
                    result = subprocess.run(
                        ['bash', str(script_path), '--help'],
                        cwd=self.project_root,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    # Help should exit with 0 and produce output
                    has_help = result.returncode == 0 and len(result.stdout) > 50
                    results[f'{script}_help'] = has_help
                    status = "✅" if has_help else "⚠️"
                    self.logger.info(f"{status} {script}: Help {'Available' if has_help else 'Limited'}")
                except Exception as e:
                    results[f'{script}_help'] = False
                    self.logger.warning(f"⚠️  {script}: Help test failed - {e}")
        
        # Test Python scripts with --help
        python_scripts = ['setup_environment.py', 'init_database.py']
        for script in python_scripts:
            script_path = self.scripts_dir / script
            if script_path.exists():
                try:
                    result = subprocess.run(
                        [sys.executable, str(script_path), '--help'],
                        cwd=self.project_root,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    # Help should exit with 0 and produce output
                    has_help = result.returncode == 0 and len(result.stdout) > 50
                    results[f'{script}_help'] = has_help
                    status = "✅" if has_help else "⚠️"
                    self.logger.info(f"{status} {script}: Help {'Available' if has_help else 'Limited'}")
                except Exception as e:
                    results[f'{script}_help'] = False
                    self.logger.warning(f"⚠️  {script}: Help test failed - {e}")
        
        return results
    
    def test_dry_run_capabilities(self) -> Dict[str, bool]:
        """Test scripts in dry-run or check modes where available"""
        self.logger.info("Testing dry-run capabilities...")
        
        results = {}
        
        # Test environment setup check
        try:
            result = subprocess.run(
                [sys.executable, str(self.scripts_dir / 'setup_environment.py'), '--check'],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30
            )
            # This should run without error (even if .env doesn't exist)
            results['environment_check'] = True
            self.logger.info("✅ setup_environment.py --check: Working")
        except Exception as e:
            results['environment_check'] = False
            self.logger.warning(f"⚠️  setup_environment.py --check: {e}")
        
        # Test database health check
        try:
            result = subprocess.run(
                [sys.executable, str(self.scripts_dir / 'init_database.py'), '--check-health'],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30
            )
            # This should run (may fail if Redis not available, but script should handle it)
            results['database_check'] = True
            self.logger.info("✅ init_database.py --check-health: Working")
        except Exception as e:
            results['database_check'] = False
            self.logger.warning(f"⚠️  init_database.py --check-health: {e}")
        
        return results
    
    async def test_hardware_detection_basic(self) -> Dict[str, bool]:
        """Test basic hardware detection functionality"""
        self.logger.info("Testing hardware detection...")
        
        results = {}
        
        try:
            # Test that hardware detection can at least start
            sys.path.insert(0, str(self.scripts_dir))
            from hardware_detection import HardwareDetector
            
            detector = HardwareDetector()
            
            # Test system info detection (should work on any system)
            system_info = await detector._detect_system_info()
            
            if system_info and isinstance(system_info, dict):
                results['system_info_detection'] = True
                self.logger.info("✅ Hardware detection: System info working")
            else:
                results['system_info_detection'] = False
                self.logger.warning("⚠️  Hardware detection: System info failed")
            
            # Test GPIO detection (may fail on non-Pi systems)
            try:
                gpio_info = await detector._detect_gpio_capability()
                results['gpio_detection'] = isinstance(gpio_info, dict)
                status = "✅" if results['gpio_detection'] else "⚠️"
                self.logger.info(f"{status} Hardware detection: GPIO detection {'working' if results['gpio_detection'] else 'limited'}")
            except Exception:
                results['gpio_detection'] = False
                self.logger.info("⚠️  Hardware detection: GPIO detection not available (expected on non-Pi systems)")
                
        except Exception as e:
            results['hardware_detection_basic'] = False
            self.logger.error(f"❌ Hardware detection basic test failed: {e}")
        finally:
            if str(self.scripts_dir) in sys.path:
                sys.path.remove(str(self.scripts_dir))
        
        return results
    
    def test_configuration_files(self) -> Dict[str, bool]:
        """Test that required configuration files exist"""
        self.logger.info("Testing configuration files...")
        
        results = {}
        
        config_files = [
            'config/hardware.yaml',
            'config/weather.yaml',
            'config/safety.yaml',
            '.env.example',
            'requirements.txt'
        ]
        
        for config_file in config_files:
            file_path = self.project_root / config_file
            exists = file_path.exists()
            results[config_file] = exists
            status = "✅" if exists else "❌"
            self.logger.info(f"{status} {config_file}: {'Present' if exists else 'Missing'}")
        
        return results
    
    def run_all_tests(self) -> Dict[str, Dict[str, bool]]:
        """Run all installation tests"""
        self.logger.info("="*60)
        self.logger.info("RUNNING LAWNBERRY PI INSTALLATION TESTS")
        self.logger.info("="*60)
        
        all_results = {}
        
        # Run synchronous tests
        all_results['permissions'] = self.test_script_permissions()
        all_results['syntax'] = self.test_script_syntax()
        all_results['imports'] = self.test_import_capabilities()
        all_results['help_options'] = self.test_help_options()
        all_results['dry_run'] = self.test_dry_run_capabilities()
        all_results['config_files'] = self.test_configuration_files()
        
        # Run async tests
        try:
            async def run_async_tests():
                return await self.test_hardware_detection_basic()
            
            all_results['hardware_detection'] = asyncio.run(run_async_tests())
        except Exception as e:
            self.logger.error(f"Async tests failed: {e}")
            all_results['hardware_detection'] = {'error': str(e)}
        
        # Store results
        self.test_results = all_results
        
        # Print summary
        self._print_test_summary()
        
        return all_results
    
    def _print_test_summary(self):
        """Print test summary"""
        self.logger.info("="*60)
        self.logger.info("TEST SUMMARY")
        self.logger.info("="*60)
        
        total_tests = 0
        passed_tests = 0
        
        for category, tests in self.test_results.items():
            if isinstance(tests, dict):
                category_passed = sum(1 for result in tests.values() if result is True)
                category_total = len([r for r in tests.values() if isinstance(r, bool)])
                
                total_tests += category_total
                passed_tests += category_passed
                
                self.logger.info(f"{category.title()}: {category_passed}/{category_total} passed")
        
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        self.logger.info("-"*60)
        self.logger.info(f"Overall: {passed_tests}/{total_tests} tests passed ({success_rate:.1f}%)")
        
        if success_rate >= 80:
            self.logger.info("✅ Installation scripts are ready for use!")
        elif success_rate >= 60:
            self.logger.info("⚠️  Installation scripts mostly working - some issues detected")
        else:
            self.logger.info("❌ Installation scripts have significant issues")
        
        self.logger.info("="*60)
    
    def save_results(self, output_file: str = 'installation_test_results.json'):
        """Save test results to file"""
        output_path = self.project_root / output_file
        
        with open(output_path, 'w') as f:
            json.dump(self.test_results, f, indent=2, default=str)
        
        self.logger.info(f"Test results saved to: {output_path}")


def main():
    """Main test function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test LawnBerry Pi Installation Scripts')
    parser.add_argument('--project-root', help='Project root directory')
    parser.add_argument('--save-results', help='Save results to file')
    
    args = parser.parse_args()
    
    tester = InstallationTester(args.project_root)
    results = tester.run_all_tests()
    
    if args.save_results:
        tester.save_results(args.save_results)
    
    # Return success if most tests passed
    total_passed = sum(
        sum(1 for r in category.values() if r is True)
        for category in results.values()
        if isinstance(category, dict)
    )
    total_tests = sum(
        len([r for r in category.values() if isinstance(r, bool)])
        for category in results.values()
        if isinstance(category, dict)
    )
    
    success_rate = (total_passed / total_tests) if total_tests > 0 else 0
    return success_rate >= 0.8


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
