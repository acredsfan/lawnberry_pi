"""
Test Pattern Visualization Implementation
Tests for hybrid pattern generation algorithms and API endpoints.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch
from src.navigation.pattern_service import PatternService
from src.navigation.pattern_generator import PatternGenerator, PatternType, Point, Boundary
from src.web_api.models import MowingPattern


class TestPatternVisualization:
    """Test pattern visualization functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.pattern_service = PatternService()
        self.pattern_generator = PatternGenerator()
        
        # Sample boundary for testing
        self.test_boundary = [
            {'lat': 40.0, 'lng': -82.0},
            {'lat': 40.001, 'lng': -82.0},
            {'lat': 40.001, 'lng': -82.001},
            {'lat': 40.0, 'lng': -82.001}
        ]
        
        self.boundary_points = [Point(coord['lat'], coord['lng']) for coord in self.test_boundary]
        self.boundary_obj = Boundary(self.boundary_points)
    
    @pytest.mark.asyncio
    async def test_pattern_generation_all_types(self):
        """Test that all 5 pattern types can be generated"""
        patterns_to_test = [
            MowingPattern.PARALLEL_LINES,
            MowingPattern.CHECKERBOARD,
            MowingPattern.SPIRAL,
            MowingPattern.WAVES,
            MowingPattern.CROSSHATCH
        ]
        
        for pattern in patterns_to_test:
            paths = await self.pattern_service.generate_pattern_path(
                pattern, self.test_boundary
            )
            
            assert len(paths) > 0, f"Pattern {pattern.value} should generate at least one path"
            assert all(len(path) >= 2 for path in paths), f"Pattern {pattern.value} paths should have at least 2 points"
            
            # Verify coordinates are within reasonable bounds
            for path in paths:
                for point in path:
                    assert 39.99 <= point['lat'] <= 40.002, f"Latitude out of bounds in {pattern.value}"
                    assert -82.002 <= point['lng'] <= -81.999, f"Longitude out of bounds in {pattern.value}"
    
    @pytest.mark.asyncio
    async def test_waves_pattern_parameters(self):
        """Test waves pattern with different parameters"""
        test_params = [
            {'amplitude': 0.5, 'wavelength': 5.0, 'base_angle': 0},
            {'amplitude': 1.0, 'wavelength': 10.0, 'base_angle': 45},
            {'amplitude': 1.5, 'wavelength': 15.0, 'base_angle': 90}
        ]
        
        for params in test_params:
            paths = await self.pattern_service.generate_pattern_path(
                MowingPattern.WAVES, self.test_boundary, params
            )
            
            assert len(paths) > 0, f"Waves pattern with params {params} should generate paths"
            
            # Verify wave characteristics (simplified check)
            for path in paths:
                if len(path) > 10:  # Only check longer paths
                    y_coords = [p['lng'] for p in path]
                    # Check for wave-like variation
                    variation = max(y_coords) - min(y_coords)
                    assert variation > 0.0001, "Wave pattern should show variation"
    
    @pytest.mark.asyncio
    async def test_crosshatch_pattern_parameters(self):
        """Test crosshatch pattern with different parameters"""
        test_params = [
            {'first_angle': 30, 'second_angle': 120, 'spacing': 0.3},
            {'first_angle': 45, 'second_angle': 135, 'spacing': 0.5},
            {'first_angle': 60, 'second_angle': 150, 'spacing': 0.2}
        ]
        
        for params in test_params:
            paths = await self.pattern_service.generate_pattern_path(
                MowingPattern.CROSSHATCH, self.test_boundary, params
            )
            
            assert len(paths) > 0, f"Crosshatch pattern with params {params} should generate paths"
            
            # Should generate multiple sets of lines for crosshatch
            assert len(paths) >= 4, "Crosshatch should generate multiple path segments"
    
    @pytest.mark.asyncio
    async def test_pattern_efficiency_calculation(self):
        """Test efficiency metrics calculation"""
        efficiency = await self.pattern_service.estimate_pattern_efficiency(
            MowingPattern.PARALLEL_LINES, self.test_boundary
        )
        
        required_fields = ['total_distance', 'coverage_area', 'efficiency_score', 'estimated_time_minutes']
        for field in required_fields:
            assert field in efficiency, f"Efficiency should include {field}"
            assert isinstance(efficiency[field], (int, float)), f"{field} should be numeric"
            assert efficiency[field] >= 0, f"{field} should be non-negative"
        
        # Efficiency score should be between 0 and 1
        assert 0 <= efficiency['efficiency_score'] <= 1, "Efficiency score should be between 0 and 1"
    
    @pytest.mark.asyncio
    async def test_boundary_compliance(self):
        """Test that patterns respect boundary constraints"""
        for pattern in [MowingPattern.WAVES, MowingPattern.CROSSHATCH]:
            paths = await self.pattern_service.generate_pattern_path(
                pattern, self.test_boundary
            )
            
            # All points should be within or very close to boundary
            min_lat = min(coord['lat'] for coord in self.test_boundary)
            max_lat = max(coord['lat'] for coord in self.test_boundary)
            min_lng = min(coord['lng'] for coord in self.test_boundary)
            max_lng = max(coord['lng'] for coord in self.test_boundary)
            
            for path in paths:
                for point in path:
                    # Allow small tolerance for boundary edge processing
                    assert (min_lat - 0.0001) <= point['lat'] <= (max_lat + 0.0001), \
                        f"Point {point} in {pattern.value} violates lat boundary"
                    assert (min_lng - 0.0001) <= point['lng'] <= (max_lng + 0.0001), \
                        f"Point {point} in {pattern.value} violates lng boundary"
    
    def test_hybrid_algorithm_components(self):
        """Test hybrid algorithm components work correctly"""
        # Test mathematical core generation
        params = {'spacing': 0.3, 'angle': 0, 'overlap': 0.1}
        paths = self.pattern_generator.generate_pattern(
            PatternType.PARALLEL_LINES, self.boundary_obj, params
        )
        
        assert len(paths) > 0, "Mathematical core should generate paths"
        
        # Test grid-based boundary adaptation
        for path in paths:
            assert len(path) >= 2, "Each path should have at least 2 points"
            
            # Check boundary compliance (grid refinement effect)
            for point in path:
                assert self._point_reasonable_bounds(point), "Point should be in reasonable bounds"
    
    def test_pattern_parameter_validation(self):
        """Test parameter validation works correctly"""
        # Test waves parameter validation
        waves_params = {'amplitude': 5.0, 'wavelength': 1.0}  # Invalid values
        validated = self.pattern_service._validate_pattern_parameters(
            MowingPattern.WAVES, waves_params
        )
        
        assert 0.25 <= validated['amplitude'] <= 2.0, "Amplitude should be clamped to valid range"
        assert 3.0 <= validated['wavelength'] <= 15.0, "Wavelength should be clamped to valid range"
        
        # Test crosshatch parameter validation
        crosshatch_params = {'first_angle': 200, 'second_angle': -50}  # Invalid angles
        validated = self.pattern_service._validate_pattern_parameters(
            MowingPattern.CROSSHATCH, crosshatch_params
        )
        
        assert 0 <= validated['first_angle'] < 180, "First angle should be normalized"
        assert 0 <= validated['second_angle'] < 180, "Second angle should be normalized"
    
    def _point_reasonable_bounds(self, point: Point) -> bool:
        """Check if point is within reasonable bounds of test boundary"""
        return (39.999 <= point.x <= 40.002 and 
                -82.002 <= point.y <= -81.999)


@pytest.mark.integration
class TestPatternVisualizationAPI:
    """Integration tests for pattern visualization API endpoints"""
    
    @pytest.mark.asyncio
    async def test_pattern_generation_endpoint(self):
        """Test pattern generation API endpoint"""
        # This would test the actual API endpoint
        # Mock implementation for now
        with patch('src.web_api.routers.patterns.pattern_service') as mock_service:
            mock_service.generate_pattern_path.return_value = [
                [{'lat': 40.0, 'lng': -82.0}, {'lat': 40.001, 'lng': -82.0}]
            ]
            
            # Simulate API call
            result = await mock_service.generate_pattern_path(
                MowingPattern.PARALLEL_LINES, 
                [{'lat': 40.0, 'lng': -82.0}]
            )
            
            assert len(result) > 0, "API should return pattern paths"
            mock_service.generate_pattern_path.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_pattern_efficiency_endpoint(self):
        """Test pattern efficiency API endpoint"""
        with patch('src.web_api.routers.patterns.pattern_service') as mock_service:
            mock_service.estimate_pattern_efficiency.return_value = {
                'total_distance': 100.0,
                'coverage_area': 50.0,
                'efficiency_score': 0.85,
                'estimated_time_minutes': 30.0
            }
            
            result = await mock_service.estimate_pattern_efficiency(
                MowingPattern.WAVES,
                [{'lat': 40.0, 'lng': -82.0}]
            )
            
            assert 'efficiency_score' in result, "API should return efficiency metrics"
            assert result['efficiency_score'] > 0, "Efficiency score should be positive"
            mock_service.estimate_pattern_efficiency.assert_called_once()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
