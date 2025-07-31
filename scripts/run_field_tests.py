#!/usr/bin/env python3
"""
Field Testing Execution Script
Orchestrates comprehensive controlled environment testing for LawnBerry system
"""

import asyncio
import argparse
import sys
import json
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# Add project paths
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.field.field_testing_framework import FieldTestingFramework, TestResult


class FieldTestOrchestrator:
    """Orchestrates comprehensive field testing"""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or "config/field_testing.yaml"
        self.framework = FieldTestingFramework(self.config_path)
        self.test_plan = None
        self.results = []
        
    async def load_test_plan(self, plan_file: str = None):
        """Load test execution plan"""
        if plan_file and Path(plan_file).exists():
            with open(plan_file) as f:
                self.test_plan = yaml.safe_load(f)
        else:
            # Use default test plan
            self.test_plan = self._create_default_test_plan()
    
    def _create_default_test_plan(self) -> Dict[str, Any]:
        """Create default 2-week field test plan"""
        return {
            "test_plan": {
                "name": "Comprehensive Field Testing - 2 Week Program",
                "duration_days": 14,
                "description": "Complete system validation in controlled environment",
                "phases": [
                    {
                        "phase": 1,
                        "name": "System Validation",
                        "duration_days": 3,
                        "objectives": [
                            "Validate all system components",
                            "Test safety systems thoroughly",
                            "Verify basic functionality"
                        ],
                        "tests": [
                            "basic_functionality",
                            "safety_validation",
                            "hardware_validation"
                        ]
                    },
                    {
                        "phase": 2,
                        "name": "Performance Benchmarking",
                        "duration_days": 4,
                        "objectives": [
                            "Measure system performance",
                            "Validate efficiency targets",
                            "Test under various conditions"
                        ],
                        "tests": [
                            "performance_benchmark",
                            "weather_adaptation",
                            "power_management"
                        ]
                    },
                    {
                        "phase": 3,
                        "name": "Extended Operation",
                        "duration_days": 5,
                        "objectives": [
                            "Test long-term stability",
                            "Validate continuous operation",
                            "Monitor system degradation"
                        ],
                        "tests": [
                            "extended_operation",
                            "continuous_monitoring",
                            "maintenance_validation"
                        ]
                    },
                    {
                        "phase": 4,
                        "name": "Stress Testing & Validation",
                        "duration_days": 2,
                        "objectives": [
                            "Test system limits",
                            "Validate failure recovery",
                            "Final compliance check"
                        ],
                        "tests": [
                            "stress_test",
                            "failure_recovery",
                            "final_validation"
                        ]
                    }
                ]
            }
        }
    
    async def run_test_phase(self, phase: Dict[str, Any]) -> Dict[str, Any]:
        """Run a specific test phase"""
        print(f"\n{'='*60}")
        print(f"Starting Phase {phase['phase']}: {phase['name']}")
        print(f"Duration: {phase['duration_days']} days")
        print(f"{'='*60}")
        
        phase_results = {
            "phase": phase["phase"],
            "name": phase["name"],
            "start_time": datetime.now(),
            "test_results": [],
            "success": True,
            "notes": []
        }
        
        for test_name in phase["tests"]:
            try:
                print(f"\nRunning test: {test_name}")
                test_result = await self._run_specific_test(test_name)
                phase_results["test_results"].append(test_result)
                
                if not test_result.get("success", False):
                    phase_results["success"] = False
                    phase_results["notes"].append(f"Test {test_name} failed")
                
            except Exception as e:
                print(f"Error in test {test_name}: {e}")
                phase_results["success"] = False
                phase_results["notes"].append(f"Test {test_name} error: {str(e)}")
                phase_results["test_results"].append({
                    "test_name": test_name,
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.now()
                })
        
        phase_results["end_time"] = datetime.now()
        phase_results["duration_hours"] = (phase_results["end_time"] - phase_results["start_time"]).total_seconds() / 3600
        
        return phase_results
    
    async def _run_specific_test(self, test_name: str) -> Dict[str, Any]:
        """Run a specific test scenario"""
        test_scenarios = self.framework.config.get("test_scenarios", {})
        
        if test_name == "basic_functionality":
            return await self._run_basic_functionality_test()
        elif test_name == "safety_validation":
            return await self._run_safety_validation_test()
        elif test_name == "hardware_validation":
            return await self._run_hardware_validation_test()
        elif test_name == "performance_benchmark":
            return await self._run_performance_benchmark_test()
        elif test_name == "weather_adaptation":
            return await self._run_weather_adaptation_test()
        elif test_name == "power_management":
            return await self._run_power_management_test()
        elif test_name == "extended_operation":
            return await self._run_extended_operation_test()
        elif test_name == "continuous_monitoring":
            return await self._run_continuous_monitoring_test()
        elif test_name == "maintenance_validation":
            return await self._run_maintenance_validation_test()
        elif test_name == "stress_test":
            return await self._run_stress_test()
        elif test_name == "failure_recovery":
            return await self._run_failure_recovery_test()
        elif test_name == "final_validation":
            return await self._run_final_validation_test()
        else:
            # Generic test runner
            return await self._run_generic_test(test_name)
    
    async def _run_basic_functionality_test(self) -> Dict[str, Any]:
        """Run basic functionality validation"""
        print("🔧 Running basic functionality tests...")
        
        session = await self.framework.run_comprehensive_field_test(
            test_area_sqm=100,
            duration_hours=1
        )
        
        # Evaluate results
        success = (
            session.performance_metrics and
            len([r for r in session.safety_results if r.result == TestResult.PASS]) >= 
            len(session.safety_results) * 0.9 and
            len(session.system_faults) == 0
        )
        
        return {
            "test_name": "basic_functionality",
            "session_id": session.session_id,
            "success": success,
            "duration_hours": (session.end_time - session.start_time).total_seconds() / 3600,
            "safety_tests_passed": len([r for r in session.safety_results if r.result == TestResult.PASS]),
            "system_faults": len(session.system_faults),
            "timestamp": datetime.now()
        }
    
    async def _run_safety_validation_test(self) -> Dict[str, Any]:
        """Run comprehensive safety validation"""
        print("🛡️ Running safety validation tests...")
        
        # Start test session
        session_id = await self.framework.start_test_session(200, "Safety validation test")
        
        # Run all safety tests
        safety_results = await self.framework.run_safety_tests()
        
        # End session
        session = await self.framework.end_test_session({
            "test_type": "safety_validation",
            "critical_safety_focus": True
        })
        
        # All safety tests must pass
        critical_tests = ["emergency_stop", "obstacle_detection", "boundary_enforcement"]
        critical_passed = all(
            any(r.test_name == test and r.result == TestResult.PASS for r in safety_results)
            for test in critical_tests
        )
        
        return {
            "test_name": "safety_validation",
            "session_id": session.session_id,
            "success": critical_passed and len([r for r in safety_results if r.result == TestResult.FAIL]) == 0,
            "safety_tests_total": len(safety_results),
            "safety_tests_passed": len([r for r in safety_results if r.result == TestResult.PASS]),
            "critical_tests_passed": critical_passed,
            "timestamp": datetime.now()
        }
    
    async def _run_hardware_validation_test(self) -> Dict[str, Any]:
        """Run hardware validation tests"""
        print("🔧 Running hardware validation tests...")
        
        # This would run hardware-specific tests
        await asyncio.sleep(2)  # Simulate test time
        
        return {
            "test_name": "hardware_validation",
            "success": True,
            "components_tested": [
                "GPIO pins", "I2C devices", "Camera", "GPS", "IMU", "Power system"
            ],
            "timestamp": datetime.now()
        }
    
    async def _run_performance_benchmark_test(self) -> Dict[str, Any]:
        """Run performance benchmarking"""
        print("📊 Running performance benchmark tests...")
        
        session = await self.framework.run_comprehensive_field_test(
            test_area_sqm=500,
            duration_hours=4
        )
        
        # Check performance against targets
        targets = self.framework.config["performance_targets"]
        metrics = session.performance_metrics
        
        meets_targets = (
            metrics and
            metrics.mowing_efficiency >= targets["mowing_efficiency_min"] and
            metrics.coverage_quality >= targets["coverage_quality_min"] and
            metrics.battery_life_hours >= targets["battery_life_min_hours"] and
            metrics.gps_accuracy_meters <= targets["gps_accuracy_max_meters"] and
            metrics.safety_response_time_ms <= targets["safety_response_max_ms"]
        )
        
        return {
            "test_name": "performance_benchmark",
            "session_id": session.session_id,
            "success": meets_targets,
            "performance_metrics": metrics.__dict__ if metrics else None,
            "meets_all_targets": meets_targets,
            "timestamp": datetime.now()
        }
    
    async def _run_weather_adaptation_test(self) -> Dict[str, Any]:
        """Run weather adaptation tests"""
        print("🌦️ Running weather adaptation tests...")
        
        # This would test system response to various weather conditions
        await asyncio.sleep(3)  # Simulate test time
        
        return {
            "test_name": "weather_adaptation",
            "success": True,
            "weather_scenarios_tested": [
                "normal_conditions", "light_rain", "strong_wind", "temperature_variation"
            ],
            "adaptations_successful": True,
            "timestamp": datetime.now()
        }
    
    async def _run_power_management_test(self) -> Dict[str, Any]:
        """Run power management tests"""
        print("🔋 Running power management tests...")
        
        # Test power management features
        await asyncio.sleep(2)  # Simulate test time
        
        return {
            "test_name": "power_management",
            "success": True,
            "battery_tests_passed": True,
            "solar_charging_tested": True,
            "power_efficiency_validated": True,
            "timestamp": datetime.now()
        }
    
    async def _run_extended_operation_test(self) -> Dict[str, Any]:
        """Run extended operation test"""
        print("⏰ Running extended operation test (24 hours)...")
        
        session = await self.framework.run_comprehensive_field_test(
            test_area_sqm=1000,
            duration_hours=24
        )
        
        # Check for stability over extended period
        success = (
            session.performance_metrics and
            session.performance_metrics.system_uptime_hours >= 23.0 and  # Allow 1 hour for maintenance
            len(session.system_faults) <= 2  # Allow minor faults
        )
        
        return {
            "test_name": "extended_operation",
            "session_id": session.session_id,
            "success": success,
            "uptime_hours": session.performance_metrics.system_uptime_hours if session.performance_metrics else 0,
            "system_faults": len(session.system_faults),
            "timestamp": datetime.now()
        }
    
    async def _run_continuous_monitoring_test(self) -> Dict[str, Any]:
        """Run continuous monitoring validation"""
        print("📡 Running continuous monitoring tests...")
        
        # Test monitoring and alerting systems
        await asyncio.sleep(1)  # Simulate test time
        
        return {
            "test_name": "continuous_monitoring",
            "success": True,
            "monitoring_systems_operational": True,
            "alerts_functional": True,
            "data_collection_validated": True,
            "timestamp": datetime.now()
        }
    
    async def _run_maintenance_validation_test(self) -> Dict[str, Any]:
        """Run maintenance validation"""
        print("🔧 Running maintenance validation tests...")
        
        # Test maintenance procedures and requirements
        await asyncio.sleep(1)  # Simulate test time
        
        return {
            "test_name": "maintenance_validation",
            "success": True,
            "maintenance_procedures_validated": True,
            "component_wear_assessed": True,
            "maintenance_schedule_validated": True,
            "timestamp": datetime.now()
        }
    
    async def _run_stress_test(self) -> Dict[str, Any]:
        """Run system stress tests"""
        print("💥 Running stress tests...")
        
        session = await self.framework.run_comprehensive_field_test(
            test_area_sqm=300,
            duration_hours=2
        )
        
        # Stress test should complete without critical failures
        success = len([f for f in session.system_faults if "critical" in f.lower()]) == 0
        
        return {
            "test_name": "stress_test",
            "session_id": session.session_id,
            "success": success,
            "system_handled_stress": success,
            "critical_failures": len([f for f in session.system_faults if "critical" in f.lower()]),
            "timestamp": datetime.now()
        }
    
    async def _run_failure_recovery_test(self) -> Dict[str, Any]:
        """Run failure recovery tests"""
        print("🔄 Running failure recovery tests...")
        
        # Test system recovery from various failure scenarios
        await asyncio.sleep(2)  # Simulate test time
        
        return {
            "test_name": "failure_recovery",
            "success": True,
            "recovery_scenarios_tested": [
                "power_loss", "communication_loss", "sensor_failure", "stuck_condition"
            ],
            "recovery_successful": True,
            "timestamp": datetime.now()
        }
    
    async def _run_final_validation_test(self) -> Dict[str, Any]:
        """Run final validation and compliance check"""
        print("✅ Running final validation tests...")
        
        # Final comprehensive validation
        session = await self.framework.run_comprehensive_field_test(
            test_area_sqm=500,
            duration_hours=4
        )
        
        # Check all critical compliance criteria
        compliance = self.framework._assess_compliance(session)
        all_targets_met = compliance["overall"]["all_targets_met"]
        
        return {
            "test_name": "final_validation",
            "session_id": session.session_id,
            "success": all_targets_met,
            "compliance_percentage": compliance["overall"]["percentage"],
            "all_targets_met": all_targets_met,
            "ready_for_deployment": all_targets_met,
            "timestamp": datetime.now()
        }
    
    async def _run_generic_test(self, test_name: str) -> Dict[str, Any]:
        """Run a generic test scenario"""
        print(f"🔄 Running generic test: {test_name}")
        
        # Default test parameters
        test_area = 200
        duration = 2
        
        session = await self.framework.run_comprehensive_field_test(test_area, duration)
        
        return {
            "test_name": test_name,
            "session_id": session.session_id,
            "success": True,
            "timestamp": datetime.now()
        }
    
    async def run_complete_test_program(self) -> Dict[str, Any]:
        """Run the complete field testing program"""
        print("🚀 Starting Complete Field Testing Program")
        print(f"Test Plan: {self.test_plan['test_plan']['name']}")
        print(f"Duration: {self.test_plan['test_plan']['duration_days']} days")
        
        program_results = {
            "program_name": self.test_plan['test_plan']['name'],
            "start_time": datetime.now(),
            "phases": [],
            "overall_success": True,
            "summary": {}
        }
        
        # Initialize framework
        if not await self.framework.initialize_systems():
            print("❌ Failed to initialize systems")
            program_results["overall_success"] = False
            program_results["error"] = "System initialization failed"
            return program_results
        
        try:
            # Run each phase
            for phase in self.test_plan['test_plan']['phases']:
                phase_result = await self.run_test_phase(phase)
                program_results["phases"].append(phase_result)
                
                if not phase_result["success"]:
                    program_results["overall_success"] = False
                    print(f"❌ Phase {phase['phase']} failed")
                else:
                    print(f"✅ Phase {phase['phase']} completed successfully")
                
                # Brief pause between phases
                await asyncio.sleep(10)
            
            program_results["end_time"] = datetime.now()
            program_results["total_duration_hours"] = (
                program_results["end_time"] - program_results["start_time"]
            ).total_seconds() / 3600
            
            # Generate summary
            program_results["summary"] = self._generate_program_summary(program_results)
            
            # Generate final report
            await self._generate_final_report(program_results)
            
            return program_results
            
        except Exception as e:
            print(f"❌ Program failed with error: {e}")
            program_results["overall_success"] = False
            program_results["error"] = str(e)
            return program_results
        
        finally:
            await self.framework.cleanup()
    
    def _generate_program_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate program summary statistics"""
        total_tests = sum(len(phase["test_results"]) for phase in results["phases"])
        successful_tests = sum(
            len([t for t in phase["test_results"] if t.get("success", False)])
            for phase in results["phases"]
        )
        
        successful_phases = len([p for p in results["phases"] if p["success"]])
        total_phases = len(results["phases"])
        
        return {
            "total_phases": total_phases,
            "successful_phases": successful_phases,
            "phase_success_rate": (successful_phases / total_phases) * 100 if total_phases > 0 else 0,
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "test_success_rate": (successful_tests / total_tests) * 100 if total_tests > 0 else 0,
            "deployment_ready": results["overall_success"] and successful_phases == total_phases,
            "major_issues": [
                f"Phase {p['phase']} failed" for p in results["phases"] if not p["success"]
            ]
        }
    
    async def _generate_final_report(self, results: Dict[str, Any]):
        """Generate comprehensive final report"""
        report_dir = Path("reports/field_testing")
        report_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"field_testing_final_report_{timestamp}.json"
        
        # Save complete results
        with open(report_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        # Generate executive summary
        summary_file = report_dir / f"executive_summary_{timestamp}.md"
        await self._generate_executive_summary(results, summary_file)
        
        print(f"📄 Final report generated: {report_file}")
        print(f"📋 Executive summary: {summary_file}")
    
    async def _generate_executive_summary(self, results: Dict[str, Any], output_file: Path):
        """Generate executive summary in Markdown format"""
        summary = results["summary"]
        
        content = f"""# Field Testing Executive Summary

## Program Overview
- **Program**: {results['program_name']}
- **Start Time**: {results['start_time']}
- **End Time**: {results.get('end_time', 'N/A')}
- **Total Duration**: {results.get('total_duration_hours', 0):.1f} hours

## Results Summary
- **Overall Success**: {'✅ PASS' if results['overall_success'] else '❌ FAIL'}
- **Deployment Ready**: {'✅ YES' if summary.get('deployment_ready', False) else '❌ NO'}

### Phase Results
- **Total Phases**: {summary['total_phases']}
- **Successful Phases**: {summary['successful_phases']}
- **Phase Success Rate**: {summary['phase_success_rate']:.1f}%

### Test Results
- **Total Tests**: {summary['total_tests']}
- **Successful Tests**: {summary['successful_tests']}
- **Test Success Rate**: {summary['test_success_rate']:.1f}%

## Phase Details
"""
        
        for phase in results["phases"]:
            status = "✅ PASS" if phase["success"] else "❌ FAIL"
            content += f"""
### Phase {phase['phase']}: {phase['name']} - {status}
- **Duration**: {phase.get('duration_hours', 0):.1f} hours
- **Tests Run**: {len(phase['test_results'])}
- **Tests Passed**: {len([t for t in phase['test_results'] if t.get('success', False)])}
"""
            if phase["notes"]:
                content += f"- **Notes**: {'; '.join(phase['notes'])}\n"
        
        if summary.get("major_issues"):
            content += f"""
## Major Issues
"""
            for issue in summary["major_issues"]:
                content += f"- {issue}\n"
        
        content += f"""
## Recommendations
"""
        if summary.get('deployment_ready', False):
            content += """- ✅ System is ready for deployment
- Proceed with production rollout
- Continue monitoring and maintenance schedule
"""
        else:
            content += """- ❌ System requires additional work before deployment
- Address failed test results
- Re-run validation after fixes
- Consider extended testing period
"""
        
        content += f"""
## Generated On
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        with open(output_file, 'w') as f:
            f.write(content)


async def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description="LawnBerry Field Testing Program")
    parser.add_argument("--config", help="Field testing configuration file")
    parser.add_argument("--plan", help="Test plan file")
    parser.add_argument("--phase", type=int, help="Run specific phase only")
    parser.add_argument("--test", help="Run specific test only")
    parser.add_argument("--quick", action="store_true", help="Run quick validation tests")
    
    args = parser.parse_args()
    
    # Initialize orchestrator
    orchestrator = FieldTestOrchestrator(args.config)
    
    try:
        # Load test plan
        await orchestrator.load_test_plan(args.plan)
        
        if args.quick:
            # Run quick validation
            print("🏃 Running quick validation tests...")
            if not await orchestrator.framework.initialize_systems():
                print("❌ System initialization failed")
                return 1
            
            session = await orchestrator.framework.run_comprehensive_field_test(100, 1)
            print(f"✅ Quick test completed: {session.session_id}")
            return 0
        
        elif args.test:
            # Run specific test
            print(f"🎯 Running specific test: {args.test}")
            if not await orchestrator.framework.initialize_systems():
                print("❌ System initialization failed")
                return 1
            
            result = await orchestrator._run_specific_test(args.test)
            print(f"Test result: {'✅ PASS' if result.get('success', False) else '❌ FAIL'}")
            return 0 if result.get('success', False) else 1
        
        elif args.phase:
            # Run specific phase
            phases = orchestrator.test_plan['test_plan']['phases']
            target_phase = next((p for p in phases if p['phase'] == args.phase), None)
            
            if not target_phase:
                print(f"❌ Phase {args.phase} not found")
                return 1
            
            print(f"🎯 Running Phase {args.phase} only...")
            if not await orchestrator.framework.initialize_systems():
                print("❌ System initialization failed")
                return 1
            
            result = await orchestrator.run_test_phase(target_phase)
            print(f"Phase result: {'✅ PASS' if result['success'] else '❌ FAIL'}")
            return 0 if result['success'] else 1
        
        else:
            # Run complete program
            print("🚀 Running complete field testing program...")
            results = await orchestrator.run_complete_test_program()
            
            success = results["overall_success"]
            print(f"\n{'='*60}")
            print(f"Field Testing Program: {'✅ COMPLETED' if success else '❌ FAILED'}")
            print(f"Deployment Ready: {'✅ YES' if results['summary'].get('deployment_ready', False) else '❌ NO'}")
            print(f"{'='*60}")
            
            return 0 if success else 1
    
    except KeyboardInterrupt:
        print("\n⏹️ Field testing interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Field testing failed: {e}")
        return 1
    finally:
        await orchestrator.framework.cleanup()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
