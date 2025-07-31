#!/usr/bin/env python3
"""
CI/CD Automation Script for Coral TPU Installation Tests
Supports automated testing in various environments without hardware dependencies
"""

import pytest
import subprocess
import os
import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from unittest.mock import patch, Mock, MagicMock
import logging
from dataclasses import dataclass
from enum import Enum
import sys


class TestEnvironment(Enum):
    """Supported test environments"""
    CI_GITHUB_ACTIONS = "github_actions"
    CI_GITLAB = "gitlab_ci" 
    DOCKER_CONTAINER = "docker"
    PI_OS_BOOKWORM_REAL = "pi_os_real"
    PI_OS_BOOKWORM_MOCK = "pi_os_mock"
    DEVELOPMENT_LOCAL = "local_dev"


@dataclass 
class EnvironmentConfig:
    """Configuration for test environment"""
    name: str
    has_real_hardware: bool
    mock_hardware: bool
    mock_os_environment: bool
    skip_hardware_tests: bool
    performance_benchmarks: bool
    detailed_logging: bool


class CoralTestCIAutomation:
    """CI/CD automation for Coral TPU installation tests"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.environments = self._setup_environment_configs()
        self.current_env = self._detect_current_environment()
        self.mock_registry = {}
        
    def _setup_environment_configs(self) -> Dict[TestEnvironment, EnvironmentConfig]:
        """Setup configurations for different test environments"""
        return {
            TestEnvironment.CI_GITHUB_ACTIONS: EnvironmentConfig(
                name="GitHub Actions CI",
                has_real_hardware=False,
                mock_hardware=True,
                mock_os_environment=True,
                skip_hardware_tests=True,
                performance_benchmarks=False,
                detailed_logging=True
            ),
            TestEnvironment.CI_GITLAB: EnvironmentConfig(
                name="GitLab CI",
                has_real_hardware=False,
                mock_hardware=True,
                mock_os_environment=True,
                skip_hardware_tests=True,
                performance_benchmarks=False,
                detailed_logging=True
            ),
            TestEnvironment.DOCKER_CONTAINER: EnvironmentConfig(
                name="Docker Container",
                has_real_hardware=False,
                mock_hardware=True,
                mock_os_environment=True,
                skip_hardware_tests=True,
                performance_benchmarks=True,
                detailed_logging=True
            ),
            TestEnvironment.PI_OS_BOOKWORM_REAL: EnvironmentConfig(
                name="Pi OS Bookworm (Real Hardware)",
                has_real_hardware=True,
                mock_hardware=False,
                mock_os_environment=False,
                skip_hardware_tests=False,
                performance_benchmarks=True,
                detailed_logging=True
            ),
            TestEnvironment.PI_OS_BOOKWORM_MOCK: EnvironmentConfig(
                name="Pi OS Bookworm (Mocked Hardware)",
                has_real_hardware=False,
                mock_hardware=True,
                mock_os_environment=False,
                skip_hardware_tests=True,
                performance_benchmarks=True,
                detailed_logging=True
            ),
            TestEnvironment.DEVELOPMENT_LOCAL: EnvironmentConfig(
                name="Local Development",
                has_real_hardware=False,
                mock_hardware=True,
                mock_os_environment=True,
                skip_hardware_tests=True,
                performance_benchmarks=False,
                detailed_logging=False
            )
        }
    
    def _detect_current_environment(self) -> TestEnvironment:
        """Detect current test environment"""
        
        # Check for CI environment variables
        if os.getenv('GITHUB_ACTIONS'):
            return TestEnvironment.CI_GITHUB_ACTIONS
        elif os.getenv('GITLAB_CI'):
            return TestEnvironment.CI_GITLAB
        elif os.getenv('DOCKER_CONTAINER') or Path('/.dockerenv').exists():
            return TestEnvironment.DOCKER_CONTAINER
        
        # Check for Pi OS
        try:
            with open('/etc/os-release', 'r') as f:
                os_release = f.read()
            if 'VERSION_CODENAME=bookworm' in os_release:
                # Check if we have real Coral hardware
                try:
                    result = subprocess.run(['lsusb'], capture_output=True, text=True)
                    if result.returncode == 0 and '18d1:9302' in result.stdout:
                        return TestEnvironment.PI_OS_BOOKWORM_REAL
                    else:
                        return TestEnvironment.PI_OS_BOOKWORM_MOCK
                except:
                    return TestEnvironment.PI_OS_BOOKWORM_MOCK
        except:
            pass
        
        return TestEnvironment.DEVELOPMENT_LOCAL
    
    def setup_environment_mocks(self) -> Dict[str, Any]:
        """Setup mocks based on current environment"""
        config = self.environments[self.current_env]
        mocks = {}
        
        if config.mock_os_environment:
            mocks.update(self._setup_os_mocks())
        
        if config.mock_hardware:
            mocks.update(self._setup_hardware_mocks())
        
        self.mock_registry = mocks
        return mocks
    
    def _setup_os_mocks(self) -> Dict[str, Any]:
        """Setup OS environment mocks"""
        mocks = {}
        
        # Mock /etc/os-release for Pi OS Bookworm
        mock_os_release = """
NAME="Raspberry Pi OS"
VERSION="12 (bookworm)"
ID=raspbian
ID_LIKE=debian
PRETTY_NAME="Raspberry Pi OS (Bookworm)"
VERSION_ID="12"
HOME_URL="http://www.raspberrypi.org/"
SUPPORT_URL="http://www.raspberrypi.org/forums/"
BUG_REPORT_URL="http://www.raspberrypi.org/bugs/"
VERSION_CODENAME=bookworm
"""
        
        # Mock platform information
        mocks['platform.system'] = Mock(return_value='Linux')
        mocks['platform.machine'] = Mock(return_value='aarch64')
        mocks['sys.version_info'] = (3, 11, 2, 'final', 0)
        
        # Mock file system operations
        def mock_open_os_release(*args, **kwargs):
            if '/etc/os-release' in str(args[0]):
                from io import StringIO
                return StringIO(mock_os_release.strip())
            raise FileNotFoundError()
        
        mocks['builtins.open'] = mock_open_os_release
        
        return mocks
    
    def _setup_hardware_mocks(self) -> Dict[str, Any]:
        """Setup hardware mocks"""
        mocks = {}
        
        # Mock subprocess calls
        def mock_subprocess_run(*args, **kwargs):
            command = args[0] if args else []
            
            if 'lsusb' in command:
                # Mock USB devices - can be configured to show/hide Coral
                mock_result = Mock()
                if self._should_mock_coral_present():
                    mock_result.stdout = "Bus 001 Device 002: ID 18d1:9302 Google Inc. Coral Edge TPU"
                else:
                    mock_result.stdout = "Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub"
                mock_result.returncode = 0
                return mock_result
            
            elif 'lspci' in command:
                # Mock PCIe devices
                mock_result = Mock()
                mock_result.stdout = ""
                mock_result.returncode = 0
                return mock_result
            
            elif 'apt-cache' in command:
                # Mock package availability
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = "Package found"
                return mock_result
            
            elif 'apt-get' in command:
                # Mock package installation
                mock_result = Mock()
                if self._should_mock_apt_success():
                    mock_result.returncode = 0
                    mock_result.stdout = "Successfully installed"
                else:
                    mock_result.returncode = 1
                    mock_result.stderr = "Package installation failed"
                return mock_result
            
            elif 'pip' in command:
                # Mock pip installation
                mock_result = Mock()
                if 'pycoral' in str(command):
                    # Mock pip failure for Python 3.11+ ARM64
                    mock_result.returncode = 1
                    mock_result.stderr = "No matching distribution found for pycoral>=2.0.0"
                else:
                    mock_result.returncode = 0
                    mock_result.stdout = "Successfully installed"
                return mock_result
            
            else:
                # Default mock
                mock_result = Mock()
                mock_result.returncode = 0
                mock_result.stdout = ""
                return mock_result
        
        mocks['subprocess.run'] = mock_subprocess_run
        
        # Mock imports
        def mock_import_pycoral():
            if self._should_mock_pycoral_available():
                mock_edgetpu = Mock()
                mock_edgetpu.list_edge_tpus = Mock(return_value=[])
                return mock_edgetpu
            else:
                raise ImportError("No module named 'pycoral'")
        
        mocks['pycoral.utils.edgetpu'] = mock_import_pycoral()
        
        # Mock device nodes
        def mock_pathlib_glob(pattern):
            if 'apex_' in pattern:
                if self._should_mock_coral_present():
                    return [Path('/dev/apex_0')]
                else:
                    return []
            return []
        
        mocks['pathlib.Path.glob'] = mock_pathlib_glob
        
        return mocks
    
    def _should_mock_coral_present(self) -> bool:
        """Determine if we should mock Coral hardware as present"""
        # Can be controlled via environment variables for different test scenarios
        return os.getenv('MOCK_CORAL_PRESENT', 'false').lower() == 'true'
    
    def _should_mock_pycoral_available(self) -> bool:
        """Determine if we should mock PyCoral as available"""
        return os.getenv('MOCK_PYCORAL_AVAILABLE', 'false').lower() == 'true'
    
    def _should_mock_apt_success(self) -> bool:
        """Determine if we should mock apt operations as successful"""
        return os.getenv('MOCK_APT_SUCCESS', 'true').lower() == 'true'
    
    def run_test_suite(self, test_categories: Optional[List[str]] = None) -> Dict[str, Any]:
        """Run appropriate test suite for current environment"""
        config = self.environments[self.current_env]
        
        self.logger.info(f"Running Coral TPU tests in environment: {config.name}")
        
        # Setup mocks
        mocks = self.setup_environment_mocks()
        
        # Determine which tests to run
        if test_categories is None:
            test_categories = self._get_default_test_categories(config)
        
        # Build pytest command
        pytest_args = self._build_pytest_command(config, test_categories)
        
        # Run tests with mocks applied
        with self._apply_mocks(mocks):
            result = self._execute_pytest(pytest_args)
        
        # Generate report
        report = self._generate_test_report(result, config)
        
        return report
    
    def _get_default_test_categories(self, config: EnvironmentConfig) -> List[str]:
        """Get default test categories for environment"""
        categories = ['installation', 'runtime', 'integration']
        
        if config.has_real_hardware:
            categories.append('hardware')
        
        if config.performance_benchmarks:
            categories.append('performance')
        
        return categories
    
    def _build_pytest_command(self, config: EnvironmentConfig, categories: List[str]) -> List[str]:
        """Build pytest command for environment"""
        args = [
            'pytest',
            'tests/coral/',
            '-v',
            '--tb=short',
            '--strict-markers',
        ]
        
        # Add markers based on configuration
        markers = []
        
        if config.skip_hardware_tests:
            markers.append('not real_hardware')
        
        if not config.has_real_hardware:
            markers.append('not hardware')
        
        if 'performance' in categories and config.performance_benchmarks:
            markers.append('performance')
        
        if markers:
            args.extend(['-m', ' and '.join(markers)])
        
        # Add coverage if in CI
        if self.current_env in [TestEnvironment.CI_GITHUB_ACTIONS, TestEnvironment.CI_GITLAB]:
            args.extend([
                '--cov=src',
                '--cov-report=xml:coverage.xml',
                '--cov-report=term-missing'
            ])
        
        # Add detailed logging if configured
        if config.detailed_logging:
            args.extend([
                '--log-cli-level=INFO',
                '--log-cli-format=%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            ])
        
        return args
    
    def _apply_mocks(self, mocks: Dict[str, Any]):
        """Apply mocks as context manager"""
        from contextlib import ExitStack
        
        stack = ExitStack()
        
        for target, mock_obj in mocks.items():
            if '.' in target:
                stack.enter_context(patch(target, mock_obj))
        
        return stack
    
    def _execute_pytest(self, args: List[str]) -> Dict[str, Any]:
        """Execute pytest and return results"""
        try:
            # Run pytest programmatically to capture results
            import pytest
            
            # Capture results
            result = {
                'exit_code': pytest.main(args),
                'environment': self.current_env.value,
                'args': args
            }
            
            return result
            
        except Exception as e:
            return {
                'exit_code': 1,
                'error': str(e),
                'environment': self.current_env.value,
                'args': args
            }
    
    def _generate_test_report(self, result: Dict[str, Any], config: EnvironmentConfig) -> Dict[str, Any]:
        """Generate comprehensive test report"""
        
        report = {
            'environment': {
                'name': config.name,
                'type': self.current_env.value,
                'has_real_hardware': config.has_real_hardware,
                'mocked_components': list(self.mock_registry.keys()) if self.mock_registry else []
            },
            'execution': {
                'exit_code': result.get('exit_code', 1),
                'success': result.get('exit_code', 1) == 0,
                'pytest_args': result.get('args', [])
            },
            'summary': {
                'tests_run': True,
                'hardware_tests_skipped': config.skip_hardware_tests,
                'performance_benchmarks_run': config.performance_benchmarks
            }
        }
        
        if 'error' in result:
            report['execution']['error'] = result['error']
        
        return report
    
    def generate_ci_config_github_actions(self) -> str:
        """Generate GitHub Actions workflow configuration"""
        
        workflow = """
name: Coral TPU Installation Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  coral-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.11, 3.12]
        coral-scenario: [no-coral, mock-coral-present, mock-coral-software]
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-dev.txt
    
    - name: Set up test environment
      run: |
        export MOCK_CORAL_PRESENT=${{ contains(matrix.coral-scenario, 'coral-present') }}
        export MOCK_PYCORAL_AVAILABLE=${{ contains(matrix.coral-scenario, 'coral-software') }}
        export MOCK_APT_SUCCESS=true
    
    - name: Run Coral installation tests
      run: |
        python -m pytest tests/coral/ -v --tb=short \
          --cov=src --cov-report=xml --cov-report=term-missing \
          -m "not real_hardware and not hardware"
    
    - name: Upload coverage reports
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        flags: coral-tests
        name: coral-${{ matrix.python-version }}-${{ matrix.coral-scenario }}
"""
        
        return workflow.strip()
    
    def run_comprehensive_test_matrix(self) -> Dict[str, Any]:
        """Run comprehensive test matrix across scenarios"""
        
        scenarios = [
            {'coral_present': False, 'pycoral_available': False, 'apt_success': True},
            {'coral_present': False, 'pycoral_available': True, 'apt_success': True},
            {'coral_present': True, 'pycoral_available': False, 'apt_success': True},
            {'coral_present': True, 'pycoral_available': True, 'apt_success': True},
            {'coral_present': False, 'pycoral_available': False, 'apt_success': False},
        ]
        
        results = {}
        
        for i, scenario in enumerate(scenarios):
            scenario_name = f"scenario_{i+1}"
            
            # Set environment variables for scenario
            os.environ['MOCK_CORAL_PRESENT'] = str(scenario['coral_present']).lower()
            os.environ['MOCK_PYCORAL_AVAILABLE'] = str(scenario['pycoral_available']).lower()
            os.environ['MOCK_APT_SUCCESS'] = str(scenario['apt_success']).lower()
            
            self.logger.info(f"Running test scenario {i+1}: {scenario}")
            
            # Run tests for this scenario
            scenario_result = self.run_test_suite()
            results[scenario_name] = {
                'scenario': scenario,
                'result': scenario_result
            }
        
        # Generate summary
        summary = {
            'total_scenarios': len(scenarios),
            'successful_scenarios': sum(
                1 for r in results.values() 
                if r['result']['execution']['success']
            ),
            'scenarios': results
        }
        
        return summary


def main():
    """Main entry point for CI automation"""
    automation = CoralTestCIAutomation()
    
    print(f"Detected environment: {automation.current_env.value}")
    print(f"Environment config: {automation.environments[automation.current_env].name}")
    
    # Check command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--generate-github-actions':
            print(automation.generate_ci_config_github_actions())
            return
        elif sys.argv[1] == '--comprehensive-matrix':
            results = automation.run_comprehensive_test_matrix()
            print(json.dumps(results, indent=2))
            return
    
    # Run normal test suite
    results = automation.run_test_suite()
    
    print("\n" + "="*60)
    print("CORAL TPU CI TEST RESULTS")
    print("="*60)
    print(f"Environment: {results['environment']['name']}")
    print(f"Success: {'✅ PASSED' if results['execution']['success'] else '❌ FAILED'}")
    print(f"Exit Code: {results['execution']['exit_code']}")
    
    if results['environment']['mocked_components']:
        print(f"Mocked Components: {', '.join(results['environment']['mocked_components'])}")
    
    print("="*60)
    
    # Exit with appropriate code
    sys.exit(results['execution']['exit_code'])


if __name__ == '__main__':
    main()
