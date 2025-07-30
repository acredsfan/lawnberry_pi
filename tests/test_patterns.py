"""
Test script for validating the new mowing patterns implementation.
"""

import asyncio
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from navigation.pattern_service import pattern_service
from navigation.pattern_generator import Point, Boundary
from web_api.models import MowingPattern

async def test_waves_pattern():
    """Test waves pattern generation"""
    print("Testing Waves Pattern...")
    
    # Create a simple rectangular boundary
    boundary_coords = [
        {'lat': 0.0, 'lng': 0.0},
        {'lat': 0.0, 'lng': 10.0},
        {'lat': 10.0, 'lng': 10.0},
        {'lat': 10.0, 'lng': 0.0}
    ]
    
    try:
        # Test with default parameters
        paths = await pattern_service.generate_pattern_path(
            MowingPattern.WAVES, boundary_coords
        )
        
        print(f"✅ Waves pattern generated {len(paths)} paths")
        
        # Test efficiency estimation
        efficiency = await pattern_service.estimate_pattern_efficiency(
            MowingPattern.WAVES, boundary_coords
        )
        
        print(f"✅ Efficiency score: {efficiency.get('efficiency_score', 'N/A')}")
        
        # Test validation
        validation = await pattern_service.validate_pattern_feasibility(
            MowingPattern.WAVES, boundary_coords
        )
        
        print(f"✅ Pattern feasible: {validation.get('feasible', False)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Waves pattern test failed: {e}")
        return False

async def test_crosshatch_pattern():
    """Test crosshatch pattern generation"""
    print("Testing Crosshatch Pattern...")
    
    # Create a simple rectangular boundary
    boundary_coords = [
        {'lat': 0.0, 'lng': 0.0},
        {'lat': 0.0, 'lng': 10.0},
        {'lat': 10.0, 'lng': 10.0},
        {'lat': 10.0, 'lng': 0.0}
    ]
    
    try:
        # Test with custom parameters
        parameters = {
            'first_angle': 45,
            'second_angle': 135,
            'spacing': 0.5
        }
        
        paths = await pattern_service.generate_pattern_path(
            MowingPattern.CROSSHATCH, boundary_coords, parameters
        )
        
        print(f"✅ Crosshatch pattern generated {len(paths)} paths")
        
        # Test efficiency estimation
        efficiency = await pattern_service.estimate_pattern_efficiency(
            MowingPattern.CROSSHATCH, boundary_coords, parameters
        )
        
        print(f"✅ Efficiency score: {efficiency.get('efficiency_score', 'N/A')}")
        
        # Test validation
        validation = await pattern_service.validate_pattern_feasibility(
            MowingPattern.CROSSHATCH, boundary_coords, parameters
        )
        
        print(f"✅ Pattern feasible: {validation.get('feasible', False)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Crosshatch pattern test failed: {e}")
        return False

async def test_pattern_configurations():
    """Test pattern configuration management"""
    print("Testing Pattern Configurations...")
    
    try:
        # Get all available patterns
        patterns = await pattern_service.get_available_patterns()
        
        print(f"✅ Found {len(patterns)} available patterns:")
        for pattern in patterns:
            print(f"  - {pattern.pattern.value}: {len(pattern.parameters)} parameters")
        
        # Test getting specific pattern config
        waves_config = await pattern_service.get_pattern_config(MowingPattern.WAVES)
        print(f"✅ Waves pattern has {len(waves_config.parameters)} parameters")
        
        crosshatch_config = await pattern_service.get_pattern_config(MowingPattern.CROSSHATCH)
        print(f"✅ Crosshatch pattern has {len(crosshatch_config.parameters)} parameters")
        
        return True
        
    except Exception as e:
        print(f"❌ Pattern configuration test failed: {e}")
        return False

async def main():
    """Run all pattern tests"""
    print("🔄 Testing Mowing Pattern Implementation")
    print("=" * 50)
    
    tests = [
        test_pattern_configurations,
        test_waves_pattern,
        test_crosshatch_pattern
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
            print()
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append(False)
    
    print("=" * 50)
    print(f"Test Results: {sum(results)}/{len(results)} passed")
    
    if all(results):
        print("🎉 All pattern tests passed!")
        return True
    else:
        print("⚠️  Some pattern tests failed")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
