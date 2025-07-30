"""
Sensors Router
Sensor data retrieval and sensor management endpoints.
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Request, Query, HTTPException
from datetime import datetime, timedelta

from ..models import SensorReading, SensorStatus, SensorType, PaginationParams, PaginatedResponse
from ..auth import get_current_user, require_permission
from ..exceptions import NotFoundError, ServiceUnavailableError
from ..mqtt_bridge import MQTTBridge


router = APIRouter()


@router.get("/", response_model=List[SensorStatus])
async def get_all_sensors(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get status of all sensors"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get sensor status from cache
    sensors = []
    sensor_types = ["gps", "imu", "tof", "camera", "power", "environmental"]
    
    for sensor_type in sensor_types:
        # Check for sensor data in cache
        status_data = mqtt_bridge.get_cached_data(f"sensors/{sensor_type}/status")
        
        if status_data:
            sensors.append(SensorStatus(
                sensor_id=sensor_type,
                sensor_type=SensorType(sensor_type),
                online=status_data.get("online", False),
                last_reading=datetime.fromisoformat(status_data.get("last_reading", datetime.utcnow().isoformat())),
                error_count=status_data.get("error_count", 0),
                calibration_status=status_data.get("calibration_status", "unknown")
            ))
        else:
            # Default status if no data available
            sensors.append(SensorStatus(
                sensor_id=sensor_type,
                sensor_type=SensorType(sensor_type),
                online=False,
                error_count=0,
                calibration_status="unknown"
            ))
    
    return sensors


@router.get("/{sensor_type}", response_model=SensorReading)
async def get_sensor_current_data(
    sensor_type: SensorType,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get current data from a specific sensor"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get sensor data from cache
    sensor_data = mqtt_bridge.get_cached_data(f"sensors/{sensor_type.value}/data")
    
    if not sensor_data:
        raise NotFoundError("sensor_data", f"No current data available for {sensor_type.value}")
    
    return SensorReading(
        sensor_id=f"{sensor_type.value}_main",
        sensor_type=sensor_type,
        timestamp=datetime.fromisoformat(sensor_data.get("timestamp", datetime.utcnow().isoformat())),
        value=sensor_data.get("value", {}),
        unit=sensor_data.get("unit", ""),
        quality=sensor_data.get("quality", 1.0),
        metadata=sensor_data.get("metadata", {})
    )


@router.get("/{sensor_type}/history", response_model=PaginatedResponse)
async def get_sensor_history(
    sensor_type: SensorType,
    request: Request,
    pagination: PaginationParams = Depends(),
    start_time: Optional[datetime] = Query(None, description="Start time for data range"),
    end_time: Optional[datetime] = Query(None, description="End time for data range"),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get historical sensor data"""
    # This would typically query a database for historical data
    # For now, return a placeholder response
    
    if not start_time:
        start_time = datetime.utcnow() - timedelta(hours=24)
    if not end_time:
        end_time = datetime.utcnow()
    
    # Placeholder historical data
    items = []
    total = 0
    
    return PaginatedResponse(
        items=items,
        total=total,
        page=pagination.page,
        size=pagination.size,
        pages=1
    )


@router.get("/{sensor_type}/status", response_model=SensorStatus)
async def get_sensor_status(
    sensor_type: SensorType,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get detailed status of a specific sensor"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get sensor status from cache
    status_data = mqtt_bridge.get_cached_data(f"sensors/{sensor_type.value}/status")
    
    if not status_data:
        raise NotFoundError("sensor_status", f"No status data available for {sensor_type.value}")
    
    return SensorStatus(
        sensor_id=f"{sensor_type.value}_main",
        sensor_type=sensor_type,
        online=status_data.get("online", False),
        last_reading=datetime.fromisoformat(status_data.get("last_reading", datetime.utcnow().isoformat())),
        error_count=status_data.get("error_count", 0),
        calibration_status=status_data.get("calibration_status", "unknown")
    )


@router.post("/{sensor_type}/calibrate")
async def calibrate_sensor(
    sensor_type: SensorType,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Trigger sensor calibration"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Send calibration command
    success = await mqtt_bridge.publish_message(
        f"sensors/{sensor_type.value}/calibrate",
        {
            "command": "calibrate",
            "sensor_type": sensor_type.value,
            "requested_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("calibration", f"Failed to send calibration command for {sensor_type.value}")
    
    return {
        "success": True,
        "message": f"Calibration started for {sensor_type.value}",
        "sensor_type": sensor_type.value
    }


@router.post("/{sensor_type}/reset")
async def reset_sensor(
    sensor_type: SensorType,
    request: Request,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Reset a sensor"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Send reset command
    success = await mqtt_bridge.publish_message(
        f"sensors/{sensor_type.value}/reset",
        {
            "command": "reset",
            "sensor_type": sensor_type.value,
            "requested_by": current_user.get("username", "unknown"),
            "timestamp": datetime.utcnow().isoformat()
        },
        qos=2
    )
    
    if not success:
        raise ServiceUnavailableError("reset", f"Failed to send reset command for {sensor_type.value}")
    
    return {
        "success": True,
        "message": f"Reset command sent for {sensor_type.value}",
        "sensor_type": sensor_type.value
    }


@router.get("/gps/location")
async def get_current_location(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get current GPS location"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get GPS data from cache
    gps_data = mqtt_bridge.get_cached_data("sensors/gps/data")
    
    if not gps_data:
        raise NotFoundError("gps_data", "No current GPS data available")
    
    location = gps_data.get("value", {})
    
    return {
        "latitude": location.get("latitude", 0.0),
        "longitude": location.get("longitude", 0.0),
        "altitude": location.get("altitude", 0.0),
        "accuracy": location.get("accuracy", 0.0),
        "timestamp": gps_data.get("timestamp", datetime.utcnow().isoformat()),
        "satellite_count": location.get("satellites", 0),
        "fix_quality": location.get("fix_quality", "unknown")
    }


@router.get("/imu/orientation")
async def get_current_orientation(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get current IMU orientation data"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get IMU data from cache
    imu_data = mqtt_bridge.get_cached_data("sensors/imu/data")
    
    if not imu_data:
        raise NotFoundError("imu_data", "No current IMU data available")
    
    orientation = imu_data.get("value", {})
    
    return {
        "roll": orientation.get("roll", 0.0),
        "pitch": orientation.get("pitch", 0.0),
        "yaw": orientation.get("yaw", 0.0),
        "quaternion": orientation.get("quaternion", [1.0, 0.0, 0.0, 0.0]),
        "acceleration": orientation.get("acceleration", [0.0, 0.0, 0.0]),
        "angular_velocity": orientation.get("angular_velocity", [0.0, 0.0, 0.0]),
        "timestamp": imu_data.get("timestamp", datetime.utcnow().isoformat()),
        "calibration_status": orientation.get("calibration_status", "unknown")
    }


@router.get("/environmental/conditions")
async def get_environmental_conditions(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get current environmental sensor data"""
    mqtt_bridge: MQTTBridge = request.app.state.mqtt_bridge
    
    if not mqtt_bridge or not mqtt_bridge.is_connected():
        raise ServiceUnavailableError("mqtt_bridge", "MQTT bridge not available")
    
    # Get environmental data from cache
    env_data = mqtt_bridge.get_cached_data("sensors/environmental/data")
    
    if not env_data:
        raise NotFoundError("environmental_data", "No current environmental data available")
    
    conditions = env_data.get("value", {})
    
    return {
        "temperature": conditions.get("temperature", 0.0),
        "humidity": conditions.get("humidity", 0.0),
        "pressure": conditions.get("pressure", 0.0),
        "light_level": conditions.get("light_level", 0.0),
        "rain_detected": conditions.get("rain_detected", False),
        "timestamp": env_data.get("timestamp", datetime.utcnow().isoformat()),
        "sensor_health": conditions.get("sensor_health", "unknown")
    }
