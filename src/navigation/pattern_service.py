"""
Pattern Service
Service layer for mowing pattern generation and management.
Integrates with existing API and provides pattern generation capabilities.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from .pattern_generator import PatternGenerator, PatternType, Point, Boundary
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from web_api.models import MowingPattern, PatternConfig

class PatternService:
    """Service for managing mowing patterns and configurations"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.generator = PatternGenerator()
        self._pattern_configs: Dict[str, Dict[str, Any]] = {}
        self._initialize_default_configs()

    async def initialize_ai_optimizer(self):
        """Initialize AI pattern optimizer"""
        try:
            from .ai_pattern_optimizer import ai_pattern_optimizer
            await ai_pattern_optimizer.initialize()
            self.logger.info("AI pattern optimizer initialized")
        except Exception as e:
            self.logger.warning(f"Could not initialize AI optimizer: {e}")
    
    async def generate_ai_optimized_pattern(
        self, 
        pattern: MowingPattern, 
        boundary_coords: List[Dict[str, float]], 
        yard_characteristics: Dict[str, Any],
        environmental_conditions: Dict[str, Any],
        optimization_strategy: str = "balanced",
        base_parameters: Optional[Dict[str, Any]] = None
    ) -> List[List[Dict[str, float]]]:
        """
        Generate AI-optimized mowing pattern with advanced algorithmic enhancements
        """
        try:
            from .ai_pattern_optimizer import ai_pattern_optimizer, YardCharacteristics, OptimizationStrategy
            
            # Convert boundary coordinates to internal format
            boundary_points = [Point(coord['lat'], coord['lng']) for coord in boundary_coords]
            boundary = Boundary(boundary_points)
            
            # Convert yard characteristics
            yard_char = YardCharacteristics(
                area=yard_characteristics.get('area', 100.0),
                shape_complexity=yard_characteristics.get('shape_complexity', 0.5),
                obstacle_density=yard_characteristics.get('obstacle_density', 0.1),
                slope_variance=yard_characteristics.get('slope_variance', 0.1),
                edge_ratio=yard_characteristics.get('edge_ratio', 0.2),
                irregular_sections=yard_characteristics.get('irregular_sections', 0),
                grass_type_distribution=yard_characteristics.get('grass_type_distribution', {'default': 1.0})
            )
            
            # Get base parameters if not provided
            if base_parameters is None:
                config = self._pattern_configs.get(pattern.value, {})
                base_parameters = config.get('parameters', {})
            
            # Convert pattern enum to internal type
            pattern_type = PatternType(pattern.value)
            
            # Get optimization strategy
            try:
                strategy = OptimizationStrategy(optimization_strategy)
            except ValueError:
                strategy = OptimizationStrategy.BALANCED
            
            # Get AI-optimized parameters
            optimized_params = await ai_pattern_optimizer.optimize_pattern_for_yard(
                pattern_type, boundary, yard_char, environmental_conditions, strategy, base_parameters
            )
            
            # Generate pattern with optimized parameters
            paths = self.generator.generate_pattern(pattern_type, boundary, optimized_params)
            
            # Convert back to coordinate format
            result_paths = []
            for path in paths:
                coord_path = [{'lat': point.x, 'lng': point.y} for point in path]
                result_paths.append(coord_path)
            
            self.logger.info(f"Generated AI-optimized {pattern.value} pattern with {len(result_paths)} paths")
            return result_paths
            
        except Exception as e:
            self.logger.error(f"AI pattern optimization failed: {e}")
            # Fallback to standard pattern generation
            return await self.generate_pattern_path(pattern, boundary_coords, base_parameters)
    
    async def learn_from_pattern_performance(
        self, 
        pattern: MowingPattern,
        boundary_coords: List[Dict[str, float]],
        yard_characteristics: Dict[str, Any],
        environmental_conditions: Dict[str, Any],
        performance_metrics: Dict[str, float]
    ):
        """Learn from pattern performance for continuous improvement"""
        try:
            from .ai_pattern_optimizer import ai_pattern_optimizer, PatternPerformanceMetric
            from datetime import datetime
            
            # Create performance metric
            performance_data = PatternPerformanceMetric(
                pattern_type=pattern.value,
                coverage_efficiency=performance_metrics.get('coverage_efficiency', 0.8),
                battery_usage=performance_metrics.get('battery_usage', 0.5),
                time_to_complete=performance_metrics.get('time_to_complete', 3600),
                grass_quality_score=performance_metrics.get('grass_quality_score', 0.8),
                terrain_adaptation_score=performance_metrics.get('terrain_adaptation_score', 0.7),
                weather_resilience=performance_metrics.get('weather_resilience', 0.8),
                user_satisfaction=performance_metrics.get('user_satisfaction', 0.8),
                edge_case_handling=performance_metrics.get('edge_case_handling', 0.7),
                timestamp=datetime.now(),
                yard_characteristics=yard_characteristics,
                environmental_conditions=environmental_conditions
            )
            
            # Feed to AI optimizer for learning
            await ai_pattern_optimizer.learn_from_performance(performance_data)
            
            self.logger.info(f"Logged performance data for {pattern.value} pattern")
            
        except Exception as e:
            self.logger.error(f"Failed to log pattern performance: {e}")

    
    def _initialize_default_configs(self):
        """Initialize default pattern configurations with proper parameters"""
        
        self._pattern_configs = {
            MowingPattern.PARALLEL_LINES.value: {
                'parameters': {
                    'spacing': 0.3,
                    'angle': 0,
                    'overlap': 0.1
                },
                'coverage_overlap': 0.1,
                'edge_cutting': True,
                'description': 'Straight parallel lines pattern for efficient coverage'
            },
            MowingPattern.CHECKERBOARD.value: {
                'parameters': {
                    'spacing': 0.5,
                    'overlap': 0.05,
                    'block_size': 2.0
                },
                'coverage_overlap': 0.05,
                'edge_cutting': True,
                'description': 'Alternating squares pattern for thorough coverage'
            },
            MowingPattern.SPIRAL.value: {
                'parameters': {
                    'spacing': 0.3,
                    'direction': 'inward',
                    'start_edge': 'outer'
                },
                'coverage_overlap': 0.1,
                'edge_cutting': True,
                'description': 'Spiral pattern ideal for irregular shaped areas'
            },
            MowingPattern.WAVES.value: {
                'parameters': {
                    'amplitude': 0.75,      # meters (0.25-2.0)
                    'wavelength': 8.0,      # meters (3-15)
                    'base_angle': 0,        # degrees (0-180)
                    'spacing': 0.4,         # meters between wave centers
                    'overlap': 0.1
                },
                'coverage_overlap': 0.1,
                'edge_cutting': True,
                'description': 'Sinusoidal wave pattern for natural appearance and excellent coverage'
            },
            MowingPattern.CROSSHATCH.value: {
                'parameters': {
                    'first_angle': 45,      # degrees (0-180)
                    'second_angle': 135,    # degrees (0-180)
                    'spacing': 0.3,         # meters (0.2-1.0)
                    'overlap': 0.1
                },
                'coverage_overlap': 0.1,
                'edge_cutting': True,
                'description': 'Overlapping perpendicular lines for maximum coverage and cut quality'
            }
        }
    
    async def get_available_patterns(self) -> List[PatternConfig]:
        """Get list of all available patterns with their default configurations"""
        patterns = []
        
        for pattern_enum in MowingPattern:
            config_data = self._pattern_configs.get(pattern_enum.value, {})
            
            pattern_config = PatternConfig(
                pattern=pattern_enum,
                parameters=config_data.get('parameters', {}),
                coverage_overlap=config_data.get('coverage_overlap', 0.1),
                edge_cutting=config_data.get('edge_cutting', True)
            )
            patterns.append(pattern_config)
        
        return patterns
    
    async def get_pattern_config(self, pattern_name: MowingPattern) -> PatternConfig:
        """Get configuration for a specific pattern"""
        config_data = self._pattern_configs.get(pattern_name.value, {})
        
        return PatternConfig(
            pattern=pattern_name,
            parameters=config_data.get('parameters', {}),
            coverage_overlap=config_data.get('coverage_overlap', 0.1),
            edge_cutting=config_data.get('edge_cutting', True)
        )
    
    async def update_pattern_config(self, pattern_name: MowingPattern, config: PatternConfig) -> bool:
        """Update pattern configuration with validation"""
        try:
            # Validate pattern-specific parameters
            validated_params = self._validate_pattern_parameters(pattern_name, config.parameters)
            
            # Update stored configuration
            if pattern_name.value not in self._pattern_configs:
                self._pattern_configs[pattern_name.value] = {}
            
            self._pattern_configs[pattern_name.value].update({
                'parameters': validated_params,
                'coverage_overlap': config.coverage_overlap,
                'edge_cutting': config.edge_cutting,
                'last_updated': datetime.utcnow().isoformat()
            })
            
            self.logger.info(f"Updated configuration for pattern: {pattern_name.value}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to update pattern config for {pattern_name.value}: {e}")
            return False
    
    def _validate_pattern_parameters(self, pattern: MowingPattern, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize pattern parameters"""
        validated = parameters.copy()
        
        if pattern == MowingPattern.WAVES:
            # Validate waves parameters
            validated['amplitude'] = max(0.25, min(2.0, parameters.get('amplitude', 0.75)))
            validated['wavelength'] = max(3.0, min(15.0, parameters.get('wavelength', 8.0)))
            validated['base_angle'] = parameters.get('base_angle', 0) % 180
            validated['spacing'] = max(0.2, min(1.0, parameters.get('spacing', 0.4)))
            validated['overlap'] = max(0.0, min(0.5, parameters.get('overlap', 0.1)))
            
        elif pattern == MowingPattern.CROSSHATCH:
            # Validate crosshatch parameters
            validated['first_angle'] = parameters.get('first_angle', 45) % 180
            validated['second_angle'] = parameters.get('second_angle', 135) % 180
            validated['spacing'] = max(0.2, min(1.0, parameters.get('spacing', 0.3)))
            validated['overlap'] = max(0.0, min(0.5, parameters.get('overlap', 0.1)))
            
            # Ensure angles are different enough for effective crosshatch
            angle_diff = abs(validated['first_angle'] - validated['second_angle'])
            if angle_diff < 30 or angle_diff > 150:
                self.logger.warning(f"Crosshatch angles may not be optimal: {validated['first_angle']}° and {validated['second_angle']}°")
        
        elif pattern == MowingPattern.PARALLEL_LINES:
            validated['spacing'] = max(0.2, min(1.0, parameters.get('spacing', 0.3)))
            validated['angle'] = parameters.get('angle', 0) % 180
            validated['overlap'] = max(0.0, min(0.5, parameters.get('overlap', 0.1)))
            
        elif pattern == MowingPattern.CHECKERBOARD:
            validated['spacing'] = max(0.2, min(1.0, parameters.get('spacing', 0.5)))
            validated['overlap'] = max(0.0, min(0.5, parameters.get('overlap', 0.05)))
            validated['block_size'] = max(1.0, min(5.0, parameters.get('block_size', 2.0)))
            
        elif pattern == MowingPattern.SPIRAL:
            validated['spacing'] = max(0.2, min(1.0, parameters.get('spacing', 0.3)))
            validated['direction'] = parameters.get('direction', 'inward')
            validated['start_edge'] = parameters.get('start_edge', 'outer')
        
        return validated
    
    async def generate_pattern_path(self, pattern: MowingPattern, boundary_coords: List[Dict[str, float]], 
                                  parameters: Optional[Dict[str, Any]] = None) -> List[List[Dict[str, float]]]:
        """
        Generate mowing path for specified pattern and boundary
        Returns list of paths, where each path is a list of coordinate points
        """
        try:
            # Convert boundary coordinates to internal format
            boundary_points = [Point(coord['lat'], coord['lng']) for coord in boundary_coords]
            boundary = Boundary(boundary_points)
            
            # Get pattern configuration
            config = await self.get_pattern_config(pattern)
            
            # Use provided parameters or default ones
            pattern_params = parameters or config.parameters
            
            # Validate parameters
            validated_params = self._validate_pattern_parameters(pattern, pattern_params)
            
            # Convert pattern enum to internal type
            if pattern == MowingPattern.WAVES:
                pattern_type = PatternType.WAVES
            elif pattern == MowingPattern.CROSSHATCH:
                pattern_type = PatternType.CROSSHATCH
            elif pattern == MowingPattern.PARALLEL_LINES:
                pattern_type = PatternType.PARALLEL_LINES
            elif pattern == MowingPattern.CHECKERBOARD:
                pattern_type = PatternType.CHECKERBOARD
            elif pattern == MowingPattern.SPIRAL:
                pattern_type = PatternType.SPIRAL
            else:
                raise ValueError(f"Unsupported pattern: {pattern}")
            
            # Generate pattern paths
            paths = self.generator.generate_pattern(pattern_type, boundary, validated_params)
            
            # Convert back to coordinate format
            result_paths = []
            for path in paths:
                coord_path = [{'lat': point.x, 'lng': point.y} for point in path]
                result_paths.append(coord_path)
            
            self.logger.info(f"Generated {len(result_paths)} paths for {pattern.value} pattern")
            return result_paths
            
        except Exception as e:
            self.logger.error(f"Failed to generate pattern {pattern.value}: {e}")
            raise
    
    async def estimate_pattern_efficiency(self, pattern: MowingPattern, boundary_coords: List[Dict[str, float]], 
                                        parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Estimate pattern efficiency metrics for battery usage optimization
        """
        try:
            paths = await self.generate_pattern_path(pattern, boundary_coords, parameters)
            
            if not paths:
                return {'total_distance': 0, 'coverage_area': 0, 'efficiency_score': 0}
            
            # Calculate total mowing distance
            total_distance = 0
            for path in paths:
                for i in range(len(path) - 1):
                    p1, p2 = path[i], path[i + 1]
                    # Simple distance calculation (should use proper geodetic distance)
                    dist = ((p2['lat'] - p1['lat'])**2 + (p2['lng'] - p1['lng'])**2)**0.5
                    total_distance += dist
            
            # Calculate travel distance between paths
            travel_distance = 0
            for i in range(len(paths) - 1):
                last_point = paths[i][-1]
                next_point = paths[i + 1][0]
                dist = ((next_point['lat'] - last_point['lat'])**2 + (next_point['lng'] - last_point['lng'])**2)**0.5
                travel_distance += dist
            
            # Estimate coverage area (simplified)
            config = await self.get_pattern_config(pattern)
            spacing = config.parameters.get('spacing', 0.3)
            coverage_area = total_distance * spacing  # Rough estimate
            
            # Calculate efficiency score (higher is better)
            if total_distance + travel_distance > 0:
                efficiency_score = total_distance / (total_distance + travel_distance)
            else:
                efficiency_score = 0
            
            return {
                'total_distance': round(total_distance, 2),
                'travel_distance': round(travel_distance, 2),
                'coverage_area': round(coverage_area, 2),
                'efficiency_score': round(efficiency_score, 3),
                'estimated_time_minutes': round((total_distance + travel_distance) / 0.02, 1),  # Assuming 2cm/s avg speed
                'pattern_paths': len(paths)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to estimate pattern efficiency: {e}")
            return {'error': str(e)}
    
    async def validate_pattern_feasibility(self, pattern: MowingPattern, boundary_coords: List[Dict[str, float]], 
                                         parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Validate if pattern is feasible for given boundary and parameters
        """
        try:
            # Basic boundary validation
            if len(boundary_coords) < 3:
                return {
                    'feasible': False,
                    'issues': ['Boundary must have at least 3 points'],
                    'recommendations': ['Define a proper polygon boundary']
                }
            
            # Pattern-specific validation
            issues = []
            recommendations = []
            
            config = await self.get_pattern_config(pattern)
            params = parameters or config.parameters
            
            if pattern == MowingPattern.WAVES:
                amplitude = params.get('amplitude', 0.75)
                wavelength = params.get('wavelength', 8.0)
                
                # Check if wave amplitude is reasonable for boundary size
                # This is a simplified check - could be more sophisticated
                if amplitude > 1.5:
                    issues.append('Wave amplitude may be too large for typical residential boundaries')
                    recommendations.append('Consider reducing amplitude to 0.5-1.0m')
                
                if wavelength < 5.0:
                    issues.append('Short wavelength may create too many direction changes')
                    recommendations.append('Consider increasing wavelength to 6-10m for smoother operation')
            
            elif pattern == MowingPattern.CROSSHATCH:
                first_angle = params.get('first_angle', 45)
                second_angle = params.get('second_angle', 135)
                spacing = params.get('spacing', 0.3)
                
                angle_diff = abs(first_angle - second_angle)
                if angle_diff < 30:
                    issues.append('Crosshatch angles too similar - may not provide effective coverage')
                    recommendations.append('Use angles with at least 30° difference')
                
                if spacing < 0.25:
                    issues.append('Very tight spacing may increase mowing time significantly')
                    recommendations.append('Consider 0.3-0.5m spacing for balance of coverage and efficiency')
            
            return {
                'feasible': len(issues) == 0,
                'issues': issues,
                'recommendations': recommendations,
                'pattern_suitable': True  # Could add more sophisticated suitability analysis
            }
            
        except Exception as e:
            self.logger.error(f"Failed to validate pattern feasibility: {e}")
            return {
                'feasible': False,
                'issues': [f'Validation error: {str(e)}'],
                'recommendations': ['Check boundary data and pattern parameters']
            }

# Global pattern service instance
pattern_service = PatternService()
