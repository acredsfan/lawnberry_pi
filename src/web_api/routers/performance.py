"""
Performance Management API Router
Provides REST endpoints for dynamic resource management and performance monitoring
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

from ..dependencies import get_system_manager
from system_integration.dynamic_resource_manager import OperationMode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/performance", tags=["performance"])


@router.get("/status")
async def get_performance_status(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get comprehensive performance status including dynamic resource management"""
    try:
        # Get enhanced system status
        enhanced_status = await system_manager.enhanced_monitor.get_comprehensive_status()
        
        return {
            "success": True,
            "data": enhanced_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting performance status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard")
async def get_performance_dashboard(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get performance dashboard data"""
    try:
        dashboard_data = await system_manager.enhanced_monitor.dashboard.get_dashboard_data()
        
        return {
            "success": True,
            "data": dashboard_data,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting dashboard data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/predictions")
async def get_performance_predictions(
    horizon_minutes: int = Query(30, ge=5, le=180, description="Prediction horizon in minutes"),
    system_manager=Depends(get_system_manager)
) -> Dict[str, Any]:
    """Get performance predictions for specified time horizon"""
    try:
        predictions = await system_manager.enhanced_monitor.get_performance_predictions(horizon_minutes)
        
        return {
            "success": True,
            "data": predictions,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resource-allocation")
async def get_resource_allocation(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get current resource allocation status"""
    try:
        resource_status = await system_manager.enhanced_monitor.resource_manager.get_current_status()
        
        return {
            "success": True,
            "data": resource_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting resource allocation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/operation-mode")
async def set_operation_mode(
    mode: str,
    system_manager=Depends(get_system_manager)
) -> Dict[str, Any]:
    """Set system operation mode for dynamic resource optimization"""
    try:
        # Validate mode
        try:
            operation_mode = OperationMode(mode.lower())
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid operation mode. Valid modes: {[m.value for m in OperationMode]}"
            )
        
        # Set operation mode
        await system_manager.enhanced_monitor.set_operation_mode(operation_mode)
        
        return {
            "success": True,
            "message": f"Operation mode set to {mode}",
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting operation mode: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def get_performance_alerts(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get active performance alerts"""
    try:
        dashboard_data = await system_manager.enhanced_monitor.dashboard.get_dashboard_data()
        alerts = dashboard_data.get('active_alerts', {})
        
        return {
            "success": True,
            "data": {
                "active_alerts": alerts,
                "alert_count": len(alerts)
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    system_manager=Depends(get_system_manager)
) -> Dict[str, Any]:
    """Acknowledge a performance alert"""
    try:
        success = await system_manager.enhanced_monitor.dashboard.acknowledge_alert(alert_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return {
            "success": True,
            "message": f"Alert {alert_id} acknowledged",
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/optimization-suggestions")
async def get_optimization_suggestions(
    limit: int = Query(10, ge=1, le=50, description="Maximum number of suggestions to return"),
    system_manager=Depends(get_system_manager)
) -> Dict[str, Any]:
    """Get system optimization suggestions"""
    try:
        enhanced_status = await system_manager.enhanced_monitor.get_comprehensive_status()
        suggestions = enhanced_status.get('optimization_suggestions', [])
        
        # Limit results
        limited_suggestions = suggestions[-limit:] if suggestions else []
        
        return {
            "success": True,
            "data": {
                "suggestions": limited_suggestions,
                "total_suggestions": len(suggestions)
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting optimization suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/automation/rules")
async def get_automation_rules(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get automation rules status"""
    try:
        enhanced_status = await system_manager.enhanced_monitor.get_comprehensive_status()
        automation = enhanced_status.get('automation', {})
        
        return {
            "success": True,
            "data": automation,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting automation rules: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/automation/rules/{rule_id}/enable")
async def enable_automation_rule(
    rule_id: str,
    system_manager=Depends(get_system_manager)
) -> Dict[str, Any]:
    """Enable an automation rule"""
    try:
        success = await system_manager.enhanced_monitor.enable_automation_rule(rule_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Automation rule not found")
        
        return {
            "success": True,
            "message": f"Automation rule {rule_id} enabled",
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling automation rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/automation/rules/{rule_id}/disable")
async def disable_automation_rule(
    rule_id: str,
    system_manager=Depends(get_system_manager)
) -> Dict[str, Any]:
    """Disable an automation rule"""
    try:
        success = await system_manager.enhanced_monitor.disable_automation_rule(rule_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Automation rule not found")
        
        return {
            "success": True,
            "message": f"Automation rule {rule_id} disabled",
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling automation rule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report")
async def get_performance_report(
    hours: int = Query(24, ge=1, le=168, description="Report period in hours"),
    system_manager=Depends(get_system_manager)
) -> Dict[str, Any]:
    """Get comprehensive performance report"""
    try:
        report = await system_manager.enhanced_monitor.dashboard.get_performance_report(hours)
        
        return {
            "success": True,
            "data": report,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error generating performance report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/efficiency")
async def get_efficiency_metrics(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get detailed efficiency metrics"""
    try:
        dashboard_data = await system_manager.enhanced_monitor.dashboard.get_dashboard_data()
        efficiency_metrics = dashboard_data.get('efficiency_metrics', {})
        
        return {
            "success": True,
            "data": efficiency_metrics,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting efficiency metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services/performance")
async def get_service_performance(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get individual service performance statistics"""
    try:
        dashboard_data = await system_manager.enhanced_monitor.dashboard.get_dashboard_data()
        service_performance = dashboard_data.get('service_performance', {})
        
        return {
            "success": True,
            "data": service_performance,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting service performance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/allocations")
async def get_allocation_history(
    limit: int = Query(50, ge=1, le=200, description="Maximum number of allocation decisions to return"),
    system_manager=Depends(get_system_manager)
) -> Dict[str, Any]:
    """Get recent resource allocation decision history"""
    try:
        dashboard_data = await system_manager.enhanced_monitor.dashboard.get_dashboard_data()
        allocations = dashboard_data.get('recent_allocations', [])
        
        # Limit results
        limited_allocations = allocations[-limit:] if allocations else []
        
        return {
            "success": True,
            "data": {
                "allocations": limited_allocations,
                "total_decisions": len(allocations)
            },
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting allocation history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/monitoring/status")
async def get_monitoring_status(system_manager=Depends(get_system_manager)) -> Dict[str, Any]:
    """Get dynamic monitoring system status"""
    try:
        enhanced_status = await system_manager.enhanced_monitor.get_comprehensive_status()
        monitoring_status = enhanced_status.get('enhanced_monitoring', {})
        
        return {
            "success": True,
            "data": monitoring_status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting monitoring status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
