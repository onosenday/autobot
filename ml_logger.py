"""
ML Logger - Sistema de logging para entrenamiento de Machine Learning.

Registra transiciones (estado, acción, nuevo estado, recompensa) junto con
screenshots para entrenar modelos de imitación o RL.
"""
import os
import sqlite3
import datetime
import cv2
import numpy as np
import json

class MLLogger:
    def __init__(self, db_path="ml_data.db", screenshots_dir="training_data"):
        self.db_path = db_path
        self.screenshots_dir = screenshots_dir
        self._init_db()
        self._init_dirs()
        
        # Session tracking
        self.session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.transition_count = 0
        
    def _init_db(self):
        """Inicializa la base de datos para transiciones ML."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ml_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    timestamp TEXT,
                    state_before TEXT,
                    action TEXT,
                    action_value INTEGER,
                    state_after TEXT,
                    reward REAL,
                    screenshot_path TEXT,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ml_sessions (
                    session_id TEXT PRIMARY KEY,
                    start_time TEXT,
                    end_time TEXT,
                    total_transitions INTEGER,
                    total_reward REAL,
                    notes TEXT
                )
            """)
            # Index for faster queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session ON ml_transitions(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_state ON ml_transitions(state_before)")
    
    def _init_dirs(self):
        """Crea directorios para screenshots si no existen."""
        if not os.path.exists(self.screenshots_dir):
            os.makedirs(self.screenshots_dir)
    
    def start_session(self, notes=""):
        """Inicia una nueva sesión de logging."""
        self.session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.transition_count = 0
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO ml_sessions (session_id, start_time, total_transitions, total_reward, notes)
                    VALUES (?, ?, 0, 0.0, ?)
                """, (self.session_id, datetime.datetime.now().isoformat(), notes))
            print(f"[MLLogger] Session started: {self.session_id}")
        except Exception as e:
            print(f"[MLLogger] Error starting session: {e}")
        
        return self.session_id
    
    def end_session(self):
        """Finaliza la sesión actual."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Calcular totales
                cursor = conn.execute("""
                    SELECT COUNT(*), COALESCE(SUM(reward), 0) 
                    FROM ml_transitions WHERE session_id = ?
                """, (self.session_id,))
                count, total_reward = cursor.fetchone()
                
                conn.execute("""
                    UPDATE ml_sessions 
                    SET end_time = ?, total_transitions = ?, total_reward = ?
                    WHERE session_id = ?
                """, (datetime.datetime.now().isoformat(), count, total_reward, self.session_id))
            
            print(f"[MLLogger] Session ended: {self.session_id} ({count} transitions, {total_reward:.1f} reward)")
        except Exception as e:
            print(f"[MLLogger] Error ending session: {e}")
    
    def log_transition(self, screenshot, state_before, action, state_after, reward, metadata=None):
        """
        Registra una transición completa.
        
        Args:
            screenshot: numpy array (cv2 image) o None
            state_before: BotState enum o string
            action: Action enum o string
            state_after: BotState enum o string
            reward: float
            metadata: dict opcional con info extra (coords click, etc)
        """
        timestamp = datetime.datetime.now().isoformat()
        self.transition_count += 1
        
        # Convertir enums a strings si es necesario
        state_before_str = state_before.name if hasattr(state_before, 'name') else str(state_before)
        action_str = action.name if hasattr(action, 'name') else str(action)
        action_val = action.value if hasattr(action, 'value') else -1
        state_after_str = state_after.name if hasattr(state_after, 'name') else str(state_after)
        
        # Guardar screenshot ya preprocesado para el modelo (160x90 grayscale JPEG)
        screenshot_path = None
        if screenshot is not None:
            filename = f"{self.session_id}_{self.transition_count:06d}_{state_before_str}_{action_str}.jpg"
            screenshot_path = os.path.join(self.screenshots_dir, filename)
            try:
                # Convertir a escala de grises
                gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
                
                # Resize al tamano exacto del modelo (160x90)
                gray = cv2.resize(gray, (160, 90))
                
                # Guardar como JPEG calidad 90% (a este tamano el archivo es muy pequeno)
                cv2.imwrite(screenshot_path, gray, [cv2.IMWRITE_JPEG_QUALITY, 90])
            except Exception as e:
                print(f"[MLLogger] Error saving screenshot: {e}")
                screenshot_path = None
        
        # Serializar metadata
        metadata_json = json.dumps(metadata) if metadata else None
        
        # Insertar en BD
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO ml_transitions 
                    (session_id, timestamp, state_before, action, action_value, state_after, reward, screenshot_path, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (self.session_id, timestamp, state_before_str, action_str, action_val, 
                      state_after_str, reward, screenshot_path, metadata_json))
        except Exception as e:
            print(f"[MLLogger] Error logging transition: {e}")
        
        return screenshot_path
    
    def get_session_stats(self, session_id=None):
        """Obtiene estadísticas de una sesión."""
        sid = session_id or self.session_id
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as transitions,
                        COALESCE(SUM(reward), 0) as total_reward,
                        COUNT(DISTINCT state_before) as unique_states,
                        COUNT(DISTINCT action) as unique_actions
                    FROM ml_transitions WHERE session_id = ?
                """, (sid,))
                row = cursor.fetchone()
                return {
                    "transitions": row[0],
                    "total_reward": row[1],
                    "unique_states": row[2],
                    "unique_actions": row[3]
                }
        except Exception as e:
            print(f"[MLLogger] Error getting stats: {e}")
            return None
    
    def get_action_distribution(self, session_id=None):
        """Obtiene distribución de acciones en una sesión."""
        sid = session_id or self.session_id
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT action, COUNT(*) as count
                    FROM ml_transitions WHERE session_id = ?
                    GROUP BY action ORDER BY count DESC
                """, (sid,))
                return {row[0]: row[1] for row in cursor.fetchall()}
        except Exception as e:
            print(f"[MLLogger] Error getting distribution: {e}")
            return {}


def calculate_reward(state_before, action, state_after, gold_gained=0, extra_info=None):
    """
    Calcula la recompensa para una transicion.
    
    Estructura de recompensas definida con el usuario:
    - Recompensa por oro: FIJA (+50) independiente de cantidad
    - Transiciones correctas: +5 a +20 segun progreso
    - Penalizaciones: -1 a -10 segun error
    
    Args:
        state_before: Estado antes de la accion
        action: Accion tomada
        state_after: Estado despues de la accion
        gold_gained: Oro ganado (solo para saber si hubo recompensa, no afecta valor)
        extra_info: dict con info extra (ej: {"wrong_x": True, "tz_incomplete": True})
    
    Returns:
        float: Valor de recompensa
    """
    reward = 0.0
    extra_info = extra_info or {}
    
    # Convertir a strings
    sb = state_before.name if hasattr(state_before, 'name') else str(state_before)
    sa = state_after.name if hasattr(state_after, 'name') else str(state_after)
    act = action.name if hasattr(action, 'name') else str(action)
    
    # ========== RECOMPENSAS POSITIVAS ==========
    
    # Recompensa FIJA por obtener oro
    if gold_gained > 0:
        reward += 50.0
    
    # Progresion de estados principales (transiciones correctas)
    transitions_rewards = {
        ("GAME_LOBBY", "AD_INTERMEDIATE"): 5.0,      # Click en moneda exitoso
        ("AD_INTERMEDIATE", "AD_WATCHING"): 5.0,    # Confirmacion exitosa
        ("AD_WATCHING", "REWARD_SCREEN"): 10.0,     # Anuncio completado
        ("REWARD_SCREEN", "GAME_LOBBY"): 5.0,       # Recompensa cerrada
    }
    
    if (sb, sa) in transitions_rewards:
        reward += transitions_rewards[(sb, sa)]
    
    # Progresion Timezone (cada paso correcto)
    tz_rewards = {
        ("GAME_LOBBY", "TZ_INIT"): 2.0,
        ("TZ_INIT", "TZ_OPEN_SETTINGS"): 2.0,
        ("TZ_OPEN_SETTINGS", "TZ_SEARCH_REGION"): 2.0,
        ("TZ_SEARCH_REGION", "TZ_INPUT_SEARCH"): 3.0,
        ("TZ_INPUT_SEARCH", "TZ_SELECT_COUNTRY"): 3.0,
        ("TZ_SELECT_COUNTRY", "TZ_SELECT_CITY"): 3.0,
        ("TZ_SELECT_CITY", "TZ_RETURN_GAME"): 5.0,
        ("TZ_RETURN_GAME", "GAME_LOBBY"): 20.0,  # Timezone COMPLETADO
    }
    
    if (sb, sa) in tz_rewards:
        reward += tz_rewards[(sb, sa)]
    
    # ========== PENALIZACIONES ==========
    
    # Click sin efecto (mismo estado)
    if sb == sa and act not in ["WAIT", "NONE"]:
        reward -= 1.0
    
    # Volver a UNKNOWN (reset/error)
    if sa == "UNKNOWN" and sb != "UNKNOWN":
        reward -= 5.0
    
    # Click en X incorrecto (falso positivo)
    if extra_info.get("wrong_x", False):
        reward -= 5.0
    
    # Timezone incompleto (fallo en la secuencia)
    if extra_info.get("tz_incomplete", False):
        reward -= 10.0
    
    # Timeout de anuncio
    if extra_info.get("ad_timeout", False):
        reward -= 10.0
    
    return reward


# Tabla de recompensas para referencia
REWARD_TABLE = """
=== TABLA DE RECOMPENSAS ===

POSITIVAS:
+50   Obtener oro (fija, independiente de cantidad)
+20   Completar cambio de zona horaria
+10   Cerrar anuncio correctamente (AD_WATCHING -> REWARD_SCREEN)
+5    Transicion correcta en flujo principal
+2-5  Transiciones correctas en flujo timezone

PENALIZACIONES:
-1    Click sin efecto (mismo estado)
-5    Volver a UNKNOWN
-5    Click en X incorrecto (falso positivo)
-10   Timeout de anuncio
-10   Timezone incompleto
"""
