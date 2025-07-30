"""
Boundary Monitor - GPS-based boundary enforcement and no-go zone management
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass
import math

from ..communication import MQTTClient, MessageProtocol, SensorData
from ..hardware.data_structures import GPSReading
from ..sensor_fusion.data_structures import HazardLevel

logger = logging.getLogger(__name__)


@dataclass
class BoundaryPoint:
    """GPS boundary point"""
    latitude: float
    longitude: float
    point_id: str
    timestamp: datetime


@dataclass
class NoGoZone:
    """No-go zone definition"""
    zone_id: str
    name: str
    boundary_points: List[BoundaryPoint]
    zone_type: str  # "permanent", "temporary", "weather", "maintenance"
    active: bool
    created_by: str
    expires_at: Optional[datetime] = None


@dataclass
class BoundaryViolation:
    """Boundary violation event"""
    violation_id: str
    violation_type: str  # "boundary_exit", "no_go_entry", "safety_margin"
    current_position: Tuple[float, float]  # lat, lon
    violation_distance: float  # meters
    severity: HazardLevel
    timestamp: datetime
    zone_info: Optional[Dict[str, Any]] = None


class BoundaryMonitor:
    """
    GPS-based boundary monitoring system that enforces yard boundaries
    and no-go zones with 1m safety margin
    """
    
    def __init__(self, mqtt_client: MQTTClient, config):
        self.mqtt_client = mqtt_client
        self.config = config
        
        # Boundary configuration
        self._safety_margin_m = config.boundary_safety_margin_m
        self._gps_accuracy_threshold_m = 2.0  # Only trust GPS readings better than 2m
        
        # Boundary and zone data
        self._yard_boundary: List[BoundaryPoint] = []
        self._no_go_zones: Dict[str, NoGoZone] = {}
        self._current_position: Optional[GPSReading] = None
        
        # Violation tracking
        self._active_violations: Dict[str, BoundaryViolation] = {}
        self._violation_history: List[BoundaryViolation] = []
        
        # Monitoring state
        self._boundary_loaded = False
        self._monitoring_active = False
        self._last_valid_position: Optional[Tuple[float, float]] = None
        
        # Performance tracking
        self._boundary_checks_count = 0
        self._violations_count = 0
        self._false_violations_count = 0
        
        # Emergency callbacks
        self._emergency_callbacks: List[Callable] = []
        
        # Tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start(self):
        """Start the boundary monitoring system"""
        logger.info("Starting boundary monitoring system")
        self._running = True
        
        # Subscribe to boundary and position data
        await self._subscribe_to_boundary_data()
        
        # Load boundary configuration
        await self._load_boundary_configuration()
        
        # Start monitoring task
        self._monitoring_task = asyncio.create_task(self._boundary_monitoring_loop())
        
        logger.info("Boundary monitoring system started")
    
    async def stop(self):
        """Stop the boundary monitoring system"""
        logger.info("Stopping boundary monitoring system")
        self._running = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
    
    async def _subscribe_to_boundary_data(self):
        """Subscribe to boundary-related MQTT topics"""
        subscriptions = [
            ("lawnberry/maps/boundaries", self._handle_boundary_update),
            ("lawnberry/maps/no_go_zones", self._handle_no_go_zones_update),
            ("lawnberry/maps/boundary_test", self._handle_boundary_test)
        ]
        
        for topic, handler in subscriptions:
            await self.mqtt_client.subscribe(topic, handler)
    
    async def _load_boundary_configuration(self):
        """Load boundary configuration from persistent storage"""
        try:
            # Request current boundary data
            await self.mqtt_client.publish(
                "lawnberry/maps/request_boundaries",
                SensorData.create(
                    sender="boundary_monitor",
                    sensor_type="boundary_request",
                    data={"request_type": "all_boundaries"}
                )
            )
            
            # Wait a moment for data to arrive
            await asyncio.sleep(1.0)
            
            if self._yard_boundary:
                self._boundary_loaded = True
                self._monitoring_active = True
                logger.info(f"Boundary loaded with {len(self._yard_boundary)} points")
            else:
                logger.warning("No boundary data loaded - monitoring disabled")
                
        except Exception as e:
            logger.error(f"Error loading boundary configuration: {e}")
    
    async def _handle_boundary_update(self, topic: str, message: MessageProtocol):
        """Handle boundary update from mapping system"""
        try:
            boundary_data = message.payload
            
            if boundary_data.get('boundary_type') == 'yard_boundary':
                await self._update_yard_boundary(boundary_data['points'])
            
        except Exception as e:
            logger.error(f"Error handling boundary update: {e}")
    
    async def _update_yard_boundary(self, boundary_points: List[Dict[str, Any]]):
        """Update yard boundary points"""
        try:
            new_boundary = []
            
            for point_data in boundary_points:
                boundary_point = BoundaryPoint(
                    latitude=point_data['latitude'],
                    longitude=point_data['longitude'],
                    point_id=point_data.get('point_id', f"point_{len(new_boundary)}"),
                    timestamp=datetime.fromisoformat(point_data.get('timestamp', datetime.now().isoformat()))
                )
                new_boundary.append(boundary_point)
            
            self._yard_boundary = new_boundary
            self._boundary_loaded = len(new_boundary) >= 3  # Minimum 3 points for a boundary
            
            if self._boundary_loaded:
                self._monitoring_active = True
                logger.info(f"Yard boundary updated with {len(new_boundary)} points")
                
                # Publish boundary status
                await self._publish_boundary_status()
            else:
                logger.warning(f"Insufficient boundary points ({len(new_boundary)}) - need at least 3")
                
        except Exception as e:
            logger.error(f"Error updating yard boundary: {e}")
    
    async def _handle_no_go_zones_update(self, topic: str, message: MessageProtocol):
        """Handle no-go zones update"""
        try:
            zones_data = message.payload
            
            for zone_data in zones_data.get('zones', []):
                await self._update_no_go_zone(zone_data)
                
        except Exception as e:
            logger.error(f"Error handling no-go zones update: {e}")
    
    async def _update_no_go_zone(self, zone_data: Dict[str, Any]):
        """Update or create a no-go zone"""
        try:
            zone_id = zone_data['zone_id']
            
            # Create boundary points for the zone
            zone_points = []
            for point_data in zone_data['boundary_points']:
                boundary_point = BoundaryPoint(
                    latitude=point_data['latitude'],
                    longitude=point_data['longitude'],
                    point_id=point_data.get('point_id', f"zone_{zone_id}_point_{len(zone_points)}"),
                    timestamp=datetime.now()
                )
                zone_points.append(boundary_point)
            
            # Create or update no-go zone
            no_go_zone = NoGoZone(
                zone_id=zone_id,
                name=zone_data.get('name', f"No-go zone {zone_id}"),
                boundary_points=zone_points,
                zone_type=zone_data.get('zone_type', 'permanent'),
                active=zone_data.get('active', True),
                created_by=zone_data.get('created_by', 'system'),
                expires_at=datetime.fromisoformat(zone_data['expires_at']) if zone_data.get('expires_at') else None
            )
            
            self._no_go_zones[zone_id] = no_go_zone
            logger.info(f"Updated no-go zone {zone_id}: {no_go_zone.name}")
            
        except Exception as e:
            logger.error(f"Error updating no-go zone: {e}")
    
    async def update_position(self, gps_reading: GPSReading):
        """Update current position and check for boundary violations"""
        try:
            # Validate GPS reading accuracy
            if gps_reading.accuracy > self._gps_accuracy_threshold_m:
                logger.debug(f"GPS accuracy {gps_reading.accuracy}m exceeds threshold {self._gps_accuracy_threshold_m}m")
                return
            
            self._current_position = gps_reading
            current_coords = (gps_reading.latitude, gps_reading.longitude)
            
            # Update last valid position
            self._last_valid_position = current_coords
            
            # Check boundaries if monitoring is active
            if self._monitoring_active and self._boundary_loaded:
                await self._check_boundary_violations(current_coords)
            
            self._boundary_checks_count += 1
            
        except Exception as e:
            logger.error(f"Error updating position: {e}")
    
    async def _check_boundary_violations(self, current_coords: Tuple[float, float]):
        """Check for boundary and no-go zone violations"""
        try:
            lat, lon = current_coords
            
            # Check yard boundary
            if self._yard_boundary:
                distance_to_boundary = self._calculate_distance_to_boundary(current_coords, self._yard_boundary)
                
                # Check if outside boundary (negative distance means outside)
                if distance_to_boundary < 0:
                    await self._handle_boundary_violation(
                        "boundary_exit",
                        current_coords,
                        abs(distance_to_boundary),
                        HazardLevel.HIGH
                    )
                elif distance_to_boundary < self._safety_margin_m:
                    await self._handle_boundary_violation(
                        "safety_margin",
                        current_coords,
                        self._safety_margin_m - distance_to_boundary,
                        HazardLevel.MEDIUM
                    )
            
            # Check no-go zones
            for zone_id, zone in self._no_go_zones.items():
                if not zone.active:
                    continue
                
                # Check if zone has expired
                if zone.expires_at and datetime.now() > zone.expires_at:
                    zone.active = False
                    continue
                
                if self._is_point_inside_polygon(current_coords, zone.boundary_points):
                    await self._handle_boundary_violation(
                        "no_go_entry",
                        current_coords,
                        0.0,  # Inside the zone
                        HazardLevel.HIGH,
                        zone_info={
                            'zone_id': zone_id,
                            'zone_name': zone.name,
                            'zone_type': zone.zone_type
                        }
                    )
            
        except Exception as e:
            logger.error(f"Error checking boundary violations: {e}")
    
    def _calculate_distance_to_boundary(self, point: Tuple[float, float], 
                                      boundary_points: List[BoundaryPoint]) -> float:
        """Calculate distance from point to boundary (positive = inside, negative = outside)"""
        try:
            lat, lon = point
            
            # Convert boundary points to coordinate tuples
            boundary_coords = [(bp.latitude, bp.longitude) for bp in boundary_points]
            
            # Check if point is inside polygon using ray casting algorithm
            inside = self._is_point_inside_polygon(point, boundary_points)
            
            # Calculate minimum distance to boundary edges
            min_distance = float('inf')
            
            for i in range(len(boundary_coords)):
                j = (i + 1) % len(boundary_coords)
                
                # Calculate distance from point to line segment
                distance = self._point_to_line_distance(
                    point, boundary_coords[i], boundary_coords[j]
                )
                min_distance = min(min_distance, distance)
            
            # Return positive distance if inside, negative if outside
            return min_distance if inside else -min_distance
            
        except Exception as e:
            logger.error(f"Error calculating distance to boundary: {e}")
            return 0.0
    
    def _is_point_inside_polygon(self, point: Tuple[float, float], 
                               boundary_points: List[BoundaryPoint]) -> bool:
        """Check if point is inside polygon using ray casting algorithm"""
        try:
            lat, lon = point
            boundary_coords = [(bp.latitude, bp.longitude) for bp in boundary_points]
            
            n = len(boundary_coords)
            inside = False
            
            p1_lat, p1_lon = boundary_coords[0]
            for i in range(1, n + 1):
                p2_lat, p2_lon = boundary_coords[i % n]
                
                if lat > min(p1_lat, p2_lat):
                    if lat <= max(p1_lat, p2_lat):
                        if lon <= max(p1_lon, p2_lon):
                            if p1_lat != p2_lat:
                                xinters = (lat - p1_lat) * (p2_lon - p1_lon) / (p2_lat - p1_lat) + p1_lon
                            if p1_lon == p2_lon or lon <= xinters:
                                inside = not inside
                
                p1_lat, p1_lon = p2_lat, p2_lon
            
            return inside
            
        except Exception as e:
            logger.error(f"Error checking point inside polygon: {e}")
            return False
    
    def _point_to_line_distance(self, point: Tuple[float, float], 
                              line_start: Tuple[float, float], 
                              line_end: Tuple[float, float]) -> float:
        """Calculate distance from point to line segment in meters"""
        try:
            # Convert GPS coordinates to approximate meters using equirectangular projection
            def gps_to_meters(lat, lon, ref_lat, ref_lon):
                R = 6371000  # Earth radius in meters
                lat_rad = math.radians(lat)
                ref_lat_rad = math.radians(ref_lat)
                delta_lat = math.radians(lat - ref_lat)
                delta_lon = math.radians(lon - ref_lon)
                
                x = delta_lon * math.cos((lat_rad + ref_lat_rad) / 2) * R
                y = delta_lat * R
                return x, y
            
            # Use line start as reference point
            ref_lat, ref_lon = line_start
            
            # Convert all points to meters
            px, py = gps_to_meters(point[0], point[1], ref_lat, ref_lon)
            ax, ay = 0, 0  # line_start is reference
            bx, by = gps_to_meters(line_end[0], line_end[1], ref_lat, ref_lon)
            
            # Calculate distance from point to line segment
            ab_length_sq = (bx - ax) ** 2 + (by - ay) ** 2
            
            if ab_length_sq == 0:
                # Line segment is a point
                return math.sqrt((px - ax) ** 2 + (py - ay) ** 2)
            
            # Parameter t that represents the projection of point onto line
            t = max(0, min(1, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / ab_length_sq))
            
            # Closest point on line segment
            closest_x = ax + t * (bx - ax)
            closest_y = ay + t * (by - ay)
            
            # Distance from point to closest point on line
            distance = math.sqrt((px - closest_x) ** 2 + (py - closest_y) ** 2)
            return distance
            
        except Exception as e:
            logger.error(f"Error calculating point to line distance: {e}")
            return 0.0
    
    async def _handle_boundary_violation(self, violation_type: str, position: Tuple[float, float],
                                       distance: float, severity: HazardLevel,
                                       zone_info: Optional[Dict[str, Any]] = None):
        """Handle boundary violation event"""
        try:
            violation_id = f"{violation_type}_{int(datetime.now().timestamp())}"
            
            violation = BoundaryViolation(
                violation_id=violation_id,
                violation_type=violation_type,
                current_position=position,
                violation_distance=distance,
                severity=severity,
                timestamp=datetime.now(),
                zone_info=zone_info
            )
            
            # Check if this is a new violation (avoid spam)
            similar_violation = self._find_similar_active_violation(violation)
            if similar_violation:
                # Update existing violation
                similar_violation.violation_distance = distance
                similar_violation.timestamp = datetime.now()
                return
            
            # Add new violation
            self._active_violations[violation_id] = violation
            self._violation_history.append(violation)
            self._violations_count += 1
            
            # Log violation
            logger.warning(f"Boundary violation: {violation_type} at {position}, distance: {distance:.1f}m")
            
            # Publish violation alert
            await self._publish_violation_alert(violation)
            
            # Trigger emergency callback if critical
            if severity in [HazardLevel.CRITICAL, HazardLevel.HIGH]:
                for callback in self._emergency_callbacks:
                    try:
                        await callback([{
                            'source': 'boundary_monitor',
                            'alert': {
                                'hazard_type': violation_type,
                                'hazard_level': severity.value,
                                'description': f"Boundary violation: {violation_type}",
                                'immediate_response_required': severity == HazardLevel.CRITICAL,
                                'violation_data': {
                                    'violation_type': violation_type,
                                    'position': position,
                                    'distance': distance,
                                    'zone_info': zone_info
                                }
                            }
                        }])
                    except Exception as e:
                        logger.error(f"Error in boundary emergency callback: {e}")
            
        except Exception as e:
            logger.error(f"Error handling boundary violation: {e}")
    
    def _find_similar_active_violation(self, new_violation: BoundaryViolation) -> Optional[BoundaryViolation]:
        """Find similar active violation to avoid duplicates"""
        for violation in self._active_violations.values():
            if (violation.violation_type == new_violation.violation_type and
                (datetime.now() - violation.timestamp).total_seconds() < 5.0):  # Within 5 seconds
                return violation
        return None
    
    async def _boundary_monitoring_loop(self):
        """Main boundary monitoring loop"""
        while self._running:
            try:
                # Clean up old violations
                await self._cleanup_old_violations()
                
                # Check for expired no-go zones
                await self._cleanup_expired_zones()
                
                # Publish monitoring status
                if self._boundary_checks_count % 100 == 0:  # Every 100 checks
                    await self._publish_monitoring_status()
                
                await asyncio.sleep(1.0)  # 1Hz monitoring rate
                
            except Exception as e:
                logger.error(f"Error in boundary monitoring loop: {e}")
                await asyncio.sleep(1.0)
    
    async def check_critical_violations(self) -> List[Dict[str, Any]]:
        """Check for critical boundary violations"""
        critical_violations = []
        
        try:
            current_time = datetime.now()
            
            for violation in self._active_violations.values():
                # Check if violation is recent and critical
                if ((current_time - violation.timestamp).total_seconds() < 10.0 and
                    violation.severity == HazardLevel.CRITICAL):
                    
                    critical_violations.append({
                        'source': 'boundary_monitor',
                        'alert': {
                            'hazard_type': f"critical_{violation.violation_type}",
                            'hazard_level': 'CRITICAL',
                            'description': f"Critical boundary violation: {violation.violation_type}",
                            'immediate_response_required': True,
                            'violation_data': {
                                'violation_type': violation.violation_type,
                                'position': violation.current_position,
                                'distance': violation.violation_distance,
                                'zone_info': violation.zone_info
                            }
                        }
                    })
            
        except Exception as e:
            logger.error(f"Error checking critical violations: {e}")
            critical_violations.append({
                'source': 'boundary_monitor',
                'alert': {
                    'hazard_type': 'system_error',
                    'hazard_level': 'CRITICAL',
                    'description': f"Boundary monitor error: {e}",
                    'immediate_response_required': True
                }
            })
        
        return critical_violations
    
    async def get_current_status(self) -> Dict[str, Any]:
        """Get current boundary monitoring status"""
        current_time = datetime.now()
        
        # Get recent violations
        recent_violations = [
            {
                'violation_type': v.violation_type,
                'distance': v.violation_distance,
                'severity': v.severity.value,
                'age_seconds': (current_time - v.timestamp).total_seconds()
            }
            for v in self._active_violations.values()
            if (current_time - v.timestamp).total_seconds() < 60.0
        ]
        
        return {
            'is_safe': len([v for v in recent_violations if v['severity'] in ['CRITICAL', 'HIGH']]) == 0,
            'monitoring_active': self._monitoring_active,
            'boundary_loaded': self._boundary_loaded,
            'boundary_points_count': len(self._yard_boundary),
            'no_go_zones_count': len([z for z in self._no_go_zones.values() if z.active]),
            'active_violations': recent_violations,
            'current_position': self._last_valid_position,
            'safety_margin_m': self._safety_margin_m
        }
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get boundary monitoring performance metrics"""
        return {
            'boundary_checks': self._boundary_checks_count,
            'total_violations': self._violations_count,
            'false_violations': self._false_violations_count,
            'monitoring_active': self._monitoring_active,
            'boundary_loaded': self._boundary_loaded,
            'active_no_go_zones': len([z for z in self._no_go_zones.values() if z.active])
        }
    
    def register_emergency_callback(self, callback: Callable):
        """Register callback for emergency boundary violations"""
        self._emergency_callbacks.append(callback)
    
    # Additional helper methods...
    async def _cleanup_old_violations(self):
        """Clean up old violation records"""
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(seconds=30)  # 30 seconds timeout
        
        expired_violations = [
            vid for vid, violation in self._active_violations.items()
            if violation.timestamp < cutoff_time
        ]
        
        for vid in expired_violations:
            del self._active_violations[vid]
    
    async def _cleanup_expired_zones(self):
        """Clean up expired no-go zones"""
        current_time = datetime.now()
        
        for zone in self._no_go_zones.values():
            if zone.expires_at and current_time > zone.expires_at:
                zone.active = False
    
    async def _publish_violation_alert(self, violation: BoundaryViolation):
        """Publish boundary violation alert"""
        alert_data = {
            'violation_id': violation.violation_id,
            'violation_type': violation.violation_type,
            'position': violation.current_position,
            'distance': violation.violation_distance,
            'severity': violation.severity.value,
            'timestamp': violation.timestamp.isoformat(),
            'zone_info': violation.zone_info
        }
        
        message = SensorData.create(
            sender="boundary_monitor",
            sensor_type="boundary_violation",
            data=alert_data
        )
        
        await self.mqtt_client.publish("lawnberry/safety/boundary_violation", message)
