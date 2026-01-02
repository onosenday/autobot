import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
from PIL import Image, ImageTk
import cv2
import queue
import subprocess
import time
import json
import os
from datetime import datetime, timedelta
from adb_wrapper import ADBWrapper
from logger import GoldLogger
from ml.trainer import ModelTrainer
from ml.evaluator import ModelEvaluator
from ml.monitor import LiveMonitor
from i18n import t, get_current_language, set_language, get_supported_languages, get_language_name, register_language_change_callback


# Importamos la clase del bot (que refactorizaremos en breve)
# Importación diferida o asumiendo que main.py estará listo
try:
    from main import RealRacingBot
except ImportError:
    RealRacingBot = None

class BotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(t("app_title"))
        # Aumentado ancho a 1200 para acomodar las 3 columnas sin cortes
        self.root.geometry("1200x720")
        self.root.configure(bg="#102A43") # Match Theme BG
        
        self.adb_preview = ADBWrapper()
        self.is_bot_running = False
        
        self.bot_thread = None
        self.stop_event = threading.Event()
        self.log_queue = queue.Queue()
        self.image_queue = queue.Queue()
        
        self.bot_instance = None
        
        self.logo_photo = None
        try:
            # Robust Path Resolution
            base_dir = os.path.dirname(os.path.abspath(__file__))
            logo_path = os.path.join(base_dir, "assets", "app_logo.png")
            print(f"DEBUG: Intentando cargar logo desde: {logo_path}")
            
            if os.path.exists(logo_path):
                # UI Logo (Load Logic)
                pil_img = Image.open(logo_path)
                
                # Window Icon (Use PIL object)
                icon_photo = ImageTk.PhotoImage(pil_img)
                self.root.iconphoto(True, icon_photo)
                
                # Banner Logo (Resize Larger)
                pil_resized = pil_img.resize((100, 100), Image.Resampling.LANCZOS)
                self.logo_photo = ImageTk.PhotoImage(pil_resized)
                print("DEBUG: Logo cargado correctamente.")
            else:
                print(f"DEBUG: Logo NO encontrado en {logo_path}")
        except Exception as e:
            print(f"Error loading logo: {e}")

        self._apply_theme()
        self._setup_ui()
        self._start_queue_processing()
        
        # Hilo de preview constante
        self.preview_thread = threading.Thread(target=self._run_idle_preview, daemon=True)
        self.preview_thread.start()
        
        # Overlay Drawing State
        self.current_pil_image = None
        self.current_photo = None
        self.current_ratio = 1.0
        self.current_x_offset = 0
        self.current_y_offset = 0
        self.bg_image_id = None # ID for persistent background image

        # Session Data
        self.logger = GoldLogger()
        self.session_start_time = None
        self.session_initial_gold = 0
        self.current_session_gold = 0
        
        # Window Handles (Singleton)
        self.chart_window = None
        self.calendar_window = None
        # Window Handles (Singleton)
        self.chart_window = None
        self.calendar_window = None
        self.chart_offset = 0 # Offset de dias para la grafica
        
        # Click Visualization
        self.active_clicks = [] # Stores (x, y, timestamp)
        
        # ML Visualization
        self.latest_prediction = None # (is_correct, pred_label, confidence, timestamp)

    def _schedule_device_status_update(self):
        """Actualiza estado de batería, WiFi y brillo cada 30s."""
        try:
            # Batería
            level = self.adb_preview.get_battery_level()
            if level is not None:
                # 5 Niveles de Color para Batería
                if level < 20: color = "#FC8181"   # Red (Critical)
                elif level < 40: color = "#DD6B20" # Orange (Low)
                elif level < 60: color = "#F6E05E" # Yellow (Mid)
                elif level < 80: color = "#68D391" # Light Green (Good)
                else: color = "#38A169"            # Green (Full)
                
                self.lbl_battery.config(text=f"{level}%", fg=color)
            
            # WiFi
            wifi_status = self.adb_preview.is_wifi_enabled()
            if wifi_status is True:
                self.lbl_wifi.config(text="ON", fg="#68D391")  # Green
            elif wifi_status is False:
                self.lbl_wifi.config(text="OFF", fg="#FC8181")  # Red
            else:
                self.lbl_wifi.config(text="--", fg="#A0AEC0")
            
            # Brillo
            brightness = self.adb_preview.get_brightness()
            if brightness is not None:
                # Convertir 0-255 a porcentaje
                pct = int((brightness / 255) * 100)
                if pct < 10: color = "#68D391"   # Green (Low = good for battery)
                elif pct < 50: color = "#F6E05E" # Yellow
                else: color = "#FC8181"          # Red (High = draining battery)
                
                self.lbl_brightness.config(text=f"{pct}%", fg=color)
        except:
            pass
        self.root.after(30000, self._schedule_device_status_update)

    def _apply_theme(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Paleta "Night Blue"
        BG_MAIN = "#102A43"   # Deep Navy
        BG_PANEL = "#1E3246"  # Sidebar / Panel
        BG_CARD = "#243B53"   # Cards
        FG_TEXT = "#D9E2EC"   # Text
        ACCENT = "#334E68"
        BTN_BG = "#2B6CB0"    # Vivid Blue
        BTN_FG = "#FFFFFF"
        BTN_ACTIVE = "#3182CE"

        style.configure(".", background=BG_MAIN, foreground=FG_TEXT, font=("Segoe UI", 10))
        
        # Custom Frames
        style.configure("Main.TFrame", background=BG_MAIN)
        style.configure("Panel.TFrame", background=BG_PANEL)
        
        # Cards
        style.configure("Card.TLabelframe", background=BG_CARD, bordercolor=BG_MAIN, relief="flat")
        style.configure("Card.TLabelframe.Label", background=BG_CARD, foreground="#829AB1", font=("Segoe UI", 9, "bold"))
        
        # Labels
        style.configure("TLabel", background=BG_MAIN, foreground=FG_TEXT)
        style.configure("Panel.TLabel", background=BG_PANEL, foreground=FG_TEXT)
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"), foreground="#627D98", background=BG_PANEL)
        
        style.configure("Stat.TLabel", background=BG_PANEL, foreground="#829AB1", font=("Segoe UI", 8)) 
        style.configure("StatValue.TLabel", background=BG_PANEL, font=("Segoe UI", 14, "bold")) 
        style.configure("Status.TLabel", background=BG_PANEL, foreground="#48BB78", font=("Segoe UI", 11, "bold"))

        # Buttons
        style.configure("Action.TButton", padding=10, relief="flat", background=BTN_BG, foreground=BTN_FG, borderwidth=0, font=("Segoe UI", 10, "bold"))
        style.map("Action.TButton", background=[('active', BTN_ACTIVE)])
        
        style.configure("Small.TButton", padding=5, relief="flat", background=ACCENT, foreground=FG_TEXT, borderwidth=0, font=("Segoe UI", 8))

        # Combobox (para selector de idioma)
        style.configure("TCombobox",
                        fieldbackground=BG_CARD,
                        background=ACCENT,
                        foreground=FG_TEXT,
                        arrowcolor=FG_TEXT,
                        bordercolor=ACCENT,
                        lightcolor=BG_CARD,
                        darkcolor=BG_CARD,
                        insertcolor=FG_TEXT)
        style.map("TCombobox",
                  fieldbackground=[('readonly', BG_CARD)],
                  foreground=[('readonly', FG_TEXT)],
                  background=[('readonly', ACCENT)])

    def _setup_ui(self):
        # Master Container 3 Columnas
        main_container = ttk.Frame(self.root, style="Main.TFrame")
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # =========================================================================
        # COLUMNA 1: IZQUIERDA (CONTROL) (20%)
        # =========================================================================
        left_panel = ttk.Frame(main_container, style="Panel.TFrame", padding=15)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0,1))
        
        # LOGO / HEADER
        header_frame = tk.Frame(left_panel, bg="#1E3246") # Match Panel BG
        header_frame.pack(anchor=tk.W, pady=(0, 15))
        
        if self.logo_photo:
            tk.Label(header_frame, image=self.logo_photo, bg="#1E3246").pack(side=tk.LEFT, padx=(0, 10))
            
        self.lbl_header = ttk.Label(header_frame, text=t("header_title"), style="Header.TLabel", justify=tk.LEFT)
        self.lbl_header.pack(side=tk.LEFT)
        
        # DEVICE STATUS ROW (Battery, WiFi, Brightness)
        self.status_row = tk.Frame(left_panel, bg="#1E3246")
        self.status_row.pack(anchor=tk.W, pady=(0, 15))
        
        # Battery
        self.lbl_battery_label = tk.Label(self.status_row, text=t("battery_label"), fg="#829AB1", bg="#1E3246", font=("Segoe UI", 9))
        self.lbl_battery_label.pack(side=tk.LEFT)
        self.lbl_battery = tk.Label(self.status_row, text="--%", fg="#A0AEC0", bg="#1E3246", font=("Segoe UI", 9, "bold"))
        self.lbl_battery.pack(side=tk.LEFT)
        
        # Separator
        tk.Label(self.status_row, text="  │  ", fg="#4A5568", bg="#1E3246", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        
        # WiFi
        self.lbl_wifi_label = tk.Label(self.status_row, text=t("wifi_label"), fg="#829AB1", bg="#1E3246", font=("Segoe UI", 9))
        self.lbl_wifi_label.pack(side=tk.LEFT)
        self.lbl_wifi = tk.Label(self.status_row, text="--", fg="#A0AEC0", bg="#1E3246", font=("Segoe UI", 9, "bold"))
        self.lbl_wifi.pack(side=tk.LEFT)
        
        # Separator
        tk.Label(self.status_row, text="  │  ", fg="#4A5568", bg="#1E3246", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        
        # Brightness
        self.lbl_brightness_label = tk.Label(self.status_row, text=t("brightness_label"), fg="#829AB1", bg="#1E3246", font=("Segoe UI", 9))
        self.lbl_brightness_label.pack(side=tk.LEFT)
        self.lbl_brightness = tk.Label(self.status_row, text="--", fg="#A0AEC0", bg="#1E3246", font=("Segoe UI", 9, "bold"))
        self.lbl_brightness.pack(side=tk.LEFT)
        
        self._schedule_device_status_update()

        # LANGUAGE SELECTOR
        self.lang_frame = tk.Frame(left_panel, bg="#1E3246")
        self.lang_frame.pack(anchor=tk.W, pady=(0, 25))
        self.lbl_lang_section = tk.Label(self.lang_frame, text=t("language_section"), fg="#829AB1", bg="#1E3246", font=("Segoe UI", 8))
        self.lbl_lang_section.pack(anchor=tk.W)
        
        # Crear lista de idiomas para el combobox
        lang_names = [get_language_name(code) for code in get_supported_languages()]
        self.lang_combo = ttk.Combobox(self.lang_frame, values=lang_names, state="readonly", width=12)
        
        # Seleccionar idioma actual
        current_lang = get_current_language()
        current_idx = get_supported_languages().index(current_lang) if current_lang in get_supported_languages() else 0
        self.lang_combo.current(current_idx)
        self.lang_combo.pack(anchor=tk.W, pady=(5, 0))
        self.lang_combo.bind("<<ComboboxSelected>>", self._on_language_change)

        # CONTROL PRINCIPAL
        self.lbl_control_section = ttk.Label(left_panel, text=t("control_section"), style="Stat.TLabel")
        self.lbl_control_section.pack(anchor=tk.W, pady=(0,5))
        
        self.btn_start = ttk.Button(left_panel, text=t("btn_start"), command=self.start_bot, style="Action.TButton")
        self.btn_start.pack(fill=tk.X, pady=(0, 8))
        
        self.btn_stop = ttk.Button(left_panel, text=t("btn_stop"), command=self.stop_bot, state=tk.DISABLED, style="Action.TButton")
        self.btn_stop.pack(fill=tk.X, pady=(0, 20))
        
        # STATUS INDICATOR
        self.status_frame = tk.Frame(left_panel, bg="#1E3246")
        self.status_frame.pack(fill=tk.X, pady=(0, 20))
        self.lbl_status_section = tk.Label(self.status_frame, text=t("status_section"), fg="#829AB1", bg="#1E3246", font=("Segoe UI", 8))
        self.lbl_status_section.pack(anchor=tk.W)
        
        self.lbl_status = tk.Label(self.status_frame, text=t("status_inactive"), fg="#A0AEC0", bg="#1E3246", font=("Segoe UI", 12, "bold"))
        self.lbl_status.pack(anchor=tk.W)



        # CAPTURE BUTTON
        self.btn_capture = ttk.Button(left_panel, text=t("btn_capture"), command=self._capture_screen, style="Action.TButton")
        self.btn_capture.pack(fill=tk.X, pady=(0, 20))
        
        # ML NEURAL NET SECTION
        self.lbl_ml_section = ttk.Label(left_panel, text=t("ml_section"), style="Stat.TLabel")
        self.lbl_ml_section.pack(anchor=tk.W, pady=(10,5))
        
        ml_frame = tk.Frame(left_panel, bg="#1E3246")
        ml_frame.pack(fill=tk.X)
        
        # Buttons ML Grid
        self.btn_ml_train = tk.Button(ml_frame, text=t("btn_ml_train"), bg="#4A5568", fg="white", bd=0, command=self._ml_train, cursor="hand2")
        self.btn_ml_train.pack(fill=tk.X, pady=2)
        
        self.btn_ml_test = tk.Button(ml_frame, text=t("btn_ml_test"), bg="#38A169", fg="white", bd=0, command=self._ml_test, cursor="hand2")
        self.btn_ml_test.pack(fill=tk.X, pady=2)
        
        self.btn_ml_activate = tk.Button(ml_frame, text=t("btn_ml_activate"), bg="#805AD5", fg="white", bd=0, command=self._ml_toggle_monitor, cursor="hand2")
        self.btn_ml_activate.pack(fill=tk.X, pady=2)
        
        self.lbl_ml_status = tk.Label(ml_frame, text=t("ml_status_ready"), bg="#1E3246", fg="#718096", font=("Segoe UI", 8))
        self.lbl_ml_status.pack(anchor=tk.W, pady=(5,0))

        # =========================================================================
        # COLUMNA 2: CENTRO (VISION + LOGS) (55%)
        # =========================================================================
        center_panel = ttk.Frame(main_container, style="Main.TFrame", padding=15)
        center_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # LOGS HEADER
        log_header = tk.Frame(center_panel, bg="#102A43")
        log_header.pack(fill=tk.X, pady=(0, 5))
        self.lbl_log_header = tk.Label(log_header, text=t("log_header"), fg="#627D98", bg="#102A43", font=("Consolas", 10, "bold"))
        self.lbl_log_header.pack(side=tk.LEFT)
        
        # LOG AREA (Arriba)
        self.log_area = scrolledtext.ScrolledText(center_panel, height=12, state=tk.DISABLED, 
                                                  font=("Consolas", 10), 
                                                  bg="#0F2439", fg="#D9E2EC", 
                                                  relief="flat", padx=10, pady=10,
                                                  insertbackground="white")
        self.log_area.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        self._configure_log_tags()

        # LIVE VIEW HEADER
        view_header = tk.Frame(center_panel, bg="#102A43")
        view_header.pack(fill=tk.X, pady=(0, 5))
        self.lbl_preview_header = tk.Label(view_header, text=t("preview_header"), fg="#627D98", bg="#102A43", font=("Consolas", 10, "bold"))
        self.lbl_preview_header.pack(side=tk.LEFT)
        
        # PREVIEW CONTAINER (Abajo)
        # Ratio 16:9 for 640px width -> 360px height
        self.preview_frame = tk.Frame(center_panel, bg="#000000", width=640, height=360)
        self.preview_frame.pack(anchor=tk.CENTER)
        self.preview_frame.pack_propagate(False) # Force size
        
        self.canvas = tk.Canvas(self.preview_frame, width=640, height=360, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # =========================================================================
        # COLUMNA 3: DERECHA (METRICAS) (25%)
        # =========================================================================
        right_panel = ttk.Frame(main_container, style="Panel.TFrame", padding=15)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(1,0))
        
        self.lbl_stats_section = ttk.Label(right_panel, text=t("stats_section"), style="Stat.TLabel")
        self.lbl_stats_section.pack(anchor=tk.W, pady=(0,15))
        
        # SESSION TIMER
        self.lbl_runtime = self._create_stat_block(right_panel, t("stat_session_time"), "00:00:00", "#63B3ED")
        
        # GOLD SESSION
        self.lbl_gold = self._create_stat_block(right_panel, t("stat_session_gold"), "0", "#F6E05E")
        
        # GOLD RATE
        self.lbl_gold_speed = self._create_stat_block(right_panel, t("stat_gold_rate"), "0", "#F6E05E")
        
        # ADS RATE
        self.lbl_speed = self._create_stat_block(right_panel, t("stat_ads_rate"), "0.0", "#63B3ED")
        
        # TOTAL HISTORY
        self.lbl_gold_history = self._create_stat_block(right_panel, t("stat_total_history"), "--", "#CBD5E0")
        
        # GRAPHS & CALENDAR
        btn_frame = tk.Frame(right_panel, bg="#1E3246")
        btn_frame.pack(fill=tk.X, pady=20)
        
        self.btn_chart = tk.Button(btn_frame, text=t("btn_chart"), bg="#2D3748", fg="white", bd=0, pady=5, command=self._show_history_chart)
        self.btn_chart.pack(fill=tk.X, pady=2)
        self.btn_calendar = tk.Button(btn_frame, text=t("btn_calendar"), bg="#2D3748", fg="white", bd=0, pady=5, command=self._show_calendar_view)
        self.btn_calendar.pack(fill=tk.X, pady=2)
        
        # ML METRICS MINI-DASH
        self.lbl_ml_metrics_section = ttk.Label(right_panel, text=t("ml_metrics_section"), style="Stat.TLabel")
        self.lbl_ml_metrics_section.pack(anchor=tk.W, pady=(20,10))
        
        self.lbl_ml_accuracy = self._create_metric_row(right_panel, t("ml_metric_accuracy"), "N/A", "#9F7AEA")
        self.lbl_ml_samples = self._create_metric_row(right_panel, t("ml_metric_samples"), "0", "#A0AEC0")
        self.lbl_ml_concordance = self._create_metric_row(right_panel, t("ml_metric_concordance"), "--", "#A0AEC0")

        # Initialize ML components
        self._init_ml_components()

    def _create_stat_block(self, parent, label, initial, color):
        frame = tk.Frame(parent, bg="#1E3246")
        frame.pack(fill=tk.X, pady=(0, 15))
        tk.Label(frame, text=label, fg="#829AB1", bg="#1E3246", font=("Segoe UI", 9)).pack(anchor=tk.W)
        lbl = tk.Label(frame, text=initial, fg=color, bg="#1E3246", font=("Segoe UI", 20, "bold"))
        lbl.pack(anchor=tk.W)
        return lbl

    def _create_metric_row(self, parent, label, initial, color):
        frame = tk.Frame(parent, bg="#1E3246")
        frame.pack(fill=tk.X, pady=2)
        tk.Label(frame, text=label, fg="#829AB1", bg="#1E3246", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        lbl = tk.Label(frame, text=initial, fg=color, bg="#1E3246", font=("Segoe UI", 9, "bold"))
        lbl.pack(side=tk.RIGHT)
        return lbl

    def _configure_log_tags(self):
        self.log_area.tag_config("gold", foreground="#F6E05E")     # Yellow
        self.log_area.tag_config("error", foreground="#FC8181")    # Red
        self.log_area.tag_config("state", foreground="#63B3ED")    # Blue
        self.log_area.tag_config("success", foreground="#68D391")  # Green
        self.log_area.tag_config("ml", foreground="#D6BCFA", font=("Consolas", 10, "italic")) # Purple Italic for ML
        self.log_area.tag_config("highlight", foreground="#D9E2EC", font=("Consolas", 10, "bold"))


    def log_message(self, msg):
        self.log_queue.put(msg)

    def update_image(self, cv2_image):
        if cv2_image is not None:
            self.image_queue.put(cv2_image)
            
    def update_stats(self, todays_total_gold, total_history=0, ads_per_hour=0, gold_per_hour=0):
        # Programar actualización en el hilo principal
        def _update():
            # Calcular oro de sesión real (Total Hoy - Inicial al empezar sesión)
            # Si no estamos corriendo, mostramos 0 o el último valor
            session_val = 0
            if self.is_bot_running and self.session_initial_gold >= 0:
                session_val = max(0, todays_total_gold - self.session_initial_gold)
            
            self.current_session_gold = session_val # Guardar para logging

            # Use formatting with separators for thousands
            self.lbl_gold.config(text=f"{session_val:,}")
            self.lbl_gold_history.config(text=f"{total_history:,}")
            self.lbl_speed.config(text=f"{ads_per_hour:.1f} /h")
            self.lbl_gold_speed.config(text=f"{int(gold_per_hour):,} /h")
        self.root.after(0, _update)

    def _start_queue_processing(self):
        self._process_logs()
        self._process_images()
        
    def _process_logs(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_area.config(state=tk.NORMAL)
            
            # Map icons to tags
            icon_map = {
                "💰": "gold", "🤑": "gold",
                "⚠": "error", "❌": "error", "Error": "error",
                "🔄": "state", 
                "✅": "success", "Listo": "success",
                "🧠": "ml", "🧪": "ml", # ML Icons match ML tag
                "👀": "state", "👉": "state", "🔍": "state", "⌨": "state", "🖱": "state"
            }
            
            found_icon = None
            tag_to_use = None
            
            # Find first matching icon
            for icon, tag in icon_map.items():
                if icon in msg:
                    found_icon = icon
                    tag_to_use = tag
                    break
            
            if found_icon:
                parts = msg.split(found_icon, 1)
                self.log_area.insert(tk.END, parts[0]) # Timestamp / Prefix
                self.log_area.insert(tk.END, found_icon, tag_to_use) # Colored Icon
                self.log_area.insert(tk.END, parts[1] + "\n") # Rest of text
            else:
                self.log_area.insert(tk.END, msg + "\n")

            self.log_area.see(tk.END)
            self.log_area.config(state=tk.DISABLED)
            
            # Actualizar status label si el mensaje parece un estado
            # Actualizar status label si el mensaje parece un estado
            if "Estado:" in msg or "CAMBIO ESTADO:" in msg:
                clean_msg = ""
                # Caso 1: Cambio de estado explícito
                if "CAMBIO ESTADO" in msg:
                     # Parsear "CAMBIO ESTADO: X -> Y" => Mostrar "Y"
                     parts = msg.split("->")
                     if len(parts) > 1:
                         new_state = parts[-1].strip()
                         clean_msg = new_state
                # Caso 2: Mensaje de "Estado:" (log directo)
                elif "Estado:" in msg:
                    # Limpiar timestamp y prefijo
                    clean_msg = msg.split("]")[-1].strip()
                    if "Estado:" in clean_msg:
                        clean_msg = clean_msg.split("Estado:")[-1].strip()
                    # Quitar el bullet si lo hubiera
                    clean_msg = clean_msg.replace("•", "").strip()
                
                if clean_msg:
                    self.lbl_status.config(text=clean_msg)

        self.root.after(100, self._process_logs)

    def _process_images(self):
        try:
            # 1. Update Image State if new frame available
            latest_image = None
            while not self.image_queue.empty():
                latest_image = self.image_queue.get_nowait()
            
            if latest_image is not None:
                # Convertir CV2 (BGR) a PIL (RGB)
                rgb_image = cv2.cvtColor(latest_image, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(rgb_image)
                
                # Resize manteniendo aspect ratio
                target_w, target_h = 640, 360
                ratio = min(target_w / pil_image.width, target_h / pil_image.height)
                new_w = int(pil_image.width * ratio)
                new_h = int(pil_image.height * ratio)
                
                pil_image = pil_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
                
                # Store State
                self.current_pil_image = pil_image
                self.current_photo = ImageTk.PhotoImage(pil_image)
                self.current_ratio = ratio
                self.current_x_offset = (target_w - new_w) // 2
                self.current_y_offset = (target_h - new_h) // 2
                
                # Update BG Image Item
                if self.bg_image_id:
                     self.canvas.itemconfig(self.bg_image_id, image=self.current_photo)
                     self.canvas.coords(self.bg_image_id, self.current_x_offset, self.current_y_offset)
                else:
                     self.bg_image_id = self.canvas.create_image(self.current_x_offset, self.current_y_offset, image=self.current_photo, anchor=tk.NW, tags="bg")
                     self.canvas.tag_lower("bg") # Ensure background is always at bottom

            # 2. Update Overlays (Animation Loop)
            if self.current_photo:
                # Clear ONLY overlays
                self.canvas.delete("overlay")
                
                # Draw Active Clicks
                current_time = time.time()
                self.active_clicks = [c for c in self.active_clicks if current_time - c[2] < 1.0]
                
                for (cx, cy, ts) in self.active_clicks:
                    draw_x = self.current_x_offset + (cx * self.current_ratio)
                    draw_y = self.current_y_offset + (cy * self.current_ratio)
                    
                    elapsed = current_time - ts
                    radius_anim = 10 + (elapsed * 20)
                    
                    # Canvas Tags="overlay"
                    self.canvas.create_oval(draw_x-radius_anim, draw_y-radius_anim, draw_x+radius_anim, draw_y+radius_anim, outline="#F56565", width=3, tags="overlay")
                
                # Draw ML Prediction Overlay
                if self.latest_prediction:
                    is_correct, pred_idx, conf, ts = self.latest_prediction
                    if time.time() - ts < 3.0: 
                        color = "#48BB78" if is_correct else "#F56565"
                        text = f"AI: Class {pred_idx} ({conf*100:.0f}%)"
                        self.canvas.create_text(10, 350, anchor=tk.SW, text=text, fill=color, font=("Segoe UI", 12, "bold"), tags="overlay")

        except Exception as e:
            pass
            
        self.root.after(100, self._process_images) # Optimizado a 100ms (10FPS)

    def _run_idle_preview(self):
        """Toma capturas periodicas cuando el bot no está corriendo."""
        while True:
            if not self.is_bot_running:
                try:
                    # Usamos take_screenshot del wrapper (fix SD card ya implementado alli)
                    # Hemos añadido timeout en adb_wrapper para que esto no bloquee
                    img = self.adb_preview.take_screenshot()
                    if img is not None:
                        self.update_image(img)
                except Exception as e:
                    print(f"Error preview idle: {e}")
                    time.sleep(2) # Espera extra si falla
                
                time.sleep(1.5) # 1.5s refresh rate pare idle
            else:
                time.sleep(1) # Dormir mientras el bot corre (él manda las imagenes)

    def visualize_click(self, x, y):
        """Callback para registrar clicks del bot."""
        self.active_clicks.append((x, y, time.time()))

    def visualize_prediction(self, is_correct, pred_idx, confidence, actual_idx):
        """Callback para visualizar predicciones ML."""
        self.latest_prediction = (is_correct, pred_idx, confidence, time.time())

    def _on_language_change(self, event=None):
        """Callback cuando el usuario cambia el idioma en el combobox."""
        selected_idx = self.lang_combo.current()
        lang_codes = get_supported_languages()
        if 0 <= selected_idx < len(lang_codes):
            new_lang = lang_codes[selected_idx]
            if set_language(new_lang):
                self._refresh_all_texts()

    def _refresh_all_texts(self):
        """Actualiza todos los textos de la GUI con el idioma actual."""
        # Título de la ventana
        self.root.title(t("app_title"))
        
        # Panel izquierdo
        self.lbl_header.config(text=t("header_title"))
        self.lbl_battery_label.config(text=t("battery_label"))
        self.lbl_lang_section.config(text=t("language_section"))
        self.lbl_control_section.config(text=t("control_section"))
        self.btn_start.config(text=t("btn_start"))
        self.btn_stop.config(text=t("btn_stop"))
        self.lbl_status_section.config(text=t("status_section"))
        self.btn_capture.config(text=t("btn_capture"))
        self.lbl_ml_section.config(text=t("ml_section"))
        self.btn_ml_train.config(text=t("btn_ml_train"))
        self.btn_ml_test.config(text=t("btn_ml_test"))
        
        # Actualizar botón ML según estado
        if hasattr(self, 'ml_monitor') and self.ml_monitor and self.ml_monitor.is_active:
            self.btn_ml_activate.config(text=t("btn_ml_deactivate"))
        else:
            self.btn_ml_activate.config(text=t("btn_ml_activate"))
        
        # Si el status actual no es un estado del bot, actualizarlo
        current_status = self.lbl_status.cget("text")
        if current_status in ["INACTIVO", "INACTIVE", "INACTIF", "INAKTIV", "INATTIVO"]:
            self.lbl_status.config(text=t("status_inactive"))
        elif current_status in ["Detenido", "Stopped", "Arrêté", "Gestoppt", "Fermato"]:
            self.lbl_status.config(text=t("status_stopped"))
        
        # Panel central
        self.lbl_log_header.config(text=t("log_header"))
        self.lbl_preview_header.config(text=t("preview_header"))
        
        # Panel derecho
        self.lbl_stats_section.config(text=t("stats_section"))
        self.btn_chart.config(text=t("btn_chart"))
        self.btn_calendar.config(text=t("btn_calendar"))
        self.lbl_ml_metrics_section.config(text=t("ml_metrics_section"))

    def start_bot(self):
        if self.bot_thread and self.bot_thread.is_alive():
            return
        
        self.is_bot_running = True
        self.stop_event.clear()
        self.btn_start.config(state=tk.DISABLED)
        self.btn_stop.config(state=tk.NORMAL)
        self.lbl_status.config(text=t("status_starting"), foreground="#63B3ED")
        
        self.bot_thread = threading.Thread(target=self._run_bot_thread, daemon=True)
        self.bot_thread.start()
        
        # Start Session Tracking
        self.session_start_time = datetime.now()
        self.session_initial_gold = self.logger.get_todays_gold() # Snapshot inicio
        self.current_session_gold = 0
        self._update_runtime_timer()

    def _update_runtime_timer(self):
        if self.is_bot_running and self.session_start_time:
            delta = datetime.now() - self.session_start_time
            # Format HH:MM:SS
            total_seconds = int(delta.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            time_str = f"{hours:02}:{minutes:02}:{seconds:02}"
            self.lbl_runtime.config(text=time_str)
            
            self.root.after(1000, self._update_runtime_timer)

    def stop_bot(self):
        if self.bot_thread and self.bot_thread.is_alive():
            self.log_message(t("msg_stopping_bot"))
            self.stop_event.set()
            self.lbl_status.config(text=t("status_stopping"), foreground="#FC8181")
            self.btn_stop.config(state=tk.DISABLED)
            # El botón de iniciar se reactivará cuando muera el hilo

    def _run_bot_thread(self):
        try:
            if not RealRacingBot:
                self.log_message(t("msg_bot_class_not_found"))
                return

            self.bot_instance = RealRacingBot(
                stop_event=self.stop_event,
                log_callback=self.log_message,
                image_callback=self.update_image,
                stats_callback=self.update_stats,
                monitor_callback=self.ml_monitor.submit if self.ml_monitor else None,
                click_callback=self.visualize_click
            )
            self.bot_instance.run()
        except Exception as e:
            self.log_message(t("msg_bot_error", error=str(e)))
        finally:
            # Log Session End
            if self.session_start_time:
                end_time = datetime.now()
                # Log to DB
                self.logger.log_session(self.session_start_time, end_time, self.current_session_gold)
                self.session_start_time = None # Stop timer loop logic check

            self.log_message(t("msg_bot_stopped"))
            self.root.after(0, self._reset_buttons)

        refresh_chart()

    def _capture_screen(self):
        """Captura la pantalla y la guarda en disco."""
        import os
        from datetime import datetime
        
        # Crear directorio si no existe
        if not os.path.exists("screenshots"):
            os.makedirs("screenshots")
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshots/capture_{timestamp}.png"
        
        def save_task():
            try:
                # Prioridad: Bot Instance (si corre), sino ADB Preview
                img = None
                if self.is_bot_running and self.bot_instance:
                    img = self.bot_instance.adb.take_screenshot()
                else:
                    img = self.adb_preview.take_screenshot()
                
                if img is not None:
                    # Save using OpenCV
                    cv2.imwrite(filename, img)
                    self.log_message(t("msg_capture_saved", filename=filename))
                else:
                    self.log_message(t("msg_capture_error"))
            except Exception as e:
                self.log_message(t("msg_capture_failed", error=str(e)))
        
        # Ejecutar en hilo para no bloquear GUI
        threading.Thread(target=save_task, daemon=True).start()

    def _show_history_chart(self):
        """Muestra popup con gráfica de barras navegable."""
        if self.chart_window is not None and self.chart_window.winfo_exists():
            self.chart_window.lift()
            return

        self.chart_offset = 0 # Reset al abrir

        popup = tk.Toplevel(self.root)
        self.chart_window = popup
        popup.title(t("chart_title"))
        popup.geometry("600x450")
        popup.configure(bg="#102A43")
        
        # Header Navegable
        header = tk.Frame(popup, bg="#102A43")
        header.pack(fill=tk.X, padx=20, pady=10)
        
        btn_prev = tk.Button(header, text="◀", font=("Segoe UI", 12), 
                            bg="#102A43", fg="#4FD1C5", bd=0, cursor="hand2",
                            command=lambda: navigate(7)) # Mas antiguo (+offset)
        btn_prev.pack(side=tk.LEFT)
        
        lbl_range = tk.Label(header, text=t("chart_last_days"), font=("Segoe UI", 16, "bold"), 
                            bg="#102A43", fg="#D9E2EC")
        lbl_range.pack(side=tk.LEFT, expand=True)
        
        btn_next = tk.Button(header, text="▶", font=("Segoe UI", 12), 
                            bg="#102A43", fg="#4FD1C5", bd=0, cursor="hand2",
                            command=lambda: navigate(-7)) # Mas reciente (-offset)
        btn_next.pack(side=tk.RIGHT)
        
        # Canvas
        cw, ch = 550, 320
        canvas = tk.Canvas(popup, width=cw, height=ch, bg="#1E3246", highlightthickness=0)
        canvas.pack(pady=10, padx=20)
        
        def navigate(delta):
            self.chart_offset += delta
            if self.chart_offset < 0: self.chart_offset = 0
            refresh_chart()

        def refresh_chart():
            try:
                if not popup.winfo_exists(): return
            except: return
                
            canvas.delete("all")
            
            # Obtener datos con offset
            data = self.logger.get_daily_history(7, offset=self.chart_offset)
            
            # Actualizar etiqueta de rango
            if self.chart_offset == 0:
                lbl_range.config(text=t("chart_last_days"))
                btn_next.config(state=tk.DISABLED, fg="#243B53")
            else:
                end_date = datetime.now() - timedelta(days=self.chart_offset)
                start_date = end_date - timedelta(days=6)
                lbl_range.config(text=f"{start_date.strftime('%d/%m')} - {end_date.strftime('%d/%m')}")
                btn_next.config(state=tk.NORMAL, fg="#4FD1C5")

            if not data:
                canvas.create_text(cw/2, ch/2, text=t("chart_no_data"), fill="#829AB1", font=("Segoe UI", 12))
            else:
                # Max para normalizar
                max_val = max(d[1] for d in data) if data else 1
                if max_val == 0: max_val = 1
                
                bar_width = cw / len(data) * 0.6
                spacing = cw / len(data) * 0.4
                
                margin_bottom = 40
                margin_top = 30
                draw_h = ch - margin_bottom - margin_top
                
                x_start = spacing / 2
                
                for i, (date_str, amount) in enumerate(data):
                    h_bar = (amount / max_val) * draw_h
                    if amount > 0 and h_bar < 2: h_bar = 2
                    
                    x0 = x_start + i * (bar_width + spacing)
                    y0 = ch - margin_bottom
                    x1 = x0 + bar_width
                    y1 = y0 - h_bar
                    
                    # Heatmap Logic (Misma que calendario)
                    color = "#2C5282"
                    if amount > 0:
                        ratio = amount / max_val
                        if ratio < 0.2: color = "#3182CE"
                        elif ratio < 0.4: color = "#38B2AC"
                        elif ratio < 0.6: color = "#48BB78"
                        elif ratio < 0.8: color = "#D69E2E"
                        else: color = "#DD6B20"
                    else:
                        color = "#243B53" # Empty
                    
                    if amount > 0:
                        canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")
                        # Value
                        canvas.create_text((x0+x1)/2, y1 - 10, text=f"{amount}", fill="#FFFFFF", font=("Segoe UI", 9, "bold"))
                    
                    # Date Label
                    try:
                        y, m, d = date_str.split('-')
                        formatted_date = f"{d}/{m}"
                    except:
                        formatted_date = date_str
                    
                    canvas.create_text((x0+x1)/2, y0 + 15, text=formatted_date, fill="#829AB1", font=("Segoe UI", 8))

            # Auto-refresh solo si estamos en offset 0 (Live)
            if self.chart_offset == 0:
                 popup.after(60000, refresh_chart)

        refresh_chart()


    def _show_calendar_view(self):
        """Muestra popup con vista de calendario mensual navegable."""
        # Singleton Check
        if self.calendar_window is not None and self.calendar_window.winfo_exists():
            self.calendar_window.lift()
            return

        import calendar
        
        popup = tk.Toplevel(self.root)
        self.calendar_window = popup
        popup.title(t("calendar_title"))
        popup.geometry("500x420")
        popup.configure(bg="#102A43")
        
        # Estado del mes actual
        current_date = [datetime.now().year, datetime.now().month]
        
        # Header con navegacion
        header = tk.Frame(popup, bg="#102A43")
        header.pack(fill=tk.X, padx=20, pady=10)
        
        btn_prev = tk.Button(header, text="◀", font=("Segoe UI", 14), 
                            bg="#102A43", fg="#4FD1C5", bd=0, cursor="hand2",
                            command=lambda: navigate(-1))
        btn_prev.pack(side=tk.LEFT)
        
        lbl_month = tk.Label(header, text="", font=("Segoe UI", 16, "bold"), 
                            bg="#102A43", fg="#D9E2EC")
        lbl_month.pack(side=tk.LEFT, expand=True)
        
        btn_next = tk.Button(header, text="▶", font=("Segoe UI", 14), 
                            bg="#102A43", fg="#4FD1C5", bd=0, cursor="hand2",
                            command=lambda: navigate(1))
        btn_next.pack(side=tk.RIGHT)
        
        # Canvas para el calendario
        cal_frame = tk.Frame(popup, bg="#1E3246")
        cal_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Dias de la semana
        days_header = tk.Frame(cal_frame, bg="#1E3246")
        days_header.pack(fill=tk.X)
        calendar_days = t("calendar_days")
        for day_name in calendar_days:
            tk.Label(days_header, text=day_name, width=6, font=("Segoe UI", 9, "bold"),
                    bg="#1E3246", fg="#829AB1").pack(side=tk.LEFT, padx=2)
        
        # Grid de dias
        days_grid = tk.Frame(cal_frame, bg="#1E3246")
        days_grid.pack(fill=tk.BOTH, expand=True, pady=5)
        
        day_labels = []
        for row in range(6):
            row_frame = tk.Frame(days_grid, bg="#1E3246")
            row_frame.pack(fill=tk.X)
            row_labels = []
            for col in range(7):
                lbl = tk.Label(row_frame, text="", width=6, height=2, font=("Segoe UI", 9),
                              bg="#243B53", fg="#D9E2EC", relief="flat")
                lbl.pack(side=tk.LEFT, padx=2, pady=2)
                row_labels.append(lbl)
            day_labels.append(row_labels)
        
        def get_month_data(year, month):
            """Obtiene datos de oro para el mes."""
            try:
                with sqlite3.connect(self.logger.db_path) as conn:
                    query = """
                        SELECT substr(timestamp, 1, 10) as day, SUM(amount)
                        FROM gold_history
                        WHERE timestamp LIKE ?
                        GROUP BY day
                    """
                    pattern = f"{year:04d}-{month:02d}-%"
                    cursor = conn.execute(query, (pattern,))
                    return {row[0]: row[1] for row in cursor.fetchall()}
            except:
                return {}
        
        def refresh_calendar():
            # Check if popup still valid
            try:
                if not popup.winfo_exists(): return
            except: return

            year, month = current_date
            month_names = t("calendar_months")
            lbl_month.config(text=f"{month_names[month]} {year}")
            
            # Obtener datos del mes
            month_data = get_month_data(year, month)
            
            # Calcular grid del calendario
            cal = calendar.Calendar(firstweekday=0)  # Lunes primero
            month_days = cal.monthdayscalendar(year, month)
            
            # Calcular Max del mes para normalizar
            max_gold = max(month_data.values()) if month_data else 1
            
            # Limpiar y rellenar
            for row_idx, row_labels in enumerate(day_labels):
                for col_idx, lbl in enumerate(row_labels):
                    if row_idx < len(month_days):
                        day = month_days[row_idx][col_idx]
                        if day == 0:
                            lbl.config(text="", bg="#1E3246")
                        else:
                            day_str = f"{year:04d}-{month:02d}-{day:02d}"
                            gold = month_data.get(day_str, 0)
                            
                            # Heatmap 5 Colores
                            # 1. Azul (Muy bajo) -> 5. Rojo/Naranja (Top)
                            bg_color = "#243B53" # Default (0)
                            fg_color = "#829AB1"
                            
                            if gold > 0:
                                ratio = gold / max_gold
                                
                                if ratio < 0.2:
                                    bg_color = "#3182CE" # Blue 500
                                    fg_color = "#FFFFFF"
                                elif ratio < 0.4:
                                    bg_color = "#38B2AC" # Teal 400
                                    fg_color = "#FFFFFF"
                                elif ratio < 0.6:
                                    bg_color = "#48BB78" # Green 400
                                    fg_color = "#FFFFFF"
                                elif ratio < 0.8:
                                    bg_color = "#D69E2E" # Yellow 600 (Darker for contrast)
                                    fg_color = "#FFFFFF"
                                else:
                                    bg_color = "#DD6B20" # Orange 600
                                    fg_color = "#FFFFFF"
                            
                            display = f"{day}\n{gold}" if gold > 0 else str(day)
                            lbl.config(text=display, bg=bg_color, fg=fg_color)
                    else:
                        lbl.config(text="", bg="#1E3246")
            
            # Schedule next refresh
            popup.after(60000, refresh_calendar)
        
        def navigate(delta):
            current_date[1] += delta
            if current_date[1] > 12:
                current_date[1] = 1
                current_date[0] += 1
            elif current_date[1] < 1:
                current_date[1] = 12
                current_date[0] -= 1
            refresh_calendar()
        
        # Necesitamos importar sqlite3 para la query
        import sqlite3
        
        refresh_calendar()


    def _init_ml_components(self):
        """Inicializa componentes ML."""
        try:
            self.ml_trainer = ModelTrainer()
            self.ml_evaluator = ModelEvaluator()
            self.ml_monitor = LiveMonitor()
            self._update_ml_stats()
            # Iniciar actualizacion periodica (cada 5 segundos)
            self._schedule_ml_stats_update()
        except Exception as e:
            print(f"Error inicializando ML: {e}")
            self.ml_trainer = None
            self.ml_evaluator = None
            self.ml_monitor = None
    
    def _schedule_ml_stats_update(self):
        """Actualiza stats ML periodicamente."""
        self._update_ml_stats()
        self.root.after(5000, self._schedule_ml_stats_update)  # Cada 5 segundos
    
    def _update_ml_stats(self):
        """Actualiza estadisticas ML en la GUI."""
        if not hasattr(self, 'ml_trainer') or not self.ml_trainer:
            return
        
        # Accuracy
        if hasattr(self.ml_evaluator, 'accuracy') and self.ml_evaluator.accuracy > 0:
            self.lbl_ml_accuracy.config(text=f"{self.ml_evaluator.accuracy:.1f}%")
        
        # Capturas nuevas
        samples = self.ml_trainer.get_sample_count()
        color = "#68D391" if samples >= 500 else "#FC8181"  # Verde si >500, rojo si <500
        self.lbl_ml_samples.config(text=str(samples), fg=color)
        
        # Concordancia (si monitor activo)
        if hasattr(self, 'ml_monitor') and self.ml_monitor and self.ml_monitor.is_active:
            stats = self.ml_monitor.get_stats()
            conc = stats.get('concordance', 0)
            if conc >= 99:
                color = "#68D391"  # Verde
            elif conc >= 97:
                color = "#63B3ED"  # Azul
            else:
                color = "#FC8181"  # Rojo
            self.lbl_ml_concordance.config(text=f"{conc:.1f}%", fg=color)
        else:
            self.lbl_ml_concordance.config(text="--", fg="#A0AEC0")
    
    def _ml_train(self):
        """Inicia entrenamiento del modelo."""
        if not self.ml_trainer:
            self.lbl_ml_status.config(text=t("ml_error_not_initialized"))
            return
        
        if self.ml_trainer.is_training:
            self.lbl_ml_status.config(text=t("ml_status_training"))
            return
        
        samples = self.ml_trainer.get_sample_count()
        if samples < 10:
            self.lbl_ml_status.config(text=t("ml_error_min_samples", count=samples))
            return
        
        self.btn_ml_train.config(state=tk.DISABLED)
        self.lbl_ml_status.config(text=t("ml_training_started"))
        
        def on_complete(success, accuracy):
            self.root.after(0, lambda: self._on_training_complete(success, accuracy))
        
        self.ml_trainer.train(epochs=10, callback=on_complete)
        
        # Iniciar timer para actualizar progreso
        self._update_training_progress()
    
    def _update_training_progress(self):
        """Actualiza progreso de entrenamiento."""
        if not self.ml_trainer or not self.ml_trainer.is_training:
            return
        
        # Obtener logs
        logs = self.ml_trainer.get_logs()
        for log in logs:
            self.lbl_ml_status.config(text=log)
            # También enviar al log principal para persistencia
            self.log_message(f"🧠 {log}")
        
        # Actualizar cada 500ms
        self.root.after(500, self._update_training_progress)
    
    def _on_training_complete(self, success, accuracy):
        """Callback cuando termina el entrenamiento."""
        self.btn_ml_train.config(state=tk.NORMAL)
        if success:
            self.lbl_ml_status.config(text=t("ml_training_complete", accuracy=f"{accuracy:.1f}"))
            self.lbl_ml_accuracy.config(text=f"{accuracy:.1f}%")
        else:
            self.lbl_ml_status.config(text=t("ml_training_error"))
        self._update_ml_stats()
    
    def _ml_test(self):
        """Ejecuta test del modelo."""
        if not self.ml_evaluator:
            self.lbl_ml_status.config(text=t("ml_error_not_initialized"))
            return
        
        self.lbl_ml_status.config(text=t("ml_status_evaluating"))
        self.btn_ml_test.config(state=tk.DISABLED)
        
        def _run_test():
            self.log_message("🧪 Monitor: Iniciando evaluación...")
            result = self.ml_evaluator.evaluate()
            self.root.after(0, lambda: self._on_test_complete(result))
        
        import threading
        threading.Thread(target=_run_test, daemon=True).start()
    
    def _on_test_complete(self, result):
        """Callback cuando termina el test."""
        self.btn_ml_test.config(state=tk.NORMAL)
        if "error" in result:
            self.lbl_ml_status.config(text=f"Error: {result['error']}")
        else:
            acc = result.get('accuracy', 0)
            total = result.get('total_samples', 0)
            self.log_message(f"🧪 Test Completo: {acc:.1f}% ({total} muestras)")
            self.lbl_ml_status.config(text=f"Test: {acc:.1f}% ({total} muestras)")
            self.lbl_ml_accuracy.config(text=f"{acc:.1f}%")
    
    def _ml_toggle_monitor(self):
        """Activa/desactiva monitor en tiempo real."""
        if not self.ml_monitor:
            self.lbl_ml_status.config(text=t("ml_error_not_initialized"))
            self.log_message(t("ml_error_not_initialized"))
            return
        
        if self.ml_monitor.is_active:
            self.ml_monitor.stop()
            self.btn_ml_activate.config(text=t("btn_ml_activate"), bg="#805AD5")
            self.lbl_ml_status.config(text=t("ml_status_monitor_stopped"))
            self.log_message(t("ml_status_monitor_stopped"))
            self.lbl_ml_concordance.config(text="--", fg="#A0AEC0")
        else:
            if not self.ml_monitor.model.is_trained:
                self.lbl_ml_status.config(text=t("ml_error_not_trained"))
                self.log_message(t("ml_error_not_trained"))
                return
            self.ml_monitor.start(prediction_callback=self.visualize_prediction)
            self.btn_ml_activate.config(text=t("btn_ml_deactivate"), bg="#C53030")
            self.lbl_ml_status.config(text=t("ml_status_monitor_active"))
            self.log_message(t("ml_status_monitor_active"))
            self._update_monitor_stats()
    
    def _update_monitor_stats(self):
        """Actualiza estadisticas del monitor."""
        if not self.ml_monitor or not self.ml_monitor.is_active:
            return
        
        stats = self.ml_monitor.get_stats()
        conc = stats.get('concordance', 0)
        
        if conc >= 99:
            color = "#68D391"  # Verde
        elif conc >= 97:
            color = "#63B3ED"  # Azul
        else:
            color = "#FC8181"  # Rojo
        
        self.lbl_ml_concordance.config(text=f"{conc:.1f}%", fg=color)
        
        # Actualizar cada segundo
        self.root.after(1000, self._update_monitor_stats)

    def _reset_buttons(self):
        self.is_bot_running = False
        self.btn_start.config(state=tk.NORMAL)
        self.btn_stop.config(state=tk.DISABLED)
        self.lbl_status.config(text=t("status_stopped"), foreground="#A0AEC0")

    # open_scrcpy removed

def main():
    root = tk.Tk()
    # Intentar cargar icono si existe
    # root.iconbitmap("assets/icon.ico") 
    app = BotGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
