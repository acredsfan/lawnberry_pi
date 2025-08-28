"""
Deployment Manager - Automated deployment system with A/B deployment and security updates
Handles system updates, rollbacks, and fleet management for Lawnberry autonomous mower
"""

import asyncio
import logging
import json
import hashlib
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Callable, Awaitable
from dataclasses import dataclass, asdict
from enum import Enum
import aiofiles
import aiohttp
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.exceptions import InvalidSignature

from .config_manager import ConfigManager
from .health_monitor import HealthMonitor
from .state_machine import SystemStateMachine, SystemState
from .deployment_events import build_event, DeploymentLifecycleEvent


logger = logging.getLogger(__name__)


class DeploymentType(Enum):
    """Types of deployments"""
    SECURITY = "security"
    BUG_FIX = "bug_fix"
    FEATURE = "feature"
    CONFIGURATION = "configuration"
    EMERGENCY = "emergency"


class DeploymentStatus(Enum):
    """Deployment status"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    STAGING = "staging"
    TESTING = "testing"
    DEPLOYING = "deploying"
    ACTIVE = "active"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class DeploymentPackage:
    """Deployment package information"""
    version: str
    package_type: DeploymentType
    checksum: str
    signature: str
    download_url: str
    size: int
    created_at: datetime
    priority: int  # 1=emergency, 2=security, 3=bug_fix, 4=feature
    metadata: Dict[str, Any]


@dataclass
class DeploymentState:
    """Current deployment state"""
    active_partition: str  # 'A' or 'B'
    active_version: str
    standby_partition: str
    standby_version: Optional[str]
    last_deployment: Optional[datetime]
    rollback_available: bool
    health_check_passed: bool
    deployment_in_progress: bool


class DeploymentManager:
    """
    Manages automated deployments with A/B deployment, security updates, and fleet management
    """
    
    def __init__(self, config_manager: ConfigManager, health_monitor: HealthMonitor, 
                 state_machine: SystemStateMachine):
        self.config_manager = config_manager
        self.health_monitor = health_monitor
        self.state_machine = state_machine
        
        # Deployment configuration
        self.config = self._load_deployment_config()
        
        # System paths (use writable location under /var/lib for state)
        # NOTE: /opt/lawnberry is treated as an immutable runtime. All writable
        # deployment state must live under /var/lib/lawnberry to satisfy system
        # hardening and avoid read-only filesystem errors.
        self.deployment_dir = Path("/var/lib/lawnberry/deployments")
        self.partition_a_path = self.deployment_dir / "partition_a"
        self.partition_b_path = self.deployment_dir / "partition_b"
        self.backup_dir = Path("/var/lib/lawnberry/backups")
        self.staging_dir = Path("/tmp/lawnberry_staging")
        
        # Current state
        self.deployment_state = DeploymentState(
            active_partition="A",
            active_version="1.0.0",
            standby_partition="B",
            standby_version=None,
            last_deployment=None,
            rollback_available=False,
            health_check_passed=True,
            deployment_in_progress=False
        )
        
        # Update checking
        self.update_check_interval = self.config.get('update_check_interval', 3600)  # 1 hour
        self.security_update_priority = True
        
        # Fleet management
        self.device_id = self._get_device_id()
        self.fleet_config = self.config.get('fleet', {})
        
        # Cryptographic verification
        self.public_key = self._load_public_key()
        
        # Background tasks
        self._update_checker_task: Optional[asyncio.Task] = None
        self._deployment_task: Optional[asyncio.Task] = None
        # Optional async publisher (topic, payload)
        self._event_publisher: Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]] = None

    def register_event_publisher(self, publisher: Callable[[str, Dict[str, Any]], Awaitable[None]]):
        """Register async publisher for deployment events."""
        self._event_publisher = publisher

    async def _emit_event(self, payload: Dict[str, Any]):
        if not self._event_publisher:
            return
        try:
            await self._event_publisher("deployment/events", payload)
        except Exception as e:  # pragma: no cover
            logger.debug(f"Deployment event publish failed: {e}")
        
    def _load_deployment_config(self) -> Dict[str, Any]:
        """Load deployment configuration"""
        try:
            config = self.config_manager.get_config('deployment')
            return config if config else self._default_deployment_config()
        except Exception as e:
            logger.warning(f"Failed to load deployment config, using defaults: {e}")
            return self._default_deployment_config()
    
    def _default_deployment_config(self) -> Dict[str, Any]:
        """Default deployment configuration"""
        return {
            'update_server_url': 'https://updates.lawnberry.com/api/v1',
            'update_check_interval': 3600,
            'security_update_priority': True,
            'auto_deploy_security': True,
            'auto_deploy_bug_fixes': True,
            'auto_deploy_features': False,
            'health_check_timeout': 300,
            'deployment_timeout': 1800,
            'rollback_timeout': 300,
            'max_retry_attempts': 3,
            'fleet': {
                'enabled': False,
                'group_id': 'default',
                'deployment_wave': 1
            },
            'backup': {
                'retention_days': 30,
                'max_backups': 10
            }
        }
    
    def _get_device_id(self) -> str:
        """Get unique device identifier"""
        try:
            # Use MAC address or create persistent device ID
            import uuid
            device_id_file = Path("/var/lib/lawnberry/device_id")
            
            if device_id_file.exists():
                return device_id_file.read_text().strip()
            else:
                device_id = str(uuid.uuid4())
                device_id_file.parent.mkdir(parents=True, exist_ok=True)
                device_id_file.write_text(device_id)
                return device_id
        except Exception as e:
            logger.error(f"Failed to get device ID: {e}")
            return "unknown"
    
    def _load_public_key(self):
        """Load public key for signature verification"""
        try:
            # Prefer var-lib writable location; fall back to /opt if provisioned there
            candidates = [
                Path("/var/lib/lawnberry/keys/deployment_public.pem"),
                Path("/opt/lawnberry/keys/deployment_public.pem"),
            ]
            for public_key_path in candidates:
                if public_key_path.exists():
                    with open(public_key_path, 'rb') as f:
                        return serialization.load_pem_public_key(f.read())
            logger.warning("Deployment public key not found, signature verification disabled")
            return None
        except Exception as e:
            logger.error(f"Failed to load public key: {e}")
            return None
    
    async def initialize(self):
        """Initialize deployment manager"""
        try:
            logger.info("Initializing Deployment Manager")
            
            # Create directories
            for path in [self.deployment_dir, self.partition_a_path, 
                        self.partition_b_path, self.backup_dir, self.staging_dir]:
                path.mkdir(parents=True, exist_ok=True)
            
            # Load current deployment state
            await self._load_deployment_state()
            
            # Start background tasks
            self._update_checker_task = asyncio.create_task(self._update_checker_loop())
            
            logger.info("Deployment Manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Deployment Manager: {e}")
            raise
    
    async def shutdown(self):
        """Shutdown deployment manager"""
        logger.info("Shutting down Deployment Manager")
        
        # Cancel background tasks
        if self._update_checker_task:
            self._update_checker_task.cancel()
            try:
                await self._update_checker_task
            except asyncio.CancelledError:
                pass
        
        if self._deployment_task:
            self._deployment_task.cancel()
            try:
                await self._deployment_task
            except asyncio.CancelledError:
                pass
    
    async def _load_deployment_state(self):
        """Load current deployment state from disk"""
        try:
            state_file = self.deployment_dir / "deployment_state.json"
            if state_file.exists():
                async with aiofiles.open(state_file, 'r') as f:
                    data = json.loads(await f.read())
                    # Convert datetime strings back to datetime objects
                    if data.get('last_deployment'):
                        data['last_deployment'] = datetime.fromisoformat(data['last_deployment'])
                    self.deployment_state = DeploymentState(**data)
            
            # Verify current deployment
            await self._verify_current_deployment()
            
        except Exception as e:
            logger.error(f"Failed to load deployment state: {e}")
            # Use default state
    
    async def _save_deployment_state(self):
        """Save deployment state to disk"""
        try:
            state_file = self.deployment_dir / "deployment_state.json"
            data = asdict(self.deployment_state)
            # Convert datetime to string for JSON serialization
            if data.get('last_deployment'):
                data['last_deployment'] = data['last_deployment'].isoformat()
            
            async with aiofiles.open(state_file, 'w') as f:
                await f.write(json.dumps(data, indent=2))
                
        except Exception as e:
            logger.error(f"Failed to save deployment state: {e}")
    
    async def _verify_current_deployment(self):
        """Verify current deployment integrity"""
        try:
            active_path = self.partition_a_path if self.deployment_state.active_partition == 'A' else self.partition_b_path
            
            # Check if deployment exists and is valid
            if not active_path.exists() or not (active_path / "src").exists():
                logger.warning("Active deployment not found or invalid")
                self.deployment_state.health_check_passed = False
                return False
            
            # Perform basic health check
            health_ok = await self._perform_health_check(active_path)
            self.deployment_state.health_check_passed = health_ok
            
            return health_ok
            
        except Exception as e:
            logger.error(f"Failed to verify current deployment: {e}")
            self.deployment_state.health_check_passed = False
            return False
    
    async def _perform_health_check(self, deployment_path: Path) -> bool:
        """Perform health check on a deployment"""
        try:
            # Check critical files exist
            critical_files = [
                "src/system_integration/system_manager.py",
                "src/hardware/__init__.py",
                "src/safety/__init__.py",
                "config/system.yaml"
            ]
            
            for file_path in critical_files:
                if not (deployment_path / file_path).exists():
                    logger.error(f"Critical file missing: {file_path}")
                    return False
            
            # Run system health checks through health monitor
            if hasattr(self.health_monitor, 'run_deployment_health_check'):
                return await self.health_monitor.run_deployment_health_check(deployment_path)
            
            return True
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def _update_checker_loop(self):
        """Background loop to check for updates"""
        while True:
            try:
                await self._check_for_updates()
                await asyncio.sleep(self.update_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Update checker error: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    async def _check_for_updates(self):
        """Check for available updates"""
        try:
            if self.deployment_state.deployment_in_progress:
                return
            
            update_url = f"{self.config['update_server_url']}/check"
            params = {
                'device_id': self.device_id,
                'current_version': self.deployment_state.active_version,
                'group_id': self.fleet_config.get('group_id', 'default')
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(update_url, params=params) as response:
                    if response.status == 200:
                        update_info = await response.json()
                        
                        if update_info.get('update_available'):
                            package = DeploymentPackage(**update_info['package'])
                            await self._handle_available_update(package)
                    
        except Exception as e:
            logger.error(f"Failed to check for updates: {e}")
    
    async def _handle_available_update(self, package: DeploymentPackage):
        """Handle an available update based on type and configuration"""
        try:
            logger.info(f"Update available: {package.version} ({package.package_type.value})")
            
            # Determine if auto-deployment should occur
            should_auto_deploy = False
            
            if package.package_type == DeploymentType.EMERGENCY:
                should_auto_deploy = True
            elif package.package_type == DeploymentType.SECURITY:
                should_auto_deploy = self.config.get('auto_deploy_security', True)
            elif package.package_type == DeploymentType.BUG_FIX:
                should_auto_deploy = self.config.get('auto_deploy_bug_fixes', True)
            elif package.package_type == DeploymentType.FEATURE:
                should_auto_deploy = self.config.get('auto_deploy_features', False)
            
            if should_auto_deploy:
                # Schedule deployment
                self._deployment_task = asyncio.create_task(
                    self._deploy_update(package)
                )
            else:
                logger.info(f"Update {package.version} available but auto-deploy disabled for {package.package_type.value}")
                # Notify about available update
                await self._notify_update_available(package)
                
        except Exception as e:
            logger.error(f"Failed to handle available update: {e}")
    
    async def _deploy_update(self, package: DeploymentPackage) -> bool:
        """Deploy an update using A/B deployment"""
        try:
            self.deployment_state.deployment_in_progress = True
            await self._save_deployment_state()
            
            logger.info(f"Starting deployment of {package.version}")
            await self._notify_deployment_started(package)
            
            # Determine target partition
            target_partition = 'B' if self.deployment_state.active_partition == 'A' else 'A'
            target_path = self.partition_b_path if target_partition == 'B' else self.partition_a_path
            
            # Download and verify package
            if not await self._download_package(package, target_path):
                raise Exception("Package download failed")
            
            # Backup current configuration
            await self._backup_current_deployment()
            
            # Deploy to staging
            if not await self._stage_deployment(package, target_path):
                raise Exception("Staging deployment failed")
            
            # Run health checks on staged deployment
            if not await self._perform_health_check(target_path):
                raise Exception("Health check failed on staged deployment")
            
            # Switch to new deployment
            await self._switch_deployment(target_partition, package.version)
            
            # Final health check
            await asyncio.sleep(10)  # Allow system to stabilize
            if not await self._verify_current_deployment():
                logger.error("Post-deployment health check failed, rolling back")
                await self.rollback_deployment()
                return False
            
            # Mark deployment as successful
            self.deployment_state.last_deployment = datetime.now()
            self.deployment_state.rollback_available = True
            self.deployment_state.deployment_in_progress = False
            await self._save_deployment_state()
            
            logger.info(f"Successfully deployed {package.version}")
            await self._notify_deployment_success(package)
            
            return True
            
        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            self.deployment_state.deployment_in_progress = False
            await self._save_deployment_state()
            await self._notify_deployment_failure(package, str(e))
            return False
    
    async def _download_package(self, package: DeploymentPackage, target_path: Path) -> bool:
        """Download and verify deployment package"""
        try:
            logger.info(f"Downloading package {package.version}")
            
            # Create staging directory
            staging_path = self.staging_dir / f"package_{package.version}"
            staging_path.mkdir(parents=True, exist_ok=True)
            
            # Download package
            async with aiohttp.ClientSession() as session:
                async with session.get(package.download_url) as response:
                    if response.status != 200:
                        raise Exception(f"Download failed with status {response.status}")
                    
                    package_file = staging_path / "package.tar.gz"
                    async with aiofiles.open(package_file, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
            
            # Verify checksum
            if not await self._verify_checksum(package_file, package.checksum):
                raise Exception("Checksum verification failed")
            
            # Verify signature
            if self.public_key and not await self._verify_signature(package_file, package.signature):
                raise Exception("Signature verification failed")
            
            # Extract package
            await self._extract_package(package_file, target_path)
            
            # Cleanup staging
            shutil.rmtree(staging_path, ignore_errors=True)
            
            return True
            
        except Exception as e:
            logger.error(f"Package download failed: {e}")
            return False
    
    async def _verify_checksum(self, file_path: Path, expected_checksum: str) -> bool:
        """Verify file checksum"""
        try:
            sha256_hash = hashlib.sha256()
            async with aiofiles.open(file_path, 'rb') as f:
                while chunk := await f.read(8192):
                    sha256_hash.update(chunk)
            
            calculated_checksum = sha256_hash.hexdigest()
            return calculated_checksum == expected_checksum
            
        except Exception as e:
            logger.error(f"Checksum verification failed: {e}")
            return False
    
    async def _verify_signature(self, file_path: Path, signature: str) -> bool:
        """Verify package signature"""
        try:
            if not self.public_key:
                logger.warning("No public key available for signature verification")
                return True  # Skip verification if no key
            
            # Read file content
            async with aiofiles.open(file_path, 'rb') as f:
                file_content = await f.read()
            
            # Decode signature from base64
            import base64
            signature_bytes = base64.b64decode(signature)
            
            # Verify signature
            self.public_key.verify(
                signature_bytes,
                file_content,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            return True
            
        except InvalidSignature:
            logger.error("Invalid package signature")
            return False
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False
    
    async def _extract_package(self, package_file: Path, target_path: Path):
        """Extract deployment package"""
        try:
            # Remove existing deployment
            if target_path.exists():
                shutil.rmtree(target_path)
            
            target_path.mkdir(parents=True, exist_ok=True)
            
            # Extract package
            import tarfile
            with tarfile.open(package_file, 'r:gz') as tar:
                tar.extractall(target_path)
            
        except Exception as e:
            logger.error(f"Package extraction failed: {e}")
            raise
    
    async def _backup_current_deployment(self):
        """Backup current deployment and configuration"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / f"backup_{timestamp}"
            backup_path.mkdir(parents=True, exist_ok=True)
            
            # Backup current deployment
            active_path = self.partition_a_path if self.deployment_state.active_partition == 'A' else self.partition_b_path
            if active_path.exists():
                shutil.copytree(active_path, backup_path / "deployment")
            
            # Backup configuration
            config_path = Path("/opt/lawnberry/config")
            if config_path.exists():
                shutil.copytree(config_path, backup_path / "config")
            
            # Backup state
            state_data = {
                'deployment_state': asdict(self.deployment_state),
                'backup_timestamp': timestamp,
                'active_version': self.deployment_state.active_version
            }
            
            async with aiofiles.open(backup_path / "backup_info.json", 'w') as f:
                await f.write(json.dumps(state_data, indent=2, default=str))
            
            # Cleanup old backups
            await self._cleanup_old_backups()
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            # Continue with deployment even if backup fails
    
    async def _cleanup_old_backups(self):
        """Remove old backup files based on retention policy"""
        try:
            retention_days = self.config.get('backup', {}).get('retention_days', 30)
            max_backups = self.config.get('backup', {}).get('max_backups', 10)
            
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            # Get all backup directories
            backups = []
            for backup_dir in self.backup_dir.iterdir():
                if backup_dir.is_dir() and backup_dir.name.startswith('backup_'):
                    try:
                        timestamp_str = backup_dir.name.replace('backup_', '')
                        backup_date = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                        backups.append((backup_date, backup_dir))
                    except ValueError:
                        continue
            
            # Sort by date (newest first)
            backups.sort(key=lambda x: x[0], reverse=True)
            
            # Remove old backups
            for i, (backup_date, backup_dir) in enumerate(backups):
                if i >= max_backups or backup_date < cutoff_date:
                    logger.info(f"Removing old backup: {backup_dir.name}")
                    shutil.rmtree(backup_dir, ignore_errors=True)
                    
        except Exception as e:
            logger.error(f"Backup cleanup failed: {e}")
    
    async def _stage_deployment(self, package: DeploymentPackage, target_path: Path) -> bool:
        """Stage deployment for testing"""
        try:
            # Validate deployment structure
            required_dirs = ["src", "config"]
            for dir_name in required_dirs:
                if not (target_path / dir_name).exists():
                    logger.error(f"Required directory missing: {dir_name}")
                    return False
            
            # Update configuration if needed
            await self._update_deployment_config(package, target_path)
            
            return True
            
        except Exception as e:
            logger.error(f"Staging failed: {e}")
            return False
    
    async def _update_deployment_config(self, package: DeploymentPackage, target_path: Path):
        """Update configuration for new deployment"""
        try:
            # Merge configuration changes from package metadata
            config_updates = package.metadata.get('config_updates', {})
            
            for config_name, updates in config_updates.items():
                config_file = target_path / "config" / f"{config_name}.yaml"
                if config_file.exists():
                    # Load current config
                    import yaml
                    with open(config_file, 'r') as f:
                        config_data = yaml.safe_load(f)
                    
                    # Apply updates
                    self._deep_update(config_data, updates)
                    
                    # Save updated config
                    with open(config_file, 'w') as f:
                        yaml.dump(config_data, f, default_flow_style=False)
                        
        except Exception as e:
            logger.error(f"Configuration update failed: {e}")
            # Continue with deployment
    
    def _deep_update(self, target: Dict, source: Dict):
        """Deep update dictionary"""
        for key, value in source.items():
            if isinstance(value, dict) and key in target and isinstance(target[key], dict):
                self._deep_update(target[key], value)
            else:
                target[key] = value
    
    async def _switch_deployment(self, target_partition: str, version: str):
        """Switch to new deployment"""
        try:
            logger.info(f"Switching to partition {target_partition} version {version}")
            
            # Update deployment state
            old_partition = self.deployment_state.active_partition
            old_version = self.deployment_state.active_version
            
            self.deployment_state.standby_partition = old_partition
            self.deployment_state.standby_version = old_version
            self.deployment_state.active_partition = target_partition
            self.deployment_state.active_version = version
            
            await self._save_deployment_state()
            
            # Update systemd service files to point to new partition
            await self._update_systemd_services(target_partition)
            
            # Restart system services
            await self._restart_system_services()
            
        except Exception as e:
            logger.error(f"Deployment switch failed: {e}")
            raise
    
    async def _update_systemd_services(self, partition: str):
        """Update systemd service files to use new partition"""
        try:
            partition_path = self.partition_a_path if partition == 'A' else self.partition_b_path
            
            # Update working directory in service files
            service_files = [
                "/etc/systemd/system/lawnberry-system.service",
                "/etc/systemd/system/lawnberry-hardware.service",
                "/etc/systemd/system/lawnberry-communication.service",
                "/etc/systemd/system/lawnberry-data.service",
                "/etc/systemd/system/lawnberry-sensor-fusion.service",
                "/etc/systemd/system/lawnberry-weather.service",
                "/etc/systemd/system/lawnberry-api.service"
            ]
            
            for service_file in service_files:
                service_path = Path(service_file)
                if service_path.exists():
                    # Read service file
                    content = service_path.read_text()
                    
                    # Update WorkingDirectory
                    content = content.replace(
                        "WorkingDirectory=/opt/lawnberry",
                        f"WorkingDirectory={partition_path}"
                    )
                    
                    # Update PYTHONPATH
                    content = content.replace(
                        "Environment=PYTHONPATH=/opt/lawnberry",
                        f"Environment=PYTHONPATH={partition_path}"
                    )
                    
                    # Write updated service file
                    service_path.write_text(content)
            
            # Reload systemd
            await self._run_command(["systemctl", "daemon-reload"])
            
        except Exception as e:
            logger.error(f"Failed to update systemd services: {e}")
            raise
    
    async def _restart_system_services(self):
        """Restart system services for new deployment"""
        try:
            services = [
                "lawnberry-system",
                "lawnberry-hardware", 
                "lawnberry-communication",
                "lawnberry-data",
                "lawnberry-sensor-fusion",
                "lawnberry-weather",
                "lawnberry-api"
            ]
            
            # Stop services in reverse order
            for service in reversed(services):
                await self._run_command(["systemctl", "stop", service])
                await asyncio.sleep(2)
            
            # Start services in order
            for service in services:
                await self._run_command(["systemctl", "start", service])
                await asyncio.sleep(5)  # Allow time for service to start
                
                # Check service status
                result = await self._run_command(["systemctl", "is-active", service])
                if result.returncode != 0:
                    logger.error(f"Failed to start service: {service}")
                    raise Exception(f"Service {service} failed to start")
                    
        except Exception as e:
            logger.error(f"Failed to restart services: {e}")
            raise
    
    async def _run_command(self, command: List[str]) -> subprocess.CompletedProcess:
        """Run system command"""
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            result = subprocess.CompletedProcess(
                command, process.returncode or 0, stdout, stderr
            )
            
            if result.returncode != 0:
                logger.warning(f"Command failed: {' '.join(command)}, stderr: {stderr.decode()}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to run command {' '.join(command)}: {e}")
            raise
    
    async def rollback_deployment(self) -> bool:
        """Rollback to previous deployment"""
        try:
            if not self.deployment_state.rollback_available:
                logger.error("No rollback available")
                return False
            
            logger.info("Rolling back deployment")
            
            # Switch back to standby partition
            old_partition = self.deployment_state.active_partition
            old_version = self.deployment_state.active_version
            
            self.deployment_state.active_partition = self.deployment_state.standby_partition
            self.deployment_state.active_version = self.deployment_state.standby_version or "unknown"
            self.deployment_state.standby_partition = old_partition
            self.deployment_state.standby_version = old_version
            
            await self._save_deployment_state()
            
            # Update systemd services
            await self._update_systemd_services(self.deployment_state.active_partition)
            
            # Restart services
            await self._restart_system_services()
            
            # Verify rollback
            await asyncio.sleep(10)
            if await self._verify_current_deployment():
                logger.info("Rollback successful")
                await self._notify_rollback_success()
                return True
            else:
                logger.error("Rollback failed health check")
                return False
                
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            await self._notify_rollback_failure(str(e))
            return False
    
    async def get_deployment_status(self) -> Dict[str, Any]:
        """Get current deployment status"""
        return {
            'active_partition': self.deployment_state.active_partition,
            'active_version': self.deployment_state.active_version,
            'standby_partition': self.deployment_state.standby_partition,
            'standby_version': self.deployment_state.standby_version,
            'last_deployment': self.deployment_state.last_deployment.isoformat() if self.deployment_state.last_deployment else None,
            'rollback_available': self.deployment_state.rollback_available,
            'health_check_passed': self.deployment_state.health_check_passed,
            'deployment_in_progress': self.deployment_state.deployment_in_progress,
            'device_id': self.device_id
        }
    
    async def manual_deploy(self, package_url: str, version: str, package_type: str = "manual") -> bool:
        """Manually deploy a package"""
        try:
            # Create deployment package
            package = DeploymentPackage(
                version=version,
                package_type=DeploymentType(package_type),
                checksum="",  # Skip checksum for manual deploy
                signature="",  # Skip signature for manual deploy
                download_url=package_url,
                size=0,
                created_at=datetime.now(),
                priority=3,
                metadata={}
            )
            
            return await self._deploy_update(package)
            
        except Exception as e:
            logger.error(f"Manual deployment failed: {e}")
            return False
    
    # Notification methods (to be implemented based on communication system)
    async def _notify_update_available(self, package: DeploymentPackage):
        logger.info(f"Update notification: {package.version} ({package.package_type.value})")
        await self._emit_event(build_event(
            DeploymentLifecycleEvent.UPDATE_AVAILABLE,
            status="available",
            version=package.version,
            package_type=package.package_type.value,
            message=f"Update {package.version} available ({package.package_type.value})",
            device_id=self.device_id,
            metadata={"priority": package.priority},
        ))

    async def _notify_deployment_started(self, package: DeploymentPackage):
        logger.info(f"Deployment started: {package.version}")
        await self._emit_event(build_event(
            DeploymentLifecycleEvent.DEPLOYMENT_STARTED,
            status="in_progress",
            version=package.version,
            package_type=package.package_type.value,
            message=f"Deployment started for {package.version}",
            device_id=self.device_id,
        ))

    async def _notify_deployment_success(self, package: DeploymentPackage):
        logger.info(f"Deployment success notification: {package.version}")
        await self._emit_event(build_event(
            DeploymentLifecycleEvent.DEPLOYMENT_SUCCESS,
            status="success",
            version=package.version,
            package_type=package.package_type.value,
            message=f"Deployment succeeded: {package.version}",
            device_id=self.device_id,
        ))

    async def _notify_deployment_failure(self, package: DeploymentPackage, error: str):
        logger.error(f"Deployment failure notification: {package.version} - {error}")
        await self._emit_event(build_event(
            DeploymentLifecycleEvent.DEPLOYMENT_FAILURE,
            status="failure",
            version=package.version if package else None,
            package_type=package.package_type.value if package else None,
            message=f"Deployment failed: {error}",
            device_id=self.device_id,
        ))

    async def _notify_rollback_success(self):
        logger.info("Rollback success notification")
        await self._emit_event(build_event(
            DeploymentLifecycleEvent.ROLLBACK_SUCCESS,
            status="success",
            version=self.deployment_state.active_version,
            package_type=None,
            message="Rollback succeeded",
            device_id=self.device_id,
        ))

    async def _notify_rollback_failure(self, error: str):
        logger.error(f"Rollback failure notification: {error}")
        await self._emit_event(build_event(
            DeploymentLifecycleEvent.ROLLBACK_FAILURE,
            status="failure",
            version=self.deployment_state.active_version,
            package_type=None,
            message=f"Rollback failed: {error}",
            device_id=self.device_id,
        ))
