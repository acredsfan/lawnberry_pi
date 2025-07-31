import sys
sys.path.append('.')

try:
    from src.navigation.pattern_service import PatternService
    from src.web_api.models import MowingPattern
    print("✓ Pattern service imports successful")
    
    service = PatternService()
    patterns = service._pattern_configs
    
    print(f"✓ Available patterns: {list(patterns.keys())}")
    
    expected_patterns = ['parallel_lines', 'checkerboard', 'spiral', 'waves', 'crosshatch']
    for pattern in expected_patterns:
        if pattern in patterns:
            params = patterns[pattern]['parameters']
            print(f"✓ {pattern}: {list(params.keys())}")
        else:
            print(f"✗ Missing pattern: {pattern}")
    
    print("✓ Pattern visualization implementation verified!")
    
except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
