import time
import os
import subprocess
import datetime
import random
import cv2
# pyautogui removed
from config import *
from adb_wrapper import ADBWrapper
from vision import Vision
from ocr import OCR
from logger import GoldLogger

class RealRacingBot:
    def __init__(self, stop_event=None, log_callback=None, image_callback=None, stats_callback=None):
        self.adb = ADBWrapper()
        self.vision = Vision()
        self.ocr = OCR()
        self.logger = GoldLogger()
        self.current_timezone_state = "MADRID" 
        self.last_screen_shape = None # To store (height, width) of the last screenshot
        
        # Session Params for Stats
        self.session_start = time.time()
        self.session_ads = 0
        self.session_gold = 0
        self.last_reward_time = 0 # Debounce for rewards

        # UI Callbacks
        self.stop_event = stop_event
        self.log_callback = log_callback
        self.image_callback = image_callback
        self.stats_callback = stats_callback

        # Cargar stats iniciales
        if self.stats_callback:
            t_gold = self.logger.get_todays_gold() or 0
            h_gold = self.logger.get_all_time_gold() or 0
            
            self.stats_callback(
                int(t_gold), 
                int(h_gold),
                0.0,
                0.0
            )
            
        # Verificar calibración (REMOVED)
        # if not DESKTOP_CALIBRATION["enabled"]:
        #    self.log("ADVERTENCIA: No hay calibración. Los clicks no funcionarán bien.")

    def log(self, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {message}"
        print(full_msg)
        if self.log_callback:
            self.log_callback(full_msg)

    def update_live_view(self, image):
        if self.image_callback:
            self.image_callback(image)

    def is_stopped(self):
        if self.stop_event and self.stop_event.is_set():
            return True
        return False

    def is_within_time_window(self):
        now = datetime.datetime.now()
        return START_HOUR <= now.hour < END_HOUR
        
    def device_tap(self, x, y, duration=None):
        """
        Realiza un click directo en las coordenadas del dispositivo usando ADB.
        No requiere conversión ni calibración si las coordenadas vienen de la screenshot.
        """
        self.log(f"ADB Tap en ({int(x)}, {int(y)})")
        if duration and duration > 0.1:
             self.adb.long_tap(x, y, int(duration * 1000))
        else:
             self.adb.tap(x, y)

    def _search_country(self, term):
        """Busca país usando lupa. Retorna True si éxito."""
        self.log(f"🔎 Buscando País '{term}'...")
        # 1. Buscar Lupa
        scr = self.adb.take_screenshot()
        match = self.vision.find_template(scr, os.path.join(ASSETS_DIR, SEARCH_ICON_TEMPLATE))
        
        if match:
            cx, cy, w, h = match
            click_x = cx + w + 50
            self.device_tap(click_x, cy)
            time.sleep(0.5) 
            
            self.adb._run_command(["input", "text", term])
            time.sleep(1.0) 
            
            # Buscar resultado
            scr = self.adb.take_screenshot()
            results = self.ocr.get_screen_texts(scr, min_y=250)
            
            # Exacto
            for text, x, y, w, h in results:
                if text.upper() == term.upper():
                    self.log(f"✅ País Exacto '{text}' ({x},{y}). Click.")
                    self.device_tap(x+w//2, y+h//2)
                    return True
            
            # Parcial
            for text, x, y, w, h in results:
                if term.upper() in text.upper():
                     self.log(f"✅ País Parcial '{text}' ({x},{y}). Click.")
                     self.device_tap(x+w//2, y+h//2)
                     return True
                     
            self.log(f"❌ No encontré país '{term}' en resultados.")
            return False
            
        else:
            self.log("⚠ No veo lupa. Intentando click directo...")
            return self._click_city_direct(term)

    def _click_city_direct(self, name):
        """Busca texto en pantalla (City) y pulsa."""
        self.log(f"Buscando '{name}' en pantalla...")
        scr = self.adb.take_screenshot()
        
        # Exacto (Prioridad)
        coords = self.ocr.find_text(scr, name, exact_match=True)
        if coords:
            self.log(f"✅ Click directo '{name}' {coords}")
            self.device_tap(*coords)
            return True
            
        # Parcial (Fallback, útil para Madrid que puede estar rodeado)
        coords = self.ocr.find_text(scr, name, exact_match=False)
        if coords:
            self.log(f"✅ Click directo parcial '{name}' {coords}")
            self.device_tap(*coords)
            return True
            
        self.log(f"❌ No veo '{name}' en pantalla.")
        return False

    def perform_timezone_switch(self, target_zone_name):
        """
        Cambia la zona horaria usando lógica de Máquina de Estados (State-Aware).
        Analiza la pantalla en cada paso para saber qué hacer.
        """
        # Mapeo de zonas
        TARAWA = "Pacific/Tarawa"
        MADRID = "Europe/Madrid"
        
        target_country = "Kiribati"
        target_city = "Kiritimati"
        search_term = "Kiribati"
        
        if target_zone_name == "MADRID":
            target_country = "Espana" # o España
            target_city = "Madrid"
            search_term = "Espa" # "Espana" a veces no sale si escribes ñ
        
        self.log(f"⚡ Cambiando zona horaria a {target_zone_name} (S-Aware)...")
        # 1. Lanzar Ajustes
        self.adb._run_command(["am", "start", "-a", "android.settings.DATE_SETTINGS"])
        time.sleep(1.5) # Espera inicial
        
        max_steps = 15
        for step in range(max_steps):
            scr = self.adb.take_screenshot()
            if scr is None:
                self.log("❌ Error capturando pantalla. Reintentando...")
                time.sleep(1.0)
                continue

            all_texts = self.ocr.get_screen_texts(scr)
            full_str = " ".join([t[0].lower() for t in all_texts])
            
            self.log(f"--- Paso {step+1}/{max_steps} ---")
            
            # --- LÓGICA DE ESTADOS ---
            
            # 1. FINAL: ¿Vemos la Ciudad Objetivo?
            city_found = False
            for (txt, x, y, w, h) in all_texts:
                if target_city.lower() in txt.lower():
                    self.log(f"📍 ESTADO: Ciudad '{target_city}' encontrada.")
                    self.device_tap(x + w//2, y + h//2)
                    self.log("✅ CLICK FINAL. Zona cambiada.")
                    time.sleep(1.0) # Esperar cierre menú
                    
                    # Volver al juego
                    self.adb.input_keyevent(3) # Home
                    self.adb._run_command(["am", "start", "-a", "android.intent.action.MAIN", "-n", f"{PACKAGE_NAME}/.MainActivity"])
                    time.sleep(2.0)
                    return True

            # 2. RESULTADO BÚSQUEDA PAÍS: ¿Vemos el País Objetivo?
            country_candidate = None
            for (txt, x, y, w, h) in all_texts:
                if search_term.lower() in txt.lower():
                    if y > 250: # Filtrar header/input
                        country_candidate = (txt, x, y, w, h)
                        break
            
            if country_candidate:
                self.log(f"📍 ESTADO: País '{country_candidate[0]}' encontrado.")
                self.device_tap(country_candidate[1] + country_candidate[3]//2, country_candidate[2] + country_candidate[4]//2)
                time.sleep(2.0) # Esperar carga ciudad
                continue 

            # 3. Lista de Zonas ("Seleccionar zona horaria")
            # Identificamos por título y botón Región
            is_zone_list = "seleccionar" in full_str and "zona" in full_str
            region_btn = None
            
            if is_zone_list:
                # Buscar botón "Región" (abajo)
                candidates = [c for c in all_texts if "regi" in c[0].lower()]
                if candidates:
                    candidates.sort(key=lambda c: c[2]) # Orden Y
                    region_btn = candidates[-1]

            if is_zone_list and region_btn:
                self.log("📍 ESTADO: Menú Intermedio (Lista Zonas). Click 'Región'.")
                self.device_tap(region_btn[1] + region_btn[3]//2, region_btn[2] + region_btn[4]//2)
                time.sleep(2.0)
                continue

            # 4. Main Settings ("Fecha y hora")
            is_main = ("fecha" in full_str or "hora" in full_str) and "autom" in full_str
            
            if is_main:
                self.log("📍 ESTADO: Menú Principal.")
                # Buscar "Zona"
                candidates = [c for c in all_texts if "zona" in c[0].lower() or "time" in c[0].lower()]
                # Filtrar linea de Automática
                autom_y = next((c[2] for c in all_texts if "autom" in c[0].lower()), None)
                
                valid_candidates = []
                for c in candidates:
                     if autom_y and abs(c[2] - autom_y) < 80: continue
                     valid_candidates.append(c)
                
                valid_candidates.sort(key=lambda c: c[2])
                
                target = None
                if len(valid_candidates) >= 3:
                     target = valid_candidates[2]
                elif valid_candidates:
                     target = valid_candidates[-1]
                     
                if target:
                    self.log(f"👉 Click Zona (Candidato Y={target[2]})")
                    self.device_tap(target[1] + target[3]//2, target[2] + target[4]//2)
                    time.sleep(2.0)
                    continue
                else:
                    self.log("⚠ En Main pero sin botón Zona claro. Click fallback.")
                    self.device_tap(540, 1500)
                    time.sleep(2.0)
                    continue

            # 5. Fallback: Asumir Lista Regiones -> Buscar
            # Si no es nada de lo anterior, probablemente estamos en la lista de paises pero no leímos el título
            self.log("📍 ESTADO: Desconocido (¿Lista Regiones?). Click Lupa y Escribir.")
            
            # Click Lupa Top-Right (Hardcoded coords as fallback)
            # O buscar texto "Buscar"
            search_icon = next((c for c in all_texts if "search" in c[0].lower() or "buscar" in c[0].lower()), None)
            
            if search_icon:
                 self.device_tap(search_icon[1] + search_icon[3]//2, search_icon[2] + search_icon[4]//2)
            else:
                 self.device_tap(980, 160) # Top Right Blind
            
            time.sleep(1.0)
            self.log(f"⌨ Escribiendo '{search_term}'...")
            self.adb._run_command(["input", "text", search_term])
            time.sleep(2.5) # Esperar resultados
            continue
            
        self.log("❌ Timeout: No se pudo completar el cambio de zona.")
        return False

    def _wait_click_country_result(self, term):
        """Busca el resultado del país en OCR con retries cortos."""
        for _ in range(10): # Aumentado a 10 intentos (~3-4s máx)
            scr = self.adb.take_screenshot()
            results = self.ocr.get_screen_texts(scr, min_y=250)
            
            # Exacto
            for text, x, y, w, h in results:
                if text.upper() == term.upper():
                    self.device_tap(x+w//2, y+h//2)
                    return True
            # Parcial
            for text, x, y, w, h in results:
                if term.upper() in text.upper():
                     self.device_tap(x+w//2, y+h//2)
                     return True
            time.sleep(0.3)
        return False



    def _wait_and_click_text(self, text, timeout=5):
        start = time.time()
        while time.time() - start < timeout:
            scr = self.adb.take_screenshot()
            coords = self.ocr.find_text(scr, text)
            if coords:
                self.log(f"Texto '{text}' encontrado en {coords}. Click.")
                self.device_tap(*coords)
                time.sleep(1.5)
                return True
            time.sleep(0.5)
        return False

    def _wait_and_click_template(self, template_name, timeout=5):
        start = time.time()
        while time.time() - start < timeout:
            scr = self.adb.take_screenshot()
            match = self.vision.find_template(scr, os.path.join(ASSETS_DIR, template_name))
            if match:
                self.log(f"Icono '{template_name}' encontrado en {match[:2]}. Click.")
                self.device_tap(match[0], match[1])
                time.sleep(1.5)
                return True
            # Fallback: OCR de "Search" o "Buscar"? (Opcional)
            time.sleep(0.5)
        return False

    def handle_reward_screen(self):
        """Intenta detectar y leer la pantalla de recompensa."""
        self.log("Buscando pantalla de recompensa...")
        screen = self.adb.take_screenshot()
        self.last_screen_shape = screen.shape # Save resolution
        self.update_live_view(screen)
        
        # Incrementar contador de anuncios vistos en esta sesión
        self.session_ads += 1
        
        # Debounce check: Ignorar si ocurrio hace menos de 10s
        if time.time() - self.last_reward_time < 10:
            self.log(f"⚠ Recompensa ignorada (Debounce active: {time.time() - self.last_reward_time:.1f}s)")
            return

        # Intentar leer oro
        gold = self.ocr.extract_gold_amount(screen)
        if gold > 0:
            self.log(f"¡RECOMPENSA LEÍDA: {gold} ORO!")
            self.logger.log_gold(gold)
            self.session_gold += gold
            self.last_reward_time = time.time()

        # Calcular velocidad (Ads/Hour y Gold/Hour)
        elapsed = time.time() - self.session_start
        ads_per_hour = 0
        gold_per_hour = 0
        if elapsed > 0:
            hours = elapsed / 3600.0
            ads_per_hour = self.session_ads / hours
            gold_per_hour = self.session_gold / hours
        
        # Actualizar UI siempre (aunque no haya oro, hubo anuncio)
        if self.stats_callback:
            t_gold = self.logger.get_todays_gold() or 0
            h_gold = self.logger.get_all_time_gold() or 0
            
            self.stats_callback(
                int(t_gold),
                int(h_gold),
                ads_per_hour,
                gold_per_hour
            )
        
        # Buscar la X de cierre de recompensa (iterar variantes)
        match = None
        for template_name in REWARD_CLOSE_TEMPLATES:
            full_path = os.path.join(ASSETS_DIR, template_name)
            match = self.vision.find_template(screen, full_path)
            if match:
                self.log(f"Botón cerrar recompensa encontrado ({template_name}).")
                break
        
        if match:
            x, y, w, h = match
            self.device_tap(x, y)
        else:
            self.log("No hallé botón recompensa. Click seguridad (Top-Left).")
            # Click al 10% x 10%
            if screen is not None:
                h, w = screen.shape[:2]
                self.device_tap(int(w*0.1), int(h*0.1))
            
        time.sleep(2)

    def interact_with_coin(self, screenshot, coin_match):
        """Dibuja debug y hace click en la moneda."""
        cx, cy, w, h = coin_match
        
        # --- DEBUG DRAWING ---
        top_left = (cx - w//2, cy - h//2)
        bottom_right = (cx + w//2, cy + h//2)
        debug_img = screenshot.copy()
        cv2.rectangle(debug_img, top_left, bottom_right, (0, 255, 0), 3)
        # Guardar para el usuario
        cv2.imwrite("debug_last_click.png", debug_img)
        self.update_live_view(debug_img)
        # ---------------------

        # Usar toque largo (200ms) para asegurar
        self.device_tap(cx, cy, duration=0.2)
        self.log(f"✅ Click Moneda ({cx}, {cy}).")

    def process_active_ad(self):
        """
        Monitorea un anuncio activo: espera a que salga la X, gestiona falsos positivos,
        detecta congelamientos y finalmente cierra el anuncio.
        """
        self.log("🔁 Procesando anuncio activo/cerrando...")
        start_wait = time.time()
        ad_finished = False
        ignored_zones = [] # Lista de zonas (x,y,radio) donde hemos encontrado X falsas
        
        # Variables for stall detection
        last_frame_hash = None
        stall_streak = 0
        black_screen_start = 0
        
        while time.time() - start_wait < 65: # Timeout generoso
            if self.is_stopped(): return False

            screenshot = self.adb.take_screenshot()
            self.last_screen_shape = screenshot.shape
            self.update_live_view(screenshot)
            
            # --- STALL DETECTION (Imagen congelada) ---
            curr_gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
            # Usamos un resize pequeño para hash rápido y tolerante a ruido
            curr_small = cv2.resize(curr_gray, (32, 32)) 
            
            if last_frame_hash is not None:
                # Comparar diferencia
                diff = cv2.absdiff(curr_small, last_frame_hash)
                non_zero = cv2.countNonZero(diff)
                
                if non_zero < 50: # Muy pocas diferencias
                    stall_streak += 1
                    self.log(f"Imagen estática detectada ({stall_streak}/2)...")
                else:
                    stall_streak = 0
            
            stall_detected = (stall_streak >= 2)
            last_frame_hash = curr_small
            # ------------------------------------------

            # 1. Detección Dinámica de X (Forma) con Ignored Zones
            match_dynamic = self.vision.find_close_button_dynamic(screenshot, ignored_zones=ignored_zones)
            
            if match_dynamic:
                # Si encontramos una NUEVA X (o una no ignorada), reseteamos el stall
                stall_streak = 0 
                
                cx, cy, w, h = match_dynamic
                self.log(f"Posible botón cerrar en {cx},{cy}.")
                
                # Click tentativo
                self.device_tap(cx, cy, duration=0.2)
                time.sleep(2) # Esperar reacción
                
                # VERIFICAR SI FUE UN FALSO POSITIVO (Aparece "Seguir Viendo")
                screen_after = self.adb.take_screenshot()
                self.update_live_view(screen_after)
                
                resume_match = self.vision.find_template(screen_after, os.path.join(ASSETS_DIR, AD_RESUME_TEMPLATE))
                if resume_match:
                    # ES UN FALSO CIERRE
                    rx, ry, rw, rh = resume_match
                    self.log("¡Falso cierre detectado! Apareció 'Seguir Viendo'.")
                    
                    # 1. Resumir la reproducción
                    self.device_tap(rx, ry)
                    
                    # 2. Ignorar esta zona en el futuro
                    ignored_radius = max(w, h) + 20 # Radio generoso
                    ignored_zones.append((cx, cy, ignored_radius))
                    self.log(f"Zona {cx},{cy} (r={ignored_radius}) añadida a lista negra. Reanudando espera...")
                    
                    time.sleep(2) # Dejar que el video continue
                    continue # Volver al bucle principal
                
                else:
                    # 2. CHECK: ¿Nos ha sacado del juego? (Fake X que abre Play Store)
                    if self.ensure_game_context():
                        self.log("¡Falso cierre detectado! Me sacó del juego (Play Store/Browser).")
                        # La función ensure_game_context ya nos ha devuelto al juego
                        
                        # 3. Ignorar esta zona en el futuro
                        ignored_radius = max(w, h) + 20
                        ignored_zones.append((cx, cy, ignored_radius))
                        self.log(f"Zona {cx},{cy} (r={ignored_radius}) añadida a lista negra. Esperando recuperación...")
                        
                        time.sleep(3) # Esperar a que el juego repinte
                        continue

                    # FUE UN CIERRE VALIDO (O al menos no salió el cartel de aviso ni nos sacó)
                    self.log("Parece un cierre válido.")
                    self.handle_reward_screen()
                    ad_finished = True
                    break
            elif stall_detected and len(ignored_zones) > 0:
                # SOLO si está congelado Y no encontramos ninguna X nueva
                self.log("⚠ Anuncio CONGELADO y sin nuevas X. Reseteando zonas ignoradas.")
                ignored_zones = []
                stall_streak = 0
                continue
            
            # --- BLACK SCREEN CHECK ---
            avg_color = cv2.mean(screenshot)[0]
            if avg_color < 5: # Muy oscuro
                if black_screen_start == 0:
                    black_screen_start = time.time()
                elif time.time() - black_screen_start > 10:
                    self.log("⚫ ERROR: Pantalla negra persistente (>10s). Reiniciando juego...")
                    self.adb.stop_app(PACKAGE_NAME)
                    time.sleep(1)
                    return False # Salir del loop de anuncio (el outer loop relanzará el juego)
            else:
                black_screen_start = 0
            # ---------------------------

            # 2. X de reward directa (iterar variantes) y FAST FORWARD
            match_reward = None
            
            # 2. X de reward directa (iterar variantes)
            match_reward = None
            for t_name in REWARD_CLOSE_TEMPLATES:
                match_reward = self.vision.find_template(screenshot, os.path.join(ASSETS_DIR, t_name))
                if match_reward: break
                
            if match_reward:
                self.log("Anuncio se cerró solo (Detectado reward close).")
                self.handle_reward_screen()
                ad_finished = True
                break
            
            # --- 3. [NEW] Detección de Anuncios Web/Consentimiento (Requieren BACK) ---
            if self.handle_web_consent(screenshot):
                # Check rápido si salió (opcional, el loop lo captará)
                continue
            # --------------------------------------------------------------------------
            
            time.sleep(2)
            
        if not ad_finished:
            self.log("Timeout anuncio. Back de emergencia.")
            # Último recurso: OCR a texto completo por si dice "Cerrar"
            # (Omitido o simplificado, el back suele bastar)
            self.adb.input_keyevent(4) # BACK de emergencia
            return False
        
        return True

    def check_device_timezone(self):
        """Verifica la zona horaria actual del dispositivo."""
        try:
            # date +%z devuelve +0100, +0200, +1400 etc
            output = self.adb._run_command(["date", "+%z"], timeout=5)
            if output:
                tz_offset = output.strip()
                self.log(f"Zona horaria detectada: {tz_offset}")
                if "+1400" in tz_offset:
                    return "KIRITIMATI"
                return "MADRID"
        except Exception as e:
            self.log(f"Error check timezone: {e}")
        return "UNKNOWN"

    def handle_timezone_cycle(self):
        """
        Ejecuta el ciclo 'The Kiritimati Trick':
        1. Ir a Kiritimati.
        2. Esperar moneda (SIN CLICK).
        3. Volver a Madrid.
        4. Esperar moneda (CLICK).
        """
        self.log("🔄 Iniciando Ciclo de Cambio de Zona (No More Gold detected)...")
        
        # 1. Kiritimati
        if self.perform_timezone_switch("KIRITIMATI"):
             self.log("✅ Switch Kiritimati OK.")
        else:
             self.log("⚠ Switch Kiritimati completado (o timeout), forzando vuelta al juego...")
        
        # SAFETY: Siempre asegurar que volvemos al juego antes de esperar
        self.ensure_game_context()
        
        self.log("Esperando moneda en Kiritimati (SIN TOCAR)...")
        found_coin = False
        start_wait = time.time()
        while time.time() - start_wait < 30:
            if self.is_stopped(): return
            scr = self.adb.take_screenshot()
            self.update_live_view(scr)
            if self.vision.find_template(scr, os.path.join(ASSETS_DIR, COIN_ICON_TEMPLATE)):
                found_coin = True
                self.log("✅ Moneda detectada en Kiritimati.")
                break
            time.sleep(1)
            
        if not found_coin:
            self.log("⚠ No apareció moneda en Kiritimati. ¿Quizás volver a Madrid?")
            # Procedemos a Madrid de todas formas por seguridad
            
        # 2. Madrid
        if self.perform_timezone_switch("MADRID"):
             self.log("✅ Switch Madrid OK.")
        
        # SAFETY
        self.ensure_game_context()
        
        self.log("Regresado a Madrid. Listo para continuar.")

    def handle_web_consent(self, screenshot):
        """
        Detección de anuncios tipo Web/Consentimiento (Cookies, Preferencias, etc).
        Retorna True si realizó acción (Click Back).
        """
        # Palabras clave fuertes
        web_keywords = ["cookies", "preferencias", "aviso", "consent"]
        
        # Usar get_lines para scan rápido
        lines = self.ocr.get_lines(screenshot)
        full_text_lower = " ".join(lines).lower()
        
        # Contar palabras (aproximado)
        word_count = len(full_text_lower.split())
        
        found_keyword = next((k for k in web_keywords if k in full_text_lower), None)
        
        if found_keyword and word_count > 50:
            self.log(f"⚠ Detectado anuncio Web/Consentimiento (keyword: '{found_keyword}', words: {word_count}).")
            self.log("👉 Ejecutando acción: BOTÓN ATRÁS (Back).")
            self.adb.input_keyevent(4) # KEYCODE_BACK
            time.sleep(2.0) # Esperar a que el sistema reaccione
            return True
            
        return False

    def handle_google_survey(self, screenshot):
        """
        Maneja la encuesta de Google en 2 pasos:
        1. Click en 'X' (Arriba izquierda) si detecta 'Google'/'Encuesta'.
        2. Click en 'Saltar' si aparece el botón.
        Retorna True si realizó alguna acción.
        """
        # 1. Buscar botón 'Saltar' (Paso 2)
        # Usamos OCR para leer texto
        # Optimizamos buscando en la mitad inferior o todo
        
        # Primero leemos todo el texto para contexto
        text_lines = self.ocr.get_lines(screenshot)
        full_text = " ".join(text_lines).lower()
        
        # Solo buscamos 'Saltar' si parece una encuesta/anuncio de Google
        # Keywords: google, encuesta, recompensa, survey, reward
        context_keywords = ["google", "encuesta", "recompensa", "survey", "reward", "tecnologia"]
        is_google_context = any(k in full_text for k in context_keywords)
        
        if is_google_context:
            saltar_pos = self.ocr.find_text(screenshot, "Saltar", case_sensitive=True)
            if saltar_pos:
                self.log(f"Encuesta Google: Botón 'Saltar' detectado en {saltar_pos} (Contexto Validado). Click.")
                self.device_tap(saltar_pos[0], saltar_pos[1])
                time.sleep(2)
                return True

        # 2. Buscar Pantalla 1 ('tecnologia de Google' o 'encuesta')
        # Buscamos keywords
        text_lines = self.ocr.get_lines(screenshot)
        full_text = " ".join(text_lines).lower()
        
        if "google" in full_text and ("encuesta" in full_text or "tecnologia" in full_text or "technology" in full_text):
            self.log("Encuesta Google: Detectada pantalla inicial.")
            
            # Intentar buscar la 'X' específicamente
            x_pos = self.ocr.find_text(screenshot, "X", exact_match=True)
            
            if x_pos and x_pos[1] < 200 and x_pos[0] < 300: # X debe estar arriba izquierda
                self.log(f"Encuesta Google: Click en 'X' encontrada por OCR en {x_pos}.")
                self.device_tap(x_pos[0], x_pos[1])
            else:
                self.log("Encuesta Google: 'X' no leída, usando click ciego en (170, 80).")
                self.device_tap(170, 80)
                
            time.sleep(2)
            return True
            
        return False

    def ensure_game_context(self):
        """
        Verifica que el juego esté en primer plano. 
        Si está en Ajustes u otra app, intenta restaurar el juego.
        Retorna True si tuvo que corregir el contexto (requiere espera).
        """
        current_pkg = self.adb.get_current_package()
        
        # Caso Ideal
        if current_pkg == PACKAGE_NAME:
            return False 
            
        # Ignorar si es "UNKNOWN" momentáneo (buffer de adb)
        if current_pkg == "UNKNOWN":
            return False

        self.log(f"⚠ Contexto incorrecto detectado: '{current_pkg}'")
        
        # 1. Atrapado en Ajustes (Crash durante cambio de zona)
        if "settings" in current_pkg:
            self.log("Atrapado en Ajustes. Cerrando y volviendo al juego...")
            self.adb.stop_app(current_pkg) # Force stop settings
            self.adb.start_app(PACKAGE_NAME)
            return True
            
        # 2. Launcher o cualquier otra App
        self.log(f"App fuera de foco. Lanzando {PACKAGE_NAME}...")
        self.adb.start_app(PACKAGE_NAME)
        return True

    def run(self):
        self.log("Iniciando Bot Real Racing 3 (State-Aware)...")
        if not self.adb.connect():
            self.log("Error: Dispositivo no conectado.")
            self.stop_event.set()
            return

        # Verificar si el juego está corriendo
        self.log(f"Verificando estado de {PACKAGE_NAME}...")
        if self.adb.get_current_package() != PACKAGE_NAME:
             self.log("🚀 Juego no detectado en primer plano. Lanzando...")
             self.adb.start_app(PACKAGE_NAME)
             
             # Esperar a que abra
             game_open = False
             for _ in range(35): # Aumentado a 35s por carga lenta
                 if self.is_stopped(): return
                 time.sleep(1)
                 if self.adb.get_current_package() == PACKAGE_NAME:
                     game_open = True
                     self.log("✅ Juego detectado en primer plano.")
                     break
            
             if not game_open:
                 self.log("⚠ El inicio estándar tardó. Intentando lanzamiento forzado...")
                 # Fallback: am start directo a la actividad principal (intento)
                 # Nota: .MainActivity suele ser el default, pero si falla no pasa nada grave
                 self.adb._run_command(["am", "start", "-n", f"{PACKAGE_NAME}/.MainActivity"])
                 time.sleep(5)
        else:
             self.log("✅ Juego ya estaba abierto. Continuando...")
             
        time.sleep(2) # Estabilización
        
        # Inicializar estado de zona horaria
        current_tz = self.check_device_timezone()
        if current_tz != "UNKNOWN":
            self.current_timezone_state = current_tz
        self.log(f"Estado Inicial Zona: {self.current_timezone_state}")

        last_restricted_log_time = 0

        while not self.is_stopped():
            # 0. Chequeo de Contexto Global (Rescue)
            if self.ensure_game_context():
                time.sleep(3) # Esperar a que el juego cargue/vuelva
                continue

            # Time Check (00:00 - 12:00)
            now_hour = datetime.datetime.now().hour
            restricted_mode = (0 <= now_hour < 12)

            if restricted_mode and (time.time() - last_restricted_log_time > 300): # Log cada 5 min
                self.log("🕒 MODO RESTRINGIDO (00-12h): Proceso no disponible hasta las 12. Solo recolección visible.")
                last_restricted_log_time = time.time()

            # 1. Capturar estado
            screenshot = self.adb.take_screenshot()
            if screenshot is None:
                self.log("Error capturando pantalla. Reintentando...")
                time.sleep(2)
                continue
            
            self.last_screen_shape = screenshot.shape
            self.update_live_view(screenshot)

            # 2. Máquina de Estados Reactiva (Prioridad)
            
            # Z) PRIORIDAD: Check especial Encuesta Google (Saltar)
            # Si aparece el diálogo "Saltar", debemos pulsarlo antes de cualquier otra X
            if self.handle_google_survey(screenshot):
                 self.log("Encuesta gestionada (Prioridad). Continuando...")
                 continue

            # Z.1) PRIORIDAD: Check especial Web/Consentimiento (Back)
            if self.handle_web_consent(screenshot):
                 time.sleep(2) # Esperar tras back
                 continue
            
            # A) Pantalla Intermedia (Confirmar Anuncio)
            match_inter = self.vision.find_template(screenshot, os.path.join(ASSETS_DIR, INTERMEDIATE_TEMPLATE))
            if match_inter:
                self.log("Detectada Pantalla Intermedia. Confirmando...")
                cx, cy, w, h = match_inter
                match_conf = self.vision.find_template(screenshot, os.path.join(ASSETS_DIR, AD_CONFIRM_TEMPLATE))
                
                if match_conf:
                    bx, by, bw, bh = match_conf
                    self.device_tap(bx, by)
                else:
                    self.device_tap(cx, cy)
                
                time.sleep(3) # Esperar a que arranque anuncio y dejar que el próximo loop detecte "Nada" o "X"
                continue

            # B) Sin Oro (Iniciar Ciclo Timezone O Parar/Esperar)
            match_no_gold = self.vision.find_template(screenshot, os.path.join(ASSETS_DIR, NO_MORE_GOLD_TEMPLATE))
            if match_no_gold:
                if restricted_mode:
                    self.log("⏳ MODO RESTRINGIDO: 'No More Gold' detectado. Pausando hasta las 12:00...")
                    while datetime.datetime.now().hour < 12:
                        if self.is_stopped(): return
                        for _ in range(60): 
                            if self.is_stopped(): return
                            time.sleep(1)
                        self.log(f"💤 Esperando a las 12:00... (Actual: {datetime.datetime.now().strftime('%H:%M')})")
                    
                    self.log("⏰ ¡Horario desbloqueado! Reanudando operaciones.")
                
                self.log("Detectado 'No hay más anuncios'. Iniciando truco Kiritimati...")
                self.handle_timezone_cycle()
                continue
                
            # C) Moneda Normal
            match_coin = self.vision.find_template(screenshot, os.path.join(ASSETS_DIR, COIN_ICON_TEMPLATE))
            if match_coin:
                # Verificar timezone actual real (Seguridad detectada en loop)
                real_tz = self.check_device_timezone()
                if real_tz == "KIRITIMATI":
                     self.log("⚠ Moneda visible pero estamos en KIRITIMATI. Cambiando a MADRID...")
                     self.perform_timezone_switch("MADRID")
                     continue
                
                # Click en moneda (No bloqueante)
                self.interact_with_coin(screenshot, match_coin)
                time.sleep(1.5) # Esperar transición a Intermedia o Reward
                continue

            # D) Recompensa atrapada (Check preventivo)
            # Primero chequear si ya estamos en la recompensa para evitar falsos positivos de FF/X
            match_reward = None
            for template_name in REWARD_CLOSE_TEMPLATES:
                full_path = os.path.join(ASSETS_DIR, template_name)
                match_reward = self.vision.find_template(screenshot, full_path)
                if match_reward: break
            
            if match_reward:
                self.log("Detectado cierre de recompensa (Check Prioritario).")
                self.handle_reward_screen()
                continue

            # E) Anuncio Activo (X Visible)
            match_x = self.vision.find_close_button_dynamic(screenshot)
            if match_x:
                self.log("Detectada 'X' de anuncio. Retomando cierre de anuncio...")
                self.process_active_ad()
                continue

            # F) Fast Forward (Solo si NO hay X)
            match_ff = self.vision.find_fast_forward_button(screenshot)
            if match_ff:
                 self.log("Detectado botón Fast Forward (>> - Dynamic). Click.")
                 self.device_tap(match_ff[0], match_ff[1])
                 time.sleep(2)
                 continue
                
            # Nada detectado

            # Nada detectado
            self.log("Esperando (Nada detectado)...")
            time.sleep(1.5)

if __name__ == "__main__":
    # Modo CLI Legacy (si se ejecuta directo)
    bot = RealRacingBot()
    bot.run()
