#!/usr/bin/env python3
"""
Test script for TPU integration functionality
Validates Google Coral TPU detection, model loading, and performance
"""

import asyncio
import logging
import sys
import numpy as np
from pathlib import Path
import time
import json

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from vision.coral_tpu_manager import CoralTPUManager, CPUFallbackManager
from vision.data_structures import VisionConfig


def setup_logging():
    """Setup logging for test"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


async def test_tpu_detection():
    """Test TPU device detection"""
    print("\n=== TPU Device Detection Test ===")
    
    try:
        from pycoral.utils import edgetpu
        tpu_devices = edgetpu.list_edge_tpus()
        
        if tpu_devices:
            print(f"✅ Found {len(tpu_devices)} TPU device(s):")
            for i, device in enumerate(tpu_devices):
                print(f"   Device {i}: {device}")
            return True
        else:
            print("❌ No TPU devices found")
            print("   Make sure Coral TPU is connected via USB")
            return False
            
    except ImportError:
        print("❌ pycoral not available")
        print("   Install with: pip install pycoral")
        return False
    except Exception as e:
        print(f"❌ Error detecting TPU: {e}")
        return False


async def test_model_loading():
    """Test custom model loading"""
    print("\n=== Custom Model Loading Test ===")
    
    config = VisionConfig(
        enable_tpu=True,
        fallback_to_cpu=True,
        primary_model_path="models/custom/lawn_obstacles_v1.tflite"
    )
    
    # Test TPU model loading
    tpu_manager = CoralTPUManager(config)
    tpu_success = await tpu_manager.initialize("models/custom/lawn_obstacles_v1.tflite")
    
    if tpu_success:
        print("✅ TPU model loading successful")
        stats = tpu_manager.get_performance_stats()
        if stats['model_info']:
            model_info = stats['model_info']
            print(f"   Model: {model_info['name']} v{model_info['version']}")
            print(f"   Lawn optimized: {model_info['metadata'].get('lawn_optimized', False)}")
            print(f"   Classes: {len(model_info['metadata'].get('custom_classes', {}))}")
        await tpu_manager.shutdown()
    else:
        print("❌ TPU model loading failed")
    
    # Test CPU fallback
    cpu_manager = CPUFallbackManager(config)
    cpu_success = await cpu_manager.initialize("models/custom/lawn_obstacles_v1.tflite")
    
    if cpu_success:
        print("✅ CPU fallback model loading successful")
        if cpu_manager._model_info:
            print(f"   Model: {cpu_manager._model_info['name']} (CPU mode)")
    else:
        print("❌ CPU fallback model loading failed")
    
    return tpu_success or cpu_success


async def test_inference_performance():
    """Test inference performance on both TPU and CPU"""
    print("\n=== Inference Performance Test ===")
    
    config = VisionConfig(
        enable_tpu=True,
        fallback_to_cpu=True,
        primary_model_path="models/custom/lawn_obstacles_v1.tflite"
    )
    
    # Create test image (simulated camera frame)
    test_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    
    # Test TPU performance
    tpu_manager = CoralTPUManager(config)
    tpu_success = await tpu_manager.initialize("models/custom/lawn_obstacles_v1.tflite")
    
    if tpu_success:
        print("🔄 Running TPU performance benchmark...")
        benchmark_results = await tpu_manager.benchmark_performance(test_image, iterations=50)
        
        if 'error' not in benchmark_results:
            print("✅ TPU Performance Results:")
            print(f"   Average inference time: {benchmark_results['average_inference_time_ms']:.2f} ms")
            print(f"   Theoretical FPS: {benchmark_results['fps_theoretical']:.1f}")
            print(f"   Success rate: {benchmark_results['success_rate']:.2%}")
        else:
            print(f"❌ TPU benchmark failed: {benchmark_results['error']}")
        
        await tpu_manager.shutdown()
    
    # Test CPU performance for comparison
    cpu_manager = CPUFallbackManager(config)
    cpu_success = await cpu_manager.initialize("models/custom/lawn_obstacles_v1.tflite")
    
    if cpu_success:
        print("🔄 Running CPU performance test...")
        start_time = time.time()
        
        # Simulate CPU inference (placeholder)
        await asyncio.sleep(0.1)  # Simulate CPU processing time
        
        cpu_time = (time.time() - start_time) * 1000
        print("✅ CPU Performance Results:")
        print(f"   Simulated inference time: {cpu_time:.2f} ms")
        print(f"   Note: This is a placeholder - actual CPU inference would be implemented")


async def test_graceful_fallback():
    """Test graceful fallback from TPU to CPU"""
    print("\n=== Graceful Fallback Test ===")
    
    config = VisionConfig(
        enable_tpu=True,
        fallback_to_cpu=True,
        primary_model_path="models/custom/lawn_obstacles_v1.tflite",
        backup_model_path="models/custom/lawn_obstacles_v1.tflite"
    )
    
    # Test fallback scenario
    print("🔄 Testing fallback scenario...")
    
    # Try TPU first
    tpu_manager = CoralTPUManager(config)
    tpu_available = tpu_manager.is_available()
    
    # Try CPU fallback
    cpu_manager = CPUFallbackManager(config)
    cpu_success = await cpu_manager.initialize(config.backup_model_path)
    
    if not tpu_available and cpu_success:
        print("✅ Graceful fallback working:")
        print("   TPU not available, successfully fell back to CPU")
    elif tpu_available:
        print("✅ TPU available, fallback not needed")
    else:
        print("❌ Both TPU and CPU fallback failed")
        return False
    
    return True


async def test_custom_model_metadata():
    """Test custom model metadata loading"""
    print("\n=== Custom Model Metadata Test ===")
    
    metadata_path = Path("models/custom/lawn_obstacles_v1.json")
    
    if metadata_path.exists():
        print("✅ Custom model metadata found")
        
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        model_info = metadata.get('model_info', {})
        print(f"   Model name: {model_info.get('name', 'Unknown')}")
        print(f"   Version: {model_info.get('version', 'Unknown')}")
        print(f"   Description: {model_info.get('description', 'No description')}")
        print(f"   TPU optimized: {model_info.get('tpu_optimized', False)}")
        
        classes = metadata.get('classes', {})
        print(f"   Object classes: {len(classes)}")
        for class_id, class_name in classes.items():
            if int(class_id) < 5:  # Show first 5 classes
                print(f"     {class_id}: {class_name}")
        
        return True
    else:
        print("❌ Custom model metadata not found")
        return False


def print_summary(results):
    """Print test summary"""
    print("\n" + "="*50)
    print("TPU INTEGRATION TEST SUMMARY")
    print("="*50)
    
    total_tests = len(results)
    passed_tests = sum(results.values())
    
    print(f"Total tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success rate: {passed_tests/total_tests:.1%}")
    
    print("\nDetailed Results:")
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {test_name}: {status}")
    
    if passed_tests == total_tests:
        print("\n🎉 All tests passed! TPU integration is working correctly.")
    else:
        print(f"\n⚠️  Some tests failed. Check the logs above for details.")


async def main():
    """Main test function"""
    setup_logging()
    
    print("TPU Integration Test Suite")
    print("=" * 50)
    
    results = {}
    
    # Run all tests
    results['TPU Detection'] = await test_tpu_detection()
    results['Model Loading'] = await test_model_loading()
    results['Inference Performance'] = await test_inference_performance()
    results['Graceful Fallback'] = await test_graceful_fallback()
    results['Custom Model Metadata'] = await test_custom_model_metadata()
    
    # Print summary
    print_summary(results)
    
    return all(results.values())


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
