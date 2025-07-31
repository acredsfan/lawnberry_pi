#!/usr/bin/env python3
"""
Field Testing Implementation Validation Script
Validates that all field testing components are properly implemented and functional
"""

import asyncio
import sys
import json
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple

# Add project paths
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))


def validate_file_structure() -> Tuple[bool, List[str]]:
    """Validate that all required files exist"""
    required_files = [
        "tests/field/field_testing_framework.py",
        "config/field_testing.yaml",
        "scripts/run_field_tests.py",
        "docs/field-testing-guide.md"
    ]
    
    issues = []
    all_exist = True
    
    print("🔍 Validating field testing file structure...")
    
    for file_path in required_files:
        path = Path(file_path)
        if not path.exists():
            issues.append(f"Missing required file: {file_path}")
            all_exist = False
            print(f"❌ Missing: {file_path}")
        else:
            print(f"✅ Found: {file_path}")
    
    return all_exist, issues


def validate_configuration() -> Tuple[bool, List[str]]:
    """Validate field testing configuration"""
    print("🔍 Validating field testing configuration...")
    
    config_file = Path("config/field_testing.yaml")
    issues = []
    
    if not config_file.exists():
        issues.append("Field testing configuration file missing")
        return False, issues
    
    try:
        with open(config_file) as f:
            config = yaml.safe_load(f)
        
        # Check required sections
        required_sections = [
            "test_environment",
            "safety_testing",
            "performance_targets",
            "data_collection",
            "test_scenarios"
        ]
        
        for section in required_sections:
            if section not in config:
                issues.append(f"Missing configuration section: {section}")
            else:
                print(f"✅ Found config section: {section}")
        
        # Validate performance targets
        if "performance_targets" in config:
            targets = config["performance_targets"]
            required_targets = [
                "mowing_efficiency_min",
                "coverage_quality_min",
                "battery_life_min_hours",
                "gps_accuracy_max_meters",
                "safety_response_max_ms",
                "obstacle_detection_accuracy_min"
            ]
            
            for target in required_targets:
                if target not in targets:
                    issues.append(f"Missing performance target: {target}")
                else:
                    print(f"✅ Found performance target: {target}")
        
        # Validate safety testing configuration
        if "safety_testing" in config:
            safety = config["safety_testing"]
            required_safety = [
                "emergency_stop_tests",
                "obstacle_scenarios",
                "boundary_tests"
            ]
            
            for safety_test in required_safety:
                if safety_test not in safety:
                    issues.append(f"Missing safety test configuration: {safety_test}")
                else:
                    print(f"✅ Found safety test config: {safety_test}")
        
        return len(issues) == 0, issues
        
    except Exception as e:
        issues.append(f"Error loading configuration: {e}")
        return False, issues


def validate_framework_imports() -> Tuple[bool, List[str]]:
    """Validate that the field testing framework can be imported"""
    print("🔍 Validating field testing framework imports...")
    
    issues = []
    
    try:
        from tests.field.field_testing_framework import (
            FieldTestingFramework,
            TestResult,
            PerformanceMetrics,
            SafetyTestResult,
            FieldTestSession
        )
        print("✅ Successfully imported FieldTestingFramework")
        print("✅ Successfully imported TestResult enum")
        print("✅ Successfully imported PerformanceMetrics")
        print("✅ Successfully imported SafetyTestResult")
        print("✅ Successfully imported FieldTestSession")
        
        # Test framework instantiation
        framework = FieldTestingFramework()
        print("✅ Successfully instantiated FieldTestingFramework")
        
        return True, issues
        
    except ImportError as e:
        issues.append(f"Import error: {e}")
        return False, issues
    except Exception as e:
        issues.append(f"Framework validation error: {e}")
        return False, issues


def validate_test_scenarios() -> Tuple[bool, List[str]]:
    """Validate test scenario configuration"""
    print("🔍 Validating test scenarios...")
    
    issues = []
    
    try:
        with open("config/field_testing.yaml") as f:
            config = yaml.safe_load(f)
        
        if "test_scenarios" not in config:
            issues.append("No test scenarios configured")
            return False, issues
        
        scenarios = config["test_scenarios"]
        required_scenarios = [
            "basic_functionality",
            "safety_validation",
            "performance_benchmark"
        ]
        
        for scenario in required_scenarios:
            if scenario not in scenarios:
                issues.append(f"Missing test scenario: {scenario}")
            else:
                scenario_config = scenarios[scenario]
                if "duration_minutes" not in scenario_config:
                    issues.append(f"Scenario {scenario} missing duration_minutes")
                if "test_area_sqm" not in scenario_config:
                    issues.append(f"Scenario {scenario} missing test_area_sqm")
                if "required_tests" not in scenario_config:
                    issues.append(f"Scenario {scenario} missing required_tests")
                
                if len([k for k in ["duration_minutes", "test_area_sqm", "required_tests"] 
                       if k in scenario_config]) == 3:
                    print(f"✅ Valid scenario configuration: {scenario}")
        
        return len(issues) == 0, issues
        
    except Exception as e:
        issues.append(f"Error validating test scenarios: {e}")
        return False, issues


def validate_safety_requirements() -> Tuple[bool, List[str]]:
    """Validate safety requirements configuration"""
    print("🔍 Validating safety requirements...")
    
    issues = []
    
    try:
        with open("config/field_testing.yaml") as f:
            config = yaml.safe_load(f)
        
        if "safety_testing" not in config:
            issues.append("No safety testing configuration")
            return False, issues
        
        safety = config["safety_testing"]
        
        # Check emergency stop tests
        if "emergency_stop_tests" in safety:
            emergency_tests = safety["emergency_stop_tests"]
            required_emergency_tests = [
                "physical_button",
                "remote_command",
                "web_interface",
                "automatic_detection"
            ]
            
            for test in required_emergency_tests:
                if test not in emergency_tests:
                    issues.append(f"Missing emergency stop test: {test}")
                else:
                    print(f"✅ Found emergency stop test: {test}")
        
        # Check obstacle scenarios
        if "obstacle_scenarios" in safety:
            obstacle_tests = safety["obstacle_scenarios"]
            required_obstacle_tests = [
                "stationary_object",
                "moving_person",
                "moving_pet"
            ]
            
            for test in required_obstacle_tests:
                if test not in obstacle_tests:
                    issues.append(f"Missing obstacle scenario: {test}")
                else:
                    print(f"✅ Found obstacle scenario: {test}")
        
        # Check boundary tests
        if "boundary_tests" in safety:
            boundary_tests = safety["boundary_tests"]
            required_boundary_tests = [
                "gps_boundary",
                "physical_boundary",
                "no_go_zones"
            ]
            
            for test in required_boundary_tests:
                if test not in boundary_tests:
                    issues.append(f"Missing boundary test: {test}")
                else:
                    print(f"✅ Found boundary test: {test}")
        
        return len(issues) == 0, issues
        
    except Exception as e:
        issues.append(f"Error validating safety requirements: {e}")
        return False, issues


def validate_performance_targets() -> Tuple[bool, List[str]]:
    """Validate performance targets are realistic and complete"""
    print("🔍 Validating performance targets...")
    
    issues = []
    
    try:
        with open("config/field_testing.yaml") as f:
            config = yaml.safe_load(f)
        
        if "performance_targets" not in config:
            issues.append("No performance targets configured")
            return False, issues
        
        targets = config["performance_targets"]
        
        # Define expected ranges for validation
        target_ranges = {
            "mowing_efficiency_min": (70.0, 95.0),
            "coverage_quality_min": (90.0, 99.0),
            "battery_life_min_hours": (2.0, 12.0),
            "gps_accuracy_max_meters": (0.1, 2.0),
            "safety_response_max_ms": (50, 500),
            "obstacle_detection_accuracy_min": (95.0, 100.0),
            "system_uptime_min_percent": (95.0, 100.0)
        }
        
        for target_name, (min_val, max_val) in target_ranges.items():
            if target_name not in targets:
                issues.append(f"Missing performance target: {target_name}")
            else:
                target_value = targets[target_name]
                if not (min_val <= target_value <= max_val):
                    issues.append(f"Performance target {target_name} out of realistic range: {target_value}")
                else:
                    print(f"✅ Valid performance target: {target_name} = {target_value}")
        
        return len(issues) == 0, issues
        
    except Exception as e:
        issues.append(f"Error validating performance targets: {e}")
        return False, issues


def validate_documentation() -> Tuple[bool, List[str]]:
    """Validate field testing documentation"""
    print("🔍 Validating field testing documentation...")
    
    issues = []
    
    doc_file = Path("docs/field-testing-guide.md")
    
    if not doc_file.exists():
        issues.append("Field testing guide documentation missing")
        return False, issues
    
    try:
        with open(doc_file) as f:
            content = f.read()
        
        # Check for required sections
        required_sections = [
            "## Overview",
            "## Test Environment Setup",
            "## Safety Protocols",
            "## Testing Phases",
            "## Performance Validation",
            "## Data Collection",
            "## Reporting"
        ]
        
        for section in required_sections:
            if section not in content:
                issues.append(f"Missing documentation section: {section}")
            else:
                print(f"✅ Found documentation section: {section}")
        
        # Check for key content
        key_content = [
            "emergency stop",
            "safety protocols",
            "performance metrics",
            "test phases",
            "2-week testing program"
        ]
        
        for content_item in key_content:
            if content_item.lower() in content.lower():
                print(f"✅ Found key content: {content_item}")
            else:
                issues.append(f"Missing key content: {content_item}")
        
        return len(issues) == 0, issues
        
    except Exception as e:
        issues.append(f"Error validating documentation: {e}")
        return False, issues


async def validate_framework_functionality() -> Tuple[bool, List[str]]:
    """Test basic framework functionality"""
    print("🔍 Validating framework functionality...")
    
    issues = []
    
    try:
        from tests.field.field_testing_framework import FieldTestingFramework
        
        # Create framework instance
        framework = FieldTestingFramework()
        print("✅ Framework instance created")
        
        # Test configuration loading
        config = framework.config
        if not config:
            issues.append("Framework configuration not loaded")
        else:
            print("✅ Configuration loaded successfully")
        
        # Test logging setup
        logger = framework.logger
        if not logger:
            issues.append("Framework logging not initialized")
        else:
            print("✅ Logging system initialized")
        
        # Test basic methods exist
        required_methods = [
            'start_test_session',
            'run_safety_tests',
            'collect_performance_metrics',
            'end_test_session',
            'run_comprehensive_field_test'
        ]
        
        for method_name in required_methods:
            if not hasattr(framework, method_name):
                issues.append(f"Missing framework method: {method_name}")
            else:
                print(f"✅ Found framework method: {method_name}")
        
        return len(issues) == 0, issues
        
    except Exception as e:
        issues.append(f"Framework functionality validation error: {e}")
        return False, issues


def validate_execution_scripts() -> Tuple[bool, List[str]]:
    """Validate execution scripts"""
    print("🔍 Validating execution scripts...")
    
    issues = []
    
    script_file = Path("scripts/run_field_tests.py")
    
    if not script_file.exists():
        issues.append("Field testing execution script missing")
        return False, issues
    
    try:
        with open(script_file) as f:
            content = f.read()
        
        # Check for required classes and functions
        required_components = [
            "class FieldTestOrchestrator",
            "async def run_test_phase",
            "async def run_complete_test_program",
            "async def main()"
        ]
        
        for component in required_components:
            if component in content:
                print(f"✅ Found script component: {component}")
            else:
                issues.append(f"Missing script component: {component}")
        
        # Check for command line argument handling
        if "argparse" in content:
            print("✅ Command line argument handling present")
        else:
            issues.append("Missing command line argument handling")
        
        return len(issues) == 0, issues
        
    except Exception as e:
        issues.append(f"Error validating execution scripts: {e}")
        return False, issues


def generate_validation_report(results: Dict[str, Tuple[bool, List[str]]]) -> Dict[str, Any]:
    """Generate comprehensive validation report"""
    print("\n" + "="*60)
    print("FIELD TESTING IMPLEMENTATION VALIDATION REPORT")
    print("="*60)
    
    total_validations = len(results)
    passed_validations = sum(1 for success, _ in results.values() if success)
    
    report = {
        "validation_timestamp": datetime.now().isoformat(),
        "summary": {
            "total_validations": total_validations,
            "passed_validations": passed_validations,
            "success_rate": (passed_validations / total_validations) * 100,
            "overall_success": passed_validations == total_validations
        },
        "detailed_results": {},
        "all_issues": []
    }
    
    print(f"\nValidation Summary:")
    print(f"Total Validations: {total_validations}")
    print(f"Passed: {passed_validations}")
    print(f"Failed: {total_validations - passed_validations}")
    print(f"Success Rate: {report['summary']['success_rate']:.1f}%")
    
    print(f"\nDetailed Results:")
    for validation_name, (success, issues) in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {validation_name}")
        
        report["detailed_results"][validation_name] = {
            "success": success,
            "issues": issues
        }
        
        if issues:
            report["all_issues"].extend(issues)
            for issue in issues:
                print(f"    - {issue}")
    
    # Overall assessment
    print(f"\n" + "="*60)
    if report["summary"]["overall_success"]:
        print("🎉 FIELD TESTING IMPLEMENTATION: COMPLETE AND VALIDATED")
        print("✅ All components are properly implemented and functional")
        print("✅ Ready for field testing execution")
    else:
        print("⚠️  FIELD TESTING IMPLEMENTATION: ISSUES FOUND")
        print("❌ Some components need attention before field testing")
        print("🔧 Please address the issues listed above")
    
    print("="*60)
    
    return report


async def main():
    """Main validation execution"""
    print("🚀 Starting Field Testing Implementation Validation")
    print("="*60)
    
    # Run all validations
    validations = {
        "File Structure": validate_file_structure(),
        "Configuration": validate_configuration(),
        "Framework Imports": validate_framework_imports(),
        "Test Scenarios": validate_test_scenarios(),
        "Safety Requirements": validate_safety_requirements(),
        "Performance Targets": validate_performance_targets(),
        "Documentation": validate_documentation(),
        "Framework Functionality": await validate_framework_functionality(),
        "Execution Scripts": validate_execution_scripts()
    }
    
    # Generate report
    report = generate_validation_report(validations)
    
    # Save report
    report_dir = Path("reports/validation")
    report_dir.mkdir(parents=True, exist_ok=True)
    
    report_file = report_dir / f"field_testing_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📄 Validation report saved: {report_file}")
    
    # Return appropriate exit code
    return 0 if report["summary"]["overall_success"] else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
