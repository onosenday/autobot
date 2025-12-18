"""
Live Monitor - Compara predicciones del modelo con acciones reales del bot.
"""
import threading
import time
import queue
from collections import deque
import cv2
import numpy as np

from .model import ActionPredictor, preprocess_image


class LiveMonitor:
    """
    Monitor en tiempo real que compara predicciones del modelo
    con las acciones reales del bot.
    """
    
    def __init__(self, model_path="ml/model_weights.pth"):
        self.model_path = model_path
        self.model = ActionPredictor(num_classes=15)
        self.is_active = False
        self.is_running = False
        
        # Estadisticas
        self.total_comparisons = 0
        self.correct_predictions = 0
        self.concordance = 0.0
        
        # Historial reciente (ultimas 100 comparaciones)
        self.recent_results = deque(maxlen=100)
        
        # Queue para recibir datos del bot
        self.data_queue = queue.Queue()
        
        # Thread
        self._thread = None
        
        # Cargar modelo
        if not self.model.load(model_path):
            print("[Monitor] No model loaded")
    
    def start(self):
        """Inicia el monitor en un thread separado."""
        if self.is_running:
            return
        
        if not self.model.is_trained:
            print("[Monitor] Model not trained")
            return
        
        self.is_active = True
        self.is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print("[Monitor] Started")
    
    def stop(self):
        """Detiene el monitor."""
        self.is_active = False
        self.is_running = False
        print("[Monitor] Stopped")
    
    def submit(self, screenshot, actual_action):
        """
        Envia un screenshot y accion real para comparar.
        
        Args:
            screenshot: numpy array (imagen)
            actual_action: Action enum o int
        """
        if not self.is_active:
            return
        
        self.data_queue.put((screenshot, actual_action))
    
    def _run_loop(self):
        """Loop principal del monitor."""
        while self.is_active:
            try:
                # Esperar datos con timeout
                screenshot, actual_action = self.data_queue.get(timeout=1.0)
                
                # Preprocesar imagen
                tensor = preprocess_image(screenshot)
                
                # Predecir
                predicted_idx, confidence = self.model.predict(tensor)
                
                # Comparar
                actual_idx = actual_action.value if hasattr(actual_action, 'value') else int(actual_action)
                is_correct = (predicted_idx == actual_idx)
                
                # Actualizar estadisticas
                self.total_comparisons += 1
                if is_correct:
                    self.correct_predictions += 1
                
                self.recent_results.append(is_correct)
                
                # Calcular concordancia (sobre ultimas 100)
                if len(self.recent_results) > 0:
                    self.concordance = sum(self.recent_results) / len(self.recent_results) * 100
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[Monitor] Error: {e}")
    
    def get_stats(self):
        """Retorna estadisticas actuales."""
        return {
            "total_comparisons": self.total_comparisons,
            "correct_predictions": self.correct_predictions,
            "concordance": self.concordance,
            "is_active": self.is_active,
            "recent_count": len(self.recent_results)
        }
    
    def reset_stats(self):
        """Resetea estadisticas."""
        self.total_comparisons = 0
        self.correct_predictions = 0
        self.concordance = 0.0
        self.recent_results.clear()
