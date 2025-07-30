"""Coral TPU hardware acceleration manager"""

import asyncio
import logging
import numpy as np
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import time

try:
    from pycoral.utils import edgetpu
    from pycoral.utils import dataset
    from pycoral.adapters import common
    from pycoral.adapters import detect
    import tflite_runtime.interpreter as tflite
    CORAL_AVAILABLE = True
except ImportError:
    CORAL_AVAILABLE = False
    logging.warning("Coral TPU libraries not available, falling back to CPU")

from .data_structures import VisionConfig, ModelInfo


class CoralTPUManager:
    """Manages Coral TPU hardware acceleration for computer vision"""
    
    def __init__(self, config: VisionConfig):
        self.logger = logging.getLogger(__name__)
        self.config = config
        self._interpreter = None
        self._model_info = None
        self._tpu_available = False
        self._initialization_lock = asyncio.Lock()
        
        # Performance tracking
        self._inference_times = []
        self._inference_count = 0
        
    async def initialize(self, model_path: str) -> bool:
        """Initialize Coral TPU with specified model"""
        async with self._initialization_lock:
            try:
                if not CORAL_AVAILABLE:
                    self.logger.warning("Coral TPU libraries not available")
                    return False
                
                # Check if TPU is available
                tpu_devices = edgetpu.list_edge_tpus()
                if not tpu_devices:
                    self.logger.warning("No Coral TPU devices found")
                    return False
                
                self.logger.info(f"Found {len(tpu_devices)} Coral TPU device(s)")
                
                # Load model
                model_path = Path(model_path)
                if not model_path.exists():
                    self.logger.error(f"Model file not found: {model_path}")
                    return False
                
                # Create TPU interpreter
                self._interpreter = tflite.Interpreter(
                    model_path=str(model_path),
                    experimental_delegates=[edgetpu.make_edge_tpu_delegate()]
                )
                
                self._interpreter.allocate_tensors()
                
                # Get model information
                input_details = self._interpreter.get_input_details()
                output_details = self._interpreter.get_output_details()
                
                self._model_info = ModelInfo(
                    name=model_path.stem,
                    version="1.0",
                    path=str(model_path),
                    accuracy=0.0,  # Will be updated during operation
                    inference_time_ms=0.0,
                    tpu_optimized=True,
                    created_at=time.time(),
                    metadata={
                        'input_shape': input_details[0]['shape'].tolist(),
                        'output_count': len(output_details),
                        'input_dtype': str(input_details[0]['dtype']),
                        'quantized': input_details[0]['dtype'] != np.float32
                    }
                )
                
                self._tpu_available = True
                self.logger.info(f"Coral TPU initialized with model: {model_path}")
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to initialize Coral TPU: {e}")
                self._tpu_available = False
                return False
    
    async def run_inference(self, image: np.ndarray) -> Optional[Dict[str, Any]]:
        """Run inference on Coral TPU"""
        if not self._tpu_available or self._interpreter is None:
            return None
        
        try:
            start_time = time.time()
            
            # Preprocess image for model input
            processed_image = await self._preprocess_for_inference(image)
            if processed_image is None:
                return None
            
            # Set input tensor
            input_details = self._interpreter.get_input_details()
            self._interpreter.set_tensor(input_details[0]['index'], processed_image)
            
            # Run inference
            self._interpreter.invoke()
            
            # Get output tensors
            output_details = self._interpreter.get_output_details()
            outputs = {}
            
            for i, output_detail in enumerate(output_details):
                outputs[f'output_{i}'] = self._interpreter.get_tensor(output_detail['index'])
            
            # Calculate inference time
            inference_time = (time.time() - start_time) * 1000
            self._inference_times.append(inference_time)
            if len(self._inference_times) > 100:
                self._inference_times.pop(0)
            
            self._inference_count += 1
            
            # Update model info with latest inference time
            if self._model_info:
                self._model_info.inference_time_ms = inference_time
            
            return {
                'outputs': outputs,
                'inference_time_ms': inference_time,
                'model_info': self._model_info,
                'tpu_used': True
            }
            
        except Exception as e:
            self.logger.error(f"TPU inference failed: {e}")
            return None
    
    async def _preprocess_for_inference(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Preprocess image for model inference"""
        try:
            if self._model_info is None:
                return None
            
            # Get expected input shape
            input_shape = self._model_info.metadata['input_shape']
            height, width = input_shape[1], input_shape[2]
            
            # Resize image to model input size
            import cv2
            resized = cv2.resize(image, (width, height))
            
            # Convert to RGB if needed (OpenCV uses BGR)
            if len(resized.shape) == 3 and resized.shape[2] == 3:
                resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            
            # Normalize based on model requirements
            if self._model_info.metadata.get('quantized', False):
                # For quantized models, keep uint8
                processed = resized.astype(np.uint8)
            else:
                # For float models, normalize to [0, 1]
                processed = resized.astype(np.float32) / 255.0
            
            # Add batch dimension
            processed = np.expand_dims(processed, axis=0)
            
            return processed
            
        except Exception as e:
            self.logger.error(f"Error preprocessing image for inference: {e}")
            return None
    
    def parse_detection_results(self, inference_results: Dict[str, Any], 
                              confidence_threshold: float = 0.5) -> List[Dict[str, Any]]:
        """Parse TPU inference results into detection format"""
        try:
            if not inference_results or 'outputs' not in inference_results:
                return []
            
            outputs = inference_results['outputs']
            detections = []
            
            # Assume EfficientDet output format: boxes, classes, scores, num_detections
            if 'output_0' in outputs:  # boxes
                boxes = outputs['output_0'][0]  # Remove batch dimension
                classes = outputs['output_1'][0] if 'output_1' in outputs else None
                scores = outputs['output_2'][0] if 'output_2' in outputs else None
                num_detections = int(outputs['output_3'][0]) if 'output_3' in outputs else len(boxes)
                
                for i in range(min(num_detections, len(boxes))):
                    if scores is not None and scores[i] < confidence_threshold:
                        continue
                    
                    # Convert normalized coordinates to pixel coordinates
                    # Assuming boxes are in [ymin, xmin, ymax, xmax] format
                    ymin, xmin, ymax, xmax = boxes[i]
                    
                    detection = {
                        'bbox': {
                            'x': float(xmin),
                            'y': float(ymin),
                            'width': float(xmax - xmin),
                            'height': float(ymax - ymin)
                        },
                        'confidence': float(scores[i]) if scores is not None else 1.0,
                        'class_id': int(classes[i]) if classes is not None else 0,
                        'inference_time_ms': inference_results.get('inference_time_ms', 0)
                    }
                    
                    detections.append(detection)
            
            return detections
            
        except Exception as e:
            self.logger.error(f"Error parsing detection results: {e}")
            return []
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get TPU performance statistics"""
        avg_inference_time = 0.0
        if self._inference_times:
            avg_inference_time = sum(self._inference_times) / len(self._inference_times)
        
        return {
            'tpu_available': self._tpu_available,
            'inference_count': self._inference_count,
            'average_inference_time_ms': avg_inference_time,
            'recent_inference_times': self._inference_times[-10:] if self._inference_times else [],
            'model_info': self._model_info.__dict__ if self._model_info else None
        }
    
    async def benchmark_performance(self, test_image: np.ndarray, iterations: int = 100) -> Dict[str, Any]:
        """Benchmark TPU performance with test image"""
        if not self._tpu_available:
            return {'error': 'TPU not available'}
        
        try:
            inference_times = []
            successful_inferences = 0
            
            for i in range(iterations):
                result = await self.run_inference(test_image)
                if result:
                    inference_times.append(result['inference_time_ms'])
                    successful_inferences += 1
                
                # Small delay to prevent overheating
                await asyncio.sleep(0.01)
            
            if inference_times:
                return {
                    'iterations': iterations,
                    'successful_inferences': successful_inferences,
                    'success_rate': successful_inferences / iterations,
                    'average_inference_time_ms': sum(inference_times) / len(inference_times),
                    'min_inference_time_ms': min(inference_times),
                    'max_inference_time_ms': max(inference_times),
                    'fps_theoretical': 1000 / (sum(inference_times) / len(inference_times))
                }
            else:
                return {'error': 'No successful inferences'}
                
        except Exception as e:
            self.logger.error(f"Error during TPU benchmarking: {e}")
            return {'error': str(e)}
    
    async def load_new_model(self, model_path: str) -> bool:
        """Load a new model into the TPU"""
        self.logger.info(f"Loading new model: {model_path}")
        
        # Clean up current model
        if self._interpreter:
            del self._interpreter
            self._interpreter = None
        
        # Initialize with new model
        return await self.initialize(model_path)
    
    def is_available(self) -> bool:
        """Check if TPU is available and ready"""
        return self._tpu_available and self._interpreter is not None
    
    async def shutdown(self):
        """Shutdown TPU and clean up resources"""
        try:
            if self._interpreter:
                del self._interpreter
                self._interpreter = None
            
            self._tpu_available = False
            self.logger.info("Coral TPU shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during TPU shutdown: {e}")


# Fallback CPU implementation for when Coral TPU is not available
class CPUFallbackManager:
    """CPU fallback for when Coral TPU is not available"""
    
    def __init__(self, config: VisionConfig):
        self.logger = logging.getLogger(__name__)
        self.config = config
        self._interpreter = None
        self._model_info = None
        
    async def initialize(self, model_path: str) -> bool:
        """Initialize CPU-based TensorFlow Lite interpreter"""
        try:
            model_path = Path(model_path)
            if not model_path.exists():
                self.logger.error(f"Model file not found: {model_path}")
                return False
            
            # Create CPU interpreter
            self._interpreter = tflite.Interpreter(model_path=str(model_path))
            self._interpreter.allocate_tensors()
            
            self.logger.info(f"CPU fallback initialized with model: {model_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize CPU fallback: {e}")
            return False
    
    async def run_inference(self, image: np.ndarray) -> Optional[Dict[str, Any]]:
        """Run inference on CPU"""
        if self._interpreter is None:
            return None
        
        try:
            start_time = time.time()
            
            # Similar preprocessing and inference logic as TPU version
            # but without TPU-specific optimizations
            
            inference_time = (time.time() - start_time) * 1000
            
            return {
                'outputs': {},  # Implement actual inference
                'inference_time_ms': inference_time,
                'tpu_used': False
            }
            
        except Exception as e:
            self.logger.error(f"CPU inference failed: {e}")
            return None
    
    def is_available(self) -> bool:
        """Check if CPU fallback is available"""
        return self._interpreter is not None
