"""
AI-Based Pattern Optimization System
Advanced machine learning algorithms for mowing pattern optimization and continuous improvement.
"""

import asyncio
import hashlib
import json
import logging
import pickle
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ML imports
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from .pattern_generator import Boundary, PatternGenerator, PatternType, Point
from .pattern_service import PatternService


@dataclass
class PatternPerformanceMetric:
    """Performance metrics for pattern evaluation"""

    pattern_type: str
    coverage_efficiency: float
    battery_usage: float
    time_to_complete: float
    grass_quality_score: float
    terrain_adaptation_score: float
    weather_resilience: float
    user_satisfaction: float
    edge_case_handling: float
    timestamp: datetime
    yard_characteristics: Dict[str, float]
    environmental_conditions: Dict[str, float]


@dataclass
class YardCharacteristics:
    """Yard geometry and terrain analysis"""

    area: float
    shape_complexity: float  # 0-1 scale
    obstacle_density: float
    slope_variance: float
    edge_ratio: float  # perimeter to area ratio
    irregular_sections: int
    grass_type_distribution: Dict[str, float]


class OptimizationStrategy(Enum):
    """AI optimization strategies"""

    EFFICIENCY_FOCUSED = "efficiency"
    QUALITY_FOCUSED = "quality"
    BATTERY_OPTIMIZED = "battery"
    TERRAIN_ADAPTIVE = "terrain"
    WEATHER_RESILIENT = "weather"
    BALANCED = "balanced"


class AIPatternOptimizer:
    """Advanced AI-based pattern optimization system"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.pattern_generator = PatternGenerator()

        # ML Models for different optimization aspects
        self.efficiency_model = MLPRegressor(
            hidden_layer_sizes=(100, 50, 25),
            activation="relu",
            solver="adam",
            max_iter=1000,
            random_state=42,
        )

        self.battery_model = GradientBoostingRegressor(
            n_estimators=100, learning_rate=0.1, max_depth=6, random_state=42
        )

        self.terrain_model = RandomForestRegressor(n_estimators=150, max_depth=10, random_state=42)

        # Feature scalers
        self.scaler_efficiency = StandardScaler()
        self.scaler_battery = StandardScaler()
        self.scaler_terrain = StandardScaler()

        # Performance data storage
        self.performance_data: List[PatternPerformanceMetric] = []
        self.model_path = Path("data/ml_models/pattern_optimization")
        self.model_path.mkdir(parents=True, exist_ok=True)

        # Advanced pattern parameters
        self.optimization_cache = {}
        self.learning_rate = 0.01
        self.exploration_factor = 0.1

    async def initialize(self) -> bool:
        """Initialize the AI pattern optimizer"""
        try:
            self.logger.info("Initializing AI Pattern Optimizer...")

            # Load existing models if available
            await self._load_trained_models()

            # Load historical performance data
            await self._load_performance_data()

            # Initialize optimization cache
            self._initialize_optimization_cache()

            self.logger.info("AI Pattern Optimizer initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize AI optimizer: {e}")
            return False

    async def optimize_pattern_for_yard(
        self,
        pattern_type: PatternType,
        boundary: Boundary,
        yard_characteristics: YardCharacteristics,
        environmental_conditions: Dict[str, float],
        optimization_strategy: OptimizationStrategy = OptimizationStrategy.BALANCED,
        base_parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        AI-optimized pattern parameter generation based on yard analysis and historical performance
        """
        try:
            self.logger.info(f"Optimizing {pattern_type.value} pattern for yard characteristics")

            # Extract features for ML prediction
            features = self._extract_optimization_features(
                boundary, yard_characteristics, environmental_conditions
            )

            # Get base parameters
            if base_parameters is None:
                base_parameters = self._get_default_parameters(pattern_type)

            # Apply AI-based optimization based on strategy
            optimized_params = await self._apply_ai_optimization(
                pattern_type, features, base_parameters, optimization_strategy
            )

            # Validate and refine parameters
            validated_params = await self._validate_and_refine_parameters(
                pattern_type, optimized_params, boundary
            )

            # Cache optimization for future reference
            cache_key = self._generate_cache_key(
                pattern_type, yard_characteristics, environmental_conditions
            )
            self.optimization_cache[cache_key] = {
                "parameters": validated_params,
                "timestamp": datetime.now(),
                "confidence": self._calculate_optimization_confidence(features),
            }

            return validated_params

        except Exception as e:
            self.logger.error(f"Pattern optimization failed: {e}")
            return base_parameters or self._get_default_parameters(pattern_type)

    async def _apply_ai_optimization(
        self,
        pattern_type: PatternType,
        features: np.ndarray,
        base_parameters: Dict[str, Any],
        strategy: OptimizationStrategy,
    ) -> Dict[str, Any]:
        """Apply AI-based optimization based on selected strategy"""

        optimized_params = base_parameters.copy()

        try:
            if pattern_type == PatternType.WAVES:
                optimized_params = await self._optimize_waves_pattern_ai(
                    features, base_parameters, strategy
                )
            elif pattern_type == PatternType.CROSSHATCH:
                optimized_params = await self._optimize_crosshatch_pattern_ai(
                    features, base_parameters, strategy
                )
            elif pattern_type in [
                PatternType.PARALLEL_LINES,
                PatternType.CHECKERBOARD,
                PatternType.SPIRAL,
            ]:
                optimized_params = await self._optimize_standard_pattern_ai(
                    pattern_type, features, base_parameters, strategy
                )

        except Exception as e:
            self.logger.error(f"AI optimization failed, using base parameters: {e}")

        return optimized_params

    async def _optimize_waves_pattern_ai(
        self, features: np.ndarray, base_parameters: Dict[str, Any], strategy: OptimizationStrategy
    ) -> Dict[str, Any]:
        """AI-enhanced waves pattern optimization with advanced mathematical models"""

        optimized = base_parameters.copy()

        # Advanced sinusoidal parameter optimization
        if hasattr(self.efficiency_model, "predict") and self._is_model_trained("efficiency"):
            try:
                # Predict optimal amplitude based on yard characteristics
                amplitude_features = np.concatenate(
                    [features, [base_parameters.get("amplitude", 0.75)]]
                )
                predicted_amplitude = self.efficiency_model.predict([amplitude_features])[0]
                optimized["amplitude"] = np.clip(predicted_amplitude, 0.25, 2.0)

                # Frequency modulation based on terrain complexity
                terrain_complexity = features[1] if len(features) > 1 else 0.5
                wavelength_modifier = 1.0 + (terrain_complexity - 0.5) * 0.4
                optimized["wavelength"] = np.clip(
                    base_parameters.get("wavelength", 8.0) * wavelength_modifier, 3.0, 15.0
                )

                # Directional optimization based on yard shape
                if len(features) > 4:  # edge_ratio available
                    edge_ratio = features[4]
                    if edge_ratio > 0.3:  # Complex boundary
                        optimized["base_angle"] = (optimized.get("base_angle", 0) + 15) % 180

                # Advanced spacing optimization
                if strategy == OptimizationStrategy.QUALITY_FOCUSED:
                    optimized["spacing"] = max(0.2, optimized.get("spacing", 0.4) * 0.8)
                elif strategy == OptimizationStrategy.EFFICIENCY_FOCUSED:
                    optimized["spacing"] = min(0.6, optimized.get("spacing", 0.4) * 1.2)

            except Exception as e:
                self.logger.warning(f"Advanced waves optimization failed: {e}")

        return optimized

    async def _optimize_crosshatch_pattern_ai(
        self, features: np.ndarray, base_parameters: Dict[str, Any], strategy: OptimizationStrategy
    ) -> Dict[str, Any]:
        """AI-enhanced crosshatch pattern with variable angle optimization"""

        optimized = base_parameters.copy()

        try:
            # Advanced geometric angle optimization
            if hasattr(self.terrain_model, "predict") and self._is_model_trained("terrain"):
                # Predict optimal angles based on terrain and obstacles
                angle_features = np.concatenate(
                    [
                        features,
                        [
                            base_parameters.get("first_angle", 45),
                            base_parameters.get("second_angle", 135),
                        ],
                    ]
                )
                predicted_angles = self.terrain_model.predict([angle_features])[0]

                # Ensure angles are perpendicular and within valid range
                first_angle = np.clip(predicted_angles, 0, 180)
                second_angle = (first_angle + 90) % 180

                optimized["first_angle"] = first_angle
                optimized["second_angle"] = second_angle

            # Dynamic line spacing based on coverage requirements
            if strategy == OptimizationStrategy.QUALITY_FOCUSED:
                optimized["spacing"] = max(0.2, optimized.get("spacing", 0.3) * 0.75)
            elif strategy == OptimizationStrategy.BATTERY_OPTIMIZED:
                optimized["spacing"] = min(0.8, optimized.get("spacing", 0.3) * 1.5)

            # Obstacle-aware overlap adjustment
            if len(features) > 2:  # obstacle_density available
                obstacle_density = features[2]
                if obstacle_density > 0.3:
                    optimized["overlap"] = min(0.2, optimized.get("overlap", 0.1) * 1.5)

        except Exception as e:
            self.logger.warning(f"Advanced crosshatch optimization failed: {e}")

        return optimized

    async def _optimize_standard_pattern_ai(
        self,
        pattern_type: PatternType,
        features: np.ndarray,
        base_parameters: Dict[str, Any],
        strategy: OptimizationStrategy,
    ) -> Dict[str, Any]:
        """AI optimization for standard patterns (parallel, checkerboard, spiral)"""

        optimized = base_parameters.copy()

        try:
            # Battery-optimized spacing prediction
            if hasattr(self.battery_model, "predict") and self._is_model_trained("battery"):
                battery_features = np.concatenate([features, [base_parameters.get("spacing", 0.3)]])
                predicted_spacing = self.battery_model.predict([battery_features])[0]
                optimized["spacing"] = np.clip(predicted_spacing, 0.2, 1.0)

            # Strategy-specific optimizations
            if strategy == OptimizationStrategy.EFFICIENCY_FOCUSED:
                if "angle" in optimized:
                    # Optimize angle for rectangular yards
                    if len(features) > 4:
                        edge_ratio = features[4]
                        if edge_ratio < 0.25:  # Very rectangular
                            optimized["angle"] = 0  # Align with long edge

            elif strategy == OptimizationStrategy.TERRAIN_ADAPTIVE:
                if len(features) > 3:  # slope_variance available
                    slope_variance = features[3]
                    if slope_variance > 0.3:  # High slope variation
                        if "spacing" in optimized:
                            optimized["spacing"] = max(0.2, optimized["spacing"] * 0.8)

        except Exception as e:
            self.logger.warning(f"Standard pattern optimization failed: {e}")

        return optimized

    async def learn_from_performance(self, performance_metric: PatternPerformanceMetric):
        """Continuous learning from pattern performance data"""
        try:
            self.performance_data.append(performance_metric)

            # Retrain models periodically
            if len(self.performance_data) % 10 == 0:
                await self._retrain_models()

            # Save performance data
            await self._save_performance_data()

            self.logger.info(f"Learned from {performance_metric.pattern_type} pattern performance")

        except Exception as e:
            self.logger.error(f"Failed to learn from performance: {e}")

    async def _retrain_models(self):
        """Retrain ML models with accumulated performance data"""
        try:
            if len(self.performance_data) < 20:
                return

            self.logger.info("Retraining AI models with new performance data...")

            # Prepare training data
            X, y_efficiency, y_battery, y_terrain = self._prepare_training_data()

            if len(X) < 10:
                return

            # Split data
            X_train, X_test, y_eff_train, y_eff_test = train_test_split(
                X, y_efficiency, test_size=0.2, random_state=42
            )

            # Train efficiency model
            X_train_scaled = self.scaler_efficiency.fit_transform(X_train)
            self.efficiency_model.fit(X_train_scaled, y_eff_train)

            # Train battery model
            X_train_battery = self.scaler_battery.fit_transform(X_train)
            _, _, y_bat_train, y_bat_test = train_test_split(
                X, y_battery, test_size=0.2, random_state=42
            )
            self.battery_model.fit(X_train_battery, y_bat_train)

            # Train terrain model
            X_train_terrain = self.scaler_terrain.fit_transform(X_train)
            _, _, y_ter_train, y_ter_test = train_test_split(
                X, y_terrain, test_size=0.2, random_state=42
            )
            self.terrain_model.fit(X_train_terrain, y_ter_train)

            # Save updated models
            await self._save_trained_models()

            self.logger.info("AI models retrained successfully")

        except Exception as e:
            self.logger.error(f"Model retraining failed: {e}")

    def _extract_optimization_features(
        self,
        boundary: Boundary,
        yard_characteristics: YardCharacteristics,
        environmental_conditions: Dict[str, float],
    ) -> np.ndarray:
        """Extract features for ML optimization"""

        features = [
            yard_characteristics.area,
            yard_characteristics.shape_complexity,
            yard_characteristics.obstacle_density,
            yard_characteristics.slope_variance,
            yard_characteristics.edge_ratio,
            float(yard_characteristics.irregular_sections),
            environmental_conditions.get("temperature", 20.0),
            environmental_conditions.get("humidity", 50.0),
            environmental_conditions.get("wind_speed", 5.0),
            environmental_conditions.get("light_level", 0.8),
        ]

        return np.array(features)

    def _prepare_training_data(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Prepare training data from performance metrics"""

        X = []
        y_efficiency = []
        y_battery = []
        y_terrain = []

        for metric in self.performance_data:
            # Features from yard characteristics and environment
            features = [
                metric.yard_characteristics.get("area", 0),
                metric.yard_characteristics.get("shape_complexity", 0.5),
                metric.yard_characteristics.get("obstacle_density", 0.1),
                metric.yard_characteristics.get("slope_variance", 0.1),
                metric.yard_characteristics.get("edge_ratio", 0.2),
                metric.environmental_conditions.get("temperature", 20.0),
                metric.environmental_conditions.get("humidity", 50.0),
                metric.environmental_conditions.get("wind_speed", 5.0),
            ]

            # Targets
            X.append(features)
            y_efficiency.append(metric.coverage_efficiency)
            y_battery.append(metric.battery_usage)
            y_terrain.append(metric.terrain_adaptation_score)

        return np.array(X), np.array(y_efficiency), np.array(y_battery), np.array(y_terrain)

    def _get_default_parameters(self, pattern_type: PatternType) -> Dict[str, Any]:
        """Get default parameters for pattern type"""
        defaults = {
            PatternType.WAVES: {
                "amplitude": 0.75,
                "wavelength": 8.0,
                "base_angle": 0,
                "spacing": 0.4,
                "overlap": 0.1,
            },
            PatternType.CROSSHATCH: {
                "first_angle": 45,
                "second_angle": 135,
                "spacing": 0.3,
                "overlap": 0.1,
            },
            PatternType.PARALLEL_LINES: {"spacing": 0.3, "angle": 0, "overlap": 0.1},
            PatternType.CHECKERBOARD: {"spacing": 0.5, "overlap": 0.05, "block_size": 2.0},
            PatternType.SPIRAL: {"spacing": 0.3, "direction": "inward", "start_edge": "outer"},
        }

        result = defaults.get(pattern_type, {})
        return result if isinstance(result, dict) else {}

    def _is_model_trained(self, model_type: str) -> bool:
        """Check if a model has been trained"""
        model_map = {
            "efficiency": self.efficiency_model,
            "battery": self.battery_model,
            "terrain": self.terrain_model,
        }

        model = model_map.get(model_type)
        return bool(hasattr(model, "n_features_in_")) if model else False

    def _generate_cache_key(
        self,
        pattern_type: PatternType,
        yard_characteristics: YardCharacteristics,
        environmental_conditions: Dict[str, float],
    ) -> str:
        """Generate cache key for optimization results"""
        key_data = {
            "pattern": pattern_type.value,
            "area": round(yard_characteristics.area, 1),
            "complexity": round(yard_characteristics.shape_complexity, 2),
            "obstacles": round(yard_characteristics.obstacle_density, 2),
            "temp": round(environmental_conditions.get("temperature", 20), 1),
        }

        return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()

    def _calculate_optimization_confidence(self, features: np.ndarray) -> float:
        """Calculate confidence score for optimization"""
        # Simple confidence based on data similarity to training set
        if len(self.performance_data) < 5:
            return 0.3

        # More sophisticated confidence calculation could be implemented here
        return min(0.9, 0.5 + len(self.performance_data) * 0.02)

    async def _validate_and_refine_parameters(
        self, pattern_type: PatternType, parameters: Dict[str, Any], boundary: Boundary
    ) -> Dict[str, Any]:
        """Validate and refine optimized parameters"""

        refined = parameters.copy()

        # Pattern-specific validation and refinement
        if pattern_type == PatternType.WAVES:
            # Ensure amplitude doesn't exceed boundary constraints
            bounds = self._get_boundary_bounds(boundary)
            max_safe_amplitude = min(bounds["width"], bounds["height"]) * 0.2
            refined["amplitude"] = min(refined.get("amplitude", 0.75), max_safe_amplitude)

        elif pattern_type == PatternType.CROSSHATCH:
            # Ensure angles are properly separated
            first_angle = refined.get("first_angle", 45)
            second_angle = refined.get("second_angle", 135)
            angle_diff = abs(second_angle - first_angle)
            if angle_diff < 30 or angle_diff > 150:
                refined["second_angle"] = (first_angle + 90) % 180

        return refined

    def _get_boundary_bounds(self, boundary: Boundary) -> Dict[str, float]:
        """Get boundary bounding box"""
        if not boundary.points:
            return {"width": 10.0, "height": 10.0}

        xs = [p.x for p in boundary.points]
        ys = [p.y for p in boundary.points]

        return {"width": max(xs) - min(xs), "height": max(ys) - min(ys)}

    def _initialize_optimization_cache(self):
        """Initialize optimization cache"""
        self.optimization_cache = {}

    async def _load_trained_models(self):
        """Load previously trained models"""
        try:
            model_files = {
                "efficiency": self.model_path / "efficiency_model.pkl",
                "battery": self.model_path / "battery_model.pkl",
                "terrain": self.model_path / "terrain_model.pkl",
            }

            for model_type, file_path in model_files.items():
                if file_path.exists():
                    with open(file_path, "rb") as f:
                        model_data = pickle.load(f)
                        if model_type == "efficiency":
                            self.efficiency_model = model_data["model"]
                            self.scaler_efficiency = model_data["scaler"]
                        elif model_type == "battery":
                            self.battery_model = model_data["model"]
                            self.scaler_battery = model_data["scaler"]
                        elif model_type == "terrain":
                            self.terrain_model = model_data["model"]
                            self.scaler_terrain = model_data["scaler"]

        except Exception as e:
            self.logger.warning(f"Could not load trained models: {e}")

    async def _save_trained_models(self):
        """Save trained models"""
        try:
            model_data = {
                "efficiency": {"model": self.efficiency_model, "scaler": self.scaler_efficiency},
                "battery": {"model": self.battery_model, "scaler": self.scaler_battery},
                "terrain": {"model": self.terrain_model, "scaler": self.scaler_terrain},
            }

            for model_type, data in model_data.items():
                file_path = self.model_path / f"{model_type}_model.pkl"
                with open(file_path, "wb") as f:
                    pickle.dump(data, f)

        except Exception as e:
            self.logger.error(f"Failed to save trained models: {e}")

    async def _load_performance_data(self):
        """Load historical performance data"""
        try:
            data_file = self.model_path / "performance_data.json"
            if data_file.exists():
                with open(data_file, "r") as f:
                    data = json.load(f)
                    self.performance_data = [PatternPerformanceMetric(**item) for item in data]
        except Exception as e:
            self.logger.warning(f"Could not load performance data: {e}")

    async def _save_performance_data(self):
        """Save performance data"""
        try:
            data_file = self.model_path / "performance_data.json"
            with open(data_file, "w") as f:
                data = [asdict(metric) for metric in self.performance_data[-100:]]  # Keep last 100
                json.dump(data, f, default=str, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save performance data: {e}")


# Global AI optimizer instance
ai_pattern_optimizer = AIPatternOptimizer()
