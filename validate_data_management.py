#!/usr/bin/env python3
"""
Validation script for data management system
"""

import sys
import os
sys.path.append('.')

def test_imports():
    """Test all module imports"""
    try:
        from src.data_management import DataManager
        from src.data_management.models import SensorReading, DataType
        from src.data_management.cache_manager import CacheManager
        from src.data_management.database_manager import DatabaseManager
        from src.data_management.state_manager import StateManager, SystemState
        from src.data_management.analytics_engine import AnalyticsEngine
        print("✓ All imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def test_models():
    """Test model creation and serialization"""
    try:
        from datetime import datetime
        from src.data_management.models import SensorReading
        
        # Create test sensor reading
        reading = SensorReading(
            sensor_id='test_01',
            sensor_type='temperature',
            timestamp=datetime.now(),
            value=25.5,
            unit='°C'
        )
        print(f"✓ SensorReading created: {reading.sensor_id} = {reading.value}{reading.unit}")
        
        # Test serialization
        data_dict = reading.to_dict()
        restored = SensorReading.from_dict(data_dict)
        
        if restored.sensor_id == reading.sensor_id and restored.value == reading.value:
            print("✓ Model serialization/deserialization successful")
            return True
        else:
            print("✗ Model serialization failed")
            return False
            
    except Exception as e:
        print(f"✗ Model test error: {e}")
        return False

def test_database_schema():
    """Test database manager initialization"""
    try:
        import tempfile
        import asyncio
        from src.data_management.database_manager import DatabaseManager
        
        async def test_db():
            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
                db = DatabaseManager(tmp.name)
                success = await db.initialize()
                await db.close()
                os.unlink(tmp.name)
                return success
        
        success = asyncio.run(test_db())
        if success:
            print("✓ Database schema creation successful")
            return True
        else:
            print("✗ Database schema creation failed")
            return False
            
    except Exception as e:
        print(f"✗ Database test error: {e}")
        return False

def main():
    """Run all validation tests"""
    print("Data Management System Validation")
    print("=" * 40)
    
    tests = [
        ("Module Imports", test_imports),
        ("Data Models", test_models),
        ("Database Schema", test_database_schema)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\nTesting {test_name}...")
        if test_func():
            passed += 1
        else:
            print(f"FAILED: {test_name}")
    
    print(f"\n{'='*40}")
    print(f"Validation Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ Data management system validation PASSED")
        return 0
    else:
        print("✗ Data management system validation FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
