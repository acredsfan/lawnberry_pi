#!/usr/bin/env python3
"""
Comprehensive Performance Optimization Script for LawnBerryPi
Implements optimizations for Raspberry Pi 4B and 5 with Bookworm OS
"""

import asyncio
import gc
import json
import logging
import multiprocessing
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics data class"""

    timestamp: datetime
    cpu_usage: float
    memory_usage_mb: float
    memory_percent: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    network_bytes_sent: int
    network_bytes_recv: int
    temperature: float
    sensor_fusion_latency_ms: float = 0.0
    web_response_time_ms: float = 0.0
    vision_fps: float = 0.0


class PerformanceOptimizer:
    """Comprehensive performance optimization system"""

    def __init__(self):
        self.logger = logger
        self.optimization_applied = set()
        self.baseline_metrics = None
        self.cpu_count = multiprocessing.cpu_count()

        # Performance targets from config
        self.targets = {
            "sensor_fusion_latency_ms": 80,
            "motor_control_response_ms": 50,
            "web_ui_page_load_ms": 1500,
            "max_cpu_percent": 70,
            "max_memory_gb": 6,
            "vision_target_fps": 30,
        }

    async def initialize_optimizations(self):
        """Initialize and apply all performance optimizations"""
        self.logger.info("Starting comprehensive performance optimization")

        # Collect baseline metrics
        await self._collect_baseline_metrics()

        # Apply optimizations in order of importance
        await self._apply_memory_optimizations()
        await self._apply_cpu_optimizations()
        await self._apply_io_optimizations()
        await self._apply_python_optimizations()
        await self._apply_service_optimizations()
        await self._apply_vision_optimizations()
        await self._apply_network_optimizations()

        self.logger.info("Performance optimization initialization complete")

    async def _collect_baseline_metrics(self):
        """Collect baseline performance metrics"""
        self.logger.info("Collecting baseline performance metrics")

        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk_io = psutil.disk_io_counters()
        network_io = psutil.net_io_counters()

        # Get temperature if available
        temperature = 0.0
        try:
            if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    temperature = float(f.read().strip()) / 1000.0
        except:
            pass

        self.baseline_metrics = PerformanceMetrics(
            timestamp=datetime.now(),
            cpu_usage=cpu_percent,
            memory_usage_mb=memory.used / (1024 * 1024),
            memory_percent=memory.percent,
            disk_io_read_mb=(disk_io.read_bytes if disk_io else 0) / (1024 * 1024),
            disk_io_write_mb=(disk_io.write_bytes if disk_io else 0) / (1024 * 1024),
            network_bytes_sent=network_io.bytes_sent if network_io else 0,
            network_bytes_recv=network_io.bytes_recv if network_io else 0,
            temperature=temperature,
        )

        self.logger.info(
            f"Baseline CPU: {cpu_percent:.1f}%, Memory: {memory.percent:.1f}%, Temp: {temperature:.1f}°C"
        )

    async def _apply_memory_optimizations(self):
        """Apply comprehensive memory optimizations"""
        self.logger.info("Applying memory optimizations")

        try:
            # Optimize Python garbage collection
            gc.set_threshold(700, 10, 10)  # More aggressive GC
            gc.collect()  # Force initial collection

            # Configure memory allocation strategy
            os.environ["PYTHONMALLOC"] = "pymalloc"

            # Apply kernel memory optimizations
            sysctl_optimizations = {
                "vm.swappiness": "10",
                "vm.dirty_ratio": "5",
                "vm.dirty_background_ratio": "2",
                "vm.vfs_cache_pressure": "50",
                "vm.overcommit_memory": "1",
                "vm.min_free_kbytes": "65536",
            }

            for param, value in sysctl_optimizations.items():
                try:
                    subprocess.run(
                        ["sudo", "sysctl", f"{param}={value}"], check=True, capture_output=True
                    )
                    self.logger.info(f"Applied: {param}={value}")
                except subprocess.CalledProcessError as e:
                    self.logger.warning(f"Failed to apply {param}: {e}")

            self.optimization_applied.add("memory_optimizations")

        except Exception as e:
            self.logger.error(f"Memory optimization failed: {e}")

    async def monitor_performance(self, duration_seconds: int = 300):
        """Monitor system performance for specified duration"""
        self.logger.info(f"Starting performance monitoring for {duration_seconds} seconds")

        metrics_history = []
        start_time = time.time()

        while time.time() - start_time < duration_seconds:
            current_metrics = await self._collect_current_metrics()
            metrics_history.append(current_metrics)

            # Log current performance
            self.logger.info(
                f"CPU: {current_metrics.cpu_usage:.1f}% | "
                f"Memory: {current_metrics.memory_percent:.1f}% | "
                f"Temp: {current_metrics.temperature:.1f}°C"
            )

            await asyncio.sleep(5)

        # Generate performance report
        report = await self._generate_performance_report(metrics_history)
        return report

    async def _collect_current_metrics(self):
        """Collect current performance metrics"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk_io = psutil.disk_io_counters()
        network_io = psutil.net_io_counters()

        # Get temperature
        temperature = 0.0
        try:
            if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                    temperature = float(f.read().strip()) / 1000.0
        except:
            pass

        return PerformanceMetrics(
            timestamp=datetime.now(),
            cpu_usage=cpu_percent,
            memory_usage_mb=memory.used / (1024 * 1024),
            memory_percent=memory.percent,
            disk_io_read_mb=(disk_io.read_bytes if disk_io else 0) / (1024 * 1024),
            disk_io_write_mb=(disk_io.write_bytes if disk_io else 0) / (1024 * 1024),
            network_bytes_sent=network_io.bytes_sent if network_io else 0,
            network_bytes_recv=network_io.bytes_recv if network_io else 0,
            temperature=temperature,
        )

    async def _generate_performance_report(self, metrics_history):
        """Generate comprehensive performance report"""
        if not metrics_history:
            return {}

        # Calculate averages
        avg_cpu = sum(m.cpu_usage for m in metrics_history) / len(metrics_history)
        avg_memory_mb = sum(m.memory_usage_mb for m in metrics_history) / len(metrics_history)
        max_cpu = max(m.cpu_usage for m in metrics_history)
        max_memory_mb = max(m.memory_usage_mb for m in metrics_history)

        report = {
            "monitoring_duration_seconds": len(metrics_history) * 5,
            "sample_count": len(metrics_history),
            "averages": {
                "cpu_usage_percent": round(avg_cpu, 2),
                "memory_usage_mb": round(avg_memory_mb, 2),
            },
            "peaks": {
                "max_cpu_percent": round(max_cpu, 2),
                "max_memory_mb": round(max_memory_mb, 2),
            },
            "performance_targets_met": {
                "cpu_usage": max_cpu <= self.targets["max_cpu_percent"],
                "memory_usage": max_memory_mb <= self.targets["max_memory_gb"] * 1024,
            },
            "optimizations_applied": list(self.optimization_applied),
        }

        return report


async def main():
    """Main performance optimization execution"""
    optimizer = PerformanceOptimizer()

    try:
        # Initialize optimizations
        await optimizer.initialize_optimizations()

        # Monitor performance for 2 minutes
        report = await optimizer.monitor_performance(120)

        # Save performance report
        report_path = "/tmp/performance_optimization_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        print(f"Performance optimization complete. Report saved to {report_path}")
        print(f"Optimizations applied: {', '.join(optimizer.optimization_applied)}")

    except Exception as e:
        logger.error(f"Performance optimization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
