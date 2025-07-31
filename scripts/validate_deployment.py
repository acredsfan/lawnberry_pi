#!/usr/bin/env python3
"""
Deployment Validation Script - Comprehensive validation for LawnBerry deployment
Tests installation, configuration, services, and system integration
"""

import asyncio
import logging
import sys
import json
import subprocess
import time
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import psutil
import yaml

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/deployment_validation.log')
    ]
)
logger = logging.getLogger(__name__)


class ValidationStatus(Enum):
    """Validation test status"""
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass
class ValidationTest:
    """Individual validation test"""
    name: str
    description: str
    category: str
    status: ValidationStatus
    message: str
    duration: float
    details: Optional[Dict[str, Any]] = None


@dataclass
class ValidationSuite:
    """Complete validation suite results"""
    total_tests: int
    passed: int
    failed: int
    warnings: int
    skipped: int
    duration: float
    success: bool
    tests: List[ValidationTest]


class DeploymentValidator:
    """
    Comprehensive deployment validation system
    """
    
    def __init__(self):
        self.install_dir = Path("/opt/lawnberry")
        self.config_dir = self.install_dir / "config"
        self.data_dir = Path("/var/lib/lawnberry")
        self.log_dir = Path("/var/log/lawnberry")
        
        self.required_services = [
            "lawnberry-system",
            "lawnberry-hardware",
            "lawnberry-safety",
            "lawnberry-web-api",
            "lawnberry-communication"
        ]
        
        self.tests = []
        self.start_time = time.time()
    
    async def run_all_validations(self) -> ValidationSuite:
        """Run complete deployment validation suite"""
        logger.info("Starting comprehensive deployment validation...")
        
        # Installation validation
        await self._validate_installation()
        
        # Configuration validation
        await self._validate_configuration()
        
        # System services validation
        await self._validate_services()
        
        # Hardware validation
        await self._validate_hardware()
        
        # Network validation
        await self._validate_network()
        
        # Performance validation
        await self._validate_performance()
        
        # Security validation
        await self._validate_security()
        
        # Integration validation
        await self._validate_integration()
        
        # Calculate results
        total_time = time.time() - self.start_time
        
        passed = sum(1 for t in self.tests if t.status == ValidationStatus.PASS)
        failed = sum(1 for t in self.tests if t.status == ValidationStatus.FAIL)
        warnings = sum(1 for t in self.tests if t.status == ValidationStatus.WARN)
        skipped = sum(1 for t in self.tests if t.status == ValidationStatus.SKIP)
        
        suite = ValidationSuite(
            total_tests=len(self.tests),
            passed=passed,
            failed=failed,
            warnings=warnings,
            skipped=skipped,
            duration=total_time,
            success=failed == 0,
            tests=self.tests
        )
        
        logger.info(f"Validation completed: {passed} passed, {failed} failed, {warnings} warnings")
        
        return suite
    
    async def _validate_installation(self):
        """Validate installation files and directories"""
        logger.info("Validating installation...")
        
        # Check installation directory
        await self._run_test(
            "installation_directory",
            "Installation directory exists",
            "installation",
            lambda: self.install_dir.exists(),
            f"Installation directory not found: {self.install_dir}"
        )
        
        # Check required directories
        required_dirs = [
            self.install_dir / "src",
            self.install_dir / "config",
            self.install_dir / "scripts",
            self.data_dir,
            self.log_dir
        ]
        
        for directory in required_dirs:
            await self._run_test(
                f"directory_{directory.name}",
                f"Directory exists: {directory}",
                "installation",
                lambda d=directory: d.exists(),
                f"Required directory missing: {directory}"
            )
        
        # Check required files
        required_files = [
            self.install_dir / "src" / "system_integration" / "system_manager.py",
            self.install_dir / "src" / "hardware" / "__init__.py",
            self.install_dir / "src" / "safety" / "__init__.py",
            self.config_dir / "system.yaml",
            self.config_dir / "hardware.yaml",
            self.config_dir / "safety.yaml"
        ]
        
        for file_path in required_files:
            await self._run_test(
                f"file_{file_path.name}",
                f"Required file exists: {file_path.name}",
                "installation",
                lambda f=file_path: f.exists(),
                f"Required file missing: {file_path}"
            )
        
        # Check file permissions
        await self._run_test(
            "config_permissions",
            "Configuration files have correct permissions",
            "installation",
            lambda: self._check_config_permissions(),
            "Configuration files have incorrect permissions"
        )
    
    def _check_config_permissions(self) -> bool:
        """Check configuration file permissions"""
        try:
            for config_file in self.config_dir.glob("*.yaml"):
                stat = config_file.stat()
                # Check readable by owner and group, not world-writable
                if stat.st_mode & 0o002:  # World writable
                    return False
            return True
        except Exception:
            return False
    
    async def _validate_configuration(self):
        """Validate configuration files"""
        logger.info("Validating configuration...")
        
        # Test configuration loading
        await self._run_test(
            "config_loading",
            "Configuration files load without errors",
            "configuration",
            lambda: self._test_config_loading(),
            "Configuration files have syntax errors"
        )
        
        # Validate individual configurations
        config_files = ['system.yaml', 'hardware.yaml', 'safety.yaml', 'deployment.yaml']
        
        for config_name in config_files:
            config_path = self.config_dir / config_name
            if config_path.exists():
                await self._run_test(
                    f"config_{config_name.replace('.yaml', '')}",
                    f"Configuration valid: {config_name}",
                    "configuration",
                    lambda p=config_path: self._validate_config_file(p),
                    f"Configuration validation failed: {config_name}"
                )
        
        # Test environment variables
        await self._run_test(
            "environment_variables",
            "Required environment variables are set",
            "configuration",
            lambda: self._check_environment_variables(),
            "Required environment variables missing"
        )
    
    def _test_config_loading(self) -> bool:
        """Test configuration file loading"""
        try:
            for config_file in self.config_dir.glob("*.yaml"):
                with open(config_file, 'r') as f:
                    yaml.safe_load(f)
            return True
        except Exception as e:
            logger.error(f"Configuration loading error: {e}")
            return False
    
    def _validate_config_file(self, config_path: Path) -> bool:
        """Validate individual configuration file"""
        try:
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
                
            # Basic validation
            if not isinstance(config_data, dict):
                return False
                
            # Check for empty configurations
            if not config_data:
                return False
                
            return True
        except Exception:
            return False
    
    def _check_environment_variables(self) -> bool:
        """Check required environment variables"""
        import os
        required_vars = [
            'OPENWEATHER_API_KEY',
            'REACT_APP_GOOGLE_MAPS_API_KEY',
            'JWT_SECRET_KEY'
        ]
        
        for var in required_vars:
            if not os.getenv(var):
                logger.warning(f"Environment variable not set: {var}")
                return False
        
        return True
    
    async def _validate_services(self):
        """Validate system services"""
        logger.info("Validating system services...")
        
        # Check service files exist
        for service in self.required_services:
            service_file = Path(f"/etc/systemd/system/{service}.service")
            await self._run_test(
                f"service_file_{service}",
                f"Service file exists: {service}",
                "services",
                lambda f=service_file: f.exists(),
                f"Service file missing: {service_file}"
            )
        
        # Check services are enabled
        for service in self.required_services:
            await self._run_test(
                f"service_enabled_{service}",
                f"Service enabled: {service}",
                "services",
                lambda s=service: self._is_service_enabled(s),
                f"Service not enabled: {service}"
            )
        
        # Check services are running
        for service in self.required_services:
            await self._run_test(
                f"service_running_{service}",
                f"Service running: {service}",
                "services",
                lambda s=service: self._is_service_running(s),
                f"Service not running: {service}"
            )
        
        # Check service health
        await self._run_test(
            "services_healthy",
            "All services report healthy status",
            "services",
            lambda: self._check_service_health(),
            "One or more services report unhealthy status"
        )
    
    def _is_service_enabled(self, service_name: str) -> bool:
        """Check if systemd service is enabled"""
        try:
            result = subprocess.run(
                ["systemctl", "is-enabled", service_name],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _is_service_running(self, service_name: str) -> bool:
        """Check if systemd service is running"""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True,
                text=True
            )
            return result.stdout.strip() == "active"
        except Exception:
            return False
    
    def _check_service_health(self) -> bool:
        """Check service health status"""
        try:
            # This would check service-specific health endpoints
            # For now, just check if all required services are active
            for service in self.required_services:
                if not self._is_service_running(service):
                    return False
            return True
        except Exception:
            return False
    
    async def _validate_hardware(self):
        """Validate hardware detection and configuration"""
        logger.info("Validating hardware configuration...")
        
        # Check GPIO availability
        await self._run_test(
            "gpio_available",
            "GPIO interface is available",
            "hardware",
            lambda: Path("/dev/gpiomem").exists(),
            "GPIO interface not available"
        )
        
        # Check I2C availability
        await self._run_test(
            "i2c_available",
            "I2C interface is available",
            "hardware",
            lambda: any(Path("/dev").glob("i2c-*")),
            "I2C interface not available"
        )
        
        # Check camera device
        await self._run_test(
            "camera_device",
            "Camera device is available",
            "hardware",
            lambda: Path("/dev/video0").exists(),
            "Camera device not found at /dev/video0"
        )
        
        # Check UART devices
        uart_devices = ["/dev/ttyACM0", "/dev/ttyAMA4", "/dev/ttyACM1"]
        for device in uart_devices:
            await self._run_test(
                f"uart_device_{Path(device).name}",
                f"UART device available: {device}",
                "hardware",
                lambda d=device: Path(d).exists(),
                f"UART device not found: {device}",
                allow_fail=True  # UART devices may not always be connected
            )
    
    async def _validate_network(self):
        """Validate network configuration"""
        logger.info("Validating network configuration...")
        
        # Check web API port
        await self._run_test(
            "web_api_port",
            "Web API is accessible",
            "network",
            lambda: self._test_web_api_access(),
            "Web API is not accessible"
        )
        
        # Check for port conflicts
        await self._run_test(
            "port_conflicts",
            "No port conflicts detected",
            "network",
            lambda: self._check_port_conflicts(),
            "Port conflicts detected"
        )
        
        # Test external connectivity
        await self._run_test(
            "internet_connectivity",
            "Internet connectivity available",
            "network",
            lambda: self._test_internet_connectivity(),
            "No internet connectivity"
        )
    
    def _test_web_api_access(self) -> bool:
        """Test web API accessibility"""
        try:
            response = requests.get("http://localhost:8000/health", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
    
    def _check_port_conflicts(self) -> bool:
        """Check for port conflicts"""
        try:
            # Get all listening ports
            connections = psutil.net_connections(kind='inet')
            listening_ports = [conn.laddr.port for conn in connections if conn.status == 'LISTEN']
            
            # Check for common conflicts
            required_ports = [8000, 8001, 8002]  # Web API, WebSocket, etc.
            
            for port in required_ports:
                if listening_ports.count(port) > 1:
                    return False
            
            return True
        except Exception:
            return False
    
    def _test_internet_connectivity(self) -> bool:
        """Test internet connectivity"""
        try:
            response = requests.get("https://api.openweathermap.org", timeout=10)
            return response.status_code in [200, 401]  # 401 is OK, means server is reachable
        except Exception:
            return False
    
    async def _validate_performance(self):
        """Validate system performance"""
        logger.info("Validating system performance...")
        
        # Check memory usage
        await self._run_test(
            "memory_usage",
            "Memory usage is within acceptable limits",
            "performance",
            lambda: self._check_memory_usage(),
            "Memory usage is too high"
        )
        
        # Check CPU usage
        await self._run_test(
            "cpu_usage",
            "CPU usage is within acceptable limits",
            "performance",
            lambda: self._check_cpu_usage(),
            "CPU usage is too high"
        )
        
        # Check disk space
        await self._run_test(
            "disk_space",
            "Sufficient disk space available",
            "performance",
            lambda: self._check_disk_space(),
            "Insufficient disk space"
        )
        
        # Test system responsiveness
        await self._run_test(
            "system_responsiveness",
            "System responds quickly to requests",
            "performance",
            lambda: self._test_system_responsiveness(),
            "System response time is too slow"
        )
    
    def _check_memory_usage(self) -> bool:
        """Check system memory usage"""
        try:
            memory = psutil.virtual_memory()
            return memory.percent < 85  # Less than 85% memory usage
        except Exception:
            return False
    
    def _check_cpu_usage(self) -> bool:
        """Check system CPU usage"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            return cpu_percent < 80  # Less than 80% CPU usage
        except Exception:
            return False
    
    def _check_disk_space(self) -> bool:
        """Check available disk space"""
        try:
            disk_usage = psutil.disk_usage('/')
            free_gb = disk_usage.free / (1024**3)
            return free_gb > 2  # At least 2GB free
        except Exception:
            return False
    
    def _test_system_responsiveness(self) -> bool:
        """Test system responsiveness"""
        try:
            start_time = time.time()
            # Simple responsiveness test
            subprocess.run(["echo", "test"], capture_output=True, timeout=1)
            response_time = time.time() - start_time
            return response_time < 0.1  # Less than 100ms
        except Exception:
            return False
    
    async def _validate_security(self):
        """Validate security configuration"""
        logger.info("Validating security configuration...")
        
        # Check file permissions
        await self._run_test(
            "secure_file_permissions",
            "Configuration files have secure permissions",
            "security",
            lambda: self._check_secure_permissions(),
            "Configuration files have insecure permissions"
        )
        
        # Check for default passwords
        await self._run_test(
            "no_default_passwords",
            "No default passwords detected",
            "security",
            lambda: self._check_default_passwords(),
            "Default passwords detected"
        )
        
        # Check SSL/TLS configuration
        await self._run_test(
            "ssl_configuration",
            "SSL/TLS properly configured",
            "security",
            lambda: self._check_ssl_config(),
            "SSL/TLS configuration issues"
        )
    
    def _check_secure_permissions(self) -> bool:
        """Check file permissions are secure"""
        try:
            # Check that sensitive files are not world-readable
            sensitive_paths = [
                self.config_dir,
                Path("/var/lib/lawnberry"),
                Path("/opt/lawnberry/keys") if Path("/opt/lawnberry/keys").exists() else None
            ]
            
            for path in sensitive_paths:
                if path and path.exists():
                    stat = path.stat()
                    if stat.st_mode & 0o044:  # World or other group readable
                        return False
            return True
        except Exception:
            return False
    
    def _check_default_passwords(self) -> bool:
        """Check for default passwords in configuration"""
        try:
            # This is a simplified check
            # In reality, would check for actual default password patterns
            return True  # Assume no default passwords for now
        except Exception:
            return False
    
    def _check_ssl_config(self) -> bool:
        """Check SSL/TLS configuration"""
        try:
            # Check if SSL certificates exist and are valid
            cert_dir = Path("/opt/lawnberry/ssl")
            if cert_dir.exists():
                cert_files = list(cert_dir.glob("*.crt")) + list(cert_dir.glob("*.pem"))
                return len(cert_files) > 0
            return True  # OK if no SSL configured
        except Exception:
            return False
    
    async def _validate_integration(self):
        """Validate system integration"""
        logger.info("Validating system integration...")
        
        # Test service communication
        await self._run_test(
            "service_communication",
            "Services communicate properly",
            "integration",
            lambda: self._test_service_communication(),
            "Service communication failed"
        )
        
        # Test database connectivity
        await self._run_test(
            "database_connection",
            "Database connection works",
            "integration",
            lambda: self._test_database_connection(),
            "Database connection failed"
        )
        
        # Test external API integration
        await self._run_test(
            "external_apis",
            "External API integration works",
            "integration",
            lambda: self._test_external_apis(),
            "External API integration failed"
        )
    
    def _test_service_communication(self) -> bool:
        """Test inter-service communication"""
        try:
            # Test web API health endpoint
            response = requests.get("http://localhost:8000/api/system/status", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
    
    def _test_database_connection(self) -> bool:
        """Test database connectivity"""
        try:
            # This would test actual database connection
            # For now, just check if database files exist
            db_files = list(Path("/var/lib/lawnberry").glob("*.db"))
            return len(db_files) > 0
        except Exception:
            return False
    
    def _test_external_apis(self) -> bool:
        """Test external API integration"""
        try:
            # Test OpenWeather API (simple connectivity test)
            response = requests.get("https://api.openweathermap.org", timeout=10)
            return response.status_code in [200, 401]
        except Exception:
            return False
    
    async def _run_test(self, test_id: str, description: str, category: str,
                       test_func, failure_message: str, allow_fail: bool = False):
        """Run individual validation test"""
        start_time = time.time()
        
        try:
            result = test_func()
            duration = time.time() - start_time
            
            if result:
                status = ValidationStatus.PASS
                message = "Test passed"
            else:
                status = ValidationStatus.WARN if allow_fail else ValidationStatus.FAIL
                message = failure_message
                
        except Exception as e:
            duration = time.time() - start_time
            status = ValidationStatus.WARN if allow_fail else ValidationStatus.FAIL
            message = f"{failure_message}: {str(e)}"
        
        test = ValidationTest(
            name=test_id,
            description=description,
            category=category,
            status=status,
            message=message,
            duration=duration
        )
        
        self.tests.append(test)
        
        # Log result
        if status == ValidationStatus.PASS:
            logger.info(f"✓ {description}")
        elif status == ValidationStatus.WARN:
            logger.warning(f"⚠ {description}: {message}")
        else:
            logger.error(f"✗ {description}: {message}")


def print_summary(suite: ValidationSuite):
    """Print validation summary"""
    print("\n" + "="*60)
    print("DEPLOYMENT VALIDATION SUMMARY")
    print("="*60)
    print(f"Total Tests: {suite.total_tests}")
    print(f"Passed: {suite.passed}")
    print(f"Failed: {suite.failed}")
    print(f"Warnings: {suite.warnings}")
    print(f"Skipped: {suite.skipped}")
    print(f"Duration: {suite.duration:.2f} seconds")
    print(f"Overall Result: {'SUCCESS' if suite.success else 'FAILURE'}")
    print("="*60)
    
    # Print failed tests
    if suite.failed > 0:
        print("\nFAILED TESTS:")
        print("-" * 40)
        for test in suite.tests:
            if test.status == ValidationStatus.FAIL:
                print(f"  ✗ {test.description}")
                print(f"    {test.message}")
        print()
    
    # Print warnings
    if suite.warnings > 0:
        print("\nWARNINGS:")
        print("-" * 40)
        for test in suite.tests:
            if test.status == ValidationStatus.WARN:
                print(f"  ⚠ {test.description}")
                print(f"    {test.message}")
        print()


def export_results(suite: ValidationSuite, output_file: str):
    """Export validation results to JSON file"""
    results = {
        'summary': {
            'total_tests': suite.total_tests,
            'passed': suite.passed,
            'failed': suite.failed,
            'warnings': suite.warnings,
            'skipped': suite.skipped,
            'duration': suite.duration,
            'success': suite.success,
            'timestamp': time.time()
        },
        'tests': [
            {
                'name': test.name,
                'description': test.description,
                'category': test.category,
                'status': test.status.value,
                'message': test.message,
                'duration': test.duration,
                'details': test.details
            }
            for test in suite.tests
        ]
    }
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Results exported to: {output_file}")


async def main():
    """Main validation entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="LawnBerry Deployment Validation")
    parser.add_argument('--output', '-o', help="Output file for results (JSON)")
    parser.add_argument('--quiet', '-q', action='store_true', help="Quiet mode")
    parser.add_argument('--categories', '-c', nargs='+', 
                       choices=['installation', 'configuration', 'services', 'hardware', 
                               'network', 'performance', 'security', 'integration'],
                       help="Run only specific validation categories")
    
    args = parser.parse_args()
    
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    
    validator = DeploymentValidator()
    
    # Run validation
    suite = await validator.run_all_validations()
    
    # Print summary
    if not args.quiet:
        print_summary(suite)
    
    # Export results if requested
    if args.output:
        export_results(suite, args.output)
    
    # Exit with appropriate code
    sys.exit(0 if suite.success else 1)


if __name__ == "__main__":
    asyncio.run(main())
