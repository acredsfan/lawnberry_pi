"""
Performance Testing Framework
Benchmarks system performance, response times, and resource usage
"""

import pytest
import asyncio
import time
import psutil
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from unittest.mock import Mock, AsyncMock, patch
import numpy as np

from src.sensor_fusion.fusion_engine import SensorFusionEngine
from src.safety.safety_service import SafetyService
from src.vision.vision_manager import VisionManager


@dataclass
class PerformanceMetrics:
    """Performance measurement results"""
    test_name: str
    duration_s: float
    avg_cpu_percent: float
    peak_cpu_percent: float
    avg_memory_mb: float
    peak_memory_mb: float
    operations_per_second: float
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    error_rate_percent: float


class PerformanceMonitor:
    """Real-time performance monitoring during tests"""
    
    def __init__(self, sample_interval_s: float = 0.1):
        self.sample_interval = sample_interval_s
        self.monitoring = False
        self.metrics = {
            "cpu_samples": [],
            "memory_samples": [],
            "timestamps": []
        }
        self._monitor_thread = None
    
    def start(self):
        """Start performance monitoring"""
        self.monitoring = True
        self.metrics = {"cpu_samples": [], "memory_samples": [], "timestamps": []}
        self._monitor_thread = threading.Thread(target=self._monitor_loop)
        self._monitor_thread.start()
    
    def stop(self) -> Dict[str, Any]:
        """Stop monitoring and return metrics"""
        self.monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join()
        
        if not self.metrics["cpu_samples"]:
            return {}
        
        return {
            "avg_cpu_percent": np.mean(self.metrics["cpu_samples"]),
            "peak_cpu_percent": np.max(self.metrics["cpu_samples"]),
            "avg_memory_mb": np.mean(self.metrics["memory_samples"]),
            "peak_memory_mb": np.max(self.metrics["memory_samples"]),
            "duration_s": self.metrics["timestamps"][-1] - self.metrics["timestamps"][0]
        }
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        start_time = time.time()
        
        while self.monitoring:
            try:
                cpu_percent = psutil.cpu_percent()
                memory_mb = psutil.virtual_memory().used / 1024 / 1024
                timestamp = time.time() - start_time
                
                self.metrics["cpu_samples"].append(cpu_percent)
                self.metrics["memory_samples"].append(memory_mb)
                self.metrics["timestamps"].append(timestamp)
                
                time.sleep(self.sample_interval)
                
            except Exception as e:
                print(f"Performance monitoring error: {e}")


@pytest.mark.performance
class TestSensorFusionPerformance:
    """Test sensor fusion engine performance"""
    
    @pytest.fixture
    async def fusion_engine(self, mqtt_client, test_config):
        """Create sensor fusion engine for performance testing"""
        config = test_config["sensor_fusion"].copy()
        config["update_rate_hz"] = 20  # Standard rate
        
        engine = SensorFusionEngine(mqtt_client, config)
        yield engine
        
        if hasattr(engine, '_running') and engine._running:
            await engine.stop()
    
    @pytest.mark.asyncio
    async def test_sensor_data_throughput(self, fusion_engine, performance_monitor):
        """Test sensor data processing throughput"""
        latencies = []
        
        # Mock sensor data generator
        async def generate_sensor_data():
            """Generate mock sensor data at high rate"""
            data_count = 0
            start_time = time.time()
            
            while time.time() - start_time < 30:  # 30 second test
                # Generate IMU data
                imu_data = {
                    "acceleration": {"x": 0.1, "y": 0.2, "z": 9.8},
                    "gyroscope": {"x": 0.01, "y": -0.02, "z": 0.005},
                    "orientation": {"roll": 2.0, "pitch": 1.5, "yaw": 180.0},
                    "timestamp": datetime.now()
                }
                
                # Measure processing latency
                process_start = time.time()
                await fusion_engine.process_imu_data(imu_data)
                latency_ms = (time.time() - process_start) * 1000
                latencies.append(latency_ms)
                
                data_count += 1
                await asyncio.sleep(1/50)  # 50Hz data rate
            
            return data_count
        
        # Start monitoring and fusion engine
        performance_monitor.start()
        await fusion_engine.start()
        
        try:
            # Run throughput test
            operations = await generate_sensor_data()
            
        finally:
            await fusion_engine.stop()
            perf_metrics = performance_monitor.stop()
        
        # Calculate performance metrics
        avg_latency = np.mean(latencies) if latencies else 0
        p95_latency = np.percentile(latencies, 95) if latencies else 0
        p99_latency = np.percentile(latencies, 99) if latencies else 0
        
        ops_per_second = operations / perf_metrics.get("duration_s", 1)
        
        # Performance assertions
        assert ops_per_second >= 20, f"Throughput too low: {ops_per_second} ops/s"
        assert avg_latency < 10, f"Average latency too high: {avg_latency}ms"
        assert p95_latency < 20, f"P95 latency too high: {p95_latency}ms"
        assert perf_metrics.get("peak_cpu_percent", 0) < 80, "CPU usage too high"
        
        print(f"Sensor fusion throughput: {ops_per_second:.1f} ops/s, "
              f"avg latency: {avg_latency:.1f}ms")


@pytest.mark.performance
class TestSafetySystemPerformance:
    """Test safety system response performance"""
    
    @pytest.fixture
    async def safety_service(self, mqtt_client, test_config):
        """Create safety service for performance testing"""
        from src.safety.safety_service import SafetyConfig
        
        config = SafetyConfig(**test_config["safety"])
        service = SafetyService(mqtt_client, config)
        
        # Mock hardware interface
        service._hardware_interface = Mock()
        service._hardware_interface.emergency_stop = AsyncMock()
        service._hardware_interface.resume_operation = AsyncMock()
        
        yield service
        
        if service._running:
            await service.stop()
    
    @pytest.mark.asyncio
    async def test_emergency_stop_response_time(self, safety_service, performance_monitor):
        """Test emergency stop response time under load"""
        await safety_service.start()
        
        response_times = []
        
        # Test multiple emergency stops
        for i in range(100):
            start_time = time.time()
            
            success = await safety_service.trigger_emergency_stop(
                f"Performance test {i}", "benchmark"
            )
            
            response_time = (time.time() - start_time) * 1000
            response_times.append(response_time)
            
            assert success, f"Emergency stop {i} failed"
            
            # Reset for next test
            await safety_service._reset_emergency_state()
            await asyncio.sleep(0.01)
        
        # Analyze response times
        avg_response = np.mean(response_times)
        p95_response = np.percentile(response_times, 95)
        p99_response = np.percentile(response_times, 99)
        max_response = np.max(response_times)
        
        # Critical safety assertions
        assert avg_response < 50, f"Average emergency response too slow: {avg_response}ms"
        assert p95_response < 100, f"P95 emergency response too slow: {p95_response}ms"
        assert p99_response < 100, f"P99 emergency response too slow: {p99_response}ms"
        assert max_response < 100, f"Max emergency response too slow: {max_response}ms"
        
        print(f"Emergency stop performance - Avg: {avg_response:.1f}ms, "
              f"P95: {p95_response:.1f}ms, P99: {p99_response:.1f}ms, "
              f"Max: {max_response:.1f}ms")


@pytest.mark.performance  
class TestVisionProcessingPerformance:
    """Test computer vision processing performance"""
    
    @pytest.fixture
    async def vision_manager(self, mqtt_client, test_config, mock_camera):
        """Create vision manager for performance testing"""
        with patch('cv2.VideoCapture', return_value=mock_camera):
            manager = VisionManager(mqtt_client, test_config["vision"])
            await manager.initialize()
            yield manager
            await manager.shutdown()
    
    @pytest.mark.asyncio
    async def test_frame_processing_rate(self, vision_manager, performance_monitor):
        """Test video frame processing rate and latency"""
        processing_times = []
        
        # Create test frames
        import cv2
        test_frames = []
        for i in range(100):
            # Create synthetic frame with objects
            frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
            # Add some structure to simulate real scene
            cv2.rectangle(frame, (100, 100), (200, 200), (255, 0, 0), -1)
            cv2.circle(frame, (400, 300), 50, (0, 255, 0), -1)
            test_frames.append(frame)
        
        performance_monitor.start()
        
        try:
            # Process frames and measure performance
            for frame in test_frames:
                start_time = time.time()
                
                # Process frame through vision pipeline
                detections = await vision_manager.process_frame(frame)
                
                processing_time = (time.time() - start_time) * 1000
                processing_times.append(processing_time)
                
        finally:
            perf_metrics = performance_monitor.stop()
        
        # Analyze processing performance
        avg_processing_time = np.mean(processing_times)
        p95_processing_time = np.percentile(processing_times, 95)
        frames_per_second = 1000 / avg_processing_time if avg_processing_time > 0 else 0
        
        # Performance assertions
        assert avg_processing_time < 100, f"Frame processing too slow: {avg_processing_time}ms"
        assert frames_per_second >= 10, f"Frame rate too low: {frames_per_second} FPS"
        assert p95_processing_time < 200, f"P95 processing time too high: {p95_processing_time}ms"
        
        print(f"Vision processing performance - Avg: {avg_processing_time:.1f}ms "
              f"({frames_per_second:.1f} FPS), P95: {p95_processing_time:.1f}ms")


@pytest.mark.performance
class TestMemoryLeakDetection:
    """Test for memory leaks during long-running operations"""
    
    @pytest.mark.asyncio
    async def test_long_running_sensor_fusion(self, mqtt_client, test_config):
        """Test sensor fusion for memory leaks during extended operation"""
        engine = SensorFusionEngine(mqtt_client, test_config["sensor_fusion"])
        
        # Track memory usage over time
        memory_samples = []
        
        await engine.start()
        
        try:
            # Run for 5 minutes with continuous data
            start_time = time.time()
            iteration = 0
            
            while time.time() - start_time < 300:  # 5 minutes
                # Generate sensor data
                imu_data = {
                    "acceleration": {"x": 0.1, "y": 0.2, "z": 9.8},
                    "gyroscope": {"x": 0.01, "y": -0.02, "z": 0.005},
                    "orientation": {"roll": 2.0, "pitch": 1.5, "yaw": 180.0},
                    "timestamp": datetime.now()
                }
                
                await engine.process_imu_data(imu_data)
                
                # Sample memory every 10 seconds
                if iteration % 200 == 0:  # Every 200 iterations (10s at 20Hz)
                    memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
                    memory_samples.append(memory_mb)
                    print(f"Memory usage after {time.time() - start_time:.0f}s: {memory_mb:.1f}MB")
                
                iteration += 1
                await asyncio.sleep(1/20)  # 20Hz
                
        finally:
            await engine.stop()
        
        if len(memory_samples) > 5:
            # Check for memory growth trend
            memory_growth = memory_samples[-1] - memory_samples[0]
            memory_growth_rate = memory_growth / len(memory_samples)
            
            print(f"Memory growth over test: {memory_growth:.1f}MB "
                  f"({memory_growth_rate:.2f}MB per sample)")
            
            # Memory leak assertions
            assert memory_growth < 50, f"Excessive memory growth: {memory_growth}MB"
            assert memory_growth_rate < 2, f"High memory growth rate: {memory_growth_rate}MB/sample"
        
        else:
            pytest.skip("Insufficient memory samples collected")


# Performance test utilities
def benchmark_function(func, *args, iterations=100, **kwargs):
    """Benchmark a function's performance"""
    times = []
    
    for _ in range(iterations):
        start_time = time.time()
        if asyncio.iscoroutinefunction(func):
            asyncio.run(func(*args, **kwargs))
        else:
            func(*args, **kwargs)
        
        times.append((time.time() - start_time) * 1000)
    
    return {
        "avg_ms": np.mean(times),
        "min_ms": np.min(times),
        "max_ms": np.max(times),
        "p95_ms": np.percentile(times, 95),
        "p99_ms": np.percentile(times, 99),
        "std_ms": np.std(times)
    }


def generate_performance_report(metrics_list: List[PerformanceMetrics]) -> str:
    """Generate performance test report"""
    report = "# Performance Test Report\n\n"
    report += f"Generated: {datetime.now().isoformat()}\n\n"
    
    for metrics in metrics_list:
        report += f"## {metrics.test_name}\n"
        report += f"- Duration: {metrics.duration_s:.1f}s\n"
        report += f"- Operations/sec: {metrics.operations_per_second:.1f}\n"
        report += f"- Avg Latency: {metrics.avg_latency_ms:.1f}ms\n"
        report += f"- P95 Latency: {metrics.p95_latency_ms:.1f}ms\n"
        report += f"- CPU Usage: {metrics.avg_cpu_percent:.1f}% avg, {metrics.peak_cpu_percent:.1f}% peak\n"
        report += f"- Memory Usage: {metrics.avg_memory_mb:.1f}MB avg, {metrics.peak_memory_mb:.1f}MB peak\n"
        report += f"- Error Rate: {metrics.error_rate_percent:.2f}%\n\n"
    
    return report
