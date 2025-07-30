#!/usr/bin/env python3
"""
Comprehensive Test Automation Script
Runs all test suites with coverage analysis and generates detailed reports
"""

import asyncio
import argparse
import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from tests.framework.test_manager import TestFrameworkManager, CoverageReport


class TestAutomation:
    """Automated test execution and reporting"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config = self._load_config(config_file)
        self.test_manager = TestFrameworkManager()
        self.results = {}
        self.start_time = datetime.now()
        
    def _load_config(self, config_file: Optional[str]) -> Dict[str, Any]:
        """Load test automation configuration"""
        default_config = {
            "test_suites": {
                "unit": {
                    "enabled": True,
                    "parallel": True,
                    "timeout": 300,
                    "retry_failed": 1
                },
                "integration": {
                    "enabled": True,
                    "parallel": False,
                    "timeout": 600,
                    "retry_failed": 1
                },
                "safety": {
                    "enabled": True,
                    "parallel": False,
                    "timeout": 300,
                    "retry_failed": 0,  # No retries for safety tests
                    "required_coverage": 100.0
                },
                "performance": {
                    "enabled": True,
                    "parallel": False,
                    "timeout": 900,
                    "retry_failed": 1
                },
                "hardware": {
                    "enabled": False,  # Disabled by default (requires hardware)
                    "parallel": False,
                    "timeout": 1200,
                    "retry_failed": 0
                }
            },
            "coverage": {
                "overall_threshold": 90.0,
                "safety_critical_threshold": 100.0,
                "fail_under_threshold": True,
                "generate_html_report": True,
                "exclude_patterns": ["*/tests/*", "*/test_*", "*/__pycache__/*"]
            },
            "reporting": {
                "generate_junit_xml": True,
                "generate_html_report": True,
                "generate_json_report": True,
                "upload_results": False,
                "output_directory": "test_reports"
            },
            "notifications": {
                "enabled": False,
                "on_failure_only": True,
                "webhook_url": None
            }
        }
        
        if config_file and Path(config_file).exists():
            import yaml
            with open(config_file) as f:
                user_config = yaml.safe_load(f)
                default_config.update(user_config)
        
        return default_config
    
    async def run_all_tests(self) -> bool:
        """Run all enabled test suites"""
        print("🚀 Starting Comprehensive Test Execution")
        print(f"Started at: {self.start_time.isoformat()}")
        print("-" * 60)
        
        overall_success = True
        
        # Run each test suite
        for suite_name, suite_config in self.config["test_suites"].items():
            if not suite_config["enabled"]:
                print(f"⏭️  Skipping {suite_name} tests (disabled)")
                continue
            
            print(f"\n📋 Running {suite_name} tests...")
            success = await self._run_test_suite(suite_name, suite_config)
            
            if not success:
                overall_success = False
                if suite_name == "safety":
                    print(f"❌ CRITICAL: {suite_name} tests failed - stopping execution")
                    break
        
        # Generate comprehensive report
        await self._generate_final_report(overall_success)
        
        return overall_success
    
    async def _run_test_suite(self, suite_name: str, config: Dict[str, Any]) -> bool:
        """Run a specific test suite"""
        suite_start_time = datetime.now()
        
        try:
            # Determine test path
            test_path = self._get_test_path(suite_name)
            if not test_path.exists():
                print(f"⚠️  Test path not found: {test_path}")
                return False
            
            # Build pytest command
            cmd = self._build_pytest_command(suite_name, test_path, config)
            
            # Run tests
            print(f"Running: {' '.join(cmd)}")
            result = await self._execute_test_command(cmd, config["timeout"])
            
            # Process results
            suite_duration = (datetime.now() - suite_start_time).total_seconds()
            success = result.returncode == 0
            
            self.results[suite_name] = {
                "success": success,
                "duration_s": suite_duration,
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr
            }
            
            if success:
                print(f"✅ {suite_name} tests passed ({suite_duration:.1f}s)")
            else:
                print(f"❌ {suite_name} tests failed ({suite_duration:.1f}s)")
                if config.get("retry_failed", 0) > 0:
                    print(f"🔄 Retrying failed {suite_name} tests...")
                    retry_success = await self._retry_failed_tests(suite_name, config)
                    if retry_success:
                        print(f"✅ {suite_name} tests passed on retry")
                        self.results[suite_name]["success"] = True
                        return True
            
            return success
            
        except Exception as e:
            print(f"❌ Error running {suite_name} tests: {e}")
            self.results[suite_name] = {
                "success": False,
                "error": str(e),
                "duration_s": 0
            }
            return False
    
    def _get_test_path(self, suite_name: str) -> Path:
        """Get test path for suite"""
        test_paths = {
            "unit": Path("tests/unit"),
            "integration": Path("tests/integration"),
            "safety": Path("tests") / "test_safety_system.py",
            "performance": Path("tests/performance"),
            "hardware": Path("tests/hardware")
        }
        
        return test_paths.get(suite_name, Path(f"tests/test_{suite_name}*.py"))
    
    def _build_pytest_command(self, suite_name: str, test_path: Path, config: Dict[str, Any]) -> List[str]:
        """Build pytest command with appropriate options"""
        cmd = ["python", "-m", "pytest", str(test_path)]
        
        # Add common options
        cmd.extend([
            "-v",
            "--tb=short",
            f"--cov=src",
            "--cov-report=term-missing",
            "--cov-report=xml:coverage.xml",
        ])
        
        # Add coverage threshold for safety tests
        if suite_name == "safety":
            cmd.append(f"--cov-fail-under={config.get('required_coverage', 100)}")
        
        # Add markers
        if suite_name in ["unit", "integration", "safety", "performance", "hardware"]:
            cmd.extend(["-m", suite_name])
        
        # Add parallel execution for unit tests
        if config.get("parallel", False) and suite_name == "unit":
            cmd.extend(["-n", "auto"])
        
        # Add JUnit XML output
        if self.config["reporting"]["generate_junit_xml"]:
            cmd.extend(["--junit-xml", f"test_reports/junit_{suite_name}.xml"])
        
        # Add HTML report
        if self.config["reporting"]["generate_html_report"]:
            cmd.extend(["--cov-report=html:htmlcov"])
        
        return cmd
    
    async def _execute_test_command(self, cmd: List[str], timeout: int) -> subprocess.CompletedProcess:
        """Execute test command with timeout"""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=Path.cwd()
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=process.returncode,
                stdout=stdout.decode(),
                stderr=stderr.decode()
            )
            
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=-1,
                stdout="",
                stderr=f"Test execution timed out after {timeout}s"
            )
    
    async def _retry_failed_tests(self, suite_name: str, config: Dict[str, Any]) -> bool:
        """Retry failed tests"""
        # Use pytest's last-failed option
        test_path = self._get_test_path(suite_name)
        cmd = self._build_pytest_command(suite_name, test_path, config)
        cmd.append("--lf")  # Run last failed
        
        result = await self._execute_test_command(cmd, config["timeout"])
        return result.returncode == 0
    
    async def _generate_final_report(self, overall_success: bool):
        """Generate comprehensive final report"""
        end_time = datetime.now()
        total_duration = (end_time - self.start_time).total_seconds()
        
        # Calculate summary statistics
        total_suites = len([s for s in self.config["test_suites"].values() if s["enabled"]])
        passed_suites = len([r for r in self.results.values() if r.get("success", False)])
        failed_suites = total_suites - passed_suites
        
        # Generate report
        report = {
            "timestamp": end_time.isoformat(),
            "overall_success": overall_success,
            "duration_s": total_duration,
            "summary": {
                "total_suites": total_suites,
                "passed_suites": passed_suites,
                "failed_suites": failed_suites,
                "success_rate": (passed_suites / total_suites * 100) if total_suites > 0 else 100
            },
            "suite_results": self.results,
            "configuration": self.config
        }
        
        # Save reports
        await self._save_reports(report)
        
        # Print summary
        self._print_final_summary(report)
        
        # Send notifications if configured
        if self.config["notifications"]["enabled"]:
            await self._send_notifications(report)
    
    async def _save_reports(self, report: Dict[str, Any]):
        """Save test reports in various formats"""
        output_dir = Path(self.config["reporting"]["output_directory"])
        output_dir.mkdir(exist_ok=True)
        
        timestamp = self.start_time.strftime("%Y%m%d_%H%M%S")
        
        # JSON report
        if self.config["reporting"]["generate_json_report"]:
            json_file = output_dir / f"comprehensive_test_report_{timestamp}.json"
            with open(json_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            print(f"📊 JSON report saved: {json_file}")
        
        # HTML report
        if self.config["reporting"]["generate_html_report"]:
            html_file = output_dir / f"comprehensive_test_report_{timestamp}.html"
            await self._generate_html_report(report, html_file)
            print(f"📊 HTML report saved: {html_file}")
        
        # Coverage report (already generated by pytest)
        coverage_file = Path("coverage.xml")
        if coverage_file.exists():
            target_coverage = output_dir / f"coverage_{timestamp}.xml"
            coverage_file.rename(target_coverage)
            print(f"📊 Coverage report saved: {target_coverage}")
    
    async def _generate_html_report(self, report: Dict[str, Any], output_file: Path):
        """Generate HTML test report"""
        success_color = "#28a745" if report["overall_success"] else "#dc3545"
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Comprehensive Test Report - Lawnberry</title>
    <meta charset="utf-8">
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px; background: #f8f9fa; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; border-bottom: 2px solid #dee2e6; padding-bottom: 20px; margin-bottom: 30px; }}
        .status {{ font-size: 1.5em; font-weight: bold; color: {success_color}; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 30px 0; }}
        .metric {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; border-left: 4px solid #007bff; }}
        .metric-value {{ font-size: 2em; font-weight: bold; color: #333; }}
        .metric-label {{ color: #666; margin-top: 5px; }}
        .suite-results {{ margin-top: 40px; }}
        .suite {{ margin-bottom: 20px; padding: 20px; border-radius: 8px; border-left: 4px solid #ccc; }}
        .suite.success {{ border-left-color: #28a745; background: #f8fff9; }}
        .suite.failure {{ border-left-color: #dc3545; background: #fff8f8; }}
        .suite-header {{ font-size: 1.2em; font-weight: bold; margin-bottom: 10px; }}
        .suite-details {{ font-size: 0.9em; color: #666; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #dee2e6; }}
        th {{ background-color: #f8f9fa; font-weight: 600; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #dee2e6; text-align: center; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Lawnberry Autonomous Mower</h1>
            <h2>Comprehensive Test Report</h2>
            <p class="status">{'✅ ALL TESTS PASSED' if report['overall_success'] else '❌ SOME TESTS FAILED'}</p>
            <p>Generated: {report['timestamp']}</p>
        </div>
        
        <div class="summary">
            <div class="metric">
                <div class="metric-value">{report['summary']['total_suites']}</div>
                <div class="metric-label">Total Test Suites</div>
            </div>
            <div class="metric">
                <div class="metric-value">{report['summary']['passed_suites']}</div>
                <div class="metric-label">Passed Suites</div>
            </div>
            <div class="metric">
                <div class="metric-value">{report['summary']['failed_suites']}</div>
                <div class="metric-label">Failed Suites</div>
            </div>
            <div class="metric">
                <div class="metric-value">{report['summary']['success_rate']:.1f}%</div>
                <div class="metric-label">Success Rate</div>
            </div>
            <div class="metric">
                <div class="metric-value">{report['duration_s']:.1f}s</div>
                <div class="metric-label">Total Duration</div>
            </div>
        </div>
        
        <div class="suite-results">
            <h3>📋 Test Suite Results</h3>
        """
        
        for suite_name, result in report["suite_results"].items():
            success_class = "success" if result.get("success", False) else "failure"
            status_icon = "✅" if result.get("success", False) else "❌"
            
            html_content += f"""
            <div class="suite {success_class}">
                <div class="suite-header">
                    {status_icon} {suite_name.title()} Tests
                </div>
                <div class="suite-details">
                    Duration: {result.get('duration_s', 0):.1f}s
                    {'| Error: ' + result.get('error', '') if 'error' in result else ''}
                </div>
            </div>
            """
        
        html_content += f"""
        </div>
        
        <div class="footer">
            <p>Report generated by Lawnberry Test Automation Framework</p>
            <p>For detailed logs and coverage reports, check individual test outputs</p>
        </div>
    </div>
</body>
</html>
        """
        
        with open(output_file, 'w') as f:
            f.write(html_content)
    
    def _print_final_summary(self, report: Dict[str, Any]):
        """Print final test summary"""
        print("\n" + "="*60)
        print("📊 COMPREHENSIVE TEST SUMMARY")
        print("="*60)
        
        if report["overall_success"]:
            print("🎉 ALL TESTS PASSED!")
        else:
            print("❌ SOME TESTS FAILED!")
        
        print(f"⏱️  Total Duration: {report['duration_s']:.1f}s")
        print(f"📋 Test Suites: {report['summary']['passed_suites']}/{report['summary']['total_suites']} passed")
        print(f"📈 Success Rate: {report['summary']['success_rate']:.1f}%")
        
        print("\n📋 Suite Breakdown:")
        for suite_name, result in report["suite_results"].items():
            status = "✅ PASS" if result.get("success", False) else "❌ FAIL"
            duration = result.get("duration_s", 0)
            print(f"  {suite_name:12} {status:8} ({duration:5.1f}s)")
        
        print("="*60)
    
    async def _send_notifications(self, report: Dict[str, Any]):
        """Send notifications about test results"""
        if self.config["notifications"]["on_failure_only"] and report["overall_success"]:
            return
        
        webhook_url = self.config["notifications"]["webhook_url"]
        if not webhook_url:
            return
        
        # Prepare notification payload
        status = "SUCCESS" if report["overall_success"] else "FAILURE"
        color = "#28a745" if report["overall_success"] else "#dc3545"
        
        payload = {
            "embeds": [{
                "title": f"Lawnberry Test Results - {status}",
                "description": f"Comprehensive test execution completed",
                "color": int(color.replace("#", ""), 16),
                "fields": [
                    {
                        "name": "Success Rate",
                        "value": f"{report['summary']['success_rate']:.1f}%",
                        "inline": True
                    },
                    {
                        "name": "Duration", 
                        "value": f"{report['duration_s']:.1f}s",
                        "inline": True
                    },
                    {
                        "name": "Suites",
                        "value": f"{report['summary']['passed_suites']}/{report['summary']['total_suites']}",
                        "inline": True
                    }
                ],
                "timestamp": report["timestamp"]
            }]
        }
        
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status == 204:
                        print("📨 Notification sent successfully")
                    else:
                        print(f"⚠️  Notification send failed: {response.status}")
        except Exception as e:
            print(f"⚠️  Notification error: {e}")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Run comprehensive test suite")
    parser.add_argument("--config", help="Test configuration file")
    parser.add_argument("--suites", nargs="+", help="Specific test suites to run")
    parser.add_argument("--hardware", action="store_true", help="Enable hardware tests")
    parser.add_argument("--skip-safety", action="store_true", help="Skip safety tests (NOT RECOMMENDED)")
    parser.add_argument("--parallel", action="store_true", help="Enable parallel test execution")
    parser.add_argument("--timeout", type=int, default=1800, help="Global timeout in seconds")
    
    args = parser.parse_args()
    
    # Create test automation instance
    automation = TestAutomation(args.config)
    
    # Override configuration based on arguments
    if args.suites:
        # Disable all suites first, then enable specified ones
        for suite in automation.config["test_suites"]:
            automation.config["test_suites"][suite]["enabled"] = False
        for suite in args.suites:
            if suite in automation.config["test_suites"]:
                automation.config["test_suites"][suite]["enabled"] = True
    
    if args.hardware:
        automation.config["test_suites"]["hardware"]["enabled"] = True
    
    if args.skip_safety:
        print("⚠️  WARNING: Safety tests disabled - NOT RECOMMENDED FOR PRODUCTION!")
        automation.config["test_suites"]["safety"]["enabled"] = False
    
    if args.parallel:
        for suite in automation.config["test_suites"].values():
            suite["parallel"] = True
    
    # Run tests
    try:
        success = await automation.run_all_tests()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n🛑 Test execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"💥 Test execution failed with error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
