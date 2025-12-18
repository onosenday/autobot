"""
Action Prediction Model - CNN for predicting bot actions from screenshots.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import os

class ActionPredictor(nn.Module):
    """
    CNN simple para clasificacion de acciones.
    Input: Imagen grayscale 640x360 -> resize a 160x90
    Output: 15 clases (Action enum values)
    """
    
    def __init__(self, num_classes=15):
        super(ActionPredictor, self).__init__()
        
        # Feature extractor (CNN)
        self.conv1 = nn.Conv2d(1, 32, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        self.pool = nn.MaxPool2d(2, 2)
        self.dropout = nn.Dropout(0.25)
        
        # Classifier
        # Despues de 3 poolings: 160/8=20, 90/8=11.25 -> 20x11
        self.fc1 = nn.Linear(128 * 20 * 11, 256)
        self.fc2 = nn.Linear(256, 64)
        self.fc3 = nn.Linear(64, num_classes)
        
        self.num_classes = num_classes
        self._is_trained = False
        
    def forward(self, x):
        # x shape: (batch, 1, 160, 90)
        x = self.pool(F.relu(self.conv1(x)))   # -> (batch, 32, 80, 45)
        x = self.pool(F.relu(self.conv2(x)))   # -> (batch, 64, 40, 22)
        x = self.pool(F.relu(self.conv3(x)))   # -> (batch, 128, 20, 11)
        
        x = x.view(x.size(0), -1)  # Flatten
        x = self.dropout(F.relu(self.fc1(x)))
        x = self.dropout(F.relu(self.fc2(x)))
        x = self.fc3(x)
        
        return x
    
    def predict(self, image_tensor):
        """
        Predice la accion para una imagen.
        
        Args:
            image_tensor: Tensor (1, 1, 160, 90) normalizado
            
        Returns:
            int: Indice de la accion predicha
            float: Confianza (probabilidad)
        """
        self.eval()
        with torch.no_grad():
            output = self(image_tensor)
            probs = F.softmax(output, dim=1)
            confidence, predicted = torch.max(probs, 1)
            return predicted.item(), confidence.item()
    
    def save(self, path="ml/model_weights.pth"):
        """Guarda el modelo."""
        torch.save({
            'model_state_dict': self.state_dict(),
            'num_classes': self.num_classes,
            'is_trained': self._is_trained
        }, path)
        print(f"[Model] Saved to {path}")
    
    def load(self, path="ml/model_weights.pth"):
        """Carga el modelo."""
        if not os.path.exists(path):
            print(f"[Model] No weights found at {path}")
            return False
        
        checkpoint = torch.load(path, map_location='cpu', weights_only=True)
        self.load_state_dict(checkpoint['model_state_dict'])
        self._is_trained = checkpoint.get('is_trained', True)
        print(f"[Model] Loaded from {path}")
        return True
    
    @property
    def is_trained(self):
        return self._is_trained
    
    @is_trained.setter
    def is_trained(self, value):
        self._is_trained = value


def preprocess_image(image_np):
    """
    Preprocesa una imagen para el modelo.
    Las imagenes guardadas ya estan en 160x90 grayscale.
    Solo normaliza y convierte a tensor.
    
    Args:
        image_np: numpy array (90, 160) grayscale o (H, W, 3) BGR
        
    Returns:
        torch.Tensor: (1, 1, 90, 160)
    """
    import cv2
    import numpy as np
    
    # Convertir a grayscale si viene en color (para uso en vivo)
    if len(image_np.shape) == 3:
        image_np = cv2.cvtColor(image_np, cv2.COLOR_BGR2GRAY)
    
    # Resize solo si no es ya 160x90 (para uso en vivo)
    if image_np.shape != (90, 160):
        image_np = cv2.resize(image_np, (160, 90))
    
    # Normalizar a [0, 1]
    image_np = image_np.astype(np.float32) / 255.0
    
    # Convertir a tensor (1, 1, H, W)
    tensor = torch.from_numpy(image_np).unsqueeze(0).unsqueeze(0)
    
    return tensor
