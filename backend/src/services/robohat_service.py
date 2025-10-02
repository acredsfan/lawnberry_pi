"""
RoboHAT RP2040 Service for LawnBerry Pi v2
Serial bridge interface for RoboHAT firmware health and control
"""

import asyncio
import logging
import serial
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RoboHATStatus:
    """RoboHAT firmware status"""
    firmware_version: str = "unknown"
    uptime_seconds: int = 0
    watchdog_active: bool = False
    last_watchdog_echo: Optional[str] = None
    watchdog_latency_ms: float = 0.0
    serial_connected: bool = False
    error_count: int = 0
    last_error: Optional[str] = None
    motor_controller_ok: bool = False
    encoder_feedback_ok: bool = False
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "firmware_version": self.firmware_version,
            "uptime_seconds": self.uptime_seconds,
            "watchdog_active": self.watchdog_active,
            "last_watchdog_echo": self.last_watchdog_echo,
            "watchdog_latency_ms": self.watchdog_latency_ms,
            "serial_connected": self.serial_connected,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "motor_controller_ok": self.motor_controller_ok,
            "encoder_feedback_ok": self.encoder_feedback_ok,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "health_status": self.get_health_status()
        }
    
    def get_health_status(self) -> str:
        """Get overall health status"""
        if not self.serial_connected:
            return "disconnected"
        if self.error_count > 10:
            return "fault"
        if not self.watchdog_active or not self.motor_controller_ok:
            return "warning"
        return "healthy"


class RoboHATService:
    """RoboHAT RP2040 serial bridge service"""
    
    def __init__(self, serial_port: str = "/dev/ttyACM0", baud_rate: int = 115200):
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.serial_conn: Optional[serial.Serial] = None
        self.status = RoboHATStatus()
        self.running = False
        self.watchdog_task: Optional[asyncio.Task] = None
        self.read_task: Optional[asyncio.Task] = None
        
    async def initialize(self) -> bool:
        """Initialize RoboHAT serial connection"""
        try:
            logger.info(f"Initializing RoboHAT service on {self.serial_port} at {self.baud_rate} baud")
            
            # Open serial connection
            self.serial_conn = serial.Serial(
                port=self.serial_port,
                baudrate=self.baud_rate,
                timeout=1.0,
                write_timeout=1.0
            )
            
            # Wait for connection to stabilize
            await asyncio.sleep(2.0)
            
            # Query firmware version
            await self._send_command("GET_VERSION")
            await asyncio.sleep(0.5)
            
            # Read response
            response = await self._read_response()
            if response and "version" in response:
                self.status.firmware_version = response["version"]
                logger.info(f"RoboHAT firmware version: {self.status.firmware_version}")
            
            self.status.serial_connected = True
            self.running = True
            
            # Start background tasks
            self.watchdog_task = asyncio.create_task(self._watchdog_loop())
            self.read_task = asyncio.create_task(self._read_loop())
            
            logger.info("RoboHAT service initialized successfully")
            return True
            
        except serial.SerialException as e:
            logger.error(f"Failed to initialize RoboHAT service: {e}")
            self.status.serial_connected = False
            self.status.last_error = str(e)
            return False
        except Exception as e:
            logger.error(f"Unexpected error initializing RoboHAT: {e}")
            self.status.last_error = str(e)
            return False
    
    async def _send_command(self, command: str, params: Optional[Dict[str, Any]] = None) -> bool:
        """Send command to RoboHAT firmware"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return False
        
        try:
            message = {
                "cmd": command,
                "params": params or {},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            json_msg = json.dumps(message) + "\n"
            self.serial_conn.write(json_msg.encode('utf-8'))
            self.serial_conn.flush()
            
            return True
        except Exception as e:
            logger.error(f"Failed to send RoboHAT command: {e}")
            self.status.error_count += 1
            self.status.last_error = str(e)
            return False
    
    async def _read_response(self, timeout: float = 1.0) -> Optional[Dict[str, Any]]:
        """Read response from RoboHAT firmware"""
        if not self.serial_conn or not self.serial_conn.is_open:
            return None
        
        try:
            # Wait for data with timeout
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                if self.serial_conn.in_waiting > 0:
                    line = self.serial_conn.readline().decode('utf-8').strip()
                    if line:
                        try:
                            return json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON from RoboHAT: {line}")
                await asyncio.sleep(0.01)
            
            return None
        except Exception as e:
            logger.error(f"Failed to read RoboHAT response: {e}")
            self.status.error_count += 1
            return None
    
    async def _watchdog_loop(self):
        """Periodic watchdog ping loop"""
        while self.running:
            try:
                # Send watchdog ping
                start_time = datetime.now(timezone.utc)
                await self._send_command("WATCHDOG_PING")
                
                # Wait for echo
                response = await self._read_response(timeout=0.5)
                
                if response and response.get("cmd") == "WATCHDOG_ECHO":
                    end_time = datetime.now(timezone.utc)
                    latency_ms = (end_time - start_time).total_seconds() * 1000
                    
                    self.status.watchdog_active = True
                    self.status.last_watchdog_echo = response.get("echo", "")
                    self.status.watchdog_latency_ms = latency_ms
                    
                    logger.debug(f"Watchdog echo received: {latency_ms:.2f}ms")
                else:
                    self.status.watchdog_active = False
                    logger.warning("Watchdog echo timeout")
                
                # Update uptime
                if response and "uptime" in response:
                    self.status.uptime_seconds = response["uptime"]
                
                # Wait before next ping (2 Hz)
                await asyncio.sleep(0.5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchdog loop error: {e}")
                self.status.watchdog_active = False
                await asyncio.sleep(1.0)
    
    async def _read_loop(self):
        """Continuous read loop for RoboHAT messages"""
        while self.running:
            try:
                response = await self._read_response(timeout=0.1)
                
                if response:
                    self._process_message(response)
                
                await asyncio.sleep(0.01)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Read loop error: {e}")
                await asyncio.sleep(0.1)
    
    def _process_message(self, message: Dict[str, Any]):
        """Process incoming message from RoboHAT"""
        msg_type = message.get("type", "")
        
        if msg_type == "status":
            # Update status from periodic status messages
            self.status.motor_controller_ok = message.get("motor_ok", False)
            self.status.encoder_feedback_ok = message.get("encoder_ok", False)
            
        elif msg_type == "error":
            # Handle error message
            error_msg = message.get("message", "Unknown error")
            logger.error(f"RoboHAT error: {error_msg}")
            self.status.error_count += 1
            self.status.last_error = error_msg
            
        elif msg_type == "motor_feedback":
            # Motor encoder feedback (could be forwarded to motor service)
            logger.debug(f"Motor feedback: {message}")
    
    async def send_motor_command(self, left_speed: float, right_speed: float) -> bool:
        """Send motor command to RoboHAT"""
        params = {
            "left_speed": int(left_speed * 100),  # -100 to 100
            "right_speed": int(right_speed * 100)
        }
        return await self._send_command("MOTOR_COMMAND", params)
    
    async def send_blade_command(self, active: bool, speed: float = 1.0) -> bool:
        """Send blade motor command to RoboHAT"""
        params = {
            "active": active,
            "speed": int(speed * 100)  # 0 to 100
        }
        return await self._send_command("BLADE_COMMAND", params)
    
    async def emergency_stop(self) -> bool:
        """Send emergency stop command to RoboHAT"""
        logger.critical("Sending emergency stop to RoboHAT")
        return await self._send_command("EMERGENCY_STOP")
    
    async def clear_emergency(self) -> bool:
        """Clear emergency stop on RoboHAT"""
        logger.info("Clearing emergency stop on RoboHAT")
        return await self._send_command("CLEAR_EMERGENCY")
    
    def get_status(self) -> RoboHATStatus:
        """Get current RoboHAT status"""
        self.status.timestamp = datetime.now(timezone.utc)
        return self.status
    
    async def shutdown(self):
        """Shutdown RoboHAT service"""
        logger.info("Shutting down RoboHAT service")
        
        self.running = False
        
        # Cancel background tasks
        if self.watchdog_task:
            self.watchdog_task.cancel()
            try:
                await self.watchdog_task
            except asyncio.CancelledError:
                pass
        
        if self.read_task:
            self.read_task.cancel()
            try:
                await self.read_task
            except asyncio.CancelledError:
                pass
        
        # Close serial connection
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        
        self.status.serial_connected = False
        logger.info("RoboHAT service shutdown complete")


# Global RoboHAT service instance
robohat_service: Optional[RoboHATService] = None


def get_robohat_service() -> Optional[RoboHATService]:
    """Get global RoboHAT service instance"""
    return robohat_service


async def initialize_robohat_service(serial_port: str = "/dev/ttyACM0", baud_rate: int = 115200) -> bool:
    """Initialize global RoboHAT service"""
    global robohat_service
    
    if robohat_service is None:
        robohat_service = RoboHATService(serial_port, baud_rate)
    
    return await robohat_service.initialize()


async def shutdown_robohat_service():
    """Shutdown global RoboHAT service"""
    global robohat_service
    
    if robohat_service:
        await robohat_service.shutdown()
        robohat_service = None
