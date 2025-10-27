"""Inter-Process Communication (IPC) sockets and coordination contracts.

This module provides IPC mechanisms for coordinating between different LawnBerry Pi
services, including sensor data exchange, hardware control commands, and system
status synchronization using Unix domain sockets and message queues.
"""
import json
import logging
import socket
import threading
import time
import queue
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, asdict
from enum import Enum
import struct
import select

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """IPC message types for service coordination."""
    SENSOR_DATA = "sensor_data"
    MOTOR_COMMAND = "motor_command"
    SAFETY_STATUS = "safety_status"
    SYSTEM_STATUS = "system_status"
    CONFIG_UPDATE = "config_update"
    HEALTH_CHECK = "health_check"
    SHUTDOWN = "shutdown"


@dataclass
class IPCMessage:
    """Standard IPC message format."""
    message_type: str
    timestamp: float
    source_service: str
    target_service: str = "all"
    data: Dict[str, Any] = None
    correlation_id: str = ""
    
    def __post_init__(self):
        if self.data is None:
            self.data = {}


@dataclass
class SensorDataMessage:
    """Sensor data IPC message."""
    imu_data: Dict[str, float]
    battery_voltage: float
    current_draw: float
    tof_distances: List[Dict[str, Any]]
    gps_position: Dict[str, float]
    environmental: Dict[str, float]


@dataclass
class MotorCommandMessage:
    """Motor control IPC message."""
    left_motor_pwm: int
    right_motor_pwm: int
    blade_motor_pwm: int
    motor_enable: bool
    emergency_stop: bool


@dataclass
class SafetyStatusMessage:
    """Safety status IPC message."""
    emergency_stop_active: bool
    tilt_detected: bool
    obstacle_detected: bool
    blade_safety_ok: bool
    safety_interlocks: List[str]


class IPCSocket:
    """Unix domain socket for IPC communication."""
    
    def __init__(self, socket_path: str, is_server: bool = False):
        self.socket_path = Path(socket_path)
        self.is_server = is_server
        self.socket = None
        self.connected = False
        self._stop_event = threading.Event()
        
        # Create socket directory
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        
        if self.is_server:
            # Remove existing socket file
            if self.socket_path.exists():
                self.socket_path.unlink()
    
    def start_server(self, message_handler: Callable[[IPCMessage], None]):
        """Start IPC server to handle incoming messages."""
        if not self.is_server:
            raise ValueError("Not configured as server")
        
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(str(self.socket_path))
        self.socket.listen(5)
        self.socket.settimeout(1.0)  # Non-blocking accept
        
        logger.info(f"IPC server listening on {self.socket_path}")
        
        def server_thread():
            while not self._stop_event.is_set():
                try:
                    conn, addr = self.socket.accept()
                    # Handle client in separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(conn, message_handler),
                        daemon=True
                    )
                    client_thread.start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if not self._stop_event.is_set():
                        logger.error(f"Server error: {e}")
        
        threading.Thread(target=server_thread, daemon=True).start()
    
    def _handle_client(self, conn: socket.socket, handler: Callable[[IPCMessage], None]):
        """Handle client connection."""
        try:
            while not self._stop_event.is_set():
                # Read message length (4 bytes)
                length_data = self._recv_all(conn, 4)
                if not length_data:
                    break
                
                message_length = struct.unpack('!I', length_data)[0]
                
                # Read message data
                message_data = self._recv_all(conn, message_length)
                if not message_data:
                    break
                
                # Parse and handle message
                try:
                    message_dict = json.loads(message_data.decode('utf-8'))
                    message = IPCMessage(**message_dict)
                    handler(message)
                except (json.JSONDecodeError, TypeError) as e:
                    logger.error(f"Invalid message format: {e}")
                
        except Exception as e:
            logger.error(f"Client handler error: {e}")
        finally:
            conn.close()
    
    def _recv_all(self, conn: socket.socket, length: int) -> bytes:
        """Receive exact number of bytes."""
        data = b''
        while len(data) < length:
            packet = conn.recv(length - len(data))
            if not packet:
                break
            data += packet
        return data
    
    def connect_client(self) -> bool:
        """Connect as client to IPC server."""
        if self.is_server:
            raise ValueError("Cannot connect as client when configured as server")
        
        try:
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.connect(str(self.socket_path))
            self.connected = True
            logger.info(f"Connected to IPC server at {self.socket_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to IPC server: {e}")
            return False
    
    def send_message(self, message: IPCMessage) -> bool:
        """Send message to IPC server."""
        if not self.connected or not self.socket:
            return False
        
        try:
            # Serialize message
            message_json = json.dumps(asdict(message))
            message_bytes = message_json.encode('utf-8')
            
            # Send length followed by data
            length = struct.pack('!I', len(message_bytes))
            self.socket.sendall(length + message_bytes)
            return True
            
        except Exception as e:
            logger.error(f"Failed to send IPC message: {e}")
            self.connected = False
            return False
    
    def close(self):
        """Close IPC socket."""
        self._stop_event.set()
        
        if self.socket:
            self.socket.close()
            self.socket = None
        
        if self.is_server and self.socket_path.exists():
            self.socket_path.unlink()
        
        self.connected = False


class IPCCoordinator:
    """Central coordinator for IPC communication between services."""
    
    def __init__(self, service_name: str, ipc_dir: str = "./run/ipc"):
        self.service_name = service_name
        self.ipc_dir = Path(ipc_dir)
        self.ipc_dir.mkdir(parents=True, exist_ok=True)
        
        self._servers: Dict[str, IPCSocket] = {}
        self._clients: Dict[str, IPCSocket] = {}
        self._message_handlers: Dict[str, Callable[[IPCMessage], None]] = {}
        self._message_queue = queue.Queue()
        
        # Start message processing thread
        self._stop_event = threading.Event()
        self._processor_thread = threading.Thread(target=self._process_messages, daemon=True)
        self._processor_thread.start()
    
    def create_server(self, endpoint_name: str, handler: Callable[[IPCMessage], None]):
        """Create IPC server endpoint."""
        socket_path = self.ipc_dir / f"{self.service_name}_{endpoint_name}.sock"
        server = IPCSocket(str(socket_path), is_server=True)
        server.start_server(lambda msg: self._message_queue.put((endpoint_name, msg)))
        
        self._servers[endpoint_name] = server
        self._message_handlers[endpoint_name] = handler
        
        logger.info(f"Created IPC server endpoint: {endpoint_name}")
    
    def connect_to_service(self, target_service: str, endpoint_name: str) -> bool:
        """Connect to another service's IPC endpoint."""
        socket_path = self.ipc_dir / f"{target_service}_{endpoint_name}.sock"
        client = IPCSocket(str(socket_path), is_server=False)
        
        if client.connect_client():
            self._clients[f"{target_service}_{endpoint_name}"] = client
            return True
        return False
    
    def send_to_service(self, target_service: str, endpoint_name: str, 
                       message_type: MessageType, data: Dict[str, Any]) -> bool:
        """Send message to another service."""
        client_key = f"{target_service}_{endpoint_name}"
        
        if client_key not in self._clients:
            # Try to connect
            if not self.connect_to_service(target_service, endpoint_name):
                return False
        
        message = IPCMessage(
            message_type=message_type.value,
            timestamp=time.time(),
            source_service=self.service_name,
            target_service=target_service,
            data=data
        )
        
        return self._clients[client_key].send_message(message)
    
    def broadcast_message(self, message_type: MessageType, data: Dict[str, Any]):
        """Broadcast message to all connected services."""
        message = IPCMessage(
            message_type=message_type.value,
            timestamp=time.time(),
            source_service=self.service_name,
            target_service="all",
            data=data
        )
        
        for client in self._clients.values():
            client.send_message(message)
    
    def _process_messages(self):
        """Process incoming messages from queue."""
        while not self._stop_event.is_set():
            try:
                endpoint_name, message = self._message_queue.get(timeout=1.0)
                
                if endpoint_name in self._message_handlers:
                    handler = self._message_handlers[endpoint_name]
                    handler(message)
                else:
                    logger.warning(f"No handler for endpoint: {endpoint_name}")
                    
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing IPC message: {e}")
    
    def shutdown(self):
        """Shutdown IPC coordinator."""
        self._stop_event.set()
        
        # Close all servers and clients
        for server in self._servers.values():
            server.close()
        
        for client in self._clients.values():
            client.close()
        
        # Wait for processor thread
        if self._processor_thread.is_alive():
            self._processor_thread.join(timeout=5.0)


class ServiceCoordinationContracts:
    """Defines IPC contracts between LawnBerry Pi services."""
    
    @staticmethod
    def create_backend_coordinator() -> IPCCoordinator:
        """Create IPC coordinator for backend service."""
        coordinator = IPCCoordinator("backend")
        
        # Backend receives sensor data from sensor service
        def handle_sensor_data(message: IPCMessage):
            logger.info(f"Received sensor data: {message.data}")
            # Update WebSocket clients with telemetry
            # This would integrate with the WebSocket hub
        
        # Backend receives safety status updates
        def handle_safety_status(message: IPCMessage):
            logger.info(f"Safety status update: {message.data}")
            # Update system safety state
        
        coordinator.create_server("telemetry", handle_sensor_data)
        coordinator.create_server("safety", handle_safety_status)
        
        return coordinator
    
    @staticmethod
    def create_sensor_coordinator() -> IPCCoordinator:
        """Create IPC coordinator for sensor service."""
        coordinator = IPCCoordinator("sensors")
        
        # Sensor service receives motor commands from backend
        def handle_motor_commands(message: IPCMessage):
            logger.info(f"Motor command received: {message.data}")
            # Execute motor control commands
        
        coordinator.create_server("control", handle_motor_commands)
        
        # Connect to backend for sending telemetry
        coordinator.connect_to_service("backend", "telemetry")
        
        return coordinator
    
    @staticmethod
    def send_sensor_data(coordinator: IPCCoordinator, sensor_data: SensorDataMessage):
        """Send sensor data to backend service."""
        coordinator.send_to_service(
            "backend", 
            "telemetry",
            MessageType.SENSOR_DATA,
            asdict(sensor_data)
        )
    
    @staticmethod
    def send_motor_command(coordinator: IPCCoordinator, motor_cmd: MotorCommandMessage):
        """Send motor command to sensor service."""
        coordinator.send_to_service(
            "sensors",
            "control", 
            MessageType.MOTOR_COMMAND,
            asdict(motor_cmd)
        )
    
    @staticmethod
    def send_safety_alert(coordinator: IPCCoordinator, safety_status: SafetyStatusMessage):
        """Broadcast safety alert to all services."""
        coordinator.broadcast_message(
            MessageType.SAFETY_STATUS,
            asdict(safety_status)
        )