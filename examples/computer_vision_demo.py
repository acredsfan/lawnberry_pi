"""
Computer Vision System Demo

This demo shows how to use the computer vision system for object detection,
safety monitoring, and continuous learning.
"""

import asyncio
import logging
from pathlib import Path
from datetime import datetime

from src.vision import VisionManager, VisionConfig, ProcessingMode
from src.hardware.managers import CameraManager
from src.communication.client import MQTTClient


async def vision_system_demo():
    """Demonstrate the computer vision system capabilities"""
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("Starting Computer Vision System Demo")
    
    # Create configuration
    config = VisionConfig(
        confidence_threshold=0.6,
        nms_threshold=0.4,
        max_detections=20,
        max_processing_time_ms=100.0,
        enable_tpu=True,
        fallback_to_cpu=True,
        person_detection_distance=3.0,
        pet_detection_distance=1.5,
        enable_continuous_learning=True,
        primary_model_path="models/efficientdet_d0.tflite",
        backup_model_path="models/mobilenet_ssd.tflite"
    )
    
    # Initialize components
    camera_manager = CameraManager("/dev/video0")
    mqtt_client = MQTTClient("localhost", 1883)
    data_storage_path = Path("vision_data")
    
    # Create vision manager
    vision_manager = VisionManager(
        camera_manager=camera_manager,
        mqtt_client=mqtt_client,
        config=config,
        data_storage_path=data_storage_path
    )
    
    try:
        # Initialize systems
        logger.info("Initializing camera...")
        await camera_manager.initialize(width=1920, height=1080, fps=30)
        
        logger.info("Connecting to MQTT broker...")
        await mqtt_client.connect()
        
        logger.info("Initializing vision system...")
        success = await vision_manager.initialize()
        
        if not success:
            logger.error("Failed to initialize vision system")
            return
        
        # Register safety callback
        def safety_callback(critical_objects):
            logger.warning(f"SAFETY ALERT: {len(critical_objects)} critical objects detected!")
            for obj in critical_objects:
                logger.warning(f"  - {obj.object_type.value}: confidence={obj.confidence:.2f}, "
                             f"distance={obj.distance_estimate:.1f}m")
        
        vision_manager.register_safety_callback(safety_callback)
        
        # Start vision processing
        logger.info("Starting vision processing...")
        await vision_manager.start_processing(ProcessingMode.REAL_TIME)
        
        # Run demo scenarios
        await demo_real_time_detection(vision_manager, logger)
        await demo_training_collection(vision_manager, logger)
        await demo_performance_monitoring(vision_manager, logger)
        
        # Keep running for demonstration
        logger.info("Vision system running... Press Ctrl+C to stop")
        await asyncio.sleep(30)  # Run for 30 seconds
        
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
    except Exception as e:
        logger.error(f"Demo error: {e}")
    finally:
        # Cleanup
        logger.info("Shutting down vision system...")
        await vision_manager.shutdown()
        await mqtt_client.disconnect()


async def demo_real_time_detection(vision_manager: VisionManager, logger):
    """Demonstrate real-time object detection"""
    logger.info("\n=== Real-time Object Detection Demo ===")
    
    # Let the system process frames for a few seconds
    await asyncio.sleep(5)
    
    # Get current statistics
    stats = await vision_manager.get_system_statistics()
    
    logger.info(f"Frames processed: {stats['system']['frames_processed']}")
    logger.info(f"Objects detected: {stats['system']['objects_detected']}")
    logger.info(f"Current FPS: {stats['system']['current_fps']:.1f}")
    logger.info(f"Average latency: {stats['system']['average_latency_ms']:.1f}ms")
    
    if stats['object_detector']['tpu_stats'].get('tpu_available'):
        logger.info("Coral TPU is active and processing frames")
    else:
        logger.info("Using CPU fallback for processing")


async def demo_training_collection(vision_manager: VisionManager, logger):
    """Demonstrate training data collection"""
    logger.info("\n=== Training Data Collection Demo ===")
    
    # Manually collect a training image
    logger.info("Collecting training image manually...")
    
    # This would normally be triggered by interesting detections
    # For demo, we'll simulate it with a command
    await vision_manager.mqtt_client.publish("commands/vision", {
        'command': 'collect_training_image'
    })
    
    await asyncio.sleep(1)
    
    # Get training statistics
    stats = await vision_manager.get_system_statistics()
    training_stats = stats.get('training_manager', {})
    
    logger.info(f"Training images collected: {training_stats.get('images_collected', {})}")
    logger.info(f"Continuous learning enabled: {training_stats.get('continuous_learning_enabled', False)}")


async def demo_performance_monitoring(vision_manager: VisionManager, logger):
    """Demonstrate performance monitoring"""
    logger.info("\n=== Performance Monitoring Demo ===")
    
    # Get comprehensive statistics
    stats = await vision_manager.get_system_statistics()
    
    # System performance
    system_stats = stats.get('system', {})
    logger.info(f"System uptime: {system_stats.get('uptime_seconds', 0):.1f} seconds")
    logger.info(f"Processing active: {system_stats.get('processing_active', False)}")
    logger.info(f"Safety triggers: {system_stats.get('safety_triggers', 0)}")
    
    # Camera processor performance
    camera_stats = stats.get('camera_processor', {})
    logger.info(f"Camera frames processed: {camera_stats.get('frames_processed', 0)}")
    logger.info(f"Camera processing time: {camera_stats.get('average_processing_time_ms', 0):.1f}ms")
    
    # Object detector performance
    detector_stats = stats.get('object_detector', {})
    logger.info(f"Detection model: {detector_stats.get('current_model', 'unknown')}")
    logger.info(f"Model loaded: {detector_stats.get('model_loaded', False)}")
    
    # TPU performance if available
    tpu_stats = detector_stats.get('tpu_stats', {})
    if tpu_stats.get('tpu_available'):
        logger.info(f"TPU inference time: {tpu_stats.get('average_inference_time_ms', 0):.1f}ms")
        logger.info(f"TPU inference count: {tpu_stats.get('inference_count', 0)}")


async def demo_manual_labeling():
    """Demonstrate manual labeling of training images"""
    logger = logging.getLogger(__name__)
    logger.info("\n=== Manual Labeling Demo ===")
    
    # This would typically be done through a web interface
    # Here we show the API for programmatic labeling
    
    config = VisionConfig()
    data_storage_path = Path("vision_data")
    
    from src.vision.training_manager import TrainingManager
    training_manager = TrainingManager(config, data_storage_path)
    
    # Example: Label an image with a person detection
    example_labels = [
        {
            'object_type': 'person',
            'bbox': {
                'x': 100,
                'y': 50,
                'width': 200,
                'height': 400
            },
            'confidence': 0.95,
            'difficulty': 'normal',
            'verified': True,
            'labeler': 'demo_user'
        }
    ]
    
    # This would use an actual image path in practice
    image_path = "vision_data/training_images/unlabeled/example_frame.jpg"
    
    logger.info(f"Example labeling format for image: {image_path}")
    logger.info(f"Labels: {example_labels}")


if __name__ == "__main__":
    # Run the main demo
    asyncio.run(vision_system_demo())
    
    # Run the labeling demo
    asyncio.run(demo_manual_labeling())
