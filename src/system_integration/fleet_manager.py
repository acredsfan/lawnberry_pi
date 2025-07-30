"""
Fleet Manager - Multi-device deployment and management system
Handles fleet-wide updates, device grouping, and coordinated deployments
"""

import asyncio
import logging
import json
import aiohttp
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict
from enum import Enum
import aiofiles

from .config_manager import ConfigManager
from .deployment_manager import DeploymentManager, DeploymentPackage, DeploymentType


logger = logging.getLogger(__name__)


class DeviceStatus(Enum):
    """Device status"""
    ONLINE = "online"
    OFFLINE = "offline"
    UPDATING = "updating"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class DeploymentWave(Enum):
    """Deployment wave priorities"""
    CANARY = 1      # 5% of fleet
    EARLY = 2       # 15% of fleet
    STANDARD = 3    # 60% of fleet
    LATE = 4        # 15% of fleet
    FINAL = 5       # 5% of fleet


@dataclass
class FleetDevice:
    """Fleet device information"""
    device_id: str
    name: str
    group_id: str
    wave: DeploymentWave
    status: DeviceStatus
    current_version: str
    last_seen: datetime
    location: Optional[str]
    metadata: Dict[str, Any]
    health_score: float  # 0.0 - 1.0


@dataclass
class FleetDeployment:
    """Fleet deployment tracking"""
    deployment_id: str
    package: DeploymentPackage
    target_groups: List[str]
    started_at: datetime
    completed_at: Optional[datetime]
    success_count: int
    failure_count: int
    pending_count: int
    rollback_count: int
    device_results: Dict[str, str]  # device_id -> result


class FleetManager:
    """
    Manages fleet-wide deployments and device coordination
    """
    
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.config = self._load_fleet_config()
        
        # Fleet state
        self.devices: Dict[str, FleetDevice] = {}
        self.active_deployments: Dict[str, FleetDeployment] = {}
        
        # Fleet server communication
        self.fleet_server_url = self.config.get('server_url', '')
        self.fleet_api_key = self.config.get('api_key', '')
        
        # Device grouping
        self.device_groups = self.config.get('groups', {})
        
        # Deployment coordination
        self.max_concurrent_deployments = self.config.get('max_concurrent_deployments', 5)
        self.wave_delay_seconds = self.config.get('wave_delay_seconds', 300)  # 5 minutes
        self.health_threshold = self.config.get('health_threshold', 0.8)
        
        # Background tasks
        self._fleet_sync_task: Optional[asyncio.Task] = None
        self._deployment_coordinator_task: Optional[asyncio.Task] = None
        
    def _load_fleet_config(self) -> Dict[str, Any]:
        """Load fleet configuration"""
        try:
            config = self.config_manager.get_config('fleet')
            return config if config else self._default_fleet_config()
        except Exception as e:
            logger.warning(f"Failed to load fleet config, using defaults: {e}")
            return self._default_fleet_config()
    
    def _default_fleet_config(self) -> Dict[str, Any]:
        """Default fleet configuration"""
        return {
            'enabled': False,
            'server_url': 'https://fleet.lawnberry.com/api/v1',
            'api_key': '',
            'sync_interval': 300,  # 5 minutes
            'max_concurrent_deployments': 5,
            'wave_delay_seconds': 300,
            'health_threshold': 0.8,
            'groups': {
                'production': {
                    'description': 'Production devices',
                    'auto_deploy_security': True,
                    'auto_deploy_features': False,
                    'wave_distribution': {
                        'canary': 0.05,
                        'early': 0.15,
                        'standard': 0.60,
                        'late': 0.15,
                        'final': 0.05
                    }
                },
                'staging': {
                    'description': 'Staging devices',
                    'auto_deploy_security': True,
                    'auto_deploy_features': True,
                    'wave_distribution': {
                        'canary': 0.20,
                        'early': 0.30,
                        'standard': 0.50,
                        'late': 0.0,
                        'final': 0.0
                    }
                }
            }
        }
    
    async def initialize(self):
        """Initialize fleet manager"""
        try:
            if not self.config.get('enabled', False):
                logger.info("Fleet management disabled")
                return
            
            logger.info("Initializing Fleet Manager")
            
            # Load fleet state
            await self._load_fleet_state()
            
            # Start background tasks
            self._fleet_sync_task = asyncio.create_task(self._fleet_sync_loop())
            self._deployment_coordinator_task = asyncio.create_task(self._deployment_coordinator_loop())
            
            logger.info("Fleet Manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Fleet Manager: {e}")
            raise
    
    async def shutdown(self):
        """Shutdown fleet manager"""
        if not self.config.get('enabled', False):
            return
            
        logger.info("Shutting down Fleet Manager")
        
        # Cancel background tasks
        if self._fleet_sync_task:
            self._fleet_sync_task.cancel()
            try:
                await self._fleet_sync_task
            except asyncio.CancelledError:
                pass
        
        if self._deployment_coordinator_task:
            self._deployment_coordinator_task.cancel()
            try:
                await self._deployment_coordinator_task
            except asyncio.CancelledError:
                pass
    
    async def _load_fleet_state(self):
        """Load fleet state from disk"""
        try:
            state_file = Path("/var/lib/lawnberry/fleet_state.json")
            if state_file.exists():
                async with aiofiles.open(state_file, 'r') as f:
                    data = json.loads(await f.read())
                    
                    # Load devices
                    for device_data in data.get('devices', []):
                        # Convert datetime strings back
                        if device_data.get('last_seen'):
                            device_data['last_seen'] = datetime.fromisoformat(device_data['last_seen'])
                        
                        device_data['status'] = DeviceStatus(device_data['status'])
                        device_data['wave'] = DeploymentWave(device_data['wave'])
                        
                        device = FleetDevice(**device_data)
                        self.devices[device.device_id] = device
                    
                    # Load active deployments
                    for deployment_data in data.get('active_deployments', []):
                        # Convert datetime strings back
                        if deployment_data.get('started_at'):
                            deployment_data['started_at'] = datetime.fromisoformat(deployment_data['started_at'])
                        if deployment_data.get('completed_at'):
                            deployment_data['completed_at'] = datetime.fromisoformat(deployment_data['completed_at'])
                        
                        # Reconstruct package
                        package_data = deployment_data['package']
                        package_data['package_type'] = DeploymentType(package_data['package_type'])
                        package_data['created_at'] = datetime.fromisoformat(package_data['created_at'])
                        package = DeploymentPackage(**package_data)
                        deployment_data['package'] = package
                        
                        deployment = FleetDeployment(**deployment_data)
                        self.active_deployments[deployment.deployment_id] = deployment
                        
        except Exception as e:
            logger.warning(f"Failed to load fleet state: {e}")
    
    async def _save_fleet_state(self):
        """Save fleet state to disk"""
        try:
            state_data = {
                'devices': [],
                'active_deployments': [],
                'last_updated': datetime.now().isoformat()
            }
            
            # Save devices
            for device in self.devices.values():
                device_data = asdict(device)
                device_data['status'] = device_data['status'].value
                device_data['wave'] = device_data['wave'].value
                if device_data.get('last_seen'):
                    device_data['last_seen'] = device_data['last_seen'].isoformat()
                state_data['devices'].append(device_data)
            
            # Save active deployments
            for deployment in self.active_deployments.values():
                deployment_data = asdict(deployment)
                deployment_data['started_at'] = deployment_data['started_at'].isoformat()
                if deployment_data.get('completed_at'):
                    deployment_data['completed_at'] = deployment_data['completed_at'].isoformat()
                
                # Handle package serialization
                package_data = asdict(deployment.package)
                package_data['package_type'] = package_data['package_type'].value
                package_data['created_at'] = package_data['created_at'].isoformat()
                deployment_data['package'] = package_data
                
                state_data['active_deployments'].append(deployment_data)
            
            state_file = Path("/var/lib/lawnberry/fleet_state.json")
            state_file.parent.mkdir(parents=True, exist_ok=True)
            
            async with aiofiles.open(state_file, 'w') as f:
                await f.write(json.dumps(state_data, indent=2))
                
        except Exception as e:
            logger.error(f"Failed to save fleet state: {e}")
    
    async def _fleet_sync_loop(self):
        """Background loop to sync with fleet server"""
        while True:
            try:
                await self._sync_with_fleet_server()
                await asyncio.sleep(self.config.get('sync_interval', 300))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Fleet sync error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    async def _sync_with_fleet_server(self):
        """Sync device status and deployments with fleet server"""
        try:
            if not self.fleet_server_url or not self.fleet_api_key:
                return
            
            headers = {
                'Authorization': f'Bearer {self.fleet_api_key}',
                'Content-Type': 'application/json'
            }
            
            # Get current device info
            device_info = await self._get_local_device_info()
            
            async with aiohttp.ClientSession() as session:
                # Report device status
                await self._report_device_status(session, headers, device_info)
                
                # Get fleet updates
                await self._get_fleet_updates(session, headers)
                
                # Report deployment status
                await self._report_deployment_status(session, headers)
                
        except Exception as e:
            logger.error(f"Fleet server sync failed: {e}")
    
    async def _get_local_device_info(self) -> Dict[str, Any]:
        """Get local device information"""
        try:
            # This would integrate with the deployment manager
            return {
                'device_id': 'local_device',  # Would get actual device ID
                'version': '1.0.0',  # Would get actual version
                'status': 'online',
                'health_score': 1.0,  # Would calculate actual health
                'last_deployment': datetime.now().isoformat(),
                'metadata': {
                    'location': 'unknown',
                    'model': 'lawnberry-v1'
                }
            }
        except Exception as e:
            logger.error(f"Failed to get device info: {e}")
            return {}
    
    async def _report_device_status(self, session: aiohttp.ClientSession, headers: Dict[str, str], device_info: Dict[str, Any]):
        """Report device status to fleet server"""
        try:
            url = f"{self.fleet_server_url}/devices/status"
            async with session.post(url, headers=headers, json=device_info) as response:
                if response.status != 200:
                    logger.warning(f"Failed to report device status: {response.status}")
                    
        except Exception as e:
            logger.error(f"Device status report failed: {e}")
    
    async def _get_fleet_updates(self, session: aiohttp.ClientSession, headers: Dict[str, str]):
        """Get fleet updates from server"""
        try:
            url = f"{self.fleet_server_url}/fleet/devices"
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    fleet_data = await response.json()
                    await self._update_fleet_devices(fleet_data)
                    
        except Exception as e:
            logger.error(f"Fleet updates fetch failed: {e}")
    
    async def _update_fleet_devices(self, fleet_data: Dict[str, Any]):
        """Update fleet device information"""
        try:
            for device_data in fleet_data.get('devices', []):
                device_id = device_data['device_id']
                
                # Convert data
                device_data['status'] = DeviceStatus(device_data['status'])
                device_data['wave'] = DeploymentWave(device_data['wave'])
                device_data['last_seen'] = datetime.fromisoformat(device_data['last_seen'])
                
                device = FleetDevice(**device_data)
                self.devices[device_id] = device
            
            await self._save_fleet_state()
            
        except Exception as e:
            logger.error(f"Fleet device update failed: {e}")
    
    async def _report_deployment_status(self, session: aiohttp.ClientSession, headers: Dict[str, str]):
        """Report deployment status to fleet server"""
        try:
            for deployment in self.active_deployments.values():
                deployment_status = {
                    'deployment_id': deployment.deployment_id,
                    'success_count': deployment.success_count,
                    'failure_count': deployment.failure_count,
                    'pending_count': deployment.pending_count,
                    'device_results': deployment.device_results
                }
                
                url = f"{self.fleet_server_url}/deployments/{deployment.deployment_id}/status"
                async with session.post(url, headers=headers, json=deployment_status) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to report deployment status: {response.status}")
                        
        except Exception as e:
            logger.error(f"Deployment status report failed: {e}")
    
    async def _deployment_coordinator_loop(self):
        """Background loop to coordinate deployments"""
        while True:
            try:
                await self._coordinate_deployments()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Deployment coordinator error: {e}")
                await asyncio.sleep(60)
    
    async def _coordinate_deployments(self):
        """Coordinate ongoing deployments"""
        try:
            for deployment in list(self.active_deployments.values()):
                if deployment.completed_at is None:
                    await self._process_deployment(deployment)
                    
        except Exception as e:
            logger.error(f"Deployment coordination failed: {e}")
    
    async def _process_deployment(self, deployment: FleetDeployment):
        """Process a single deployment"""
        try:
            # Get devices for deployment
            target_devices = self._get_deployment_targets(deployment)
            
            # Organize by waves
            wave_devices = self._organize_by_waves(target_devices)
            
            # Process each wave
            for wave, devices in wave_devices.items():
                if await self._should_process_wave(deployment, wave, devices):
                    await self._deploy_to_wave(deployment, wave, devices)
                    
                    # Wait between waves
                    if wave != DeploymentWave.FINAL:
                        await asyncio.sleep(self.wave_delay_seconds)
            
            # Check if deployment is complete
            await self._check_deployment_completion(deployment)
            
        except Exception as e:
            logger.error(f"Deployment processing failed: {e}")
    
    def _get_deployment_targets(self, deployment: FleetDeployment) -> List[FleetDevice]:
        """Get target devices for deployment"""
        targets = []
        
        for device in self.devices.values():
            if (device.group_id in deployment.target_groups and 
                device.status == DeviceStatus.ONLINE and
                device.health_score >= self.health_threshold):
                targets.append(device)
        
        return targets
    
    def _organize_by_waves(self, devices: List[FleetDevice]) -> Dict[DeploymentWave, List[FleetDevice]]:
        """Organize devices by deployment waves"""
        wave_devices: Dict[DeploymentWave, List[FleetDevice]] = {wave: [] for wave in DeploymentWave}
        
        for device in devices:
            wave_devices[device.wave].append(device)
        
        return wave_devices
    
    async def _should_process_wave(self, deployment: FleetDeployment, wave: DeploymentWave, devices: List[FleetDevice]) -> bool:
        """Check if wave should be processed"""
        try:
            # Check if previous waves completed successfully
            if wave != DeploymentWave.CANARY:
                previous_waves = [w for w in DeploymentWave if w.value < wave.value]
                for prev_wave in previous_waves:
                    prev_success_rate = self._calculate_wave_success_rate(deployment, prev_wave)
                    if prev_success_rate < 0.9:  # 90% success threshold
                        logger.warning(f"Delaying wave {wave.name} due to low success rate in previous waves")
                        return False
            
            # Check if any devices in this wave are ready
            ready_devices = [d for d in devices if d.device_id not in deployment.device_results]
            return len(ready_devices) > 0
            
        except Exception as e:
            logger.error(f"Wave readiness check failed: {e}")
            return False
    
    def _calculate_wave_success_rate(self, deployment: FleetDeployment, wave: DeploymentWave) -> float:
        """Calculate success rate for a wave"""
        try:
            wave_devices = [d for d in self.devices.values() if d.wave == wave]
            wave_results = [(d.device_id, deployment.device_results.get(d.device_id)) 
                           for d in wave_devices]
            
            completed = [r for r in wave_results if r[1] is not None]
            successful = [r for r in completed if r[1] == 'success']
            
            return len(successful) / len(completed) if completed else 0.0
            
        except Exception as e:
            logger.error(f"Success rate calculation failed: {e}")
            return 0.0
    
    async def _deploy_to_wave(self, deployment: FleetDeployment, wave: DeploymentWave, devices: List[FleetDevice]):
        """Deploy to devices in a wave"""
        try:
            logger.info(f"Deploying to wave {wave.name} ({len(devices)} devices)")
            
            # Deploy to devices in parallel (with concurrency limit)
            semaphore = asyncio.Semaphore(self.max_concurrent_deployments)
            tasks = []
            
            for device in devices:
                if device.device_id not in deployment.device_results:
                    task = asyncio.create_task(
                        self._deploy_to_device(semaphore, deployment, device)
                    )
                    tasks.append(task)
            
            # Wait for all deployments in this wave
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except Exception as e:
            logger.error(f"Wave deployment failed: {e}")
    
    async def _deploy_to_device(self, semaphore: asyncio.Semaphore, deployment: FleetDeployment, device: FleetDevice):
        """Deploy to a single device"""
        async with semaphore:
            try:
                logger.info(f"Deploying to device {device.device_id}")
                
                # Update device status
                device.status = DeviceStatus.UPDATING
                
                # This would send deployment command to device
                # For now, simulate deployment
                await asyncio.sleep(5)  # Simulate deployment time
                
                # Simulate success/failure
                import random
                success = random.random() > 0.1  # 90% success rate
                
                if success:
                    deployment.device_results[device.device_id] = 'success'
                    deployment.success_count += 1
                    device.status = DeviceStatus.ONLINE
                    device.current_version = deployment.package.version
                else:
                    deployment.device_results[device.device_id] = 'failed'
                    deployment.failure_count += 1
                    device.status = DeviceStatus.ERROR
                
                logger.info(f"Device {device.device_id} deployment: {'success' if success else 'failed'}")
                
            except Exception as e:
                logger.error(f"Device deployment failed {device.device_id}: {e}")
                deployment.device_results[device.device_id] = 'error'
                deployment.failure_count += 1
                device.status = DeviceStatus.ERROR
            finally:
                await self._save_fleet_state()
    
    async def _check_deployment_completion(self, deployment: FleetDeployment):
        """Check if deployment is complete"""
        try:
            total_devices = len(self._get_deployment_targets(deployment))
            completed_devices = len(deployment.device_results)
            
            if completed_devices >= total_devices:
                deployment.completed_at = datetime.now()
                logger.info(f"Deployment {deployment.deployment_id} completed: {deployment.success_count} success, {deployment.failure_count} failed")
                
                # Send completion notification
                await self._notify_deployment_completion(deployment)
                
        except Exception as e:
            logger.error(f"Deployment completion check failed: {e}")
    
    async def create_fleet_deployment(self, package: DeploymentPackage, target_groups: List[str]) -> str:
        """Create a new fleet deployment"""
        try:
            deployment_id = f"fleet_deploy_{int(datetime.now().timestamp())}"
            
            deployment = FleetDeployment(
                deployment_id=deployment_id,
                package=package,
                target_groups=target_groups,
                started_at=datetime.now(),
                completed_at=None,
                success_count=0,
                failure_count=0,
                pending_count=len(self._get_deployment_targets_by_groups(target_groups)),
                rollback_count=0,
                device_results={}
            )
            
            self.active_deployments[deployment_id] = deployment
            await self._save_fleet_state()
            
            logger.info(f"Created fleet deployment {deployment_id} for groups {target_groups}")
            return deployment_id
            
        except Exception as e:
            logger.error(f"Fleet deployment creation failed: {e}")
            raise
    
    def _get_deployment_targets_by_groups(self, target_groups: List[str]) -> List[FleetDevice]:
        """Get deployment targets by groups"""
        targets = []
        for device in self.devices.values():
            if device.group_id in target_groups:
                targets.append(device)
        return targets
    
    async def get_fleet_status(self) -> Dict[str, Any]:
        """Get current fleet status"""
        try:
            device_counts = {}
            for status in DeviceStatus:
                device_counts[status.value] = len([d for d in self.devices.values() if d.status == status])
            
            version_counts = {}
            for device in self.devices.values():
                version = device.current_version
                version_counts[version] = version_counts.get(version, 0) + 1
            
            return {
                'total_devices': len(self.devices),
                'device_status_counts': device_counts,
                'version_distribution': version_counts,
                'active_deployments': len([d for d in self.active_deployments.values() if d.completed_at is None]),
                'groups': list(self.device_groups.keys()),
                'last_sync': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Fleet status failed: {e}")
            return {}
    
    async def get_deployment_status(self, deployment_id: str) -> Optional[Dict[str, Any]]:
        """Get deployment status"""
        try:
            deployment = self.active_deployments.get(deployment_id)
            if not deployment:
                return None
            
            return {
                'deployment_id': deployment.deployment_id,
                'package_version': deployment.package.version,
                'target_groups': deployment.target_groups,
                'started_at': deployment.started_at.isoformat(),
                'completed_at': deployment.completed_at.isoformat() if deployment.completed_at else None,
                'success_count': deployment.success_count,
                'failure_count': deployment.failure_count,
                'pending_count': deployment.pending_count,
                'rollback_count': deployment.rollback_count,
                'progress': len(deployment.device_results) / (deployment.success_count + deployment.failure_count + deployment.pending_count) * 100
            }
            
        except Exception as e:
            logger.error(f"Deployment status failed: {e}")
            return None
    
    async def rollback_fleet_deployment(self, deployment_id: str) -> bool:
        """Rollback a fleet deployment"""
        try:
            deployment = self.active_deployments.get(deployment_id)
            if not deployment:
                logger.error(f"Deployment {deployment_id} not found")
                return False
            
            logger.info(f"Rolling back fleet deployment {deployment_id}")
            
            # Send rollback commands to all devices that were successfully updated
            rollback_tasks = []
            for device_id, result in deployment.device_results.items():
                if result == 'success':
                    device = self.devices.get(device_id)
                    if device:
                        task = asyncio.create_task(self._rollback_device(device))
                        rollback_tasks.append(task)
            
            # Wait for all rollbacks
            if rollback_tasks:
                results = await asyncio.gather(*rollback_tasks, return_exceptions=True)
                successful_rollbacks = sum(1 for r in results if r is True)
                deployment.rollback_count = successful_rollbacks
            
            await self._save_fleet_state()
            
            logger.info(f"Fleet rollback completed: {deployment.rollback_count} devices rolled back")
            return True
            
        except Exception as e:
            logger.error(f"Fleet rollback failed: {e}")
            return False
    
    async def _rollback_device(self, device: FleetDevice) -> bool:
        """Rollback a single device"""
        try:
            logger.info(f"Rolling back device {device.device_id}")
            
            # This would send rollback command to device
            # For now, simulate rollback
            await asyncio.sleep(3)
            
            # Simulate rollback success
            device.status = DeviceStatus.ONLINE
            return True
            
        except Exception as e:
            logger.error(f"Device rollback failed {device.device_id}: {e}")
            return False
    
    async def _notify_deployment_completion(self, deployment: FleetDeployment):
        """Notify about deployment completion"""
        logger.info(f"Fleet deployment {deployment.deployment_id} completed")
        # TODO: Send notification via MQTT/web UI
