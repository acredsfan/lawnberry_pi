"""
MQTT Broker Management
Handles local Mosquitto broker setup and management
"""

import asyncio
import logging
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional
import tempfile
import os


class MQTTBroker:
    """Local Mosquitto MQTT Broker Manager"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.logger = logging.getLogger(__name__)
        self.config = config or self._default_config()
        self.process: Optional[subprocess.Popen] = None
        self.config_file: Optional[Path] = None
        self._running = False
        
    def _default_config(self) -> Dict[str, Any]:
        """Default broker configuration"""
        return {
            'port': 1883,
            'bind_address': 'localhost',
            'keepalive': 60,
            'max_connections': 100,
            'persistence': True,
            'persistence_location': '/tmp/mosquitto_persistence',
            'log_level': 'warning',
            'allow_anonymous': True,  # For local development
            'auth': {
                'enabled': False,
                'username': 'lawnberry',
                'password': 'secure_password'
            },
            'tls': {
                'enabled': False,
                'cert_file': None,
                'key_file': None,
                'ca_file': None
            },
            'websockets': {
                'enabled': True,
                'port': 9001
            }
        }
    
    async def start(self) -> bool:
        """Start the Mosquitto broker"""
        if self._running:
            self.logger.info("MQTT broker already running")
            return True
            
        try:
            # Check if mosquitto is installed
            result = subprocess.run(['which', 'mosquitto'], 
                                  capture_output=True, text=True)
            if result.returncode != 0:
                self.logger.error("Mosquitto not installed. Install with: sudo apt-get install mosquitto")
                return False
            
            # Generate configuration file
            self.config_file = await self._generate_config()
            
            # Start mosquitto process
            cmd = ['mosquitto', '-c', str(self.config_file)]
            self.logger.info(f"Starting Mosquitto broker with command: {' '.join(cmd)}")
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )
            
            # Wait a moment for startup
            await asyncio.sleep(1)
            
            # Check if process is still running
            if self.process.poll() is None:
                self._running = True
                self.logger.info(f"MQTT broker started on port {self.config['port']}")
                return True
            else:
                stdout, stderr = self.process.communicate()
                self.logger.error(f"Failed to start MQTT broker: {stderr.decode()}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error starting MQTT broker: {e}")
            return False
    
    async def stop(self):
        """Stop the Mosquitto broker"""
        if not self._running:
            return
            
        try:
            if self.process:
                # Terminate process group
                os.killpg(os.getpgid(self.process.pid), 15)  # SIGTERM
                
                # Wait for graceful shutdown
                for _ in range(50):  # 5 second timeout
                    if self.process.poll() is not None:
                        break
                    await asyncio.sleep(0.1)
                
                # Force kill if still running
                if self.process.poll() is None:
                    os.killpg(os.getpgid(self.process.pid), 9)  # SIGKILL
                
                self.process = None
            
            # Clean up config file
            if self.config_file and self.config_file.exists():
                self.config_file.unlink()
                
            self._running = False
            self.logger.info("MQTT broker stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping MQTT broker: {e}")
    
    async def _generate_config(self) -> Path:
        """Generate Mosquitto configuration file"""
        config_content = [
            f"port {self.config['port']}",
            f"bind_address {self.config['bind_address']}",
            f"max_connections {self.config['max_connections']}",
            f"log_type {self.config['log_level']}",
        ]
        
        # Persistence settings
        if self.config['persistence']:
            os.makedirs(self.config['persistence_location'], exist_ok=True)
            config_content.extend([
                "persistence true",
                f"persistence_location {self.config['persistence_location']}"
            ])
        else:
            config_content.append("persistence false")
        
        # Authentication
        if self.config['auth']['enabled']:
            # Create password file
            pass_file = Path(tempfile.gettempdir()) / "mosquitto_passwd"
            subprocess.run([
                'mosquitto_passwd', '-c', '-b', str(pass_file),
                self.config['auth']['username'],
                self.config['auth']['password']
            ])
            config_content.extend([
                "allow_anonymous false",
                f"password_file {pass_file}"
            ])
        else:
            config_content.append("allow_anonymous true")
        
        # TLS settings
        if self.config['tls']['enabled']:
            config_content.extend([
                f"cafile {self.config['tls']['ca_file']}",
                f"certfile {self.config['tls']['cert_file']}",
                f"keyfile {self.config['tls']['key_file']}"
            ])
        
        # WebSocket support
        if self.config['websockets']['enabled']:
            config_content.extend([
                f"listener {self.config['websockets']['port']}",
                "protocol websockets"
            ])
        
        # Write configuration file
        config_file = Path(tempfile.gettempdir()) / "mosquitto_lawnberry.conf"
        with open(config_file, 'w') as f:
            f.write('\n'.join(config_content))
        
        return config_file
    
    def is_running(self) -> bool:
        """Check if broker is running"""
        if not self._running or not self.process:
            return False
        return self.process.poll() is None
    
    async def get_status(self) -> Dict[str, Any]:
        """Get broker status information"""
        return {
            'running': self.is_running(),
            'port': self.config['port'],
            'bind_address': self.config['bind_address'],
            'websocket_port': self.config['websockets']['port'] if self.config['websockets']['enabled'] else None,
            'auth_enabled': self.config['auth']['enabled'],
            'tls_enabled': self.config['tls']['enabled'],
            'persistence_enabled': self.config['persistence']
        }
