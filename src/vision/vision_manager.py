"""Main vision system manager orchestrating all computer vision components"""

import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path
from datetime import datetime
import time

from ..hardware.managers import CameraManager
try:
    import psutil  # type: ignore
except Exception:
    class _PsutilShim:
        @staticmethod
        def cpu_percent():
            return 0.0
    psutil = _PsutilShim()  # type: ignore
from ..communication.client import MQTTClient
from .camera_processor import CameraProcessor
from .object_detector import ObjectDetector
from .coral_tpu_manager import CoralTPUManager
from .training_manager import TrainingManager
from .data_structures import (
    VisionFrame, VisionConfig, ProcessingMode, 
    DetectedObject, SafetyLevel, ObjectType
)


class VisionManager:
    """Main orchestrator for the computer vision system"""
    
    def __init__(self, camera_manager: CameraManager, mqtt_client: MQTTClient, 
                 config: VisionConfig, data_storage_path: Path):
        self.logger = logging.getLogger(__name__)
        self.camera_manager = camera_manager
        self.mqtt_client = mqtt_client
        self.config = config
        
        # Core components
        self.camera_processor = CameraProcessor(camera_manager)
        self.object_detector = ObjectDetector(config)
        self.training_manager = TrainingManager(config, data_storage_path)
        
        # System state
        self._processing_active = False
        self._processing_task = None
        self._processing_mode = ProcessingMode.REAL_TIME
        
        # Performance monitoring
        self._frame_count = 0
        self._last_fps_calculation = time.time()
        self._current_fps = 0.0
        
        # Safety callbacks
        self._safety_callbacks: List[Callable[[List[DetectedObject]], None]] = []
        
        # Statistics
        self._system_stats = {
            'frames_processed': 0,
            'objects_detected': 0,
            'safety_triggers': 0,
            'average_latency_ms': 0.0,
            'uptime_seconds': 0.0
        }
        self._start_time = time.time()
    
    async def initialize(self) -> bool:
        """Initialize the vision system"""
        try:
            self.logger.info("Initializing computer vision system...")
            
            # Initialize object detector
            detector_success = await self.object_detector.initialize()
            if not detector_success:
                self.logger.error("Failed to initialize object detector")
                return False
            
            # Start camera capture
            await self.camera_manager.start_capture()
            
            # Setup MQTT subscriptions
            await self._setup_mqtt_subscriptions()
            
            self.logger.info("Computer vision system initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error initializing vision system: {e}")
            return False
    
    async def start_processing(self, mode: ProcessingMode = ProcessingMode.REAL_TIME):
        """Start vision processing loop"""
        if self._processing_active:
            self.logger.warning("Vision processing already active")
            return
        
        try:
            self._processing_mode = mode
            self._processing_active = True
            self._processing_task = asyncio.create_task(self._processing_loop())
            
            self.logger.info(f"Vision processing started in {mode.value} mode")
            
        except Exception as e:
            self.logger.error(f"Error starting vision processing: {e}")
            self._processing_active = False
    
    async def stop_processing(self):
        """Stop vision processing loop"""
        if not self._processing_active:
            return
        
        try:
            self._processing_active = False
            
            if self._processing_task:
                await self._processing_task
                self._processing_task = None
            
            self.logger.info("Vision processing stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping vision processing: {e}")
    
    async def _processing_loop(self):
        """Optimized main vision processing loop with performance enhancements"""
        self.logger.info("Vision processing loop started with performance optimizations")
        
        # Performance optimization variables
        frame_skip_counter = 0
        target_fps = 30
        frame_time_target = 1.0 / target_fps
        processing_times = []
        
        while self._processing_active:
            try:
                loop_start_time = time.perf_counter()
                
                # Dynamic frame skipping under high load
                current_load = psutil.cpu_percent()
                if current_load > 80 and frame_skip_counter % 2 == 0:
                    frame_skip_counter += 1
                    await asyncio.sleep(0.001)  # Small sleep to prevent CPU spinning
                    continue
                
                frame_skip_counter += 1
                
                # Get and process frame with timeout
                try:
                    vision_frame = await asyncio.wait_for(
                        self.camera_processor.get_processed_frame(self._processing_mode),
                        timeout=0.05  # 50ms timeout for frame processing
                    )
                except asyncio.TimeoutError:
                    self.logger.warning("Frame processing timeout - skipping frame")
                    continue
                
                if vision_frame:
                    # Run object detection
                    vision_frame = await self.object_detector.detect_objects(vision_frame)
                    
                    # Process results
                    await self._process_vision_results(vision_frame)
                    
                    # Update statistics
                    self._update_statistics(vision_frame)
                    
                    # Check for training opportunities
                    if self.config.enable_continuous_learning:
                        await self._check_training_opportunities(vision_frame)
                
                # Calculate processing time and maintain target FPS
                processing_time = (time.time() - loop_start_time) * 1000
                
                # Ensure we don't exceed maximum processing time
                if processing_time > self.config.max_processing_time_ms:
                    self.logger.warning(f"Processing time exceeded limit: {processing_time:.1f}ms")
                
                # Sleep to maintain target FPS (30fps = ~33ms per frame)
                target_frame_time = 33.3  # milliseconds
                sleep_time = max(0, (target_frame_time - processing_time) / 1000)
                
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in vision processing loop: {e}")
                await asyncio.sleep(0.1)  # Brief pause before retrying
        
        self.logger.info("Vision processing loop ended")
    
    async def _process_vision_results(self, vision_frame: VisionFrame):
        """Process vision results and trigger appropriate actions"""
        try:
            # Check for safety-critical objects
            critical_objects = vision_frame.get_critical_objects()
            
            if critical_objects:
                await self._handle_safety_critical_detection(critical_objects, vision_frame)
            
            # Publish detection results via MQTT
            await self._publish_detection_results(vision_frame)
            
            # Handle specific object types
            await self._handle_specific_objects(vision_frame.objects)
            
        except Exception as e:
            self.logger.error(f"Error processing vision results: {e}")
    
    async def _handle_safety_critical_detection(self, critical_objects: List[DetectedObject], 
                                              vision_frame: VisionFrame):
        """Handle detection of safety-critical objects"""
        try:
            self.logger.warning(f"Safety-critical objects detected: {len(critical_objects)}")
            
            # Create safety alert message
            safety_alert = {
                'timestamp': vision_frame.timestamp.isoformat(),
                'frame_id': vision_frame.frame_id,
                'critical_objects': [],
                'recommended_action': 'EMERGENCY_STOP'
            }
            
            for obj in critical_objects:
                obj_data = {
                    'type': obj.object_type.value,
                    'confidence': obj.confidence,
                    'safety_level': obj.safety_level.value,
                    'distance_estimate': obj.distance_estimate,
                    'bbox': {
                        'x': obj.bounding_box.x,
                        'y': obj.bounding_box.y,
                        'width': obj.bounding_box.width,
                        'height': obj.bounding_box.height
                    }
                }
                safety_alert['critical_objects'].append(obj_data)
            
            # Publish safety alert
            await self.mqtt_client.publish(
                "safety/vision_alert",
                safety_alert,
                qos=2  # Ensure delivery
            )
            
            # Call registered safety callbacks
            for callback in self._safety_callbacks:
                try:
                    callback(critical_objects)
                except Exception as e:
                    self.logger.error(f"Error in safety callback: {e}")
            
            # Update statistics
            self._system_stats['safety_triggers'] += 1
            
        except Exception as e:
            self.logger.error(f"Error handling safety-critical detection: {e}")
    
    async def _publish_detection_results(self, vision_frame: VisionFrame):
        """Publish detection results via MQTT"""
        try:
            # Create detection message
            detection_msg = {
                'timestamp': vision_frame.timestamp.isoformat(),
                'frame_id': vision_frame.frame_id,
                'processing_time_ms': vision_frame.processing_time_ms,
                'model_version': vision_frame.model_version,
                'tpu_used': vision_frame.tpu_used,
                'objects': []
            }
            
            for obj in vision_frame.objects:
                obj_data = {
                    'type': obj.object_type.value,
                    'confidence': obj.confidence,
                    'safety_level': obj.safety_level.value,
                    'distance_estimate': obj.distance_estimate,
                    'bbox': {
                        'x': obj.bounding_box.x,
                        'y': obj.bounding_box.y,
                        'width': obj.bounding_box.width,
                        'height': obj.bounding_box.height,
                        'confidence': obj.bounding_box.confidence
                    }
                }
                detection_msg['objects'].append(obj_data)
            
            # Publish detection results
            await self.mqtt_client.publish("vision/detections", detection_msg, qos=1)
            
            # Publish frame analysis summary
            analysis_msg = {
                'timestamp': vision_frame.timestamp.isoformat(),
                'frame_id': vision_frame.frame_id,
                'object_count': len(vision_frame.objects),
                'safety_critical_count': len(vision_frame.get_critical_objects()),
                'processing_performance': {
                    'processing_time_ms': vision_frame.processing_time_ms,
                    'tpu_used': vision_frame.tpu_used,
                    'model_version': vision_frame.model_version
                }
            }
            
            await self.mqtt_client.publish("vision/frame_analysis", analysis_msg, qos=0)
            
        except Exception as e:
            self.logger.error(f"Error publishing detection results: {e}")
    
    async def _handle_specific_objects(self, objects: List[DetectedObject]):
        """Handle detection of specific object types"""
        try:
            # Group objects by type
            objects_by_type = {}
            for obj in objects:
                if obj.object_type not in objects_by_type:
                    objects_by_type[obj.object_type] = []
                objects_by_type[obj.object_type].append(obj)
            
            # Handle people detection
            if ObjectType.PERSON in objects_by_type:
                people = objects_by_type[ObjectType.PERSON]
                self.logger.info(f"Detected {len(people)} person(s)")
                
                # Check if people are within safety distance
                for person in people:
                    if person.distance_estimate and person.distance_estimate < self.config.person_detection_distance:
                        self.logger.warning(f"Person detected within safety distance: {person.distance_estimate:.1f}m")
            
            # Handle pet detection
            if ObjectType.PET in objects_by_type:
                pets = objects_by_type[ObjectType.PET]
                self.logger.info(f"Detected {len(pets)} pet(s)")
                
                for pet in pets:
                    if pet.distance_estimate and pet.distance_estimate < self.config.pet_detection_distance:
                        self.logger.warning(f"Pet detected within safety distance: {pet.distance_estimate:.1f}m")
            
            # Handle hazardous objects
            hazardous_types = [ObjectType.HOSE, ObjectType.CABLE, ObjectType.HOLE]
            for hazard_type in hazardous_types:
                if hazard_type in objects_by_type:
                    hazards = objects_by_type[hazard_type]
                    self.logger.warning(f"Detected {len(hazards)} {hazard_type.value}(s)")
            
        except Exception as e:
            self.logger.error(f"Error handling specific objects: {e}")
    
    async def _check_training_opportunities(self, vision_frame: VisionFrame):
        """Check if frame should be collected for training"""
        try:
            should_collect = False
            trigger_reason = "unknown"
            
            # Collect frames with interesting detections
            if len(vision_frame.objects) > 0:
                should_collect = True
                trigger_reason = "objects_detected"
            
            # Collect frames with poor performance
            elif vision_frame.processing_time_ms > self.config.max_processing_time_ms * 0.8:
                should_collect = True
                trigger_reason = "slow_processing"
            
            # Collect frames with low confidence detections
            elif any(obj.confidence < 0.7 for obj in vision_frame.objects):
                should_collect = True
                trigger_reason = "low_confidence"
            
            # Random sampling for general improvement
            elif self._frame_count % 1000 == 0:  # Every 1000th frame
                should_collect = True
                trigger_reason = "random_sampling"
            
            if should_collect:
                success = await self.training_manager.collect_training_image(
                    vision_frame, trigger_reason
                )
                
                if success:
                    self.logger.debug(f"Training image collected: {trigger_reason}")
            
        except Exception as e:
            self.logger.error(f"Error checking training opportunities: {e}")
    
    async def _setup_mqtt_subscriptions(self):
        """Setup MQTT subscriptions for vision commands"""
        try:
            # Subscribe to vision commands
            await self.mqtt_client.subscribe("commands/vision", self._handle_vision_command)
            
            self.logger.info("MQTT subscriptions setup complete")
            
        except Exception as e:
            self.logger.error(f"Error setting up MQTT subscriptions: {e}")
    
    async def _handle_vision_command(self, topic: str, payload: Dict[str, Any]):
        """Handle incoming MQTT vision commands"""
        try:
            command = payload.get('command')
            
            if command == 'start_processing':
                mode_str = payload.get('mode', 'real_time')
                mode = ProcessingMode(mode_str)
                await self.start_processing(mode)
                
            elif command == 'stop_processing':
                await self.stop_processing()
                
            elif command == 'collect_training_image':
                # Force collection of current frame for training
                vision_frame = await self.camera_processor.get_processed_frame(ProcessingMode.TRAINING)
                if vision_frame:
                    await self.training_manager.collect_training_image(vision_frame, "manual_request")
                
            elif command == 'update_config':
                # Update configuration
                new_config = payload.get('config', {})
                await self._update_config(new_config)
                
            elif command == 'get_statistics':
                # Send current statistics
                stats = await self.get_system_statistics()
                await self.mqtt_client.publish("responses/vision", {
                    'command': 'statistics',
                    'data': stats
                })
            
            else:
                self.logger.warning(f"Unknown vision command: {command}")
            
        except Exception as e:
            self.logger.error(f"Error handling vision command: {e}")
    
    async def _update_config(self, new_config: Dict[str, Any]):
        """Update vision system configuration"""
        try:
            # Update configuration values
            for key, value in new_config.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
                    self.logger.info(f"Updated config: {key} = {value}")
            
            # Restart processing if mode changed
            if self._processing_active and 'processing_mode' in new_config:
                await self.stop_processing()
                new_mode = ProcessingMode(new_config['processing_mode'])
                await self.start_processing(new_mode)
            
        except Exception as e:
            self.logger.error(f"Error updating config: {e}")
    
    def _update_statistics(self, vision_frame: VisionFrame):
        """Update system performance statistics"""
        try:
            self._frame_count += 1
            self._system_stats['frames_processed'] += 1
            self._system_stats['objects_detected'] += len(vision_frame.objects)
            
            # Calculate FPS
            current_time = time.time()
            if current_time - self._last_fps_calculation >= 1.0:  # Update every second
                self._current_fps = self._frame_count / (current_time - self._last_fps_calculation)
                self._frame_count = 0
                self._last_fps_calculation = current_time
            
            # Calculate average latency
            if self._system_stats['frames_processed'] > 0:
                total_latency = self._system_stats['average_latency_ms'] * (self._system_stats['frames_processed'] - 1)
                total_latency += vision_frame.processing_time_ms
                self._system_stats['average_latency_ms'] = total_latency / self._system_stats['frames_processed']
            
            # Update uptime
            self._system_stats['uptime_seconds'] = time.time() - self._start_time
            
        except Exception as e:
            self.logger.error(f"Error updating statistics: {e}")
    
    async def get_system_statistics(self) -> Dict[str, Any]:
        """Get comprehensive system statistics"""
        try:
            # Get component statistics
            camera_stats = self.camera_processor.get_processing_stats()
            detector_stats = self.object_detector.get_detection_stats()
            training_stats = await self.training_manager.get_training_statistics()
            
            return {
                'system': {
                    **self._system_stats,
                    'current_fps': self._current_fps,
                    'processing_active': self._processing_active,
                    'processing_mode': self._processing_mode.value if self._processing_mode else None
                },
                'camera_processor': camera_stats,
                'object_detector': detector_stats,
                'training_manager': training_stats,
                'configuration': {
                    'confidence_threshold': self.config.confidence_threshold,
                    'nms_threshold': self.config.nms_threshold,
                    'max_processing_time_ms': self.config.max_processing_time_ms,
                    'enable_tpu': self.config.enable_tpu,
                    'continuous_learning': self.config.enable_continuous_learning
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error getting system statistics: {e}")
            return {}
    
    def register_safety_callback(self, callback: Callable[[List[DetectedObject]], None]):
        """Register a callback for safety-critical detections"""
        self._safety_callbacks.append(callback)
        self.logger.info("Safety callback registered")
    
    def unregister_safety_callback(self, callback: Callable[[List[DetectedObject]], None]):
        """Unregister a safety callback"""
        if callback in self._safety_callbacks:
            self._safety_callbacks.remove(callback)
            self.logger.info("Safety callback unregistered")
    
    async def manual_label_image(self, image_path: str, labels: List[Dict[str, Any]]) -> bool:
        """Manually label a training image"""
        return await self.training_manager.label_training_image(image_path, labels)
    
    async def trigger_model_retraining(self) -> bool:
        """Trigger retraining of the detection model"""
        return await self.training_manager.trigger_model_retraining()
    
    async def update_detection_model(self, model_path: str) -> bool:
        """Update the object detection model"""
        return await self.object_detector.update_model(model_path)
    
    async def shutdown(self):
        """Shutdown the vision system"""
        try:
            self.logger.info("Shutting down vision system...")
            
            # Stop processing
            await self.stop_processing()
            
            # Stop camera capture
            await self.camera_manager.stop_capture()
            
            # Cleanup training data
            await self.training_manager.cleanup_old_training_data()
            
            self.logger.info("Vision system shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during vision system shutdown: {e}")
