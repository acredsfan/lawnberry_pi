"""
Enhanced Safety API Endpoints
Provides API access to enhanced safety features with tiered access control
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from safety.access_control import SafetyAccessLevel, TrainingModule
from ..auth import require_permission, get_current_user
from ..schemas import SuccessResponse, ErrorResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enhanced-safety", tags=["Enhanced Safety"])


@router.get("/status", response_model=Dict[str, Any])
async def get_enhanced_safety_status(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get comprehensive enhanced safety status"""
    try:
        # This would get the safety service instance from the app state
        # For demonstration, we'll return a mock status
        return {
            "timestamp": datetime.now().isoformat(),
            "system_state": "READY",
            "enhanced_features": {
                "access_control": {
                    "enabled": True,
                    "user_access_level": "basic",
                    "total_events": 15,
                    "recent_events": 3
                },
                "sensor_fusion": {
                    "enabled": True,
                    "performance_metrics": {
                        "obstacles_detected": 42,
                        "detection_accuracy": 0.94,
                        "response_time_ms": 85.2
                    },
                    "system_status": {
                        "sensor_reliability": {
                            "tof_left": "good",
                            "tof_right": "good", 
                            "camera_vision": "excellent",
                            "imu": "good",
                            "environmental": "good"
                        },
                        "adaptive_weights_enabled": True
                    }
                },
                "enhanced_protocols": {
                    "enabled": True,
                    "safety_status": {
                        "active_violations": 0,
                        "total_events_today": 2,
                        "current_weather": "clear",
                        "geofence_zones": 3,
                        "emergency_contacts": 2
                    }
                },
                "environmental_safety": {
                    "enabled": True,
                    "total_events": 8,
                    "status": {
                        "current_slope": {
                            "angle_degrees": 5.2,
                            "safety_assessment": "safe",
                            "stability_factor": 0.92
                        },
                        "current_surface": {
                            "surface_type": "grass_dry",
                            "moisture_level": 0.3,
                            "grip_factor": 0.85,
                            "mowing_suitability": 0.95
                        },
                        "active_hazards": 0,
                        "recent_wildlife_detections": 1
                    }
                },
                "maintenance_safety": {
                    "enabled": True,
                    "total_events": 5,
                    "status": {
                        "blade_status": {
                            "main_blade": {
                                "condition": "good",
                                "wear_percentage": 35.2,
                                "replacement_recommended": False,
                                "safety_concern": False
                            }
                        },
                        "battery_status": {
                            "main_battery": {
                                "health_status": "good",
                                "capacity_percentage": 87.5,
                                "safety_concerns": [],
                                "estimated_remaining_life_days": 1247
                            }
                        },
                        "active_lockouts": 0,
                        "system_health": "good"
                    }
                }
            }
        }
    except Exception as e:
        logger.error(f"Error getting enhanced safety status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get safety status: {str(e)}"
        )


@router.get("/access-control/status")
async def get_access_control_status(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get user's access control status and available features"""
    username = current_user.get('username', 'unknown')
    
    # Mock user status - in practice this would come from the access controller
    return {
        "username": username,
        "access_level": "basic",
        "is_qualified": True,
        "experience_hours": 25.5,
        "safety_violations": 0,
        "training_records": [
            {
                "module": "basic_safety",
                "completed_at": "2024-01-15T10:30:00",
                "score": 95.0,
                "expires_at": "2025-01-15T10:30:00",
                "is_valid": True
            }
        ],
        "missing_training": ["advanced_configuration", "sensor_systems"],
        "configurable_parameters": [
            "emergency_stop_distance",
            "person_safety_radius", 
            "pet_safety_radius",
            "boundary_safety_margin",
            "enable_weather_safety",
            "enable_vision_safety"
        ],
        "feature_access": [
            "basic_mowing_patterns",
            "standard_boundary_control",
            "basic_weather_monitoring",
            "emergency_stop",
            "basic_status_monitoring"
        ]
    }


@router.get("/training/modules")
async def get_training_modules(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get available training modules"""
    return {
        "modules": {
            "basic_safety": {
                "title": "Basic Safety Operations",
                "description": "Fundamental safety concepts and basic system operation",
                "duration_minutes": 30,
                "passing_score": 80.0,
                "expires_months": 12,
                "topics": [
                    "Emergency stop procedures",
                    "Personal protective equipment", 
                    "Basic hazard recognition",
                    "Standard operating procedures",
                    "Boundary setup and validation"
                ]
            },
            "advanced_configuration": {
                "title": "Advanced Safety Configuration",
                "description": "Performance vs safety trade-offs and advanced parameters",
                "duration_minutes": 60,
                "passing_score": 85.0,
                "expires_months": 6,
                "topics": [
                    "Safety parameter optimization",
                    "Performance trade-off analysis",
                    "Risk assessment procedures",
                    "Advanced boundary configuration",
                    "Weather-based safety adjustments"
                ]
            },
            "sensor_systems": {
                "title": "Sensor Systems and Fusion",
                "description": "Understanding sensor integration and fusion algorithms",
                "duration_minutes": 90,
                "passing_score": 90.0,
                "expires_months": 6,
                "topics": [
                    "Multi-sensor fusion principles",
                    "Sensor conflict resolution",
                    "Predictive obstacle detection",
                    "Environmental sensor integration",
                    "Sensor diagnostics and validation"
                ]
            }
        }
    }


@router.post("/training/complete")
async def complete_training(
    training_data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Complete a training module"""
    module = training_data.get('module')
    score = training_data.get('score', 0.0)
    
    if not module or score < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid training data"
        )
    
    username = current_user.get('username')
    
    # Mock training completion - in practice this would update the access controller
    logger.info(f"User {username} completed training module {module} with score {score}")
    
    return {
        "success": True,
        "message": f"Training module {module} completed successfully",
        "score": score,
        "passed": score >= 80.0,  # Assuming 80% passing score
        "certificate_id": f"{username}_{module}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    }


@router.get("/sensor-fusion/performance")
async def get_sensor_fusion_performance(
    current_user: Dict[str, Any] = Depends(require_permission("read"))
):
    """Get sensor fusion performance metrics"""
    return {
        "timestamp": datetime.now().isoformat(),
        "performance_metrics": {
            "detection_accuracy": 0.94,
            "false_positive_rate": 0.03,
            "response_time_ms": 85.2,
            "sensor_fusion_rate": 20.0
        },
        "sensor_reliability": {
            "tof_left": "good",
            "tof_right": "good",
            "camera_vision": "excellent", 
            "imu": "good",
            "environmental": "good"
        },
        "sensor_weights": {
            "tof_left": 0.25,
            "tof_right": 0.25,
            "camera_vision": 0.35,
            "imu": 0.10,
            "environmental": 0.05
        },
        "environmental_conditions": {
            "temperature": 22.5,
            "humidity": 45.0,
            "visibility_factor": 0.95,
            "weather_condition": "clear"
        },
        "tracked_obstacles": 0,
        "adaptive_weights_enabled": True
    }


@router.get("/environmental/status")
async def get_environmental_safety_status(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get environmental safety status"""
    return {
        "timestamp": datetime.now().isoformat(),
        "current_slope": {
            "angle_degrees": 5.2,
            "safety_assessment": "safe",
            "stability_factor": 0.92
        },
        "current_surface": {
            "surface_type": "grass_dry",
            "moisture_level": 0.3,
            "grip_factor": 0.85,
            "mowing_suitability": 0.95
        },
        "active_hazards": 0,
        "recent_wildlife_detections": 1,
        "safety_thresholds": {
            "max_safe_slope": 15.0,
            "min_grip_factor": 0.6,
            "min_stability_factor": 0.7
        },
        "environmental_conditions": {
            "temperature": 22.5,
            "humidity": 45.0,
            "light_level": 85000,
            "weather_condition": "clear",
            "wind_speed": 2.3,
            "precipitation": False
        }
    }


@router.get("/maintenance/status")
async def get_maintenance_safety_status(
    current_user: Dict[str, Any] = Depends(require_permission("read"))
):
    """Get maintenance safety status"""
    return {
        "timestamp": datetime.now().isoformat(),
        "blade_status": {
            "main_blade": {
                "condition": "good",
                "wear_percentage": 35.2,
                "sharpness_score": 0.82,
                "cutting_efficiency": 0.88,
                "replacement_recommended": False,
                "safety_concern": False,
                "estimated_remaining_hours": 128.5
            }
        },
        "battery_status": {
            "main_battery": {
                "health_status": "good",
                "capacity_percentage": 87.5,
                "voltage": 12.3,
                "temperature": 23.8,
                "charge_cycles": 156,
                "safety_concerns": [],
                "estimated_remaining_life_days": 1247
            }
        },
        "active_lockouts": 0,
        "maintenance_reminders": [
            {
                "type": "blade_inspection",
                "description": "Visual blade inspection and sharpness test",
                "overdue_hours": 8.5,
                "required_access_level": "basic"
            }
        ],
        "recent_diagnostics": 3,
        "system_health": "good",
        "safety_thresholds": {
            "blade_wear_threshold": 70.0,
            "battery_capacity_threshold": 80.0,
            "battery_temp_max": 45.0,
            "vibration_threshold": 2.0
        }
    }


@router.post("/emergency/trigger")
async def trigger_emergency_stop(
    emergency_data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Trigger emergency stop with enhanced safety protocols"""
    reason = emergency_data.get('reason', 'Manual emergency stop')
    username = current_user.get('username')
    
    logger.critical(f"Emergency stop triggered by user {username}: {reason}")
    
    # Mock emergency response - in practice this would trigger the actual emergency system
    return {
        "success": True,
        "message": "Emergency stop activated",
        "timestamp": datetime.now().isoformat(),
        "triggered_by": username,
        "reason": reason,
        "emergency_id": f"emergency_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    }


@router.get("/protocols/violations")
async def get_safety_violations(
    current_user: Dict[str, Any] = Depends(require_permission("read"))
):
    """Get recent safety violations and protocol events"""
    return {
        "timestamp": datetime.now().isoformat(),
        "active_violations": 0,
        "total_events_today": 2,
        "recent_violations": [
            {
                "event_id": "boundary_breach_20241215_143022",
                "type": "boundary_breach",
                "severity": "caution",
                "timestamp": "2024-12-15T14:30:22",
                "resolved": True,
                "description": "Temporary boundary violation in zone garden_bed"
            },
            {
                "event_id": "weather_violation_20241215_080145", 
                "type": "weather_violation",
                "severity": "warning",
                "timestamp": "2024-12-15T08:01:45",
                "resolved": True,
                "description": "Weather safety rule applied: light rain detected"
            }
        ],
        "current_weather": "clear",
        "weather_override_active": False,
        "geofence_zones": 3,
        "emergency_contacts": 2,
        "remote_shutdown_enabled": True
    }


@router.post("/configuration/update")
async def update_safety_configuration(
    config_data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Update safety configuration parameters based on user access level"""
    username = current_user.get('username')
    
    # Mock parameter validation based on access level
    # In practice, this would check user permissions for each parameter
    allowed_parameters = [
        "emergency_stop_distance",
        "person_safety_radius",
        "pet_safety_radius", 
        "boundary_safety_margin"
    ]
    
    updated_parameters = {}
    denied_parameters = {}
    
    for param, value in config_data.items():
        if param in allowed_parameters:
            updated_parameters[param] = value
            logger.info(f"User {username} updated safety parameter {param} to {value}")
        else:
            denied_parameters[param] = "Insufficient access level"
    
    return {
        "success": len(updated_parameters) > 0,
        "updated_parameters": updated_parameters,
        "denied_parameters": denied_parameters,
        "message": f"Updated {len(updated_parameters)} parameters, denied {len(denied_parameters)} parameters",
        "timestamp": datetime.now().isoformat()
    }


@router.get("/diagnostics/run/{diagnostic_type}")
async def run_safety_diagnostic(
    diagnostic_type: str,
    current_user: Dict[str, Any] = Depends(require_permission("write"))
):
    """Run safety system diagnostic"""
    username = current_user.get('username')
    
    valid_types = ["full", "blade", "battery", "sensors", "mechanical"]
    if diagnostic_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid diagnostic type. Must be one of: {', '.join(valid_types)}"
        )
    
    logger.info(f"User {username} initiated {diagnostic_type} safety diagnostic")
    
    # Mock diagnostic results
    return {
        "success": True,
        "diagnostic_type": diagnostic_type,
        "initiated_by": username,
        "timestamp": datetime.now().isoformat(),
        "estimated_completion_time": "2024-12-15T15:05:00",
        "diagnostic_id": f"{diagnostic_type}_diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "message": f"{diagnostic_type.title()} diagnostic initiated successfully"
    }
