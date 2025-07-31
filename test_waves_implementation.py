#!/usr/bin/env python3
"""
Simple test to verify Waves pattern implementation
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from navigation.pattern_generator import PatternGenerator, PatternType, Point, Boundary

def test_waves_pattern():
    """Test basic waves pattern generation"""
    print("Testing Waves Pattern Implementation...")
    
    # Create a simple rectangular boundary
    boundary = Boundary([
        Point(0.0, 0.0),
        Point(0.0, 10.0),
        Point(10.0, 10.0),
        Point(10.0, 0.0)
    ])
    
    # Initialize pattern generator
    generator = PatternGenerator()
    
    # Test waves pattern with default parameters
    parameters = {
        'amplitude': 0.75,
        'wavelength': 8.0,
        'base_angle': 0,
        'spacing': 0.4,
        'overlap': 0.1
    }
    
    try:
        paths = generator.generate_pattern(PatternType.WAVES, boundary, parameters)
        
        print(f"✅ Waves pattern generated {len(paths)} paths")
        
        if paths:
            total_points = sum(len(path) for path in paths)
            print(f"✅ Total points generated: {total_points}")
            
            # Verify first path has curved points (not straight line)
            if len(paths[0]) > 2:
                first_path = paths[0]
                # Check if y-coordinates vary (indicating wave pattern)
                y_coords = [p.y for p in first_path]
                y_variation = max(y_coords) - min(y_coords)
                print(f"✅ Wave amplitude variation: {y_variation:.2f}m")
                
                if y_variation > 0.1:  # Should have some wave variation
                    print("✅ Wave pattern shows proper sinusoidal variation")
                else:
                    print("⚠️  Wave variation seems minimal")
            
        return True
        
    except Exception as e:
        print(f"❌ Waves pattern test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_waves_pattern()
    print(f"\nTest {'PASSED' if success else 'FAILED'}")
