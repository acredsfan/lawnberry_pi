"""
Vision system API endpoints with comprehensive TPU integration
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import cv2
import io

from vision.vision_manager import VisionManager
from vision.coral_tpu_manager import CoralTPUManager
from vision.tpu_dashboard import TPUPerformanceDashboard
from ..dependencies import get_system_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/vision", tags=["vision"])


class TPUStatusResponse(BaseModel):
    available: bool
    operational: bool
    temperature: float
    power_draw: float
    utilization: float
    model_name: Optional[str]
    inference_times_ms: List[float]
    cache_hit_rate: float
    error_count: int


class ModelPerformanceResponse(BaseModel):
    model_name: str
    accuracy: float
    inference_time_ms: float
    confidence_scores: List[float]
    detections_count: int
    tpu_optimized: bool


@router.get("/acceleration/status")
async def get_acceleration_status(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get comprehensive acceleration status (TPU or CPU fallback)"""
    try:
        vision_manager = getattr(system_manager, 'vision_manager', None)
        if not vision_manager:
            raise HTTPException(status_code=503, detail="Vision system not available")
        
        object_detector = getattr(vision_manager, 'object_detector', None)
        if not object_detector:
            return {
                "success": True,
                "data": {
                    "coral_available": False,
                    "cpu_fallback_active": False,
                    "operational": False,
                    "message": "Object detector not configured"
                }
            }
        
        # Check both TPU and CPU managers
        tpu_manager = getattr(object_detector, 'tpu_manager', None)
        cpu_manager = getattr(object_detector, 'cpu_manager', None)
        
        status_data = {
            "coral_available": False,
            "coral_hardware_present": False,
            "cpu_fallback_active": False,
            "operational": False,
            "acceleration_mode": "none"
        }
        
        # Get TPU status if available
        if tpu_manager and tpu_manager.is_available():
            tpu_status = await tpu_manager.get_comprehensive_status()
            tpu_performance = tpu_manager.get_performance_stats()
            
            status_data.update({
                "coral_available": True,
                "coral_hardware_present": tpu_status.get('tpu_available', False),
                "operational": tpu_status.get('operational', False),
                "acceleration_mode": "coral_tpu",
                "temperature": tpu_status.get('temperature', 0.0),
                "power_draw": tpu_status.get('power_draw', 0.0),
                "utilization": tpu_status.get('utilization', 0.0),
                "model_name": tpu_status.get('current_model', None),
                "inference_times_ms": tpu_performance.get('recent_inference_times', []),
                "cache_hit_rate": tpu_performance.get('cache_hit_rate', 0.0),
                "error_count": tpu_status.get('error_count', 0),
                "health_status": tpu_status.get('health_status', 'unknown'),
                "device_info": tpu_status.get('device_info', {})
            })
        
        # Get CPU fallback status if TPU not available
        elif cpu_manager and cpu_manager.is_available():
            cpu_status = await cpu_manager.get_comprehensive_status()
            cpu_performance = cpu_manager.get_performance_stats()
            
            status_data.update({
                "cpu_fallback_active": True,
                "operational": cpu_status.get('operational', False),
                "acceleration_mode": "cpu_fallback",
                "model_name": cpu_status.get('current_model', None),
                "inference_times_ms": cpu_performance.get('recent_inference_times', []),
                "device_info": cpu_status.get('device_info', {}),
                "performance_note": "Running in CPU mode - consider Coral TPU for better performance"
            })
        
        return {
            "success": True,
            "data": status_data
        }
        
    except Exception as e:
        logger.error(f"Error getting acceleration status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get acceleration status: {str(e)}")


@router.get("/tpu/performance")
async def get_tpu_performance_metrics(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get detailed TPU performance analytics"""
    try:
        vision_manager = getattr(system_manager, 'vision_manager', None)
        if not vision_manager:
            raise HTTPException(status_code=503, detail="Vision system not available")
        
        tpu_dashboard = getattr(vision_manager, 'tpu_dashboard', None)
        if not tpu_dashboard:
            raise HTTPException(status_code=503, detail="TPU dashboard not available")
        
        # Get comprehensive performance data
        dashboard_data = await tpu_dashboard.get_dashboard_data()
        
        return {
            "success": True,
            "data": dashboard_data
        }
        
    except Exception as e:
        logger.error(f"Error getting TPU performance metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get TPU performance: {str(e)}")


@router.post("/tpu/benchmark")
async def run_tpu_benchmark(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Run TPU performance benchmark"""
    try:
        vision_manager = getattr(system_manager, 'vision_manager', None)
        if not vision_manager:
            raise HTTPException(status_code=503, detail="Vision system not available")
        
        tpu_manager = getattr(vision_manager, 'tpu_manager', None)
        if not tpu_manager:
            raise HTTPException(status_code=503, detail="TPU not available")
        
        # Run comprehensive benchmark
        benchmark_results = await tpu_manager.run_comprehensive_benchmark()
        
        return {
            "success": True,
            "data": benchmark_results,
            "message": "TPU benchmark completed successfully"
        }
        
    except Exception as e:
        logger.error(f"Error running TPU benchmark: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to run benchmark: {str(e)}")


@router.get("/models")
async def get_available_models(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get list of available custom models"""
    try:
        vision_manager = getattr(system_manager, 'vision_manager', None)
        if not vision_manager:
            raise HTTPException(status_code=503, detail="Vision system not available")
        
        # Get model information
        models = await vision_manager.get_available_models()
        
        return {
            "success": True,
            "data": {
                "models": models,
                "count": len(models)
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting available models: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get models: {str(e)}")


@router.post("/models/{model_name}/load")
async def load_model(model_name: str, system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Load a specific model for inference"""
    try:
        vision_manager = getattr(system_manager, 'vision_manager', None)
        if not vision_manager:
            raise HTTPException(status_code=503, detail="Vision system not available")
        
        # Load the specified model
        success = await vision_manager.load_model(model_name)
        
        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to load model: {model_name}")
        
        return {
            "success": True,
            "message": f"Model {model_name} loaded successfully"
        }
        
    except Exception as e:
        logger.error(f"Error loading model {model_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load model: {str(e)}")


@router.get("/models/{model_name}/performance")
async def get_model_performance(model_name: str, system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get performance metrics for a specific model"""
    try:
        vision_manager = getattr(system_manager, 'vision_manager', None)
        if not vision_manager:
            raise HTTPException(status_code=503, detail="Vision system not available")
        
        # Get model performance data
        performance = await vision_manager.get_model_performance(model_name)
        
        return {
            "success": True,
            "data": performance
        }
        
    except Exception as e:
        logger.error(f"Error getting model performance for {model_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get model performance: {str(e)}")


@router.get("/detection/status")
async def get_detection_status(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get current object detection status"""
    try:
        vision_manager = getattr(system_manager, 'vision_manager', None)
        if not vision_manager:
            raise HTTPException(status_code=503, detail="Vision system not available")
        
        # Get detection status
        status = await vision_manager.get_detection_status()
        
        return {
            "success": True,
            "data": status
        }
        
    except Exception as e:
        logger.error(f"Error getting detection status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get detection status: {str(e)}")


@router.post("/detection/test")
async def test_detection(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Test object detection with current camera feed"""
    try:
        vision_manager = getattr(system_manager, 'vision_manager', None)
        if not vision_manager:
            raise HTTPException(status_code=503, detail="Vision system not available")
        
        # Run detection test
        test_results = await vision_manager.test_detection()
        
        return {
            "success": True,
            "data": test_results,
            "message": "Detection test completed"
        }
        
    except Exception as e:
        logger.error(f"Error testing detection: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to test detection: {str(e)}")


@router.get("/config")
async def get_vision_config(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get current vision system configuration"""
    try:
        vision_manager = getattr(system_manager, 'vision_manager', None)
        if not vision_manager:
            raise HTTPException(status_code=503, detail="Vision system not available")
        
        # Get configuration
        config = vision_manager.get_config()
        
        return {
            "success": True,
            "data": config
        }
        
    except Exception as e:
        logger.error(f"Error getting vision config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get config: {str(e)}")


@router.post("/config/update")
async def update_vision_config(config_update: Dict[str, Any], system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Update vision system configuration"""
    try:
        vision_manager = getattr(system_manager, 'vision_manager', None)
        if not vision_manager:
            raise HTTPException(status_code=503, detail="Vision system not available")
        
        # Update configuration
        success = await vision_manager.update_config(config_update)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to update configuration")
        
        return {
            "success": True,
            "message": "Configuration updated successfully"
        }
        
    except Exception as e:
        logger.error(f"Error updating vision config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update config: {str(e)}")


@router.get("/camera/stream")
async def camera_stream(system_manager=Depends(get_system_manager)) -> StreamingResponse:
    """Get live camera stream"""
    try:
        # Check if hardware interface exists
        hardware_interface = getattr(system_manager, 'hardware_interface', None)
        if not hardware_interface:
            raise HTTPException(status_code=503, detail="Hardware interface not available")
        
        async def generate_stream():
            """Generate MJPEG stream"""
            try:
                while True:
                    # Get latest camera frame
                    frame = await hardware_interface.get_camera_frame()
                    if frame and frame.data:
                        # Frame is already in JPEG format from CameraManager
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame.data + b'\r\n')
                    else:
                        # Generate a placeholder frame if camera not available
                        placeholder = _generate_placeholder_frame()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + placeholder + b'\r\n')
                    
                    await asyncio.sleep(1/30)  # 30 FPS
                    
            except Exception as e:
                logger.error(f"Stream generation error: {e}")
                # Send error frame
                error_frame = _generate_error_frame(str(e))
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + error_frame + b'\r\n')
        
        return StreamingResponse(
            generate_stream(),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )
        
    except Exception as e:
        logger.error(f"Error setting up camera stream: {e}")
        raise HTTPException(status_code=500, detail=f"Camera stream error: {str(e)}")


@router.get("/camera/frame")
async def get_camera_frame(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get single camera frame as base64"""
    try:
        hardware_interface = getattr(system_manager, 'hardware_interface', None)
        if not hardware_interface:
            raise HTTPException(status_code=503, detail="Hardware interface not available")
        
        frame = await hardware_interface.get_camera_frame()
        if not frame:
            return {
                "success": False,
                "message": "No camera frame available"
            }
        
        import base64
        frame_b64 = base64.b64encode(frame.data).decode('utf-8')
        
        return {
            "success": True,
            "data": {
                "frame_id": frame.frame_id,
                "timestamp": frame.timestamp.isoformat(),
                "width": frame.width,
                "height": frame.height,
                "format": frame.format,
                "data": frame_b64
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting camera frame: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get frame: {str(e)}")


@router.get("/camera/status")
async def get_camera_status(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get camera system status"""
    try:
        hardware_interface = getattr(system_manager, 'hardware_interface', None)
        if not hardware_interface:
            raise HTTPException(status_code=503, detail="Hardware interface not available")
        
        # Get camera manager status
        camera_manager = getattr(hardware_interface, 'camera_manager', None)
        if not camera_manager:
            return {
                "success": True,
                "data": {
                    "available": False,
                    "capturing": False,
                    "message": "Camera manager not available"
                }
            }
        
        # Get recent frame to test functionality
        frame = await hardware_interface.get_camera_frame()
        
        return {
            "success": True,
            "data": {
                "available": True,
                "capturing": camera_manager._capturing if hasattr(camera_manager, '_capturing') else False,
                "device_path": getattr(camera_manager, 'device_path', '/dev/video0'),
                "last_frame": {
                    "available": frame is not None,
                    "frame_id": frame.frame_id if frame else None,
                    "timestamp": frame.timestamp.isoformat() if frame else None,
                    "resolution": f"{frame.width}x{frame.height}" if frame else None
                } if frame else None
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting camera status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get camera status: {str(e)}")


def _generate_placeholder_frame() -> bytes:
    """Generate a placeholder frame when camera is not available"""
    try:
        import numpy as np
        
        # Create a simple placeholder image
        height, width = 480, 640
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:] = (64, 64, 64)  # Dark gray background
        
        # Add text
        cv2.putText(frame, "Camera Not Available", (width//2 - 120, height//2), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        cv2.putText(frame, "LawnBerryPi", (width//2 - 60, height//2 + 40), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Encode as JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        return buffer.tobytes()
        
    except Exception:
        # Fallback to minimal frame
        return b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x11\x08\x01\xe0\x02\x80\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01\xff\xc4\x00\x14\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\xff\xc4\x00\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xda\x00\x0c\x03\x01\x00\x02\x11\x03\x11\x00\x3f\x00\xaa\xff\xd9'


def _generate_error_frame(error_message: str) -> bytes:
    """Generate an error frame with message"""
    try:
        import numpy as np
        
        height, width = 480, 640
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:] = (40, 40, 80)  # Dark red background
        
        # Add error text
        cv2.putText(frame, "Camera Error", (width//2 - 80, height//2 - 40), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        # Truncate long error messages
        if len(error_message) > 40:
            error_message = error_message[:37] + "..."
            
        cv2.putText(frame, error_message, (20, height//2 + 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 200), 1)
        
        # Encode as JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        return buffer.tobytes()
        
    except Exception:
        # Return minimal error frame
        return _generate_placeholder_frame()
