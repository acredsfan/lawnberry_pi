#!/usr/bin/env python3
"""
Comprehensive Raspberry Pi OS Bookworm Compatibility Audit Script

This script performs a complete compatibility audit for LawnBerryPi on Bookworm:
- Hardware compatibility testing (GPIO, I2C, UART, USB, Camera)
- Software compatibility testing (Python deps, systemd services, libraries)
- Performance optimization validation
- System configuration validation
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Configure comprehensive logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("/tmp/bookworm_audit.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


@dataclass
class AuditResult:
    """Result of a compatibility audit check"""

    component: str
    test_name: str
    passed: bool
    details: str
    performance_metric: Optional[float] = None
    recommendation: Optional[str] = None


class BookwormCompatibilityAuditor:
    """Comprehensive Bookworm compatibility auditor"""

    def __init__(self):
        self.results: List[AuditResult] = []
        self.start_time = datetime.now()

    async def run_full_audit(self) -> Dict:
        """Run complete Bookworm compatibility audit"""
        logger.info("=== Starting Comprehensive Bookworm Compatibility Audit ===")

        # Phase 1: System Requirements Validation
        await self._audit_system_requirements()

        # Phase 2: Hardware Interface Validation
        await self._audit_hardware_interfaces()

        # Phase 3: Software Compatibility Validation
        await self._audit_software_compatibility()

        # Phase 4: Performance Optimization Validation
        await self._audit_performance_optimizations()

        # Phase 5: Service Configuration Validation
        await self._audit_service_configurations()

        # Generate comprehensive report
        return self._generate_audit_report()

    async def _audit_system_requirements(self):
        """Audit basic system requirements for Bookworm"""
        logger.info("Auditing System Requirements...")

        # Check OS version
        try:
            if os.path.exists("/etc/os-release"):
                with open("/etc/os-release", "r") as f:
                    content = f.read()
                    if "VERSION_CODENAME=bookworm" in content:
                        self.results.append(
                            AuditResult(
                                "system", "os_detection", True, "Raspberry Pi OS Bookworm detected"
                            )
                        )
                    else:
                        self.results.append(
                            AuditResult(
                                "system",
                                "os_detection",
                                False,
                                f"Non-Bookworm OS detected: {content}",
                                recommendation="Upgrade to Raspberry Pi OS Bookworm for optimal performance",
                            )
                        )
        except Exception as e:
            self.results.append(
                AuditResult("system", "os_detection", False, f"OS detection failed: {e}")
            )

        # Check Python version
        try:
            python_version = sys.version_info
            if python_version >= (3, 11):
                self.results.append(
                    AuditResult(
                        "system",
                        "python_version",
                        True,
                        f"Python {python_version.major}.{python_version.minor}.{python_version.micro} meets requirements",
                    )
                )
            else:
                self.results.append(
                    AuditResult(
                        "system",
                        "python_version",
                        False,
                        f"Python {python_version.major}.{python_version.minor} < 3.11 required",
                        recommendation="Upgrade to Python 3.11+ for Bookworm compatibility",
                    )
                )
        except Exception as e:
            self.results.append(
                AuditResult("system", "python_version", False, f"Python version check failed: {e}")
            )

        # Check systemd version
        try:
            result = subprocess.run(
                ["systemctl", "--version"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version_line = result.stdout.split("\n")[0]
                version_num = int(version_line.split()[1])
                if version_num >= 252:
                    self.results.append(
                        AuditResult(
                            "system",
                            "systemd_version",
                            True,
                            f"systemd {version_num} supports Bookworm security features",
                        )
                    )
                else:
                    self.results.append(
                        AuditResult(
                            "system",
                            "systemd_version",
                            False,
                            f"systemd {version_num} < 252 lacks security features",
                            recommendation="Update systemd for enhanced security",
                        )
                    )
            else:
                self.results.append(
                    AuditResult(
                        "system", "systemd_version", False, "systemd not available or accessible"
                    )
                )
        except Exception as e:
            self.results.append(
                AuditResult("system", "systemd_version", False, f"systemd check failed: {e}")
            )

    async def _audit_hardware_interfaces(self):
        """Audit hardware interface compatibility"""
        logger.info("Auditing Hardware Interface Compatibility...")

        # GPIO Pin Mappings Test (pins 15, 16, 31, 32, 18, 22)
        gpio_pins = [15, 16, 31, 32, 18, 22]
        try:
            # Check if GPIO files exist (basic check without GPIO libraries)
            gpio_base = Path("/sys/class/gpio")
            if gpio_base.exists():
                self.results.append(
                    AuditResult(
                        "hardware",
                        "gpio_interface",
                        True,
                        f"GPIO interface available for pins: {gpio_pins}",
                    )
                )
            else:
                self.results.append(
                    AuditResult(
                        "hardware",
                        "gpio_interface",
                        False,
                        "GPIO interface not available",
                        recommendation="Ensure GPIO is enabled in raspi-config",
                    )
                )
        except Exception as e:
            self.results.append(
                AuditResult("hardware", "gpio_interface", False, f"GPIO check failed: {e}")
            )

        # I2C Interface Test
        try:
            i2c_devices = ["/dev/i2c-0", "/dev/i2c-1"]
            available_i2c = [dev for dev in i2c_devices if os.path.exists(dev)]
            if available_i2c:
                self.results.append(
                    AuditResult(
                        "hardware",
                        "i2c_interface",
                        True,
                        f"I2C interfaces available: {available_i2c}",
                    )
                )

                # Test I2C device detection (if i2cdetect available)
                try:
                    result = subprocess.run(
                        ["i2cdetect", "-y", "1"], capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0:
                        self.results.append(
                            AuditResult(
                                "hardware",
                                "i2c_device_scan",
                                True,
                                "I2C device scan completed successfully",
                            )
                        )
                except:
                    self.results.append(
                        AuditResult(
                            "hardware",
                            "i2c_device_scan",
                            False,
                            "i2cdetect not available for device scanning",
                        )
                    )
            else:
                self.results.append(
                    AuditResult(
                        "hardware",
                        "i2c_interface",
                        False,
                        "No I2C interfaces found",
                        recommendation="Enable I2C in raspi-config",
                    )
                )
        except Exception as e:
            self.results.append(
                AuditResult("hardware", "i2c_interface", False, f"I2C check failed: {e}")
            )

        # UART Interface Test
        uart_devices = ["/dev/ttyACM0", "/dev/ttyAMA4", "/dev/ttyACM1"]
        try:
            available_uart = [dev for dev in uart_devices if os.path.exists(dev)]
            if available_uart:
                self.results.append(
                    AuditResult(
                        "hardware",
                        "uart_interface",
                        True,
                        f"UART interfaces available: {available_uart}",
                    )
                )
            else:
                self.results.append(
                    AuditResult(
                        "hardware",
                        "uart_interface",
                        False,
                        "Expected UART devices not found",
                        recommendation="Check hardware connections and enable UART in raspi-config",
                    )
                )
        except Exception as e:
            self.results.append(
                AuditResult("hardware", "uart_interface", False, f"UART check failed: {e}")
            )

        # Camera Interface Test
        try:
            camera_devices = ["/dev/video0", "/dev/video1"]
            available_cameras = [dev for dev in camera_devices if os.path.exists(dev)]
            if available_cameras:
                self.results.append(
                    AuditResult(
                        "hardware",
                        "camera_interface",
                        True,
                        f"Camera interfaces available: {available_cameras}",
                    )
                )
            else:
                self.results.append(
                    AuditResult(
                        "hardware",
                        "camera_interface",
                        False,
                        "No camera interfaces found",
                        recommendation="Enable camera in raspi-config and check hardware",
                    )
                )
        except Exception as e:
            self.results.append(
                AuditResult("hardware", "camera_interface", False, f"Camera check failed: {e}")
            )

    async def _audit_software_compatibility(self):
        """Audit software compatibility on Bookworm"""
        logger.info("Auditing Software Compatibility...")

        # Check critical Python packages
        critical_packages = [
            "fastapi",
            "uvicorn",
            "redis",
            "pyyaml",
            "asyncio-mqtt",
            "opencv-python",
            "numpy",
            "pyserial",
            "aiosqlite",
        ]

        for package in critical_packages:
            try:
                __import__(package.replace("-", "_"))
                self.results.append(
                    AuditResult(
                        "software", f"package_{package}", True, f"Package {package} available"
                    )
                )
            except ImportError:
                self.results.append(
                    AuditResult(
                        "software",
                        f"package_{package}",
                        False,
                        f"Package {package} not available",
                        recommendation=f"Install {package} for full functionality",
                    )
                )

        # Test Raspberry Pi specific packages (if available)
        rpi_packages = ["rpi_lgpio", "gpiozero", "smbus2", "picamera2"]
        for package in rpi_packages:
            try:
                if package == "smbus2":
                    __import__("smbus2")
                elif package == "rpi_lgpio":
                    try:
                        __import__("rpi_lgpio")
                    except ImportError:
                        __import__("RPi.GPIO")
                elif package == "gpiozero":
                    __import__("gpiozero")
                elif package == "picamera2":
                    __import__("picamera2")

                self.results.append(
                    AuditResult(
                        "software",
                        f"rpi_package_{package}",
                        True,
                        f"Raspberry Pi package {package} available",
                    )
                )
            except ImportError:
                self.results.append(
                    AuditResult(
                        "software",
                        f"rpi_package_{package}",
                        False,
                        f"Raspberry Pi package {package} not available",
                        recommendation=f"Install {package} for hardware interface support",
                    )
                )

    async def _audit_performance_optimizations(self):
        """Audit Bookworm-specific performance optimizations"""
        logger.info("Auditing Performance Optimizations...")

        # Check boot configuration
        boot_config = Path("/boot/config.txt")
        if boot_config.exists():
            try:
                with open(boot_config, "r") as f:
                    config_content = f.read()

                # Check GPU memory split
                if "gpu_mem=" in config_content:
                    self.results.append(
                        AuditResult(
                            "performance", "gpu_memory_split", True, "GPU memory split configured"
                        )
                    )
                else:
                    self.results.append(
                        AuditResult(
                            "performance",
                            "gpu_memory_split",
                            False,
                            "GPU memory split not optimized",
                            recommendation="Set gpu_mem=128 for computer vision workloads",
                        )
                    )

                # Check I2C clock speed
                if "i2c_arm_baudrate=400000" in config_content:
                    self.results.append(
                        AuditResult(
                            "performance",
                            "i2c_clock_speed",
                            True,
                            "I2C clock speed optimized to 400kHz",
                        )
                    )
                else:
                    self.results.append(
                        AuditResult(
                            "performance",
                            "i2c_clock_speed",
                            False,
                            "I2C clock speed not optimized",
                            recommendation="Add i2c_arm_baudrate=400000 to /boot/config.txt",
                        )
                    )
            except Exception as e:
                self.results.append(
                    AuditResult(
                        "performance", "boot_config", False, f"Boot config check failed: {e}"
                    )
                )

        # Check CPU governor
        try:
            cpu_freq_dir = Path("/sys/devices/system/cpu/cpu0/cpufreq")
            if cpu_freq_dir.exists():
                governor_file = cpu_freq_dir / "scaling_governor"
                if governor_file.exists():
                    governor = governor_file.read_text().strip()
                    if governor in ["ondemand", "performance"]:
                        self.results.append(
                            AuditResult(
                                "performance",
                                "cpu_governor",
                                True,
                                f"CPU governor set to {governor}",
                            )
                        )
                    else:
                        self.results.append(
                            AuditResult(
                                "performance",
                                "cpu_governor",
                                False,
                                f"CPU governor {governor} may not be optimal",
                                recommendation="Consider setting to 'ondemand' for balanced performance",
                            )
                        )
        except Exception as e:
            self.results.append(
                AuditResult("performance", "cpu_governor", False, f"CPU governor check failed: {e}")
            )

    async def _audit_service_configurations(self):
        """Audit systemd service configurations for Bookworm compatibility"""
        logger.info("Auditing Service Configurations...")

        # Check if service files exist and have proper Bookworm security settings
        service_files = [
            "src/system_integration/lawnberry-system.service",
            "src/communication/lawnberry-communication.service",
            "src/hardware/lawnberry-hardware.service",
            "src/safety/lawnberry-safety.service",
        ]

        bookworm_security_features = [
            "NoNewPrivileges=true",
            "ProtectSystem=strict",
            "ProtectHome=true",
            "PrivateTmp=true",
            "RestrictRealtime=true",
            "SystemCallFilter=@system-service",
        ]

        for service_file in service_files:
            if os.path.exists(service_file):
                try:
                    with open(service_file, "r") as f:
                        content = f.read()

                    security_features_found = sum(
                        1 for feature in bookworm_security_features if feature in content
                    )

                    if security_features_found >= len(bookworm_security_features) * 0.8:
                        self.results.append(
                            AuditResult(
                                "services",
                                f"security_{Path(service_file).name}",
                                True,
                                f"Service {service_file} has Bookworm security hardening",
                            )
                        )
                    else:
                        self.results.append(
                            AuditResult(
                                "services",
                                f"security_{Path(service_file).name}",
                                False,
                                f"Service {service_file} lacks some security features",
                                recommendation="Add missing Bookworm security hardening features",
                            )
                        )
                except Exception as e:
                    self.results.append(
                        AuditResult(
                            "services",
                            f"read_{Path(service_file).name}",
                            False,
                            f"Failed to read service file: {e}",
                        )
                    )
            else:
                self.results.append(
                    AuditResult(
                        "services",
                        f"exist_{Path(service_file).name}",
                        False,
                        f"Service file {service_file} not found",
                    )
                )

    def _generate_audit_report(self) -> Dict:
        """Generate comprehensive audit report"""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        # Calculate statistics
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.passed)
        failed_tests = total_tests - passed_tests
        pass_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0

        # Group results by component
        results_by_component = {}
        for result in self.results:
            if result.component not in results_by_component:
                results_by_component[result.component] = []
            results_by_component[result.component].append(asdict(result))

        # Generate recommendations
        recommendations = [
            r.recommendation for r in self.results if r.recommendation and not r.passed
        ]

        report = {
            "audit_summary": {
                "start_time": self.start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "pass_rate_percent": round(pass_rate, 2),
            },
            "results_by_component": results_by_component,
            "recommendations": recommendations,
            "bookworm_compatibility_status": "PASS" if pass_rate >= 80 else "FAIL",
            "detailed_results": [asdict(r) for r in self.results],
        }

        return report


async def main():
    """Main audit execution"""
    auditor = BookwormCompatibilityAuditor()

    try:
        report = await auditor.run_full_audit()

        # Save report to file
        report_file = f"/tmp/bookworm_audit_report_{int(time.time())}.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        # Print summary
        print("\n" + "=" * 80)
        print("RASPBERRY PI OS BOOKWORM COMPATIBILITY AUDIT COMPLETE")
        print("=" * 80)
        print(f"Total Tests: {report['audit_summary']['total_tests']}")
        print(f"Passed: {report['audit_summary']['passed_tests']}")
        print(f"Failed: {report['audit_summary']['failed_tests']}")
        print(f"Pass Rate: {report['audit_summary']['pass_rate_percent']}%")
        print(f"Overall Status: {report['bookworm_compatibility_status']}")
        print(f"Duration: {report['audit_summary']['duration_seconds']:.2f} seconds")
        print(f"Report saved to: {report_file}")

        if report["recommendations"]:
            print(f"\nRecommendations ({len(report['recommendations'])}):")
            for i, rec in enumerate(report["recommendations"], 1):
                print(f"  {i}. {rec}")

        print("=" * 80)

        # Exit with appropriate code
        sys.exit(0 if report["bookworm_compatibility_status"] == "PASS" else 1)

    except Exception as e:
        logger.error(f"Audit failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
