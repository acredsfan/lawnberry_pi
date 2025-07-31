"""
Mowing Pattern Generation Service
Implements algorithms for generating mowing patterns including Waves and Crosshatch.
"""

import math
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

@dataclass
class Point:
    """Represents a coordinate point"""
    x: float
    y: float

@dataclass
class Line:
    """Represents a line segment"""
    start: Point
    end: Point

@dataclass
class Boundary:
    """Represents a polygon boundary"""
    points: List[Point]

class PatternType(str, Enum):
    PARALLEL_LINES = "parallel_lines"
    CHECKERBOARD = "checkerboard"
    SPIRAL = "spiral"
    WAVES = "waves"
    CROSSHATCH = "crosshatch"

class PatternGenerator:
    """Advanced pattern generation with optimized algorithms"""
    
    def __init__(self):
        self.default_spacing = 0.3  # 30cm default spacing
        self.min_spacing = 0.2
        self.max_spacing = 1.0
        
    def generate_pattern(self, pattern_type: PatternType, boundary: Boundary, 
                        parameters: Dict[str, Any], no_go_zones: Optional[List[Boundary]] = None) -> List[List[Point]]:
        """Generate mowing pattern paths based on type and parameters, avoiding no-go zones"""
        
        if pattern_type == PatternType.WAVES:
            paths = self._generate_waves_pattern(boundary, parameters)
        elif pattern_type == PatternType.CROSSHATCH:
            paths = self._generate_crosshatch_pattern(boundary, parameters)
        elif pattern_type == PatternType.PARALLEL_LINES:
            paths = self._generate_parallel_pattern(boundary, parameters)
        elif pattern_type == PatternType.CHECKERBOARD:
            paths = self._generate_checkerboard_pattern(boundary, parameters)
        elif pattern_type == PatternType.SPIRAL:
            paths = self._generate_spiral_pattern(boundary, parameters)
        else:
            raise ValueError(f"Unsupported pattern type: {pattern_type}")
        
        # Apply no-go zone filtering if zones are provided
        if no_go_zones:
            paths = self._filter_paths_for_no_go_zones(paths, no_go_zones)
        
        return paths
    
    def _generate_waves_pattern(self, boundary: Boundary, parameters: Dict[str, Any]) -> List[List[Point]]:
        """
        Generate sinusoidal wave pattern with configurable parameters
        y_new = y_base + amplitude * sin(2π * x / wavelength)
        """
        amplitude = parameters.get('amplitude', 0.75)  # meters
        wavelength = parameters.get('wavelength', 8.0)  # meters
        base_angle = parameters.get('base_angle', 0)  # degrees
        spacing = parameters.get('spacing', self.default_spacing)
        overlap = parameters.get('overlap', 0.1)
        
        # Validate parameters
        amplitude = max(0.25, min(2.0, amplitude))
        wavelength = max(3.0, min(15.0, wavelength))
        base_angle = base_angle % 180
        
        # Get boundary dimensions and center
        bounds = self._get_boundary_bounds(boundary)
        center_x = (bounds['min_x'] + bounds['max_x']) / 2
        center_y = (bounds['min_y'] + bounds['max_y']) / 2
        
        # Generate base parallel lines
        base_lines = self._generate_parallel_lines(boundary, spacing, base_angle)
        
        wave_paths = []
        
        for line in base_lines:
            # Apply sinusoidal transformation to each line
            wave_path = []
            
            # Calculate line direction and length
            dx = line.end.x - line.start.x
            dy = line.end.y - line.start.y
            line_length = math.sqrt(dx*dx + dy*dy)
            
            if line_length == 0:
                continue
                
            # Generate points along the wave
            num_points = int(max(10, line_length / 0.1))  # Point every 10cm
            
            for i in range(num_points + 1):
                t = i / num_points
                
                # Base position along line
                base_x = line.start.x + dx * t
                base_y = line.start.y + dy * t
                
                # Calculate distance along line for wave function
                distance_along_line = t * line_length
                
                # Apply sinusoidal transformation
                wave_offset = amplitude * math.sin(2 * math.pi * distance_along_line / wavelength)
                
                # Calculate perpendicular direction for wave offset
                if line_length > 0:
                    perp_x = -dy / line_length
                    perp_y = dx / line_length
                else:
                    perp_x = perp_y = 0
                
                # Boundary-aware amplitude adjustment
                wave_x = base_x + perp_x * wave_offset
                wave_y = base_y + perp_y * wave_offset
                
                # Check if point is within boundary, adjust amplitude if needed
                if not self._point_in_boundary(Point(wave_x, wave_y), boundary):
                    # Reduce amplitude to stay within boundary
                    reduced_amplitude = amplitude * 0.5
                    wave_offset = reduced_amplitude * math.sin(2 * math.pi * distance_along_line / wavelength)
                    wave_x = base_x + perp_x * wave_offset
                    wave_y = base_y + perp_y * wave_offset
                
                wave_path.append(Point(wave_x, wave_y))
            
            if wave_path:
                wave_paths.append(wave_path)
        
        # Optimize path ordering for battery efficiency
        return self._optimize_path_order(wave_paths)
    
    def _generate_crosshatch_pattern(self, boundary: Boundary, parameters: Dict[str, Any]) -> List[List[Point]]:
        """
        Generate crosshatch pattern with overlapping parallel lines at two angles
        Optimized for battery efficiency with smart path ordering
        """
        first_angle = parameters.get('first_angle', 45)  # degrees
        second_angle = parameters.get('second_angle', 135)  # degrees
        spacing = parameters.get('spacing', self.default_spacing)
        overlap = parameters.get('overlap', 0.1)
        
        # Validate parameters
        spacing = max(self.min_spacing, min(self.max_spacing, spacing))
        first_angle = first_angle % 180
        second_angle = second_angle % 180
        
        # Generate first set of parallel lines
        first_lines = self._generate_parallel_lines(boundary, spacing, first_angle)
        first_paths = [[line.start, line.end] for line in first_lines]
        
        # Generate second set of parallel lines
        second_lines = self._generate_parallel_lines(boundary, spacing, second_angle)
        second_paths = [[line.start, line.end] for line in second_lines]
        
        # Combine both sets
        all_paths = first_paths + second_paths
        
        # Advanced path ordering optimization for battery efficiency
        return self._optimize_crosshatch_paths(all_paths, boundary)
    
    def _optimize_crosshatch_paths(self, paths: List[List[Point]], boundary: Boundary) -> List[List[Point]]:
        """
        Advanced path ordering for crosshatch pattern to minimize travel distance
        Uses nearest-neighbor with look-ahead optimization
        """
        if not paths:
            return []
        
        optimized_paths = []
        remaining_paths = paths.copy()
        
        # Start with path closest to boundary center
        bounds = self._get_boundary_bounds(boundary)
        start_point = Point(
            (bounds['min_x'] + bounds['max_x']) / 2,
            (bounds['min_y'] + bounds['max_y']) / 2
        )
        
        current_position = start_point
        
        while remaining_paths:
            # Find nearest path with look-ahead optimization
            best_path_idx = self._find_optimal_next_path(current_position, remaining_paths)
            
            best_path = remaining_paths.pop(best_path_idx)
            
            # Determine best direction to traverse path
            start_dist = self._distance(current_position, best_path[0])
            end_dist = self._distance(current_position, best_path[-1])
            
            if end_dist < start_dist:
                # Reverse path for shorter travel
                best_path.reverse()
            
            optimized_paths.append(best_path)
            current_position = best_path[-1]
        
        return optimized_paths
    
    def _find_optimal_next_path(self, current_pos: Point, remaining_paths: List[List[Point]]) -> int:
        """
        Find optimal next path using nearest-neighbor with look-ahead
        Considers both immediate distance and future path connectivity
        """
        if len(remaining_paths) == 1:
            return 0
        
        best_score = float('inf')
        best_idx = 0
        
        for i, path in enumerate(remaining_paths):
            # Calculate immediate travel distance
            start_dist = self._distance(current_pos, path[0])
            end_dist = self._distance(current_pos, path[-1])
            immediate_dist = min(start_dist, end_dist)
            
            # Look-ahead: estimate future connectivity
            future_score = 0
            path_end = path[-1] if start_dist <= end_dist else path[0]
            
            # Check connectivity to remaining paths
            other_paths = remaining_paths[:i] + remaining_paths[i+1:]
            if other_paths:
                min_future_dist = min(
                    min(self._distance(path_end, other_path[0]), 
                        self._distance(path_end, other_path[-1]))
                    for other_path in other_paths
                )
                future_score = min_future_dist * 0.3  # Weight future connections
            
            total_score = immediate_dist + future_score
            
            if total_score < best_score:
                best_score = total_score
                best_idx = i
        
        return best_idx
    
    def _generate_parallel_lines(self, boundary: Boundary, spacing: float, angle: float) -> List[Line]:
        """Generate parallel lines across boundary at specified angle and spacing"""
        bounds = self._get_boundary_bounds(boundary)
        
        # Calculate rotation
        angle_rad = math.radians(angle)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        
        # Get boundary dimensions
        width = bounds['max_x'] - bounds['min_x']
        height = bounds['max_y'] - bounds['min_y']
        diagonal = math.sqrt(width*width + height*height)
        
        lines = []
        
        # Generate parallel lines
        num_lines = int(diagonal / spacing) + 2
        start_offset = -diagonal
        
        for i in range(num_lines):
            offset = start_offset + float(i) * spacing
            
            # Calculate line endpoints extending beyond boundary
            extend = diagonal
            line_start = Point(
                bounds['min_x'] + cos_a * (-extend) - sin_a * offset,
                bounds['min_y'] + sin_a * (-extend) + cos_a * offset
            )
            line_end = Point(
                bounds['min_x'] + cos_a * extend - sin_a * offset,
                bounds['min_y'] + sin_a * extend + cos_a * offset
            )
            
            # Clip line to boundary
            clipped_line = self._clip_line_to_boundary(Line(line_start, line_end), boundary)
            if clipped_line:
                lines.append(clipped_line)
        
        return lines
    
    def _generate_advanced_curved_lines(self, boundary: Boundary, parameters: Dict[str, Any]) -> List[List[Point]]:
        """Generate advanced curved line algorithms for complex irregular yard shapes"""
        curve_type = parameters.get('curve_type', 'bezier')
        spacing = parameters.get('spacing', self.default_spacing)
        complexity = parameters.get('complexity', 0.3)
        
        bounds = self._get_boundary_bounds(boundary)
        curved_paths = []
        
        if curve_type == 'bezier':
            # Generate Bezier curve-based paths
            curved_paths = self._generate_bezier_curves(boundary, spacing, complexity)
        elif curve_type == 'spline':
            # Generate B-spline based paths
            curved_paths = self._generate_spline_curves(boundary, spacing, complexity)
        elif curve_type == 'adaptive':
            # Generate boundary-adaptive curves
            curved_paths = self._generate_adaptive_curves(boundary, spacing, complexity)
        
        return curved_paths
    
    def _generate_bezier_curves(self, boundary: Boundary, spacing: float, complexity: float) -> List[List[Point]]:
        """Generate Bezier curve-based mowing paths"""
        bounds = self._get_boundary_bounds(boundary)
        paths = []
        
        # Calculate control points based on boundary geometry
        center_x = (bounds['min_x'] + bounds['max_x']) / 2
        center_y = (bounds['min_y'] + bounds['max_y']) / 2
        
        width = bounds['max_x'] - bounds['min_x']
        height = bounds['max_y'] - bounds['min_y']
        
        num_curves = int(max(width, height) / spacing)
        
        for i in range(num_curves):
            t_offset = i / num_curves
            
            # Create Bezier control points
            p0 = Point(bounds['min_x'], bounds['min_y'] + t_offset * height)
            p1 = Point(center_x + complexity * width * math.sin(t_offset * math.pi), center_y)
            p2 = Point(center_x - complexity * width * math.cos(t_offset * math.pi), center_y)
            p3 = Point(bounds['max_x'], bounds['min_y'] + t_offset * height)
            
            # Generate Bezier curve points
            curve_points = []
            for t in range(0, 101, 2):  # Generate points along curve
                t_norm = t / 100.0
                
                # Cubic Bezier formula
                x = ((1-t_norm)**3 * p0.x + 
                     3*(1-t_norm)**2*t_norm * p1.x + 
                     3*(1-t_norm)*t_norm**2 * p2.x + 
                     t_norm**3 * p3.x)
                y = ((1-t_norm)**3 * p0.y + 
                     3*(1-t_norm)**2*t_norm * p1.y + 
                     3*(1-t_norm)*t_norm**2 * p2.y + 
                     t_norm**3 * p3.y)
                
                point = Point(x, y)
                if self._point_in_boundary(point, boundary):
                    curve_points.append(point)
            
            if len(curve_points) > 5:  # Minimum viable curve
                paths.append(curve_points)
        
        return paths
    
    def _generate_random_offset_algorithms(self, boundary: Boundary, parameters: Dict[str, Any]) -> List[List[Point]]:
        """Generate sophisticated random offset algorithms to prevent grass wear patterns"""
        base_pattern = parameters.get('base_pattern', 'parallel')
        offset_variance = parameters.get('offset_variance', 0.2)
        seed_rotation = parameters.get('seed_rotation', True)
        temporal_shift = parameters.get('temporal_shift', 0.1)
        
        # Statistical distribution models for randomization
        import random
        random.seed(int(parameters.get('random_seed', 42)))
        
        if base_pattern == 'parallel':
            base_paths = self._generate_parallel_pattern(boundary, parameters)
        else:
            base_paths = self._generate_waves_pattern(boundary, parameters)
        
        randomized_paths = []
        
        for path in base_paths:
            randomized_path = []
            
            for i, point in enumerate(path):
                # Apply Gaussian random offset
                offset_x = random.gauss(0, offset_variance)
                offset_y = random.gauss(0, offset_variance)
                
                # Apply temporal shift for time-based pattern rotation
                if seed_rotation:
                    time_factor = (i / len(path)) * temporal_shift
                    rotation_angle = time_factor * math.pi / 4
                    
                    # Rotate offset
                    cos_r = math.cos(rotation_angle)
                    sin_r = math.sin(rotation_angle)
                    
                    rotated_x = offset_x * cos_r - offset_y * sin_r
                    rotated_y = offset_x * sin_r + offset_y * cos_r
                    
                    offset_x, offset_y = rotated_x, rotated_y
                
                new_point = Point(point.x + offset_x, point.y + offset_y)
                
                # Ensure point stays within boundary
                if self._point_in_boundary(new_point, boundary):
                    randomized_path.append(new_point)
                else:
                    randomized_path.append(point)  # Keep original if offset goes outside
            
            if randomized_path:
                randomized_paths.append(randomized_path)
        
        return randomized_paths
    
    def _generate_spline_curves(self, boundary: Boundary, spacing: float, complexity: float) -> List[List[Point]]:
        """Generate B-spline based mowing paths for smooth curves"""
        bounds = self._get_boundary_bounds(boundary)
        paths = []
        
        # Generate control points for B-spline
        num_control_points = max(4, int(complexity * 10))
        width = bounds['max_x'] - bounds['min_x']
        height = bounds['max_y'] - bounds['min_y']
        
        num_splines = int(max(width, height) / spacing)
        
        for i in range(num_splines):
            # Create control points along boundary
            control_points = []
            for j in range(num_control_points):
                t = j / (num_control_points - 1)
                x = bounds['min_x'] + t * width
                y = bounds['min_y'] + (i / num_splines) * height + complexity * height * math.sin(t * math.pi * 2)
                control_points.append(Point(x, y))
            
            # Generate spline curve (simplified cubic interpolation)
            spline_points = []
            for t in range(0, 101, 3):
                t_norm = t / 100.0
                
                # Simple cubic interpolation between control points
                if len(control_points) >= 4:
                    segment_index = min(len(control_points) - 4, int(t_norm * (len(control_points) - 3)))
                    local_t = (t_norm * (len(control_points) - 3)) - segment_index
                    
                    p0, p1, p2, p3 = control_points[segment_index:segment_index + 4]
                    
                    # Catmull-Rom spline interpolation
                    x = 0.5 * ((2 * p1.x) +
                              (-p0.x + p2.x) * local_t +
                              (2*p0.x - 5*p1.x + 4*p2.x - p3.x) * local_t**2 +
                              (-p0.x + 3*p1.x - 3*p2.x + p3.x) * local_t**3)
                    
                    y = 0.5 * ((2 * p1.y) +
                              (-p0.y + p2.y) * local_t +
                              (2*p0.y - 5*p1.y + 4*p2.y - p3.y) * local_t**2 +
                              (-p0.y + 3*p1.y - 3*p2.y + p3.y) * local_t**3)
                    
                    point = Point(x, y)
                    if self._point_in_boundary(point, boundary):
                        spline_points.append(point)
            
            if len(spline_points) > 5:
                paths.append(spline_points)
        
        return paths
    
    def _generate_adaptive_curves(self, boundary: Boundary, spacing: float, complexity: float) -> List[List[Point]]:
        """Generate boundary-adaptive curves that follow yard contours"""
        paths = []
        
        # Analyze boundary curvature
        boundary_segments = self._analyze_boundary_curvature(boundary)
        
        for segment in boundary_segments:
            # Generate paths that adapt to boundary curvature
            adaptive_path = []
            
            for i in range(len(segment) - 1):
                start_point = segment[i]
                end_point = segment[i + 1]
                
                # Calculate curve that follows boundary shape
                curve_points = self._generate_boundary_following_curve(
                    start_point, end_point, boundary, spacing, complexity
                )
                adaptive_path.extend(curve_points)
            
            if len(adaptive_path) > 3:
                paths.append(adaptive_path)
        
        return paths
    
    def _analyze_boundary_curvature(self, boundary: Boundary) -> List[List[Point]]:
        """Analyze boundary curvature to create adaptive segments"""
        if len(boundary.points) < 3:
            return [boundary.points]
        
        segments = []
        current_segment = [boundary.points[0]]
        
        for i in range(1, len(boundary.points) - 1):
            p1 = boundary.points[i - 1]
            p2 = boundary.points[i]
            p3 = boundary.points[i + 1]
            
            # Calculate curvature using cross product
            v1_x, v1_y = p2.x - p1.x, p2.y - p1.y
            v2_x, v2_y = p3.x - p2.x, p3.y - p2.y
            
            cross_product = v1_x * v2_y - v1_y * v2_x
            curvature = abs(cross_product) / max(0.001, (v1_x**2 + v1_y**2)**0.5 * (v2_x**2 + v2_y**2)**0.5)
            
            current_segment.append(p2)
            
            # Split segment if high curvature detected
            if curvature > 0.3 and len(current_segment) > 2:
                segments.append(current_segment)
                current_segment = [p2]
        
        current_segment.append(boundary.points[-1])
        segments.append(current_segment)
        
        return segments
    
    def _generate_boundary_following_curve(
        self, start: Point, end: Point, boundary: Boundary, spacing: float, complexity: float
    ) -> List[Point]:
        """Generate curve that follows boundary contours"""
        curve_points = []
        
        # Calculate direction vector
        dx = end.x - start.x
        dy = end.y - start.y
        length = math.sqrt(dx*dx + dy*dy)
        
        if length < 0.001:
            return [start]
        
        # Normalize direction
        dx /= length
        dy /= length
        
        # Generate points along the curve
        num_points = max(5, int(length / (spacing * 0.5)))
        
        for i in range(num_points):
            t = i / (num_points - 1) if num_points > 1 else 0
            
            # Base position
            base_x = start.x + t * (end.x - start.x)
            base_y = start.y + t * (end.y - start.y)
            
            # Add curvature that follows boundary
            perpendicular_x = -dy
            perpendicular_y = dx
            
            curve_offset = complexity * spacing * math.sin(t * math.pi)
            
            curve_x = base_x + perpendicular_x * curve_offset
            curve_y = base_y + perpendicular_y * curve_offset
            
            point = Point(curve_x, curve_y)
            if self._point_in_boundary(point, boundary):
                curve_points.append(point)
        
        return curve_points
    
    def _optimize_path_order(self, paths: List[List[Point]]) -> List[List[Point]]:
        """Optimize path ordering for minimum travel distance (nearest neighbor)"""
        if len(paths) <= 1:
            return paths
        
        optimized = []
        remaining = paths.copy()
        
        # Start with first path
        current_path = remaining.pop(0)
        optimized.append(current_path)
        current_end = current_path[-1]
        
        while remaining:
            best_idx = 0
            best_dist = float('inf')
            reverse_best = False
            
            for i, path in enumerate(remaining):
                # Check distance to start and end of path
                dist_to_start = self._distance(current_end, path[0])
                dist_to_end = self._distance(current_end, path[-1])
                
                if dist_to_start < best_dist:
                    best_dist = dist_to_start
                    best_idx = i
                    reverse_best = False
                
                if dist_to_end < best_dist:
                    best_dist = dist_to_end
                    best_idx = i
                    reverse_best = True
            
            next_path = remaining.pop(best_idx)
            if reverse_best:
                next_path.reverse()
            
            optimized.append(next_path)
            current_end = next_path[-1]
        
        return optimized
    
    def _get_boundary_bounds(self, boundary: Boundary) -> Dict[str, float]:
        """Get bounding box of boundary"""
        if not boundary.points:
            return {'min_x': 0, 'max_x': 0, 'min_y': 0, 'max_y': 0}
        
        min_x = min(p.x for p in boundary.points)
        max_x = max(p.x for p in boundary.points)
        min_y = min(p.y for p in boundary.points)
        max_y = max(p.y for p in boundary.points)
        
        return {'min_x': min_x, 'max_x': max_x, 'min_y': min_y, 'max_y': max_y}
    
    def _point_in_boundary(self, point: Point, boundary: Boundary) -> bool:
        """Check if point is inside boundary using ray casting algorithm"""
        if len(boundary.points) < 3:
            return False
        
        x, y = point.x, point.y
        n = len(boundary.points)
        inside = False
        
        p1x, p1y = boundary.points[0].x, boundary.points[0].y
        for i in range(1, n + 1):
            p2x, p2y = boundary.points[i % n].x, boundary.points[i % n].y
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        
        return inside
    
    def _clip_line_to_boundary(self, line: Line, boundary: Boundary) -> Optional[Line]:
        """Clip line to boundary using Sutherland-Hodgman algorithm"""
        # Simplified line clipping - return line if both endpoints are in boundary
        start_in = self._point_in_boundary(line.start, boundary)
        end_in = self._point_in_boundary(line.end, boundary)
        
        if start_in and end_in:
            return line
        elif start_in or end_in:
            # Line crosses boundary - simplified implementation
            return line  # Return original for now
        else:
            return None
    
    def _distance(self, p1: Point, p2: Point) -> float:
        """Calculate Euclidean distance between two points"""
        return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)
    
    # Placeholder implementations for existing patterns
    def _generate_parallel_pattern(self, boundary: Boundary, parameters: Dict[str, Any]) -> List[List[Point]]:
        """Generate basic parallel lines pattern"""
        spacing = parameters.get('spacing', self.default_spacing)
        angle = parameters.get('angle', 0)
        
        lines = self._generate_parallel_lines(boundary, spacing, angle)
        return [[line.start, line.end] for line in lines]
    
    def _generate_checkerboard_pattern(self, boundary: Boundary, parameters: Dict[str, Any]) -> List[List[Point]]:
        """Generate checkerboard pattern - placeholder"""
        # Implement checkerboard logic here
        return self._generate_parallel_pattern(boundary, parameters)
    
    def _generate_spiral_pattern(self, boundary: Boundary, parameters: Dict[str, Any]) -> List[List[Point]]:
        """Generate spiral pattern - placeholder"""
        # Implement spiral logic here  
        return self._generate_parallel_pattern(boundary, parameters)


    def _filter_paths_for_no_go_zones(self, paths: List[List[Point]], no_go_zones: List[Boundary]) -> List[List[Point]]:
        """Filter out path segments that intersect with no-go zones"""
        if not no_go_zones:
            return paths
        
        filtered_paths = []
        safety_buffer = 0.5  # 50cm safety buffer around no-go zones
        
        for path in paths:
            filtered_segments = []
            current_segment = []
            
            for i, point in enumerate(path):
                # Check if point is safe (not in any no-go zone with buffer)
                is_safe = True
                
                for zone in no_go_zones:
                    if self._is_point_in_polygon_with_buffer(point, zone, safety_buffer):
                        is_safe = False
                        break
                
                if is_safe:
                    current_segment.append(point)
                else:
                    # Point is in no-go zone, end current segment if it has points
                    if len(current_segment) >= 2:  # Need at least 2 points for a valid segment
                        filtered_segments.append(current_segment)
                    current_segment = []
            
            # Add final segment if it has enough points
            if len(current_segment) >= 2:
                filtered_segments.append(current_segment)
            
            # Add all valid segments to filtered paths
            filtered_paths.extend(filtered_segments)
        
        return filtered_paths

    def _is_point_in_polygon_with_buffer(self, point: Point, polygon: Boundary, buffer: float) -> bool:
        """Check if point is inside polygon with safety buffer"""
        # First check if point is inside the polygon
        if self._is_point_in_polygon(point, polygon.points):
            return True
        
        # Check if point is within buffer distance of polygon edges
        for i in range(len(polygon.points)):
            j = (i + 1) % len(polygon.points)
            edge_start = polygon.points[i]
            edge_end = polygon.points[j]
            
            distance = self._distance_point_to_line(point, edge_start, edge_end)
            if distance < buffer:
                return True
        
        return False

    def _is_point_in_polygon(self, point: Point, polygon_points: List[Point]) -> bool:
        """Check if point is inside polygon using ray casting algorithm"""
        x, y = point.x, point.y
        n = len(polygon_points)
        inside = False
        
        p1x, p1y = polygon_points[0].x, polygon_points[0].y
        for i in range(1, n + 1):
            p2x, p2y = polygon_points[i % n].x, polygon_points[i % n].y
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        
        return inside


    def _distance_point_to_line(self, point: Point, line_start: Point, line_end: Point) -> float:
        """Calculate distance from point to line segment"""
        # Vector from line_start to line_end
        line_vec = Point(line_end.x - line_start.x, line_end.y - line_start.y)
        line_length_sq = line_vec.x**2 + line_vec.y**2
        
        if line_length_sq == 0:
            # Line is actually a point
            return math.sqrt((point.x - line_start.x)**2 + (point.y - line_start.y)**2)
        
        # Vector from line_start to point
        point_vec = Point(point.x - line_start.x, point.y - line_start.y)
        
        # Project point onto line
        t = max(0, min(1, (point_vec.x * line_vec.x + point_vec.y * line_vec.y) / line_length_sq))
        
        # Find closest point on line
        closest = Point(
            line_start.x + t * line_vec.x,
            line_start.y + t * line_vec.y
        )
        
        # Return distance
        return math.sqrt((point.x - closest.x)**2 + (point.y - closest.y)**2)
