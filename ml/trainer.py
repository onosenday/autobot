"""
Model Trainer - Entrena el modelo con datos de ml_data.db + training_data/
"""
import os
import sqlite3
import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from datetime import datetime
import threading
import queue

from .model import ActionPredictor, preprocess_image, ENUM_TO_CLASS


class TransitionDataset(Dataset):
    """Dataset que carga transiciones de la BD y screenshots."""
    
    def __init__(self, db_path="ml_data.db", screenshots_dir="training_data", 
                 limit=None, min_id=0):
        self.screenshots_dir = screenshots_dir
        self.samples = []
        
        # Mapeo invertido: String -> Enum Int -> Class Int
        # Necesitamos saber el Enum Int de cada String en BD.
        # Asumiendo que el String en BD coincide con Key del Enum
        # Mapa auxiliar String -> Enum Int
        self.str_to_enum = {
            'WAIT': 0, 'CLICK_COIN': 1, 'CLICK_AD_CONFIRM': 2,
            'CLICK_CLOSE_X': 3, 'CLICK_FAST_FORWARD': 4, 'CLICK_REWARD_CLOSE': 5,
            'PRESS_BACK': 6, 
            'CLICK_REGION': 10, 'CLICK_SELECCIONAR': 11,
            'CLICK_SEARCH_FIELD': 12, 'CLICK_COUNTRY': 13,
            'CLICK_CITY': 14, 'PRESS_HOME': 15, 
            'CLICK_WEB_CLOSE': 20, 'CLICK_SURVEY_SKIP': 21,
            'NONE': 99
        }
        
        # Cargar desde BD
        try:
            with sqlite3.connect(db_path) as conn:
                query = """
                    SELECT id, screenshot_path, action 
                    FROM ml_transitions 
                    WHERE screenshot_path IS NOT NULL AND id > ?
                    ORDER BY id
                """
                if limit:
                    query += f" LIMIT {limit}"
                    
                cursor = conn.execute(query, (min_id,))
                for row in cursor.fetchall():
                    tid, path, action_str = row
                    
                    if path and os.path.exists(path):
                        # 1. String -> Enum Int
                        enum_val = self.str_to_enum.get(action_str)
                        if enum_val is not None:
                            # 2. Enum Int -> Class Int (via model mapping)
                            class_idx = ENUM_TO_CLASS.get(enum_val)
                            if class_idx is not None:
                                self.samples.append((path, class_idx, tid))
        except Exception as e:
            print(f"[Dataset] Error loading: {e}")
    
    def __len__(self):
        return len(self.samples)
    
    def __getitem__(self, idx):
        path, action_idx, tid = self.samples[idx]
        
        # Cargar imagen
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            # Fallback: imagen vacia
            img = np.zeros((90, 160), dtype=np.uint8)
        
        # Resize y normalizar
        img = cv2.resize(img, (160, 90))
        img = img.astype(np.float32) / 255.0
        
        # Tensor (1, H, W)
        tensor = torch.from_numpy(img).unsqueeze(0)
        
        return tensor, action_idx


class ModelTrainer:
    """Entrena el modelo con feedback visual."""
    
    def __init__(self, db_path="ml_data.db", screenshots_dir="training_data",
                 model_path="ml/model_weights.pth"):
        self.db_path = db_path
        self.screenshots_dir = screenshots_dir
        self.model_path = model_path
        
        self.model = ActionPredictor(num_classes=15)
        self.is_training = False
        self.progress = 0.0
        self.current_epoch = 0
        self.total_epochs = 0
        self.current_loss = 0.0
        self.current_accuracy = 0.0
        
        # Queue para logs
        self.log_queue = queue.Queue()
        
        # Cargar modelo existente si existe
        if os.path.exists(model_path):
            self.model.load(model_path)
    
    def log(self, msg):
        """Añade mensaje a la cola de logs."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {msg}")
        print(f"[Trainer] {msg}")
    
    def get_sample_count(self):
        """Retorna numero de muestras disponibles."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM ml_transitions WHERE screenshot_path IS NOT NULL"
                )
                return cursor.fetchone()[0]
        except:
            return 0
    
    def get_new_samples_since_training(self):
        """Retorna numero de muestras nuevas desde el ultimo entrenamiento."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Buscar ultimo ID entrenado
                cursor = conn.execute(
                    "SELECT MAX(id) FROM ml_transitions WHERE screenshot_path IS NOT NULL"
                )
                max_id = cursor.fetchone()[0] or 0
                
                # TODO: Guardar ultimo ID entrenado en metadata
                # Por ahora retornamos total
                return max_id
        except:
            return 0
    
    def train(self, epochs=10, batch_size=32, lr=0.001, train_split=0.8, callback=None):
        """
        Entrena el modelo en un hilo separado.
        
        Args:
            epochs: Numero de epocas
            batch_size: Tamano del batch
            lr: Learning rate
            train_split: Proporcion para training (resto validation)
            callback: Funcion a llamar cuando termine (success, accuracy)
        """
        def _train_thread():
            self.is_training = True
            self.total_epochs = epochs
            
            try:
                self.log("Cargando dataset...")
                dataset = TransitionDataset(self.db_path, self.screenshots_dir)
                
                if len(dataset) < 10:
                    self.log(f"Error: Solo hay {len(dataset)} muestras. Minimo 10.")
                    self.is_training = False
                    if callback:
                        callback(False, 0.0)
                    return
                
                # Split train/val
                train_size = int(len(dataset) * train_split)
                val_size = len(dataset) - train_size
                train_dataset, val_dataset = torch.utils.data.random_split(
                    dataset, [train_size, val_size]
                )
                
                train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
                val_loader = DataLoader(val_dataset, batch_size=batch_size)
                
                self.log(f"Dataset: {train_size} train, {val_size} val")
                
                # Check Device
                device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                self.log(f"Usando dispositivo: {device}")
                self.model.to(device)
                
                # Optimizer y loss
                optimizer = optim.Adam(self.model.parameters(), lr=lr)
                criterion = nn.CrossEntropyLoss()
                
                best_accuracy = 0.0
                
                for epoch in range(epochs):
                    self.current_epoch = epoch + 1
                    self.progress = (epoch / epochs) * 100
                    
                    # Training
                    self.model.train()
                    total_loss = 0.0
                    
                    for batch_idx, (images, labels) in enumerate(train_loader):
                        images, labels = images.to(device), labels.to(device)
                        
                        optimizer.zero_grad()
                        outputs = self.model(images)
                        loss = criterion(outputs, labels)
                        loss.backward()
                        optimizer.step()
                        total_loss += loss.item()
                        
                        # Feedback intrra-epoch
                        batches_10_percent = max(1, len(train_loader) // 10)
                        if (batch_idx + 1) % batches_10_percent == 0:
                            current_progress = (batch_idx + 1) / len(train_loader) * 100
                            self.log(f"Epoch {epoch+1} Progress: {current_progress:.0f}% (Loss: {loss.item():.4f})")
                    
                    avg_loss = total_loss / len(train_loader)
                    self.current_loss = avg_loss
                    
                    # Validation
                    self.model.eval()
                    correct = 0
                    total = 0
                    
                    with torch.no_grad():
                        for images, labels in val_loader:
                            images, labels = images.to(device), labels.to(device)
                            outputs = self.model(images)
                            _, predicted = torch.max(outputs, 1)
                            total += labels.size(0)
                            correct += (predicted == labels).sum().item()
                    
                    accuracy = correct / total if total > 0 else 0
                    self.current_accuracy = accuracy * 100
                    
                    self.log(f"Epoch {epoch+1}/{epochs} - Loss: {avg_loss:.4f} - Acc: {accuracy*100:.1f}%")
                    
                    if accuracy > best_accuracy:
                        best_accuracy = accuracy
                        self.model.is_trained = True
                        self.model.save(self.model_path)
                
                self.progress = 100.0
                self.log(f"Entrenamiento completado. Mejor accuracy: {best_accuracy*100:.1f}%")
                
                if callback:
                    callback(True, best_accuracy * 100)
                    
            except Exception as e:
                self.log(f"Error en entrenamiento: {e}")
                if callback:
                    callback(False, 0.0)
            finally:
                self.is_training = False
        
        thread = threading.Thread(target=_train_thread, daemon=True)
        thread.start()
        return thread
    
    def get_logs(self):
        """Retorna logs pendientes."""
        logs = []
        while not self.log_queue.empty():
            logs.append(self.log_queue.get())
        return logs
