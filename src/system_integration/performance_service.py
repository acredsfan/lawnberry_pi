"""
Performance Monitoring and Optimization Service
Provides comprehensive performance tracking, optimization, and intelligent resource management
"""

import asyncio
import gc
import json
import logging
import sqlite3
import sys
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import psutil

logger = logging.getLogger(__name__)


class OptimizationStrategy(Enum):
    """Performance optimization strategies"""

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    CUSTOM = "custom"


class PerformanceCategory(Enum):
    """Performance measurement categories"""

    CPU = "cpu"
    MEMORY = "memory"
    DISK_IO = "disk_io"
    NETWORK = "network"
    DATABASE = "database"
    WEB_API = "web_api"
    VISION = "vision"
    SENSOR_FUSION = "sensor_fusion"


class MetricType(Enum):
    """Types of performance metrics"""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


@dataclass
class PerformanceMetric:
    """Individual performance metric"""

    name: str
    category: PerformanceCategory
    metric_type: MetricType
    value: float
    timestamp: datetime
    tags: Dict[str, str] = field(default_factory=dict)
    unit: str = ""
    description: str = ""


@dataclass
class PerformanceBenchmark:
    """Performance benchmark definition"""

    name: str
    category: PerformanceCategory
    target_value: float
    threshold_warning: float
    threshold_critical: float
    unit: str
    higher_is_better: bool = True
    enabled: bool = True


@dataclass
class OptimizationRule:
    """Performance optimization rule"""

    name: str
    condition: str  # Python expression
    actions: List[str]
    cooldown_seconds: int = 300
    max_applications: int = 5
    enabled: bool = True
    last_applied: Optional[datetime] = None
    application_count: int = 0


@dataclass
class PerformanceProfile:
    """Performance profile for different operation modes"""

    name: str
    description: str
    cpu_priority: int = 0  # nice value
    memory_limit_mb: Optional[int] = None
    io_priority: int = 4  # ionice class
    network_priority: int = 0
    optimization_strategy: OptimizationStrategy = OptimizationStrategy.BALANCED
    custom_settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceReport:
    """Performance analysis report"""

    report_id: str
    timestamp: datetime
    period_start: datetime
    period_end: datetime
    overall_score: float
    category_scores: Dict[PerformanceCategory, float]
    recommendations: List[str]
    optimizations_applied: List[str]
    regression_detected: bool = False
    summary: str = ""


class PerformanceTimer:
    """Context manager for timing operations"""

    def __init__(
        self,
        performance_service,
        metric_name: str,
        category: PerformanceCategory,
        tags: Dict[str, str] = None,
    ):
        self.performance_service = performance_service
        self.metric_name = metric_name
        self.category = category
        self.tags = tags or {}
        self.start_time = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, _exc_type, _exc_val, _exc_tb):
        if self.start_time:
            duration_ms = (time.perf_counter() - self.start_time) * 1000
            asyncio.create_task(
                self.performance_service.record_metric(
                    self.metric_name, self.category, MetricType.TIMER, duration_ms, self.tags, "ms"
                )
            )


class PerformanceService:
    """Comprehensive performance monitoring and optimization service"""

    def __init__(self, db_path: str = "/var/lib/lawnberry/performance.db"):
        self.db_path = db_path

        # Metrics storage
        self.metrics_buffer: deque = deque(maxlen=10000)
        self.metrics_cache: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

        # Benchmarks and thresholds
        self.benchmarks: Dict[str, PerformanceBenchmark] = {}
        self.optimization_rules: Dict[str, OptimizationRule] = {}
        self.performance_profiles: Dict[str, PerformanceProfile] = {}

        # Current state
        self.current_profile = "balanced"
        self.active_optimizations: Set[str] = set()
        self.baseline_metrics: Dict[str, float] = {}

        # Configuration
        self.config = {
            "collection_interval": 5,  # seconds
            "analysis_interval": 60,  # seconds
            "report_interval": 3600,  # seconds
            "retention_days": 30,
            "auto_optimization": True,
            "regression_detection": True,
            "baseline_samples": 100,
        }

        # Threading
        self._db_lock = threading.Lock()
        self._metrics_lock = threading.Lock()

        # State
        self.running = False
        self.monitoring_tasks: set = set()

        self.logger = logger

        # Initialize default configurations
        self._setup_default_benchmarks()
        self._setup_default_optimization_rules()
        self._setup_default_profiles()

    async def initialize(self):
        """Initialize the performance service"""
        self.logger.info("Initializing Performance Service")

        # Initialize database
        await self._init_database()

        # Load configuration
        await self._load_configuration()

        # Establish baseline metrics
        await self._establish_baseline()

        # Start monitoring tasks
        self.running = True
        await self._start_monitoring_tasks()

        self.logger.info("Performance Service initialized")

    def _setup_default_benchmarks(self):
        """Setup default performance benchmarks"""
        benchmarks = [
            PerformanceBenchmark(
                name="cpu_usage",
                category=PerformanceCategory.CPU,
                target_value=50.0,
                threshold_warning=75.0,
                threshold_critical=90.0,
                unit="%",
                higher_is_better=False,
            ),
            PerformanceBenchmark(
                name="memory_usage",
                category=PerformanceCategory.MEMORY,
                target_value=60.0,
                threshold_warning=80.0,
                threshold_critical=95.0,
                unit="%",
                higher_is_better=False,
            ),
            PerformanceBenchmark(
                name="disk_usage",
                category=PerformanceCategory.DISK_IO,
                target_value=70.0,
                threshold_warning=85.0,
                threshold_critical=95.0,
                unit="%",
                higher_is_better=False,
            ),
            PerformanceBenchmark(
                name="api_response_time",
                category=PerformanceCategory.WEB_API,
                target_value=100.0,
                threshold_warning=500.0,
                threshold_critical=1000.0,
                unit="ms",
                higher_is_better=False,
            ),
            PerformanceBenchmark(
                name="vision_processing_fps",
                category=PerformanceCategory.VISION,
                target_value=30.0,
                threshold_warning=15.0,
                threshold_critical=5.0,
                unit="fps",
                higher_is_better=True,
            ),
            PerformanceBenchmark(
                name="sensor_fusion_latency",
                category=PerformanceCategory.SENSOR_FUSION,
                target_value=50.0,
                threshold_warning=100.0,
                threshold_critical=200.0,
                unit="ms",
                higher_is_better=False,
            ),
        ]

        for benchmark in benchmarks:
            self.benchmarks[benchmark.name] = benchmark

    def _setup_default_optimization_rules(self):
        """Setup default optimization rules"""
        rules = [
            OptimizationRule(
                name="high_cpu_optimization",
                condition="cpu_usage > 80",
                actions=["reduce_vision_fps", "increase_gc_threshold", "optimize_asyncio_tasks"],
                cooldown_seconds=300,
            ),
            OptimizationRule(
                name="high_memory_optimization",
                condition="memory_usage > 85",
                actions=["force_garbage_collection", "clear_caches", "reduce_buffer_sizes"],
                cooldown_seconds=180,
            ),
            OptimizationRule(
                name="slow_api_optimization",
                condition="api_response_time > 500",
                actions=["enable_api_caching", "optimize_database_queries", "reduce_data_payload"],
                cooldown_seconds=600,
            ),
            OptimizationRule(
                name="disk_io_optimization",
                condition="disk_io_wait > 50",
                actions=["optimize_log_rotation", "batch_disk_writes", "compress_data_files"],
                cooldown_seconds=900,
            ),
        ]

        for rule in rules:
            self.optimization_rules[rule.name] = rule

    def _setup_default_profiles(self):
        """Setup default performance profiles"""
        profiles = [
            PerformanceProfile(
                name="power_saving",
                description="Optimize for battery life and low power consumption",
                cpu_priority=10,
                memory_limit_mb=512,
                io_priority=7,
                optimization_strategy=OptimizationStrategy.AGGRESSIVE,
                custom_settings={
                    "vision_fps": 15,
                    "sensor_update_rate": 10,
                    "api_cache_timeout": 300,
                },
            ),
            PerformanceProfile(
                name="balanced",
                description="Balance between performance and resource usage",
                cpu_priority=0,
                memory_limit_mb=1024,
                io_priority=4,
                optimization_strategy=OptimizationStrategy.BALANCED,
                custom_settings={
                    "vision_fps": 30,
                    "sensor_update_rate": 20,
                    "api_cache_timeout": 120,
                },
            ),
            PerformanceProfile(
                name="performance",
                description="Optimize for maximum performance",
                cpu_priority=-5,
                memory_limit_mb=2048,
                io_priority=1,
                optimization_strategy=OptimizationStrategy.CONSERVATIVE,
                custom_settings={
                    "vision_fps": 60,
                    "sensor_update_rate": 50,
                    "api_cache_timeout": 60,
                },
            ),
        ]

        for profile in profiles:
            self.performance_profiles[profile.name] = profile

    async def _init_database(self):
        """Initialize performance database"""
        try:
            # Create database directory
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        category TEXT NOT NULL,
                        metric_type TEXT NOT NULL,
                        value REAL NOT NULL,
                        timestamp DATETIME NOT NULL,
                        tags TEXT,
                        unit TEXT,
                        description TEXT
                    )
                """
                )

                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_metrics_timestamp
                    ON metrics(timestamp)
                """
                )

                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_metrics_name_category
                    ON metrics(name, category)
                """
                )

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS performance_reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        report_id TEXT UNIQUE NOT NULL,
                        timestamp DATETIME NOT NULL,
                        period_start DATETIME NOT NULL,
                        period_end DATETIME NOT NULL,
                        overall_score REAL NOT NULL,
                        category_scores TEXT,
                        recommendations TEXT,
                        optimizations_applied TEXT,
                        regression_detected BOOLEAN,
                        summary TEXT
                    )
                """
                )

                conn.commit()

        except Exception as e:
            self.logger.error(f"Failed to initialize performance database: {e}")
            raise

    async def _start_monitoring_tasks(self):
        """Start background monitoring tasks"""
        tasks = [
            asyncio.create_task(self._metrics_collection_loop()),
            asyncio.create_task(self._performance_analysis_loop()),
            asyncio.create_task(self._optimization_loop()),
            asyncio.create_task(self._database_maintenance_loop()),
            asyncio.create_task(self._reporting_loop()),
        ]

        self.monitoring_tasks.update(tasks)

    async def _metrics_collection_loop(self):
        """Main metrics collection loop"""
        while self.running:
            try:
                await self._collect_system_metrics()
                await self._collect_service_metrics()
                await self._flush_metrics_buffer()
                await asyncio.sleep(self.config["collection_interval"])
            except Exception as e:
                self.logger.error(f"Metrics collection error: {e}")
                await asyncio.sleep(5)

    async def _performance_analysis_loop(self):
        """Performance analysis loop"""
        while self.running:
            try:
                await self._analyze_performance()
                await asyncio.sleep(self.config["analysis_interval"])
            except Exception as e:
                self.logger.error(f"Performance analysis error: {e}")
                await asyncio.sleep(30)

    async def _optimization_loop(self):
        """Performance optimization loop"""
        while self.running:
            try:
                if self.config["auto_optimization"]:
                    await self._apply_optimizations()
                await asyncio.sleep(60)
            except Exception as e:
                self.logger.error(f"Optimization loop error: {e}")
                await asyncio.sleep(30)

    async def _reporting_loop(self):
        """Performance reporting loop"""
        while self.running:
            try:
                await self._generate_performance_report()
                await asyncio.sleep(self.config["report_interval"])
            except Exception as e:
                self.logger.error(f"Reporting loop error: {e}")
                await asyncio.sleep(300)

    async def _database_maintenance_loop(self):
        """Database maintenance loop"""
        while self.running:
            try:
                await self._cleanup_old_metrics()
                await asyncio.sleep(3600)  # Run every hour
            except Exception as e:
                self.logger.error(f"Database maintenance error: {e}")
                await asyncio.sleep(1800)  # Retry in 30 minutes

    async def _collect_system_metrics(self):
        """Collect system-wide performance metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            load_avg = psutil.getloadavg() if hasattr(psutil, "getloadavg") else (0, 0, 0)

            await self.record_metric(
                "cpu_usage", PerformanceCategory.CPU, MetricType.GAUGE, cpu_percent, {}, "%"
            )
            await self.record_metric(
                "cpu_count", PerformanceCategory.CPU, MetricType.GAUGE, cpu_count, {}, "cores"
            )
            await self.record_metric(
                "load_avg_1m", PerformanceCategory.CPU, MetricType.GAUGE, load_avg[0], {}, ""
            )

            # Memory metrics
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()

            await self.record_metric(
                "memory_usage",
                PerformanceCategory.MEMORY,
                MetricType.GAUGE,
                memory.percent,
                {},
                "%",
            )
            await self.record_metric(
                "memory_used_mb",
                PerformanceCategory.MEMORY,
                MetricType.GAUGE,
                memory.used / 1024 / 1024,
                {},
                "MB",
            )
            await self.record_metric(
                "memory_available_mb",
                PerformanceCategory.MEMORY,
                MetricType.GAUGE,
                memory.available / 1024 / 1024,
                {},
                "MB",
            )
            await self.record_metric(
                "swap_usage", PerformanceCategory.MEMORY, MetricType.GAUGE, swap.percent, {}, "%"
            )

            # Disk I/O metrics
            disk_usage = psutil.disk_usage("/")
            disk_io = psutil.disk_io_counters()

            disk_percent = (disk_usage.used / disk_usage.total) * 100
            await self.record_metric(
                "disk_usage", PerformanceCategory.DISK_IO, MetricType.GAUGE, disk_percent, {}, "%"
            )

            if disk_io:
                await self.record_metric(
                    "disk_read_mb_s",
                    PerformanceCategory.DISK_IO,
                    MetricType.GAUGE,
                    disk_io.read_bytes / 1024 / 1024,
                    {},
                    "MB/s",
                )
                await self.record_metric(
                    "disk_write_mb_s",
                    PerformanceCategory.DISK_IO,
                    MetricType.GAUGE,
                    disk_io.write_bytes / 1024 / 1024,
                    {},
                    "MB/s",
                )

            # Network metrics
            network_io = psutil.net_io_counters()
            if network_io:
                await self.record_metric(
                    "network_sent_mb_s",
                    PerformanceCategory.NETWORK,
                    MetricType.GAUGE,
                    network_io.bytes_sent / 1024 / 1024,
                    {},
                    "MB/s",
                )
                await self.record_metric(
                    "network_recv_mb_s",
                    PerformanceCategory.NETWORK,
                    MetricType.GAUGE,
                    network_io.bytes_recv / 1024 / 1024,
                    {},
                    "MB/s",
                )

            # Process-specific metrics
            current_process = psutil.Process()
            await self.record_metric(
                "process_cpu_percent",
                PerformanceCategory.CPU,
                MetricType.GAUGE,
                current_process.cpu_percent(),
                {"process": "lawnberry"},
                "%",
            )

            memory_info = current_process.memory_info()
            await self.record_metric(
                "process_memory_mb",
                PerformanceCategory.MEMORY,
                MetricType.GAUGE,
                memory_info.rss / 1024 / 1024,
                {"process": "lawnberry"},
                "MB",
            )

        except Exception as e:
            self.logger.error(f"Failed to collect system metrics: {e}")

    async def _collect_service_metrics(self):
        """Collect service-specific performance metrics"""
        try:
            # Collect metrics from individual services
            # This would integrate with service managers to get specific metrics

            # Python garbage collection metrics
            gc_stats = gc.get_stats()
            if gc_stats:
                await self.record_metric(
                    "gc_collections",
                    PerformanceCategory.MEMORY,
                    MetricType.COUNTER,
                    sum(stat["collections"] for stat in gc_stats),
                    {},
                    "count",
                )

            # Thread count
            thread_count = threading.active_count()
            await self.record_metric(
                "thread_count", PerformanceCategory.CPU, MetricType.GAUGE, thread_count, {}, "count"
            )

            # Open file descriptors
            try:
                fd_count = len(psutil.Process().open_files())
                await self.record_metric(
                    "open_files",
                    PerformanceCategory.DISK_IO,
                    MetricType.GAUGE,
                    fd_count,
                    {},
                    "count",
                )
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass

        except Exception as e:
            self.logger.error(f"Failed to collect service metrics: {e}")

    async def record_metric(
        self,
        name: str,
        category: PerformanceCategory,
        metric_type: MetricType,
        value: float,
        tags: Dict[str, str] = None,
        unit: str = "",
        description: str = "",
    ):
        """Record a performance metric"""
        try:
            metric = PerformanceMetric(
                name=name,
                category=category,
                metric_type=metric_type,
                value=value,
                timestamp=datetime.now(),
                tags=tags or {},
                unit=unit,
                description=description,
            )

            with self._metrics_lock:
                self.metrics_buffer.append(metric)
                self.metrics_cache[f"{category.value}.{name}"].append(metric)

        except Exception as e:
            self.logger.error(f"Failed to record metric {name}: {e}")

    async def _flush_metrics_buffer(self):
        """Flush metrics buffer to database"""
        if not self.metrics_buffer:
            return

        try:
            with self._metrics_lock:
                metrics_to_flush = list(self.metrics_buffer)
                self.metrics_buffer.clear()

            with self._db_lock:
                with sqlite3.connect(self.db_path) as conn:
                    for metric in metrics_to_flush:
                        conn.execute(
                            """
                            INSERT INTO metrics
                            (name, category, metric_type, value, timestamp, tags, unit, description)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                            (
                                metric.name,
                                metric.category.value,
                                metric.metric_type.value,
                                metric.value,
                                metric.timestamp,
                                json.dumps(metric.tags),
                                metric.unit,
                                metric.description,
                            ),
                        )
                    conn.commit()

        except Exception as e:
            self.logger.error(f"Failed to flush metrics to database: {e}")

    async def _analyze_performance(self):
        """Analyze current performance against benchmarks"""
        try:
            current_metrics = await self._get_current_metrics()

            for benchmark_name, benchmark in self.benchmarks.items():
                if not benchmark.enabled:
                    continue

                metric_key = f"{benchmark.category.value}.{benchmark_name}"
                if metric_key in current_metrics:
                    current_value = current_metrics[metric_key]

                    # Check thresholds
                    if benchmark.higher_is_better:
                        if current_value < benchmark.threshold_critical:
                            await self._trigger_performance_alert(
                                benchmark, current_value, "critical"
                            )
                        elif current_value < benchmark.threshold_warning:
                            await self._trigger_performance_alert(
                                benchmark, current_value, "warning"
                            )
                    else:
                        if current_value > benchmark.threshold_critical:
                            await self._trigger_performance_alert(
                                benchmark, current_value, "critical"
                            )
                        elif current_value > benchmark.threshold_warning:
                            await self._trigger_performance_alert(
                                benchmark, current_value, "warning"
                            )

                    # Check for regression
                    if self.config["regression_detection"]:
                        await self._check_regression(benchmark_name, current_value)

        except Exception as e:
            self.logger.error(f"Performance analysis failed: {e}")

    async def _get_current_metrics(self) -> Dict[str, float]:
        """Get current metric values"""
        current_metrics = {}

        for metric_key, metric_deque in self.metrics_cache.items():
            if metric_deque:
                # Get average of recent values
                recent_values = [m.value for m in list(metric_deque)[-10:]]
                if recent_values:
                    current_metrics[metric_key] = sum(recent_values) / len(recent_values)

        return current_metrics

    async def _trigger_performance_alert(
        self, benchmark: PerformanceBenchmark, current_value: float, severity: str
    ):
        """Trigger performance-related alert"""
        message = f"Performance threshold exceeded for {benchmark.name}: {current_value:.2f} {benchmark.unit}"

        # This would integrate with the alerting system
        self.logger.warning(f"PERFORMANCE ALERT [{severity.upper()}]: {message}")

    async def _check_regression(self, metric_name: str, current_value: float):
        """Check for performance regression"""
        if metric_name in self.baseline_metrics:
            baseline = self.baseline_metrics[metric_name]

            # Check for significant degradation (> 20% worse than baseline)
            threshold = 0.20

            benchmark = self.benchmarks.get(metric_name)
            if benchmark:
                if benchmark.higher_is_better:
                    if current_value < baseline * (1 - threshold):
                        self.logger.warning(
                            f"Performance regression detected for {metric_name}: "
                            f"{current_value:.2f} vs baseline {baseline:.2f}"
                        )
                else:
                    if current_value > baseline * (1 + threshold):
                        self.logger.warning(
                            f"Performance regression detected for {metric_name}: "
                            f"{current_value:.2f} vs baseline {baseline:.2f}"
                        )

    async def _apply_optimizations(self):
        """Apply performance optimizations based on rules"""
        try:
            current_metrics = await self._get_current_metrics()

            for rule_name, rule in self.optimization_rules.items():
                if not rule.enabled:
                    continue

                # Check cooldown
                if rule.last_applied:
                    time_since_applied = (datetime.now() - rule.last_applied).total_seconds()
                    if time_since_applied < rule.cooldown_seconds:
                        continue

                # Check application limit
                if rule.application_count >= rule.max_applications:
                    continue

                # Evaluate condition
                try:
                    # Create context for condition evaluation
                    context = {**current_metrics}
                    context.update(
                        {
                            "cpu_usage": current_metrics.get("cpu.cpu_usage", 0),
                            "memory_usage": current_metrics.get("memory.memory_usage", 0),
                            "disk_usage": current_metrics.get("disk_io.disk_usage", 0),
                            "api_response_time": current_metrics.get(
                                "web_api.api_response_time", 0
                            ),
                            "disk_io_wait": current_metrics.get("disk_io.disk_io_wait", 0),
                        }
                    )

                    if eval(rule.condition, {"__builtins__": {}}, context):
                        self.logger.info(f"Applying optimization rule: {rule_name}")

                        success = await self._execute_optimization_actions(rule.actions)
                        if success:
                            rule.last_applied = datetime.now()
                            rule.application_count += 1
                            self.active_optimizations.add(rule_name)

                except Exception as e:
                    self.logger.error(f"Failed to evaluate optimization rule {rule_name}: {e}")

        except Exception as e:
            self.logger.error(f"Failed to apply optimizations: {e}")

    async def _execute_optimization_actions(self, actions: List[str]) -> bool:
        """Execute optimization actions"""
        try:
            success_count = 0

            for action in actions:
                try:
                    if action == "reduce_vision_fps":
                        # Reduce vision processing frame rate
                        await self._optimize_vision_fps(reduce=True)
                        success_count += 1

                    elif action == "increase_gc_threshold":
                        # Adjust garbage collection thresholds
                        gc.set_threshold(700, 10, 10)  # More aggressive GC
                        success_count += 1

                    elif action == "optimize_asyncio_tasks":
                        # Optimize asyncio event loop
                        await self._optimize_asyncio_performance()
                        success_count += 1

                    elif action == "force_garbage_collection":
                        # Force garbage collection
                        gc.collect()
                        success_count += 1

                    elif action == "clear_caches":
                        # Clear application caches
                        await self._clear_application_caches()
                        success_count += 1

                    elif action == "reduce_buffer_sizes":
                        # Reduce buffer sizes
                        await self._optimize_buffer_sizes(reduce=True)
                        success_count += 1

                    elif action == "enable_api_caching":
                        # Enable API response caching
                        await self._optimize_api_caching(enable=True)
                        success_count += 1

                    elif action == "optimize_database_queries":
                        # Optimize database query performance
                        await self._optimize_database_performance()
                        success_count += 1

                    else:
                        self.logger.warning(f"Unknown optimization action: {action}")

                except Exception as e:
                    self.logger.error(f"Failed to execute optimization action {action}: {e}")

            return success_count > 0

        except Exception as e:
            self.logger.error(f"Failed to execute optimization actions: {e}")
            return False

    async def _optimize_vision_fps(self, reduce: bool = True):
        """Optimize vision processing FPS"""
        # This would integrate with the vision service
        self.logger.info(f"{'Reducing' if reduce else 'Increasing'} vision processing FPS")

    async def _optimize_asyncio_performance(self):
        """Optimize asyncio event loop performance"""
        # Set event loop policy for better performance
        if sys.platform != "win32":
            try:
                import uvloop

                uvloop.install()
                self.logger.info("Installed uvloop for better asyncio performance")
            except ImportError:
                pass

    async def _clear_application_caches(self):
        """Clear application caches to free memory"""
        # This would integrate with various caching systems
        self.logger.info("Clearing application caches")

    async def _optimize_buffer_sizes(self, reduce: bool = True):
        """Optimize buffer sizes"""
        # Adjust buffer sizes in various components
        self.logger.info(f"{'Reducing' if reduce else 'Increasing'} buffer sizes")

    async def _optimize_api_caching(self, enable: bool = True):
        """Optimize API caching"""
        # Configure API response caching
        self.logger.info(f"{'Enabling' if enable else 'Disabling'} API caching")

    async def _optimize_database_performance(self):
        """Optimize database performance"""
        # Database-specific optimizations
        self.logger.info("Optimizing database performance")

    async def _generate_performance_report(self):
        """Generate comprehensive performance report"""
        try:
            report_id = f"perf_report_{int(time.time())}"
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)

            # Calculate performance scores
            overall_score, category_scores = await self._calculate_performance_scores(
                start_time, end_time
            )

            # Generate recommendations
            recommendations = await self._generate_recommendations(category_scores)

            # Create report
            report = PerformanceReport(
                report_id=report_id,
                timestamp=end_time,
                period_start=start_time,
                period_end=end_time,
                overall_score=overall_score,
                category_scores=category_scores,
                recommendations=recommendations,
                optimizations_applied=list(self.active_optimizations),
                regression_detected=False,  # Would be calculated
                summary=f"Overall performance score: {overall_score:.1f}/100",
            )

            # Save report to database
            await self._save_performance_report(report)

            self.logger.info(
                f"Generated performance report {report_id} - Score: {overall_score:.1f}/100"
            )

        except Exception as e:
            self.logger.error(f"Failed to generate performance report: {e}")

    async def _calculate_performance_scores(
        self, start_time: datetime, end_time: datetime
    ) -> Tuple[float, Dict[PerformanceCategory, float]]:
        """Calculate performance scores for the given time period"""
        category_scores = {}

        # Calculate scores for each category
        for category in PerformanceCategory:
            category_scores[category] = await self._calculate_category_score(
                category, start_time, end_time
            )

        # Calculate overall score as weighted average
        weights = {
            PerformanceCategory.CPU: 0.25,
            PerformanceCategory.MEMORY: 0.25,
            PerformanceCategory.DISK_IO: 0.15,
            PerformanceCategory.NETWORK: 0.10,
            PerformanceCategory.WEB_API: 0.15,
            PerformanceCategory.VISION: 0.05,
            PerformanceCategory.SENSOR_FUSION: 0.05,
        }

        overall_score = sum(
            category_scores.get(category, 100.0) * weight for category, weight in weights.items()
        )

        return overall_score, category_scores

    async def _calculate_category_score(
        self, category: PerformanceCategory, start_time: datetime, end_time: datetime
    ) -> float:
        """Calculate performance score for a specific category"""
        try:
            # Get metrics for this category in the time period
            with self._db_lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        """
                        SELECT name, AVG(value) as avg_value
                        FROM metrics
                        WHERE category = ? AND timestamp BETWEEN ? AND ?
                        GROUP BY name
                    """,
                        (category.value, start_time, end_time),
                    )

                    results = cursor.fetchall()

            if not results:
                return 100.0  # Default score if no data

            # Calculate score based on benchmarks
            total_score = 0.0
            benchmark_count = 0

            for metric_name, avg_value in results:
                if metric_name in self.benchmarks:
                    benchmark = self.benchmarks[metric_name]
                    score = self._calculate_metric_score(avg_value, benchmark)
                    total_score += score
                    benchmark_count += 1

            return total_score / benchmark_count if benchmark_count > 0 else 100.0

        except Exception as e:
            self.logger.error(f"Failed to calculate category score for {category}: {e}")
            return 50.0  # Default middle score on error

    def _calculate_metric_score(self, value: float, benchmark: PerformanceBenchmark) -> float:
        """Calculate score for a single metric"""
        if benchmark.higher_is_better:
            if value >= benchmark.target_value:
                return 100.0
            elif value >= benchmark.threshold_warning:
                return (
                    70.0
                    + (value - benchmark.threshold_warning)
                    / (benchmark.target_value - benchmark.threshold_warning)
                    * 30.0
                )
            elif value >= benchmark.threshold_critical:
                return (
                    30.0
                    + (value - benchmark.threshold_critical)
                    / (benchmark.threshold_warning - benchmark.threshold_critical)
                    * 40.0
                )
            else:
                return max(0.0, value / benchmark.threshold_critical * 30.0)
        else:
            if value <= benchmark.target_value:
                return 100.0
            elif value <= benchmark.threshold_warning:
                return (
                    70.0
                    + (benchmark.threshold_warning - value)
                    / (benchmark.threshold_warning - benchmark.target_value)
                    * 30.0
                )
            elif value <= benchmark.threshold_critical:
                return (
                    30.0
                    + (benchmark.threshold_critical - value)
                    / (benchmark.threshold_critical - benchmark.threshold_warning)
                    * 40.0
                )
            else:
                return max(
                    0.0,
                    30.0
                    * (
                        1.0
                        - min(
                            1.0,
                            (value - benchmark.threshold_critical) / benchmark.threshold_critical,
                        )
                    ),
                )

    async def _generate_recommendations(
        self, category_scores: Dict[PerformanceCategory, float]
    ) -> List[str]:
        """Generate performance improvement recommendations"""
        recommendations = []

        for category, score in category_scores.items():
            if score < 70.0:
                if category == PerformanceCategory.CPU:
                    recommendations.append(
                        "Consider reducing CPU-intensive operations or upgrading hardware"
                    )
                elif category == PerformanceCategory.MEMORY:
                    recommendations.append("Optimize memory usage or increase available RAM")
                elif category == PerformanceCategory.DISK_IO:
                    recommendations.append("Optimize disk I/O operations or upgrade storage")
                elif category == PerformanceCategory.NETWORK:
                    recommendations.append("Check network connectivity and optimize data transfer")
                elif category == PerformanceCategory.WEB_API:
                    recommendations.append("Optimize API response times and caching strategies")
                elif category == PerformanceCategory.VISION:
                    recommendations.append(
                        "Optimize computer vision processing or reduce frame rate"
                    )
                elif category == PerformanceCategory.SENSOR_FUSION:
                    recommendations.append("Optimize sensor data processing and fusion algorithms")

        if not recommendations:
            recommendations.append("System performance is within acceptable ranges")

        return recommendations

    async def _save_performance_report(self, report: PerformanceReport):
        """Save performance report to database"""
        try:
            with self._db_lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        """
                        INSERT INTO performance_reports
                        (report_id, timestamp, period_start, period_end, overall_score,
                         category_scores, recommendations, optimizations_applied,
                         regression_detected, summary)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            report.report_id,
                            report.timestamp,
                            report.period_start,
                            report.period_end,
                            report.overall_score,
                            json.dumps({k.value: v for k, v in report.category_scores.items()}),
                            json.dumps(report.recommendations),
                            json.dumps(report.optimizations_applied),
                            report.regression_detected,
                            report.summary,
                        ),
                    )
                    conn.commit()

        except Exception as e:
            self.logger.error(f"Failed to save performance report: {e}")

    async def _cleanup_old_metrics(self):
        """Clean up old metrics from database"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.config["retention_days"])

            with self._db_lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff_date,))
                    deleted_count = cursor.rowcount
                    conn.commit()

            if deleted_count > 0:
                self.logger.info(f"Cleaned up {deleted_count} old metric records")

        except Exception as e:
            self.logger.error(f"Failed to cleanup old metrics: {e}")

    async def _establish_baseline(self):
        """Establish performance baseline metrics"""
        try:
            # Collect baseline samples
            self.logger.info("Establishing performance baseline...")

            for i in range(self.config["baseline_samples"]):
                await self._collect_system_metrics()
                await asyncio.sleep(1)

            # Calculate baseline values
            current_metrics = await self._get_current_metrics()
            self.baseline_metrics = current_metrics.copy()

            self.logger.info(
                f"Performance baseline established with {len(self.baseline_metrics)} metrics"
            )

        except Exception as e:
            self.logger.error(f"Failed to establish performance baseline: {e}")

    async def _load_configuration(self):
        """Load performance service configuration"""
        # Would load from configuration file
        pass

    # Public API methods

    def timer(
        self, metric_name: str, category: PerformanceCategory, tags: Dict[str, str] = None
    ) -> PerformanceTimer:
        """Create a performance timer context manager"""
        return PerformanceTimer(self, metric_name, category, tags)

    async def get_current_performance_score(self) -> float:
        """Get current overall performance score"""
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=5)

        overall_score, _ = await self._calculate_performance_scores(start_time, end_time)
        return overall_score

    async def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        current_metrics = await self._get_current_metrics()
        overall_score = await self.get_current_performance_score()

        return {
            "overall_score": overall_score,
            "current_metrics": current_metrics,
            "active_optimizations": list(self.active_optimizations),
            "current_profile": self.current_profile,
            "baseline_established": bool(self.baseline_metrics),
        }

    async def set_performance_profile(self, profile_name: str) -> bool:
        """Set active performance profile"""
        if profile_name in self.performance_profiles:
            self.current_profile = profile_name
            profile = self.performance_profiles[profile_name]

            # Apply profile settings
            await self._apply_performance_profile(profile)

            self.logger.info(f"Switched to performance profile: {profile_name}")
            return True

        return False

    async def _apply_performance_profile(self, profile: PerformanceProfile):
        """Apply performance profile settings"""
        try:
            # Apply system-level settings
            if profile.cpu_priority != 0:
                # Set process priority
                current_process = psutil.Process()
                current_process.nice(profile.cpu_priority)

            # Apply custom settings to various services
            for setting, value in profile.custom_settings.items():
                await self._apply_profile_setting(setting, value)

        except Exception as e:
            self.logger.error(f"Failed to apply performance profile: {e}")

    async def _apply_profile_setting(self, setting: str, value: Any):
        """Apply individual profile setting"""
        # This would integrate with various services to apply settings
        self.logger.info(f"Applied profile setting: {setting} = {value}")

    async def force_optimization_run(self):
        """Force an optimization run"""
        await self._apply_optimizations()

    async def get_performance_metrics(
        self, category: Optional[PerformanceCategory] = None, hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get performance metrics for specified period"""
        try:
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)

            with self._db_lock:
                with sqlite3.connect(self.db_path) as conn:
                    if category:
                        cursor = conn.execute(
                            """
                            SELECT name, category, value, timestamp, unit
                            FROM metrics
                            WHERE category = ? AND timestamp BETWEEN ? AND ?
                            ORDER BY timestamp DESC
                        """,
                            (category.value, start_time, end_time),
                        )
                    else:
                        cursor = conn.execute(
                            """
                            SELECT name, category, value, timestamp, unit
                            FROM metrics
                            WHERE timestamp BETWEEN ? AND ?
                            ORDER BY timestamp DESC
                        """,
                            (start_time, end_time),
                        )

                    results = cursor.fetchall()

            return [
                {
                    "name": row[0],
                    "category": row[1],
                    "value": row[2],
                    "timestamp": row[3],
                    "unit": row[4],
                }
                for row in results
            ]

        except Exception as e:
            self.logger.error(f"Failed to get performance metrics: {e}")
            return []

    async def shutdown(self):
        """Shutdown the performance service"""
        self.running = False

        # Cancel monitoring tasks
        for task in self.monitoring_tasks:
            if not task.done():
                task.cancel()

        # Flush remaining metrics
        await self._flush_metrics_buffer()

        self.logger.info("Performance Service shut down")
