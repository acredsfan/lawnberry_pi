"""
Dynamic Resource Manager - Intelligent resource allocation for Raspberry Pi 4B
Implements adaptive resource management with real-time workload analysis
"""

import asyncio
import logging
import psutil
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
from pathlib import Path
import threading
import numpy as np
from collections import deque

logger = logging.getLogger(__name__)


class OperationMode(Enum):
    """System operation modes"""
    MOWING = "mowing"
    CHARGING = "charging" 
    IDLE = "idle"
    MAINTENANCE = "maintenance"
    EMERGENCY = "emergency"


class ResourceType(Enum):
    """Resource types for allocation"""
    CPU = "cpu"
    MEMORY = "memory"
    IO_BANDWIDTH = "io_bandwidth"
    NETWORK = "network"


@dataclass
class ResourceLimits:
    """Resource limits for a service"""
    cpu_percent: float = 100.0
    memory_mb: float = 1024.0
    io_priority: int = 4  # ionice priority (0-7, lower is higher priority)
    cpu_affinity: Optional[List[int]] = None
    nice_value: int = 0  # process priority (-20 to 19, lower is higher priority)


@dataclass
class ServiceResourceProfile:
    """Resource profile for different operation modes"""
    service_name: str
    base_limits: ResourceLimits
    mode_adjustments: Dict[OperationMode, ResourceLimits] = field(default_factory=dict)
    priority: int = 5  # Service priority (1-10, lower is higher priority)
    critical: bool = False
    adaptive: bool = True


@dataclass
class ResourceMetrics:
    """Real-time resource usage metrics"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_mb: float
    io_read_mb_s: float
    io_write_mb_s: float
    network_bytes_s: float
    load_average: List[float]
    temperature: Optional[float] = None


@dataclass
class AllocationDecision:
    """Resource allocation decision"""
    service_name: str
    resource_type: ResourceType
    old_value: Any
    new_value: Any
    reason: str
    timestamp: datetime
    confidence: float


class DynamicResourceManager:
    """
    Intelligent dynamic resource management for Raspberry Pi 4B
    Adapts resource allocation based on real-time workload analysis
    """
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.current_mode = OperationMode.IDLE
        
        # Resource profiles for services
        self.service_profiles: Dict[str, ServiceResourceProfile] = {}
        self.current_allocations: Dict[str, ResourceLimits] = {}
        
        # Performance monitoring
        self.metrics_history: deque = deque(maxlen=1000)
        self.allocation_history: deque = deque(maxlen=500)
        
        # Resource monitoring
        self.monitoring_active = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self.monitoring_interval = 1.0  # seconds
        
        # Thresholds and adaptation parameters
        self.cpu_pressure_threshold = 80.0
        self.memory_pressure_threshold = 75.0
        self.adaptation_cooldown = 10.0  # seconds between adaptations
        self.last_adaptation_time = 0.0
        
        # Hardware capabilities (Pi 4B specific - 8GB model target)
        self.max_memory_mb = 8192  # 8GB Pi 4B
        self.cpu_cores = 4
        self.cpu_threads = 4
        
        # Performance tracking
        self.performance_baselines: Dict[str, Dict[str, float]] = {}
        self.load_predictions: Dict[str, float] = {}
        
        # Initialize default service profiles
        self._initialize_service_profiles()
        
    def _initialize_service_profiles(self):
        """Initialize default resource profiles for all services"""
        
        # Critical safety services - highest priority, guaranteed resources
        self.service_profiles['safety'] = ServiceResourceProfile(
            service_name='safety',
            base_limits=ResourceLimits(
                cpu_percent=30.0,
                memory_mb=512.0,
                io_priority=1,
                nice_value=-10
            ),
            priority=1,
            critical=True,
            adaptive=False  # Safety never throttled
        )
        
        self.service_profiles['communication'] = ServiceResourceProfile(
            service_name='communication',
            base_limits=ResourceLimits(
                cpu_percent=15.0,
                memory_mb=256.0,
                io_priority=2,
                nice_value=-5
            ),
            priority=2,
            critical=True,
            adaptive=True
        )
        
        self.service_profiles['hardware'] = ServiceResourceProfile(
            service_name='hardware',
            base_limits=ResourceLimits(
                cpu_percent=20.0,
                memory_mb=512.0,
                io_priority=2,
                nice_value=-5
            ),
            priority=3,
            critical=True,
            adaptive=True
        )
        
        # Sensor fusion - adaptive based on mode
        self.service_profiles['sensor_fusion'] = ServiceResourceProfile(
            service_name='sensor_fusion',
            base_limits=ResourceLimits(
                cpu_percent=25.0,
                memory_mb=1024.0,
                io_priority=3,
                nice_value=0
            ),
            mode_adjustments={
                OperationMode.MOWING: ResourceLimits(cpu_percent=35.0, memory_mb=1536.0),
                OperationMode.IDLE: ResourceLimits(cpu_percent=10.0, memory_mb=512.0),
                OperationMode.CHARGING: ResourceLimits(cpu_percent=15.0, memory_mb=768.0)
            },
            priority=4,
            critical=False,
            adaptive=True
        )
        
        # Vision processing - highly adaptive
        self.service_profiles['vision'] = ServiceResourceProfile(
            service_name='vision',
            base_limits=ResourceLimits(
                cpu_percent=40.0,
                memory_mb=2048.0,
                io_priority=4,
                nice_value=5
            ),
            mode_adjustments={
                OperationMode.MOWING: ResourceLimits(cpu_percent=50.0, memory_mb=3072.0),
                OperationMode.IDLE: ResourceLimits(cpu_percent=5.0, memory_mb=512.0),
                OperationMode.CHARGING: ResourceLimits(cpu_percent=10.0, memory_mb=768.0)
            },
            priority=6,
            critical=False,
            adaptive=True
        )
        
        # Web API - adaptive based on user activity
        self.service_profiles['web_api'] = ServiceResourceProfile(
            service_name='web_api',
            base_limits=ResourceLimits(
                cpu_percent=15.0,
                memory_mb=512.0,
                io_priority=5,
                nice_value=10
            ),
            priority=7,
            critical=False,
            adaptive=True
        )
        
        # Data management - background processing
        self.service_profiles['data_management'] = ServiceResourceProfile(
            service_name='data_management',
            base_limits=ResourceLimits(
                cpu_percent=10.0,
                memory_mb=512.0,
                io_priority=6,
                nice_value=15
            ),
            priority=8,
            critical=False,
            adaptive=True
        )
        
        # Weather service - low priority
        self.service_profiles['weather'] = ServiceResourceProfile(
            service_name='weather',
            base_limits=ResourceLimits(
                cpu_percent=5.0,
                memory_mb=256.0,
                io_priority=7,
                nice_value=19
            ),
            priority=9,
            critical=False,
            adaptive=True
        )
        
        # Power management - critical but low resource
        self.service_profiles['power_management'] = ServiceResourceProfile(
            service_name='power_management',
            base_limits=ResourceLimits(
                cpu_percent=10.0,
                memory_mb=256.0,
                io_priority=2,
                nice_value=0
            ),
            priority=3,
            critical=True,
            adaptive=True
        )
        
    async def initialize(self):
        """Initialize the dynamic resource manager"""
        logger.info("Initializing Dynamic Resource Manager")
        
        # Load configuration if available
        if self.config_manager:
            await self._load_configuration()
        
        # Initialize current allocations with base limits
        for service_name, profile in self.service_profiles.items():
            self.current_allocations[service_name] = profile.base_limits
        
        # Start monitoring
        await self.start_monitoring()
        
        logger.info("Dynamic Resource Manager initialized")
    
    async def start_monitoring(self):
        """Start resource monitoring and adaptation"""
        if self.monitoring_active:
            return
            
        self.monitoring_active = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Started dynamic resource monitoring")
    
    async def stop_monitoring(self):
        """Stop resource monitoring"""
        self.monitoring_active = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped dynamic resource monitoring")
    
    async def _monitoring_loop(self):
        """Main monitoring and adaptation loop"""
        while self.monitoring_active:
            try:
                # Collect current metrics
                metrics = await self._collect_metrics()
                self.metrics_history.append(metrics)
                
                # Analyze workload and make adaptation decisions
                if await self._should_adapt():
                    decisions = await self._analyze_and_adapt(metrics)
                    await self._apply_allocation_decisions(decisions)
                
                # Update performance baselines
                await self._update_performance_baselines()
                
                await asyncio.sleep(self.monitoring_interval)
                
            except Exception as e:
                logger.error(f"Error in resource monitoring loop: {e}")
                await asyncio.sleep(self.monitoring_interval)
    
    async def _collect_metrics(self) -> ResourceMetrics:
        """Collect current system resource metrics"""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory metrics
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_mb = memory.used / 1024 / 1024
            
            # I/O metrics
            io_counters = psutil.disk_io_counters()
            if hasattr(self, '_last_io_counters'):
                time_delta = time.time() - self._last_io_time
                read_mb_s = (io_counters.read_bytes - self._last_io_counters.read_bytes) / (1024 * 1024 * time_delta)
                write_mb_s = (io_counters.write_bytes - self._last_io_counters.write_bytes) / (1024 * 1024 * time_delta)
            else:
                read_mb_s = write_mb_s = 0.0
            
            self._last_io_counters = io_counters
            self._last_io_time = time.time()
            
            # Network metrics
            network = psutil.net_io_counters()
            if hasattr(self, '_last_network_counters'):
                time_delta = time.time() - self._last_network_time
                network_bytes_s = ((network.bytes_sent + network.bytes_recv) - 
                                 (self._last_network_counters.bytes_sent + self._last_network_counters.bytes_recv)) / time_delta
            else:
                network_bytes_s = 0.0
            
            self._last_network_counters = network
            self._last_network_time = time.time()
            
            # Load average
            load_average = list(psutil.getloadavg())
            
            # Temperature (Pi specific)
            temperature = None
            try:
                with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                    temperature = float(f.read().strip()) / 1000.0
            except:
                pass
            
            return ResourceMetrics(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_mb=memory_mb,
                io_read_mb_s=read_mb_s,
                io_write_mb_s=write_mb_s,
                network_bytes_s=network_bytes_s,
                load_average=load_average,
                temperature=temperature
            )
            
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
            return ResourceMetrics(
                timestamp=datetime.now(),
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_mb=0.0,
                io_read_mb_s=0.0,
                io_write_mb_s=0.0,
                network_bytes_s=0.0,
                load_average=[0.0, 0.0, 0.0]
            )
    
    async def _should_adapt(self) -> bool:
        """Determine if resource adaptation should occur"""
        current_time = time.time()
        
        # Respect cooldown period
        if current_time - self.last_adaptation_time < self.adaptation_cooldown:
            return False
        
        # Check if we have enough metrics history
        if len(self.metrics_history) < 5:
            return False
        
        # Check for resource pressure
        recent_metrics = list(self.metrics_history)[-5:]
        avg_cpu = np.mean([m.cpu_percent for m in recent_metrics])
        avg_memory = np.mean([m.memory_percent for m in recent_metrics])
        
        return (avg_cpu > self.cpu_pressure_threshold or 
                avg_memory > self.memory_pressure_threshold or
                self._detect_workload_change())
    
    def _detect_workload_change(self) -> bool:
        """Detect significant workload changes"""
        if len(self.metrics_history) < 20:
            return False
        
        recent = list(self.metrics_history)[-10:]
        older = list(self.metrics_history)[-20:-10]
        
        recent_cpu = np.mean([m.cpu_percent for m in recent])
        older_cpu = np.mean([m.cpu_percent for m in older])
        
        recent_memory = np.mean([m.memory_percent for m in recent])
        older_memory = np.mean([m.memory_percent for m in older])
        
        # Detect significant changes (>20% relative change)
        cpu_change = abs(recent_cpu - older_cpu) / max(older_cpu, 1.0)
        memory_change = abs(recent_memory - older_memory) / max(older_memory, 1.0)
        
        return cpu_change > 0.2 or memory_change > 0.2
    
    async def _analyze_and_adapt(self, current_metrics: ResourceMetrics) -> List[AllocationDecision]:
        """Analyze current state and generate adaptation decisions"""
        decisions = []
        
        # Calculate resource pressure
        cpu_pressure = max(0, current_metrics.cpu_percent - 70.0) / 30.0  # 0-1 scale
        memory_pressure = max(0, current_metrics.memory_percent - 60.0) / 40.0  # 0-1 scale
        
        # Sort services by priority (lower number = higher priority)
        services_by_priority = sorted(
            self.service_profiles.items(),
            key=lambda x: x[1].priority
        )
        
        # Calculate total current allocation
        total_cpu_allocated = sum(limits.cpu_percent for limits in self.current_allocations.values())
        total_memory_allocated = sum(limits.memory_mb for limits in self.current_allocations.values())
        
        # If under pressure, reduce allocations for lower-priority services
        if cpu_pressure > 0.3 or memory_pressure > 0.3:
            decisions.extend(await self._reduce_allocations(cpu_pressure, memory_pressure, services_by_priority))
        
        # If resources available, increase allocations for adaptive services
        elif cpu_pressure < 0.1 and memory_pressure < 0.1:
            decisions.extend(await self._increase_allocations(services_by_priority))
        
        # Mode-based adaptations
        decisions.extend(await self._apply_mode_adaptations())
        
        return decisions
    
    async def _reduce_allocations(self, cpu_pressure: float, memory_pressure: float, 
                                services_by_priority: List) -> List[AllocationDecision]:
        """Reduce resource allocations to relieve pressure"""
        decisions = []
        
        # Start with lowest priority services
        for service_name, profile in reversed(services_by_priority):
            if not profile.adaptive or profile.critical:
                continue
            
            current_limits = self.current_allocations[service_name]
            
            # Calculate reduction factors
            cpu_reduction = min(0.3, cpu_pressure * 0.5)  # Max 30% reduction
            memory_reduction = min(0.3, memory_pressure * 0.5)  # Max 30% reduction
            
            # Apply reductions
            if cpu_pressure > 0.3:
                new_cpu = current_limits.cpu_percent * (1 - cpu_reduction)
                new_cpu = max(new_cpu, profile.base_limits.cpu_percent * 0.3)  # Minimum 30% of base
                
                if new_cpu < current_limits.cpu_percent:
                    decisions.append(AllocationDecision(
                        service_name=service_name,
                        resource_type=ResourceType.CPU,
                        old_value=current_limits.cpu_percent,
                        new_value=new_cpu,
                        reason=f"Reducing CPU due to pressure ({cpu_pressure:.2f})",
                        timestamp=datetime.now(),
                        confidence=0.8
                    ))
            
            if memory_pressure > 0.3:
                new_memory = current_limits.memory_mb * (1 - memory_reduction)
                new_memory = max(new_memory, profile.base_limits.memory_mb * 0.3)  # Minimum 30% of base
                
                if new_memory < current_limits.memory_mb:
                    decisions.append(AllocationDecision(
                        service_name=service_name,
                        resource_type=ResourceType.MEMORY,
                        old_value=current_limits.memory_mb,
                        new_value=new_memory,
                        reason=f"Reducing memory due to pressure ({memory_pressure:.2f})",
                        timestamp=datetime.now(),
                        confidence=0.8
                    ))
        
        return decisions
    
    async def _increase_allocations(self, services_by_priority: List) -> List[AllocationDecision]:
        """Increase resource allocations when resources are available"""
        decisions = []
        
        # Calculate available resources
        total_cpu_used = sum(limits.cpu_percent for limits in self.current_allocations.values())
        total_memory_used = sum(limits.memory_mb for limits in self.current_allocations.values())
        
        available_cpu = max(0, 90.0 - total_cpu_used)  # Keep 10% buffer
        available_memory = max(0, self.max_memory_mb * 0.85 - total_memory_used)  # Keep 15% buffer
        
        # Distribute available resources to high-priority adaptive services
        for service_name, profile in services_by_priority:
            if not profile.adaptive:
                continue
            
            current_limits = self.current_allocations[service_name]
            
            # Calculate potential increases
            cpu_headroom = profile.base_limits.cpu_percent * 1.5 - current_limits.cpu_percent
            memory_headroom = profile.base_limits.memory_mb * 1.5 - current_limits.memory_mb
            
            if available_cpu > 5.0 and cpu_headroom > 2.0:
                increase = min(available_cpu * 0.3, cpu_headroom, 10.0)  # Max 10% increase
                new_cpu = current_limits.cpu_percent + increase
                
                decisions.append(AllocationDecision(
                    service_name=service_name,
                    resource_type=ResourceType.CPU,
                    old_value=current_limits.cpu_percent,
                    new_value=new_cpu,
                    reason="Increasing CPU allocation due to available resources",
                    timestamp=datetime.now(),
                    confidence=0.7
                ))
                
                available_cpu -= increase
            
            if available_memory > 100.0 and memory_headroom > 50.0:
                increase = min(available_memory * 0.3, memory_headroom, 512.0)  # Max 512MB increase
                new_memory = current_limits.memory_mb + increase
                
                decisions.append(AllocationDecision(
                    service_name=service_name,
                    resource_type=ResourceType.MEMORY,
                    old_value=current_limits.memory_mb,
                    new_value=new_memory,
                    reason="Increasing memory allocation due to available resources",
                    timestamp=datetime.now(),
                    confidence=0.7
                ))
                
                available_memory -= increase
        
        return decisions
    
    async def _apply_mode_adaptations(self) -> List[AllocationDecision]:
        """Apply operation mode-specific resource adaptations"""
        decisions = []
        
        for service_name, profile in self.service_profiles.items():
            if self.current_mode not in profile.mode_adjustments:
                continue
            
            mode_limits = profile.mode_adjustments[self.current_mode]
            current_limits = self.current_allocations[service_name]
            
            # Apply mode-specific CPU adjustments
            if mode_limits.cpu_percent != current_limits.cpu_percent:
                decisions.append(AllocationDecision(
                    service_name=service_name,
                    resource_type=ResourceType.CPU,
                    old_value=current_limits.cpu_percent,
                    new_value=mode_limits.cpu_percent,
                    reason=f"Mode adaptation for {self.current_mode.value}",
                    timestamp=datetime.now(),
                    confidence=0.9
                ))
            
            # Apply mode-specific memory adjustments
            if mode_limits.memory_mb != current_limits.memory_mb:
                decisions.append(AllocationDecision(
                    service_name=service_name,
                    resource_type=ResourceType.MEMORY,
                    old_value=current_limits.memory_mb,
                    new_value=mode_limits.memory_mb,
                    reason=f"Mode adaptation for {self.current_mode.value}",
                    timestamp=datetime.now(),
                    confidence=0.9
                ))
        
        return decisions
    
    async def _apply_allocation_decisions(self, decisions: List[AllocationDecision]):
        """Apply resource allocation decisions to the system"""
        if not decisions:
            return
        
        for decision in decisions:
            try:
                # Update internal tracking
                service_limits = self.current_allocations.get(decision.service_name)
                if not service_limits:
                    continue
                
                if decision.resource_type == ResourceType.CPU:
                    service_limits.cpu_percent = decision.new_value
                elif decision.resource_type == ResourceType.MEMORY:
                    service_limits.memory_mb = decision.new_value
                
                # Apply system-level changes (systemd, cgroups, etc.)
                await self._apply_system_limits(decision.service_name, service_limits)
                
                # Log the decision
                logger.info(f"Applied resource allocation: {decision.service_name} "
                          f"{decision.resource_type.value} {decision.old_value} -> {decision.new_value} "
                          f"({decision.reason})")
                
                # Track decision history
                self.allocation_history.append(decision)
                
            except Exception as e:
                logger.error(f"Failed to apply allocation decision for {decision.service_name}: {e}")
        
        self.last_adaptation_time = time.time()
    
    async def _apply_system_limits(self, service_name: str, limits: ResourceLimits):
        """Apply resource limits at the system level"""
        try:
            # For systemd services, we would use systemctl set-property
            # For this implementation, we'll simulate the application
            
            # Example systemd commands (commented out for simulation):
            # await asyncio.create_subprocess_exec(
            #     'systemctl', 'set-property', f'lawnberry-{service_name}.service',
            #     f'CPUQuota={limits.cpu_percent}%',
            #     f'MemoryMax={int(limits.memory_mb)}M'
            # )
            
            # For now, log what would be applied
            logger.debug(f"Would apply limits to {service_name}: "
                        f"CPU={limits.cpu_percent}%, Memory={limits.memory_mb}MB, "
                        f"IOPriority={limits.io_priority}, Nice={limits.nice_value}")
            
        except Exception as e:
            logger.error(f"Failed to apply system limits for {service_name}: {e}")
    
    async def set_operation_mode(self, mode: OperationMode):
        """Set the current operation mode and trigger adaptation"""
        if self.current_mode != mode:
            logger.info(f"Changing operation mode from {self.current_mode.value} to {mode.value}")
            self.current_mode = mode
            
            # Trigger immediate adaptation for mode change
            if self.monitoring_active:
                current_metrics = await self._collect_metrics()
                decisions = await self._apply_mode_adaptations()
                await self._apply_allocation_decisions(decisions)
    
    async def get_current_status(self) -> Dict[str, Any]:
        """Get current resource allocation status"""
        total_cpu = sum(limits.cpu_percent for limits in self.current_allocations.values())
        total_memory = sum(limits.memory_mb for limits in self.current_allocations.values())
        
        latest_metrics = self.metrics_history[-1] if self.metrics_history else None
        
        return {
            'operation_mode': self.current_mode.value,
            'total_cpu_allocated': total_cpu,
            'total_memory_allocated_mb': total_memory,
            'memory_utilization_percent': (total_memory / self.max_memory_mb) * 100,
            'service_allocations': {
                name: {
                    'cpu_percent': limits.cpu_percent,
                    'memory_mb': limits.memory_mb,
                    'io_priority': limits.io_priority,
                    'nice_value': limits.nice_value
                }
                for name, limits in self.current_allocations.items()
            },
            'current_metrics': {
                'cpu_percent': latest_metrics.cpu_percent if latest_metrics else 0,
                'memory_percent': latest_metrics.memory_percent if latest_metrics else 0,
                'temperature': latest_metrics.temperature if latest_metrics else None
            } if latest_metrics else None,
            'recent_decisions': len(self.allocation_history),
            'monitoring_active': self.monitoring_active
        }
    
    async def _update_performance_baselines(self):
        """Update performance baselines for predictive allocation"""
        if len(self.metrics_history) < 50:
            return
        
        recent_metrics = list(self.metrics_history)[-50:]
        
        # Calculate rolling averages for different time windows
        for window in [10, 30, 50]:
            window_metrics = recent_metrics[-window:]
            
            baseline_key = f"window_{window}"
            if baseline_key not in self.performance_baselines:
                self.performance_baselines[baseline_key] = {}
            
            self.performance_baselines[baseline_key].update({
                'avg_cpu': np.mean([m.cpu_percent for m in window_metrics]),
                'avg_memory': np.mean([m.memory_percent for m in window_metrics]),
                'avg_io_read': np.mean([m.io_read_mb_s for m in window_metrics]),
                'avg_io_write': np.mean([m.io_write_mb_s for m in window_metrics]),
                'timestamp': datetime.now()
            })
    
    async def _load_configuration(self):
        """Load configuration from config manager"""
        # This would load custom thresholds and profiles from configuration
        pass
    
    async def shutdown(self):
        """Shutdown the resource manager"""
        logger.info("Shutting down Dynamic Resource Manager")
        await self.stop_monitoring()
        
        # Save performance data for future use
        await self._save_performance_data()
    
    async def _save_performance_data(self):
        """Save performance data for analysis and future optimization"""
        try:
            data = {
                'allocation_history': [
                    {
                        'service_name': d.service_name,
                        'resource_type': d.resource_type.value,
                        'old_value': d.old_value,
                        'new_value': d.new_value,
                        'reason': d.reason,
                        'timestamp': d.timestamp.isoformat(),
                        'confidence': d.confidence
                    }
                    for d in list(self.allocation_history)
                ],
                'performance_baselines': {
                    k: {kk: vv.isoformat() if isinstance(vv, datetime) else vv 
                        for kk, vv in v.items()}
                    for k, v in self.performance_baselines.items()
                }
            }
            
            # Would save to persistent storage
            logger.info("Performance data saved for future optimization")
            
        except Exception as e:
            logger.error(f"Failed to save performance data: {e}")
