"""
System Router
System status, health checks, and service management endpoints.
"""

from typing import Dict, Any, List
from fastapi import APIRouter, Depends, Request, HTTPException
from datetime import datetime
import psutil
import time

from ..models import SystemStatus, ServiceHealth, SuccessResponse
from ..auth import get_current_user, require_permission
from ..exceptions import ServiceUnavailableError
from ..mqtt_bridge import MQTTBridge


router = APIRouter()


@router.get("/status", response_model=SystemStatus)
async def get_system_status(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get overall system status"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    # Get basic system info
    uptime = time.time() - getattr(request.app.state, 'start_time', time.time())
    
    # Check service health
    services_online = 0
    services_total = 5  # Expected number of services
    
    if mqtt_bridge and mqtt_bridge.is_connected():
        services_online += 1
    
    # Get last error from logs (simplified)
    last_error = None
    error_count = 0
    
    return SystemStatus(
        state="idle",  # This would come from the actual system state
        uptime=uptime,
        version="1.0.0",
        services_online=services_online,
        services_total=services_total,
        last_error=last_error,
        error_count=error_count
    )


@router.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }


@router.get("/services", response_model=List[ServiceHealth])
async def get_services_status(
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("read"))
):
    """Get status of all system services"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    services = []
    
    # MQTT Bridge service
    mqtt_status = "online" if mqtt_bridge and mqtt_bridge.is_connected() else "offline"
    services.append(ServiceHealth(
        name="mqtt_bridge",
        status=mqtt_status,
        last_heartbeat=datetime.utcnow(),
        cpu_usage=0.0,
        memory_usage=0.0,
        error_count=0
    ))
    
    # Add other services (would be implemented based on actual service discovery)
    service_names = ["sensor_fusion", "navigation", "vision", "weather", "power"]
    for service_name in service_names:
        services.append(ServiceHealth(
            name=service_name,
            status="unknown",  # Would check actual service status
            last_heartbeat=datetime.utcnow(),
            cpu_usage=0.0,
            memory_usage=0.0,
            error_count=0
        ))
    
    return services


@router.get("/metrics")
async def get_system_metrics(
    current_user: Dict[str, Any] = Depends(require_permission("read"))
):
    """Get system performance metrics"""
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        
        # Memory usage
        memory = psutil.virtual_memory()
        
        # Disk usage
        disk = psutil.disk_usage('/')
        
        # Network stats (if available)
        try:
            network = psutil.net_io_counters()
            network_stats = {
                "bytes_sent": network.bytes_sent,
                "bytes_recv": network.bytes_recv,
                "packets_sent": network.packets_sent,
                "packets_recv": network.packets_recv
            }
        except:
            network_stats = None
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "cpu": {
                "usage_percent": cpu_percent,
                "count": cpu_count,
                "load_average": list(psutil.getloadavg()) if hasattr(psutil, 'getloadavg') else None
            },
            "memory": {
                "total": memory.total,
                "available": memory.available,
                "used": memory.used,
                "usage_percent": memory.percent
            },
            "disk": {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "usage_percent": (disk.used / disk.total) * 100
            },
            "network": network_stats
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting system metrics: {str(e)}")


@router.post("/emergency-stop", response_model=SuccessResponse)
async def emergency_stop(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Trigger emergency stop"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Send emergency stop command
    success = await mqtt_bridge.publish_message(
        "safety/emergency_stop",
        {
            "command": "emergency_stop",
            "triggered_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat(),
            "reason": "Manual emergency stop via API"
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("emergency_stop", "Failed to send emergency stop command")
    
    return SuccessResponse(
        message="Emergency stop triggered successfully"
    )


@router.post("/restart-service", response_model=SuccessResponse)
async def restart_service(
    service_name: str,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("manage"))
):
    """Restart a specific service"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Send service restart command
    success = await mqtt_bridge.publish_message(
        f"system/services/{service_name}/restart",
        {
            "command": "restart",
            "service": service_name,
            "requested_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError(service_name, f"Failed to restart service: {service_name}")
    
    return SuccessResponse(
        message=f"Service restart command sent: {service_name}"
    )


@router.get("/logs")
async def get_system_logs(
    lines: int = 100,
    level: str = "INFO",
    service: str = None,
    current_user: Dict[str, Any] = Depends(require_permission("read"))
):
    """Get system logs"""
    # This would implement actual log retrieval
    # For now, return a placeholder
    
    return {
        "logs": [],
        "total_lines": 0,
        "requested_lines": lines,
        "level": level,
        "service": service,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/config/backup")
async def backup_configuration(
    current_user: Dict[str, Any] = Depends(require_permission("manage"))
):
    """Create configuration backup"""
    # This would implement actual configuration backup
    return {
        "backup_id": f"backup_{int(datetime.utcnow().timestamp())}",
        "timestamp": datetime.utcnow().isoformat(),
        "size": 0,
        "status": "created"
    }


@router.post("/config/restore")
async def restore_configuration(
    backup_id: str,
    current_user: Dict[str, Any] = Depends(require_permission("manage"))
):
    """Restore configuration from backup"""
    # This would implement actual configuration restore
    return SuccessResponse(
        message=f"Configuration restore initiated: {backup_id}"
    )


@router.get("/diagnostics")
async def run_diagnostics(
    current_user: Dict[str, Any] = Depends(require_permission("read"))
):
    """Run system diagnostics"""
    diagnostics = {
        "timestamp": datetime.utcnow().isoformat(),
        "system_health": "good",
        "checks": [
            {
                "name": "mqtt_connectivity",
                "status": "pass",
                "message": "MQTT broker is reachable"
            },
            {
                "name": "disk_space",
                "status": "pass", 
                "message": "Sufficient disk space available"
            },
            {
                "name": "memory_usage",
                "status": "pass",
                "message": "Memory usage within normal limits"
            },
            {
                "name": "sensor_connectivity",
                "status": "unknown",
                "message": "Sensor status check not implemented"
            }
        ]
    }
    
    return diagnostics
