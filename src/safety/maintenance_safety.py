"""
Maintenance Safety System
Implements blade wear detection, battery safety monitoring, and maintenance safety lockouts
"""

import asyncio
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from ..communication import MessageProtocol, MQTTClient
from .access_control import SafetyAccessController, SafetyAccessLevel

logger = logging.getLogger(__name__)


class MaintenanceStatus(Enum):
    """Maintenance status levels"""

    OPTIMAL = "optimal"
    GOOD = "good"
    ATTENTION_NEEDED = "attention_needed"
    MAINTENANCE_REQUIRED = "maintenance_required"
    CRITICAL = "critical"
    FAILED = "failed"


class BladeCondition(Enum):
    """Blade condition assessment"""

    SHARP = "sharp"
    SLIGHTLY_DULL = "slightly_dull"
    DULL = "dull"
    VERY_DULL = "very_dull"
    DAMAGED = "damaged"
    MISSING = "missing"


class BatteryHealthStatus(Enum):
    """Battery health status"""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"
    FAILED = "failed"


class MaintenanceLockoutType(Enum):
    """Types of maintenance lockouts"""

    BLADE_SAFETY = "blade_safety"
    BATTERY_SAFETY = "battery_safety"
    SENSOR_FAILURE = "sensor_failure"
    MECHANICAL_ISSUE = "mechanical_issue"
    SCHEDULED_MAINTENANCE = "scheduled_maintenance"
    DIAGNOSTIC_FAILURE = "diagnostic_failure"


@dataclass
class BladeWearData:
    """Blade wear assessment data"""

    blade_id: str
    condition: BladeCondition
    sharpness_score: float  # 0.0 to 1.0, higher is sharper
    wear_percentage: float  # 0.0 to 100.0
    vibration_level: float  # Abnormal vibration indicator
    cutting_efficiency: float  # 0.0 to 1.0
    estimated_remaining_hours: float
    replacement_recommended: bool
    safety_concern: bool
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class BatteryHealthData:
    """Battery health monitoring data"""

    battery_id: str
    health_status: BatteryHealthStatus
    capacity_percentage: float  # Current capacity vs original
    voltage: float
    current: float
    temperature: float
    charge_cycles: int
    degradation_rate: float  # Capacity loss per cycle
    estimated_remaining_life_days: float
    safety_concerns: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MaintenanceLockout:
    """Maintenance safety lockout"""

    lockout_id: str
    lockout_type: MaintenanceLockoutType
    severity: MaintenanceStatus
    description: str
    affected_systems: List[str]
    required_access_level: SafetyAccessLevel
    override_possible: bool
    created_at: datetime
    expires_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None


@dataclass
class DiagnosticResult:
    """System diagnostic result"""

    test_id: str
    test_name: str
    status: MaintenanceStatus
    result_data: Dict[str, Any]
    issues_found: List[str]
    recommendations: List[str]
    safety_impact: bool
    timestamp: datetime = field(default_factory=datetime.now)


class MaintenanceSafetySystem:
    """Comprehensive maintenance safety monitoring system"""

    def __init__(
        self,
        mqtt_client: MQTTClient,
        access_controller: SafetyAccessController,
        config: Dict[str, Any],
    ):
        self.mqtt_client = mqtt_client
        self.access_controller = access_controller
        self.config = config
        # Startup grace period to avoid premature lockouts when metrics aren't available yet
        self.startup_grace_seconds: float = float(self.config.get("startup_grace_seconds", 180.0))
        self._start_time: datetime = datetime.now()
        self.allow_missing_data: bool = bool(
            self.config.get("allow_missing_data_during_warmup", True)
        )

        # Safety thresholds
        self.blade_wear_threshold = config.get("blade_wear_threshold", 70.0)  # Percentage
        self.battery_capacity_threshold = config.get(
            "battery_capacity_threshold", 80.0
        )  # Percentage
        self.battery_temp_max = config.get("battery_temp_max", 45.0)  # Celsius
        self.vibration_threshold = config.get("vibration_threshold", 2.0)  # G-force

        # Component monitoring
        self.blade_data: Dict[str, BladeWearData] = {}
        self.battery_data: Dict[str, BatteryHealthData] = {}
        self.active_lockouts: Dict[str, MaintenanceLockout] = {}
        self.diagnostic_history: List[DiagnosticResult] = []

        # Sensor data for analysis
        self.motor_current_history: List[Tuple[datetime, float]] = []
        self.vibration_history: List[Tuple[datetime, float]] = []
        self.battery_voltage_history: List[Tuple[datetime, float]] = []
        self.temperature_history: List[Tuple[datetime, float]] = []

        # Analysis parameters
        self.analysis_window_minutes = 10
        self.diagnostic_frequency_hours = 6
        self.last_full_diagnostic = datetime.now() - timedelta(hours=24)

        # Maintenance scheduling
        self.maintenance_schedule = self._initialize_maintenance_schedule()
        self.maintenance_reminders: List[Dict[str, Any]] = []

        # Callbacks
        self.blade_callbacks: List[Callable] = []
        self.battery_callbacks: List[Callable] = []
        self.lockout_callbacks: List[Callable] = []
        self.diagnostic_callbacks: List[Callable] = []

        # Tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._diagnostic_task: Optional[asyncio.Task] = None
        self._maintenance_task: Optional[asyncio.Task] = None
        self._running = False

    def _initialize_maintenance_schedule(self) -> Dict[str, Dict[str, Any]]:
        """Initialize maintenance schedule"""
        return {
            "blade_inspection": {
                "frequency_hours": 50,
                "last_performed": datetime.now() - timedelta(hours=40),
                "description": "Visual blade inspection and sharpness test",
                "required_access_level": SafetyAccessLevel.BASIC,
            },
            "blade_replacement": {
                "frequency_hours": 200,
                "last_performed": datetime.now() - timedelta(hours=150),
                "description": "Replace mower blades",
                "required_access_level": SafetyAccessLevel.ADVANCED,
            },
            "battery_health_check": {
                "frequency_hours": 100,
                "last_performed": datetime.now() - timedelta(hours=80),
                "description": "Comprehensive battery health assessment",
                "required_access_level": SafetyAccessLevel.BASIC,
            },
            "system_diagnostic": {
                "frequency_hours": 168,  # Weekly
                "last_performed": self.last_full_diagnostic,
                "description": "Full system diagnostic and safety validation",
                "required_access_level": SafetyAccessLevel.TECHNICIAN,
            },
            "sensor_calibration": {
                "frequency_hours": 336,  # Bi-weekly
                "last_performed": datetime.now() - timedelta(hours=300),
                "description": "Calibrate all safety sensors",
                "required_access_level": SafetyAccessLevel.TECHNICIAN,
            },
            "deep_cleaning": {
                "frequency_hours": 168,  # Weekly
                "last_performed": datetime.now() - timedelta(hours=100),
                "description": "Deep clean mower deck and components",
                "required_access_level": SafetyAccessLevel.BASIC,
            },
        }

    async def start(self):
        """Start maintenance safety system"""
        logger.info("Starting maintenance safety system")
        self._running = True

        # Subscribe to sensor data
        await self._subscribe_to_sensors()

        # Start monitoring tasks
        self._monitoring_task = asyncio.create_task(self._maintenance_monitoring_loop())
        self._diagnostic_task = asyncio.create_task(self._diagnostic_loop())
        self._maintenance_task = asyncio.create_task(self._maintenance_scheduling_loop())

    async def stop(self):
        """Stop maintenance safety system"""
        logger.info("Stopping maintenance safety system")
        self._running = False

        for task in [self._monitoring_task, self._diagnostic_task, self._maintenance_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _subscribe_to_sensors(self):
        """Subscribe to sensor data for maintenance monitoring using separate handler registration and namespaced topics"""

        async def _wrap(handler: Callable, topic: str, message):
            try:
                if hasattr(message, "payload"):
                    payload = message.payload
                else:
                    payload = message if isinstance(message, dict) else {}
                await handler(payload)
            except Exception as e:
                logger.error(f"MaintenanceSafety handler error for {topic}: {e}")

        # Motor current (map to power data if available)
        motor_topic = "lawnberry/sensors/power/data"
        await self.mqtt_client.subscribe(motor_topic)
        self.mqtt_client.add_message_handler(
            motor_topic, lambda t, m: _wrap(self._handle_motor_current, t, m)
        )

        # Vibration data (if published by a sensor service under sensors/vibration)
        vib_topic = "lawnberry/sensors/vibration"
        await self.mqtt_client.subscribe(vib_topic)
        self.mqtt_client.add_message_handler(
            vib_topic, lambda t, m: _wrap(self._handle_vibration_data, t, m)
        )

        # Battery/status maps to sensors/power/data, already subscribed above; still listen to a named status topic if present
        batt_topic = "lawnberry/system/power/status"
        await self.mqtt_client.subscribe(batt_topic)
        self.mqtt_client.add_message_handler(
            batt_topic, lambda t, m: _wrap(self._handle_battery_data, t, m)
        )

        # Temperature readings typically come from environmental data
        temp_topic = "lawnberry/sensors/environmental/data"
        await self.mqtt_client.subscribe(temp_topic)
        self.mqtt_client.add_message_handler(
            temp_topic, lambda t, m: _wrap(self._handle_temperature_data, t, m)
        )

        # Maintenance commands
        cmd_topic = "lawnberry/maintenance/command"
        await self.mqtt_client.subscribe(cmd_topic)
        self.mqtt_client.add_message_handler(
            cmd_topic, lambda t, m: _wrap(self._handle_maintenance_command, t, m)
        )

    async def _handle_motor_current(self, data: Dict[str, Any]):
        """Handle motor current data for blade wear analysis"""
        current = data.get("current", 0.0)
        timestamp = datetime.now()

        self.motor_current_history.append((timestamp, current))

        # Maintain history size
        cutoff_time = timestamp - timedelta(minutes=self.analysis_window_minutes)
        self.motor_current_history = [
            (t, c) for t, c in self.motor_current_history if t > cutoff_time
        ]

        # Analyze blade condition if enough data
        if len(self.motor_current_history) > 20:
            await self._analyze_blade_condition()

    async def _handle_vibration_data(self, data: Dict[str, Any]):
        """Handle vibration data for mechanical health analysis"""
        vibration = data.get("magnitude", 0.0)
        timestamp = datetime.now()

        self.vibration_history.append((timestamp, vibration))

        # Maintain history size
        cutoff_time = timestamp - timedelta(minutes=self.analysis_window_minutes)
        self.vibration_history = [(t, v) for t, v in self.vibration_history if t > cutoff_time]

        # Check for excessive vibration
        if vibration > self.vibration_threshold:
            await self._handle_excessive_vibration(vibration)

    async def _handle_battery_data(self, data: Dict[str, Any]):
        """Handle battery data for health monitoring"""
        battery_id = data.get("battery_id", "main")
        voltage = data.get("voltage", 0.0)
        current = data.get("current", 0.0)
        temperature = data.get("temperature", 20.0)
        capacity = data.get("capacity_percentage", 100.0)

        timestamp = datetime.now()
        self.battery_voltage_history.append((timestamp, voltage))
        self.temperature_history.append((timestamp, temperature))

        # Maintain history size
        cutoff_time = timestamp - timedelta(minutes=self.analysis_window_minutes)
        self.battery_voltage_history = [
            (t, v) for t, v in self.battery_voltage_history if t > cutoff_time
        ]
        self.temperature_history = [
            (t, temp) for t, temp in self.temperature_history if t > cutoff_time
        ]

        # Analyze battery health
        await self._analyze_battery_health(battery_id, data)

    async def _handle_temperature_data(self, data: Dict[str, Any]):
        """Handle temperature data for thermal monitoring"""
        temperature = data.get("temperature", 20.0)
        component = data.get("component", "system")

        # Check for overheating
        if temperature > self.battery_temp_max and component == "battery":
            await self._handle_battery_overheating(temperature)

    async def _handle_maintenance_command(self, data: Dict[str, Any]):
        """Handle maintenance commands"""
        command = data.get("command")
        user = data.get("user", "system")

        if command == "override_lockout":
            lockout_id = data.get("lockout_id")
            await self._handle_lockout_override(lockout_id, user)
        elif command == "schedule_maintenance":
            maintenance_type = data.get("type")
            await self._schedule_maintenance(maintenance_type, user)
        elif command == "run_diagnostic":
            diagnostic_type = data.get("diagnostic_type", "full")
            await self._run_diagnostic(diagnostic_type, user)

    async def _analyze_blade_condition(self):
        """Analyze blade condition from motor current data"""
        if not self.motor_current_history:
            return

        # Extract current values from history
        currents = [current for _, current in self.motor_current_history]

        # Calculate statistics
        avg_current = statistics.mean(currents)
        current_std = statistics.stdev(currents) if len(currents) > 1 else 0
        max_current = max(currents)

        # Analyze cutting efficiency based on current patterns
        # Higher current typically indicates duller blades or more resistance
        baseline_current = 2.0  # Assume 2A baseline for sharp blades

        # Calculate blade metrics
        sharpness_score = max(0.0, min(1.0, baseline_current / max(avg_current, 0.1)))
        wear_percentage = min(100.0, ((avg_current - baseline_current) / baseline_current) * 100)
        cutting_efficiency = sharpness_score

        # Determine condition
        if wear_percentage > 80:
            condition = BladeCondition.VERY_DULL
        elif wear_percentage > 60:
            condition = BladeCondition.DULL
        elif wear_percentage > 40:
            condition = BladeCondition.SLIGHTLY_DULL
        elif wear_percentage < 10:
            condition = BladeCondition.SHARP
        else:
            condition = BladeCondition.SLIGHTLY_DULL

        # Check vibration correlation
        vibration_level = 0.0
        if self.vibration_history:
            recent_vibrations = [v for _, v in self.vibration_history[-10:]]
            vibration_level = statistics.mean(recent_vibrations)

        # Estimate remaining hours (simplified calculation)
        if wear_percentage > 0:
            estimated_remaining_hours = max(
                0, (100 - wear_percentage) * 2
            )  # 2 hours per percentage point
        else:
            estimated_remaining_hours = 200  # Default for sharp blades

        # Determine if replacement is recommended
        replacement_recommended = wear_percentage > self.blade_wear_threshold
        safety_concern = wear_percentage > 85 or vibration_level > self.vibration_threshold

        blade_data = BladeWearData(
            blade_id="main_blade",
            condition=condition,
            sharpness_score=sharpness_score,
            wear_percentage=wear_percentage,
            vibration_level=vibration_level,
            cutting_efficiency=cutting_efficiency,
            estimated_remaining_hours=estimated_remaining_hours,
            replacement_recommended=replacement_recommended,
            safety_concern=safety_concern,
        )

        # Store blade data
        self.blade_data["main_blade"] = blade_data

        # Check for safety concerns
        if safety_concern:
            await self._create_blade_safety_lockout(blade_data)

        # Trigger callbacks
        for callback in self.blade_callbacks:
            try:
                await callback(blade_data)
            except Exception as e:
                logger.error(f"Error in blade callback: {e}")

        # Publish blade data
        await self.mqtt_client.publish(
            "lawnberry/maintenance/blade_status",
            {
                "blade_id": blade_data.blade_id,
                "condition": blade_data.condition.value,
                "wear_percentage": blade_data.wear_percentage,
                "sharpness_score": blade_data.sharpness_score,
                "replacement_recommended": blade_data.replacement_recommended,
                "safety_concern": blade_data.safety_concern,
                "timestamp": blade_data.timestamp.isoformat(),
            },
        )

        logger.debug(
            f"Blade analysis: {condition.value}, wear: {wear_percentage:.1f}%, efficiency: {cutting_efficiency:.2f}"
        )

    async def _analyze_battery_health(self, battery_id: str, data: Dict[str, Any]):
        """Analyze battery health from monitoring data"""
        voltage = data.get("voltage", 0.0)
        current = data.get("current", 0.0)
        temperature = data.get("temperature", 20.0)
        capacity_percentage = data.get("capacity_percentage", 100.0)
        charge_cycles = data.get("charge_cycles", 0)

        # Determine health status based on capacity
        if capacity_percentage > 90:
            health_status = BatteryHealthStatus.EXCELLENT
        elif capacity_percentage > 80:
            health_status = BatteryHealthStatus.GOOD
        elif capacity_percentage > 70:
            health_status = BatteryHealthStatus.FAIR
        elif capacity_percentage > 50:
            health_status = BatteryHealthStatus.POOR
        elif capacity_percentage > 20:
            health_status = BatteryHealthStatus.CRITICAL
        else:
            health_status = BatteryHealthStatus.FAILED

        # Calculate degradation rate (simplified)
        if charge_cycles > 0:
            degradation_rate = (100 - capacity_percentage) / charge_cycles
        else:
            degradation_rate = 0.0

        # Estimate remaining life
        if degradation_rate > 0:
            cycles_to_failure = (capacity_percentage - 20) / degradation_rate  # 20% minimum
            estimated_remaining_life_days = cycles_to_failure * 2  # Assume 1 cycle every 2 days
        else:
            estimated_remaining_life_days = 365 * 5  # 5 years for new battery

        # Check for safety concerns
        safety_concerns = []
        if temperature > self.battery_temp_max:
            safety_concerns.append("overheating")
        if voltage < 10.0:  # Assuming 12V system
            safety_concerns.append("low_voltage")
        if capacity_percentage < 30:
            safety_concerns.append("low_capacity")
        if temperature < -10:
            safety_concerns.append("too_cold")

        battery_health = BatteryHealthData(
            battery_id=battery_id,
            health_status=health_status,
            capacity_percentage=capacity_percentage,
            voltage=voltage,
            current=current,
            temperature=temperature,
            charge_cycles=charge_cycles,
            degradation_rate=degradation_rate,
            estimated_remaining_life_days=estimated_remaining_life_days,
            safety_concerns=safety_concerns,
        )

        # Store battery data
        self.battery_data[battery_id] = battery_health

        # Check for safety concerns
        if safety_concerns:
            await self._create_battery_safety_lockout(battery_health)

        # Trigger callbacks
        for callback in self.battery_callbacks:
            try:
                await callback(battery_health)
            except Exception as e:
                logger.error(f"Error in battery callback: {e}")

        # Publish battery data
        await self.mqtt_client.publish(
            "lawnberry/maintenance/battery_status",
            {
                "battery_id": battery_id,
                "health_status": health_status.value,
                "capacity_percentage": capacity_percentage,
                "temperature": temperature,
                "safety_concerns": safety_concerns,
                "estimated_remaining_life_days": estimated_remaining_life_days,
                "timestamp": battery_health.timestamp.isoformat(),
            },
        )

        logger.debug(f"Battery health: {health_status.value}, capacity: {capacity_percentage:.1f}%")

    async def _handle_excessive_vibration(self, vibration: float):
        """Handle excessive vibration detection"""
        logger.warning(f"Excessive vibration detected: {vibration:.2f}g")

        # Create diagnostic result for vibration issue
        diagnostic = DiagnosticResult(
            test_id=f"vibration_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            test_name="Vibration Analysis",
            status=MaintenanceStatus.ATTENTION_NEEDED
            if vibration < 3.0
            else MaintenanceStatus.CRITICAL,
            result_data={"vibration_level": vibration, "threshold": self.vibration_threshold},
            issues_found=[
                f"Excessive vibration: {vibration:.2f}g (threshold: {self.vibration_threshold}g)"
            ],
            recommendations=[
                "Check blade balance",
                "Inspect blade for damage",
                "Check motor mount",
            ],
            safety_impact=True,
        )

        self.diagnostic_history.append(diagnostic)

        # Create lockout if critical
        if vibration > 3.0:
            await self._create_mechanical_safety_lockout(
                "excessive_vibration", f"Excessive vibration: {vibration:.2f}g"
            )

    async def _handle_battery_overheating(self, temperature: float):
        """Handle battery overheating"""
        logger.critical(f"Battery overheating detected: {temperature:.1f}°C")

        # Create immediate safety lockout
        await self._create_battery_safety_lockout_direct(
            "overheating", f"Battery temperature: {temperature:.1f}°C"
        )

    async def _create_blade_safety_lockout(self, blade_data: BladeWearData):
        """Create blade safety lockout"""
        lockout_id = f"blade_safety_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        severity = MaintenanceStatus.ATTENTION_NEEDED
        if blade_data.wear_percentage > 90:
            severity = MaintenanceStatus.CRITICAL
        elif blade_data.wear_percentage > 80:
            severity = MaintenanceStatus.MAINTENANCE_REQUIRED

        description = f"Blade safety concern: {blade_data.condition.value}, {blade_data.wear_percentage:.1f}% wear"
        if blade_data.vibration_level > self.vibration_threshold:
            description += f", excessive vibration: {blade_data.vibration_level:.2f}g"

        lockout = MaintenanceLockout(
            lockout_id=lockout_id,
            lockout_type=MaintenanceLockoutType.BLADE_SAFETY,
            severity=severity,
            description=description,
            affected_systems=["mowing", "blade_motor"],
            required_access_level=SafetyAccessLevel.ADVANCED,
            override_possible=blade_data.wear_percentage < 95,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=24)
            if severity != MaintenanceStatus.CRITICAL
            else None,
        )

        await self._activate_lockout(lockout)

    async def _create_battery_safety_lockout(self, battery_data: BatteryHealthData):
        """Create battery safety lockout"""
        lockout_id = f"battery_safety_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        severity = MaintenanceStatus.ATTENTION_NEEDED
        if "overheating" in battery_data.safety_concerns or battery_data.capacity_percentage < 30:
            severity = MaintenanceStatus.CRITICAL
        elif battery_data.health_status in [BatteryHealthStatus.POOR, BatteryHealthStatus.CRITICAL]:
            severity = MaintenanceStatus.MAINTENANCE_REQUIRED

        description = f"Battery safety concerns: {', '.join(battery_data.safety_concerns)}"

        lockout = MaintenanceLockout(
            lockout_id=lockout_id,
            lockout_type=MaintenanceLockoutType.BATTERY_SAFETY,
            severity=severity,
            description=description,
            affected_systems=["power", "charging"],
            required_access_level=SafetyAccessLevel.TECHNICIAN
            if "overheating" in battery_data.safety_concerns
            else SafetyAccessLevel.ADVANCED,
            override_possible=severity != MaintenanceStatus.CRITICAL,
            created_at=datetime.now(),
        )

        await self._activate_lockout(lockout)

    async def _create_battery_safety_lockout_direct(self, _concern: str, description: str):
        """Create direct battery safety lockout"""
        lockout_id = f"battery_emergency_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        lockout = MaintenanceLockout(
            lockout_id=lockout_id,
            lockout_type=MaintenanceLockoutType.BATTERY_SAFETY,
            severity=MaintenanceStatus.CRITICAL,
            description=description,
            affected_systems=["power", "charging", "all_operations"],
            required_access_level=SafetyAccessLevel.TECHNICIAN,
            override_possible=False,
            created_at=datetime.now(),
        )

        await self._activate_lockout(lockout)

    async def _create_mechanical_safety_lockout(self, issue_type: str, description: str):
        """Create mechanical safety lockout"""
        lockout_id = f"mechanical_{issue_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        lockout = MaintenanceLockout(
            lockout_id=lockout_id,
            lockout_type=MaintenanceLockoutType.MECHANICAL_ISSUE,
            severity=MaintenanceStatus.CRITICAL,
            description=description,
            affected_systems=["mowing", "navigation"],
            required_access_level=SafetyAccessLevel.TECHNICIAN,
            override_possible=True,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1),
        )

        await self._activate_lockout(lockout)

    async def _activate_lockout(self, lockout: MaintenanceLockout):
        """Activate a maintenance lockout"""
        self.active_lockouts[lockout.lockout_id] = lockout

        # Trigger callbacks
        for callback in self.lockout_callbacks:
            try:
                await callback(lockout)
            except Exception as e:
                logger.error(f"Error in lockout callback: {e}")

        # Publish lockout
        await self.mqtt_client.publish(
            "lawnberry/maintenance/lockout_activated",
            {
                "lockout_id": lockout.lockout_id,
                "type": lockout.lockout_type.value,
                "severity": lockout.severity.value,
                "description": lockout.description,
                "affected_systems": lockout.affected_systems,
                "override_possible": lockout.override_possible,
                "timestamp": lockout.created_at.isoformat(),
            },
        )

        logger.warning(f"Maintenance lockout activated: {lockout.description}")

    async def _handle_lockout_override(self, lockout_id: str, user: str):
        """Handle lockout override request"""
        if lockout_id not in self.active_lockouts:
            logger.warning(f"Lockout override requested for non-existent lockout: {lockout_id}")
            return

        lockout = self.active_lockouts[lockout_id]

        # Check if override is possible
        if not lockout.override_possible:
            logger.warning(f"Override not possible for lockout: {lockout_id}")
            await self.mqtt_client.publish(
                "lawnberry/maintenance/override_denied",
                {
                    "lockout_id": lockout_id,
                    "reason": "override_not_permitted",
                    "user": user,
                    "timestamp": datetime.now().isoformat(),
                },
            )
            return

        # Check user access level
        user_has_access = await self.access_controller.check_feature_access(
            user, f"override_{lockout.lockout_type.value}"
        )

        if not user_has_access:
            logger.warning(f"User {user} does not have access to override lockout {lockout_id}")
            await self.mqtt_client.publish(
                "lawnberry/maintenance/override_denied",
                {
                    "lockout_id": lockout_id,
                    "reason": "insufficient_access_level",
                    "user": user,
                    "timestamp": datetime.now().isoformat(),
                },
            )
            return

        # Perform override
        lockout.resolved_at = datetime.now()
        lockout.resolved_by = user
        del self.active_lockouts[lockout_id]

        # Log safety violation for override
        await self.access_controller.record_safety_violation(
            user, "maintenance_override", f"Override of maintenance lockout: {lockout.description}"
        )

        await self.mqtt_client.publish(
            "lawnberry/maintenance/lockout_overridden",
            {"lockout_id": lockout_id, "user": user, "timestamp": datetime.now().isoformat()},
        )

        logger.warning(f"Maintenance lockout overridden by {user}: {lockout_id}")

    async def _maintenance_monitoring_loop(self):
        """Main maintenance monitoring loop"""
        while self._running:
            try:
                # Check for expired lockouts
                current_time = datetime.now()
                expired_lockouts = []

                for lockout_id, lockout in self.active_lockouts.items():
                    if lockout.expires_at and lockout.expires_at < current_time:
                        expired_lockouts.append(lockout_id)

                # Remove expired lockouts
                for lockout_id in expired_lockouts:
                    lockout = self.active_lockouts[lockout_id]
                    lockout.resolved_at = current_time
                    del self.active_lockouts[lockout_id]

                    await self.mqtt_client.publish(
                        "lawnberry/maintenance/lockout_expired",
                        {"lockout_id": lockout_id, "timestamp": current_time.isoformat()},
                    )

                    logger.info(f"Maintenance lockout expired: {lockout_id}")

                await asyncio.sleep(60.0)  # Check every minute

            except Exception as e:
                logger.error(f"Error in maintenance monitoring loop: {e}")
                await asyncio.sleep(60.0)

    async def _diagnostic_loop(self):
        """Periodic diagnostic loop"""
        while self._running:
            try:
                current_time = datetime.now()
                time_since_diagnostic = current_time - self.last_full_diagnostic

                # Run full diagnostic every 6 hours
                if time_since_diagnostic.total_seconds() > self.diagnostic_frequency_hours * 3600:
                    await self._run_diagnostic("full", "system")
                    self.last_full_diagnostic = current_time

                await asyncio.sleep(3600.0)  # Check every hour

            except Exception as e:
                logger.error(f"Error in diagnostic loop: {e}")
                await asyncio.sleep(3600.0)

    async def _maintenance_scheduling_loop(self):
        """Maintenance scheduling loop"""
        while self._running:
            try:
                current_time = datetime.now()

                # Check maintenance schedule
                for maintenance_type, schedule in self.maintenance_schedule.items():
                    time_since_last = current_time - schedule["last_performed"]
                    frequency_hours = schedule["frequency_hours"]

                    if time_since_last.total_seconds() > frequency_hours * 3600:
                        await self._schedule_maintenance_reminder(maintenance_type, schedule)

                await asyncio.sleep(3600.0)  # Check every hour

            except Exception as e:
                logger.error(f"Error in maintenance scheduling loop: {e}")
                await asyncio.sleep(3600.0)

    async def _run_diagnostic(self, diagnostic_type: str, user: str):
        """Run system diagnostic"""
        logger.info(f"Running {diagnostic_type} diagnostic requested by {user}")

        diagnostic_tests = []

        if diagnostic_type in ["full", "blade"]:
            diagnostic_tests.append(await self._diagnostic_blade_system())

        if diagnostic_type in ["full", "battery"]:
            diagnostic_tests.append(await self._diagnostic_battery_system())

        if diagnostic_type in ["full", "sensors"]:
            diagnostic_tests.append(await self._diagnostic_sensor_system())

        if diagnostic_type in ["full", "mechanical"]:
            diagnostic_tests.append(await self._diagnostic_mechanical_system())

        # Process diagnostic results
        for diagnostic in diagnostic_tests:
            if diagnostic:
                self.diagnostic_history.append(diagnostic)

                # Trigger callbacks
                for callback in self.diagnostic_callbacks:
                    try:
                        await callback(diagnostic)
                    except Exception as e:
                        logger.error(f"Error in diagnostic callback: {e}")

                # Create lockouts for critical issues
                if diagnostic.status == MaintenanceStatus.CRITICAL and diagnostic.safety_impact:
                    await self._create_diagnostic_lockout(diagnostic)

        # Maintain diagnostic history size
        if len(self.diagnostic_history) > 100:
            self.diagnostic_history = self.diagnostic_history[-100:]

        logger.info(
            f"Completed {diagnostic_type} diagnostic: {len(diagnostic_tests)} tests performed"
        )

    async def _diagnostic_blade_system(self) -> DiagnosticResult:
        """Diagnostic test for blade system"""
        issues = []
        recommendations = []
        safety_impact = False

        # Check current blade data
        if "main_blade" in self.blade_data:
            blade_data = self.blade_data["main_blade"]

            if blade_data.wear_percentage > 80:
                issues.append(f"High blade wear: {blade_data.wear_percentage:.1f}%")
                recommendations.append("Replace blades")
                safety_impact = True

            if blade_data.vibration_level > self.vibration_threshold:
                issues.append(f"Excessive vibration: {blade_data.vibration_level:.2f}g")
                recommendations.append("Check blade balance and mounting")
                safety_impact = True

            if blade_data.cutting_efficiency < 0.7:
                issues.append(f"Poor cutting efficiency: {blade_data.cutting_efficiency:.2f}")
                recommendations.append("Sharpen or replace blades")
        else:
            issues.append("No blade data available")
            recommendations.append("Run blade analysis test")

        # Determine status
        if safety_impact:
            status = MaintenanceStatus.CRITICAL
        elif issues:
            status = MaintenanceStatus.ATTENTION_NEEDED
        else:
            status = MaintenanceStatus.OPTIMAL

        return DiagnosticResult(
            test_id=f"blade_diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            test_name="Blade System Diagnostic",
            status=status,
            result_data={"blade_count": len(self.blade_data)},
            issues_found=issues,
            recommendations=recommendations,
            safety_impact=safety_impact,
        )

    async def _diagnostic_battery_system(self) -> DiagnosticResult:
        """Diagnostic test for battery system"""
        issues = []
        recommendations = []
        safety_impact = False

        # Check battery data
        for battery_id, battery_data in self.battery_data.items():
            if battery_data.capacity_percentage < 70:
                issues.append(
                    f"Battery {battery_id} low capacity: {battery_data.capacity_percentage:.1f}%"
                )
                recommendations.append(f"Consider replacing battery {battery_id}")

                if battery_data.capacity_percentage < 30:
                    safety_impact = True

            if battery_data.safety_concerns:
                issues.append(
                    f"Battery {battery_id} safety concerns: {', '.join(battery_data.safety_concerns)}"
                )
                recommendations.append(f"Address battery {battery_id} safety issues immediately")
                safety_impact = True

        if not self.battery_data:
            issues.append("No battery data available")
            recommendations.append("Check battery monitoring system")

        # Determine status
        if safety_impact:
            status = MaintenanceStatus.CRITICAL
        elif issues:
            status = MaintenanceStatus.ATTENTION_NEEDED
        else:
            status = MaintenanceStatus.OPTIMAL

        return DiagnosticResult(
            test_id=f"battery_diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            test_name="Battery System Diagnostic",
            status=status,
            result_data={"battery_count": len(self.battery_data)},
            issues_found=issues,
            recommendations=recommendations,
            safety_impact=safety_impact,
        )

    async def _diagnostic_sensor_system(self) -> DiagnosticResult:
        """Diagnostic test for sensor system"""
        issues = []
        recommendations = []
        safety_impact = False
        in_warmup = (datetime.now() - self._start_time).total_seconds() < self.startup_grace_seconds

        # Check sensor data availability
        if not self.motor_current_history:
            issues.append("No motor current data")
            recommendations.append("Check motor current sensor")
            # Treat missing data as non-critical during warmup if allowed
            if not (in_warmup and self.allow_missing_data):
                safety_impact = True

        if not self.vibration_history:
            issues.append("No vibration data")
            recommendations.append("Check vibration sensor")

        if not self.battery_voltage_history:
            issues.append("No battery voltage data")
            recommendations.append("Check battery monitoring system")
            if not (in_warmup and self.allow_missing_data):
                safety_impact = True

        # Determine status
        if safety_impact:
            status = MaintenanceStatus.CRITICAL
        elif issues:
            status = MaintenanceStatus.ATTENTION_NEEDED
        else:
            status = MaintenanceStatus.OPTIMAL

        return DiagnosticResult(
            test_id=f"sensor_diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            test_name="Sensor System Diagnostic",
            status=status,
            result_data={
                "motor_current_samples": len(self.motor_current_history),
                "vibration_samples": len(self.vibration_history),
                "battery_voltage_samples": len(self.battery_voltage_history),
            },
            issues_found=issues,
            recommendations=recommendations,
            safety_impact=safety_impact,
        )

    async def _diagnostic_mechanical_system(self) -> DiagnosticResult:
        """Diagnostic test for mechanical system"""
        issues = []
        recommendations = []
        safety_impact = False

        # Check vibration levels
        if self.vibration_history:
            recent_vibrations = [v for _, v in self.vibration_history[-20:]]
            avg_vibration = statistics.mean(recent_vibrations)

            if avg_vibration > self.vibration_threshold:
                issues.append(f"High average vibration: {avg_vibration:.2f}g")
                recommendations.append("Inspect mechanical components for wear or damage")
                safety_impact = True

        # Check for mechanical lockouts
        mechanical_lockouts = [
            lockout
            for lockout in self.active_lockouts.values()
            if lockout.lockout_type == MaintenanceLockoutType.MECHANICAL_ISSUE
        ]

        if mechanical_lockouts:
            issues.extend([lockout.description for lockout in mechanical_lockouts])
            recommendations.append("Resolve active mechanical lockouts")
            safety_impact = True

        # Determine status
        if safety_impact:
            status = MaintenanceStatus.CRITICAL
        elif issues:
            status = MaintenanceStatus.ATTENTION_NEEDED
        else:
            status = MaintenanceStatus.OPTIMAL

        return DiagnosticResult(
            test_id=f"mechanical_diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            test_name="Mechanical System Diagnostic",
            status=status,
            result_data={
                "active_mechanical_lockouts": len(mechanical_lockouts),
                "average_vibration": statistics.mean([v for _, v in self.vibration_history])
                if self.vibration_history
                else 0,
            },
            issues_found=issues,
            recommendations=recommendations,
            safety_impact=safety_impact,
        )

    async def _create_diagnostic_lockout(self, diagnostic: DiagnosticResult):
        """Create lockout based on diagnostic results"""
        lockout_id = f"diagnostic_{diagnostic.test_id}"

        lockout = MaintenanceLockout(
            lockout_id=lockout_id,
            lockout_type=MaintenanceLockoutType.DIAGNOSTIC_FAILURE,
            severity=diagnostic.status,
            description=f"Diagnostic failure: {diagnostic.test_name} - {', '.join(diagnostic.issues_found)}",
            affected_systems=["all_operations"] if diagnostic.safety_impact else ["maintenance"],
            required_access_level=SafetyAccessLevel.TECHNICIAN,
            override_possible=True,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=6),
        )

        await self._activate_lockout(lockout)

    async def _schedule_maintenance_reminder(self, maintenance_type: str, schedule: Dict[str, Any]):
        """Schedule maintenance reminder"""
        reminder = {
            "type": maintenance_type,
            "description": schedule["description"],
            "required_access_level": schedule["required_access_level"].value,
            "overdue_hours": (datetime.now() - schedule["last_performed"]).total_seconds() / 3600
            - schedule["frequency_hours"],
            "created_at": datetime.now(),
        }

        self.maintenance_reminders.append(reminder)

        # Publish reminder
        await self.mqtt_client.publish("lawnberry/maintenance/reminder", reminder)

        logger.info(f"Maintenance reminder scheduled: {maintenance_type}")

    def register_blade_callback(self, callback: Callable):
        """Register callback for blade monitoring"""
        self.blade_callbacks.append(callback)

    def register_battery_callback(self, callback: Callable):
        """Register callback for battery monitoring"""
        self.battery_callbacks.append(callback)

    def register_lockout_callback(self, callback: Callable):
        """Register callback for maintenance lockouts"""
        self.lockout_callbacks.append(callback)

    def register_diagnostic_callback(self, callback: Callable):
        """Register callback for diagnostic results"""
        self.diagnostic_callbacks.append(callback)

    async def get_maintenance_status(self) -> Dict[str, Any]:
        """Get comprehensive maintenance status"""
        return {
            "blade_status": {
                blade_id: {
                    "condition": data.condition.value,
                    "wear_percentage": data.wear_percentage,
                    "replacement_recommended": data.replacement_recommended,
                    "safety_concern": data.safety_concern,
                }
                for blade_id, data in self.blade_data.items()
            },
            "battery_status": {
                battery_id: {
                    "health_status": data.health_status.value,
                    "capacity_percentage": data.capacity_percentage,
                    "safety_concerns": data.safety_concerns,
                    "estimated_remaining_life_days": data.estimated_remaining_life_days,
                }
                for battery_id, data in self.battery_data.items()
            },
            "active_lockouts": len(self.active_lockouts),
            "maintenance_reminders": len(self.maintenance_reminders),
            "recent_diagnostics": len(
                [d for d in self.diagnostic_history if (datetime.now() - d.timestamp).days < 7]
            ),
            "system_health": "critical"
            if any(l.severity == MaintenanceStatus.CRITICAL for l in self.active_lockouts.values())
            else "good",
        }
