#!/usr/bin/env python3
"""
Coral TPU Test Framework Runner
Demonstrates running the complete test framework with different configurations
"""

import subprocess
import sys
import os
import argparse
import json
from pathlib import Path
from typing import List, Dict, Any

def run_command(cmd: List[str], capture_output: bool = True) -> Dict[str, Any]:
    """Run command and return result"""
    try:
        result = subprocess.run(
            cmd, 
            capture_output=capture_output, 
            text=True,
            cwd=Path(__file__).parent.parent.parent
        )
        return {
            'success': result.returncode == 0,
            'returncode': result.returncode,
            'stdout': result.stdout if capture_output else '',
            'stderr': result.stderr if capture_output else '',
            'command': ' '.join(cmd)
        }
    except Exception as e:
        return {
            'success': False,
            'returncode': -1,
            'stdout': '',
            'stderr': str(e),
            'command': ' '.join(cmd)
        }

def run_installation_tests() -> Dict[str, Any]:
    """Run Coral installation tests"""
    print("🔧 Running Coral Installation Tests...")
    
    cmd = [
        'python', '-m', 'pytest', 
        'tests/coral/test_coral_installation_framework.py',
        '-v', '--tb=short',
        '-m', 'not real_hardware'
    ]
    
    result = run_command(cmd, capture_output=False)
    return result

def run_performance_benchmarks() -> Dict[str, Any]:
    """Run performance benchmarks"""
    print("📊 Running Performance Benchmarks...")
    
    cmd = [
        'python', '-m', 'pytest',
        'tests/coral/test_coral_performance_benchmarks.py',
        '-v', '--tb=short',
        '-m', 'performance and not real_hardware'
    ]
    
    result = run_command(cmd, capture_output=False)
    return result

def run_ci_automation_demo() -> Dict[str, Any]:
    """Demonstrate CI automation"""
    print("🤖 Running CI Automation Demo...")
    
    cmd = ['python', 'tests/coral/test_coral_ci_automation.py']
    result = run_command(cmd, capture_output=False)
    return result

def run_comprehensive_matrix() -> Dict[str, Any]:
    """Run comprehensive test matrix"""
    print("🧪 Running Comprehensive Test Matrix...")
    
    cmd = [
        'python', 'tests/coral/test_coral_ci_automation.py', 
        '--comprehensive-matrix'
    ]
    
    result = run_command(cmd)
    
    if result['success'] and result['stdout']:
        try:
            matrix_results = json.loads(result['stdout'])
            print(f"✅ Matrix Results: {matrix_results['successful_scenarios']}/{matrix_results['total_scenarios']} scenarios passed")
        except:
            pass
    
    return result

def run_hardware_specific_tests() -> Dict[str, Any]:
    """Run hardware-specific tests (only if hardware detected)"""
    print("🔌 Checking for Coral hardware...")
    
    # Check if hardware is present
    hardware_check = run_command(['lsusb'])
    has_coral = hardware_check['success'] and '18d1:9302' in hardware_check['stdout']
    
    if has_coral:
        print("✅ Coral hardware detected - running hardware-specific tests")
        cmd = [
            'python', '-m', 'pytest',
            'tests/coral/',
            '-v', '--tb=short',
            '-m', 'real_hardware'
        ]
        result = run_command(cmd, capture_output=False)
    else:
        print("ℹ️  No Coral hardware detected - skipping hardware-specific tests")
        result = {
            'success': True,
            'returncode': 0,
            'stdout': 'Skipped - no hardware',
            'stderr': '',
            'command': 'hardware check'
        }
    
    return result

def generate_github_actions_config():
    """Generate GitHub Actions configuration"""
    print("⚙️  Generating GitHub Actions configuration...")
    
    cmd = [
        'python', 'tests/coral/test_coral_ci_automation.py',
        '--generate-github-actions'
    ]
    
    result = run_command(cmd)
    
    if result['success']:
        config_path = Path('.github/workflows/coral-tests.yml')
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(result['stdout'])
        print(f"✅ GitHub Actions config saved to: {config_path}")
    else:
        print(f"❌ Failed to generate config: {result['stderr']}")
    
    return result

def main():
    """Main test runner"""
    parser = argparse.ArgumentParser(description='Coral TPU Test Framework Runner')
    parser.add_argument('--installation', action='store_true', 
                       help='Run installation tests')
    parser.add_argument('--performance', action='store_true',
                       help='Run performance benchmarks')
    parser.add_argument('--ci-demo', action='store_true',
                       help='Run CI automation demo')
    parser.add_argument('--matrix', action='store_true',
                       help='Run comprehensive test matrix')
    parser.add_argument('--hardware', action='store_true',
                       help='Run hardware-specific tests')
    parser.add_argument('--generate-ci', action='store_true',
                       help='Generate CI configuration files')
    parser.add_argument('--all', action='store_true',
                       help='Run all tests and demos')
    
    args = parser.parse_args()
    
    if not any(vars(args).values()):
        args.all = True  # Default to running everything
    
    print("🚀 Coral TPU Test Framework Runner")
    print("=" * 50)
    
    results = {}
    
    try:
        if args.all or args.installation:
            results['installation'] = run_installation_tests()
            print()
        
        if args.all or args.performance:
            results['performance'] = run_performance_benchmarks()
            print()
        
        if args.all or args.ci_demo:
            results['ci_demo'] = run_ci_automation_demo()
            print()
        
        if args.all or args.matrix:
            results['matrix'] = run_comprehensive_matrix()
            print()
        
        if args.all or args.hardware:
            results['hardware'] = run_hardware_specific_tests()
            print()
        
        if args.all or args.generate_ci:
            results['generate_ci'] = generate_github_actions_config()
            print()
        
        # Summary
        print("=" * 50)
        print("📋 CORAL TEST FRAMEWORK SUMMARY")
        print("=" * 50)
        
        total_tests = 0
        passed_tests = 0
        
        for test_name, result in results.items():
            if result['success']:
                status = "✅ PASSED"
                passed_tests += 1
            else:
                status = "❌ FAILED"
            total_tests += 1
            
            print(f"{status}: {test_name}")
            if not result['success'] and result.get('stderr'):
                print(f"    Error: {result['stderr'][:100]}...")
        
        print("=" * 50)
        print(f"Overall: {passed_tests}/{total_tests} test categories passed")
        
        if passed_tests == total_tests:
            print("🎉 All Coral test framework components working correctly!")
            return 0
        else:
            print("⚠️  Some test categories failed - check output above")
            return 1
            
    except KeyboardInterrupt:
        print("\n⏹️  Test run interrupted by user")
        return 130
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
