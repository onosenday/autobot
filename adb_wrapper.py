import adbutils
import cv2
import numpy as np
import time
import re
from PIL import Image

class ADBWrapper:
    def __init__(self, device_id=None):
        self.device_id = device_id
        self.device = None
        self._connect_client()

    def _connect_client(self):
        try:
            if self.device_id:
                self.device = adbutils.adb.device(serial=self.device_id)
            else:
                # Si no se especifica ID, usar el primero disponible
                self.device = adbutils.adb.device()
        except Exception as e:
            print(f"Error conectando con adbutils: {e}")
            self.device = None

    def _ensure_connection(self):
        if self.device is None:
            self._connect_client()
        return self.device is not None

    def _run_command(self, cmd_args, timeout=None):
        """
        Ejecuta un comando shell en el dispositivo. 
        """
        if not self._ensure_connection():
            return None
        
        cmd_str = " ".join(cmd_args)
        try:
            # adbutils shell devuelve string
            return self.device.shell(cmd_str, timeout=timeout)
        except adbutils.AdbTimeout:
            return None
        except Exception as e:
            print(f"Error ejecutando comando '{cmd_str}': {e}")
            return None

    def connect(self):
        """Verifica que hay un dispositivo conectado."""
        try:
            # Forzar reconexión/chequeo
            self._connect_client()
            if self.device:
                # device.prop es una propiedad que contiene los system properties
                model = self.device.prop.get('ro.product.model', 'Unknown')
                print(f"Dispositivo conectado: {self.device.serial} ({model})")
                return True
            else:
                return False
        except Exception as e:
            print(f"Excepción al conectar: {e}")
            return False

    def take_screenshot(self):
        """Toma una captura de pantalla usando adbutils (que usa screencap y socket)."""
        if not self._ensure_connection():
            return None

        for attempt in range(3):
            try:
                # adbutils.device.screenshot() devuelve una PIL Image
                pil_image = self.device.screenshot()
                
                # Convertir PIL a OpenCV (numpy array RGB -> BGR)
                open_cv_image = np.array(pil_image)
                # Convert RGB to BGR
                open_cv_image = open_cv_image[:, :, ::-1].copy() 
                
                return open_cv_image
            except Exception as e:
                # print(f"Error captura intento {attempt}: {e}")
                time.sleep(0.5)
            
        print("Error recuperando captura tras 3 intentos")
        return None

    def tap(self, x, y):
        """Alias for tap_robust."""
        self.tap_robust(x, y)

    def tap_robust(self, x, y):
        """
        Intenta hacer click usando SWIPE muy corto para saltarse la seguridad de Xiaomi.
        """
        # Swipe de 100ms
        self._run_command(["input", "swipe", str(x), str(y), str(x), str(y), "100"])

    def long_tap(self, x, y, duration=500):
        """Simula un toque largo con ligero movimiento (jitter)."""
        x2 = x + 3
        y2 = y + 3
        self._run_command(["input", "swipe", str(x), str(y), str(x2), str(y2), str(duration)])

    def swipe(self, x1, y1, x2, y2, duration=300):
        self._run_command(["input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)])

    def input_keyevent(self, keycode):
        """Envía un evento de tecla."""
        try:
            if self._ensure_connection():
                self.device.keyevent(keycode)
        except Exception as e:
            print(f"Error enviando keyevent {keycode}: {e}")

    def stop_app(self, package_name):
        try:
            if self._ensure_connection():
                self.device.app_stop(package_name)
        except Exception as e:
            print(f"Error parando app {package_name}: {e}")

    def start_app(self, package_name):
        # adbutils tiene app_start, pero a veces requiere activity exacta.
        # Fallback a monkey si adbutils falla o intentar adbutils primero con un launch flag?
        # Usaremos monkey vía shell para mantener comportamiento previo robusto si no sabemos la Activity.
        self._run_command(["monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"])

    def get_current_package(self):
        """Detecta el paquete de la app en primer plano."""
        if not self._ensure_connection():
            return "UNKNOWN"
            
        try:
            return self.device.app_current().package
        except Exception:
            # Fallback a lógica manual si adbutils falla en ciertos dispositivos
            pass

        # Intento 1: dumpsys window
        out = self._run_command(["dumpsys", "window", "windows", "|", "grep", "mCurrentFocus"])
        if out:
            match = re.search(r'\b([a-zA-Z0-9_\.]+)/', out)
            if match:
                return match.group(1)

        # Intento 2: dumpsys activity
        out = self._run_command(["dumpsys", "activity", "activities", "|", "grep", "ResumedActivity"])
        if out:
             match = re.search(r'\b([a-zA-Z0-9_\.]+)/', out)
             if match:
                 return match.group(1)
                 
        return "UNKNOWN"
