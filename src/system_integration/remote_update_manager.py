"""
Remote Update Manager - Secure remote update system with user approval workflow
Handles secure update delivery, user approval, and automated rollback capabilities
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import aiofiles
import aiohttp
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from .config_manager import ConfigManager
from .deployment_manager import DeploymentManager, DeploymentPackage, DeploymentType
from .health_monitor import HealthMonitor
from .system_monitor import Alert, AlertLevel, SystemMonitor

logger = logging.getLogger(__name__)


class UpdateApprovalStatus(Enum):
    """Update approval status"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    AUTO_APPROVED = "auto_approved"


class UpdateNotificationMethod(Enum):
    """Update notification methods"""

    WEB_UI = "web_ui"
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    SYSTEM_LOG = "system_log"


@dataclass
class UpdateRequest:
    """Remote update request"""

    update_id: str
    package: DeploymentPackage
    approval_status: UpdateApprovalStatus
    notification_methods: List[UpdateNotificationMethod]
    approval_timeout: datetime
    auto_approve_conditions: Dict[str, Any]
    user_message: str
    changelog: str
    rollback_plan: str
    created_at: datetime
    approved_at: Optional[datetime]
    approved_by: Optional[str]


@dataclass
class UpdateApprovalRule:
    """Automatic approval rule"""

    rule_id: str
    name: str
    conditions: Dict[str, Any]
    auto_approve: bool
    delay_minutes: int
    notification_required: bool
    enabled: bool


class RemoteUpdateManager:
    """
    Manages secure remote updates with user approval workflow
    """

    def __init__(
        self,
        config_manager: ConfigManager,
        deployment_manager: DeploymentManager,
        system_monitor: SystemMonitor,
        health_monitor: HealthMonitor,
    ):
        self.config_manager = config_manager
        self.deployment_manager = deployment_manager
        self.system_monitor = system_monitor
        self.health_monitor = health_monitor

        # Configuration
        self.config = self._load_update_config()

        # Update tracking
        self.pending_updates: Dict[str, UpdateRequest] = {}
        self.approval_rules: Dict[str, UpdateApprovalRule] = {}
        self.notification_callbacks: Dict[UpdateNotificationMethod, Callable] = {}

        # Security
        self.update_server_url = self.config.get("update_server_url", "")
        self.api_key = self.config.get("api_key", "")
        # Prefer var-lib location for keys; fall back to /opt if configured or present there
        default_public_key_candidates = [
            Path("/var/lib/lawnberry/keys/update_public.pem"),
            Path("/opt/lawnberry/keys/update_public.pem"),
        ]
        configured_path = self.config.get("public_key_path")
        if configured_path:
            self.public_key_path = Path(configured_path)
        else:
            self.public_key_path = next(
                (p for p in default_public_key_candidates if p.exists()),
                default_public_key_candidates[0],
            )

        # Update state
        self.last_check_time: Optional[datetime] = None
        self.check_interval = self.config.get("check_interval", 3600)  # 1 hour
        self.running = False

    def _load_update_config(self) -> Dict[str, Any]:
        """Load remote update configuration"""
        try:
            return self.config_manager.get_config("deployment")["remote_updates"]
        except KeyError:
            return {
                "enabled": True,
                "check_interval": 3600,
                "approval_timeout_hours": 24,
                "auto_approve_security": True,
                "auto_approve_config": True,
                "require_approval_features": True,
                "notification_methods": ["web_ui", "system_log"],
                "max_pending_updates": 5,
            }

    async def initialize(self):
        """Initialize the remote update manager"""
        logger.info("Initializing Remote Update Manager")

        # Load approval rules
        await self._load_approval_rules()

        # Setup notification callbacks
        self._setup_notification_callbacks()

        # Load pending updates from disk
        await self._load_pending_updates()

        # Verify update server connectivity
        await self._verify_server_connectivity()

        logger.info("Remote Update Manager initialized successfully")

    async def start(self):
        """Start the remote update manager"""
        if self.running:
            return

        self.running = True
        logger.info("Starting Remote Update Manager")

        # Start update check loop
        asyncio.create_task(self._update_check_loop())

        # Start approval timeout handler
        asyncio.create_task(self._approval_timeout_handler())

    async def stop(self):
        """Stop the remote update manager"""
        self.running = False
        logger.info("Stopping Remote Update Manager")

        # Save pending updates
        await self._save_pending_updates()

    async def check_for_updates(self, force: bool = False) -> List[DeploymentPackage]:
        """Check for available updates from remote server"""
        if not force and self.last_check_time:
            elapsed = (datetime.now() - self.last_check_time).total_seconds()
            if elapsed < self.check_interval:
                return []

        logger.info("Checking for remote updates...")

        try:
            available_updates = await self._fetch_available_updates()
            self.last_check_time = datetime.now()

            # Filter updates we haven't seen before
            new_updates = []
            for update in available_updates:
                if not await self._is_update_known(update):
                    new_updates.append(update)

            if new_updates:
                logger.info(f"Found {len(new_updates)} new updates")
                await self._process_new_updates(new_updates)

            return new_updates

        except Exception as e:
            logger.error(f"Failed to check for updates: {e}")
            return []

    async def _fetch_available_updates(self) -> List[DeploymentPackage]:
        """Fetch available updates from remote server"""
        if not self.update_server_url:
            return []

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Get current system info
        system_info = await self._get_system_info()

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self.update_server_url}/updates/available",
                    headers=headers,
                    params=system_info,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

                    updates = []
                    for update_data in data.get("updates", []):
                        package = DeploymentPackage(
                            version=update_data["version"],
                            package_type=DeploymentType(update_data["type"]),
                            checksum=update_data["checksum"],
                            signature=update_data["signature"],
                            download_url=update_data["download_url"],
                            size=update_data["size"],
                            created_at=datetime.fromisoformat(update_data["created_at"]),
                            priority=update_data["priority"],
                            metadata=update_data.get("metadata", {}),
                        )
                        updates.append(package)

                    return updates

            except Exception as e:
                logger.error(f"Failed to fetch updates from server: {e}")
                raise

    async def _get_system_info(self) -> Dict[str, str]:
        """Get current system information for update checks"""
        # Get current version from installed package metadata
        try:
            from importlib.metadata import version

            current_version = version("lawnberrypi")
        except Exception:
            current_version = "0.0.0"

        # Get hardware info
        system_metrics = await self.system_monitor.get_current_metrics()

        return {
            "current_version": current_version,
            "hardware_model": await self._get_hardware_model(),
            "os_version": await self._get_os_version(),
            "system_id": await self._get_system_id(),
            "memory_gb": str(int(system_metrics.memory_usage / 1024 / 1024 / 1024)),
            "arch": "armv7l",
        }

    async def _process_new_updates(self, updates: List[DeploymentPackage]):
        """Process newly discovered updates"""
        for package in updates:
            # Create update request
            update_request = UpdateRequest(
                update_id=f"update_{package.version}_{int(datetime.now().timestamp())}",
                package=package,
                approval_status=UpdateApprovalStatus.PENDING,
                notification_methods=[
                    UpdateNotificationMethod.WEB_UI,
                    UpdateNotificationMethod.SYSTEM_LOG,
                ],
                approval_timeout=datetime.now()
                + timedelta(hours=self.config.get("approval_timeout_hours", 24)),
                auto_approve_conditions=await self._get_auto_approve_conditions(package),
                user_message=package.metadata.get("user_message", ""),
                changelog=package.metadata.get("changelog", ""),
                rollback_plan=package.metadata.get("rollback_plan", ""),
                created_at=datetime.now(),
                approved_at=None,
                approved_by=None,
            )

            # Check auto-approval rules
            if await self._should_auto_approve(update_request):
                update_request.approval_status = UpdateApprovalStatus.AUTO_APPROVED
                update_request.approved_at = datetime.now()
                update_request.approved_by = "system_auto_approval"

                logger.info(f"Auto-approved update {update_request.update_id}")

                # Schedule immediate deployment
                asyncio.create_task(self._deploy_approved_update(update_request))
            else:
                # Send notifications for approval
                await self._send_approval_notifications(update_request)

            # Store pending update
            self.pending_updates[update_request.update_id] = update_request

    async def _should_auto_approve(self, update_request: UpdateRequest) -> bool:
        """Check if update should be auto-approved based on rules"""
        package = update_request.package

        # Check configuration-based auto-approval
        if package.package_type == DeploymentType.SECURITY and self.config.get(
            "auto_approve_security", True
        ):
            return True

        if package.package_type == DeploymentType.CONFIGURATION and self.config.get(
            "auto_approve_config", True
        ):
            return True

        if package.package_type == DeploymentType.EMERGENCY:
            return True

        # Check custom approval rules
        for rule in self.approval_rules.values():
            if not rule.enabled:
                continue

            if await self._evaluate_approval_rule(rule, update_request):
                return rule.auto_approve

        return False

    async def _evaluate_approval_rule(
        self, rule: UpdateApprovalRule, update_request: UpdateRequest
    ) -> bool:
        """Evaluate if approval rule conditions are met"""
        conditions = rule.conditions
        package = update_request.package

        # Check package type condition
        if "package_types" in conditions:
            if package.package_type.value not in conditions["package_types"]:
                return False

        # Check priority condition
        if "max_priority" in conditions:
            if package.priority > conditions["max_priority"]:
                return False

        # Check size condition
        if "max_size_mb" in conditions:
            if package.size > conditions["max_size_mb"] * 1024 * 1024:
                return False

        # Check system health condition
        if "require_healthy_system" in conditions and conditions["require_healthy_system"]:
            system_health = await self.health_monitor.get_overall_health()
            if system_health.status.value != "healthy":
                return False

        # Check maintenance window condition
        if "maintenance_window" in conditions:
            current_time = datetime.now()
            window = conditions["maintenance_window"]
            if not self._is_in_maintenance_window(current_time, window):
                return False

        return True

    def _is_in_maintenance_window(self, current_time: datetime, window: Dict[str, Any]) -> bool:
        """Check if current time is within maintenance window"""
        # Simple implementation - can be enhanced for complex schedules
        start_hour = window.get("start_hour", 0)
        end_hour = window.get("end_hour", 6)  # Default maintenance window: 00:00-06:00

        current_hour = current_time.hour

        if start_hour <= end_hour:
            return start_hour <= current_hour <= end_hour
        else:  # Window crosses midnight
            return current_hour >= start_hour or current_hour <= end_hour

    async def approve_update(
        self, update_id: str, approved_by: str, user_message: str = ""
    ) -> bool:
        """Manually approve a pending update"""
        if update_id not in self.pending_updates:
            logger.error(f"Update {update_id} not found in pending updates")
            return False

        update_request = self.pending_updates[update_id]

        if update_request.approval_status != UpdateApprovalStatus.PENDING:
            logger.error(f"Update {update_id} is not pending approval")
            return False

        # Update approval status
        update_request.approval_status = UpdateApprovalStatus.APPROVED
        update_request.approved_at = datetime.now()
        update_request.approved_by = approved_by

        logger.info(f"Update {update_id} approved by {approved_by}")

        # Create approval alert
        await self.system_monitor.create_alert(
            level=AlertLevel.INFO,
            source="remote_update_manager",
            message=f"Update {update_request.package.version} approved by {approved_by}",
            metadata={"update_id": update_id, "user_message": user_message},
        )

        # Schedule deployment
        asyncio.create_task(self._deploy_approved_update(update_request))

        return True

    async def reject_update(self, update_id: str, rejected_by: str, reason: str = "") -> bool:
        """Manually reject a pending update"""
        if update_id not in self.pending_updates:
            logger.error(f"Update {update_id} not found in pending updates")
            return False

        update_request = self.pending_updates[update_id]

        if update_request.approval_status != UpdateApprovalStatus.PENDING:
            logger.error(f"Update {update_id} is not pending approval")
            return False

        # Update approval status
        update_request.approval_status = UpdateApprovalStatus.REJECTED

        logger.info(f"Update {update_id} rejected by {rejected_by}: {reason}")

        # Create rejection alert
        await self.system_monitor.create_alert(
            level=AlertLevel.WARNING,
            source="remote_update_manager",
            message=f"Update {update_request.package.version} rejected by {rejected_by}",
            metadata={"update_id": update_id, "reason": reason},
        )

        # Remove from pending updates
        del self.pending_updates[update_id]

        return True

    async def _deploy_approved_update(self, update_request: UpdateRequest):
        """Deploy an approved update"""
        logger.info(f"Deploying approved update {update_request.update_id}")

        try:
            # Download and verify package
            package_path = await self._download_and_verify_package(update_request.package)

            # Create system backup before deployment
            backup_id = await self._create_pre_deployment_backup()

            # Deploy using deployment manager
            deployment_result = await self.deployment_manager.deploy_package(
                package_path, update_request.package, backup_available=backup_id is not None
            )

            if deployment_result.success:
                logger.info(f"Update {update_request.update_id} deployed successfully")

                # Remove from pending updates
                if update_request.update_id in self.pending_updates:
                    del self.pending_updates[update_request.update_id]

                # Send success notification
                await self._send_deployment_notification(
                    update_request, True, "Deployment successful"
                )

            else:
                logger.error(
                    f"Update {update_request.update_id} deployment failed: {deployment_result.error}"
                )

                # Send failure notification
                await self._send_deployment_notification(
                    update_request, False, deployment_result.error
                )

                # Keep in pending for potential retry
                update_request.approval_status = UpdateApprovalStatus.PENDING

        except Exception as e:
            logger.error(f"Failed to deploy update {update_request.update_id}: {e}")

            # Send failure notification
            await self._send_deployment_notification(update_request, False, str(e))

    async def _download_and_verify_package(self, package: DeploymentPackage) -> Path:
        """Download and verify update package"""
        download_dir = Path("/tmp/lawnberry_updates")
        download_dir.mkdir(exist_ok=True)

        package_file = download_dir / f"update_{package.version}.tar.gz"

        # Download package
        async with aiohttp.ClientSession() as session:
            async with session.get(package.download_url) as response:
                response.raise_for_status()

                async with aiofiles.open(package_file, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)

        # Verify checksum
        actual_checksum = await self._calculate_file_checksum(package_file)
        if actual_checksum != package.checksum:
            raise ValueError(f"Package checksum verification failed")

        # Verify signature if available
        if package.signature and self.public_key_path.exists():
            if not await self._verify_package_signature(package_file, package.signature):
                raise ValueError(f"Package signature verification failed")

        return package_file

    async def _calculate_file_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of file"""
        hash_sha256 = hashlib.sha256()

        async with aiofiles.open(file_path, "rb") as f:
            while True:
                chunk = await f.read(8192)
                if not chunk:
                    break
                hash_sha256.update(chunk)

        return hash_sha256.hexdigest()

    async def _verify_package_signature(self, package_file: Path, signature: str) -> bool:
        """Verify package digital signature"""
        try:
            # Load public key
            async with aiofiles.open(self.public_key_path, "rb") as f:
                public_key_data = await f.read()

            public_key = serialization.load_pem_public_key(public_key_data)

            # Read package data
            async with aiofiles.open(package_file, "rb") as f:
                package_data = await f.read()

            # Verify signature
            signature_bytes = bytes.fromhex(signature)

            public_key.verify(
                signature_bytes,
                package_data,
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256(),
            )

            return True

        except InvalidSignature:
            return False
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False

    async def get_pending_updates(self) -> List[Dict[str, Any]]:
        """Get list of pending updates for UI"""
        pending = []

        for update_request in self.pending_updates.values():
            pending.append(
                {
                    "update_id": update_request.update_id,
                    "version": update_request.package.version,
                    "type": update_request.package.package_type.value,
                    "size": update_request.package.size,
                    "priority": update_request.package.priority,
                    "status": update_request.approval_status.value,
                    "created_at": update_request.created_at.isoformat(),
                    "approval_timeout": update_request.approval_timeout.isoformat(),
                    "user_message": update_request.user_message,
                    "changelog": update_request.changelog,
                    "rollback_plan": update_request.rollback_plan,
                }
            )

        return pending

    async def _send_approval_notifications(self, update_request: UpdateRequest):
        """Send update approval notifications"""
        for method in update_request.notification_methods:
            if method in self.notification_callbacks:
                try:
                    await self.notification_callbacks[method](update_request)
                except Exception as e:
                    logger.error(f"Failed to send {method.value} notification: {e}")

    async def _send_deployment_notification(
        self, update_request: UpdateRequest, success: bool, message: str
    ):
        """Send deployment result notification"""
        notification_data = {
            "update_id": update_request.update_id,
            "version": update_request.package.version,
            "success": success,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }

        for method in update_request.notification_methods:
            if method in self.notification_callbacks:
                try:
                    await self.notification_callbacks[method](notification_data)
                except Exception as e:
                    logger.error(f"Failed to send {method.value} notification: {e}")

    def _setup_notification_callbacks(self):
        """Setup notification method callbacks"""
        self.notification_callbacks = {
            UpdateNotificationMethod.WEB_UI: self._send_web_ui_notification,
            UpdateNotificationMethod.SYSTEM_LOG: self._send_system_log_notification,
            # Additional methods can be added here
        }

    async def _send_web_ui_notification(self, data):
        """Send notification to web UI"""
        # This would integrate with the web UI notification system
        logger.info(f"Web UI notification: {data}")

    async def _send_system_log_notification(self, data):
        """Send notification to system log"""
        if isinstance(data, UpdateRequest):
            logger.info(
                f"Update approval required: {data.package.version} ({data.package.package_type.value})"
            )
        else:
            logger.info(f"Update deployment result: {data}")

    async def _update_check_loop(self):
        """Main update checking loop"""
        while self.running:
            try:
                await self.check_for_updates()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in update check loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retry

    async def _approval_timeout_handler(self):
        """Handle approval timeouts"""
        while self.running:
            now = datetime.now()
            expired_updates = []

            for update_id, update_request in self.pending_updates.items():
                if (
                    update_request.approval_status == UpdateApprovalStatus.PENDING
                    and now > update_request.approval_timeout
                ):
                    expired_updates.append(update_id)

            for update_id in expired_updates:
                update_request = self.pending_updates[update_id]
                update_request.approval_status = UpdateApprovalStatus.EXPIRED

                logger.warning(f"Update {update_id} approval expired")

                # Send expiration alert
                await self.system_monitor.create_alert(
                    level=AlertLevel.WARNING,
                    source="remote_update_manager",
                    message=f"Update {update_request.package.version} approval expired",
                    metadata={"update_id": update_id},
                )

                # Remove from pending
                del self.pending_updates[update_id]

            # Check every 5 minutes
            await asyncio.sleep(300)

    async def _load_approval_rules(self):
        """Load approval rules from configuration"""
        rules_config = self.config.get("approval_rules", [])

        for rule_config in rules_config:
            rule = UpdateApprovalRule(
                rule_id=rule_config["rule_id"],
                name=rule_config["name"],
                conditions=rule_config["conditions"],
                auto_approve=rule_config["auto_approve"],
                delay_minutes=rule_config.get("delay_minutes", 0),
                notification_required=rule_config.get("notification_required", True),
                enabled=rule_config.get("enabled", True),
            )
            self.approval_rules[rule.rule_id] = rule

    async def _load_pending_updates(self):
        """Load pending updates from persistent storage"""
        # Implementation would load from database or file
        pass

    async def _save_pending_updates(self):
        """Save pending updates to persistent storage"""
        # Implementation would save to database or file
        pass

    async def _verify_server_connectivity(self):
        """Verify connectivity to update server"""
        if not self.update_server_url:
            logger.warning("No update server URL configured")
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.update_server_url}/health", timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        logger.info("Update server connectivity verified")
                    else:
                        logger.warning(f"Update server returned status {response.status}")
        except Exception as e:
            logger.warning(f"Cannot connect to update server: {e}")

    async def _create_pre_deployment_backup(self) -> Optional[str]:
        """Create system backup before deployment"""
        try:
            # This would integrate with the backup system
            backup_id = f"pre_update_{int(datetime.now().timestamp())}"
            logger.info(f"Created pre-deployment backup: {backup_id}")
            return backup_id
        except Exception as e:
            logger.error(f"Failed to create pre-deployment backup: {e}")
            return None

    async def _get_hardware_model(self) -> str:
        """Get hardware model information"""
        try:
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if line.startswith("Model"):
                        return line.split(":")[1].strip()
            return "unknown"
        except:
            return "unknown"

    async def _get_os_version(self) -> str:
        """Get OS version information"""
        try:
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME"):
                        return line.split("=")[1].strip().strip('"')
            return "unknown"
        except:
            return "unknown"

    async def _get_system_id(self) -> str:
        """Get unique system identifier"""
        try:
            with open("/etc/machine-id", "r") as f:
                return f.read().strip()
        except:
            return "unknown"

    async def _is_update_known(self, package: DeploymentPackage) -> bool:
        """Check if update package is already known"""
        # Check if we've seen this version before
        for update_request in self.pending_updates.values():
            if update_request.package.version == package.version:
                return True

        # Check deployment history
        # Implementation would check database or log files
        return False

    async def _get_auto_approve_conditions(self, package: DeploymentPackage) -> Dict[str, Any]:
        """Get auto-approval conditions for package"""
        return {
            "security_update": package.package_type == DeploymentType.SECURITY,
            "config_update": package.package_type == DeploymentType.CONFIGURATION,
            "emergency_update": package.package_type == DeploymentType.EMERGENCY,
            "low_priority": package.priority >= 3,
            "small_size": package.size < 10 * 1024 * 1024,  # 10 MB
        }
