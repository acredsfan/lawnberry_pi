#!/usr/bin/env python3
"""
Custom model training script for lawn mowing obstacle detection
Generates TPU-optimized TensorFlow Lite models for Coral TPU
"""

import json
import logging
import numpy as np
import tensorflow as tf
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import cv2
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LawnModelTrainer:
    """Train custom models for lawn mowing obstacle detection"""
    
    def __init__(self, config_path: str):
        """Initialize trainer with configuration"""
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.model = None
        
    def _load_config(self) -> Dict:
        """Load training configuration"""
        with open(self.config_path, 'r') as f:
            return json.load(f)
    
    def create_lawn_detection_model(self) -> tf.keras.Model:
        """Create a custom EfficientDet-style model for lawn obstacles"""
        input_shape = self.config['training_config']['input_size']
        num_classes = len(self.config['classes'])
        
        # Base model using MobileNetV2 for efficiency
        base_model = tf.keras.applications.MobileNetV2(
            input_shape=input_shape,
            include_top=False,
            weights='imagenet'
        )
        
        # Add custom detection head
        x = base_model.output
        x = tf.keras.layers.GlobalAveragePooling2D()(x)
        x = tf.keras.layers.Dense(512, activation='relu')(x)
        x = tf.keras.layers.Dropout(0.3)(x)
        
        # Detection outputs
        bbox_output = tf.keras.layers.Dense(4, activation='sigmoid', name='bbox')(x)
        class_output = tf.keras.layers.Dense(num_classes, activation='softmax', name='classes')(x)
        confidence_output = tf.keras.layers.Dense(1, activation='sigmoid', name='confidence')(x)
        
        model = tf.keras.Model(
            inputs=base_model.input,
            outputs=[bbox_output, class_output, confidence_output]
        )
        
        return model
    
    def compile_model(self, model: tf.keras.Model) -> tf.keras.Model:
        """Compile model with appropriate loss functions and metrics"""
        model.compile(
            optimizer=tf.keras.optimizers.Adam(
                learning_rate=self.config['training_config']['learning_rate']
            ),
            loss={
                'bbox': 'mse',
                'classes': 'categorical_crossentropy',
                'confidence': 'binary_crossentropy'
            },
            loss_weights={
                'bbox': 1.0,
                'classes': 2.0,
                'confidence': 1.0
            },
            metrics={
                'classes': ['accuracy'],
                'confidence': ['binary_accuracy']
            }
        )
        return model
    
    def create_synthetic_data(self, num_samples: int = 1000) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
        """Create synthetic training data for demonstration"""
        input_shape = self.config['training_config']['input_size']
        num_classes = len(self.config['classes'])
        
        # Generate synthetic images (grass-like textures with obstacles)
        X = np.random.rand(num_samples, *input_shape).astype(np.float32)
        
        # Add grass-like texture
        for i in range(num_samples):
            # Create grass-like base
            grass_color = np.random.uniform(0.2, 0.6, 3)  # Green variations
            X[i] = np.full(input_shape, grass_color)
            
            # Add random noise for texture
            noise = np.random.normal(0, 0.1, input_shape)
            X[i] = np.clip(X[i] + noise, 0, 1)
        
        # Generate synthetic labels
        y_bbox = np.random.rand(num_samples, 4).astype(np.float32)
        y_classes = np.random.randint(0, num_classes, num_samples)
        y_classes_one_hot = tf.keras.utils.to_categorical(y_classes, num_classes)
        y_confidence = np.random.rand(num_samples, 1).astype(np.float32)
        
        labels = {
            'bbox': y_bbox,
            'classes': y_classes_one_hot,
            'confidence': y_confidence
        }
        
        return X, labels
    
    def train_model(self, save_path: str = None) -> str:
        """Train the lawn detection model"""
        logger.info("Creating lawn detection model...")
        self.model = self.create_lawn_detection_model()
        self.model = self.compile_model(self.model)
        
        logger.info(f"Model created with {self.model.count_params()} parameters")
        
        # Generate training data
        logger.info("Generating synthetic training data...")
        X_train, y_train = self.create_synthetic_data(1000)
        X_val, y_val = self.create_synthetic_data(200)
        
        # Training callbacks
        callbacks = [
            tf.keras.callbacks.EarlyStopping(
                monitor='val_loss',
                patience=10,
                restore_best_weights=True
            ),
            tf.keras.callbacks.ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=5,
                min_lr=1e-7
            )
        ]
        
        # Train model
        logger.info("Training model...")
        history = self.model.fit(
            X_train, y_train,
            validation_data=(X_val, y_val),
            epochs=self.config['training_config']['epochs'],
            batch_size=self.config['training_config']['batch_size'],
            callbacks=callbacks,
            verbose=1
        )
        
        # Save model
        if save_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = f"models/custom/lawn_model_{timestamp}.h5"
        
        self.model.save(save_path)
        logger.info(f"Model saved to {save_path}")
        
        return save_path
    
    def convert_to_tflite(self, model_path: str, output_path: str = None, 
                         quantize_for_tpu: bool = True) -> str:
        """Convert trained model to TensorFlow Lite format optimized for TPU"""
        if output_path is None:
            output_path = model_path.replace('.h5', '_tpu_optimized.tflite')
        
        logger.info(f"Converting model to TensorFlow Lite: {output_path}")
        
        # Load the trained model
        model = tf.keras.models.load_model(model_path)
        
        # Create TensorFlow Lite converter
        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        
        if quantize_for_tpu:
            # Quantize for TPU (Edge TPU requires full integer quantization)
            converter.optimizations = [tf.lite.Optimize.DEFAULT]
            converter.target_spec.supported_types = [tf.int8]
            converter.inference_input_type = tf.uint8
            converter.inference_output_type = tf.uint8
            
            # Representative dataset for quantization
            def representative_dataset():
                for _ in range(100):
                    yield [np.random.rand(1, *self.config['training_config']['input_size']).astype(np.float32)]
            
            converter.representative_dataset = representative_dataset
        
        # Convert model
        tflite_model = converter.convert()
        
        # Save TensorFlow Lite model
        with open(output_path, 'wb') as f:
            f.write(tflite_model)
        
        logger.info(f"TensorFlow Lite model saved to {output_path}")
        
        # Create model metadata
        metadata = {
            "model_info": self.config["model_info"].copy(),
            "conversion_date": datetime.now().isoformat(),
            "quantized": quantize_for_tpu,
            "file_size_bytes": len(tflite_model),
            "classes": self.config["classes"]
        }
        
        metadata_path = output_path.replace('.tflite', '_metadata.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        return output_path


def main():
    """Main training function"""
    config_path = "models/custom/lawn_obstacles_v1.json"
    trainer = LawnModelTrainer(config_path)
    
    # Train model
    model_path = trainer.train_model()
    
    # Convert to TensorFlow Lite for TPU
    tflite_path = trainer.convert_to_tflite(model_path, quantize_for_tpu=True)
    
    logger.info(f"Training complete. TensorFlow Lite model: {tflite_path}")


if __name__ == "__main__":
    main()
