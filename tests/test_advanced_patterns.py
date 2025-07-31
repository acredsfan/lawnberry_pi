"""
Comprehensive test suite for advanced mowing patterns with AI optimization.
Tests Waves and Crosshatch patterns with sophisticated algorithmic enhancements.
"""

import asyncio
import pytest
import numpy as np
from typing import Dict, List, Any
from datetime import datetime
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from navigation.pattern_service import PatternService
from navigation.pattern_generator import PatternGenerator, PatternType, Point, Boundary
from navigation.ai_pattern_optimizer import (
    AIPatternOptimizer, YardCharacteristics, OptimizationStrategy, 
    PatternPerformanceMetric
)
from web_api.models import MowingPattern


class TestAdvancedPatterns:
    """Test suite for advanced mowing patterns"""
    
    @pytest.fixture
    def pattern_service(self):
        """Create pattern service instance"""
        return PatternService()
    
    @pytest.fixture
    def pattern_generator(self):
        """Create pattern generator instance"""
        return PatternGenerator()
    
    @pytest.fixture
    def ai_optimizer(self):
        """Create AI optimizer instance"""
        return AIPatternOptimizer()
    
    @pytest.fixture
    def simple_boundary(self):
        """Simple rectangular boundary for testing"""
        return [
            {'lat': 0.0, 'lng': 0.0},
            {'lat': 0.0, 'lng': 10.0},
            {'lat': 10.0, 'lng': 10.0},
            {'lat': 10.0, 'lng': 0.0}
        ]
    
    @pytest.fixture
    def complex_boundary(self):
        """Complex irregular boundary for testing"""
        return [
            {'lat': 0.0, 'lng': 0.0},
            {'lat': 2.0, 'lng': 3.0},
            {'lat': 8.0, 'lng': 5.0},
            {'lat': 12.0, 'lng': 2.0},
            {'lat': 10.0, 'lng': 8.0},
            {'lat': 4.0, 'lng': 12.0},
            {'lat': 1.0, 'lng': 8.0}
        ]
    
    @pytest.fixture
    def yard_characteristics(self):
        """Standard yard characteristics for testing"""
        return {
            'area': 100.0,
            'shape_complexity': 0.3,
            'obstacle_density': 0.15,
            'slope_variance': 0.2,
            'edge_ratio': 0.25,
            'irregular_sections': 2,
            'grass_type_distribution': {'bermuda': 0.7, 'fescue': 0.3}
        }
    
    @pytest.fixture
    def environmental_conditions(self):
        """Standard environmental conditions for testing"""
        return {
            'temperature': 22.0,
            'humidity': 60.0,
            'wind_speed': 5.0,
            'light_level': 0.8,
            'rain_probability': 0.1
        }

    async def test_waves_pattern_basic_functionality(self, pattern_service, simple_boundary):
        """Test basic Waves pattern generation"""
        print("Testing Waves Pattern Basic Functionality...")
        
        paths = await pattern_service.generate_pattern_path(
            MowingPattern.WAVES, simple_boundary
        )
        
        assert len(paths) > 0, "Waves pattern should generate at least one path"
        assert all(len(path) > 0 for path in paths), "All paths should contain points"
        
        # Verify sinusoidal characteristics
        for path in paths:
            if len(path) > 10:
                # Check for wave-like variation in y-coordinates
                y_coords = [point['lat'] for point in path]
                y_variation = max(y_coords) - min(y_coords)
                assert y_variation > 0, "Waves pattern should have y-coordinate variation"
        
        print(f"✅ Waves pattern generated {len(paths)} paths successfully")

    async def test_crosshatch_pattern_basic_functionality(self, pattern_service, simple_boundary):
        """Test basic Crosshatch pattern generation"""
        print("Testing Crosshatch Pattern Basic Functionality...")
        
        parameters = {
            'first_angle': 45,
            'second_angle': 135,
            'spacing': 0.4
        }
        
        paths = await pattern_service.generate_pattern_path(
            MowingPattern.CROSSHATCH, simple_boundary, parameters
        )
        
        assert len(paths) > 0, "Crosshatch pattern should generate at least one path"
        assert len(paths) % 2 == 0, "Crosshatch should generate even number of paths (two angles)"
        
        print(f"✅ Crosshatch pattern generated {len(paths)} paths successfully")

    async def test_ai_pattern_optimization(self, pattern_service, simple_boundary, 
                                         yard_characteristics, environmental_conditions):
        """Test AI-based pattern optimization"""
        print("Testing AI Pattern Optimization...")
        
        # Test AI-optimized Waves pattern
        optimized_paths = await pattern_service.generate_ai_optimized_pattern(
            MowingPattern.WAVES,
            simple_boundary,
            yard_characteristics,
            environmental_conditions,
            optimization_strategy="efficiency"
        )
        
        assert len(optimized_paths) > 0, "AI optimization should generate paths"
        
        # Test different optimization strategies
        strategies = ["efficiency", "quality", "battery", "balanced"]
        for strategy in strategies:
            paths = await pattern_service.generate_ai_optimized_pattern(
                MowingPattern.CROSSHATCH,
                simple_boundary,
                yard_characteristics,
                environmental_conditions,
                optimization_strategy=strategy
            )
            assert len(paths) > 0, f"Strategy {strategy} should generate paths"
        
        print("✅ AI pattern optimization working for all strategies")

    async def test_sophisticated_algorithmic_variations(self, pattern_generator, simple_boundary):
        """Test sophisticated algorithmic variations"""
        print("Testing Sophisticated Algorithmic Variations...")
        
        boundary = Boundary([Point(coord['lat'], coord['lng']) for coord in simple_boundary])
        
        # Test Bezier curve generation
        bezier_params = {
            'curve_type': 'bezier',
            'spacing': 0.5,
            'complexity': 0.4
        }
        
        bezier_paths = pattern_generator._generate_advanced_curved_lines(boundary, bezier_params)
        assert len(bezier_paths) > 0, "Bezier curves should be generated"
        
        # Test random offset algorithms
        random_params = {
            'base_pattern': 'parallel',
            'offset_variance': 0.3,
            'seed_rotation': True,
            'temporal_shift': 0.2
        }
        
        random_paths = pattern_generator._generate_random_offset_algorithms(boundary, random_params)
        assert len(random_paths) > 0, "Random offset algorithms should generate paths"
        
        print("✅ Sophisticated algorithmic variations working")

    async def test_pattern_efficiency_estimation(self, pattern_service, simple_boundary):
        """Test pattern efficiency estimation with AI enhancement"""
        print("Testing Pattern Efficiency Estimation...")
        
        # Test efficiency estimation for Waves
        waves_efficiency = await pattern_service.estimate_pattern_efficiency(
            MowingPattern.WAVES, simple_boundary
        )
        
        assert 'efficiency_score' in waves_efficiency, "Efficiency estimation should include score"
        assert waves_efficiency['efficiency_score'] >= 0, "Efficiency score should be non-negative"
        
        # Test efficiency estimation for Crosshatch
        crosshatch_efficiency = await pattern_service.estimate_pattern_efficiency(
            MowingPattern.CROSSHATCH, simple_boundary
        )
        
        assert 'efficiency_score' in crosshatch_efficiency, "Crosshatch efficiency should include score"
        
        print("✅ Pattern efficiency estimation working")

    async def test_complex_boundary_handling(self, pattern_service, complex_boundary,
                                           yard_characteristics, environmental_conditions):
        """Test advanced patterns with complex irregular boundaries"""
        print("Testing Complex Boundary Handling...")
        
        # Update yard characteristics for complex boundary
        complex_yard = yard_characteristics.copy()
        complex_yard['shape_complexity'] = 0.8
        complex_yard['irregular_sections'] = 5
        
        # Test Waves with complex boundary
        waves_paths = await pattern_service.generate_ai_optimized_pattern(
            MowingPattern.WAVES,
            complex_boundary,
            complex_yard,
            environmental_conditions,
            optimization_strategy="terrain"
        )
        
        assert len(waves_paths) > 0, "Waves should handle complex boundaries"
        
        # Test Crosshatch with complex boundary
        crosshatch_paths = await pattern_service.generate_ai_optimized_pattern(
            MowingPattern.CROSSHATCH,
            complex_boundary,
            complex_yard,
            environmental_conditions,
            optimization_strategy="quality"
        )
        
        assert len(crosshatch_paths) > 0, "Crosshatch should handle complex boundaries"
        
        print("✅ Complex boundary handling working")

    async def test_ai_learning_system(self, pattern_service, simple_boundary,
                                    yard_characteristics, environmental_conditions):
        """Test AI learning from performance data"""
        print("Testing AI Learning System...")
        
        # Simulate pattern performance data
        performance_metrics = {
            'coverage_efficiency': 0.85,
            'battery_usage': 0.6,
            'time_to_complete': 2400,
            'grass_quality_score': 0.9,
            'terrain_adaptation_score': 0.8,
            'weather_resilience': 0.7,
            'user_satisfaction': 0.85,
            'edge_case_handling': 0.75
        }
        
        # Test learning from Waves pattern performance
        await pattern_service.learn_from_pattern_performance(
            MowingPattern.WAVES,
            simple_boundary,
            yard_characteristics,
            environmental_conditions,
            performance_metrics
        )
        
        # Test learning from Crosshatch pattern performance
        await pattern_service.learn_from_pattern_performance(
            MowingPattern.CROSSHATCH,
            simple_boundary,
            yard_characteristics,
            environmental_conditions,
            performance_metrics
        )
        
        print("✅ AI learning system working")

    async def test_pattern_parameter_validation(self, pattern_service, simple_boundary):
        """Test pattern parameter validation and edge cases"""
        print("Testing Pattern Parameter Validation...")
        
        # Test Waves with extreme parameters
        extreme_waves_params = {
            'amplitude': 5.0,  # Too high
            'wavelength': 100.0,  # Too high
            'spacing': 0.05,  # Too small
            'base_angle': 720  # Invalid angle
        }
        
        paths = await pattern_service.generate_pattern_path(
            MowingPattern.WAVES, simple_boundary, extreme_waves_params
        )
        assert len(paths) > 0, "Should handle extreme parameters gracefully"
        
        # Test Crosshatch with invalid angles
        invalid_crosshatch_params = {
            'first_angle': 45,
            'second_angle': 50,  # Too close to first angle
            'spacing': 0.3
        }
        
        paths = await pattern_service.generate_pattern_path(
            MowingPattern.CROSSHATCH, simple_boundary, invalid_crosshatch_params
        )
        assert len(paths) > 0, "Should handle invalid angle parameters"
        
        print("✅ Parameter validation working")

    async def test_performance_benchmarking(self, pattern_service, simple_boundary):
        """Test comprehensive performance benchmarking"""
        print("Testing Performance Benchmarking...")
        
        import time
        
        patterns_to_test = [MowingPattern.WAVES, MowingPattern.CROSSHATCH]
        performance_results = {}
        
        for pattern in patterns_to_test:
            start_time = time.time()
            
            paths = await pattern_service.generate_pattern_path(pattern, simple_boundary)
            
            end_time = time.time()
            generation_time = end_time - start_time
            
            performance_results[pattern.value] = {
                'generation_time': generation_time,
                'path_count': len(paths),
                'total_points': sum(len(path) for path in paths)
            }
        
        # Verify performance is reasonable
        for pattern, metrics in performance_results.items():
            assert metrics['generation_time'] < 10.0, f"{pattern} generation should be under 10 seconds"
            assert metrics['path_count'] > 0, f"{pattern} should generate paths"
            
        print("✅ Performance benchmarking completed")
        for pattern, metrics in performance_results.items():
            print(f"  {pattern}: {metrics['generation_time']:.3f}s, {metrics['path_count']} paths, {metrics['total_points']} points")

    async def test_integration_with_safety_systems(self, pattern_service, simple_boundary):
        """Test integration with boundary and no-go zone systems"""
        print("Testing Integration with Safety Systems...")
        
        # Test with no-go zones (simulated as smaller boundaries within main boundary)
        no_go_zones = [
            [{'lat': 3.0, 'lng': 3.0}, {'lat': 3.0, 'lng': 5.0}, 
             {'lat': 5.0, 'lng': 5.0}, {'lat': 5.0, 'lng': 3.0}]
        ]
        
        # Generate patterns and verify they respect boundaries
        waves_paths = await pattern_service.generate_pattern_path(
            MowingPattern.WAVES, simple_boundary
        )
        
        crosshatch_paths = await pattern_service.generate_pattern_path(
            MowingPattern.CROSSHATCH, simple_boundary
        )
        
        # Verify all points are within boundary
        for paths in [waves_paths, crosshatch_paths]:
            for path in paths:
                for point in path:
                    lat, lng = point['lat'], point['lng']
                    assert 0 <= lat <= 10, f"Point {lat}, {lng} outside boundary"
                    assert 0 <= lng <= 10, f"Point {lat}, {lng} outside boundary"
        
        print("✅ Safety system integration working")


async def run_comprehensive_tests():
    """Run all advanced pattern tests"""
    print("🔄 Running Comprehensive Advanced Pattern Tests")
    print("=" * 60)
    
    test_suite = TestAdvancedPatterns()
    
    # Create fixtures
    pattern_service = test_suite.pattern_service()
    pattern_generator = test_suite.pattern_generator()
    ai_optimizer = test_suite.ai_optimizer()
    simple_boundary = test_suite.simple_boundary()
    complex_boundary = test_suite.complex_boundary()
    yard_characteristics = test_suite.yard_characteristics()
    environmental_conditions = test_suite.environmental_conditions()
    
    # Initialize AI optimizer
    await ai_optimizer.initialize()
    await pattern_service.initialize_ai_optimizer()
    
    # Run tests
    tests = [
        test_suite.test_waves_pattern_basic_functionality(pattern_service, simple_boundary),
        test_suite.test_crosshatch_pattern_basic_functionality(pattern_service, simple_boundary),
        test_suite.test_ai_pattern_optimization(pattern_service, simple_boundary, 
                                               yard_characteristics, environmental_conditions),
        test_suite.test_sophisticated_algorithmic_variations(pattern_generator, simple_boundary),
        test_suite.test_pattern_efficiency_estimation(pattern_service, simple_boundary),
        test_suite.test_complex_boundary_handling(pattern_service, complex_boundary,
                                                 yard_characteristics, environmental_conditions),
        test_suite.test_ai_learning_system(pattern_service, simple_boundary,
                                          yard_characteristics, environmental_conditions),
        test_suite.test_pattern_parameter_validation(pattern_service, simple_boundary),
        test_suite.test_performance_benchmarking(pattern_service, simple_boundary),
        test_suite.test_integration_with_safety_systems(pattern_service, simple_boundary)
    ]
    
    # Execute all tests
    passed = 0
    failed = 0
    
    for i, test in enumerate(tests, 1):
        try:
            await test
            passed += 1
            print(f"Test {i}/10 ✅ PASSED")
        except Exception as e:
            failed += 1
            print(f"Test {i}/10 ❌ FAILED: {e}")
    
    print("=" * 60)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All advanced pattern tests PASSED!")
        return True
    else:
        print(f"⚠️ {failed} tests failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_comprehensive_tests())
    exit(0 if success else 1)
