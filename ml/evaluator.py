"""
Model Evaluator - Evalua el modelo en datos de test.
"""
import sqlite3
import numpy as np
import torch
from .model import ActionPredictor, preprocess_image
from torch.utils.data import DataLoader
from .trainer import TransitionDataset


class ModelEvaluator:
    """Evalua el modelo cargado."""
    
    def __init__(self, model_path="ml/model_weights.pth", db_path="ml_data.db"):
        self.model_path = model_path
        self.db_path = db_path
        self.model = ActionPredictor(num_classes=15)
        self.accuracy = 0.0
        self.is_evaluating = False
        
        # Cargar modelo
        if not self.model.load(model_path):
            print("[Evaluator] No model found")
    
    def evaluate(self, test_split=0.2):
        """
        Evalua el modelo en un subset de datos.
        
        Returns:
            dict: accuracy, confusion_matrix, etc.
        """
        self.is_evaluating = True
        
        try:
            dataset = TransitionDataset(self.db_path)
            
            if len(dataset) < 10:
                return {"error": "Not enough samples", "accuracy": 0.0}
            
            # Usar ultimo 20% como test
            test_size = int(len(dataset) * test_split)
            test_indices = list(range(len(dataset) - test_size, len(dataset)))
            test_dataset = torch.utils.data.Subset(dataset, test_indices)
            
            test_loader = DataLoader(test_dataset, batch_size=32)
            
            self.model.eval()
            correct = 0
            total = 0
            predictions = []
            actuals = []
            
            with torch.no_grad():
                for images, labels in test_loader:
                    outputs = self.model(images)
                    _, predicted = torch.max(outputs, 1)
                    total += labels.size(0)
                    correct += (predicted == labels).sum().item()
                    predictions.extend(predicted.tolist())
                    actuals.extend(labels.tolist())
            
            self.accuracy = (correct / total * 100) if total > 0 else 0
            
            return {
                "accuracy": self.accuracy,
                "total_samples": total,
                "correct": correct,
                "predictions": predictions,
                "actuals": actuals
            }
            
        except Exception as e:
            return {"error": str(e), "accuracy": 0.0}
        finally:
            self.is_evaluating = False
    
    def get_accuracy(self):
        """Retorna accuracy del ultimo test."""
        return self.accuracy
