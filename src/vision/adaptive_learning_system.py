"""
Adaptive learning system for continuous improvement of ML obstacle detection
Implements online learning and environment-specific adaptation
"""

import asyncio
import logging
import numpy as np
import json
import pickle
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple, Set
from pathlib import Path
from collections import deque, defaultdict
from dataclasses import dataclass, asdict
from enum import Enum

from .ml_obstacle_detector import MLDetectionResult
from .data_structures import VisionFrame, SafetyLevel
from ..communication import MQTTClient, MessageProtocol


class FeedbackType(Enum):
    """Types of feedback for learning"""
    CORRECT_DETECTION = "correct_detection"
    FALSE_POSITIVE = "false_positive"
    MISSED_DETECTION = "missed_detection"
    USER_CORRECTION = "user_correction"
    ENVIRONMENT_CHANGE = "environment_change"


@dataclass
class LearningExample:
    """A single learning example"""
    example_id: str
    timestamp: datetime
    object_type: str
    confidence: float
    bounding_box: Dict[str, int]
    features: Dict[str, float]
    ground_truth: Optional[str]
    feedback_type: FeedbackType
    environment_context: Dict[str, Any]
    user_feedback: Optional[str] = None


@dataclass
class ModelPerformanceMetrics:
    """Performance metrics for model evaluation"""
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    false_positive_rate: float
    false_negative_rate: float
    confidence_calibration: float
    environment_specific_scores: Dict[str, float]


class AdaptiveLearningSystem:
    """Adaptive learning system for ML obstacle detection"""
    
    def __init__(self, mqtt_client: MQTTClient, data_dir: Path):
        self.logger = logging.getLogger(__name__)
        self.mqtt_client = mqtt_client
        self.data_dir = Path(data_dir)
        
        # Create directories
        self.training_data_dir = self.data_dir / "training_data"
        self.models_dir = self.data_dir / "adaptive_models"
        self.metrics_dir = self.data_dir / "metrics"
        
        for dir_path in [self.training_data_dir, self.models_dir, self.metrics_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # Learning configuration
        self.learning_config = {
            "min_examples_for_training": 100,
            "retraining_threshold": 500,
            "adaptation_threshold": 0.1,
            "confidence_adjustment_rate": 0.05,
            "environment_context_weight": 0.3,
            "user_feedback_weight": 0.5,
            "temporal_decay_factor": 0.95,
            "max_training_examples": 10000
        }
        
        # Learning buffers
        self.learning_examples: deque = deque(maxlen=self.learning_config["max_training_examples"])
        self.feedback_buffer: deque = deque(maxlen=1000)
        self.environment_contexts: Dict[str, Dict] = {}
        
        # Performance tracking
        self.model_metrics: Dict[str, ModelPerformanceMetrics] = {}
        self.adaptation_history: List[Dict] = []
        self.confidence_adjustments: Dict[str, float] = defaultdict(float)
        
        # Environment detection
        self.current_environment: Dict[str, Any] = {}
        self.environment_classifier = None
        self.environment_history: deque = deque(maxlen=100)
        
        # Online learning state
        self.online_learning_enabled = True
        self.adaptation_in_progress = False
        self.last_adaptation_time: Optional[datetime] = None
        
        # Model versioning
        self.current_model_version = "1.0.0"
        self.model_update_queue: deque = deque(maxlen=10)
        
        # User interaction
        self.user_feedback_weight_decay = 0.9
        self.user_expertise_scores: Dict[str, float] = defaultdict(lambda: 0.5)
        
        # Tasks
        self._learning_task: Optional[asyncio.Task] = None
        self._adaptation_task: Optional[asyncio.Task] = None
        self._running = False
        
    async def start(self):
        """Start the adaptive learning system"""
        try:
            self.logger.info("Starting adaptive learning system")
            
            # Load existing data
            await self._load_existing_data()
            
            # Initialize environment classifier
            await self._initialize_environment_classifier()
            
            # Subscribe to feedback topics
            await self._subscribe_to_feedback()
            
            # Start learning tasks
            self._running = True
            self._learning_task = asyncio.create_task(self._learning_loop())
            self._adaptation_task = asyncio.create_task(self._adaptation_loop())
            
            self.logger.info("Adaptive learning system started")
            
        except Exception as e:
            self.logger.error(f"Error starting adaptive learning system: {e}")
    
    async def stop(self):
        """Stop the adaptive learning system"""
        try:
            self.logger.info("Stopping adaptive learning system")
            
            self._running = False
            
            # Cancel tasks
            for task in [self._learning_task, self._adaptation_task]:
                if task:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            
            # Save current state
            await self._save_learning_state()
            
            self.logger.info("Adaptive learning system stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping adaptive learning system: {e}")
    
    async def _load_existing_data(self):
        """Load existing learning data and models"""
        try:
            # Load learning examples
            examples_file = self.training_data_dir / "learning_examples.pkl"
            if examples_file.exists():
                with open(examples_file, 'rb') as f:
                    stored_examples = pickle.load(f)
                    self.learning_examples.extend(stored_examples)
                    self.logger.info(f"Loaded {len(stored_examples)} learning examples")
            
            # Load environment contexts
            contexts_file = self.training_data_dir / "environment_contexts.json"
            if contexts_file.exists():
                with open(contexts_file, 'r') as f:
                    self.environment_contexts = json.load(f)
                    self.logger.info(f"Loaded {len(self.environment_contexts)} environment contexts")
            
            # Load model metrics
            metrics_file = self.metrics_dir / "model_metrics.json"
            if metrics_file.exists():
                with open(metrics_file, 'r') as f:
                    metrics_data = json.load(f)
                    for model_name, metrics in metrics_data.items():
                        self.model_metrics[model_name] = ModelPerformanceMetrics(**metrics)
                    self.logger.info(f"Loaded metrics for {len(self.model_metrics)} models")
            
        except Exception as e:
            self.logger.error(f"Error loading existing data: {e}")
    
    async def _save_learning_state(self):
        """Save current learning state"""
        try:
            # Save learning examples
            examples_file = self.training_data_dir / "learning_examples.pkl"
            with open(examples_file, 'wb') as f:
                pickle.dump(list(self.learning_examples), f)
            
            # Save environment contexts
            contexts_file = self.training_data_dir / "environment_contexts.json"
            with open(contexts_file, 'w') as f:
                json.dump(self.environment_contexts, f, indent=2)
            
            # Save model metrics
            metrics_file = self.metrics_dir / "model_metrics.json"
            metrics_data = {
                name: asdict(metrics) for name, metrics in self.model_metrics.items()
            }
            with open(metrics_file, 'w') as f:
                json.dump(metrics_data, f, indent=2)
            
            self.logger.info("Learning state saved successfully")
            
        except Exception as e:
            self.logger.error(f"Error saving learning state: {e}")
    
    async def _initialize_environment_classifier(self):
        """Initialize environment classification"""
        try:
            # Simple environment classification based on lighting, weather, etc.
            self.environment_classifier = {
                "lighting_levels": {"low": 0.3, "medium": 0.6, "high": 1.0},
                "weather_conditions": {"sunny": 1.0, "cloudy": 0.7, "rainy": 0.3},
                "grass_conditions": {"dry": 1.0, "wet": 0.5, "overgrown": 0.3},
                "obstacle_density": {"low": 1.0, "medium": 0.7, "high": 0.4}
            }
            
            self.logger.info("Environment classifier initialized")
            
        except Exception as e:
            self.logger.error(f"Error initializing environment classifier: {e}")
    
    async def _subscribe_to_feedback(self):
        """Subscribe to feedback topics"""
        try:
            feedback_topics = [
                "lawnberry/learning/user_feedback",
                "lawnberry/learning/detection_feedback",
                "lawnberry/learning/environment_change",
                "lawnberry/safety/false_positive_report",
                "lawnberry/safety/missed_detection_report"
            ]
            
            for topic in feedback_topics:
                await self.mqtt_client.subscribe(topic, self._handle_feedback)
            
        except Exception as e:
            self.logger.error(f"Error subscribing to feedback topics: {e}")
    
    async def _handle_feedback(self, topic: str, message: MessageProtocol):
        """Handle incoming feedback"""
        try:
            payload = message.payload
            feedback_type = self._determine_feedback_type(topic, payload)
            
            # Create learning example from feedback
            learning_example = await self._create_learning_example(feedback_type, payload)
            if learning_example:
                self.learning_examples.append(learning_example)
                self.feedback_buffer.append((topic, payload, datetime.now()))
                
                self.logger.info(f"Received {feedback_type.value} feedback")
                
                # Check if we need immediate adaptation
                if await self._should_trigger_immediate_adaptation(feedback_type, payload):
                    await self._trigger_adaptation()
                    
        except Exception as e:
            self.logger.error(f"Error handling feedback: {e}")
    
    def _determine_feedback_type(self, topic: str, payload: Dict) -> FeedbackType:
        """Determine feedback type from topic and payload"""
        if "user_feedback" in topic:
            return FeedbackType.USER_CORRECTION
        elif "false_positive" in topic:
            return FeedbackType.FALSE_POSITIVE
        elif "missed_detection" in topic:
            return FeedbackType.MISSED_DETECTION
        elif "environment_change" in topic:
            return FeedbackType.ENVIRONMENT_CHANGE
        else:
            return FeedbackType.CORRECT_DETECTION
    
    async def _create_learning_example(self, feedback_type: FeedbackType, 
                                     payload: Dict) -> Optional[LearningExample]:
        """Create a learning example from feedback"""
        try:
            # Extract basic information
            detection_id = payload.get("detection_id", f"feedback_{datetime.now().isoformat()}")
            object_type = payload.get("object_type", "unknown")
            confidence = payload.get("confidence", 0.0)
            
            # Extract or create bounding box
            bounding_box = payload.get("bounding_box", {
                "x1": 0, "y1": 0, "x2": 100, "y2": 100
            })
            
            # Extract features (would be more sophisticated in real implementation)
            features = await self._extract_features(payload)
            
            # Get current environment context
            environment_context = await self._get_current_environment_context()
            
            # Determine ground truth
            ground_truth = None
            if feedback_type == FeedbackType.USER_CORRECTION:
                ground_truth = payload.get("correct_type", object_type)
            elif feedback_type == FeedbackType.FALSE_POSITIVE:
                ground_truth = "false_positive"
            
            learning_example = LearningExample(
                example_id=detection_id,
                timestamp=datetime.now(),
                object_type=object_type,
                confidence=confidence,
                bounding_box=bounding_box,
                features=features,
                ground_truth=ground_truth,
                feedback_type=feedback_type,
                environment_context=environment_context,
                user_feedback=payload.get("user_comment")
            )
            
            return learning_example
            
        except Exception as e:
            self.logger.error(f"Error creating learning example: {e}")
            return None
    
    async def _extract_features(self, payload: Dict) -> Dict[str, float]:
        """Extract features for learning"""
        try:
            # Basic feature extraction (would be more sophisticated in real implementation)
            features = {
                "confidence": payload.get("confidence", 0.0),
                "distance": payload.get("distance", 1.0),
                "size_ratio": payload.get("size_ratio", 0.1),
                "motion_magnitude": 0.0,
                "lighting_condition": self.current_environment.get("lighting", 0.5),
                "weather_score": self.current_environment.get("weather", 1.0)
            }
            
            # Add motion features if available
            motion_vector = payload.get("motion_vector")
            if motion_vector:
                features["motion_magnitude"] = np.linalg.norm(motion_vector)
                features["motion_x"] = motion_vector[0]
                features["motion_y"] = motion_vector[1]
            
            return features
            
        except Exception as e:
            self.logger.error(f"Error extracting features: {e}")
            return {}
    
    async def _get_current_environment_context(self) -> Dict[str, Any]:
        """Get current environment context"""
        try:
            # Get latest environment data (would integrate with sensors in real implementation)
            context = {
                "timestamp": datetime.now().isoformat(),
                "lighting_level": self.current_environment.get("lighting", 0.7),
                "weather_condition": self.current_environment.get("weather", "sunny"),
                "grass_condition": self.current_environment.get("grass", "dry"),
                "obstacle_density": self.current_environment.get("obstacles", "low"),
                "time_of_day": datetime.now().hour,
                "season": self._get_season()
            }
            
            return context
            
        except Exception as e:
            self.logger.error(f"Error getting environment context: {e}")
            return {}
    
    def _get_season(self) -> str:
        """Get current season"""
        month = datetime.now().month
        if month in [12, 1, 2]:
            return "winter"
        elif month in [3, 4, 5]:
            return "spring"
        elif month in [6, 7, 8]:
            return "summer"
        else:
            return "autumn"
    
    async def _should_trigger_immediate_adaptation(self, feedback_type: FeedbackType, 
                                                 payload: Dict) -> bool:
        """Determine if immediate adaptation is needed"""
        try:
            # Trigger immediate adaptation for critical feedback
            if feedback_type in [FeedbackType.FALSE_POSITIVE, FeedbackType.MISSED_DETECTION]:
                # Check if this is a recurring issue
                similar_feedback_count = sum(
                    1 for ex in list(self.learning_examples)[-50:]  # Last 50 examples
                    if (ex.feedback_type == feedback_type and 
                        ex.object_type == payload.get("object_type"))
                )
                
                if similar_feedback_count >= 3:
                    return True
            
            # Trigger for user corrections with high confidence
            if (feedback_type == FeedbackType.USER_CORRECTION and 
                payload.get("user_confidence", 0.0) > 0.8):
                return True
            
            # Trigger for environment changes
            if feedback_type == FeedbackType.ENVIRONMENT_CHANGE:
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking adaptation trigger: {e}")
            return False
    
    async def _learning_loop(self):
        """Main learning loop"""
        while self._running:
            try:
                # Check if we have enough examples for training
                if len(self.learning_examples) >= self.learning_config["min_examples_for_training"]:
                    await self._update_model_performance()
                    await self._adjust_confidence_thresholds()
                
                # Save state periodically
                if len(self.learning_examples) % 100 == 0:
                    await self._save_learning_state()
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                self.logger.error(f"Error in learning loop: {e}")
                await asyncio.sleep(10)
    
    async def _adaptation_loop(self):
        """Adaptation loop for environment-specific adjustments"""
        while self._running:
            try:
                # Monitor environment changes
                await self._monitor_environment_changes()
                
                # Check if adaptation is needed
                if await self._should_adapt_to_environment():
                    await self._adapt_to_environment()
                
                # Update confidence adjustments
                await self._update_confidence_adjustments()
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Error in adaptation loop: {e}")
                await asyncio.sleep(30)
    
    async def _update_model_performance(self):
        """Update model performance metrics"""
        try:
            # Calculate performance metrics from recent examples
            recent_examples = list(self.learning_examples)[-1000:]  # Last 1000 examples
            
            # Group by object type
            performance_by_type = defaultdict(list)
            for example in recent_examples:
                if example.ground_truth is not None:
                    performance_by_type[example.object_type].append(example)
            
            # Calculate metrics for each object type
            for object_type, examples in performance_by_type.items():
                metrics = await self._calculate_performance_metrics(examples)
                self.model_metrics[object_type] = metrics
            
            # Log performance summary
            if self.model_metrics:
                avg_accuracy = np.mean([m.accuracy for m in self.model_metrics.values()])
                avg_precision = np.mean([m.precision for m in self.model_metrics.values()])
                avg_recall = np.mean([m.recall for m in self.model_metrics.values()])
                
                self.logger.info(f"Model performance - Accuracy: {avg_accuracy:.3f}, "
                               f"Precision: {avg_precision:.3f}, Recall: {avg_recall:.3f}")
                
        except Exception as e:
            self.logger.error(f"Error updating model performance: {e}")
    
    async def _calculate_performance_metrics(self, examples: List[LearningExample]) -> ModelPerformanceMetrics:
        """Calculate performance metrics for a set of examples"""
        try:
            if not examples:
                return ModelPerformanceMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {})
            
            # Calculate basic metrics
            true_positives = sum(1 for ex in examples if ex.feedback_type == FeedbackType.CORRECT_DETECTION)
            false_positives = sum(1 for ex in examples if ex.feedback_type == FeedbackType.FALSE_POSITIVE)
            false_negatives = sum(1 for ex in examples if ex.feedback_type == FeedbackType.MISSED_DETECTION)
            
            total_predictions = len(examples)
            total_actual_positives = true_positives + false_negatives
            
            # Calculate metrics
            accuracy = true_positives / total_predictions if total_predictions > 0 else 0.0
            precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0
            recall = true_positives / total_actual_positives if total_actual_positives > 0 else 0.0
            f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
            
            false_positive_rate = false_positives / total_predictions if total_predictions > 0 else 0.0
            false_negative_rate = false_negatives / total_actual_positives if total_actual_positives > 0 else 0.0
            
            # Calculate confidence calibration
            confidence_calibration = await self._calculate_confidence_calibration(examples)
            
            # Calculate environment-specific scores
            environment_scores = await self._calculate_environment_specific_scores(examples)
            
            return ModelPerformanceMetrics(
                accuracy=accuracy,
                precision=precision,
                recall=recall,
                f1_score=f1_score,
                false_positive_rate=false_positive_rate,
                false_negative_rate=false_negative_rate,
                confidence_calibration=confidence_calibration,
                environment_specific_scores=environment_scores
            )
            
        except Exception as e:
            self.logger.error(f"Error calculating performance metrics: {e}")
            return ModelPerformanceMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, {})
    
    async def _calculate_confidence_calibration(self, examples: List[LearningExample]) -> float:
        """Calculate how well confidence scores match actual accuracy"""
        try:
            if not examples:
                return 0.0
            
            # Group examples by confidence bins
            confidence_bins = np.linspace(0, 1, 11)  # 10 bins
            bin_accuracy = []
            bin_confidence = []
            
            for i in range(len(confidence_bins) - 1):
                bin_min, bin_max = confidence_bins[i], confidence_bins[i + 1]
                bin_examples = [ex for ex in examples 
                              if bin_min <= ex.confidence < bin_max]
                
                if bin_examples:
                    bin_acc = sum(1 for ex in bin_examples 
                                if ex.feedback_type == FeedbackType.CORRECT_DETECTION) / len(bin_examples)
                    bin_conf = np.mean([ex.confidence for ex in bin_examples])
                    
                    bin_accuracy.append(bin_acc)
                    bin_confidence.append(bin_conf)
            
            if not bin_accuracy:
                return 0.0
            
            # Calculate Expected Calibration Error (ECE)
            ece = np.mean([abs(acc - conf) for acc, conf in zip(bin_accuracy, bin_confidence)])
            return 1.0 - ece  # Return calibration quality (higher is better)
            
        except Exception as e:
            self.logger.error(f"Error calculating confidence calibration: {e}")
            return 0.0
    
    async def _calculate_environment_specific_scores(self, examples: List[LearningExample]) -> Dict[str, float]:
        """Calculate performance scores for different environments"""
        try:
            environment_scores = {}
            
            # Group by environment conditions
            env_groups = defaultdict(list)
            for example in examples:
                env_context = example.environment_context
                lighting = env_context.get("lighting_level", "medium")
                weather = env_context.get("weather_condition", "sunny")
                env_key = f"{lighting}_{weather}"
                env_groups[env_key].append(example)
            
            # Calculate accuracy for each environment
            for env_key, env_examples in env_groups.items():
                if env_examples:
                    correct = sum(1 for ex in env_examples 
                                if ex.feedback_type == FeedbackType.CORRECT_DETECTION)
                    accuracy = correct / len(env_examples)
                    environment_scores[env_key] = accuracy
            
            return environment_scores
            
        except Exception as e:
            self.logger.error(f"Error calculating environment-specific scores: {e}")
            return {}
    
    async def _adjust_confidence_thresholds(self):
        """Adjust confidence thresholds based on performance"""
        try:
            for object_type, metrics in self.model_metrics.items():
                current_adjustment = self.confidence_adjustments[object_type]
                
                # Adjust based on false positive rate
                if metrics.false_positive_rate > 0.05:  # Target < 5% FP rate
                    # Increase threshold to reduce false positives
                    adjustment = self.learning_config["confidence_adjustment_rate"]
                    self.confidence_adjustments[object_type] = min(0.3, current_adjustment + adjustment)
                elif metrics.false_positive_rate < 0.02:  # Very low FP rate
                    # Decrease threshold to catch more true positives
                    adjustment = -self.learning_config["confidence_adjustment_rate"] * 0.5
                    self.confidence_adjustments[object_type] = max(-0.3, current_adjustment + adjustment)
                
                # Log significant adjustments
                if abs(self.confidence_adjustments[object_type] - current_adjustment) > 0.01:
                    self.logger.info(f"Adjusted confidence threshold for {object_type}: "
                                   f"{current_adjustment:.3f} -> {self.confidence_adjustments[object_type]:.3f}")
                    
        except Exception as e:
            self.logger.error(f"Error adjusting confidence thresholds: {e}")
    
    async def _monitor_environment_changes(self):
        """Monitor for significant environment changes"""
        try:
            # Get current environment context
            current_context = await self._get_current_environment_context()
            
            # Compare with recent history
            if self.environment_history:
                recent_context = self.environment_history[-1]
                
                # Check for significant changes
                changes = {}
                for key in current_context:
                    if key in recent_context:
                        if isinstance(current_context[key], (int, float)):
                            diff = abs(current_context[key] - recent_context[key])
                            if diff > 0.2:  # 20% change threshold
                                changes[key] = diff
                        elif current_context[key] != recent_context[key]:
                            changes[key] = "category_change"
                
                if changes:
                    self.logger.info(f"Environment changes detected: {changes}")
                    await self._handle_environment_change(changes)
            
            # Update history
            self.environment_history.append(current_context)
            self.current_environment = current_context
            
        except Exception as e:
            self.logger.error(f"Error monitoring environment changes: {e}")
    
    async def _handle_environment_change(self, changes: Dict[str, Any]):
        """Handle detected environment changes"""
        try:
            # Create environment change feedback
            feedback_payload = {
                "changes": changes,
                "timestamp": datetime.now().isoformat(),
                "current_environment": self.current_environment
            }
            
            # Add to learning examples
            learning_example = await self._create_learning_example(
                FeedbackType.ENVIRONMENT_CHANGE, 
                feedback_payload
            )
            if learning_example:
                self.learning_examples.append(learning_example)
            
            # Trigger adaptation if significant change
            significant_changes = sum(1 for change in changes.values() 
                                    if isinstance(change, (int, float)) and change > 0.3)
            if significant_changes >= 2:
                await self._trigger_adaptation()
                
        except Exception as e:
            self.logger.error(f"Error handling environment change: {e}")
    
    async def _should_adapt_to_environment(self) -> bool:
        """Check if environment adaptation is needed"""
        try:
            if self.adaptation_in_progress:
                return False
            
            # Check time since last adaptation
            if self.last_adaptation_time:
                time_since_adaptation = (datetime.now() - self.last_adaptation_time).total_seconds()
                if time_since_adaptation < 300:  # 5 minutes minimum between adaptations
                    return False
            
            # Check if we have enough environment-specific data
            recent_examples = list(self.learning_examples)[-100:]
            
            # Group by environment
            env_performance = defaultdict(list)
            for example in recent_examples:
                env_key = self._get_environment_key(example.environment_context)
                env_performance[env_key].append(example)
            
            # Check for poor performance in current environment
            current_env_key = self._get_environment_key(self.current_environment)
            if current_env_key in env_performance:
                env_examples = env_performance[current_env_key]
                if len(env_examples) >= 10:  # Minimum examples for reliable assessment
                    false_positives = sum(1 for ex in env_examples 
                                        if ex.feedback_type == FeedbackType.FALSE_POSITIVE)
                    fp_rate = false_positives / len(env_examples)
                    
                    if fp_rate > 0.1:  # 10% false positive rate threshold
                        return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Error checking environment adaptation need: {e}")
            return False
    
    def _get_environment_key(self, environment_context: Dict[str, Any]) -> str:
        """Get a key representing the environment context"""
        try:
            lighting = environment_context.get("lighting_level", "medium")
            weather = environment_context.get("weather_condition", "sunny")
            grass = environment_context.get("grass_condition", "dry")
            return f"{lighting}_{weather}_{grass}"
        except Exception as e:
            self.logger.error(f"Error getting environment key: {e}")
            return "unknown"
    
    async def _trigger_adaptation(self):
        """Trigger model adaptation"""
        try:
            if self.adaptation_in_progress:
                return
            
            self.adaptation_in_progress = True
            self.logger.info("Triggering model adaptation")
            
            # Perform adaptation
            await self._adapt_to_environment()
            
            self.last_adaptation_time = datetime.now()
            self.adaptation_in_progress = False
            
            # Record adaptation event
            adaptation_record = {
                "timestamp": datetime.now().isoformat(),
                "trigger": "automatic",
                "examples_used": len(self.learning_examples),
                "environment": self.current_environment.copy()
            }
            self.adaptation_history.append(adaptation_record)
            
            # Publish adaptation notification
            await self.mqtt_client.publish(
                "lawnberry/learning/adaptation_complete",
                adaptation_record
            )
            
        except Exception as e:
            self.logger.error(f"Error triggering adaptation: {e}")
            self.adaptation_in_progress = False
    
    async def _adapt_to_environment(self):
        """Adapt model to current environment"""
        try:
            # Get environment-specific examples
            current_env_key = self._get_environment_key(self.current_environment)
            env_examples = [ex for ex in self.learning_examples 
                          if self._get_environment_key(ex.environment_context) == current_env_key]
            
            if len(env_examples) < 20:
                self.logger.warning(f"Insufficient examples for environment adaptation: {len(env_examples)}")
                return
            
            # Update confidence adjustments for this environment
            await self._update_environment_specific_adjustments(env_examples)
            
            # Update model weights (simplified - would involve actual model retraining)
            await self._update_model_weights(env_examples)
            
            self.logger.info(f"Adapted to environment: {current_env_key} using {len(env_examples)} examples")
            
        except Exception as e:
            self.logger.error(f"Error adapting to environment: {e}")
    
    async def _update_environment_specific_adjustments(self, examples: List[LearningExample]):
        """Update environment-specific confidence adjustments"""
        try:
            # Calculate environment-specific performance
            object_performance = defaultdict(list)
            for example in examples:
                object_performance[example.object_type].append(example)
            
            # Adjust confidence thresholds for each object type in this environment
            for object_type, obj_examples in object_performance.items():
                false_positives = sum(1 for ex in obj_examples 
                                    if ex.feedback_type == FeedbackType.FALSE_POSITIVE)
                fp_rate = false_positives / len(obj_examples)
                
                # Calculate environment-specific adjustment
                env_adjustment_key = f"{object_type}_{self._get_environment_key(self.current_environment)}"
                
                if fp_rate > 0.05:
                    self.confidence_adjustments[env_adjustment_key] = 0.1
                elif fp_rate < 0.02:
                    self.confidence_adjustments[env_adjustment_key] = -0.05
                    
        except Exception as e:
            self.logger.error(f"Error updating environment-specific adjustments: {e}")
    
    async def _update_model_weights(self, examples: List[LearningExample]):
        """Update model weights based on examples (simplified)"""
        try:
            # In a real implementation, this would involve:
            # 1. Feature extraction from examples
            # 2. Online learning algorithm (e.g., SGD updates)
            # 3. Model weight updates
            # 4. Validation on held-out data
            
            # For now, we'll simulate by updating confidence adjustments
            self.logger.info(f"Updated model weights using {len(examples)} examples")
            
        except Exception as e:
            self.logger.error(f"Error updating model weights: {e}")
    
    async def _update_confidence_adjustments(self):
        """Update confidence adjustments based on recent performance"""
        try:
            # Apply temporal decay to adjustments
            decay_factor = self.learning_config["temporal_decay_factor"]
            
            for key in self.confidence_adjustments:
                self.confidence_adjustments[key] *= decay_factor
                
                # Remove very small adjustments
                if abs(self.confidence_adjustments[key]) < 0.01:
                    self.confidence_adjustments[key] = 0.0
                    
        except Exception as e:
            self.logger.error(f"Error updating confidence adjustments: {e}")
    
    def get_confidence_adjustment(self, object_type: str, environment_context: Optional[Dict] = None) -> float:
        """Get confidence adjustment for an object type and environment"""
        try:
            # Get base adjustment for object type
            base_adjustment = self.confidence_adjustments.get(object_type, 0.0)
            
            # Get environment-specific adjustment if context provided
            env_adjustment = 0.0
            if environment_context:
                env_key = self._get_environment_key(environment_context)
                env_adjustment_key = f"{object_type}_{env_key}"
                env_adjustment = self.confidence_adjustments.get(env_adjustment_key, 0.0)
            
            # Combine adjustments
            total_adjustment = base_adjustment + env_adjustment * self.learning_config["environment_context_weight"]
            
            return np.clip(total_adjustment, -0.5, 0.5)  # Limit adjustment range
            
        except Exception as e:
            self.logger.error(f"Error getting confidence adjustment: {e}")
            return 0.0
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """Get learning system statistics"""
        try:
            recent_examples = list(self.learning_examples)[-100:]
            
            stats = {
                "total_examples": len(self.learning_examples),
                "recent_examples": len(recent_examples),
                "environments_seen": len(set(self._get_environment_key(ex.environment_context) 
                                           for ex in recent_examples)),
                "adaptations_performed": len(self.adaptation_history),
                "last_adaptation": self.last_adaptation_time.isoformat() if self.last_adaptation_time else None,
                "adaptation_in_progress": self.adaptation_in_progress,
                "confidence_adjustments_active": sum(1 for adj in self.confidence_adjustments.values() if abs(adj) > 0.01),
                "current_environment": self.current_environment,
                "feedback_types": {
                    feedback_type.value: sum(1 for ex in recent_examples if ex.feedback_type == feedback_type)
                    for feedback_type in FeedbackType
                }
            }
            
            if self.model_metrics:
                avg_accuracy = np.mean([m.accuracy for m in self.model_metrics.values()])
                avg_f1 = np.mean([m.f1_score for m in self.model_metrics.values()])
                stats["average_accuracy"] = avg_accuracy
                stats["average_f1_score"] = avg_f1
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting learning stats: {e}")
            return {}
    
    async def add_user_feedback(self, detection_id: str, object_type: str, 
                              correct_type: Optional[str], confidence: float, 
                              user_comment: Optional[str] = None):
        """Add user feedback for a detection"""
        try:
            feedback_payload = {
                "detection_id": detection_id,
                "object_type": object_type,
                "correct_type": correct_type,
                "user_confidence": confidence,
                "user_comment": user_comment,
                "timestamp": datetime.now().isoformat()
            }
            
            # Create learning example
            learning_example = await self._create_learning_example(
                FeedbackType.USER_CORRECTION, 
                feedback_payload
            )
            
            if learning_example:
                self.learning_examples.append(learning_example)
                
                # Weight user feedback based on user expertise
                user_id = feedback_payload.get("user_id", "default")
                feedback_weight = self.user_expertise_scores[user_id] * self.learning_config["user_feedback_weight"]
                
                # Apply immediate confidence adjustment if high-confidence feedback
                if confidence > 0.8:
                    current_adj = self.confidence_adjustments.get(object_type, 0.0)
                    if correct_type == "false_positive":
                        adjustment = feedback_weight * 0.1  # Increase threshold
                    else:
                        adjustment = -feedback_weight * 0.05  # Decrease threshold
                    
                    self.confidence_adjustments[object_type] = np.clip(
                        current_adj + adjustment, -0.3, 0.3
                    )
                
                self.logger.info(f"Added user feedback for {object_type}: {correct_type}")
                
        except Exception as e:
            self.logger.error(f"Error adding user feedback: {e}")
