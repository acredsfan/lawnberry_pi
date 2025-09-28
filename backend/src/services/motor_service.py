"""
MotorService for LawnBerry Pi v2
Motor control abstraction for RoboHAT/Cytron and L298N fallback
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple

from ..models import (
    MotorControl, DriveCommand, BladeCommand, EncoderFeedback, MotorDiagnostics,
    DriveController, ControlMode, MotorStatus
)

logger = logging.getLogger(__name__)


class RoboHATCytronController:
    """RoboHAT + Cytron MDDRC10 controller interface"""
    
    def __init__(self):
        self.initialized = False
        self.last_command: Optional[DriveCommand] = None
        
    async def initialize(self) -> bool:
        """Initialize RoboHAT + Cytron controller"""
        try:
            logger.info("Initializing RoboHAT + Cytron MDDRC10 controller")
            # RoboHAT initialization would go here
            # - Setup UART communication
            # - Configure motor parameters
            # - Enable encoder feedback
            self.initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize RoboHAT controller: {e}")
            return False
    
    async def send_drive_command(self, command: DriveCommand) -> bool:
        """Send drive command to RoboHAT"""
        if not self.initialized:
            return False
        
        try:
            # Convert to RoboHAT protocol
            left_speed = int(command.left_motor_speed * 100)  # -100 to 100
            right_speed = int(command.right_motor_speed * 100)
            
            # Send command via UART (placeholder)
            logger.debug(f"RoboHAT command: L={left_speed}, R={right_speed}")
            
            self.last_command = command
            return True
        except Exception as e:
            logger.error(f"Failed to send RoboHAT command: {e}")
            return False
    
    async def read_encoder_feedback(self) -> Optional[EncoderFeedback]:
        """Read encoder feedback from RoboHAT"""
        if not self.initialized:
            return None
        
        try:
            # Read encoder data from RoboHAT (placeholder)
            feedback = EncoderFeedback(
                left_encoder_ticks=1250,
                right_encoder_ticks=1200,
                left_rpm=45.0,
                right_rpm=43.5,
                left_distance=2.5,  # meters
                right_distance=2.4
            )
            return feedback
        except Exception as e:
            logger.error(f"Failed to read encoder feedback: {e}")
            return None
    
    async def get_diagnostics(self) -> Optional[MotorDiagnostics]:
        """Get motor diagnostics from RoboHAT"""
        try:
            diagnostics = MotorDiagnostics(
                left_motor_current=1.2,   # A
                right_motor_current=1.1,  # A
                controller_temperature=35.0,  # °C
                voltage_supply=12.6,      # V
                error_flags={}
            )
            return diagnostics
        except Exception as e:
            logger.error(f"Failed to get RoboHAT diagnostics: {e}")
            return None


class L298NController:
    """L298N H-Bridge controller interface (fallback)"""
    
    def __init__(self):
        self.initialized = False
        self.gpio_pins = {
            'motor1_in1': 18,
            'motor1_in2': 19,
            'motor1_enable': 12,
            'motor2_in1': 20,
            'motor2_in2': 21,
            'motor2_enable': 13
        }
        
    async def initialize(self) -> bool:
        """Initialize L298N controller"""
        try:
            logger.info("Initializing L298N H-Bridge controller")
            # GPIO initialization would go here
            # - Setup PWM pins
            # - Configure direction pins
            self.initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize L298N controller: {e}")
            return False
    
    async def send_drive_command(self, command: DriveCommand) -> bool:
        """Send drive command to L298N"""
        if not self.initialized:
            return False
        
        try:
            # Convert speed to PWM duty cycle (0-100)
            left_duty = abs(command.left_motor_speed) * 100
            right_duty = abs(command.right_motor_speed) * 100
            
            # Set direction pins
            left_forward = command.left_motor_speed >= 0
            right_forward = command.right_motor_speed >= 0
            
            # Set GPIO pins (placeholder)
            logger.debug(f"L298N: L={left_duty}%({'FWD' if left_forward else 'REV'}), "
                        f"R={right_duty}%({'FWD' if right_forward else 'REV'})")
            
            return True
        except Exception as e:
            logger.error(f"Failed to send L298N command: {e}")
            return False
    
    async def read_encoder_feedback(self) -> Optional[EncoderFeedback]:
        """L298N doesn't have built-in encoder support"""
        return None
    
    async def get_diagnostics(self) -> Optional[MotorDiagnostics]:
        """Get basic L298N diagnostics"""
        try:
            diagnostics = MotorDiagnostics(
                controller_temperature=30.0,  # Estimated
                voltage_supply=12.6,      # V
                error_flags={}
            )
            return diagnostics
        except Exception as e:
            logger.error(f"Failed to get L298N diagnostics: {e}")
            return None


class BladeController:
    """IBT-4 H-Bridge blade motor controller"""
    
    def __init__(self):
        self.initialized = False
        self.blade_active = False
        self.gpio_pins = {
            'blade_in1': 24,  # GPIO 24
            'blade_in2': 25   # GPIO 25
        }
        
    async def initialize(self) -> bool:
        """Initialize blade controller"""
        try:
            logger.info("Initializing IBT-4 blade controller")
            # GPIO initialization for blade control
            self.initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize blade controller: {e}")
            return False
    
    async def send_blade_command(self, command: BladeCommand) -> bool:
        """Send blade control command"""
        if not self.initialized:
            return False
        
        try:
            if command.active and command.safety_enabled:
                # Activate blade with specified speed
                speed_pwm = command.speed * 100  # Convert to PWM duty cycle
                logger.debug(f"Blade ON: {speed_pwm}% speed")
                self.blade_active = True
            else:
                # Stop blade
                logger.debug("Blade OFF")
                self.blade_active = False
            
            return True
        except Exception as e:
            logger.error(f"Failed to send blade command: {e}")
            return False
    
    def emergency_stop_blade(self):
        """Immediately stop blade motor"""
        logger.critical("Blade emergency stop")
        self.blade_active = False
        # Immediate GPIO stop would go here


class SafetySystem:
    """Motor safety monitoring and interlocks"""
    
    def __init__(self):
        self.emergency_stop_active = False
        self.tilt_cutoff_active = False
        self.safety_violations = []
        
    def check_safety_conditions(self, motor_control: MotorControl, 
                               sensor_data: Dict[str, Any]) -> bool:
        """Check all safety conditions"""
        violations = []
        
        # Check emergency stop
        if self.emergency_stop_active:
            violations.append("Emergency stop activated")
        
        # Check tilt angle (if IMU data available)
        if 'imu' in sensor_data and sensor_data['imu']:
            roll = sensor_data['imu'].get('roll', 0)
            pitch = sensor_data['imu'].get('pitch', 0)
            
            if abs(roll) > 30 or abs(pitch) > 30:
                violations.append(f"Excessive tilt: roll={roll:.1f}°, pitch={pitch:.1f}°")
                self.tilt_cutoff_active = True
            else:
                self.tilt_cutoff_active = False
        
        # Check battery voltage
        if 'power' in sensor_data and sensor_data['power']:
            voltage = sensor_data['power'].get('battery_voltage', 12.0)
            if voltage < 10.5:
                violations.append(f"Low battery voltage: {voltage:.1f}V")
        
        # Check motor temperature
        if motor_control.diagnostics:
            temp = motor_control.diagnostics.controller_temperature
            if temp and temp > 70.0:
                violations.append(f"High motor temperature: {temp:.1f}°C")
        
        self.safety_violations = violations
        return len(violations) == 0
    
    def activate_emergency_stop(self):
        """Activate emergency stop"""
        self.emergency_stop_active = True
        logger.critical("Emergency stop activated by safety system")
    
    def reset_emergency_stop(self):
        """Reset emergency stop (manual action required)"""
        self.emergency_stop_active = False
        logger.info("Emergency stop reset")


class MotorService:
    """Main motor control service"""
    
    def __init__(self, controller_type: DriveController = DriveController.L298N_ALT):
        self.controller_type = controller_type
        self.motor_control = MotorControl(controller_type=controller_type)
        self.safety_system = SafetySystem()
        
        # Initialize controllers
        if controller_type == DriveController.ROBOHAT_MDDRC10:
            self.drive_controller = RoboHATCytronController()
            self.motor_control.encoder_enabled = True
        else:
            self.drive_controller = L298NController()
            self.motor_control.encoder_enabled = False
        
        self.blade_controller = BladeController()
        self.command_timeout_task: Optional[asyncio.Task] = None
        
    async def initialize(self) -> bool:
        """Initialize motor service"""
        logger.info(f"Initializing motor service with {self.controller_type} controller")
        
        # Initialize drive controller
        drive_init = await self.drive_controller.initialize()
        blade_init = await self.blade_controller.initialize()
        
        if drive_init:
            self.motor_control.left_motor_status = MotorStatus.STOPPED
            self.motor_control.right_motor_status = MotorStatus.STOPPED
        
        if blade_init:
            self.motor_control.blade_motor_status = MotorStatus.STOPPED
        
        return drive_init and blade_init
    
    async def send_drive_command(self, command: DriveCommand, 
                                sensor_data: Dict[str, Any] = None) -> bool:
        """Send drive command with safety checks"""
        
        # Update motor control state
        self.motor_control.drive_command = command
        self.motor_control.last_command_time = datetime.now(timezone.utc)
        self.motor_control.command_sequence += 1
        
        # Check safety conditions
        if not self.safety_system.check_safety_conditions(self.motor_control, sensor_data or {}):
            logger.warning(f"Drive command blocked by safety: {self.safety_violations}")
            self.motor_control.emergency_stop()
            return False
        
        # Convert arcade controls if needed
        if command.throttle is not None and command.turn is not None:
            left_speed, right_speed = self.motor_control.calculate_differential_drive(
                command.throttle, command.turn
            )
            command.left_motor_speed = left_speed
            command.right_motor_speed = right_speed
        
        # Apply speed limits
        max_speed = command.max_speed_limit
        command.left_motor_speed = max(-max_speed, min(max_speed, command.left_motor_speed))
        command.right_motor_speed = max(-max_speed, min(max_speed, command.right_motor_speed))
        
        # Send to hardware controller
        success = await self.drive_controller.send_drive_command(command)
        
        if success:
            # Update motor status
            self.motor_control.left_motor_status = (
                MotorStatus.RUNNING if abs(command.left_motor_speed) > 0.01 else MotorStatus.STOPPED
            )
            self.motor_control.right_motor_status = (
                MotorStatus.RUNNING if abs(command.right_motor_speed) > 0.01 else MotorStatus.STOPPED
            )
            
            # Setup command timeout
            self._setup_command_timeout(command.timeout_ms)
        
        return success
    
    async def send_blade_command(self, command: BladeCommand,
                                sensor_data: Dict[str, Any] = None) -> bool:
        """Send blade command with safety checks"""
        
        # Update motor control state
        self.motor_control.blade_command = command
        
        # Enhanced safety checks for blade
        if command.active:
            if not self.safety_system.check_safety_conditions(self.motor_control, sensor_data or {}):
                logger.warning("Blade activation blocked by safety system")
                return False
            
            if self.motor_control.tilt_cutoff_active:
                logger.warning("Blade activation blocked by tilt cutoff")
                return False
        
        # Send to blade controller
        success = await self.blade_controller.send_blade_command(command)
        
        if success:
            self.motor_control.blade_motor_status = (
                MotorStatus.RUNNING if command.active else MotorStatus.STOPPED
            )
        
        return success
    
    def _setup_command_timeout(self, timeout_ms: int):
        """Setup command timeout to stop motors"""
        if self.command_timeout_task:
            self.command_timeout_task.cancel()
        
        async def timeout_handler():
            await asyncio.sleep(timeout_ms / 1000.0)
            logger.warning("Motor command timeout - stopping motors")
            await self.emergency_stop()
        
        self.command_timeout_task = asyncio.create_task(timeout_handler())
    
    async def emergency_stop(self) -> bool:
        """Emergency stop all motors"""
        logger.critical("Motor emergency stop activated")
        
        self.safety_system.activate_emergency_stop()
        self.motor_control.emergency_stop()
        
        # Stop drive motors
        stop_command = DriveCommand(
            left_motor_speed=0.0,
            right_motor_speed=0.0,
            control_mode=ControlMode.EMERGENCY_STOP
        )
        await self.drive_controller.send_drive_command(stop_command)
        
        # Stop blade immediately
        self.blade_controller.emergency_stop_blade()
        
        # Update status
        self.motor_control.left_motor_status = MotorStatus.STOPPED
        self.motor_control.right_motor_status = MotorStatus.STOPPED
        self.motor_control.blade_motor_status = MotorStatus.STOPPED
        
        return True
    
    async def update_feedback(self) -> MotorControl:
        """Update motor feedback and diagnostics"""
        
        # Read encoder feedback if available
        if self.motor_control.encoder_enabled:
            encoder_data = await self.drive_controller.read_encoder_feedback()
            if encoder_data:
                self.motor_control.encoder_feedback = encoder_data
        
        # Read diagnostics
        diagnostics = await self.drive_controller.get_diagnostics()
        if diagnostics:
            self.motor_control.diagnostics = diagnostics
        
        # Update safety status
        self.motor_control.emergency_stop_active = self.safety_system.emergency_stop_active
        self.motor_control.tilt_cutoff_active = self.safety_system.tilt_cutoff_active
        self.motor_control.blade_safety_ok = not self.safety_system.tilt_cutoff_active
        
        self.motor_control.timestamp = datetime.now(timezone.utc)
        return self.motor_control
    
    async def reset_emergency_stop(self) -> bool:
        """Reset emergency stop (requires manual confirmation)"""
        if not self.motor_control.emergency_stop_active:
            return True
        
        # Check that it's safe to reset
        if self.safety_system.safety_violations:
            logger.warning(f"Cannot reset E-stop: {self.safety_system.safety_violations}")
            return False
        
        self.safety_system.reset_emergency_stop()
        self.motor_control.emergency_stop_active = False
        
        logger.info("Emergency stop reset - system ready")
        return True
    
    async def get_motor_status(self) -> Dict[str, Any]:
        """Get current motor status"""
        return {
            "controller_type": self.controller_type,
            "left_motor_status": self.motor_control.left_motor_status,
            "right_motor_status": self.motor_control.right_motor_status,
            "blade_motor_status": self.motor_control.blade_motor_status,
            "emergency_stop_active": self.motor_control.emergency_stop_active,
            "tilt_cutoff_active": self.motor_control.tilt_cutoff_active,
            "blade_safety_ok": self.motor_control.blade_safety_ok,
            "encoder_enabled": self.motor_control.encoder_enabled,
            "safety_violations": self.safety_system.safety_violations,
            "last_command_time": self.motor_control.last_command_time,
            "command_sequence": self.motor_control.command_sequence
        }
    
    async def shutdown(self):
        """Shutdown motor service"""
        logger.info("Shutting down motor service")
        await self.emergency_stop()
        
        if self.command_timeout_task:
            self.command_timeout_task.cancel()