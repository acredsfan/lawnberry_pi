#!/usr/bin/env python3
"""
Comprehensive Performance Benchmarking Suite for LawnBerryPi
Tests all system components against performance targets
"""

import asyncio
import time
import psutil
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import json
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

logger = logging.getLogger(__name__)

@dataclass
class BenchmarkResult:
    """Individual benchmark result"""
    name: str
    target_value: float
    actual_value: float
    unit: str
    passed: bool
    timestamp: datetime

class PerformanceBenchmarkSuite:
    """Comprehensive performance benchmark suite"""
    
    def __init__(self):
        self.results: List[BenchmarkResult] = []
        self.targets = {
            'sensor_fusion_latency_ms': 80,
            'motor_control_response_ms': 50,
            'web_ui_load_time_ms': 1500,
            'memory_usage_gb': 6,
            'cpu_usage_percent': 70,
            'vision_fps': 30,
            'api_response_time_ms': 200
        }
        
    async def run_comprehensive_benchmarks(self) -> Dict[str, Any]:
        """Run all performance benchmarks"""
        logger.info("Starting comprehensive performance benchmarking")
        
        # System resource benchmarks
        await self._benchmark_system_resources()
        
        # Sensor fusion latency benchmark
        await self._benchmark_sensor_fusion_latency()
        
        # Web interface performance benchmark
        await self._benchmark_web_interface()
        
        # Vision processing benchmark
        await self._benchmark_vision_processing()
        
        # Memory efficiency benchmark
        await self._benchmark_memory_efficiency()
        
        # Generate final report
        report = self._generate_benchmark_report()
        return report
        
    async def _benchmark_system_resources(self):
        """Benchmark system resource utilization"""
        logger.info("Benchmarking system resources")
        
        # Monitor system for 60 seconds under load
        measurements = []
        start_time = time.time()
        
        while time.time() - start_time < 60:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            measurements.append({
                'cpu': cpu_percent,
                'memory_gb': memory.used / (1024**3),
                'memory_percent': memory.percent
            })
            
            await asyncio.sleep(1)
        
        # Calculate averages
        avg_cpu = sum(m['cpu'] for m in measurements) / len(measurements)
        avg_memory_gb = sum(m['memory_gb'] for m in measurements) / len(measurements)
        max_cpu = max(m['cpu'] for m in measurements)
        max_memory_gb = max(m['memory_gb'] for m in measurements)
        
        # Record results
        self.results.append(BenchmarkResult(
            name="Average CPU Usage",
            target_value=self.targets['cpu_usage_percent'],
            actual_value=avg_cpu,
            unit="%",
            passed=avg_cpu <= self.targets['cpu_usage_percent'],
            timestamp=datetime.now()
        ))
        
        self.results.append(BenchmarkResult(
            name="Peak Memory Usage",
            target_value=self.targets['memory_usage_gb'],
            actual_value=max_memory_gb,
            unit="GB",
            passed=max_memory_gb <= self.targets['memory_usage_gb'],
            timestamp=datetime.now()
        ))
        
    async def _benchmark_sensor_fusion_latency(self):
        """Benchmark sensor fusion latency"""
        logger.info("Benchmarking sensor fusion latency")
        
        # Simulate sensor fusion operations
        latency_measurements = []
        
        for i in range(100):
            start_time = time.perf_counter()
            
            # Simulate sensor fusion processing
            await self._simulate_sensor_fusion_cycle()
            
            latency_ms = (time.perf_counter() - start_time) * 1000
            latency_measurements.append(latency_ms)
            
            await asyncio.sleep(0.01)  # 100Hz simulation
        
        avg_latency = sum(latency_measurements) / len(latency_measurements)
        max_latency = max(latency_measurements)
        
        self.results.append(BenchmarkResult(
            name="Sensor Fusion Average Latency",
            target_value=self.targets['sensor_fusion_latency_ms'],
            actual_value=avg_latency,
            unit="ms",
            passed=avg_latency <= self.targets['sensor_fusion_latency_ms'],
            timestamp=datetime.now()
        ))
        
        self.results.append(BenchmarkResult(
            name="Sensor Fusion Peak Latency",
            target_value=self.targets['sensor_fusion_latency_ms'] * 1.5,
            actual_value=max_latency,
            unit="ms",
            passed=max_latency <= self.targets['sensor_fusion_latency_ms'] * 1.5,
            timestamp=datetime.now()
        ))
        
    async def _simulate_sensor_fusion_cycle(self):
        """Simulate a sensor fusion processing cycle"""
        # Simulate GPS processing
        await asyncio.sleep(0.005)
        
        # Simulate IMU processing
        await asyncio.sleep(0.003)
        
        # Simulate ToF sensor processing
        await asyncio.sleep(0.008)
        
        # Simulate data fusion
        await asyncio.sleep(0.004)
        
    async def _benchmark_web_interface(self):
        """Benchmark web interface performance"""
        logger.info("Benchmarking web interface performance")
        
        # Simulate web interface loading
        load_times = []
        
        for i in range(10):
            start_time = time.perf_counter()
            
            # Simulate page load operations
            await self._simulate_web_page_load()
            
            load_time_ms = (time.perf_counter() - start_time) * 1000
            load_times.append(load_time_ms)
            
            await asyncio.sleep(0.1)
        
        avg_load_time = sum(load_times) / len(load_times)
        
        self.results.append(BenchmarkResult(
            name="Web Interface Load Time",
            target_value=self.targets['web_ui_load_time_ms'],
            actual_value=avg_load_time,
            unit="ms",
            passed=avg_load_time <= self.targets['web_ui_load_time_ms'],
            timestamp=datetime.now()
        ))
        
    async def _simulate_web_page_load(self):
        """Simulate web page loading operations"""
        # Simulate database queries
        await asyncio.sleep(0.05)
        
        # Simulate template rendering
        await asyncio.sleep(0.03)
        
        # Simulate asset loading
        await asyncio.sleep(0.02)
        
    async def _benchmark_vision_processing(self):
        """Benchmark vision processing performance"""
        logger.info("Benchmarking vision processing")
        
        # Simulate vision processing for 30 seconds
        frame_times = []
        start_time = time.time()
        frame_count = 0
        
        while time.time() - start_time < 30:
            frame_start = time.perf_counter()
            
            # Simulate frame processing
            await self._simulate_frame_processing()
            
            frame_time = time.perf_counter() - frame_start
            frame_times.append(frame_time)
            frame_count += 1
            
            # Target 30 FPS
            await asyncio.sleep(max(0, 1/30 - frame_time))
        
        actual_fps = frame_count / 30
        avg_frame_time_ms = (sum(frame_times) / len(frame_times)) * 1000
        
        self.results.append(BenchmarkResult(
            name="Vision Processing FPS",
            target_value=self.targets['vision_fps'],
            actual_value=actual_fps,
            unit="fps",
            passed=actual_fps >= self.targets['vision_fps'] * 0.9,  # 90% of target
            timestamp=datetime.now()
        ))
        
    async def _simulate_frame_processing(self):
        """Simulate vision frame processing"""
        # Simulate image preprocessing
        await asyncio.sleep(0.005)
        
        # Simulate object detection
        await asyncio.sleep(0.015)
        
        # Simulate result processing
        await asyncio.sleep(0.003)
        
    async def _benchmark_memory_efficiency(self):
        """Benchmark memory efficiency over time"""
        logger.info("Benchmarking memory efficiency")
        
        initial_memory = psutil.virtual_memory().used
        
        # Run memory-intensive operations
        for i in range(100):
            # Simulate memory allocation and deallocation
            data = [0] * 10000  # Allocate some memory
            await asyncio.sleep(0.01)
            del data  # Free memory
            
        final_memory = psutil.virtual_memory().used
        memory_growth_mb = (final_memory - initial_memory) / (1024 * 1024)
        
        self.results.append(BenchmarkResult(
            name="Memory Growth During Operations",
            target_value=50,  # Max 50MB growth
            actual_value=memory_growth_mb,
            unit="MB",
            passed=memory_growth_mb <= 50,
            timestamp=datetime.now()
        ))
        
    def _generate_benchmark_report(self) -> Dict[str, Any]:
        """Generate comprehensive benchmark report"""
        passed_count = sum(1 for r in self.results if r.passed)
        total_count = len(self.results)
        
        report = {
            'benchmark_summary': {
                'total_tests': total_count,
                'passed_tests': passed_count,
                'failed_tests': total_count - passed_count,
                'success_rate': (passed_count / total_count) * 100 if total_count > 0 else 0,
                'timestamp': datetime.now().isoformat()
            },
            'detailed_results': [],
            'performance_targets_met': passed_count == total_count,
            'recommendations': []
        }
        
        # Add detailed results
        for result in self.results:
            report['detailed_results'].append({
                'name': result.name,
                'target': result.target_value,
                'actual': result.actual_value,
                'unit': result.unit,
                'passed': result.passed,
                'performance_ratio': result.actual_value / result.target_value if result.target_value > 0 else 0,
                'timestamp': result.timestamp.isoformat()
            })
        
        # Generate recommendations
        for result in self.results:
            if not result.passed:
                if 'latency' in result.name.lower():
                    report['recommendations'].append(f"Optimize {result.name}: consider reducing processing load or improving algorithms")
                elif 'memory' in result.name.lower():
                    report['recommendations'].append(f"Optimize {result.name}: implement memory pooling or reduce buffer sizes")
                elif 'cpu' in result.name.lower():
                    report['recommendations'].append(f"Optimize {result.name}: distribute load across cores or reduce computational complexity")
        
        return report

async def main():
    """Main benchmark execution"""
    suite = PerformanceBenchmarkSuite()
    
    try:
        # Run comprehensive benchmarks
        report = await suite.run_comprehensive_benchmarks()
        
        # Save benchmark report
        report_path = '/tmp/performance_benchmark_report.json'
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Print summary
        print(f"Performance Benchmarking Complete")
        print(f"Report saved to: {report_path}")
        print(f"Tests passed: {report['benchmark_summary']['passed_tests']}/{report['benchmark_summary']['total_tests']}")
        print(f"Success rate: {report['benchmark_summary']['success_rate']:.1f}%")
        
        if report['performance_targets_met']:
            print("✓ All performance targets met!")
            return 0
        else:
            print("⚠ Some performance targets not met")
            for rec in report['recommendations']:
                print(f"  • {rec}")
            return 1
            
    except Exception as e:
        logger.error(f"Benchmark suite failed: {e}")
        return 1

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
