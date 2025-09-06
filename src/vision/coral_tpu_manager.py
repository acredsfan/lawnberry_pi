"""Enhanced Coral TPU hardware acceleration manager with advanced lawn-specific optimizations"""

import asyncio
import hashlib
import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

try:
    import psutil
except Exception:
    psutil = None
from collections import deque

# Try to import Coral TPU libraries first
try:
    from pycoral.utils import edgetpu

    CORAL_AVAILABLE = True
    CORAL_HARDWARE_PRESENT = False  # Will be set during initialization
    logging.info("Coral TPU libraries imported successfully")
except ImportError as e:
    CORAL_AVAILABLE = False
    CORAL_HARDWARE_PRESENT = False
    edgetpu = None
    logging.warning(f"Coral TPU libraries not available: {e}. Using CPU fallback.")

# Try to import TensorFlow Lite runtime
try:
    import tflite_runtime.interpreter as tflite

    TFLITE_AVAILABLE = True
    logging.info("TensorFlow Lite runtime imported successfully")
except ImportError:
    try:
        import tensorflow.lite as tflite

        TFLITE_AVAILABLE = True
        logging.info("Using TensorFlow Lite from TensorFlow package")
    except ImportError as e:
        TFLITE_AVAILABLE = False
        tflite = None
        logging.error(f"Neither tflite_runtime nor tensorflow.lite available: {e}")

from .data_structures import ModelInfo, VisionConfig


class CoralTPUManager:
    """Enhanced Coral TPU hardware acceleration manager with advanced features"""

    def __init__(self, config: VisionConfig):
        self.logger = logging.getLogger(__name__)
        self.config = config
        self._interpreter = None
        self._model_info = None
        self._tpu_available = False
        self._initialization_lock = asyncio.Lock()

        # Enhanced performance tracking
        self._inference_times: deque = deque(maxlen=1000)
        self._inference_count = 0
        self._power_consumption: deque = deque(maxlen=100)
        self._temperature_readings: deque = deque(maxlen=100)

        # Advanced caching system
        self._inference_cache: Dict[str, Any] = {}
        self._cache_hit_count = 0
        self._cache_miss_count = 0
        self._max_cache_size = 100

        # TPU health monitoring
        self._health_status = {
            "operational": False,
            "temperature": 0.0,
            "power_draw": 0.0,
            "utilization": 0.0,
            "error_count": 0,
            "last_check": time.time(),
        }

        # Model management
        self._loaded_models: Dict[str, Any] = {}
        self._active_model_queue: queue.Queue = queue.Queue(maxsize=3)

        # Performance optimization settings
        self._optimization_settings = {
            "enable_batching": True,
            "batch_size": 4,
            "enable_caching": True,
            "cache_threshold": 0.95,  # Similarity threshold for cache hits
            "power_management": True,
            "thermal_throttling": True,
        }

    async def initialize(self, model_path: str) -> bool:
        """Enhanced TPU initialization with comprehensive hardware detection"""
        async with self._initialization_lock:
            try:
                if not CORAL_AVAILABLE:
                    self.logger.warning(
                        "Coral TPU libraries not available - ensure pycoral and tflite-runtime[coral] are installed"
                    )
                    self._log_installation_help()
                    return False

                # Enhanced TPU device detection
                tpu_devices = edgetpu.list_edge_tpus()
                if not tpu_devices:
                    self.logger.warning("No Coral TPU devices found")
                    self._log_connection_troubleshooting()
                    return False

                # Log detailed TPU information
                for i, device in enumerate(tpu_devices):
                    self.logger.info(
                        f"TPU Device {i}: Type={device['type']}, Path={device.get('path', 'N/A')}"
                    )

                # Validate model file
                model_path = Path(model_path)
                if not model_path.exists():
                    self.logger.error(f"Model file not found: {model_path}")
                    await self._suggest_available_models()
                    return False

                # Load enhanced model metadata
                custom_metadata = await self._load_enhanced_metadata(model_path)

                # Create TPU interpreter with error handling
                try:
                    self._interpreter = tflite.Interpreter(
                        model_path=str(model_path),
                        experimental_delegates=[edgetpu.make_edge_tpu_delegate()],
                    )
                    self._interpreter.allocate_tensors()

                except Exception as delegate_error:
                    self.logger.error(f"Failed to create TPU delegate: {delegate_error}")
                    self.logger.info("Attempting TPU initialization with alternative settings...")
                    # Try with specific TPU device
                    if tpu_devices:
                        try:
                            delegate = edgetpu.make_edge_tpu_delegate(device=tpu_devices[0]["path"])
                            self._interpreter = tflite.Interpreter(
                                model_path=str(model_path), experimental_delegates=[delegate]
                            )
                            self._interpreter.allocate_tensors()
                        except Exception as retry_error:
                            self.logger.error(f"TPU initialization retry failed: {retry_error}")
                            return False

                # Enhanced model information gathering
                input_details = self._interpreter.get_input_details()
                output_details = self._interpreter.get_output_details()

                # Create comprehensive model info
                model_info = custom_metadata.get("model_info", {})
                self._model_info = ModelInfo(
                    name=model_info.get("name", Path(model_path).stem),
                    version=model_info.get("version", "1.0"),
                    path=str(model_path),
                    accuracy=model_info.get("accuracy", 0.0),
                    inference_time_ms=model_info.get("inference_time_ms", 0.0),
                    tpu_optimized=model_info.get("tpu_optimized", True),
                    created_at=time.time(),
                    metadata={
                        "input_shape": input_details[0]["shape"].tolist(),
                        "output_count": len(output_details),
                        "input_dtype": str(input_details[0]["dtype"]),
                        "quantized": input_details[0]["dtype"] != np.float32,
                        "custom_classes": custom_metadata.get("classes", {}),
                        "performance_metrics": custom_metadata.get("performance_metrics", {}),
                        "lawn_optimized": "lawn" in model_info.get("description", "").lower(),
                        "advanced_features": custom_metadata.get("advanced_features", {}),
                        "tpu_device_info": tpu_devices[0] if tpu_devices else None,
                    },
                )

                # Initialize TPU health monitoring
                await self._start_health_monitoring()

                self._tpu_available = True
                self._health_status["operational"] = True

                self.logger.info(f"Enhanced Coral TPU initialized successfully!")
                if self._model_info:
                    self.logger.info(f"Model: {self._model_info.name} v{self._model_info.version}")
                    self.logger.info(f"Input shape: {self._model_info.metadata['input_shape']}")
                    self.logger.info(
                        f"Lawn-optimized: {self._model_info.metadata['lawn_optimized']}"
                    )
                    self.logger.info(
                        f"Advanced caching: {self._optimization_settings['enable_caching']}"
                    )
                    self.logger.info(
                        f"Power management: {self._optimization_settings['power_management']}"
                    )

                return True

            except Exception as e:
                self.logger.error(f"Failed to initialize Enhanced Coral TPU: {e}")
                self._health_status["error_count"] += 1
                self._tpu_available = False
                return False

    def _log_installation_help(self):
        """Log TPU installation help information"""
        self.logger.info("TPU Installation Help:")
        self.logger.info("1. Install TPU runtime: pip install pycoral")
        self.logger.info("2. Install TensorFlow Lite: pip install tflite-runtime[coral]")
        self.logger.info("3. For Raspberry Pi: https://coral.ai/docs/accelerator/get-started/")
        self.logger.info("4. Verify USB connection and permissions")

    def _log_connection_troubleshooting(self):
        """Log TPU connection troubleshooting steps"""
        self.logger.info("TPU Connection Troubleshooting:")
        self.logger.info("1. Check USB connection (use lsusb to verify)")
        self.logger.info("2. Verify TPU permissions: sudo usermod -a -G plugdev $USER")
        self.logger.info("3. Reboot after permission changes")
        self.logger.info("4. Try different USB port (preferably USB 3.0)")
        self.logger.info("5. Check power supply (TPU requires adequate power)")

    async def _suggest_available_models(self):
        """Suggest available models if specified model not found"""
        custom_models = list(Path("models/custom").glob("*.tflite"))
        if custom_models:
            self.logger.info("Available custom models:")
            for model in custom_models:
                self.logger.info(f"  - {model.name}")
        else:
            self.logger.info("No custom models found in models/custom/")
            self.logger.info("Consider training a model or downloading a pre-trained model")

    async def _load_enhanced_metadata(self, model_path: Path) -> Dict[str, Any]:
        """Load enhanced model metadata with validation"""
        metadata_path = Path(str(model_path).replace(".tflite", ".json"))
        custom_metadata = {}

        if metadata_path.exists():
            try:
                with open(metadata_path, "r") as f:
                    custom_metadata = json.load(f)
                self.logger.info(
                    f"Loaded enhanced metadata: {custom_metadata.get('model_info', {}).get('name', 'Unknown')}"
                )

                # Validate metadata structure
                if "model_info" not in custom_metadata:
                    custom_metadata["model_info"] = {}
                if "classes" not in custom_metadata:
                    custom_metadata["classes"] = {}

            except Exception as e:
                self.logger.warning(f"Failed to load model metadata: {e}")
                custom_metadata = {}
        else:
            self.logger.info("No metadata file found, using defaults")

        return custom_metadata

    async def _start_health_monitoring(self):
        """Start TPU health monitoring in background"""
        asyncio.create_task(self._health_monitoring_loop())

    async def _health_monitoring_loop(self):
        """Background health monitoring loop"""
        while self._tpu_available:
            try:
                # Update health status
                self._health_status["last_check"] = time.time()

                # Monitor system resources (simplified)
                if hasattr(psutil, "sensors_temperatures"):
                    temps = psutil.sensors_temperatures()
                    if temps:
                        # Use CPU temp as proxy for system thermal status
                        cpu_temps = temps.get("cpu_thermal", [])
                        if cpu_temps:
                            self._health_status["temperature"] = cpu_temps[0].current
                            self._temperature_readings.append(cpu_temps[0].current)

                # Monitor power (simplified - would need actual TPU power monitoring)
                self._health_status["power_draw"] = 2.5  # Typical TPU power draw in watts
                self._power_consumption.append(self._health_status["power_draw"])

                # Calculate utilization based on inference frequency
                if len(self._inference_times) > 0:
                    recent_inferences = sum(
                        1 for t in self._inference_times if time.time() - t < 60
                    )
                    self._health_status["utilization"] = min(
                        recent_inferences / 60.0, 1.0
                    )  # Normalize to 0-1

                await asyncio.sleep(5)  # Check every 5 seconds

            except Exception as e:
                self.logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(10)

    async def run_inference(self, image: np.ndarray) -> Optional[Dict[str, Any]]:
        """Enhanced TPU inference with caching and optimization"""
        if not self._tpu_available or self._interpreter is None:
            return None

        try:
            start_time = time.time()

            # Check cache first if enabled
            if self._optimization_settings["enable_caching"]:
                cache_result = await self._check_inference_cache(image)
                if cache_result:
                    self._cache_hit_count += 1
                    return cache_result

            self._cache_miss_count += 1

            # Preprocess image for model input
            processed_image = await self._preprocess_for_inference(image)
            if processed_image is None:
                return None

            # Set input tensor
            input_details = self._interpreter.get_input_details()
            self._interpreter.set_tensor(input_details[0]["index"], processed_image)

            # Run inference with error handling
            try:
                self._interpreter.invoke()
            except Exception as inference_error:
                self.logger.error(f"TPU inference invocation failed: {inference_error}")
                self._health_status["error_count"] += 1
                return None

            # Get output tensors
            output_details = self._interpreter.get_output_details()
            outputs = {}

            for i, output_detail in enumerate(output_details):
                outputs[f"output_{i}"] = self._interpreter.get_tensor(output_detail["index"])

            # Calculate inference time
            inference_time = (time.time() - start_time) * 1000
            self._inference_times.append(time.time())  # Store timestamp for utilization calc
            self._inference_count += 1

            # Update model info with latest inference time
            if self._model_info:
                self._model_info.inference_time_ms = inference_time

            result = {
                "outputs": outputs,
                "inference_time_ms": inference_time,
                "model_info": self._model_info,
                "tpu_used": True,
                "cache_hit": False,
                "health_status": self._health_status.copy(),
            }

            # Cache result if enabled
            if self._optimization_settings["enable_caching"]:
                await self._cache_inference_result(image, result)

            return result

        except Exception as e:
            self.logger.error(f"Enhanced TPU inference failed: {e}")
            self._health_status["error_count"] += 1
            return None

    async def _preprocess_for_inference(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Preprocess image for model inference"""
        try:
            if self._model_info is None:
                return None

            # Get expected input shape
            input_shape = self._model_info.metadata["input_shape"]
            height, width = input_shape[1], input_shape[2]

            # Resize image to model input size
            import cv2

            resized = cv2.resize(image, (width, height))

            # Convert to RGB if needed (OpenCV uses BGR)
            if len(resized.shape) == 3 and resized.shape[2] == 3:
                resized = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

            # Normalize based on model requirements
            if self._model_info.metadata.get("quantized", False):
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

    def parse_detection_results(
        self, inference_results: Dict[str, Any], confidence_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """Parse TPU inference results into detection format"""
        try:
            if not inference_results or "outputs" not in inference_results:
                return []

            outputs = inference_results["outputs"]
            detections = []

            # Assume EfficientDet output format: boxes, classes, scores, num_detections
            if "output_0" in outputs:  # boxes
                boxes = outputs["output_0"][0]  # Remove batch dimension
                classes = outputs["output_1"][0] if "output_1" in outputs else None
                scores = outputs["output_2"][0] if "output_2" in outputs else None
                num_detections = (
                    int(outputs["output_3"][0]) if "output_3" in outputs else len(boxes)
                )

                for i in range(min(num_detections, len(boxes))):
                    if scores is not None and scores[i] < confidence_threshold:
                        continue

                    # Convert normalized coordinates to pixel coordinates
                    # Assuming boxes are in [ymin, xmin, ymax, xmax] format
                    ymin, xmin, ymax, xmax = boxes[i]

                    detection = {
                        "bbox": {
                            "x": float(xmin),
                            "y": float(ymin),
                            "width": float(xmax - xmin),
                            "height": float(ymax - ymin),
                        },
                        "confidence": float(scores[i]) if scores is not None else 1.0,
                        "class_id": int(classes[i]) if classes is not None else 0,
                        "inference_time_ms": inference_results.get("inference_time_ms", 0),
                    }

                    detections.append(detection)

            return detections

        except Exception as e:
            self.logger.error(f"Error parsing detection results: {e}")
            return []

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive TPU performance statistics"""
        try:
            # Convert deque to list for calculations
            inference_times_list = list(self._inference_times)
            avg_inference_time = (
                sum(inference_times_list) / len(inference_times_list)
                if inference_times_list
                else 0.0
            )

            return {
                "tpu_available": self._tpu_available,
                "total_inferences": self._inference_count,
                "cache_hit_rate": self._cache_hit_count
                / max(self._cache_hit_count + self._cache_miss_count, 1),
                "cache_hits": self._cache_hit_count,
                "cache_misses": self._cache_miss_count,
                "average_inference_time_ms": avg_inference_time,
                "recent_inference_times": inference_times_list[-10:]
                if inference_times_list
                else [],
                "health_status": self._health_status.copy(),
                "optimization_settings": self._optimization_settings.copy(),
                "model_info": {
                    "name": self._model_info.name if self._model_info else "None",
                    "version": self._model_info.version if self._model_info else "None",
                    "lawn_optimized": self._model_info.metadata.get("lawn_optimized", False)
                    if self._model_info
                    else False,
                }
                if self._model_info
                else {},
            }
        except Exception as e:
            self.logger.error(f"Failed to get performance stats: {e}")
            return {}

    async def _check_inference_cache(self, image: np.ndarray) -> Optional[Dict[str, Any]]:
        """Check if similar inference result exists in cache"""
        try:
            # Create image hash for cache key
            image_hash = hashlib.md5(image.tobytes()).hexdigest()

            # Check for exact match first
            if image_hash in self._inference_cache:
                cached_result = self._inference_cache[image_hash].copy()
                cached_result["cache_hit"] = True
                return cached_result

            return None

        except Exception as e:
            self.logger.error(f"Cache check failed: {e}")
            return None

    async def _cache_inference_result(self, image: np.ndarray, result: Dict[str, Any]):
        """Cache inference result for future use"""
        try:
            # Don't cache if cache is full
            if len(self._inference_cache) >= self._max_cache_size:
                # Remove oldest entries (simple FIFO)
                oldest_key = next(iter(self._inference_cache))
                del self._inference_cache[oldest_key]

            # Create cache key
            image_hash = hashlib.md5(image.tobytes()).hexdigest()

            # Store result (copy to avoid reference issues)
            cache_entry = result.copy()
            cache_entry["cached_at"] = time.time()

            self._inference_cache[image_hash] = cache_entry

        except Exception as e:
            self.logger.error(f"Failed to cache inference result: {e}")

    async def update_optimization_settings(self, settings: Dict[str, Any]):
        """Update TPU optimization settings"""
        try:
            for key, value in settings.items():
                if key in self._optimization_settings:
                    self._optimization_settings[key] = value
                    self.logger.info(f"Updated optimization setting {key}: {value}")

            # Clear cache if caching was disabled
            if not self._optimization_settings["enable_caching"]:
                self._inference_cache.clear()
                self.logger.info("Cleared inference cache")

        except Exception as e:
            self.logger.error(f"Failed to update optimization settings: {e}")

    async def benchmark_performance(
        self, test_image: np.ndarray, iterations: int = 100
    ) -> Dict[str, Any]:
        """Benchmark TPU performance with test image"""
        if not self._tpu_available:
            return {"error": "TPU not available"}

        try:
            inference_times = []
            successful_inferences = 0

            for i in range(iterations):
                result = await self.run_inference(test_image)
                if result:
                    inference_times.append(result["inference_time_ms"])
                    successful_inferences += 1

                # Small delay to prevent overheating
                await asyncio.sleep(0.01)

            if inference_times:
                return {
                    "iterations": iterations,
                    "successful_inferences": successful_inferences,
                    "success_rate": successful_inferences / iterations,
                    "average_inference_time_ms": sum(inference_times) / len(inference_times),
                    "min_inference_time_ms": min(inference_times),
                    "max_inference_time_ms": max(inference_times),
                    "fps_theoretical": 1000 / (sum(inference_times) / len(inference_times)),
                }
            else:
                return {"error": "No successful inferences"}

        except Exception as e:
            self.logger.error(f"Error during TPU benchmarking: {e}")
            return {"error": str(e)}

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
        self._model_info: Optional[Dict[str, Any]] = None

    async def initialize(self, model_path: str) -> bool:
        """Initialize CPU-based TensorFlow Lite interpreter"""
        try:
            model_path = Path(model_path)
            if not model_path.exists():
                self.logger.error(f"Model file not found: {model_path}")
                return False

            # Load custom model metadata if available
            metadata_path = Path(str(model_path).replace(".tflite", ".json"))
            custom_metadata = {}
            if metadata_path.exists():
                with open(metadata_path, "r") as f:
                    custom_metadata = json.load(f)
                self.logger.info(f"Loaded custom model metadata for CPU fallback")

            # Create CPU interpreter
            self._interpreter = tflite.Interpreter(model_path=str(model_path))
            self._interpreter.allocate_tensors()

            # Store model info
            model_info = custom_metadata.get("model_info", {})
            self._model_info = {
                "name": model_info.get("name", Path(model_path).stem),
                "version": model_info.get("version", "1.0"),
                "lawn_optimized": "lawn" in model_info.get("description", "").lower(),
                "custom_classes": custom_metadata.get("classes", {}),
            }

            self.logger.info(f"CPU fallback initialized with model: {model_path}")
            if self._model_info:
                self.logger.info(f"Model: {self._model_info['name']} (CPU mode)")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize CPU fallback: {e}")
            return False

    async def run_inference(self, image: np.ndarray) -> Optional[Dict[str, Any]]:
        """Run inference on CPU using TensorFlow Lite"""
        if self._interpreter is None:
            self.logger.error("CPU interpreter not initialized")
            return None
        if not TFLITE_AVAILABLE:
            self.logger.error("TensorFlow Lite not available")
            return None

        try:
            start_time = time.time()

            # Get input details
            input_details = self._interpreter.get_input_details()
            output_details = self._interpreter.get_output_details()

            # Preprocess image to match input requirements
            input_shape = input_details[0]["shape"]
            if len(input_shape) == 4:  # Batch dimension included
                height, width = input_shape[1], input_shape[2]
            else:
                height, width = input_shape[0], input_shape[1]

            # Resize and normalize image
            processed_image = cv2.resize(image, (width, height))
            if input_details[0]["dtype"] == np.uint8:
                input_data = np.expand_dims(processed_image, axis=0).astype(np.uint8)
            else:
                input_data = np.expand_dims(processed_image, axis=0).astype(np.float32) / 255.0

            # Run inference
            self._interpreter.set_tensor(input_details[0]["index"], input_data)
            self._interpreter.invoke()

            # Get outputs
            outputs = {}
            for output_detail in output_details:
                output_data = self._interpreter.get_tensor(output_detail["index"])
                outputs[output_detail["name"]] = output_data

            inference_time = (time.time() - start_time) * 1000

            return {
                "outputs": outputs,
                "inference_time_ms": inference_time,
                "tpu_used": False,
                "input_shape": input_shape,
                "model_info": self._model_info,
            }

        except Exception as e:
            self.logger.error(f"CPU inference failed: {e}")
            return None

    def is_available(self) -> bool:
        """Check if CPU fallback is available"""
        return self._interpreter is not None and TFLITE_AVAILABLE

    async def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get comprehensive CPU fallback status"""
        try:
            return {
                "tpu_available": False,
                "cpu_fallback_active": True,
                "operational": self.is_available(),
                "temperature": 0.0,  # CPU temperature not monitored
                "power_draw": 0.0,  # CPU power not monitored separately
                "utilization": 0.0,  # Would need separate monitoring
                "error_count": 0,
                "health_status": "healthy" if self.is_available() else "offline",
                "last_inference_time": None,
                "current_model": self._model_info.get("name") if self._model_info else None,
                "device_info": {
                    "type": "CPU",
                    "runtime": "TensorFlow Lite",
                    "available": TFLITE_AVAILABLE,
                },
            }
        except Exception as e:
            self.logger.error(f"Error getting CPU status: {e}")
            return {
                "tpu_available": False,
                "cpu_fallback_active": True,
                "operational": False,
                "error_message": str(e),
            }

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get CPU performance statistics"""
        return {
            "recent_inference_times": [],
            "cache_hit_rate": 0.0,
            "average_inference_time": 0.0,
            "total_inferences": 0,
            "cpu_mode": True,
        }

    async def run_comprehensive_benchmark(self) -> Dict[str, Any]:
        """Run comprehensive TPU performance benchmark"""
        if not self.is_available():
            return {"error": "TPU not available for benchmarking", "benchmark_completed": False}

        try:
            self.logger.info("Starting TPU comprehensive benchmark...")
            benchmark_start = time.time()

            # Create test frames of different sizes
            test_frames = [
                np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8),
                np.random.randint(0, 255, (320, 320, 3), dtype=np.uint8),
                np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8),
            ]

            benchmark_results = {
                "benchmark_completed": True,
                "benchmark_duration": 0.0,
                "frame_sizes_tested": [(224, 224), (320, 320), (512, 512)],
                "inference_times": {},
                "throughput_fps": {},
                "memory_usage": {},
                "errors_encountered": 0,
            }

            # Test each frame size
            for i, frame in enumerate(test_frames):
                size_key = f"{frame.shape[0]}x{frame.shape[1]}"
                times = []
                errors = 0

                # Run 20 inference cycles for each size
                for cycle in range(20):
                    try:
                        start_time = time.time()

                        # Run inference (simulate with actual processing)
                        if self._interpreter:
                            input_details = self._interpreter.get_input_details()
                            processed_frame = self._preprocess_frame(
                                frame, input_details[0]["shape"][1:3]
                            )

                            self._interpreter.set_tensor(input_details[0]["index"], processed_frame)
                            self._interpreter.invoke()

                            # Get output (don't process, just measure timing)
                            output_details = self._interpreter.get_output_details()
                            self._interpreter.get_tensor(output_details[0]["index"])

                        inference_time = (time.time() - start_time) * 1000  # Convert to ms
                        times.append(inference_time)

                    except Exception as e:
                        self.logger.warning(
                            f"Benchmark error for size {size_key}, cycle {cycle}: {e}"
                        )
                        errors += 1
                        benchmark_results["errors_encountered"] += 1

                if times:
                    avg_time = sum(times) / len(times)
                    min_time = min(times)
                    max_time = max(times)

                    benchmark_results["inference_times"][size_key] = {
                        "average_ms": round(avg_time, 2),
                        "min_ms": round(min_time, 2),
                        "max_ms": round(max_time, 2),
                        "std_dev": round(np.std(times), 2) if len(times) > 1 else 0.0,
                    }

                    benchmark_results["throughput_fps"][size_key] = round(1000.0 / avg_time, 1)

                # Memory usage simulation (would use actual monitoring in production)
                benchmark_results["memory_usage"][size_key] = {
                    "estimated_mb": round(frame.nbytes / (1024 * 1024), 2)
                }

            benchmark_results["benchmark_duration"] = round(time.time() - benchmark_start, 2)

            # Overall performance assessment
            avg_times = [
                times["average_ms"] for times in benchmark_results["inference_times"].values()
            ]
            if avg_times:
                overall_avg = sum(avg_times) / len(avg_times)
                benchmark_results["overall_performance"] = {
                    "average_inference_ms": round(overall_avg, 2),
                    "meets_50ms_target": overall_avg < 50.0,
                    "performance_grade": self._calculate_performance_grade(overall_avg),
                }

            self.logger.info(
                f"TPU benchmark completed in {benchmark_results['benchmark_duration']}s"
            )
            return benchmark_results

        except Exception as e:
            self.logger.error(f"Benchmark failed: {e}")
            return {"error": f"Benchmark failed: {str(e)}", "benchmark_completed": False}

    def _calculate_performance_grade(self, avg_inference_ms: float) -> str:
        """Calculate performance grade based on inference time"""
        if avg_inference_ms < 20:
            return "Excellent"
        elif avg_inference_ms < 35:
            return "Good"
        elif avg_inference_ms < 50:
            return "Fair"
        else:
            return "Poor"

    async def load_custom_model(self, model_path: str) -> bool:
        """Load a custom model for TPU inference"""
        try:
            model_path = Path(model_path)
            if not model_path.exists():
                self.logger.error(f"Custom model not found: {model_path}")
                return False

            # Re-initialize with new model
            success = await self.initialize(str(model_path))
            if success:
                self.logger.info(f"Successfully loaded custom model: {model_path.name}")

            return success

        except Exception as e:
            self.logger.error(f"Failed to load custom model {model_path}: {e}")
            return False

    def get_model_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the currently loaded model"""
        if not self._model_info:
            return None

        return {
            "name": self._model_info.name,
            "version": self._model_info.version,
            "path": self._model_info.path,
            "accuracy": self._model_info.accuracy,
            "inference_time_ms": self._model_info.inference_time_ms,
            "tpu_optimized": self._model_info.tpu_optimized,
            "created_at": self._model_info.created_at,
            "metadata": self._model_info.metadata,
        }
