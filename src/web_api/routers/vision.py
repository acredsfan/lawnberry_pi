"""
Vision system API endpoints with comprehensive TPU integration
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from ...vision.vision_manager import VisionManager
from ...vision.coral_tpu_manager import CoralTPUManager
from ...vision.tpu_dashboard import TPUPerformanceDashboard
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


@router.get("/tpu/status")
async def get_tpu_status(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get comprehensive TPU status and performance metrics"""
    try:
        vision_manager = getattr(system_manager, 'vision_manager', None)
        if not vision_manager:
            raise HTTPException(status_code=503, detail="Vision system not available")
        
        tpu_manager = getattr(vision_manager, 'tpu_manager', None)
        if not tpu_manager:
            return {
                "success": True,
                "data": {
                    "available": False,
                    "operational": False,
                    "message": "TPU not configured"
                }
            }
        
        # Get comprehensive TPU status
        status = await tpu_manager.get_comprehensive_status()
        performance_stats = tpu_manager.get_performance_stats()
        
        return {
            "success": True,
            "data": {
                "available": status.get('tpu_available', False),
                "operational": status.get('operational', False),
                "temperature": status.get('temperature', 0.0),
                "power_draw": status.get('power_draw', 0.0),
                "utilization": status.get('utilization', 0.0),
                "model_name": status.get('current_model', None),
                "inference_times_ms": performance_stats.get('recent_inference_times', []),
                "cache_hit_rate": performance_stats.get('cache_hit_rate', 0.0),
                "error_count": status.get('error_count', 0),
                "health_status": status.get('health_status', 'unknown'),
                "last_inference": status.get('last_inference_time', None),
                "device_info": status.get('device_info', {})
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting TPU status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get TPU status: {str(e)}")


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
