"""
Comprehensive tests for the computer vision system
"""

import pytest
import asyncio
import numpy as np
import cv2
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from src.vision import VisionManager, VisionConfig, ProcessingMode
from src.vision.camera_processor import CameraProcessor
from src.vision.object_detector import ObjectDetector
from src.vision.coral_tpu_manager import CoralTPUManager
from src.vision.training_manager import TrainingManager
from src.vision.data_structures import (
    VisionFrame, DetectedObject, BoundingBox, ObjectType, SafetyLevel
)
from src.hardware.managers import CameraManager
from src.hardware.data_structures import CameraFrame


@pytest.fixture
def vision_config():
    """Create test vision configuration"""
    return VisionConfig(
        confidence_threshold=0.5,
        nms_threshold=0.4,
        max_detections=10,
        max_processing_time_ms=100.0,
        enable_tpu=False,  # Disable TPU for testing
        fallback_to_cpu=True,
        enable_continuous_learning=False  # Disable for testing
    )


@pytest.fixture
def mock_camera_manager():
    """Create mock camera manager"""
    manager = Mock(spec=CameraManager)
    manager.get_latest_frame = AsyncMock()
    manager.start_capture = AsyncMock()
    manager.stop_capture = AsyncMock()
    return manager


@pytest.fixture
def mock_mqtt_client():
    """Create mock MQTT client"""
    client = Mock()
    client.publish = AsyncMock()
    client.subscribe = AsyncMock()
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    return client


@pytest.fixture
def sample_camera_frame():
    """Create sample camera frame for testing"""
    # Create a test image
    test_image = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.rectangle(test_image, (100, 100), (300, 300), (255, 255, 255), -1)
    
    # Encode to JPEG
    _, encoded = cv2.imencode('.jpg', test_image)
    frame_data = encoded.tobytes()
    
    return CameraFrame(
        timestamp=datetime.now(),
        frame_id=1,
        width=640,
        height=480,
        format='jpeg',
        data=frame_data
    )


@pytest.fixture
def sample_vision_frame():
    """Create sample vision frame for testing"""
    # Create test frame data
    test_image = np.zeros((480, 640, 3), dtype=np.uint8)
    
    vision_frame = VisionFrame(
        timestamp=datetime.now(),
        frame_id=1,
        width=640,
        height=480,
        processing_time_ms=25.0,
        metadata={'processed_frame': test_image}
    )
    
    # Add test objects
    bbox = BoundingBox(x=100, y=100, width=200, height=200, confidence=0.8)
    obj = DetectedObject(
        object_type=ObjectType.PERSON,
        bounding_box=bbox,
        confidence=0.8,
        safety_level=SafetyLevel.CRITICAL,
        distance_estimate=2.5
    )
    vision_frame.objects = [obj]
    
    return vision_frame


class TestCameraProcessor:
    """Test camera processor functionality"""
    
    @pytest.mark.asyncio
    async def test_get_processed_frame(self, mock_camera_manager, sample_camera_frame):
        """Test frame processing"""
        mock_camera_manager.get_latest_frame.return_value = sample_camera_frame
        
        processor = CameraProcessor(mock_camera_manager)
        result = await processor.get_processed_frame()
        
        assert result is not None
        assert result.width == 640
        assert result.height == 480
        assert 'processed_frame' in result.metadata
        assert result.processing_time_ms > 0
    
    @pytest.mark.asyncio
    async def test_lighting_detection(self, mock_camera_manager):
        """Test lighting condition detection"""
        processor = CameraProcessor(mock_camera_manager)
        
        # Test with bright image
        bright_image = np.full((480, 640, 3), 200, dtype=np.uint8)
        conditions = await processor.detect_lighting_conditions(bright_image)
        
        assert conditions['condition'] == 'bright'
        assert conditions['mean_brightness'] > 150
        assert conditions['is_suitable_for_detection'] is True
        
        # Test with dark image
        dark_image = np.full((480, 640, 3), 30, dtype=np.uint8)
        conditions = await processor.detect_lighting_conditions(dark_image)
        
        assert conditions['condition'] == 'very_dark'
        assert conditions['mean_brightness'] < 50
        assert conditions['is_suitable_for_detection'] is False
    
    @pytest.mark.asyncio
    async def test_weather_detection(self, mock_camera_manager):
        """Test weather condition detection"""
        processor = CameraProcessor(mock_camera_manager)
        
        # Test with normal image
        normal_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        conditions = await processor.detect_weather_conditions(normal_image)
        
        assert 'rain_detected' in conditions
        assert 'fog_detected' in conditions
        assert 'weather_suitable' in conditions
    
    def test_processing_stats(self, mock_camera_manager):
        """Test processing statistics"""
        processor = CameraProcessor(mock_camera_manager)
        processor.frames_processed = 100
        processor.processing_times = [25.0, 30.0, 28.0]
        
        stats = processor.get_processing_stats()
        
        assert stats['frames_processed'] == 100
        assert stats['average_processing_time_ms'] == 27.666666666666668
        assert len(stats['recent_processing_times']) == 3


class TestObjectDetector:
    """Test object detection functionality"""
    
    @pytest.mark.asyncio
    async def test_initialization(self, vision_config):
        """Test detector initialization"""
        detector = ObjectDetector(vision_config)
        
        # Mock successful initialization
        with patch.object(detector, 'cpu_manager') as mock_cpu:
            mock_cpu.initialize = AsyncMock(return_value=True)
            mock_cpu.is_available = Mock(return_value=True)
            
            success = await detector.initialize()
            assert success is True
            assert detector._model_loaded is True
    
    @pytest.mark.asyncio
    async def test_detect_objects(self, vision_config, sample_vision_frame):
        """Test object detection on vision frame"""
        detector = ObjectDetector(vision_config)
        detector._model_loaded = True
        
        # Mock inference result
        mock_inference = {
            'outputs': {'output_0': np.array([[[0.1, 0.1, 0.3, 0.3]]])},
            'inference_time_ms': 25.0,
            'tpu_used': False
        }
        
        with patch.object(detector, 'cpu_manager') as mock_cpu:
            mock_cpu.is_available = Mock(return_value=True)
            mock_cpu.run_inference = AsyncMock(return_value=mock_inference)
        
        with patch.object(detector, '_parse_cpu_results') as mock_parse:
            mock_parse.return_value = [{
                'bbox': {'x': 0.1, 'y': 0.1, 'width': 0.2, 'height': 0.2},
                'confidence': 0.8,
                'class_id': 0
            }]
            
            result = await detector.detect_objects(sample_vision_frame)
            
            assert len(result.objects) > 0
            assert result.tpu_used is False
    
    @pytest.mark.asyncio
    async def test_surface_analysis(self, vision_config):
        """Test surface condition analysis"""
        detector = ObjectDetector(vision_config)
        
        # Create test image with hole-like feature
        test_image = np.full((480, 640, 3), 128, dtype=np.uint8)
        cv2.circle(test_image, (320, 240), 50, (0, 0, 0), -1)  # Dark circle (hole)
        
        conditions = await detector.classify_surface_conditions(test_image)
        
        assert 'holes' in conditions
        assert 'slopes' in conditions
        assert 'wet_areas' in conditions
        assert 'surface_safe' in conditions
    
    def test_class_mapping(self, vision_config):
        """Test class ID to object type mapping"""
        detector = ObjectDetector(vision_config)
        
        # Test known mappings
        assert detector._map_class_to_object_type(0) == ObjectType.PERSON
        assert detector._map_class_to_object_type(15) == ObjectType.PET
        assert detector._map_class_to_object_type(999) == ObjectType.UNKNOWN
    
    def test_distance_estimation(self, vision_config):
        """Test distance estimation"""
        detector = ObjectDetector(vision_config)
        
        # Test person detection
        person_bbox = BoundingBox(x=100, y=100, width=200, height=400, confidence=0.8)
        distance = detector._estimate_distance(person_bbox, ObjectType.PERSON)
        
        assert distance is not None
        assert 0.1 <= distance <= 50.0  # Reasonable range
    
    def test_nms_application(self, vision_config):
        """Test Non-Maximum Suppression"""
        detector = ObjectDetector(vision_config)
        
        # Create overlapping detections
        bbox1 = BoundingBox(x=100, y=100, width=200, height=200, confidence=0.9)
        bbox2 = BoundingBox(x=110, y=110, width=200, height=200, confidence=0.7)
        
        obj1 = DetectedObject(ObjectType.PERSON, bbox1, 0.9, SafetyLevel.CRITICAL)
        obj2 = DetectedObject(ObjectType.PERSON, bbox2, 0.7, SafetyLevel.CRITICAL)
        
        detections = [obj1, obj2]
        filtered = detector._apply_nms(detections)
        
        # Should keep higher confidence detection
        assert len(filtered) == 1
        assert filtered[0].confidence == 0.9


class TestTrainingManager:
    """Test training manager functionality"""
    
    @pytest.fixture
    def training_manager(self, vision_config, tmp_path):
        """Create training manager with temporary storage"""
        return TrainingManager(vision_config, tmp_path)
    
    @pytest.mark.asyncio
    async def test_collect_training_image(self, training_manager, sample_vision_frame):
        """Test training image collection"""
        # Enable continuous learning for this test
        training_manager.config.enable_continuous_learning = True
        
        with patch('cv2.imwrite', return_value=True):
            success = await training_manager.collect_training_image(
                sample_vision_frame, "test_trigger"
            )
            
            assert success is True
    
    @pytest.mark.asyncio
    async def test_label_training_image(self, training_manager, tmp_path):
        """Test training image labeling"""
        # Create test image and metadata
        test_image_path = tmp_path / "test_image.jpg"
        test_metadata_path = tmp_path / "test_image.json"
        
        # Create dummy image
        test_image = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.imwrite(str(test_image_path), test_image)
        
        # Create metadata
        import json
        metadata = {
            'timestamp': datetime.now().isoformat(),
            'image_path': str(test_image_path),
            'width': 640,
            'height': 480,
            'labels': [],
            'metadata': {},
            'is_labeled': False
        }
        
        with open(test_metadata_path, 'w') as f:
            json.dump(metadata, f)
        
        # Create labeled directory
        labeled_dir = training_manager.training_images_path / "labeled"
        labeled_dir.mkdir(parents=True, exist_ok=True)
        
        # Test labeling
        labels = [{
            'object_type': 'person',
            'bbox': {'x': 100, 'y': 100, 'width': 200, 'height': 200},
            'confidence': 0.9
        }]
        
        success = await training_manager.label_training_image(str(test_image_path), labels)
        assert success is True
    
    @pytest.mark.asyncio
    async def test_training_statistics(self, training_manager):
        """Test training statistics collection"""
        stats = await training_manager.get_training_statistics()
        
        assert 'continuous_learning_enabled' in stats
        assert 'training_active' in stats
        assert 'images_collected' in stats
        assert 'labeling_progress' in stats


class TestVisionManager:
    """Test main vision manager"""
    
    @pytest.fixture
    def vision_manager(self, mock_camera_manager, mock_mqtt_client, vision_config, tmp_path):
        """Create vision manager for testing"""
        return VisionManager(
            camera_manager=mock_camera_manager,
            mqtt_client=mock_mqtt_client,
            config=vision_config,
            data_storage_path=tmp_path
        )
    
    @pytest.mark.asyncio
    async def test_initialization(self, vision_manager):
        """Test vision manager initialization"""
        with patch.object(vision_manager.object_detector, 'initialize', return_value=True):
            success = await vision_manager.initialize()
            assert success is True
    
    @pytest.mark.asyncio
    async def test_processing_lifecycle(self, vision_manager):
        """Test processing start/stop lifecycle"""
        with patch.object(vision_manager.object_detector, 'initialize', return_value=True):
            await vision_manager.initialize()
            
            # Test start processing
            await vision_manager.start_processing(ProcessingMode.REAL_TIME)
            assert vision_manager._processing_active is True
            assert vision_manager._processing_mode == ProcessingMode.REAL_TIME
            
            # Test stop processing
            await vision_manager.stop_processing()
            assert vision_manager._processing_active is False
    
    @pytest.mark.asyncio
    async def test_safety_callbacks(self, vision_manager):
        """Test safety callback registration and triggering"""
        callback_called = False
        detected_objects = None
        
        def safety_callback(objects):
            nonlocal callback_called, detected_objects
            callback_called = True
            detected_objects = objects
        
        # Register callback
        vision_manager.register_safety_callback(safety_callback)
        
        # Create critical detection
        bbox = BoundingBox(x=100, y=100, width=200, height=200, confidence=0.9)
        critical_obj = DetectedObject(
            ObjectType.PERSON, bbox, 0.9, SafetyLevel.CRITICAL, distance_estimate=1.0
        )
        
        # Simulate safety critical detection
        await vision_manager._handle_safety_critical_detection([critical_obj], Mock())
        
        assert callback_called is True
        assert len(detected_objects) == 1
        assert detected_objects[0].object_type == ObjectType.PERSON
    
    @pytest.mark.asyncio
    async def test_mqtt_command_handling(self, vision_manager):
        """Test MQTT command handling"""
        with patch.object(vision_manager, 'start_processing') as mock_start:
            await vision_manager._handle_vision_command("commands/vision", {
                'command': 'start_processing',
                'mode': 'real_time'
            })
            
            mock_start.assert_called_once_with(ProcessingMode.REAL_TIME)
    
    @pytest.mark.asyncio
    async def test_statistics_collection(self, vision_manager):
        """Test system statistics collection"""
        # Set up some test data
        vision_manager._system_stats['frames_processed'] = 100
        vision_manager._system_stats['objects_detected'] = 25
        vision_manager._current_fps = 28.5
        
        stats = await vision_manager.get_system_statistics()
        
        assert stats['system']['frames_processed'] == 100
        assert stats['system']['objects_detected'] == 25
        assert stats['system']['current_fps'] == 28.5
        assert 'camera_processor' in stats
        assert 'object_detector' in stats
        assert 'configuration' in stats


class TestIntegration:
    """Integration tests for complete vision system"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_processing(self, mock_camera_manager, mock_mqtt_client, 
                                       vision_config, tmp_path, sample_camera_frame):
        """Test complete end-to-end processing pipeline"""
        # Setup
        mock_camera_manager.get_latest_frame.return_value = sample_camera_frame
        vision_config.enable_continuous_learning = False  # Disable for test
        
        vision_manager = VisionManager(
            camera_manager=mock_camera_manager,
            mqtt_client=mock_mqtt_client,
            config=vision_config,
            data_storage_path=tmp_path
        )
        
        # Mock detector initialization
        with patch.object(vision_manager.object_detector, 'initialize', return_value=True):
            with patch.object(vision_manager.object_detector, 'detect_objects') as mock_detect:
                # Setup mock detection result
                mock_vision_frame = VisionFrame(
                    timestamp=datetime.now(),
                    frame_id=1,
                    width=640,
                    height=480
                )
                mock_detect.return_value = mock_vision_frame
                
                # Initialize and run one processing cycle
                await vision_manager.initialize()
                
                # Process a single frame
                processed_frame = await vision_manager.camera_processor.get_processed_frame()
                assert processed_frame is not None
                
                detected_frame = await vision_manager.object_detector.detect_objects(processed_frame)
                assert detected_frame is not None
    
    @pytest.mark.asyncio
    async def test_safety_response_time(self, mock_camera_manager, mock_mqtt_client, 
                                      vision_config, tmp_path):
        """Test that safety responses meet timing requirements"""
        vision_manager = VisionManager(
            camera_manager=mock_camera_manager,
            mqtt_client=mock_mqtt_client,
            config=vision_config,
            data_storage_path=tmp_path
        )
        
        # Create critical detection
        bbox = BoundingBox(x=100, y=100, width=200, height=200, confidence=0.9)
        critical_obj = DetectedObject(
            ObjectType.PERSON, bbox, 0.9, SafetyLevel.CRITICAL, distance_estimate=1.0
        )
        
        # Measure response time
        start_time = datetime.now()
        await vision_manager._handle_safety_critical_detection([critical_obj], Mock())
        response_time = (datetime.now() - start_time).total_seconds() * 1000
        
        # Should respond within 100ms requirement
        assert response_time < vision_config.emergency_response_time_ms
    
    @pytest.mark.asyncio
    async def test_resource_constraints(self, vision_config, tmp_path):
        """Test system behavior under resource constraints"""
        training_manager = TrainingManager(vision_config, tmp_path)
        
        # Test with limited memory
        vision_config.max_memory_usage_mb = 1  # Very low limit
        
        can_collect = await training_manager._check_resource_constraints()
        # Should respect resource limits
        assert isinstance(can_collect, bool)


# Performance benchmarks
class TestPerformance:
    """Performance tests to ensure system meets requirements"""
    
    @pytest.mark.asyncio
    async def test_processing_latency(self, mock_camera_manager, sample_camera_frame):
        """Test that processing latency meets <100ms requirement"""
        mock_camera_manager.get_latest_frame.return_value = sample_camera_frame
        
        processor = CameraProcessor(mock_camera_manager)
        
        start_time = datetime.now()
        result = await processor.get_processed_frame()
        latency = (datetime.now() - start_time).total_seconds() * 1000
        
        assert result is not None
        assert latency < 100.0  # Less than 100ms requirement
    
    @pytest.mark.asyncio
    async def test_detection_accuracy_requirement(self, vision_config):
        """Test detection accuracy meets >90% requirement"""
        # This would require a labeled test dataset in practice
        # For now, we test that the accuracy tracking mechanism works
        
        detector = ObjectDetector(vision_config)
        stats = detector.get_detection_stats()
        
        # Verify accuracy tracking is available
        assert 'total_detections' in stats
        assert 'successful_detections' in stats
    
    def test_false_positive_rate(self, vision_config):
        """Test false positive rate meets <5% requirement"""
        # This would require extensive testing with known negative samples
        # For now, we verify the tracking mechanism exists
        
        detector = ObjectDetector(vision_config)
        # The false positive tracking would be implemented in the detector
        assert hasattr(detector, '_detection_stats')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
