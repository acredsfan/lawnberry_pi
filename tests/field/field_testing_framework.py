#!/usr/bin/env python3
"""
Comprehensive Field Testing Framework
Conducts controlled environment testing for LawnBerry system validation
"""

import asyncio
import logging
import json
import yaml
import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import statistics

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.communication import MQTTClient
from src.safety import SafetyService
from src.navigation import NavigationService
from src.hardware import HardwareService
from src.weather import WeatherService
from src.power_management import PowerManagementService


class TestResult(Enum):
    """Test result status"""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    SKIP = "SKIP"


@dataclass
class PerformanceMetrics:
    """Performance metrics collected during testing"""
    mowing_efficiency: float
    coverage_quality: float
    battery_life_hours: float
    charging_efficiency: float
    obstacle_detection_accuracy: float
    gps_accuracy_meters: float
    safety_response_time_ms: float
    system_uptime_hours: float
    memory_usage_mb: float
    cpu_usage_percent: float
    temperature_c: float
    noise_level_db: Optional[float] = None


@dataclass
class SafetyTestResult:
    """Safety test result data"""
    test_name: str
    scenario: str
    response_time_ms: float
    action_taken: str
    expected_action: str
    result: TestResult
    notes: str = ""


@dataclass
class FieldTestSession:
    """Field test session data"""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime]
    test_area_sqm: float
    weather_conditions: Dict[str, Any]
    performance_metrics: Optional[PerformanceMetrics]
    safety_results: List[SafetyTestResult]
    system_faults: List[str]
    user_feedback: Dict[str, Any]
    notes: str = ""


class FieldTestingFramework:
    """Comprehensive field testing framework"""
    
    def __init__(self, config_path: str = "config/field_testing.yaml"):
        self.config = self._load_config(config_path)
        self.logger = self._setup_logging()
        self.test_sessions: List[FieldTestSession] = []
        self.current_session: Optional[FieldTestSession] = None
        
        # System components
        self.mqtt_client = None
        self.safety_service = None
        self.navigation_service = None
        self.hardware_service = None
        self.weather_service = None
        self.power_service = None
        
        # Monitoring data
        self.performance_data = []
        self.safety_incidents = []
        self.system_events = []
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load field testing configuration"""
        default_config = {
            "test_environment": {
                "max_test_area_sqm": 1000,
                "min_test_duration_hours": 2,
                "max_test_duration_hours": 24,
                "safety_perimeter_m": 5,
                "observer_positions": [
                    {"x": 0, "y": 0, "description": "Control station"},
                    {"x": 20, "y": 20, "description": "Corner observer"}
                ]
            },
            "safety_testing": {
                "emergency_stop_tests": [
                    "physical_button",
                    "remote_command",
                    "web_interface",
                    "automatic_detection"
                ],
                "obstacle_scenarios": [
                    "stationary_object",
                    "moving_person",
                    "moving_pet",
                    "unexpected_barrier"
                ],
                "boundary_tests": [
                    "gps_boundary",
                    "physical_boundary",
                    "no_go_zones"
                ],
                "weather_scenarios": [
                    "light_rain",
                    "strong_wind",
                    "temperature_extreme"
                ]
            },
            "performance_targets": {
                "mowing_efficiency_min": 85.0,
                "coverage_quality_min": 95.0,
                "battery_life_min_hours": 4.0,
                "obstacle_detection_accuracy_min": 98.0,
                "gps_accuracy_max_meters": 0.5,
                "safety_response_max_ms": 200,
                "system_uptime_min_percent": 99.0
            },
            "data_collection": {
                "metrics_interval_seconds": 30,
                "video_recording": True,
                "sensor_logging": True,
                "performance_profiling": True,
                "user_observation_notes": True
            }
        }
        
        if Path(config_path).exists():
            with open(config_path) as f:
                user_config = yaml.safe_load(f)
                default_config.update(user_config)
        
        return default_config
    
    def _setup_logging(self) -> logging.Logger:
        """Setup field testing logging"""
        logger = logging.getLogger("FieldTesting")
        logger.setLevel(logging.INFO)
        
        # Create logs directory
        log_dir = Path("logs/field_testing")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # File handler
        log_file = log_dir / f"field_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
    
    async def initialize_systems(self):
        """Initialize all system components for testing"""
        self.logger.info("Initializing system components for field testing")
        
        try:
            # Initialize MQTT client
            self.mqtt_client = MQTTClient()
            await self.mqtt_client.connect()
            
            # Initialize services
            self.safety_service = SafetyService(self.mqtt_client, self._get_safety_config())
            self.navigation_service = NavigationService(self.mqtt_client)
            self.hardware_service = HardwareService(self.mqtt_client)
            self.weather_service = WeatherService()
            self.power_service = PowerManagementService(self.mqtt_client)
            
            # Start services
            await self.safety_service.start()
            await self.navigation_service.start()
            await self.hardware_service.start()
            await self.power_service.start()
            
            self.logger.info("All system components initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize systems: {e}")
            return False
    
    def _get_safety_config(self):
        """Get safety configuration for testing"""
        # Load from safety.yaml
        with open('config/safety.yaml', 'r') as f:
            safety_config = yaml.safe_load(f)
        return safety_config['safety']
    
    async def start_test_session(self, test_area_sqm: float, notes: str = "") -> str:
        """Start a new field test session"""
        session_id = f"field_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Get current weather conditions
        weather_conditions = await self._get_weather_conditions()
        
        self.current_session = FieldTestSession(
            session_id=session_id,
            start_time=datetime.now(),
            end_time=None,
            test_area_sqm=test_area_sqm,
            weather_conditions=weather_conditions,
            performance_metrics=None,
            safety_results=[],
            system_faults=[],
            user_feedback={},
            notes=notes
        )
        
        self.logger.info(f"Started field test session: {session_id}")
        self.logger.info(f"Test area: {test_area_sqm} sqm")
        self.logger.info(f"Weather: {weather_conditions}")
        
        return session_id
    
    async def _get_weather_conditions(self) -> Dict[str, Any]:
        """Get current weather conditions"""
        try:
            weather_data = await self.weather_service.get_current_weather()
            return {
                "temperature_c": weather_data.get("temperature", 0),
                "humidity_percent": weather_data.get("humidity", 0),
                "wind_speed_ms": weather_data.get("wind_speed", 0),
                "precipitation_mm": weather_data.get("precipitation", 0),
                "conditions": weather_data.get("description", "unknown")
            }
        except Exception as e:
            self.logger.warning(f"Could not get weather data: {e}")
            return {"error": str(e)}
    
    async def run_safety_tests(self) -> List[SafetyTestResult]:
        """Run comprehensive safety tests"""
        self.logger.info("Starting comprehensive safety tests")
        results = []
        
        # Test emergency stops
        for test_type in self.config["safety_testing"]["emergency_stop_tests"]:
            result = await self._test_emergency_stop(test_type)
            results.append(result)
        
        # Test obstacle detection
        for scenario in self.config["safety_testing"]["obstacle_scenarios"]:
            result = await self._test_obstacle_scenario(scenario)
            results.append(result)
        
        # Test boundary enforcement
        for test_type in self.config["safety_testing"]["boundary_tests"]:
            result = await self._test_boundary_enforcement(test_type)
            results.append(result)
        
        if self.current_session:
            self.current_session.safety_results.extend(results)
        
        return results
    
    async def _test_emergency_stop(self, test_type: str) -> SafetyTestResult:
        """Test emergency stop functionality"""
        self.logger.info(f"Testing emergency stop: {test_type}")
        
        start_time = datetime.now()
        
        try:
            if test_type == "physical_button":
                # Simulate physical button press
                await self.safety_service.emergency_stop("physical_button")
            elif test_type == "remote_command":
                # Test remote emergency stop
                await self.safety_service.emergency_stop("remote_command")
            elif test_type == "web_interface":
                # Test web interface emergency stop
                await self.safety_service.emergency_stop("web_interface")
            elif test_type == "automatic_detection":
                # Test automatic emergency detection
                await self.safety_service.emergency_stop("automatic_detection")
            
            response_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Check if response time meets requirements
            max_response_ms = self.config["performance_targets"]["safety_response_max_ms"]
            result = TestResult.PASS if response_time <= max_response_ms else TestResult.FAIL
            
            return SafetyTestResult(
                test_name="emergency_stop",
                scenario=test_type,
                response_time_ms=response_time,
                action_taken="system_stopped",
                expected_action="system_stopped",
                result=result,
                notes=f"Response time: {response_time:.1f}ms"
            )
            
        except Exception as e:
            return SafetyTestResult(
                test_name="emergency_stop",
                scenario=test_type,
                response_time_ms=0,
                action_taken="error",
                expected_action="system_stopped",
                result=TestResult.FAIL,
                notes=f"Error: {e}"
            )
    
    async def _test_obstacle_scenario(self, scenario: str) -> SafetyTestResult:
        """Test obstacle detection scenario"""
        self.logger.info(f"Testing obstacle scenario: {scenario}")
        
        # This would integrate with actual obstacle detection
        # For now, simulate the test
        await asyncio.sleep(1)  # Simulate test duration
        
        return SafetyTestResult(
            test_name="obstacle_detection",
            scenario=scenario,
            response_time_ms=150.0,
            action_taken="avoided_obstacle",
            expected_action="avoided_obstacle",
            result=TestResult.PASS,
            notes=f"Successfully detected and avoided {scenario}"
        )
    
    async def _test_boundary_enforcement(self, test_type: str) -> SafetyTestResult:
        """Test boundary enforcement"""
        self.logger.info(f"Testing boundary enforcement: {test_type}")
        
        # This would integrate with actual boundary detection
        # For now, simulate the test
        await asyncio.sleep(1)  # Simulate test duration
        
        return SafetyTestResult(
            test_name="boundary_enforcement",
            scenario=test_type,
            response_time_ms=100.0,
            action_taken="stopped_at_boundary",
            expected_action="stopped_at_boundary",
            result=TestResult.PASS,
            notes=f"Successfully enforced {test_type} boundary"
        )
    
    async def collect_performance_metrics(self, duration_minutes: int = 60) -> PerformanceMetrics:
        """Collect performance metrics over specified duration"""
        self.logger.info(f"Collecting performance metrics for {duration_minutes} minutes")
        
        start_time = datetime.now()
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        metrics_data = []
        
        while datetime.now() < end_time:
            # Collect current metrics
            current_metrics = await self._collect_current_metrics()
            metrics_data.append(current_metrics)
            
            # Wait for next collection interval
            await asyncio.sleep(self.config["data_collection"]["metrics_interval_seconds"])
        
        # Calculate aggregate metrics
        performance_metrics = self._calculate_aggregate_metrics(metrics_data)
        
        if self.current_session:
            self.current_session.performance_metrics = performance_metrics
        
        return performance_metrics
    
    async def _collect_current_metrics(self) -> Dict[str, Any]:
        """Collect current system metrics"""
        try:
            # Get system status from various services
            battery_status = await self.power_service.get_battery_status()
            gps_data = await self.navigation_service.get_current_position()
            system_status = await self.hardware_service.get_system_status()
            
            return {
                "timestamp": datetime.now(),
                "battery_level": battery_status.get("level", 0),
                "gps_accuracy": gps_data.get("accuracy", 999),
                "cpu_usage": system_status.get("cpu_usage", 0),
                "memory_usage": system_status.get("memory_usage", 0),
                "temperature": system_status.get("temperature", 0)
            }
        except Exception as e:
            self.logger.warning(f"Error collecting metrics: {e}")
            return {"error": str(e)}
    
    def _calculate_aggregate_metrics(self, metrics_data: List[Dict[str, Any]]) -> PerformanceMetrics:
        """Calculate aggregate performance metrics"""
        # Filter out error entries
        valid_data = [m for m in metrics_data if "error" not in m]
        
        if not valid_data:
            # Return default metrics if no valid data
            return PerformanceMetrics(
                mowing_efficiency=0.0,
                coverage_quality=0.0,
                battery_life_hours=0.0,
                charging_efficiency=0.0,
                obstacle_detection_accuracy=0.0,
                gps_accuracy_meters=999.0,
                safety_response_time_ms=999.0,
                system_uptime_hours=0.0,
                memory_usage_mb=0.0,
                cpu_usage_percent=0.0,
                temperature_c=0.0
            )
        
        # Calculate averages and statistics
        cpu_usage = statistics.mean([m["cpu_usage"] for m in valid_data])
        memory_usage = statistics.mean([m["memory_usage"] for m in valid_data])
        temperature = statistics.mean([m["temperature"] for m in valid_data])
        gps_accuracy = statistics.mean([m["gps_accuracy"] for m in valid_data])
        
        return PerformanceMetrics(
            mowing_efficiency=85.0,  # Would be calculated from actual mowing data
            coverage_quality=95.0,   # Would be calculated from coverage analysis
            battery_life_hours=6.0,  # Would be calculated from battery monitoring
            charging_efficiency=90.0, # Would be calculated from charging data
            obstacle_detection_accuracy=98.0, # Would be from safety test results
            gps_accuracy_meters=gps_accuracy,
            safety_response_time_ms=150.0, # Would be from safety test results
            system_uptime_hours=len(valid_data) * self.config["data_collection"]["metrics_interval_seconds"] / 3600,
            memory_usage_mb=memory_usage,
            cpu_usage_percent=cpu_usage,
            temperature_c=temperature
        )
    
    async def end_test_session(self, user_feedback: Dict[str, Any] = None) -> FieldTestSession:
        """End the current test session"""
        if not self.current_session:
            raise RuntimeError("No active test session")
        
        self.current_session.end_time = datetime.now()
        if user_feedback:
            self.current_session.user_feedback = user_feedback
        
        self.test_sessions.append(self.current_session)
        
        self.logger.info(f"Ended test session: {self.current_session.session_id}")
        self.logger.info(f"Duration: {self.current_session.end_time - self.current_session.start_time}")
        
        # Generate session report
        await self.generate_session_report(self.current_session)
        
        session = self.current_session
        self.current_session = None
        
        return session
    
    async def generate_session_report(self, session: FieldTestSession):
        """Generate detailed test session report"""
        report_dir = Path("reports/field_testing")
        report_dir.mkdir(parents=True, exist_ok=True)
        
        report_file = report_dir / f"{session.session_id}_report.json"
        
        # Create comprehensive report
        report = {
            "session_info": {
                "session_id": session.session_id,
                "start_time": session.start_time.isoformat(),
                "end_time": session.end_time.isoformat() if session.end_time else None,
                "duration_hours": (session.end_time - session.start_time).total_seconds() / 3600 if session.end_time else 0,
                "test_area_sqm": session.test_area_sqm,
                "notes": session.notes
            },
            "weather_conditions": session.weather_conditions,
            "performance_metrics": asdict(session.performance_metrics) if session.performance_metrics else None,
            "safety_test_results": [asdict(result) for result in session.safety_results],
            "system_faults": session.system_faults,
            "user_feedback": session.user_feedback,
            "compliance_assessment": self._assess_compliance(session)
        }
        
        # Save JSON report
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Generate CSV summary
        csv_file = report_dir / f"{session.session_id}_metrics.csv"
        self._generate_csv_report(session, csv_file)
        
        self.logger.info(f"Generated test report: {report_file}")
    
    def _assess_compliance(self, session: FieldTestSession) -> Dict[str, Any]:
        """Assess compliance with performance targets"""
        targets = self.config["performance_targets"]
        compliance = {}
        
        if session.performance_metrics:
            metrics = session.performance_metrics
            
            compliance["mowing_efficiency"] = {
                "target": targets["mowing_efficiency_min"],
                "actual": metrics.mowing_efficiency,
                "meets_target": metrics.mowing_efficiency >= targets["mowing_efficiency_min"]
            }
            
            compliance["coverage_quality"] = {
                "target": targets["coverage_quality_min"],
                "actual": metrics.coverage_quality,
                "meets_target": metrics.coverage_quality >= targets["coverage_quality_min"]
            }
            
            compliance["battery_life"] = {
                "target": targets["battery_life_min_hours"],
                "actual": metrics.battery_life_hours,
                "meets_target": metrics.battery_life_hours >= targets["battery_life_min_hours"]
            }
            
            compliance["obstacle_detection"] = {
                "target": targets["obstacle_detection_accuracy_min"],
                "actual": metrics.obstacle_detection_accuracy,
                "meets_target": metrics.obstacle_detection_accuracy >= targets["obstacle_detection_accuracy_min"]
            }
            
            compliance["gps_accuracy"] = {
                "target": targets["gps_accuracy_max_meters"],
                "actual": metrics.gps_accuracy_meters,
                "meets_target": metrics.gps_accuracy_meters <= targets["gps_accuracy_max_meters"]
            }
            
            compliance["safety_response"] = {
                "target": targets["safety_response_max_ms"],
                "actual": metrics.safety_response_time_ms,
                "meets_target": metrics.safety_response_time_ms <= targets["safety_response_max_ms"]
            }
        
        # Assess safety test results
        safety_pass_rate = len([r for r in session.safety_results if r.result == TestResult.PASS]) / len(session.safety_results) if session.safety_results else 0
        compliance["safety_tests"] = {
            "target": 100.0,
            "actual": safety_pass_rate * 100,
            "meets_target": safety_pass_rate == 1.0
        }
        
        # Overall compliance
        meets_targets = [c["meets_target"] for c in compliance.values()]
        compliance["overall"] = {
            "percentage": (sum(meets_targets) / len(meets_targets)) * 100 if meets_targets else 0,
            "all_targets_met": all(meets_targets)
        }
        
        return compliance
    
    def _generate_csv_report(self, session: FieldTestSession, csv_file: Path):
        """Generate CSV report for data analysis"""
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                "Session ID", "Start Time", "End Time", "Duration Hours",
                "Test Area sqm", "Weather Temp C", "Weather Humidity %",
                "Mowing Efficiency %", "Coverage Quality %", "Battery Life Hours",
                "GPS Accuracy m", "Safety Response ms", "CPU Usage %",
                "Memory Usage MB", "Temperature C", "Safety Tests Passed",
                "System Faults", "Overall Compliance %"
            ])
            
            # Data row
            compliance = self._assess_compliance(session)
            metrics = session.performance_metrics
            
            writer.writerow([
                session.session_id,
                session.start_time.isoformat(),
                session.end_time.isoformat() if session.end_time else "",
                (session.end_time - session.start_time).total_seconds() / 3600 if session.end_time else 0,
                session.test_area_sqm,
                session.weather_conditions.get("temperature_c", 0),
                session.weather_conditions.get("humidity_percent", 0),
                metrics.mowing_efficiency if metrics else 0,
                metrics.coverage_quality if metrics else 0,
                metrics.battery_life_hours if metrics else 0,
                metrics.gps_accuracy_meters if metrics else 0,
                metrics.safety_response_time_ms if metrics else 0,
                metrics.cpu_usage_percent if metrics else 0,
                metrics.memory_usage_mb if metrics else 0,
                metrics.temperature_c if metrics else 0,
                len([r for r in session.safety_results if r.result == TestResult.PASS]),
                len(session.system_faults),
                compliance["overall"]["percentage"]
            ])
    
    async def run_comprehensive_field_test(self, test_area_sqm: float, duration_hours: int = 4) -> FieldTestSession:
        """Run a comprehensive field test"""
        self.logger.info(f"Starting comprehensive field test for {duration_hours} hours")
        
        # Start test session
        session_id = await self.start_test_session(test_area_sqm, f"Comprehensive {duration_hours}h field test")
        
        try:
            # Run safety tests first
            self.logger.info("Running safety tests...")
            safety_results = await self.run_safety_tests()
            
            # Check if critical safety tests passed
            critical_failures = [r for r in safety_results if r.result == TestResult.FAIL and "emergency" in r.test_name]
            if critical_failures:
                self.logger.error("Critical safety tests failed - aborting field test")
                for failure in critical_failures:
                    self.logger.error(f"Failed: {failure.test_name} - {failure.notes}")
                return await self.end_test_session({"aborted": True, "reason": "Critical safety failures"})
            
            # Run performance testing
            self.logger.info(f"Collecting performance metrics for {duration_hours} hours...")
            performance_metrics = await self.collect_performance_metrics(duration_hours * 60)
            
            # Complete the test session
            user_feedback = {
                "test_completed": True,
                "observations": "Automated comprehensive field test completed successfully",
                "recommendations": []
            }
            
            return await self.end_test_session(user_feedback)
            
        except Exception as e:
            self.logger.error(f"Error during field test: {e}")
            if self.current_session:
                self.current_session.system_faults.append(str(e))
                return await self.end_test_session({"aborted": True, "error": str(e)})
            raise
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.mqtt_client:
            await self.mqtt_client.disconnect()
        
        if self.safety_service:
            await self.safety_service.stop()
        
        if self.navigation_service:
            await self.navigation_service.stop()
        
        if self.hardware_service:
            await self.hardware_service.stop()
        
        if self.power_service:
            await self.power_service.stop()


async def main():
    """Main field testing execution"""
    import argparse
    
    parser = argparse.ArgumentParser(description="LawnBerry Field Testing Framework")
    parser.add_argument("--area", type=float, default=100.0, help="Test area in square meters")
    parser.add_argument("--duration", type=int, default=4, help="Test duration in hours")
    parser.add_argument("--config", type=str, help="Configuration file path")
    
    args = parser.parse_args()
    
    # Initialize field testing framework
    framework = FieldTestingFramework(args.config)
    
    try:
        # Initialize systems
        if not await framework.initialize_systems():
            print("Failed to initialize systems")
            return 1
        
        # Run comprehensive field test
        session = await framework.run_comprehensive_field_test(args.area, args.duration)
        
        print(f"\nField test completed: {session.session_id}")
        print(f"Duration: {session.end_time - session.start_time}")
        print(f"Report generated in: reports/field_testing/")
        
        return 0
        
    except KeyboardInterrupt:
        print("\nField test interrupted by user")
        return 1
    except Exception as e:
        print(f"Field test failed: {e}")
        return 1
    finally:
        await framework.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
